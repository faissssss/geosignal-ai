"""Probe: tile KotaKupang bbox fully and count towers found."""
import os

import requests
from dotenv import load_dotenv

load_dotenv()
key = os.environ["OPENCELLID_API_KEY"]

TILE_DEG = 0.015
bbox = "-10.2933,123.5272,-10.1297,123.6835"
lat_sw, lon_sw, lat_ne, lon_ne = map(float, bbox.split(","))

total = 0
tiles = 0
lat = lat_sw
while lat < lat_ne:
    lon = lon_sw
    while lon < lon_ne:
        tb = f"{lat},{lon},{min(lat + TILE_DEG, lat_ne)},{min(lon + TILE_DEG, lon_ne)}"
        resp = requests.get(
            "https://opencellid.org/cell/getInArea",
            params={"key": key, "BBOX": tb, "format": "json"},
            timeout=30,
        )
        tiles += 1
        if resp.status_code != 200:
            continue
        body = resp.json()
        if isinstance(body, dict) and body.get("cells"):
            total += len(body["cells"])
        lon += TILE_DEG
    lat += TILE_DEG

print(f"tiles: {tiles}, towers found: {total}")