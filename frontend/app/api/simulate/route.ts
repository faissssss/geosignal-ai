/**
 * POST /api/simulate — Task 25.2
 * Requirements: 5.1, 5.3, 5.4
 *
 * Looks up the precomputed Before/After simulation result for a
 * (candidate_id, region_id) pair.
 *
 * When no precomputed entry exists, returns UnavailableScenario with the
 * human-readable message from the service — no fallback estimate is computed,
 * interpolated, or extrapolated (Req 5.4, Property 12).
 *
 * Response is compatible with SimulationPanel.tsx (Task 24.1).
 */

import { NextRequest, NextResponse } from 'next/server'
import { simulateBTSPlacement, ServiceError } from '@/lib/server/geosignal-service'
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

  const { candidate_id, region_id } = body as Record<string, unknown>

  // ── Validate candidate_id ───────────────────────────────────────────────
  if (typeof candidate_id !== 'string' || candidate_id.trim().length === 0) {
    return NextResponse.json(
      makeError(ERR.INVALID_REQUEST, 'candidate_id is required and must be a non-empty string.'),
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

  // ── Call service ────────────────────────────────────────────────────────
  try {
    const result = await simulateBTSPlacement(candidate_id.trim(), region_id as RegionId)

    // UnavailableScenario → 404: the scenario does not exist in the precomputed
    // grid. The discriminator and human-readable message are preserved so
    // SimulationPanel.tsx can display them (discriminates on unavailable:true).
    if ('unavailable' in result && result.unavailable === true) {
      return NextResponse.json(result, { status: 404 })
    }

    return NextResponse.json(result, { status: 200 })
  } catch (err) {
    if (err instanceof ServiceError) {
      return NextResponse.json(
        makeError(err.code, err.message),
        { status: 500 },
      )
    }
    return NextResponse.json(
      makeError(ERR.SERVICE_ERROR, 'An unexpected error occurred.'),
      { status: 500 },
    )
  }
}
