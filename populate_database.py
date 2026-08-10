#!/usr/bin/env python3
"""Populate the Supabase database with initial data for the GeoSignal AI demo.

This script runs the essential data pipeline tasks to make the app functional:
1. Task 5: Ingest GADM administrative boundaries (kecamatan)
2. Task 16: Populate ethical risk register
3. Generate sample grid_cells for demo visualization

For a full production deployment, you would also run:
- Task 7: Feature engineering with real GEE data
- Task 12: LOS precomputation
- Task 18: What-if grid precomputation
"""
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client

from geosignal.admin_boundaries import download_gadm_boundaries, parse_gadm_features

load_dotenv()

client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_SERVICE_KEY')
)

print('=' * 70)
print('GeoSignal AI — Database Population Script')
print('=' * 70)
print()

# ---------------------------------------------------------------------------
# Task 16: Populate Ethical Risk Register
# ---------------------------------------------------------------------------

print('[Task 16] Populating Ethical Risk Register...')

ethical_risks = [
    {
        'risk_id': 'digital_exclusion',
        'risk_description': 'Low-population clusters get systematically deprioritized despite genuine need',
        'impact': 'Communities with legitimate connectivity needs are overlooked by the algorithm',
        'mitigation': 'Explicit equity weighting in AHP via public facility proximity and population density',
        'responsible_owner_role': 'Model/Data Lead',
        'last_reviewed_at': datetime.now(timezone.utc).isoformat()
    },
    {
        'risk_id': 'deforestation',
        'risk_description': 'Recommended sites encourage clearing of forest canopy',
        'impact': 'Environmental damage from acting on algorithmically-suggested locations',
        'mitigation': 'Land cover and canopy-height constraints exclude high-canopy candidates by default',
        'responsible_owner_role': 'Model/Data Lead',
        'last_reviewed_at': datetime.now(timezone.utc).isoformat()
    },
    {
        'risk_id': 'opencellid_sparsity_misread',
        'risk_description': 'A blank OpenCellID record gets treated as verified zero-signal rather than unknown/unmeasured',
        'impact': 'Investment misdirected due to misinterpreting data absence as confirmed no-coverage',
        'mitigation': 'Confidence tagging explicitly flags "no nearby tower or Ookla tile" as Low-confidence unknown',
        'responsible_owner_role': 'Data Lead',
        'last_reviewed_at': datetime.now(timezone.utc).isoformat()
    },
    {
        'risk_id': 'low_confidence_funding_decisions',
        'risk_description': 'A government stakeholder acts on a Low-confidence recommendation as if it were high-fidelity',
        'impact': 'Poor infrastructure decisions based on uncertain model outputs',
        'mitigation': 'UI visually distinguishes confidence tiers; documentation frames output as GeoAI-assisted estimates',
        'responsible_owner_role': 'Product/Presentation Lead',
        'last_reviewed_at': datetime.now(timezone.utc).isoformat()
    },
    {
        'risk_id': 'maup_resampling_mismatch',
        'risk_description': 'Combining 10m, 30m, and 100m-resolution layers at a single grid size can distort scores',
        'impact': 'Coverage Score accuracy varies depending on chosen cell size',
        'mitigation': 'Test Coverage Score output at more than one grid resolution before finalizing',
        'responsible_owner_role': 'Model/Data Lead',
        'last_reviewed_at': datetime.now(timezone.utc).isoformat()
    },
]

try:
    result = client.table('ethical_risk_register').upsert(ethical_risks).execute()
    print(f'   ✅ Inserted {len(ethical_risks)} ethical risk entries')
except Exception as e:
    print(f'   ❌ Failed to insert ethical risks: {e}')

print()

# ---------------------------------------------------------------------------
# Task 5: Ingest GADM Administrative Boundaries
# ---------------------------------------------------------------------------

print('[Task 5] Downloading and ingesting GADM boundaries...')

regions_to_ingest = ['ntt', 'ntb', 'central_kalimantan']

for region_id in regions_to_ingest:
    try:
        print(f'   Downloading {region_id.upper()} boundaries from GADM...')
        # download_gadm_boundaries returns a list of GeoJSON features, not a GeoDataFrame
        features = download_gadm_boundaries(region_id)
        
        print(f'   Parsing {len(features)} features...')
        boundary_records = parse_gadm_features(features, region_id)
        
        if boundary_records:
            # Insert into Supabase
            result = client.table('admin_boundaries').upsert(boundary_records).execute()
            print(f'   ✅ Inserted {len(boundary_records)} kecamatan boundaries for {region_id.upper()}')
        else:
            print(f'   ⚠️  No boundary records parsed for {region_id.upper()}')
            
    except Exception as e:
        print(f'   ❌ Failed to process {region_id}: {e}')

print()

# ---------------------------------------------------------------------------
# Create Demo Model Artifact Record (needed for grid_cells FK constraint)
# ---------------------------------------------------------------------------

print('[Setup] Creating demo model artifact record...')

demo_model = {
    'version_id': 'demo-v0.1.0',
    'tier': '1',
    'algorithm': 'AHP-weighted ensemble (demo)',
    'training_run_id': str(uuid.uuid4()),
    'artifact_path': '/demo/model_artifacts/demo-v0.1.0',
    'created_at': datetime.now(timezone.utc).isoformat()
}

try:
    result = client.table('model_artifacts').upsert(demo_model).execute()
    print(f'   ✅ Created demo model artifact: {demo_model["version_id"]}')
except Exception as e:
    print(f'   ❌ Failed to create model artifact: {e}')

print()

# ---------------------------------------------------------------------------
# Create Demo Scoring Run Record (needed for grid_cells FK constraint)
# ---------------------------------------------------------------------------

print('[Setup] Creating demo scoring run record...')

demo_scoring_run_id = str(uuid.uuid4())
demo_scoring_run = {
    'run_id': demo_scoring_run_id,
    'model_version': 'demo-v0.1.0',
    'tier': '1',
    'region_kecamatans': ['IDN.17.11_1'],  # Sample kecamatan
    'resolution_m': 100,
    'input_checksums': {},
    'candidate_count': 0,
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'retained_for_months': 12
}

try:
    result = client.table('scoring_runs').upsert(demo_scoring_run).execute()
    print(f'   ✅ Created demo scoring run: {demo_scoring_run_id}')
except Exception as e:
    print(f'   ❌ Failed to create scoring run: {e}')

print()

# ---------------------------------------------------------------------------
# Generate Sample Grid Cells for Demo
# ---------------------------------------------------------------------------

print('[Demo] Generating sample grid cells for visualization...')
print('   (In production, this would come from Task 7 feature engineering)')

# Sample coordinates for NTT Province (around Kupang)
sample_cells = []

# Create a 5x5 grid of sample cells
import random
random.seed(42)  # Reproducible

base_lat, base_lon = -10.17, 123.57  # Kupang area
cell_size = 0.1  # degrees

for i in range(5):
    for j in range(5):
        lat = base_lat + (i * cell_size)
        lon = base_lon + (j * cell_size)
        
        # Random coverage score for demo
        coverage_score = random.uniform(20, 95)
        
        # Confidence based on score
        if coverage_score >= 70:
            confidence = 'High'
        elif coverage_score >= 40:
            confidence = 'Med'
        else:
            confidence = 'Low'
        
        sample_cells.append({
            'cell_id': str(uuid.uuid4()),
            'region_id': 'ntt',
            'lat': lat,
            'lon': lon,
            'resolution_m': 100,
            'coverage_score': coverage_score,
            'confidence_tag': confidence,
            'tier_used': '1',  # AHP tier for demo
            'shap_top3': [
                {'feature_name': 'Distance to BTS', 'direction': 'negative'},
                {'feature_name': 'Elevation', 'direction': 'negative'},
                {'feature_name': 'Population Density', 'direction': 'positive'}
            ],
            'model_version': 'demo-v0.1.0',
            'scoring_run_id': demo_scoring_run_id
        })

try:
    result = client.table('grid_cells').insert(sample_cells).execute()
    print(f'   ✅ Inserted {len(sample_cells)} sample grid cells for demo')
except Exception as e:
    print(f'   ❌ Failed to insert sample cells: {e}')

print()
print('=' * 70)
print('✅ Database population complete!')
print('=' * 70)
print()
print('Summary:')
print(f'  • {len(ethical_risks)} ethical risk entries')
print(f'  • {len(regions_to_ingest)} regions with GADM boundaries')
print(f'  • {len(sample_cells)} sample grid cells for demo')
print()
print('Next steps:')
print('  1. Refresh your browser at http://localhost:3000')
print('  2. You should now see:')
print('     - Sample heatmap data on the map')
print('     - Kecamatan dropdown populated')
print('  3. For full functionality, run Tasks 12 & 18 (LOS + what-if grid)')
print()
