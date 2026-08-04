/**
 * POST /api/drag-drop — Task 25.3
 * Requirements: 6.1, 6.3, 6.4, 6.5, 6.6, 6.7
 *
 * Accepts a dropped coordinate and returns the precomputed DragDropResult
 * from the nearest what-if grid cell.
 *
 * Invariants enforced here (beyond service-level):
 *   - overlay_enabled MUST NOT change coverage_score (Req 6.5, Property 14)
 *   - manual_wins is forwarded unchanged — never suppressed (Req 6.3, 6.4)
 *   - OutsideExtentError response never includes a Coverage Score
 *
 * Response is compatible with DragDropMarker.tsx and PowerOverlay.tsx (Task 24).
 */

import { NextRequest, NextResponse } from 'next/server'
import { dragDropLookup, ServiceError } from '@/lib/server/geosignal-service'
import { makeError, ERR, isValidRegion } from '@/lib/api-types'
import type { RegionId } from '@/lib/api-types'

export async function POST(request: NextRequest) {
  // ── Parse body ──────────────────────────────────────────────────────────
  let body: unknown
  try {
    body = await request.json()
  } catch {
    return NextResponse.json(
      makeError(ERR.INVALID_REQUEST, 'Request body must be valid JSON.'),
      { status: 400 },
    )
  }

  if (typeof body !== 'object' || body === null) {
    return NextResponse.json(
      makeError(ERR.INVALID_REQUEST, 'Request body must be a JSON object.'),
      { status: 400 },
    )
  }

  const { lat, lon, region_id, overlay_enabled } = body as Record<string, unknown>

  // ── Validate lat ────────────────────────────────────────────────────────
  if (typeof lat !== 'number' || !Number.isFinite(lat)) {
    return NextResponse.json(
      makeError(ERR.INVALID_REQUEST, 'lat must be a finite number.'),
      { status: 400 },
    )
  }
  if (lat < -90 || lat > 90) {
    return NextResponse.json(
      makeError(ERR.INVALID_REQUEST, 'lat must be between -90 and 90.'),
      { status: 400 },
    )
  }

  // ── Validate lon ────────────────────────────────────────────────────────
  if (typeof lon !== 'number' || !Number.isFinite(lon)) {
    return NextResponse.json(
      makeError(ERR.INVALID_REQUEST, 'lon must be a finite number.'),
      { status: 400 },
    )
  }
  if (lon < -180 || lon > 180) {
    return NextResponse.json(
      makeError(ERR.INVALID_REQUEST, 'lon must be between -180 and 180.'),
      { status: 400 },
    )
  }

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

  // ── Validate overlay_enabled (optional, must be boolean if present) ─────
  if (overlay_enabled !== undefined && typeof overlay_enabled !== 'boolean') {
    return NextResponse.json(
      makeError(ERR.INVALID_REQUEST, 'overlay_enabled must be a boolean when provided.'),
      { status: 400 },
    )
  }

  const overlayEnabledBool: boolean = overlay_enabled === true

  // ── Call service ────────────────────────────────────────────────────────
  try {
    const result = await dragDropLookup(lat, lon, region_id as RegionId, overlayEnabledBool)

    // OutsideExtentError → 422: the coordinate is unprocessable for this region.
    // Discriminator and message preserved; no coverage_score in the response
    // (OutsideExtentError type does not contain that field).
    // manual_wins is on DragDropResult only — forwarded unchanged.
    if ('outside_extent' in result && result.outside_extent === true) {
      return NextResponse.json(result, { status: 422 })
    }

    return NextResponse.json(result, { status: 200 })
  } catch (err) {
    if (err instanceof ServiceError) {
      const status = err.code === 'SERVICE_UNAVAILABLE' ? 503 : 500
      return NextResponse.json(
        makeError(err.code, err.message),
        { status },
      )
    }
    return NextResponse.json(
      makeError(ERR.SERVICE_ERROR, 'An unexpected error occurred.'),
      { status: 500 },
    )
  }
}
