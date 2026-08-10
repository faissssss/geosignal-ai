/**
 * GET /api/admin-boundaries
 * 
 * Fetch admin boundaries (kecamatan polygons) for a specific region.
 * Used by TargetAreaSelector to populate the kecamatan dropdown.
 * 
 * Query parameters:
 *   - region_id: One of 'ntt', 'ntb', 'central_kalimantan'
 * 
 * Returns:
 *   - 200: Array of AdminBoundary objects
 *   - 400: Missing or invalid region_id
 *   - 500: Database error
 */

import { NextRequest, NextResponse } from 'next/server'
import { fetchAdminBoundaries, ServiceError } from '@/lib/server/geosignal-service'
import type { RegionId } from '@/lib/types'

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const region_id = searchParams.get('region_id')

  // Validate region_id
  if (!region_id) {
    return NextResponse.json(
      { error: 'Missing required parameter: region_id' },
      { status: 400 }
    )
  }

  const validRegions: RegionId[] = ['ntt', 'ntb', 'central_kalimantan']
  if (!validRegions.includes(region_id as RegionId)) {
    return NextResponse.json(
      { error: `Invalid region_id: ${region_id}. Must be one of: ${validRegions.join(', ')}` },
      { status: 400 }
    )
  }

  try {
    const boundaries = await fetchAdminBoundaries(region_id as RegionId)
    return NextResponse.json(boundaries, { status: 200 })
  } catch (err) {
    if (err instanceof ServiceError) {
      const status = err.code === 'SERVICE_ERROR' ? 500 : 400
      return NextResponse.json({ error: err.message }, { status })
    }
    
    console.error('Unexpected error fetching admin boundaries:', err)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
}
