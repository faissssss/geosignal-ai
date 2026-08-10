#!/usr/bin/env python3
"""Backfill kecamatan_id on village_features via spatial containment (Phase E).

ingest_villages.py stored region-scoped village geometry without assigning
``kecamatan_id``.  This assigns each village to the kecamatan whose boundary
contains its geometry (point-in-polygon; polygon centroids for polygon
villages) using a shapely STRtree over admin_boundaries.

Villages that fall outside every boundary keep ``kecamatan_id = NULL`` (they
are still region-scoped and valid); no rows are fabricated.

The bulk update runs through ``SUPABASE_DB_URL`` (psycopg2) so every row
receives its own kecamatan_id in one statement.

Usage:
  python scripts/backfill_village_kecamatan.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
from shapely.geometry import shape
from shapely.strtree import STRtree
from supabase import create_client


def _fetch_all(client, table: str, select: str, **filters) -> list[dict]:
    rows: list[dict] = []
    page = 1000
    start = 0
    while True:
        q = client.table(table).select(select)
        for k, v in filters.items():
            q = q.eq(k, v)
        batch = q.range(start, start + page - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page:
            break
        start += page
    return rows


def _connect():
    import psycopg2

    db_url = os.getenv("SUPABASE_DB_URL")
    if db_url:
        return psycopg2.connect(db_url, connect_timeout=15, sslmode="require")
    host = os.getenv("SUPABASE_DB_HOST", "db.ljstbtohevwxfreexvuu.supabase.co")
    password = os.getenv("SUPABASE_DB_PASSWORD")
    if not password:
        raise RuntimeError(
            "Set SUPABASE_DB_URL (or SUPABASE_DB_PASSWORD + SUPABASE_DB_HOST) "
            "in .env before running the backfill."
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
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    boundaries = _fetch_all(client, "admin_boundaries", "kecamatan_id,boundary_geojson")
    geoms = [shape(b["boundary_geojson"]) for b in boundaries]
    tree = STRtree(geoms)
    index_to_kecamatan = {i: b["kecamatan_id"] for i, b in enumerate(boundaries)}

    villages = _fetch_all(client, "village_features", "feature_id,geom_geojson,kecamatan_id")
    updates: list[tuple[str, str]] = []
    for v in villages:
        geom = shape(v["geom_geojson"])
        point = geom.centroid if geom.geom_type != "Point" else geom
        kecamatan_id = None
        for idx in tree.query(point):
            if geoms[int(idx)].covers(point):
                kecamatan_id = index_to_kecamatan[int(idx)]
                break
        if kecamatan_id:
            updates.append((v["feature_id"], kecamatan_id))

    print(f"villages: {len(villages)}, to assign: {len(updates)}")
    if args.dry_run:
        print(f"dry-run: would update {len(updates)} villages")
        return 0

    conn = _connect()
    try:
        with conn.cursor() as cur:
            # Reset any stale assignments first (idempotent re-run).
            cur.execute("UPDATE village_features SET kecamatan_id = NULL")
            # Bulk per-row update via VALUES.
            from psycopg2.extras import execute_values

            execute_values(
                cur,
                """
                UPDATE village_features AS vf
                SET kecamatan_id = v.kecamatan_id
                FROM (VALUES %s) AS v(feature_id, kecamatan_id)
                WHERE vf.feature_id = v.feature_id::uuid
                """,
                updates,
            )
            updated = cur.rowcount
        conn.commit()
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        print(f"Backfill FAILED (rolled back): {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(f"updated {updated} villages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())