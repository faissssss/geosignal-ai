#!/usr/bin/env python3
"""Verify access to every production data source and write a dated report.

Phase 0 of .kiro/specs/data-production/expected-outcomes.md: prove each source
is reachable before any production write begins.  A failed source is reported
as unavailable — it never produces random values or a silent zero-data success.

Checks:
  - Supabase  : read (admin_boundaries) + source_runs count via service key.
  - GEE       : service-account auth + a small read-only SRTM sample.
  - Ookla     : HEAD on configured fixed/mobile archive URLs (no full download).
  - OpenCellID: getInAreaSize probe on the NTT bounding box (key never printed).

Usage:
  python scripts/verify_source_access.py
  python scripts/verify_source_access.py --out-dir data/access-reports
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


def _check_supabase() -> dict:
    """Verify Supabase read access and report table counts."""
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return {"status": "FAIL", "detail": "SUPABASE_URL or SUPABASE_SERVICE_KEY missing."}

    try:
        client = create_client(url, key)
        boundaries = client.table("admin_boundaries").select("region_id").limit(1).execute()
        runs = client.table("source_runs").select("run_id", count="exact").limit(1).execute()  # type: ignore[arg-type]
        return {
            "status": "PASS",
            "detail": (
                f"read OK (admin_boundaries sample: {boundaries.data}); "
                f"source_runs count: {runs.count}"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "FAIL", "detail": f"{type(exc).__name__}: {str(exc)[:300]}"}


def _check_gee() -> dict:
    """Verify GEE service-account auth with a small read-only SRTM request."""
    import ee

    email = os.environ.get("GEE_SERVICE_ACCOUNT_EMAIL", "")
    json_path = os.environ.get("GEE_SERVICE_ACCOUNT_JSON_PATH", "")
    project = os.environ.get("GEE_PROJECT_ID", "")
    if not email or not json_path or not project:
        return {"status": "FAIL", "detail": "GEE env vars incomplete (email/json/project)."}

    try:
        creds = ee.ServiceAccountCredentials(email, json_path)
        ee.Initialize(creds, project=project)
        value = (
            ee.Image("USGS/SRTMGL1_003")
            .select("elevation")
            .reduceRegion(
                ee.Reducer.mean(), ee.Geometry.Point([124.5, -8.2]), 100
            )
            .get("elevation")
            .getInfo()
        )
        return {"status": "PASS", "detail": f"SRTM sample elevation: {value} m"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "FAIL", "detail": f"{type(exc).__name__}: {str(exc)[:300]}"}


def _check_ookla() -> dict:
    """HEAD the configured Ookla archives; report size and final URL."""
    import requests

    urls = {
        "fixed": os.environ.get("OOKLA_FIXED_TILE_URL", ""),
        "mobile": os.environ.get("OOKLA_MOBILE_TILE_URL", ""),
    }
    results = []
    all_ok = True
    for name, url in urls.items():
        if not url:
            results.append(f"{name}: FAIL (URL not configured)")
            all_ok = False
            continue
        try:
            resp = requests.head(url, timeout=20, allow_redirects=True)
            size = resp.headers.get("Content-Length", "?")
            results.append(f"{name}: HTTP {resp.status_code}, {size} bytes")
            if resp.status_code != 200:
                all_ok = False
        except Exception as exc:  # noqa: BLE001
            results.append(f"{name}: FAIL ({type(exc).__name__}: {str(exc)[:150]})")
            all_ok = False
    return {"status": "PASS" if all_ok else "FAIL", "detail": "; ".join(results)}


def _check_opencellid() -> dict:
    """Probe OpenCellID getInAreaSize on the NTT bbox. Never prints the key."""
    import requests

    key = os.environ.get("OPENCELLID_API_KEY", "")
    if not key:
        return {"status": "FAIL", "detail": "OPENCELLID_API_KEY missing."}

    try:
        # Small bbox (~1.2 km²) — OpenCellID caps getInAreaSize at 4,000,000 m².
        resp = requests.get(
            "https://opencellid.org/cell/getInAreaSize",
            params={
                "key": key,
                "BBOX": "-8.21,124.49,-8.20,124.50",
                "format": "json",
            },
            timeout=30,
        )
        body = resp.text[:200]
        # A structured JSON error (e.g. "BBOX too big") still proves the key is
        # accepted; only auth/transport failures count as FAIL.
        ok = resp.status_code == 200 and '"error"' not in body
        return {
            "status": "PASS" if ok else "FAIL",
            "detail": f"HTTP {resp.status_code}: {body}",
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "FAIL", "detail": f"{type(exc).__name__}: {str(exc)[:200]}"}


def _write_report(checks: dict[str, dict], out_dir: Path) -> Path:
    """Write the dated markdown access report; returns its path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(tz=timezone.utc)
    path = out_dir / f"access-report-{now:%Y-%m-%d}.md"

    lines = [
        "# GeoSignal AI — Source Access Report",
        f"Date: {now:%Y-%m-%d %H:%M} UTC",
        "",
    ]
    for source, result in checks.items():
        lines.append(f"## {source} — {result['status']}")
        lines.append("")
        lines.append(result["detail"])
        lines.append("")

    passed = sum(1 for r in checks.values() if r["status"] == "PASS")
    failed = [name for name, r in checks.items() if r["status"] == "FAIL"]
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Sources reachable: {passed}/{len(checks)}")
    lines.append(f"- Blocking failures: {', '.join(failed) if failed else 'none'}")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-dir",
        default="data/access-reports",
        help="Directory for the dated access report.",
    )
    args = parser.parse_args()

    load_dotenv()

    checks: dict[str, dict] = {
        "Supabase": _check_supabase(),
        "GEE": _check_gee(),
        "Ookla": _check_ookla(),
        "OpenCellID": _check_opencellid(),
    }

    for source, result in checks.items():
        print(f"{source}: {result['status']} — {result['detail']}")

    report_path = _write_report(checks, Path(args.out_dir))
    print(f"\nReport written: {report_path}")

    return 0 if all(r["status"] == "PASS" for r in checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())