#!/usr/bin/env python3
"""Promote real production runs and remove demo rows transaction-safely (Phase E).

Requires a passing validation (``--validate`` runs validate_production.py
first and aborts on failure).  Uses a single PostgreSQL transaction via
``SUPABASE_DB_URL``:

  1. Captures demo grid_cells / bts_candidates IDs into a rollback manifest.
  2. Marks all ``ok`` real-data source_runs as promoted
     (``promoted_run_id`` = promotion id, ``promoted_at`` = now).
  3. Deletes demo grid_cells and bts_candidates.
  4. Commits.

The rollback manifest (``data/manifests/rollback-<promotion_id>.json``)
records the removed demo rows so an operator can restore them if needed.
Demo scoring_runs are audit rows protected by the 12-month retention
trigger and are intentionally kept.

Usage:
  python scripts/promote_run.py --validate
  python scripts/promote_run.py --yes
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

MANIFEST_DIR = Path("data/manifests")
REAL_DATASETS = (
    "gee_raster_sample",
    "osm_villages",
    "opencellid_towers",
    "ookla_fixed",
    "ookla_mobile",
    "gee_landcover_tiles",
    "srtm_contours",
    "bts_candidates",
)


def _connect():
    load_dotenv()
    import psycopg2

    db_url = os.getenv("SUPABASE_DB_URL")
    if db_url:
        return psycopg2.connect(db_url, connect_timeout=15, sslmode="require")
    host = os.getenv("SUPABASE_DB_HOST", "db.ljstbtohevwxfreexvuu.supabase.co")
    password = os.getenv("SUPABASE_DB_PASSWORD")
    if not password:
        raise RuntimeError(
            "Set SUPABASE_DB_URL (or SUPABASE_DB_PASSWORD + SUPABASE_DB_HOST) "
            "in .env before running promotion."
        )
    return psycopg2.connect(
        host=host,
        port=int(os.getenv("SUPABASE_DB_PORT", "5432")),
        dbname=os.getenv("SUPABASE_DB_NAME", "postgres"),
        user=os.getenv("SUPABASE_DB_USER", "postgres"),
        password=password,
        connect_timeout=15,
        sslmode="require",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run validate_production.py first and abort if it fails.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    args = parser.parse_args()

    if args.validate:
        print("Running validation gate ...")
        result = subprocess.run(
            [sys.executable, "scripts/validate_production.py"],
            cwd=Path(__file__).resolve().parent.parent,
        )
        if result.returncode != 0:
            print("Validation failed; promotion aborted.", file=sys.stderr)
            return 1

    if not args.yes:
        answer = input(
            "This will delete all demo grid_cells and bts_candidates and mark "
            "real source_runs as promoted. Type 'promote' to continue: "
        )
        if answer.strip().lower() != "promote":
            print("Aborted.")
            return 1

    promotion_id = str(uuid.uuid4())
    conn = _connect()
    try:
        with conn.cursor() as cur:
            # The promoted_run_id column self-references source_runs(run_id),
            # so the promotion anchor must be an existing run.  Use the
            # earliest ok real-data run of this batch.
            cur.execute(
                "SELECT run_id FROM source_runs "
                "WHERE status = 'ok' AND dataset = ANY(%s) "
                "ORDER BY ingested_at ASC LIMIT 1",
                (list(REAL_DATASETS),),
            )
            anchor = cur.fetchone()
            if not anchor:
                raise RuntimeError("No ok real-data source_runs to promote.")
            promotion_id = anchor[0]

            # 1. Capture demo rows for the rollback manifest.
            cur.execute(
                "SELECT cell_id, region_id, lat, lon, coverage_score, "
                "confidence_tag, tier_used, shap_top3, model_version, "
                "scoring_run_id, kecamatan_id, source_run_id "
                "FROM grid_cells WHERE data_source = 'demo'"
            )
            demo_grid = [
                {
                    "cell_id": r[0],
                    "region_id": r[1],
                    "lat": r[2],
                    "lon": r[3],
                    "coverage_score": r[4],
                    "confidence_tag": r[5],
                    "tier_used": r[6],
                    "shap_top3": r[7],
                    "model_version": r[8],
                    "scoring_run_id": r[9],
                    "kecamatan_id": r[10],
                    "source_run_id": r[11],
                }
                for r in cur.fetchall()
            ]
            cur.execute(
                "SELECT candidate_id, region_id, target_area_id, rank, lat, lon, "
                "expected_improvement, los_validated, confidence_tag, shap_values, "
                "model_version, scoring_run_id, excluded_by_canopy, kecamatan_id, "
                "source_run_id "
                "FROM bts_candidates WHERE data_source = 'demo'"
            )
            demo_cands = [
                {
                    "candidate_id": r[0],
                    "region_id": r[1],
                    "target_area_id": r[2],
                    "rank": r[3],
                    "lat": r[4],
                    "lon": r[5],
                    "expected_improvement": r[6],
                    "los_validated": r[7],
                    "confidence_tag": r[8],
                    "shap_values": r[9],
                    "model_version": r[10],
                    "scoring_run_id": r[11],
                    "excluded_by_canopy": r[12],
                    "kecamatan_id": r[13],
                    "source_run_id": r[14],
                }
                for r in cur.fetchall()
            ]

            # 2. Mark real source_runs as promoted.
            cur.execute(
                "UPDATE source_runs SET promoted_run_id = %s, promoted_at = NOW() "
                "WHERE status = 'ok' AND dataset = ANY(%s)",
                (promotion_id, list(REAL_DATASETS)),
            )
            promoted_count = cur.rowcount

            # 3. Delete demo rows (whatif_grid cascades on grid_cell_id).
            cur.execute("DELETE FROM grid_cells WHERE data_source = 'demo'")
            deleted_grid = cur.rowcount
            cur.execute("DELETE FROM bts_candidates WHERE data_source = 'demo'")
            deleted_cands = cur.rowcount

        conn.commit()
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        print(f"Promotion FAILED (rolled back): {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    # 4. Write the rollback manifest.
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    rollback_path = MANIFEST_DIR / f"rollback-{promotion_id}.json"
    rollback_path.write_text(
        json.dumps(
            {
                "promotion_id": promotion_id,
                "promoted_at": datetime.now(tz=timezone.utc).isoformat(),
                "promoted_source_runs": promoted_count,
                "deleted_demo_grid_cells": deleted_grid,
                "deleted_demo_bts_candidates": deleted_cands,
                "restore_instructions": (
                    "To roll back, re-insert the demo rows below with their "
                    "original IDs and set source_runs.promoted_run_id = NULL "
                    "for the affected runs."
                ),
                "demo_grid_cells": demo_grid,
                "demo_bts_candidates": demo_cands,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print(f"Promotion {promotion_id} complete.")
    print(f"  promoted source_runs: {promoted_count}")
    print(f"  deleted demo grid_cells: {deleted_grid}")
    print(f"  deleted demo bts_candidates: {deleted_cands}")
    print(f"  rollback manifest: {rollback_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())