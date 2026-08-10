#!/usr/bin/env python3
"""Validate that each selected kecamatan contains heatmap grid-cell centroids."""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

from dotenv import load_dotenv
from shapely.geometry import Point, shape
from supabase import create_client


REGIONS = ("ntt", "ntb", "central_kalimantan")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--regions", nargs="+", choices=REGIONS, default=list(REGIONS))
    parser.add_argument("--minimum", type=int, default=1)
    args = parser.parse_args()
    load_dotenv()
    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    boundaries = client.table("admin_boundaries").select(
        "region_id,kecamatan_name,boundary_geojson"
    ).in_("region_id", args.regions).execute().data or []
    cells = client.table("grid_cells").select("region_id,lat,lon").in_("region_id", args.regions).execute().data or []
    cells_by_region = defaultdict(list)
    for cell in cells:
        cells_by_region[cell["region_id"]].append(Point(cell["lon"], cell["lat"]))

    missing = []
    for boundary in sorted(boundaries, key=lambda row: (row["region_id"], row["kecamatan_name"])):
        count = sum(shape(boundary["boundary_geojson"]).covers(cell) for cell in cells_by_region[boundary["region_id"]])
        print(f"{boundary['region_id']}/{boundary['kecamatan_name']}: {count} cells")
        if count < args.minimum:
            missing.append(f"{boundary['region_id']}/{boundary['kecamatan_name']} ({count})")
    if missing:
        print("Missing coverage: " + ", ".join(missing), file=sys.stderr)
        return 1
    print(f"Coverage complete: {len(boundaries)} kecamatan have at least {args.minimum} cells.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
