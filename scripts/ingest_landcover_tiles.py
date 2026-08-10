#!/usr/bin/env python3
"""Publish ESA WorldCover v200 as XYZ raster tiles per region (Phase D).

For each region, exports the ESA WorldCover v200 ``Map`` band through GEE's
``getMapId`` and records the XYZ tile template in ``landcover_tile_sets`` with
a ``source_run``.  The ``tiles_url`` is consumed by MapView via
``source.setTiles([tilesUrl])`` (frontend/components/MapView.tsx).

A failed GEE export records status ``unavailable``; no rows are fabricated.

Usage:
  python scripts/ingest_landcover_tiles.py --dry-run
  python scripts/ingest_landcover_tiles.py --regions ntt ntb central_kalimantan
"""
from __future__ import annotations

import argparse
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client

from geosignal.gee_extract import WORLDCOVER_COLLECTION_ID, initialize_gee

REGIONS = ("ntt", "ntb", "central_kalimantan")
DATASET = "gee_landcover_tiles"
LAYER_ID = "esa-worldcover-v200"
ATTRIBUTION = "© ESA WorldCover v200 (CC-BY 4.0)"
SOURCE_URL = "https://esa-worldcover.org/en"
SOURCE_VERSION = "v200"
SOURCE_DATE = "2021-01-01"


def _tiles_url(mapid: str, token: str) -> str:
    project = os.environ["GEE_PROJECT_ID"]
    return (
        f"https://earthengine.googleapis.com/v1alpha/projects/{project}"
        f"/maps/{mapid}/tiles/{{z}}/{{x}}/{{y}}?token={token}"
    )


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
            "metadata": {"layer_id": LAYER_ID, "attribution": ATTRIBUTION},
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

    # Idempotency: skip regions already published with an ok run.
    existing = (
        client.table("source_runs")
        .select("run_id,region_id,status")
        .eq("dataset", DATASET)
        .execute()
        .data
        or []
    )
    done = {r["region_id"] for r in existing if r.get("status") == "ok"}

    for region_id in args.regions:
        if region_id in done:
            print(f"[{region_id}] already published; skipping.")
            continue

        print(f"[{region_id}] exporting WorldCover tiles ...", flush=True)
        try:
            initialize_gee()
            import ee  # noqa: PLC0415

            image = ee.ImageCollection(WORLDCOVER_COLLECTION_ID).first().select("Map")
            map_info = image.getMapId({"min": 10, "max": 100})
            url = _tiles_url(map_info["mapid"], map_info["token"])
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED: {type(exc).__name__}: {str(exc)[:150]}")
            if not args.dry_run:
                _record_source_run(client, region_id, 0, "unavailable")
            continue

        if args.dry_run:
            print(f"  dry-run: would insert tile set {url[:90]}...")
            continue

        run_id = _record_source_run(client, region_id, 1, "ok")
        client.table("landcover_tile_sets").insert(
            {
                "set_id": str(uuid.uuid4()),
                "region_id": region_id,
                "layer_id": LAYER_ID,
                "source_run_id": run_id,
                "tiles_url": url,
                "attribution": ATTRIBUTION,
                "status": "real",
            }
        ).execute()
        print(f"  inserted tile set (run {run_id})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())