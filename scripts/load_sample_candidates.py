#!/usr/bin/env python3
"""
Load sample BTS candidate data for testing the Next.js filtering features.

This script creates realistic test data for the bts_candidates table,
allowing the frontend filtering features to be validated in the browser.

Usage:
    python scripts/load_sample_candidates.py
"""

import os
import sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

def main():
    # Connect to Supabase
    client = create_client(
        os.getenv('SUPABASE_URL'),
        os.getenv('SUPABASE_SERVICE_KEY')
    )
    
    print('🔍 Checking for existing target areas...')
    
    # Get existing target_area_id for NTT region
    target_areas_result = client.table('target_areas').select('target_area_id, region_id').execute()
    
    ntt_target = next((ta for ta in target_areas_result.data if ta['region_id'] == 'ntt'), None)
    
    if not ntt_target:
        print('❌ No NTT target area found.')
        print('\nYou need to create a target area first:')
        print('1. Open http://localhost:3000/')
        print('2. Click "Target Area Selector" (top-left)')
        print('3. Select "Kecamatan" tab')
        print('4. Choose any kecamatan (e.g., "Alor")')
        print('5. Click "Confirm Target Area"')
        print('6. Re-run this script')
        sys.exit(1)
    
    target_area_id = ntt_target['target_area_id']
    print(f'✅ Found NTT target area: {target_area_id}')
    
    # Check for existing scoring run
    scoring_runs_result = client.table('scoring_runs').select('run_id').limit(1).execute()
    
    if not scoring_runs_result.data:
        print('❌ No scoring_run found. Creating a sample scoring run...')
        import uuid
        run_id = str(uuid.uuid4())
        scoring_run_result = client.table('scoring_runs').insert({
            'run_id': run_id,
            'model_version': 'v1.0',
            'tier': '1',
            'region_kecamatans': ['ntt'],
            'resolution_m': 100
        }).execute()
        print(f'✅ Created scoring run: {run_id}')
    else:
        run_id = scoring_runs_result.data[0]['run_id']
        print(f'✅ Using existing scoring run: {run_id}')
    
    # Check if candidates already exist for this target area
    existing_candidates = client.table('bts_candidates').select('candidate_id').eq('target_area_id', target_area_id).execute()
    
    if existing_candidates.data:
        print(f'\n⚠️  Warning: {len(existing_candidates.data)} candidates already exist for this target area.')
        print('Do you want to delete them and create new ones? (y/n): ', end='')
        response = input().strip().lower()
        
        if response == 'y':
            print('🗑️  Deleting existing candidates...')
            client.table('bts_candidates').delete().eq('target_area_id', target_area_id).execute()
            print('✅ Deleted existing candidates')
        else:
            print('❌ Aborted. Keeping existing candidates.')
            sys.exit(0)
    
    print('\n🏗️  Creating sample BTS candidates...')
    
    # Create 10 sample candidates with realistic data
    # Base coordinates: Alor region, NTT Province, Indonesia
    base_lat = -8.2
    base_lon = 124.5
    
    candidates = []
    confidence_tags = ['High', 'High', 'High', 'High', 'Med', 'Med', 'Med', 'Low', 'Low', 'Low']
    
    for i in range(1, 11):
        import uuid
        candidate = {
            'candidate_id': str(uuid.uuid4()),
            'region_id': 'ntt',
            'target_area_id': target_area_id,
            'rank': i,
            'lat': base_lat + (i * 0.02),  # Spread candidates across ~20km north
            'lon': base_lon + (i * 0.015),  # Spread candidates across ~15km east
            'expected_improvement': round(20.0 - (i * 1.5), 2),  # Decreasing improvement by rank
            'los_validated': i <= 7,  # First 7 are LOS-validated
            'confidence_tag': confidence_tags[i - 1],
            'shap_values': {
                'population': round(0.4 - (i * 0.02), 2),
                'terrain': round(0.3 - (i * 0.01), 2),
                'land_cover': round(0.2 - (i * 0.01), 2),
                'distance_to_grid': round(0.1 - (i * 0.005), 2)
            },
            'model_version': 'v1.0',
            'scoring_run_id': run_id,
            'excluded_by_canopy': False
        }
        candidates.append(candidate)
    
    # Insert candidates
    result = client.table('bts_candidates').insert(candidates).execute()
    
    print(f'✅ Successfully inserted {len(result.data)} sample candidates')
    
    # Display summary
    print('\n📊 Sample Data Summary:')
    print(f'   Target Area: {target_area_id}')
    print(f'   Region: ntt')
    print(f'   Candidates: {len(candidates)}')
    print(f'   Confidence: {sum(1 for c in candidates if c["confidence_tag"] == "High")} High, '
          f'{sum(1 for c in candidates if c["confidence_tag"] == "Med")} Med, '
          f'{sum(1 for c in candidates if c["confidence_tag"] == "Low")} Low')
    print(f'   LOS Validated: {sum(1 for c in candidates if c["los_validated"])} / {len(candidates)}')
    
    print('\n✨ Done! You can now test the filtering features:')
    print('1. Refresh http://localhost:3000/')
    print('2. Toggle "Candidates" checkbox in the layer controls')
    print('3. Click on a candidate marker to open the side panel')
    print('4. Verify all filtering features work correctly')
    
    print('\n📝 Note: To test the full workflow, you may also need to:')
    print('   - Run the backend pipeline to generate whatif_grid data (for simulation)')
    print('   - Load OpenCellID BTS data (for BTS tower markers)')
    print('   - Ensure grid_cells table has data (for heatmap)')

if __name__ == '__main__':
    main()
