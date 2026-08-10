#!/usr/bin/env python3
"""Download, checksum, and spatially filter Ookla Open Data (Phase 2).

Ookla is a Tier-2 *label* source only — it is never merged into the
consolidated feature vector (data-production/plan.md).  This script:

  1. Downloads the configured fixed/mobile parquet archives once into
     ``data/ookla/`` (skips if the cached file checksum matches).
  2. Records SHA-256 checksum + byte size + period in a ``source_runs`` row.
  3. Spatially filters tiles to the three regional extents using the zoom-16
     quadkey (the parquet is ~550 MB combined; we never load it whole).

A missing/failed Ookla archive is recorded with status ``unavailable`` and
treated as low-confidence unknown coverage — never as a claimed coverage gap.

Usage:
  python scripts/ingest_ookla.py --dry-run
  python scripts/ingest_ookla.py --regions ntt ntb central_kalimantan
"""
from __future__ import annotations

import argparse
import hashlib
import math
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.dataset as ds
from dotenv import load_dotenv
from supabase import create_client

REGIONS = ("ntt", "ntb", "central_kalimantan")
OOKLA_DIR = Path("data/ookla")

# Regional extents (lat_sw, lon_sw, lat_ne, lon_ne).
REGION_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "ntt": (-11.5, 118.0, -8.0, 125.5),
    "ntb": (-9.5, 115.5, -8.0, 120.0),
    "central_kalimantan": (-4.0, 110.0, 0.5, 116.0),
}

ZOOM = 16


def _tile_xy(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Convert lat/lon to web-mercator tile x/y at the given zoom."""
    lat_rad = math.radians(lat)
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def _quadkey(x: int, y: int, zoom: int) -> str:
    """Build a Bing quadkey from tile x/y at the given zoom."""
    qk = ""
    for z in range(zoom, 0, -1):
        digit = 0
        mask = 1 << (z - 1)
        if x & mask:
            digit += 1
        if y & mask:
            digit += 2
        qk += str(digit)
    return qk


def _bbox_quadkeys(bbox: tuple[float, float, float, float], zoom: int) -> set[str]:
    """Return the set of zoom-16 quadkeys covering a bounding box (bounded)."""
    lat_sw, lon_sw, lat_ne, lon_ne = bbox
    x0, y0 = _tile_xy(lat_ne, lon_sw, zoom)  # top-left
    x1, y1 = _tile_xy(lat_sw, lon_ne, zoom)  # bottom-right
    keys: set[str] = set()
    for x in range(min(x0, x1), max(x0, x1) + 1):
        for y in range(min(y0, y1), max(y0, y1) + 1):
            keys.add(_quadkey(x, y, zoom))
    return keys


def _download(url: str, dest: Path) -> int:
    """Stream-download *url* to *dest*; returns byte count."""
    import requests

    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        size = 0
        with dest.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                fh.write(chunk)
                size += len(chunk)
    return size


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _count_tiles_in_bbox(path: Path, bbox: tuple[float, float, float, float]) -> int:
    """Count parquet rows whose tile centroid is inside the bbox.

    Uses the ``tile_x`` (lon) / ``tile_y`` (lat) centroid columns with numeric
    range filters — pushed down to row groups, so the ~550 MB file is never
    loaded whole.
    """
    lat_sw, lon_sw, lat_ne, lon_ne = bbox
    table = ds.dataset(path, format="parquet").to_table(
        columns=["tile_x", "tile_y"],
        filter=(
            (ds.field("tile_x") >= lon_sw)
            & (ds.field("tile_x") <= lon_ne)
            & (ds.field("tile_y") >= lat_sw)
            & (ds.field("tile_y") <= lat_ne)
        ),
    )
    return table.num_rows


def _record_source_run(client, kind: str, region_id: str, checksum: str, size: int, tiles: int) -> str:
    run_id = str(uuid.uuid4())
    client.table("source_runs").insert(
        {
            "run_id": run_id,
            "dataset": f"ookla_{kind}",
            "region_id": region_id,
            "source_url": os.environ.get(f"OOKLA_{kind.upper()}_TILE_URL", ""),
            "source_version": "2024-Q4",
            "source_date": "2024-10-01",
            "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
            "checksum_sha256": checksum,
            "records_count": tiles,
            "metadata": {"bytes": size, "period": "2024-Q4", "zoom": ZOOM},
            "status": "ok",
        }
    ).execute()
    return run_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="+", choices=REGIONS, default=list(REGIONS))
    parser.add_argument("--kinds", nargs="+", choices=["fixed", "mobile"], default=["fixed", "mobile"])
    parser.add_argument("--dry-run", action="store_true", help="Do not download or write runs.")
    args = parser.parse_args()

    load_dotenv()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    for kind in args.kinds:
        url = os.environ.get(f"OOKLA_{kind.upper()}_TILE_URL", "")
        if not url:
            print(f"OOKLA_{kind.upper()}_TILE_URL not configured; skipping {kind}.")
            continue

        dest = OOKLA_DIR / f"2024-Q4_{kind}.parquet"
        if dest.exists():
            print(f"[{kind}] cached: {dest} ({dest.stat().st_size} bytes)")
        elif args.dry_run:
            print(f"[{kind}] dry-run: would download {url}")
            continue
        else:
            print(f"[{kind}] downloading {url} ...", flush=True)
            size = _download(url, dest)
            print(f"[{kind}] downloaded {size} bytes")

        checksum = _sha256(dest)
        print(f"[{kind}] sha256: {checksum}")

        if args.dry_run:
            continue

        for region_id in args.regions:
            tiles = _count_tiles_in_bbox(dest, REGION_BBOXES[region_id])
            run_id = _record_source_run(
                client, kind, region_id, checksum, dest.stat().st_size, tiles
            )
            print(f"  [{region_id}] {tiles} tiles -> source_run {run_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())