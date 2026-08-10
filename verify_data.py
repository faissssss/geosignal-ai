#!/usr/bin/env python3
"""Verify that all data was successfully inserted into Supabase."""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_SERVICE_KEY')
)

print('=' * 70)
print('Supabase Data Verification')
print('=' * 70)
print()

# Check all tables
tables = [
    'ethical_risk_register',
    'admin_boundaries',
    'grid_cells',
    'model_artifacts',
    'scoring_runs',
    'bts_candidates',
    'whatif_grid',
    'target_areas',
    'los_results'
]

for table in tables:
    try:
        result = client.table(table).select('*', count='exact').limit(0).execute()
        count = result.count if hasattr(result, 'count') else 0
        status = '✅' if count > 0 else '⚠️ '
        print(f'{status} {table}: {count} records')
    except Exception as e:
        print(f'❌ {table}: Error - {e}')

print()
print('=' * 70)
print('Frontend API Endpoints Check')
print('=' * 70)
print()

import requests

endpoints = [
    ('GET', 'http://localhost:3000/api/regions'),
    ('GET', 'http://localhost:3000/api/boundaries?region=ntt'),
    ('GET', 'http://localhost:3000/api/grid?region=ntt'),
]

for method, url in endpoints:
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            print(f'✅ {url}')
            print(f'   Status: {resp.status_code}, Data length: {len(data) if isinstance(data, list) else "N/A"}')
        else:
            print(f'⚠️  {url}')
            print(f'   Status: {resp.status_code}')
    except Exception as e:
        print(f'❌ {url}')
        print(f'   Error: {e}')

print()
