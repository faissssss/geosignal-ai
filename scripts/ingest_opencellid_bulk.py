#!/usr/bin/env python3
"""Ingest OpenCellID towers via the bulk country CSV export (Phase 2).

Downloads Indonesia's cell-tower CSV (MCC 510) once, filters to the three
regional extents, and persists real tower points to ``bts_locations`` with a
``source_runs`` provenance record.

Why bulk instead of tiled getInArea:
  - Full regional coverage via the API needs ~190k sequential calls (26-53 h)
    and the API drops connections under sustained load.
  - The bulk CSV is one download (2/day/token limit) + local spatial filter.

Spec behaviour (data-production/expected-outcomes.md Phase 2):
  - Missing OpenCellID records mean low-confidence *unknown coverage*, not a
    claimed coverage gap.  If the download fails, the source run is recorded
    with status ``unavailable`` and NO rows are written.

Usage:
  python scripts/ingest_opencellid_bulk.py --dry-run
  python scripts/ingest_opencellid_bulk.py
"""
from __future__ import annotations

import argparse
import gzip
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv
from supabase import create_client

REGIONS = ("ntt", "ntb", "central_kalimantan")
MCC_INDONESIA = 510
# Working bulk endpoint (downloads.php is a JS form page). Worldwide dump,
# filtered locally by MCC 510 + region bboxes.
DOWNLOAD_URL = "https://download.unwiredlabs.com/ocid/downloads"
DOWNLOAD_PARAMS = {"file": "cell_towers.csv.gz"}
DATA_DIR = Path("data/opencellid")
CSV_GZ = DATA_DIR / "cell_towers.csv.gz"
CSV_PLAIN = DATA_DIR / "cell_towers.csv"

# OpenCellID CSV columns (computed cell towers export).
CSV_COLUMNS = [
    "radio", "mcc", "net", "area", "cell", "unit", "lon", "lat",
    "range", "samples", "changeable", "created", "updated",
    "averageSignal",
]


def _region_bboxes(client) -> dict[str, tuple[float, float, float, float]]:
    """Union of kecamatan bboxes per region (tighter than padded extents)."""
    bboxes: dict[str, tuple[float, float, float, float]] = {}
    rows = (
        client.table("admin_boundaries")
        .select("region_id,boundary_geojson")
        .execute()
        .data
    )
    for r in rows:
        coords = r["boundary_geojson"].get("coordinates", [])
        lats = [pt[1] for poly in coords for ring in poly for pt in ring]
        lons = [pt[0] for poly in coords for ring in poly for pt in ring]
        if not lats or not lons:
            continue
        region = r["region_id"]
        if region not in bboxes:
            bboxes[region] = (min(lats), min(lons), max(lats), max(lons))
        else:
            lo_lat, lo_lon, hi_lat, hi_lon = bboxes[region]
            bboxes[region] = (
                min(lo_lat, min(lats)),
                min(lo_lon, min(lons)),
                max(hi_lat, max(lats)),
                max(hi_lon, max(lons)),
            )
    return bboxes


def _download(key: str) -> Path:
    """Stream-download the worldwide CSV.gz with a .part file (resume-safe)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    part = DATA_DIR / "cell_towers.csv.gz.part"

    headers = {}
    if part.exists() and part.stat().st_size > 0:
        headers["Range"] = f"bytes={part.stat().st_size}-"

    with requests.get(
        DOWNLOAD_URL,
        params={"token": key, **DOWNLOAD_PARAMS},
        headers=headers,
        stream=True,
        timeout=60,
    ) as resp:
        if resp.status_code not in (200, 206):
            raise RuntimeError(f"download failed: HTTP {resp.status_code} {resp.text[:200]}")
        mode = "ab" if resp.status_code == 206 else "wb"
        with open(part, mode) as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                if chunk:
                    fh.write(chunk)

    part.rename(CSV_GZ)
    return CSV_GZ


def _load_and_filter(csv_gz: Path, bboxes: dict) -> pd.DataFrame:
    """Read the gz CSV, filter to region bboxes, return deduped tower rows."""
    with gzip.open(csv_gz, "rt", encoding="utf-8", errors="replace") as fh:
        df = pd.read_csv(fh, low_memory=False)

    # Keep only Indonesia MCC (safety) and drop rows missing coordinates.
    df = df[(df["mcc"] == MCC_INDONESIA) & df["lat"].notna() & df["lon"].notna()]

    # Assign region by bbox containment (union of kecamatan bboxes).
    region_of: list[str] = []
    for _, row in df.iterrows():
        region = None
        for rid, (lo_lat, lo_lon, hi_lat, hi_lon) in bboxes.items():
            if lo_lat <= row["lat"] <= hi_lat and lo_lon <= row["lon"] <= hi_lon:
                region = rid
                break
        region_of.append(region)
    df["region_id"] = region_of
    df = df[df["region_id"].notna()]

    # Dedup by (mcc, net, area, cell) keeping the first occurrence.
    df = df.drop_duplicates(subset=["mcc", "net", "area", "cell"], keep="first")
    return df


def _record_source_run(client, region_id: str, records: int, status: str, detail: str) -> str:
    run_id = str(uuid.uuid4())
    client.table("source_runs").insert(
        {
            "run_id": run_id,
            "dataset": "opencellid_towers",
            "region_id": region_id,
            "source_url": "https://opencellid.org (bulk CSV export, MCC 510)",
            "source_version": "bulk-2026",
            "source_date": "2026-01-01",
            "ingested_at": datetime.now(tz=timezone.utc).isoformat(),
            "records_count": records,
            "metadata": {"method": "bulk_csv", "detail": detail},
            "status": status,
        }
    ).execute()
    return run_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="+", choices=REGIONS, default=list(REGIONS))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-download", action="store_true", help="Use existing CSV if present.")
    args = parser.parse_args()

    load_dotenv()
    key = os.environ.get("OPENCELLID_API_KEY", "")
    if not key:
        print("OPENCELLID_API_KEY missing.", file=sys.stderr)
        return 1

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    bboxes = _region_bboxes(client)
    print("Region bboxes:", {k: tuple(round(v, 3) for v in b) for k, b in bboxes.items()})

    try:
        if args.skip_download and CSV_GZ.exists():
            print(f"Using existing {CSV_GZ}")
        else:
            print("Downloading Indonesia cell towers CSV (MCC 510) ...", flush=True)
            _download(key)
            print(f"Downloaded {CSV_GZ} ({CSV_GZ.stat().st_size / 1e6:.1f} MB)")
    except Exception as exc:  # noqa: BLE001
        print(f"Download failed: {exc}", file=sys.stderr)
        if not args.dry_run:
            for region_id in args.regions:
                _record_source_run(client, region_id, 0, "unavailable", f"bulk download failed: {type(exc).__name__}")
        return 1

    df = _load_and_filter(CSV_GZ, bboxes)
    print(f"Filtered towers: {len(df)} across {sorted(df['region_id'].unique())}")

    if args.dry_run:
        print(df[["region_id", "lat", "lon", "mcc", "net", "area", "cell"]].head(5).to_string())
        return 0

    for region_id in args.regions:
        sub = df[df["region_id"] == region_id]
        if sub.empty:
            _record_source_run(client, region_id, 0, "ok", "bulk CSV: no towers in extent")
            print(f"[{region_id}] 0 towers (no records in extent)")
            continue

        # Record the source_run BEFORE inserting so rows can carry provenance.
        run_id = _record_source_run(client, region_id, len(sub), "ok", "bulk CSV filtered to extent")

        rows = []
        for _, r in sub.iterrows():
            rows.append(
                {
                    "tower_id": str(uuid.uuid4()),
                    "region_id": region_id,
                    "lat": float(r["lat"]),
                    "lon": float(r["lon"]),
                    "mcc": int(r["mcc"]),
                    "mnc": int(r["net"]),
                    "lac": int(r["area"]),
                    "cell_id": int(r["cell"]),
                    "source_run_id": run_id,
                    "status": "real",
                }
            )
        for i in range(0, len(rows), 500):
            client.table("bts_locations").insert(rows[i : i + 500]).execute()

        print(f"[{region_id}] inserted {len(rows)} towers (source_run_id={run_id})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())