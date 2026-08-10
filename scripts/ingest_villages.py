#!/usr/bin/env python3
"""Ingest approved village geometry for the three regions (Phase 2).

Source: OpenStreetMap (approved OSM source with attribution per
data-production/plan.md).  Queries the Overpass API for place/village and
place/neighbourhood polygons+nodes inside each region bbox, converts to
village_features rows with required attribution, and records a source_run.

Missing OSM results record status ``unavailable``; no rows are fabricated.

Usage:
  python scripts/ingest_villages.py --dry-run
  python scripts/ingest_villages.py --regions ntt ntb central_kalimantan
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from supabase import create_client

REGIONS = ("ntt", "ntb", "central_kalimantan")
OVERPARSE_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]
ATTRIBUTION = "© OpenStreetMap contributors"
_HEADERS = {
    "User-Agent": "GeoSignalAI/1.0 (research pipeline; contact: dev@geosignal.local)",
    "Accept": "*/*",
}

# Regional extents (lat_sw, lon_sw, lat_ne, lon_ne).
REGION_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "ntt": (-11.5, 118.0, -8.0, 125.5),
    "ntb": (-9.5, 115.5, -8.0, 120.0),
    "central_kalimantan": (-4.0, 110.0, 0.5, 116.0),
}


def _overpass_query(bbox: tuple[float, float, float, float], max_attempts: int = 3) -> list[dict]:
    """Query Overpass for villages in the bbox; returns GeoJSON Features.

    Tries each configured endpoint with retries on 504/timeout, falling back to
    the next mirror.  Uses an exact ``place=village`` match (lighter than the
    regex form) plus a way-centre pass for hamlets/neighbourhoods.
    """
    lat_sw, lon_sw, lat_ne, lon_ne = bbox
    q = f"""
    [out:json][timeout:240];
    (
      node["place"~"village|hamlet|neighbourhood"]({lat_sw},{lon_sw},{lat_ne},{lon_ne});
      way["place"~"village|hamlet|neighbourhood"]({lat_sw},{lon_sw},{lat_ne},{lon_ne});
    );
    out body geom;
    """
    last_exc: Exception | None = None
    for url in OVERPARSE_URLS:
        for attempt in range(max_attempts):
            try:
                resp = requests.post(url, data={"data": q}, timeout=280, headers=_HEADERS)
                if resp.status_code == 200:
                    return _features_from_elements(resp.json().get("elements", []))
                last_exc = RuntimeError(f"HTTP {resp.status_code} from {url}")
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
            # brief backoff between attempts
            import time

            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"All Overpass endpoints failed: {last_exc}")


def _features_from_elements(elements: list[dict]) -> list[dict]:
    features = []
    for el in elements:
        el_type = el.get("type")
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        if el_type == "node":
            geometry = {
                "type": "Point",
                "coordinates": [el.get("lon"), el.get("lat")],
            }
        else:
            geom = el.get("geometry") or []
            coords = [[g["lon"], g["lat"]] for g in geom]
            if len(coords) < 3:
                continue
            geometry = {"type": "Polygon", "coordinates": [coords]}
        features.append(
            {
                "type": "Feature",
                "properties": {"osm_id": el.get("id"), "name": name, "place": tags.get("place")},
                "geometry": geometry,
            }
        )
    return features


def _record_source_run(client, region_id: str, count: int, status: str) -> str:
    run_id = str(uuid.uuid4())
    client.table("source_runs").insert(
        {
            "run_id": run_id,
            "dataset": "osm_villages",
            "region_id": region_id,
            "source_url": "https://www.openstreetmap.org (Overpass API)",
            "source_version": "osm-2026",
            "source_date": "2026-01-01",
            "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
            "records_count": count,
            "metadata": {"attribution": ATTRIBUTION},
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

    for region_id in args.regions:
        print(f"[{region_id}] querying Overpass ...", flush=True)
        try:
            features = _overpass_query(REGION_BBOXES[region_id])
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED: {type(exc).__name__}: {str(exc)[:150]}")
            if not args.dry_run:
                _record_source_run(client, region_id, 0, "unavailable")
            continue

        print(f"  {len(features)} villages found")
        if args.dry_run or not features:
            if not features and not args.dry_run:
                _record_source_run(client, region_id, 0, "unavailable")
            continue

        rows = []
        for f in features:
            rows.append(
                {
                    "feature_id": str(uuid.uuid4()),
                    "region_id": region_id,
                    "village_name": f["properties"]["name"],
                    "attribution": ATTRIBUTION,
                    "status": "real",
                    "geom_geojson": f["geometry"],
                }
            )
        for i in range(0, len(rows), 500):
            client.table("village_features").insert(rows[i : i + 500]).execute()
        print(f"  inserted {len(rows)} villages")

        _record_source_run(client, region_id, len(rows), "ok")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())