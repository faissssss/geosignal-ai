/**
 * GET /api/grid-cells — Task 25.5
 * Requirements: 3.1, 3.4, 10.2
 *
 * Returns Coverage Score grid cells for heatmap rendering and the side panel.
 * Filtering is done server-side (not in the browser) using:
 *   - region_id  (required)
 *   - resolution_m (required, positive integer)
 *   - target_area_id (optional)
 *
 * Returns only the fields needed by CoverageHeatmap and SidePanel:
 *   cell_id, region_id, lat, lon, resolution_m, coverage_score,
 *   confidence_tag, shap_top3, model_version, scoring_run_id
 *
 * Empty results are returned as [] — not a 404 or an error.
 * Supabase credentials are never exposed to the client bundle.
 */

import { NextRequest, NextResponse } from 'next/server'
import { getGridCells, ServiceError } from '@/lib/server/geosignal-service'
import { makeError, ERR, isValidRegion } from '@/lib/api-types'
import type { RegionId } from '@/lib/api-types'

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)

  const region_id       = searchParams.get('region_id')
  const resolution_m_str = searchParams.get('resolution_m')
  const target_area_id  = searchParams.get('target_area_id') ?? undefined

  // ── Validate region_id ──────────────────────────────────────────────────
  if (!isValidRegion(region_id)) {
    return NextResponse.json(
      makeError(
        ERR.INVALID_REGION,
        `region_id must be one of: ntt, ntb, central_kalimantan. Received: ${String(region_id)}`,
      ),
      { status: 400 },
    )
  }

  // ── Validate resolution_m ───────────────────────────────────────────────
  if (resolution_m_str === null || resolution_m_str.trim() === '') {
    return NextResponse.json(
      makeError(ERR.INVALID_REQUEST, 'resolution_m is required.'),
      { status: 400 },
    )
  }

  const resolution_m = Number(resolution_m_str)
  if (!Number.isInteger(resolution_m) || resolution_m <= 0) {
    return NextResponse.json(
      makeError(ERR.INVALID_REQUEST, 'resolution_m must be a positive integer.'),
      { status: 400 },
    )
  }

  // ── Call service ────────────────────────────────────────────────────────
  try {
    const cells = await getGridCells(region_id as RegionId, resolution_m, target_area_id)
    // Empty array is valid — not an error (Req 3.1)
    return NextResponse.json(cells, { status: 200 })
  } catch (err) {
    if (err instanceof ServiceError) {
      // Do not leak internal DB details to the client
      return NextResponse.json(
        makeError(ERR.SERVICE_ERROR, 'Failed to retrieve grid cells.'),
        { status: 500 },
      )
    }
    return NextResponse.json(
      makeError(ERR.SERVICE_ERROR, 'An unexpected error occurred.'),
      { status: 500 },
    )
  }
}
