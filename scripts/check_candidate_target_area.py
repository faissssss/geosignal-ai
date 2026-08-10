#!/usr/bin/env python3
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_SERVICE_KEY')
)

# Get one candidate
result = client.table('bts_candidates').select('target_area_id, region_id').limit(1).execute()
if result.data:
    print(f"Target Area ID: {result.data[0]['target_area_id']}")
    print(f"Region ID: {result.data[0]['region_id']}")
else:
    print("No candidates found")
