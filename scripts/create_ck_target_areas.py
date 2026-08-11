#!/usr/bin/env python3
"""Create kecamatan-scoped target areas for central_kalimantan (Phase D gap fix).

Reads admin_boundaries for the 14 CK kecamatan and inserts one target_area per
kecamatan (selection_method='kecamatan'), mirroring the existing NTT/NTB target
areas. Idempotent: skips kecamatan that already have a target area.
"""
from __future__ import annotations

import os
import sys
import uuid

from dotenv import load_dotenv
from supabase import create_client

REGION = "central_kalimantan"


def main() -> int:
    load_dotenv()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    boundaries = (
        client.table("admin_boundaries")
        .select("kecamatan_id,kecamatan_name,region_id,boundary_geojson")
        .eq("region_id", REGION)
        .execute()
        .data
        or []
    )
    print(f"CK admin boundaries: {len(boundaries)}")

    existing = (
        client.table("target_areas")
        .select("kecamatan_id")
        .eq("region_id", REGION)
        .execute()
        .data
        or []
    )
    existing_kecs = {t["kecamatan_id"] for t in existing}
    print(f"Existing CK target areas: {len(existing_kecs)}")

    created = 0
    for b in sorted(boundaries, key=lambda x: x["kecamatan_id"]):
        kid = b["kecamatan_id"]
        if kid in existing_kecs:
            print(f"  skip {kid} (already has target area)")
            continue
        row = {
            "target_area_id": str(uuid.uuid4()),
            "region_id": REGION,
            "selection_method": "kecamatan",
            "kecamatan_id": kid,
            "boundary_geojson": b["boundary_geojson"],
        }
        client.table("target_areas").insert(row).execute()
        print(f"  created {kid} ({b['kecamatan_name']}) -> {row['target_area_id']}")
        created += 1

    print(f"\nCreated {created} CK target areas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())