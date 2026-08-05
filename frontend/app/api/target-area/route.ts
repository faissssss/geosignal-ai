/**
 * POST /api/target-area — Task 25.4
 * Requirements: 10.7, 10.8
 *
 * Resolves a Planner-specified target area by either:
 *   drawn_polygon — validates the GeoJSON Polygon, persists as-is
 *   kecamatan     — looks up the GADM boundary from admin_boundaries
 *
 * Validation rules:
 *   - Drawn polygons must have the correct GeoJSON type and non-empty coordinates.
 *   - Invalid polygons are REJECTED — never auto-repaired (design.md Error Handling).
 *   - Kecamatan payload must be a non-empty string.
 *   - region_id and selection_method are required.
 *
 * Response is compatible with TargetAreaSelector.tsx (Task 23.5).
 */

import { NextRequest, NextResponse } from 'next/server'
import { resolveTargetArea, ServiceError } from '@/lib/server/geosignal-service'
import { makeError, ERR, isValidRegion } from '@/lib/api-types'
import type { RegionId, SelectionMethod } from '@/lib/api-types'

const VALID_SELECTION_METHODS: ReadonlySet<SelectionMethod> = new Set([
  'drawn_polygon',
  'kecamatan',
])

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

  const { region_id, selection_method, payload } = body as Record<string, unknown>

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

  // ── Validate selection_method ───────────────────────────────────────────
  if (
    typeof selection_method !== 'string' ||
    !VALID_SELECTION_METHODS.has(selection_method as SelectionMethod)
  ) {
    return NextResponse.json(
      makeError(
        ERR.INVALID_REQUEST,
        `selection_method must be 'drawn_polygon' or 'kecamatan'. Received: ${String(selection_method)}`,
      ),
      { status: 400 },
    )
  }

  // ── Validate payload per selection_method ──────────────────────────────
  if (selection_method === 'drawn_polygon') {
    // Payload must be a GeoJSON Polygon object with non-empty coordinates
    if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) {
      return NextResponse.json(
        makeError(ERR.INVALID_REQUEST, 'payload must be a GeoJSON Polygon object for drawn_polygon.'),
        { status: 400 },
      )
    }
    const geom = payload as Record<string, unknown>
    if (geom.type !== 'Polygon') {
      return NextResponse.json(
        makeError(
          ERR.UNPROCESSABLE,
          `payload.type must be 'Polygon'. Received: '${String(geom.type)}'. Invalid polygons are not auto-repaired.`,
        ),
        { status: 422 },
      )
    }
    if (
      !Array.isArray(geom.coordinates) ||
      geom.coordinates.length === 0 ||
      !Array.isArray((geom.coordinates as unknown[][])[0]) ||
      ((geom.coordinates as unknown[][])[0] as unknown[]).length === 0
    ) {
      return NextResponse.json(
        makeError(ERR.UNPROCESSABLE, 'payload.coordinates must be a non-empty Polygon ring array.'),
        { status: 422 },
      )
    }
  } else {
    // kecamatan — payload must be a non-empty string
    if (typeof payload !== 'string' || payload.trim().length === 0) {
      return NextResponse.json(
        makeError(ERR.INVALID_REQUEST, 'payload must be a non-empty kecamatan_id string for kecamatan selection.'),
        { status: 400 },
      )
    }
  }

  // ── Call service ────────────────────────────────────────────────────────
  try {
    const targetArea = await resolveTargetArea(
      region_id as RegionId,
      selection_method as SelectionMethod,
      payload as object | string,
    )
    return NextResponse.json(targetArea, { status: 200 })
  } catch (err) {
    if (err instanceof ServiceError) {
      if (err.code === 'NOT_FOUND') {
        return NextResponse.json(makeError(err.code, err.message), { status: 404 })
      }
      if (err.code === 'UNPROCESSABLE') {
        return NextResponse.json(makeError(err.code, err.message), { status: 422 })
      }
      return NextResponse.json(makeError(err.code, err.message), { status: 500 })
    }
    return NextResponse.json(
      makeError(ERR.SERVICE_ERROR, 'An unexpected error occurred.'),
      { status: 500 },
    )
  }
}
