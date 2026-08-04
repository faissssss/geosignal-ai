/**
 * POST /api/recommendations — Task 25.1
 * Requirements: 4.1, 4.6, 4.7, 8.4, 11.3
 *
 * Accepts a target_area_id and returns ranked BTS candidates from the
 * precomputed Supabase table. All metadata (LOS, SHAP, model version,
 * scoring run ID, confidence) is forwarded without modification.
 *
 * When fewer than 2 candidates survive filtering the backend returns an
 * InsufficientCandidatesResult — this is forwarded as-is; no fake candidates
 * are added (Req 4.7).
 */

import { NextRequest, NextResponse } from 'next/server'
import { getRankedCandidates } from '@/lib/server/geosignal-service'
import { ServiceError } from '@/lib/server/geosignal-service'
import { makeError, ERR } from '@/lib/api-types'

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

  // ── Validate required fields ────────────────────────────────────────────
  const { target_area_id } = body as Record<string, unknown>

  if (
    typeof target_area_id !== 'string' ||
    target_area_id.trim().length === 0
  ) {
    return NextResponse.json(
      makeError(ERR.INVALID_REQUEST, 'target_area_id is required and must be a non-empty string.'),
      { status: 400 },
    )
  }

  // ── Call service ────────────────────────────────────────────────────────
  try {
    const result = await getRankedCandidates(target_area_id.trim())
    // Forward the result unchanged — either BTSCandidate[] or InsufficientCandidatesResult.
    // Never add fabricated candidates when count < 2.
    return NextResponse.json(result, { status: 200 })
  } catch (err) {
    if (err instanceof ServiceError) {
      return NextResponse.json(
        makeError(err.code, err.message),
        { status: 500 },
      )
    }
    // Unexpected error — do not leak internals
    return NextResponse.json(
      makeError(ERR.SERVICE_ERROR, 'An unexpected error occurred.'),
      { status: 500 },
    )
  }
}
