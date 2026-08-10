#!/usr/bin/env python3
"""Check which Supabase tables have data."""

import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_SERVICE_KEY')
)

tables = [
    'grid_cells',
    'bts_candidates',
    'whatif_grid',
    'los_results',
    'admin_boundaries',
    'target_areas',
    'model_artifacts',
    'scoring_runs',
    'ethical_risk_register'
]

print('=== Supabase Data Check ===\n')

for table in tables:
    try:
        result = client.table(table).select('*', count='exact').limit(1).execute()
        count = result.count if result.count is not None else 0
        status = '✅' if count > 0 else '⚠️ '
        print(f'{status} {table:25} {count:>6} rows')
    except Exception as e:
        print(f'❌ {table:25} ERROR: {str(e)[:50]}')

print('\n=== Summary ===')
print('✅ = Has data')
print('⚠️  = Empty (needs data)')
print('❌ = Table error')
