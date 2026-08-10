#!/usr/bin/env python3
"""Generate real BTS candidates + LOS + what-if precompute for target areas (Phase D).

For each target area (kecamatan-scoped):
  1. Loads real grid_cells for the kecamatan.
  2. Downloads SRTM + WorldCover + canopy rasters for the kecamatan bbox.
  3. Precomputes terrain-aware LOS between canopy-passing cells
     (``geosignal.los.precompute_los_grid``) and persists ``los_results``.
  4. Ranks candidates (``geosignal.candidates.rank_bts_candidates``) and
     persists ``bts_candidates`` rows (data_source='derived').
  5. Precomputes one what-if row per candidate (``whatif_grid``) from
     LOS-clear neighbours within the signal radius.

A target area whose LOS/DEM step fails records a ``source_run`` with status
``unavailable``; no candidate rows are fabricated.

Usage:
  python scripts/generate_candidates.py --dry-run
  python scripts/generate_candidates.py --target-area <uuid>
"""
from __future__ import annotations

import argparse
import io
import os
import uuid
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import rasterio
import requests
from affine import Affine
from dotenv import load_dotenv
from shapely.geometry import shape
from sklearn.neighbors import BallTree
from supabase import create_client

from geosignal.adapters import AHPAdapter
from geosignal.candidates import rank_bts_candidates
from geosignal.confidence import ConfidenceThresholds
from geosignal.constraints import is_high_canopy
from geosignal.gee_extract import (
    BAND_CANOPY,
    BAND_ELEVATION,
    BAND_LAND_COVER,
    BAND_POPULATION,
    BAND_SLOPE,
    CANOPY_IMAGE_ID,
    SRTM_IMAGE_ID,
    WORLDCOVER_COLLECTION_ID,
    initialize_gee,
)
from geosignal.los import precompute_los_grid
from geosignal.models import CONSOLIDATED_FEATURES, InsufficientCandidatesResult

REGIONS = ("ntt", "ntb", "central_kalimantan")
EXTRACT_DIR = Path("data/gee_extract")
OOKLA_DIR = Path("data/ookla")
DATASET = "bts_candidates"
MODEL_VERSION = "ahp-tier1-v1"
RESOLUTION_M = 100
SIGNAL_RADIUS_M = 5000.0
LOS_MAX_RANGE_M = 5000.0
COVERAGE_IMPROVEMENT = 15.0
GOOD_THRESHOLD = 70.0
N_CANDIDATES = 10
DEM_SCALE_M = 90
BUFFER_DEG = 0.05

REGION_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "ntt": (-11.5, 118.0, -8.0, 125.5),
    "ntb": (-9.5, 115.5, -8.0, 120.0),
    "central_kalimantan": (-4.0, 110.0, 0.5, 116.0),
}

_FEATURE_FIELDS = list(CONSOLIDATED_FEATURES)


def _fetch_all(client, table: str, select: str, **filters) -> list[dict]:
    """Fetch all rows with pagination (Supabase default page is 1000)."""
    rows: list[dict] = []
    page = 1000
    start = 0
    while True:
        q = client.table(table).select(select)
        for k, v in filters.items():
            q = q.eq(k, v)
        batch = q.range(start, start + page - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page:
            break
        start += page
    return rows


def _load_towers(client) -> dict[str, np.ndarray]:
    """Return {region_id: (N, 2) radian [lat, lon] array} of real towers."""
    rows = _fetch_all(client, "bts_locations", "region_id,lat,lon", status="real")
    by_region: dict[str, list[tuple[float, float]]] = {}
    for r in rows:
        by_region.setdefault(r["region_id"], []).append((r["lat"], r["lon"]))
    return {
        rid: np.radians(np.array(pts, dtype=np.float64))
        for rid, pts in by_region.items()
        if pts
    }


def _load_ookla_tiles(region_id: str) -> np.ndarray:
    """Return (N, 2) radian [lat, lon] tile centroids for a region (fixed+mobile)."""
    pts: list[tuple[float, float]] = []
    lat_sw, lon_sw, lat_ne, lon_ne = REGION_BBOXES[region_id]
    for kind in ("fixed", "mobile"):
        path = OOKLA_DIR / f"2024-Q4_{kind}.parquet"
        if not path.exists():
            continue
        table = ds.dataset(path, format="parquet").to_table(
            columns=["tile_x", "tile_y"],
            filter=(
                (ds.field("tile_x") >= lon_sw)
                & (ds.field("tile_x") <= lon_ne)
                & (ds.field("tile_y") >= lat_sw)
                & (ds.field("tile_y") <= lat_ne)
            ),
        )
        for row in table.to_pylist():
            pts.append((row["tile_y"], row["tile_x"]))
    if not pts:
        return np.empty((0, 2))
    return np.radians(np.array(pts, dtype=np.float64))


def _nearest_km(tree: BallTree | None, point_rad: np.ndarray) -> float:
    if tree is None:
        return float("inf")
    dist, _ = tree.query(point_rad.reshape(1, -1), k=1)
    return float(dist[0, 0]) * 6371.0


def _load_extract(region_id: str, kecamatan_id: str) -> pd.DataFrame:
    files = sorted(EXTRACT_DIR.glob(f"{region_id}__{kecamatan_id}.parquet"))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[0])


def _open_tiff(data: bytes):
    """Open a GEE download payload as a rasterio dataset.

    GEE returns a raw GeoTIFF for single-band downloads and a ZIP of GeoTIFFs
    for multi-band downloads; both are handled here.
    """
    if data[:2] == b"MM" or data[:4] == b"II*\x00":  # TIFF magic
        return rasterio.open(io.BytesIO(data))
    z = zipfile.ZipFile(io.BytesIO(data))
    tif_name = next(n for n in z.namelist() if n.endswith(".tif"))
    return rasterio.open(z.open(tif_name))


def _download_rasters(
    boundary_geojson: dict,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, Affine, str]:
    """Download elevation/land_cover/canopy GeoTIFFs for the kecamatan bbox.

    Returns (dem, land_cover, canopy, transform, crs).  Land cover and canopy
    are resampled (nearest) onto the DEM grid so all three arrays share a
    shape.  Nodata pixels are filled with 0.0 (no elevation / no canopy /
    unknown class) so the LOS raster validation passes; sampled values are
    never invented.
    """
    import ee  # noqa: PLC0415

    from rasterio.warp import Resampling, reproject

    initialize_gee()
    geom = shape(boundary_geojson)
    minx, miny, maxx, maxy = geom.bounds
    region = ee.Geometry.Rectangle(
        [minx - BUFFER_DEG, miny - BUFFER_DEG, maxx + BUFFER_DEG, maxy + BUFFER_DEG]
    )
    specs = [
        ("dem", ee.Image(SRTM_IMAGE_ID).select("elevation")),
        (
            "land_cover",
            ee.ImageCollection(WORLDCOVER_COLLECTION_ID).first().select("Map"),
        ),
        ("canopy", ee.Image(CANOPY_IMAGE_ID).select("b1")),
    ]
    bands: dict[str, tuple[np.ndarray, Affine, str]] = {}
    for name, image in specs:
        url = image.getDownloadURL(
            {"scale": DEM_SCALE_M, "region": region, "format": "GEO_TIFF"}
        )
        resp = requests.get(url, timeout=300)
        resp.raise_for_status()
        with _open_tiff(resp.content) as src:
            bands[name] = (src.read(1), src.transform, src.crs.to_string())

    dem, transform, crs = bands["dem"]
    dem = np.nan_to_num(dem.astype(np.float64), nan=0.0)
    dst_shape = dem.shape

    def _resample(name: str) -> np.ndarray:
        arr, src_transform, src_crs = bands[name]
        dst = np.empty(dst_shape, dtype=np.float64)
        reproject(
            source=arr.astype(np.float64),
            destination=dst,
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=transform,
            dst_crs=crs,
            resampling=Resampling.nearest,
        )
        return np.nan_to_num(dst, nan=0.0)

    land_cover = _resample("land_cover")
    canopy = _resample("canopy")
    return dem, land_cover, canopy, transform, crs


def _build_los_index(los_records: list[dict], region_id: str) -> dict:
    """candidate_key -> {cell_key: los_clear} (duplicates OR'd to True)."""
    index: dict[tuple[float, float], dict[tuple[float, float], bool]] = defaultdict(dict)
    for rec in los_records:
        if rec.get("region_id") != region_id:
            continue
        ck = (round(float(rec["candidate_lat"]), 7), round(float(rec["candidate_lon"]), 7))
        nk = (round(float(rec["cell_lat"]), 7), round(float(rec["cell_lon"]), 7))
        index[ck][nk] = index[ck].get(nk, False) or bool(rec["los_clear"])
    return dict(index)


def _record_source_run(client, region_id: str, count: int, status: str, metadata: dict) -> str:
    run_id = str(uuid.uuid4())
    client.table("source_runs").insert(
        {
            "run_id": run_id,
            "dataset": DATASET,
            "region_id": region_id,
            "source_url": "derived from grid_cells + SRTM LOS",
            "source_version": MODEL_VERSION,
            "source_date": datetime.now(tz=timezone.utc).date().isoformat(),
            "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
            "records_count": count,
            "metadata": metadata,
            "status": status,
        }
    ).execute()
    return run_id


def _whatif_rows(
    candidate_id: str,
    cand_lat: float,
    cand_lon: float,
    region_id: str,
    los_index: dict,
    cell_coords: np.ndarray,
    cell_ids: list[str],
    cell_scores: np.ndarray,
    tree: BallTree,
    radius_rad: float,
) -> dict:
    """Compute the single aggregate what-if row for one candidate."""
    cand_key = (round(cand_lat, 7), round(cand_lon, 7))
    neighbours = los_index.get(cand_key, {})

    indices = tree.query_radius(np.radians([[cand_lat, cand_lon]]), r=radius_rad)[0]
    affected = [
        int(i)
        for i in indices
        if neighbours.get(
            (round(float(cell_coords[int(i), 0]), 7), round(float(cell_coords[int(i), 1]), 7)),
            False,
        )
    ]

    n_total = len(cell_scores)
    n_good_before = int(np.sum(cell_scores >= GOOD_THRESHOLD))

    after = cell_scores.copy()
    if affected:
        after[affected] = np.clip(
            cell_scores[affected] + COVERAGE_IMPROVEMENT, 0.0, 100.0
        )
    n_good_after = int(np.sum(after >= GOOD_THRESHOLD))

    # Snap to the nearest grid cell.
    snap_idx = int(tree.query(np.radians([[cand_lat, cand_lon]]), k=1)[1][0][0])

    return {
        "scenario_id": str(uuid.uuid4()),
        "region_id": region_id,
        "candidate_id": candidate_id,
        "snapped_lat": float(cell_coords[snap_idx, 0]),
        "snapped_lon": float(cell_coords[snap_idx, 1]),
        "grid_resolution_m": RESOLUTION_M,
        "delta_coverage_score": (
            float(np.mean(after[affected] - cell_scores[affected])) if affected else 0.0
        ),
        "pct_good_change": float((n_good_after - n_good_before) / max(n_total, 1) * 100.0),
        "villages_newly_covered": max(0, n_good_after - n_good_before),
        "new_coverage_score": float(after[snap_idx]),
        "grid_cell_id": cell_ids[snap_idx],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-area", type=str, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    adapter = AHPAdapter()
    thresholds = ConfidenceThresholds()

    tas = (
        client.table("target_areas")
        .select("target_area_id,region_id,kecamatan_id,boundary_geojson")
        .execute()
        .data
        or []
    )
    if args.target_area:
        tas = [t for t in tas if t["target_area_id"] == args.target_area]
    if not tas:
        print("No target areas to process.")
        return 1

    by_kec: dict[str, list[dict]] = defaultdict(list)
    for t in tas:
        by_kec[t["kecamatan_id"]].append(t)

    towers_by_region = _load_towers(client)
    ookla_by_region = {rid: _load_ookla_tiles(rid) for rid in REGIONS}

    for kecamatan_id, area_list in by_kec.items():
        region_id = area_list[0]["region_id"]
        print(f"\n=== {kecamatan_id} ({region_id}) — {len(area_list)} target area(s) ===", flush=True)

        cells = _fetch_all(
            client,
            "grid_cells",
            "cell_id,region_id,kecamatan_id,lat,lon,coverage_score,model_version,scoring_run_id",
            kecamatan_id=kecamatan_id,
            data_source="real",
        )
        if not cells:
            print("  no real grid_cells; recording unavailable.")
            for ta in area_list:
                if not args.dry_run:
                    _record_source_run(
                        client, region_id, 0, "unavailable",
                        {"target_area_id": ta["target_area_id"], "reason": "no real grid_cells"},
                    )
            continue

        df = _load_extract(region_id, kecamatan_id)
        if df.empty:
            print("  no extraction parquet; recording unavailable.")
            for ta in area_list:
                if not args.dry_run:
                    _record_source_run(
                        client, region_id, 0, "unavailable",
                        {"target_area_id": ta["target_area_id"], "reason": "no extraction parquet"},
                    )
            continue

        # Align parquet features to grid_cells by rounded coordinate.
        feat_by_key = {}
        for _, row in df.iterrows():
            feat_by_key[(round(float(row["lat"]), 6), round(float(row["lon"]), 6))] = row

        cell_coords = np.array([[c["lat"], c["lon"]] for c in cells], dtype=np.float64)
        cell_ids = [c["cell_id"] for c in cells]
        cell_scores = np.array([c["coverage_score"] for c in cells], dtype=np.float64)
        cells_rad = np.radians(cell_coords)

        land_cover_classes = np.full(len(cells), -1, dtype=np.int64)
        canopy_heights = np.full(len(cells), np.nan, dtype=np.float64)
        matrix = np.full((len(cells), 8), np.inf, dtype=np.float64)
        for i, c in enumerate(cells):
            row = feat_by_key.get((round(c["lat"], 6), round(c["lon"], 6)))
            if row is None:
                continue
            land_cover_classes[i] = int(row[BAND_LAND_COVER])
            canopy_heights[i] = float(row[BAND_CANOPY])
            matrix[i, 0] = float(row[BAND_ELEVATION])
            matrix[i, 1] = float(row[BAND_SLOPE])
            matrix[i, 2] = float(row[BAND_LAND_COVER])
            matrix[i, 3] = float(row[BAND_CANOPY])
            matrix[i, 6] = float(row[BAND_POPULATION])

        # Distance-to-BTS from real towers (same as run_scoring.py).
        tower_pts = towers_by_region.get(region_id)
        tower_tree = BallTree(tower_pts, metric="haversine") if tower_pts is not None and len(tower_pts) else None
        if tower_tree is not None:
            dist_m, _ = tower_tree.query(cells_rad, k=1)
            matrix[:, 4] = dist_m[:, 0] * 6371000.0

        # Confidence source distances.
        ookla_pts = ookla_by_region.get(region_id)
        ookla_tree = BallTree(ookla_pts, metric="haversine") if ookla_pts is not None and len(ookla_pts) else None
        ocid_km = [_nearest_km(tower_tree, cells_rad[i]) for i in range(len(cells))]
        ookla_km = [_nearest_km(ookla_tree, cells_rad[i]) for i in range(len(cells))]

        # Pseudo-SHAP attribution (Tier 1 AHP), aligned with grid_cells order.
        shap_matrix = adapter.shap_values(matrix)
        shap_by_cell = [
            {feat: float(shap_matrix[i, j]) for j, feat in enumerate(_FEATURE_FIELDS)}
            for i in range(len(cells))
        ]

        # Canopy-passing cells become candidate positions.
        candidate_mask = np.array(
            [
                not is_high_canopy(int(land_cover_classes[i]), float(canopy_heights[i]))
                for i in range(len(cells))
            ],
            dtype=bool,
        )
        candidate_coords = cell_coords[candidate_mask]
        print(f"  cells={len(cells)} canopy-passing candidates={len(candidate_coords)}", flush=True)

        if len(candidate_coords) < 2:
            print("  fewer than 2 candidate positions; recording unavailable.")
            for ta in area_list:
                if not args.dry_run:
                    _record_source_run(
                        client, region_id, 0, "unavailable",
                        {"target_area_id": ta["target_area_id"], "reason": "canopy filter left <2 cells"},
                    )
            continue

        # LOS precompute (persists los_results).
        try:
            dem, land_cover_raster, canopy_raster, transform, crs = _download_rasters(
                area_list[0]["boundary_geojson"]
            )
            los_records = precompute_los_grid(
                region_id=region_id,
                candidate_coordinates=candidate_coords,
                cell_coordinates=cell_coords,
                dem=dem,
                transform=transform,
                raster_crs=crs,
                land_cover=land_cover_raster,
                canopy_height=canopy_raster,
                max_range_m=LOS_MAX_RANGE_M,
                supabase_client=None if args.dry_run else client,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  LOS FAILED: {type(exc).__name__}: {str(exc)[:150]}")
            for ta in area_list:
                if not args.dry_run:
                    _record_source_run(
                        client, region_id, 0, "unavailable",
                        {"target_area_id": ta["target_area_id"], "reason": f"LOS failed: {str(exc)[:100]}"},
                    )
            continue

        print(f"  los_records={len(los_records)}", flush=True)
        los_index = _build_los_index(los_records, region_id)

        tree = BallTree(np.radians(cell_coords), metric="haversine")
        radius_rad = SIGNAL_RADIUS_M / 6371008.8

        for ta in area_list:
            target_area_id = ta["target_area_id"]
            print(f"  -- target_area {target_area_id}", flush=True)

            # Idempotency: skip target areas that already have derived candidates.
            existing_cands = (
                client.table("bts_candidates")
                .select("candidate_id")
                .eq("target_area_id", target_area_id)
                .eq("data_source", "derived")
                .limit(1)
                .execute()
                .data
                or []
            )
            if existing_cands:
                print("    already generated; skipping.")
                continue

            ranked = rank_bts_candidates(
                grid_cells=cell_coords,
                coverage_scores=cell_scores,
                land_cover_classes=land_cover_classes,
                canopy_heights_m=canopy_heights,
                los_records=los_records,
                shap_values_by_cell=shap_by_cell,
                region_id=region_id,
                target_area_id=target_area_id,
                model_version=MODEL_VERSION,
                scoring_run_id=cells[0]["scoring_run_id"],
                nearest_opencellid_km=ocid_km,
                nearest_ookla_km=ookla_km,
                n_candidates=N_CANDIDATES,
                signal_radius_m=SIGNAL_RADIUS_M,
                confidence_thresholds=thresholds,
            )

            if isinstance(ranked, InsufficientCandidatesResult):
                print(f"    insufficient candidates: {ranked.reason}")
                if not args.dry_run:
                    _record_source_run(
                        client, region_id, 0, "unavailable",
                        {"target_area_id": target_area_id, "reason": ranked.reason},
                    )
                continue

            if args.dry_run:
                print(f"    dry-run: {len(ranked)} candidates")
                continue

            run_id = _record_source_run(
                client, region_id, len(ranked), "ok",
                {"target_area_id": target_area_id, "model_version": MODEL_VERSION},
            )
            cand_rows = []
            whatif_rows = []
            for cand in ranked:
                cand_id = str(uuid.uuid4())
                cand_rows.append(
                    {
                        "candidate_id": cand_id,
                        "region_id": region_id,
                        "target_area_id": target_area_id,
                        "rank": cand.rank,
                        "lat": float(cand.coordinate[0]),
                        "lon": float(cand.coordinate[1]),
                        "expected_improvement": round(float(cand.expected_improvement), 4),
                        "los_validated": True,
                        "confidence_tag": cand.confidence_tag,
                        "shap_values": cand.shap_values,
                        "model_version": cand.model_version,
                        "scoring_run_id": cand.scoring_run_id,
                        "excluded_by_canopy": False,
                        "kecamatan_id": kecamatan_id,
                        "data_source": "derived",
                        "source_run_id": run_id,
                    }
                )
                whatif_rows.append(
                    _whatif_rows(
                        cand_id,
                        float(cand.coordinate[0]),
                        float(cand.coordinate[1]),
                        region_id,
                        los_index,
                        cell_coords,
                        cell_ids,
                        cell_scores,
                        tree,
                        radius_rad,
                    )
                )
            for i in range(0, len(cand_rows), 500):
                client.table("bts_candidates").insert(cand_rows[i : i + 500]).execute()
            for i in range(0, len(whatif_rows), 500):
                client.table("whatif_grid").insert(whatif_rows[i : i + 500]).execute()
            print(f"    inserted {len(cand_rows)} candidates + {len(whatif_rows)} what-if rows")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())