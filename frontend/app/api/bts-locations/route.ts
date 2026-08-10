/**
 * GET /api/bts-locations — Data Production Phase 5
 *
 * Returns OpenCellID BTS tower Points for a region.
 * Server-side filtering by region_id.
 *
 * Empty results are returned as [] — not an error. Every row carries an
 * explicit data_source so the UI reports unavailable rather than fabricating.
 */

import { NextRequest, NextResponse } from 'next/server'
import { getBTSLocations, ServiceError } from '@/lib/server/geosignal-service'
import { makeError, ERR, isValidRegion } from '@/lib/api-types'
import type { RegionId } from '@/lib/api-types'

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const region_id = searchParams.get('region_id')

  if (!isValidRegion(region_id)) {
    return NextResponse.json(
      makeError(
        ERR.INVALID_REGION,
        `region_id must be one of: ntt, ntb, central_kalimantan. Received: ${String(region_id)}`,
      ),
      { status: 400 },
    )
  }

  try {
    const towers = await getBTSLocations(region_id as RegionId)
    return NextResponse.json(towers, { status: 200 })
  } catch (err) {
    if (err instanceof ServiceError) {
      return NextResponse.json(
        makeError(ERR.SERVICE_ERROR, 'Failed to retrieve BTS locations.'),
        { status: 500 },
      )
    }
    return NextResponse.json(
      makeError(ERR.SERVICE_ERROR, 'An unexpected error occurred.'),
      { status: 500 },
    )
  }
}