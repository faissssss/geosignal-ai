#!/usr/bin/env python3
"""Extract SRTM contour lines per kecamatan and persist contour_features (Phase D).

Downloads SRTMGL1_003 elevation for each kecamatan boundary (90 m), extracts
contour LineStrings at a fixed interval with matplotlib, and persists them to
``contour_features`` with provenance.  A failed download records status
``unavailable``; no rows are fabricated.

Usage:
  python scripts/ingest_contours.py --dry-run
  python scripts/ingest_contours.py --regions ntt ntb central_kalimantan
"""
from __future__ import annotations

import argparse
import io
import os
import uuid
import zipfile
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
import requests
from dotenv import load_dotenv
from shapely.geometry import LineString, shape
from supabase import create_client

from geosignal.gee_extract import SRTM_IMAGE_ID, initialize_gee

REGIONS = ("ntt", "ntb", "central_kalimantan")
DATASET = "srtm_contours"
CONTOUR_INTERVAL_M = 200
DEM_SCALE_M = 90
BUFFER_DEG = 0.05
ATTRIBUTION = "SRTMGL1 v003 (NASA/USGS)"
SOURCE_URL = "https://doi.org/10.5067/MEaSUREs/SRTM/SRTMGL1.003"
SOURCE_VERSION = "SRTMGL1_003"
SOURCE_DATE = "2015-01-01"


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


def _download_dem(boundary_geojson: dict) -> tuple[np.ndarray, rasterio.Affine]:
    """Download SRTM elevation for the kecamatan bbox; returns (dem, transform)."""
    import ee  # noqa: PLC0415

    initialize_gee()
    geom = shape(boundary_geojson)
    minx, miny, maxx, maxy = geom.bounds
    region = ee.Geometry.Rectangle(
        [minx - BUFFER_DEG, miny - BUFFER_DEG, maxx + BUFFER_DEG, maxy + BUFFER_DEG]
    )
    image = ee.Image(SRTM_IMAGE_ID).select("elevation")
    url = image.getDownloadURL(
        {"scale": DEM_SCALE_M, "region": region, "format": "GEO_TIFF"}
    )
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    with _open_tiff(resp.content) as src:
        dem = src.read(1).astype(np.float64)
        transform = src.transform
    return dem, transform


def _extract_contours(
    dem: np.ndarray,
    transform: rasterio.Affine,
    interval_m: int,
) -> list[dict]:
    """Return contour features [{elevation_m, geom_geojson}] from a DEM array."""
    height, width = dem.shape
    lon = np.array([transform.c + i * transform.a for i in range(width)])
    lat = np.array([transform.f + i * transform.e for i in range(height)])
    lon_grid, lat_grid = np.meshgrid(lon, lat)

    finite = dem[np.isfinite(dem)]
    if finite.size == 0:
        return []
    vmin = np.floor(finite.min() / interval_m) * interval_m
    vmax = np.ceil(finite.max() / interval_m) * interval_m
    levels = np.arange(vmin, vmax + interval_m, interval_m)
    if levels.size == 0:
        return []

    fig, ax = plt.subplots()
    try:
        cs = ax.contour(lon_grid, lat_grid, dem, levels=levels)
        features: list[dict] = []
        for level, segs in zip(cs.levels, cs.allsegs):
            for seg in segs:
                if len(seg) < 2:
                    continue
                coords = [[float(x), float(y)] for x, y in seg]
                # Simplify long flat-terrain lines (Douglas-Peucker) so the
                # GeoJSON payload stays bounded for huge lowland kecamatan.
                line = LineString(coords)
                if line.length > 0:
                    line = line.simplify(0.001, preserve_topology=True)
                simplified = [[float(x), float(y)] for x, y in line.coords]
                if len(simplified) < 2:
                    continue
                features.append(
                    {
                        "elevation_m": float(level),
                        "geom_geojson": {
                            "type": "LineString",
                            "coordinates": simplified,
                        },
                    }
                )
        return features
    finally:
        plt.close(fig)


def _record_source_run(client, region_id: str, count: int, status: str) -> str:
    run_id = str(uuid.uuid4())
    client.table("source_runs").insert(
        {
            "run_id": run_id,
            "dataset": DATASET,
            "region_id": region_id,
            "source_url": SOURCE_URL,
            "source_version": SOURCE_VERSION,
            "source_date": SOURCE_DATE,
            "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
            "records_count": count,
            "metadata": {"attribution": ATTRIBUTION, "interval_m": CONTOUR_INTERVAL_M},
            "status": status,
        }
    ).execute()
    return run_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="+", choices=REGIONS, default=list(REGIONS))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    # Idempotency: skip regions already extracted with an ok run.
    existing = (
        client.table("source_runs")
        .select("run_id,region_id,status")
        .eq("dataset", DATASET)
        .execute()
        .data
        or []
    )
    done = {r["region_id"] for r in existing if r.get("status") == "ok"}

    boundaries = (
        client.table("admin_boundaries")
        .select("kecamatan_id,kecamatan_name,region_id,boundary_geojson")
        .execute()
        .data
        or []
    )
    by_region: dict[str, list[dict]] = {}
    for b in boundaries:
        by_region.setdefault(b["region_id"], []).append(b)

    for region_id in args.regions:
        if region_id in done:
            print(f"[{region_id}] already extracted; skipping.")
            continue
        if region_id not in by_region:
            print(f"[{region_id}] no admin boundaries; recording unavailable.")
            if not args.dry_run:
                _record_source_run(client, region_id, 0, "unavailable")
            continue

        total = 0
        failed = 0
        for b in by_region[region_id]:
            kecamatan_id = b["kecamatan_id"]
            print(f"  [{kecamatan_id}] {b['kecamatan_name']} ...", flush=True)
            try:
                dem, transform = _download_dem(b["boundary_geojson"])
                features = _extract_contours(dem, transform, CONTOUR_INTERVAL_M)
            except Exception as exc:  # noqa: BLE001
                print(f"    FAILED: {type(exc).__name__}: {str(exc)[:120]}")
                failed += 1
                continue

            if args.dry_run:
                print(f"    dry-run: {len(features)} contour lines")
                total += len(features)
                continue

            rows = [
                {
                    "feature_id": str(uuid.uuid4()),
                    "region_id": region_id,
                    "kecamatan_id": kecamatan_id,
                    "elevation_m": f["elevation_m"],
                    "status": "real",
                    "geom_geojson": f["geom_geojson"],
                }
                for f in features
            ]
            for i in range(0, len(rows), 100):
                client.table("contour_features").insert(rows[i : i + 100]).execute()
            total += len(rows)
            print(f"    inserted {len(rows)} contour lines")

        status = "ok" if total > 0 else ("unavailable" if failed else "ok")
        if not args.dry_run:
            _record_source_run(client, region_id, total, status)
        print(f"[{region_id}] total {total} contour lines ({failed} kecamatan failed)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())