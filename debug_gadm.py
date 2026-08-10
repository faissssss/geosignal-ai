#!/usr/bin/env python3
"""Debug GADM boundary download."""
import sys
sys.path.insert(0, 'backend')

from geosignal.admin_boundaries import download_gadm_boundaries
from pathlib import Path

print('Checking GADM download...')
print()

# Check cache
cache_path = Path('data/gadm_cache/gadm41_IDN_2.json')
print(f'Cache path: {cache_path}')
print(f'Cache exists: {cache_path.exists()}')

if cache_path.exists():
    import json
    with open(cache_path) as f:
        data = json.load(f)
    print(f'Cache file has {len(data.get("features", []))} features')
    
    # Check a sample feature
    if data.get("features"):
        sample = data["features"][0]
        print(f'Sample feature properties: {list(sample.get("properties", {}).keys())}')
        print(f'Sample NAME_1: {sample.get("properties", {}).get("NAME_1")}')

print()
print('Testing download_gadm_boundaries("ntt")...')
features = download_gadm_boundaries('ntt')
print(f'Result: {len(features)} features')

if features:
    print('First feature properties:')
    print(features[0].get('properties'))
