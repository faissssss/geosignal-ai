/**
 * geosignal-service.ts — Thin server-side service boundary for Task 25 routes.
 *
 * This module is the ONLY place that calls Supabase from within the API routes.
 * Route handlers call these functions and map the results to HTTP responses.
 * Business logic (scoring, snapping, SHAP, LOS) lives exclusively in the Python
 * backend. These functions read/write Supabase only — they never compute Coverage
 * Scores, simulate BTS placement, or snap coordinates themselves.
 *
 * Every function either returns a typed result or throws a ServiceError.
 * Routes catch ServiceError and map it to the appropriate HTTP status.
 *
 * The service is designed to be easy to mock in unit tests:
 *   vi.mock('@/lib/server/geosignal-service', () => ({ ... }))
 *
 * Note on type casting: Supabase's generated types are not available in this
 * project, so query results are cast through `unknown` to our own domain types.
 * This is safe because the select columns exactly match the domain type fields.
 */

import { createClient } from '@/lib/supabase/server'
import type {
  BTSCandidate,
  GridCellResponse,
  SimulationResult,
  UnavailableScenario,
  DragDropResult,
  OutsideExtentError,
  TargetArea,
  RegionId,
  SelectionMethod,
  InsufficientCandidatesResult,
} from '@/lib/api-types'

// ---------------------------------------------------------------------------
// ServiceError — structured error thrown by service functions
// ---------------------------------------------------------------------------

export type ServiceErrorCode =
  | 'NOT_FOUND'
  | 'UNPROCESSABLE'
  | 'SERVICE_ERROR'
  | 'INSUFFICIENT_CANDIDATES'
  | 'SERVICE_UNAVAILABLE'

export class ServiceError extends Error {
  constructor(
    public readonly code: ServiceErrorCode,
    message: string,
  ) {
    super(message)
    this.name = 'ServiceError'
  }
}

// ---------------------------------------------------------------------------
// Internal row shapes — used to type-safely access Supabase query results
// after casting through unknown.
// ---------------------------------------------------------------------------

interface WhatIfGridSimRow {
  before_heatmap:         unknown
  after_heatmap:          unknown
  pct_good_change:        number
  villages_newly_covered: number
  new_coverage_score:     number
  elapsed_ms:             number | null
}

interface AdminBoundaryRow {
  boundary_geojson: object
}

// ---------------------------------------------------------------------------
// Task 25.1 — getRankedCandidates
// ---------------------------------------------------------------------------

/**
 * Fetch ranked BTS candidates for a target area from Supabase.
 * Returns the full candidate list or an InsufficientCandidatesResult.
 * Never fabricates candidates.
 */
export async function getRankedCandidates(
  target_area_id: string,
): Promise<BTSCandidate[] | InsufficientCandidatesResult> {
  const supabase = await createClient()

  const { data, error } = await supabase
    .from('bts_candidates')
    .select(
      'candidate_id, region_id, target_area_id, rank, lat, lon, ' +
      'expected_improvement, los_validated, confidence_tag, shap_values, ' +
      'model_version, scoring_run_id, excluded_by_canopy',
    )
    .eq('target_area_id', target_area_id)
    .order('rank', { ascending: true })

  if (error) {
    throw new ServiceError('SERVICE_ERROR', `Database error fetching candidates: ${error.message}`)
  }

  const rows = (data as unknown as BTSCandidate[]) ?? []

  // Fewer than 2 candidates → InsufficientCandidatesResult (Req 4.7)
  if (rows.length < 2) {
    return {
      insufficient_candidates: true,
      surviving_count: rows.length,
      reason:
        rows.length === 0
          ? 'No candidates found for this target area.'
          : 'Only one candidate survived all filters; at least two are required.',
      target_area_id,
    } satisfies InsufficientCandidatesResult
  }

  return rows
}

// ---------------------------------------------------------------------------
// Task 25.2 — simulateBTSPlacement
// ---------------------------------------------------------------------------

/**
 * Look up precomputed what-if grid for a candidate+region pair.
 * Returns SimulationResult on success or UnavailableScenario if missing.
 * Never computes, interpolates, or extrapolates (Req 5.4, Property 12).
 */
export async function simulateBTSPlacement(
  candidate_id: string,
  region_id: RegionId,
): Promise<SimulationResult | UnavailableScenario> {
  const supabase = await createClient()

  const { data, error } = await supabase
    .from('whatif_grid')
    .select(
      'before_heatmap, after_heatmap, pct_good_change, ' +
      'villages_newly_covered, new_coverage_score, elapsed_ms',
    )
    .eq('candidate_id', candidate_id)
    .eq('region_id', region_id)
    .maybeSingle()

  if (error) {
    throw new ServiceError('SERVICE_ERROR', `Database error during simulation lookup: ${error.message}`)
  }

  if (!data) {
    // No precomputed entry — return UnavailableScenario, never interpolate
    return {
      unavailable: true,
      candidate_id,
      region_id,
      message: 'No precomputed scenario available for this candidate and region.',
    } satisfies UnavailableScenario
  }

  const row = data as unknown as WhatIfGridSimRow

  return {
    before_heatmap:         row.before_heatmap         ?? {},
    after_heatmap:          row.after_heatmap           ?? {},
    pct_good_change:        row.pct_good_change,
    villages_newly_covered: row.villages_newly_covered,
    new_coverage_score:     row.new_coverage_score,
    elapsed_ms:             row.elapsed_ms              ?? 0,
  } satisfies SimulationResult
}

// ---------------------------------------------------------------------------
// Task 25.3 — dragDropLookup
// ---------------------------------------------------------------------------

/**
 * Drag-and-drop snap, coverage score, and comparison computation belongs
 * exclusively to the Python backend (Task 20.1 — drag_drop_lookup via
 * BallTree / whatif_grid). The Next.js layer is a thin pass-through.
 *
 * The Python bridge is not yet integrated in this project (Task 25 scope).
 * Until the bridge is wired, this function raises SERVICE_UNAVAILABLE so
 * the route correctly returns a structured 503 — never a mock result.
 *
 * When the bridge becomes available, replace this body with a call to the
 * Python service endpoint; do NOT reimplement snap logic here in TypeScript.
 */
export async function dragDropLookup(
  _lat: number,
  _lon: number,
  _region_id: RegionId,
  _overlay_enabled: boolean,
): Promise<DragDropResult | OutsideExtentError> {
  throw new ServiceError(
    'SERVICE_UNAVAILABLE',
    'Drag-and-drop snap and coverage lookup requires the Python backend bridge, ' +
    'which is not yet integrated. Implement the bridge in Task 26+ before enabling this route.',
  )
}

// ---------------------------------------------------------------------------
// Task 25.4 — resolveTargetArea
// ---------------------------------------------------------------------------

/**
 * Resolve a Planner-specified target area.
 * For kecamatan: looks up GADM boundary from admin_boundaries.
 * For drawn_polygon: uses the submitted GeoJSON directly.
 * Persists the resolved TargetArea to target_areas table.
 * Never auto-repairs an invalid drawn polygon (Error Handling in design.md).
 */
export async function resolveTargetArea(
  region_id: RegionId,
  selection_method: SelectionMethod,
  payload: object | string,
): Promise<TargetArea> {
  const supabase = await createClient()

  let boundary_geojson: object
  let kecamatan_id: string | null = null

  if (selection_method === 'kecamatan') {
    kecamatan_id = payload as string

    const { data, error } = await supabase
      .from('admin_boundaries')
      .select('boundary_geojson')
      .eq('kecamatan_id', kecamatan_id)
      .eq('region_id', region_id)
      .maybeSingle()

    if (error) {
      throw new ServiceError('SERVICE_ERROR', `Database error looking up kecamatan: ${error.message}`)
    }
    if (!data) {
      throw new ServiceError(
        'NOT_FOUND',
        `Kecamatan '${kecamatan_id}' not found in admin_boundaries for region '${region_id}'.`,
      )
    }
    boundary_geojson = (data as unknown as AdminBoundaryRow).boundary_geojson
  } else {
    // drawn_polygon — use submitted GeoJSON directly, no auto-repair
    boundary_geojson = payload as object
  }

  const target_area_id = crypto.randomUUID()
  const created_at = new Date().toISOString()

  const { error: insertError } = await supabase
    .from('target_areas')
    .insert({
      target_area_id,
      region_id,
      selection_method,
      kecamatan_id,
      boundary_geojson,
      created_at,
    })

  if (insertError) {
    throw new ServiceError(
      'SERVICE_ERROR',
      `Failed to persist target area: ${insertError.message}`,
    )
  }

  return {
    target_area_id,
    region_id,
    selection_method,
    kecamatan_id,
    boundary_geojson,
    created_at,
  } satisfies TargetArea
}

// ---------------------------------------------------------------------------
// Task 25.5 — getGridCells
// ---------------------------------------------------------------------------

/**
 * Fetch Coverage Score grid cells from Supabase for heatmap rendering.
 * Filtered server-side by region_id, resolution_m, and optionally target_area_id.
 * Returns only the fields required by CoverageHeatmap and SidePanel.
 * Empty results are returned as [] — not an error.
 */
export async function getGridCells(
  region_id: RegionId,
  resolution_m: number,
  target_area_id?: string,
): Promise<GridCellResponse[]> {
  const supabase = await createClient()

  let query = supabase
    .from('grid_cells')
    .select(
      'cell_id, region_id, lat, lon, resolution_m, coverage_score, ' +
      'confidence_tag, shap_top3, model_version, scoring_run_id',
    )
    .eq('region_id', region_id)
    .eq('resolution_m', resolution_m)

  if (target_area_id) {
    query = query.eq('target_area_id', target_area_id)
  }

  const { data, error } = await query

  if (error) {
    throw new ServiceError('SERVICE_ERROR', `Database error fetching grid cells: ${error.message}`)
  }

  return ((data as unknown as GridCellResponse[]) ?? [])
}
