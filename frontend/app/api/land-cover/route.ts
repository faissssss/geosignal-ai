/**
 * GET /api/land-cover — Data Production Phase 5
 *
 * Returns the browser-efficient GEE-published land-cover tile sets for a region.
 * Server-side filtering by region_id; optional kecamatan_id scoping.
 *
 * Empty results are returned as [] — not an error. Every row carries an
 * explicit data_source so the UI reports unavailable rather than fabricating.
 */

import { NextRequest, NextResponse } from 'next/server'
import { getLandCoverTileSets, ServiceError } from '@/lib/server/geosignal-service'
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
    const sets = await getLandCoverTileSets(region_id as RegionId)
    return NextResponse.json(sets, { status: 200 })
  } catch (err) {
    if (err instanceof ServiceError) {
      return NextResponse.json(
        makeError(ERR.SERVICE_ERROR, 'Failed to retrieve land-cover tile sets.'),
        { status: 500 },
      )
    }
    return NextResponse.json(
      makeError(ERR.SERVICE_ERROR, 'An unexpected error occurred.'),
      { status: 500 },
    )
  }
}