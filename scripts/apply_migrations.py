#!/usr/bin/env python3
"""Apply all infra/migrations/*.sql in sorted order (idempotent).

Uses SUPABASE_DB_URL from the environment (or .env).  Falls back to the
SUPABASE_URL/password pair when SUPABASE_DB_URL is absent.  Each migration's
SQL is executed inside a single transaction; a failure aborts that migration
and stops the run without applying later ones.

Usage:
  python scripts/apply_migrations.py
  python scripts/apply_migrations.py --file 004_data_production.sql
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "infra" / "migrations"
MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)


def _connect() -> object:
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
            "in .env before running migrations."
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


def _migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", help="Apply only this migration file.")
    args = parser.parse_args()

    if args.file:
        target = Path(args.file)
        files = [target]
    else:
        files = _migration_files()

    if not files:
        print(f"No migrations found in {MIGRATIONS_DIR}", file=sys.stderr)
        return 2

    conn = _connect()
    print(f"Connected to {conn.get_dsn_parameters()['host']}")

    for path in files:
        if not path.exists():
            print(f"skip (missing): {path.name}", file=sys.stderr)
            continue
        sql = path.read_text(encoding="utf-8")
        if not sql.strip():
            continue
        print(f"Applying {path.name} ...")
        try:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
            print(f"OK {path.name}")
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            print(f"FAILED {path.name}: {exc}", file=sys.stderr)
            return 1

    conn.close()
    print("All migrations applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())