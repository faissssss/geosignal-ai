#!/usr/bin/env python3
"""Extract real GEE raster values for every stored kecamatan (Phase 2).

Loads the 45 kecamatan boundaries from Supabase, generates analysis points
inside each polygon, samples SRTM / WorldCover / canopy / WorldPop via GEE,
writes the sampled records to a local parquet cache, and records one
``source_runs`` row per region with dataset metadata.

Usage:
  python scripts/extract_gee.py --dry-run
  python scripts/extract_gee.py --regions ntt ntb central_kalimantan
  python scripts/extract_gee.py --spacing 500 --max-points 3000
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

from geosignal.gee_extract import (
    BAND_CANOPY,
    BAND_ELEVATION,
    BAND_LAND_COVER,
    BAND_POPULATION,
    BAND_SLOPE,
    extract_kecamatan,
)

REGIONS = ("ntt", "ntb", "central_kalimantan")
OUTPUT_DIR = Path("data/gee_extract")


def _load_boundaries(client, regions: list[str]) -> list[dict]:
    rows = (
        client.table("admin_boundaries")
        .select("kecamatan_id,kecamatan_name,region_id,boundary_geojson")
        .in_("region_id", regions)
        .execute()
        .data
        or []
    )
    return sorted(rows, key=lambda r: (r["region_id"], r["kecamatan_name"]))


def _record_source_run(client, region_id: str, records: int, spacing_m: int) -> str:
    """Insert a source_runs row for the GEE extraction; returns run_id."""
    run_id = str(uuid.uuid4())
    client.table("source_runs").insert(
        {
            "run_id": run_id,
            "dataset": "gee_raster_sample",
            "region_id": region_id,
            "source_url": "Earth Engine (SRTMGL1_003, WorldCover/v200, "
            "ETH_GlobalCanopyHeight_2020_10m_v1, WorldPop/GP/100m/pop)",
            "source_version": "srtm-v3/worldcover-v200/canopy-2020/worldpop-2020",
            "source_date": "2020-01-01",
            "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
            "records_count": records,
            "metadata": {"spacing_m": spacing_m, "bands": [BAND_ELEVATION, BAND_SLOPE, BAND_LAND_COVER, BAND_CANOPY, BAND_POPULATION]},
            "status": "ok",
        }
    ).execute()
    return run_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="+", choices=REGIONS, default=list(REGIONS))
    parser.add_argument("--spacing", type=float, default=500.0, help="Grid spacing in metres.")
    parser.add_argument("--max-points", type=int, default=3000, help="Cap per kecamatan.")
    parser.add_argument("--dry-run", action="store_true", help="Sample but do not write to Supabase.")
    args = parser.parse_args()

    load_dotenv()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    boundaries = _load_boundaries(client, args.regions)
    print(f"Loaded {len(boundaries)} kecamatan boundaries for {args.regions}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total_records = 0
    per_region: dict[str, int] = {}

    for boundary in boundaries:
        region_id = boundary["region_id"]
        kecamatan_id = boundary["kecamatan_id"]
        name = boundary["kecamatan_name"]
        print(f"  [{region_id}] {name} ({kecamatan_id}) ...", end=" ", flush=True)
        try:
            records = extract_kecamatan(
                boundary["boundary_geojson"],
                spacing_m=args.spacing,
                max_points=args.max_points,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"FAILED: {type(exc).__name__}: {str(exc)[:150]}")
            return 1

        if not records:
            print("0 points (no valid geometry)")
            continue

        df = pd.DataFrame(records)
        df["region_id"] = region_id
        df["kecamatan_id"] = kecamatan_id
        df["kecamatan_name"] = name
        out_path = OUTPUT_DIR / f"{region_id}__{kecamatan_id}.parquet"
        df.to_parquet(out_path, index=False)
        print(f"{len(records)} records -> {out_path.name}")
        total_records += len(records)
        per_region[region_id] = per_region.get(region_id, 0) + len(records)

    print(f"\nTotal sampled records: {total_records}")
    print(f"Per region: {per_region}")

    if args.dry_run:
        print("Dry run — no source_runs written.")
        return 0

    for region_id, count in per_region.items():
        run_id = _record_source_run(client, region_id, count, args.spacing)
        print(f"source_run {run_id} recorded for {region_id} ({count} records)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())