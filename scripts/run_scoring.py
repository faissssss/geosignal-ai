#!/usr/bin/env python3
"""Score real GEE-sampled cells and persist production grid_cells (Phase 3).

Loads the per-kecamatan GEE extraction parquets (data/gee_extract/), builds the
eight-feature vector per cell, computes a Tier-1 AHP coverage score, tags
confidence from real source proximity, and persists rows to ``grid_cells`` with
``data_source='real'`` plus provenance (source_run_id, scoring_run_id,
kecamatan_id).

Spec behaviour (data-production/expected-outcomes.md Phase 3):
  - Each of the 45 kecamatan gets at least one non-demo heatmap cell contained
    by its own boundary.
  - Missing OpenCellID / Ookla records produce an explicit Low confidence state
    (unknown coverage), never a claimed coverage gap.
  - Low-score cells are modelled coverage gaps; provenance stays visible.

Usage:
  python scripts/run_scoring.py --dry-run
  python scripts/run_scoring.py --regions ntt ntb central_kalimantan
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
from dotenv import load_dotenv
from sklearn.neighbors import BallTree
from supabase import create_client

from geosignal.adapters import AHPAdapter
from geosignal.confidence import ConfidenceThresholds, tag_confidence
from geosignal.gee_extract import (
    BAND_CANOPY,
    BAND_ELEVATION,
    BAND_LAND_COVER,
    BAND_POPULATION,
    BAND_SLOPE,
)

REGIONS = ("ntt", "ntb", "central_kalimantan")
EXTRACT_DIR = Path("data/gee_extract")
OOKLA_DIR = Path("data/ookla")
MODEL_VERSION = "ahp-tier1-v1"
RESOLUTION_M = 100
ZOOM = 16

# Regional extents (lat_sw, lon_sw, lat_ne, lon_ne) for Ookla tile filtering.
REGION_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "ntt": (-11.5, 118.0, -8.0, 125.5),
    "ntb": (-9.5, 115.5, -8.0, 120.0),
    "central_kalimantan": (-4.0, 110.0, 0.5, 116.0),
}

# FeatureVector fields in CONSOLIDATED_FEATURES order (models.py).
_FEATURE_FIELDS = [
    "elevation_m",
    "slope_deg",
    "land_cover_class",
    "canopy_height_m",
    "distance_to_bts_m",
    "road_distance_m",
    "population_density_per_km2",
    "facility_proximity_m",
]


def _load_extract(region_id: str) -> pd.DataFrame:
    files = sorted(EXTRACT_DIR.glob(f"{region_id}__*.parquet"))
    frames = [pd.read_parquet(f) for f in files]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _load_towers(client) -> dict[str, np.ndarray]:
    """Return {region_id: (N, 2) radian [lat, lon] array} of real towers."""
    rows = client.table("bts_locations").select("region_id,lat,lon").eq("status", "real").execute().data or []
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
    """Distance in km from a point to the nearest member of a BallTree."""
    if tree is None:
        return float("inf")
    dist, _ = tree.query(point_rad.reshape(1, -1), k=1)
    return float(dist[0, 0]) * 6371.0  # radians -> km


def _build_feature_matrix(df: pd.DataFrame) -> np.ndarray:
    """Build the (N, 8) feature matrix in CONSOLIDATED_FEATURES order.

    Distance-to-BTS / road / facility are unknown (OpenCellID unavailable and
    no road/POI source ingested) — represented as ``inf`` so the confidence
    tagger reports Low (unknown coverage), never a fabricated value.
    """
    cols = {
        "elevation_m": BAND_ELEVATION,
        "slope_deg": BAND_SLOPE,
        "land_cover_class": BAND_LAND_COVER,
        "canopy_height_m": BAND_CANOPY,
        "population_density_per_km2": BAND_POPULATION,
    }
    matrix = np.full((len(df), 8), np.inf, dtype=np.float64)
    for feat_idx, feat in enumerate(_FEATURE_FIELDS):
        if feat in cols:
            matrix[:, feat_idx] = df[cols[feat]].fillna(0.0).to_numpy(dtype=np.float64)
    return matrix


def _record_scoring_run(client, region_id: str, kecamatan_ids: list[str], count: int) -> str:
    run_id = str(uuid.uuid4())
    client.table("scoring_runs").insert(
        {
            "run_id": run_id,
            "model_version": MODEL_VERSION,
            "tier": "1",
            "region_kecamatans": kecamatan_ids,
            "resolution_m": RESOLUTION_M,
            "input_checksums": {"source": "gee_extract_parquet"},
            "candidate_count": count,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "retained_for_months": 12,
        }
    ).execute()
    return run_id


def _ensure_model_artifact(client) -> None:
    """Register the Tier-1 AHP artifact (FK target for grid_cells.model_version)."""
    client.table("model_artifacts").upsert(
        {
            "version_id": MODEL_VERSION,
            "tier": "1",
            "algorithm": "AHP-weighted ensemble (Tier 1 cold start)",
            "training_run_id": None,
            "artifact_path": "/model_artifacts/ahp-tier1-v1",
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
    ).execute()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="+", choices=REGIONS, default=list(REGIONS))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    adapter = AHPAdapter()
    thresholds = ConfidenceThresholds()
    _ensure_model_artifact(client)

    towers_by_region = _load_towers(client)
    for rid, arr in towers_by_region.items():
        print(f"  towers[{rid}]: {len(arr)}")

    # Map kecamatan_id -> source_run_id from the GEE extraction runs.
    runs = client.table("source_runs").select("run_id,region_id").eq("dataset", "gee_raster_sample").execute().data or []
    source_run_by_region = {r["region_id"]: r["run_id"] for r in runs}

    total_cells = 0
    for region_id in args.regions:
        df = _load_extract(region_id)
        if df.empty:
            print(f"[{region_id}] no extraction data; skipping.")
            continue

        kecamatan_ids = sorted(df["kecamatan_id"].unique())
        print(f"[{region_id}] {len(df)} sampled cells across {len(kecamatan_ids)} kecamatan")

        # Real BTS distance + confidence source (OpenCellID towers).
        tower_pts = towers_by_region.get(region_id)
        tower_tree = BallTree(tower_pts, metric="haversine") if tower_pts is not None and len(tower_pts) else None

        # Ookla tiles (fixed+mobile) as the second confidence source.
        ookla_pts = _load_ookla_tiles(region_id)
        ookla_tree = BallTree(ookla_pts, metric="haversine") if len(ookla_pts) else None
        print(f"  ookla tiles: {len(ookla_pts)}")

        # Batch predict: AHPAdapter normalises via batch min-max, so scoring
        # must happen over the full region matrix, not per-row.
        matrix = _build_feature_matrix(df)
        cells_rad = np.radians(df[["lat", "lon"]].to_numpy(dtype=np.float64))

        if tower_tree is not None:
            dist_m, _ = tower_tree.query(cells_rad, k=1)  # radians
            matrix[:, 4] = dist_m[:, 0] * 6371000.0  # distance_to_bts_m
            print(f"  distance_to_bts_m: min {matrix[:, 4].min():.0f} m, median {np.median(matrix[:, 4]):.0f} m")

        scores = adapter.predict(matrix)  # (N,) in [0, 100]

        rows = []
        for i, (_, row) in enumerate(df.iterrows()):
            point = (row["lat"], row["lon"])
            confidence = tag_confidence(
                point,
                nearest_opencellid_km=_nearest_km(tower_tree, cells_rad[i]),
                nearest_ookla_km=_nearest_km(ookla_tree, cells_rad[i]),
                thresholds=thresholds,
            )
            rows.append(
                {
                    "cell_id": str(uuid.uuid4()),
                    "region_id": region_id,
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "resolution_m": RESOLUTION_M,
                    "coverage_score": round(float(scores[i]), 2),
                    "confidence_tag": confidence,
                    "tier_used": "1",
                    "shap_top3": None,
                    "model_version": MODEL_VERSION,
                    "kecamatan_id": row["kecamatan_id"],
                    "data_source": "real",
                    "source_run_id": source_run_by_region.get(region_id),
                }
            )

        if args.dry_run:
            print(f"  dry-run: would insert {len(rows)} real cells")
            total_cells += len(rows)
            continue

        scoring_run_id = _record_scoring_run(client, region_id, kecamatan_ids, len(rows))
        for i in range(0, len(rows), 500):
            batch = rows[i : i + 500]
            for r in batch:
                r["scoring_run_id"] = scoring_run_id
            client.table("grid_cells").insert(batch).execute()
        print(f"  inserted {len(rows)} real cells (scoring_run {scoring_run_id})")
        total_cells += len(rows)

    print(f"\nTotal real cells: {total_cells}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())