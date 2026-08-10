#!/usr/bin/env python3
"""Check grid_cells distribution across regions and kecamatan."""
from supabase import create_client
import os
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

client = create_client(
    os.getenv('SUPABASE_URL'),
    os.getenv('SUPABASE_SERVICE_KEY')
)

# Get all grid_cells with their regions
result = client.table('grid_cells').select('cell_id, region_id, lat, lon').execute()

if not result.data:
    print("⚠️  No grid_cells found in database")
    exit(0)

# Group by region
regions = defaultdict(list)
for cell in result.data:
    regions[cell['region_id']].append(cell)

print(f"\n📊 Grid Cells Distribution")
print("=" * 60)
for region_id, cells in sorted(regions.items()):
    print(f"\n{region_id.upper()}: {len(cells)} cells")
    
    # Get bounding box for this region's cells
    lats = [c['lat'] for c in cells]
    lons = [c['lon'] for c in cells]
    print(f"  Latitude range: {min(lats):.4f} to {max(lats):.4f}")
    print(f"  Longitude range: {min(lons):.4f} to {max(lons):.4f}")

print("\n" + "=" * 60)
print(f"TOTAL: {len(result.data)} cells across {len(regions)} regions")

# Now check admin_boundaries to see which kecamatan exist
print("\n📍 Admin Boundaries (Kecamatan) by Region")
print("=" * 60)
boundaries_result = client.table('admin_boundaries').select('region_id, kecamatan_id, kecamatan_name').execute()

if boundaries_result.data:
    boundaries_by_region = defaultdict(list)
    for boundary in boundaries_result.data:
        boundaries_by_region[boundary['region_id']].append(boundary)
    
    for region_id, boundaries in sorted(boundaries_by_region.items()):
        print(f"\n{region_id.upper()}: {len(boundaries)} kecamatan")
        for b in boundaries[:3]:  # Show first 3
            print(f"  - {b['kecamatan_name']}")
        if len(boundaries) > 3:
            print(f"  ... and {len(boundaries) - 3} more")
else:
    print("⚠️  No admin_boundaries found in database")
