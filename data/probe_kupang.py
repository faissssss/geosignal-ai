"""Probe: find which NTT kecamatan contains Kupang and test OpenCellID there."""
import os

import requests
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
key = os.environ["OPENCELLID_API_KEY"]
c = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

rows = (
    c.table("admin_boundaries")
    .select("kecamatan_id,kecamatan_name,region_id,boundary_geojson")
    .eq("region_id", "ntt")
    .execute()
    .data
)


def contains(gj, lat, lon):
    for poly in gj.get("coordinates", []):
        for ring in poly:
            inside = False
            n = len(ring)
            for i in range(n):
                x1, y1 = ring[i]
                x2, y2 = ring[(i + 1) % n]
                if (y1 > lat) != (y2 > lat):
                    xint = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
                    if xint > lon:
                        inside = not inside
            if inside:
                return True
    return False


# Kupang city center
target = (-10.18, 123.60)
for r in rows:
    if contains(r["boundary_geojson"], *target):
        print("Kupang is in:", r["kecamatan_id"], r["kecamatan_name"])
        # bbox of that kecamatan
        coords = r["boundary_geojson"]["coordinates"]
        lats = [pt[1] for poly in coords for ring in poly for pt in ring]
        lons = [pt[0] for poly in coords for ring in poly for pt in ring]
        bbox = f"{min(lats)},{min(lons)},{max(lats)},{max(lons)}"
        print("bbox:", bbox)
        resp = requests.get(
            "https://opencellid.org/cell/getInArea",
            params={"key": key, "BBOX": bbox, "format": "json"},
            timeout=30,
        )
        print("status:", resp.status_code, "body[:400]:", resp.text[:400])
        break