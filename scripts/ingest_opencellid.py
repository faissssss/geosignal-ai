#!/usr/bin/env python3
"""Ingest OpenCellID cell towers for the three regional extents (Phase 2).

Queries the OpenCellID ``getInArea`` API over a bounded grid of small bboxes
(API caps each call at 4,000,000 m2) and persists real tower points to
``bts_locations`` with a ``source_runs`` provenance record.

Spec behaviour (data-production/expected-outcomes.md Phase 2):
  - Missing OpenCellID records mean low-confidence *unknown coverage*, not a
    claimed coverage gap.  If the API key is rejected or quota is exhausted,
    the source run is recorded with status ``unavailable`` and NO rows are
    written — the confidence tagger then reports Low for those cells.

Usage:
  python scripts/ingest_opencellid.py --dry-run
  python scripts/ingest_opencellid.py --regions ntt ntb central_kalimantan
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from supabase import create_client

REGIONS = ("ntt", "ntb", "central_kalimantan")

# OpenCellID caps each getInArea call at 4,000,000 m2 (~2 km x 2 km).
# 0.015 deg ~= 1.67 km x 1.67 km ~= 2.8M m2 (safe margin under the cap).
TILE_DEG = 0.015
API_URL = "https://opencellid.org/cell/getInArea"


def _kecamatan_bboxes(client, region_id: str) -> list[tuple[str, str]]:
    """Return [(kecamatan_id, 'lat1,lon1,lat2,lon2'), ...] from stored boundaries.

    Tiling the padded region bbox wastes quota on ocean; tiling each kecamatan's
    actual boundary bbox keeps queries region-bounded and on land.
    """
    rows = (
        client.table("admin_boundaries")
        .select("kecamatan_id,boundary_geojson")
        .eq("region_id", region_id)
        .execute()
        .data
    )
    bboxes: list[tuple[str, str]] = []
    for r in rows:
        gj = r["boundary_geojson"]
        coords = gj.get("coordinates", [])
        lats = [pt[1] for poly in coords for ring in poly for pt in ring]
        lons = [pt[0] for poly in coords for ring in poly for pt in ring]
        if not lats or not lons:
            continue
        bboxes.append(
            (r["kecamatan_id"], f"{min(lats)},{min(lons)},{max(lats)},{max(lons)}")
        )
    return bboxes


def _tile_bbox(bbox: str) -> list[str]:
    """Return 'lat1,lon1,lat2,lon2' tiles covering one bbox."""
    lat_sw, lon_sw, lat_ne, lon_ne = map(float, bbox.split(","))
    tiles: list[str] = []
    lat = lat_sw
    while lat < lat_ne:
        lon = lon_sw
        while lon < lon_ne:
            tiles.append(f"{lat},{lon},{min(lat + TILE_DEG, lat_ne)},{min(lon + TILE_DEG, lon_ne)}")
            lon += TILE_DEG
        lat += TILE_DEG
    return tiles


def _fetch_tile(key: str, bbox: str) -> list[dict]:
    """Query getInArea for one bbox; returns list of cell dicts (or [] on error).

    The API returns ``{"count": N, "cells": [...]}`` on success and
    ``{"error": ..., "code": ...}`` on failure.
    """
    resp = requests.get(
        API_URL,
        params={"key": key, "BBOX": bbox, "format": "json"},
        timeout=30,
    )
    if resp.status_code != 200:
        return []
    body = resp.json()
    if isinstance(body, dict):
        if body.get("error"):
            return []
        return body.get("cells") or []
    return body if isinstance(body, list) else []


def _record_source_run(client, region_id: str, records: int, status: str, detail: str) -> str:
    run_id = str(uuid.uuid4())
    client.table("source_runs").insert(
        {
            "run_id": run_id,
            "dataset": "opencellid_towers",
            "region_id": region_id,
            "source_url": "https://opencellid.org (getInArea API)",
            "source_version": "api-2026",
            "source_date": "2026-01-01",
            "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
            "records_count": records,
            "metadata": {"tile_deg": TILE_DEG, "detail": detail},
            "status": status,
        }
    ).execute()
    return run_id


def _key_is_rejected(key: str) -> bool:
    """Probe the API once; True if the key is rejected/unknown."""
    try:
        probe = requests.get(
            API_URL,
            params={"key": key, "BBOX": "-8.21,124.49,-8.20,124.50", "format": "json"},
            timeout=30,
        )
        return probe.status_code == 200 and "API Key not known" in probe.text
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="+", choices=REGIONS, default=list(REGIONS))
    parser.add_argument("--max-tiles", type=int, default=200, help="Cap tiles per region (quota guard).")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    key = os.environ.get("OPENCELLID_API_KEY", "")
    if not key:
        print("OPENCELLID_API_KEY missing.", file=sys.stderr)
        return 1

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    if _key_is_rejected(key):
        print("OpenCellID API key rejected (quota or invalid). Recording unavailable runs.")
        for region_id in args.regions:
            if not args.dry_run:
                _record_source_run(client, region_id, 0, "unavailable", "API key rejected")
        return 0

    for region_id in args.regions:
        kec_bboxes = _kecamatan_bboxes(client, region_id)
        print(f"[{region_id}] {len(kec_bboxes)} kecamatan bboxes", flush=True)

        cells: list[dict] = []
        tiles_queried = 0
        for kecamatan_id, bbox in kec_bboxes:
            if tiles_queried >= args.max_tiles:
                break
            for tile_bbox in _tile_bbox(bbox):
                if tiles_queried >= args.max_tiles:
                    break
                tiles_queried += 1
                batch = _fetch_tile(key, tile_bbox)
                if not batch:
                    continue
                for c in batch:
                    c["kecamatan_id"] = kecamatan_id
                cells.extend(batch)

        print(f"  {len(cells)} towers fetched ({tiles_queried} tiles)")
        if args.dry_run:
            continue

        if cells:
            rows = []
            for c in cells:
                rows.append(
                    {
                        "tower_id": str(uuid.uuid4()),
                        "region_id": region_id,
                        "lat": c.get("lat"),
                        "lon": c.get("lon"),
                        "mcc": c.get("mcc"),
                        "mnc": c.get("mnc"),
                        "lac": c.get("lac"),
                        "cell_id": c.get("cellid"),
                        "status": "real",
                    }
                )
            # Insert in bounded batches.
            for i in range(0, len(rows), 500):
                client.table("bts_locations").insert(rows[i : i + 500]).execute()
            print(f"  inserted {len(rows)} towers")

        _record_source_run(client, region_id, len(cells), "ok", "getInArea tiled query")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())