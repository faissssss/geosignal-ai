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
  LandCoverTileSet,
  ContourFeature,
  VillageFeature,
  BTSLocation,
  DataSourceKind,
} from '@/lib/api-types'
import type { AdminBoundary } from '@/lib/types'

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
  pct_good_change:        number
  villages_newly_covered: number
  new_coverage_score:     number
  delta_coverage_score:   number | null
  snapped_lat:            number
  snapped_lon:            number
  grid_resolution_m:      number
}

interface AdminBoundaryRow {
  kecamatan_id: string
  kecamatan_name: string
  region_id: string
  boundary_geojson: object
}

// ---------------------------------------------------------------------------
// Helper: Derive region_id from GADM NAME_1 property
// ---------------------------------------------------------------------------

/**
 * Map GADM Level 1 province name to project region_id.
 * Reverses the REGION_PROVINCE_FILTERS mapping from backend.
 */
function deriveRegionIdFromGADM(name1: string): RegionId {
  const normalized = name1.toLowerCase().replace(/\s/g, '')
  
  if (normalized.includes('nusatenggaratimur')) return 'ntt'
  if (normalized.includes('nusatenggarabarat')) return 'ntb'
  if (normalized.includes('kalimantantengah')) return 'central_kalimantan'
  
  // Should never happen if database is correctly populated by backend parser
  throw new ServiceError(
    'SERVICE_ERROR',
    `Unknown GADM province: ${name1}. Admin boundaries may not be loaded for this region.`
  )
}

// ---------------------------------------------------------------------------
// fetchAdminBoundaries — Load admin boundaries for a region
// ---------------------------------------------------------------------------

/**
 * Fetch admin boundaries (kecamatan polygons) for the given region from Supabase.
 * Used by TargetAreaSelector to populate the kecamatan dropdown.
 * Returns empty array if no boundaries exist for the region.
 */
export async function fetchAdminBoundaries(
  region_id: RegionId,
): Promise<AdminBoundary[]> {
  const supabase = await createClient()

  const { data, error } = await supabase
    .from('admin_boundaries')
    .select('kecamatan_id, kecamatan_name, region_id, boundary_geojson')
    .eq('region_id', region_id)
    .order('kecamatan_name', { ascending: true })

  if (error) {
    throw new ServiceError(
      'SERVICE_ERROR',
      `Database error fetching admin boundaries: ${error.message}`
    )
  }

  const rows = ((data as unknown as AdminBoundaryRow[]) ?? [])

  // Map to AdminBoundary interface using correct GADM property mapping
  return rows.map(row => ({
    boundary_id: row.kecamatan_id,      // GID_2 from backend parse
    kecamatan_id: row.kecamatan_id,     // GID_2 from backend parse
    kecamatan_name: row.kecamatan_name, // NAME_2 from backend parse
    region_id: row.region_id,           // region_id from backend parse
    boundary_geojson: row.boundary_geojson,
  }))
}

// ---------------------------------------------------------------------------
// Task 25.1 — getRankedCandidates
// ---------------------------------------------------------------------------

/**
 * Fetch ranked BTS candidates for a target area from Supabase.
 * Returns the full candidate list or an InsufficientCandidatesResult.
 * Never fabricates candidates.
 * 
 * Special case: If target_area_id starts with "region:", queries by region_id instead.
 * This supports initial load before a specific target area is selected.
 */
export async function getRankedCandidates(
  target_area_id: string,
): Promise<BTSCandidate[] | InsufficientCandidatesResult> {
  const supabase = await createClient()

  // Check if this is a region-wide query (e.g., "region:ntt")
  const isRegionQuery = target_area_id.startsWith('region:')
  const region_id = isRegionQuery ? target_area_id.replace('region:', '') as RegionId : null

  let query = supabase
    .from('bts_candidates')
    .select(
      'candidate_id, region_id, target_area_id, rank, lat, lon, ' +
      'expected_improvement, los_validated, confidence_tag, shap_values, ' +
      'model_version, scoring_run_id, excluded_by_canopy',
    )

  // Apply filter based on query type
  if (isRegionQuery && region_id) {
    query = query.eq('region_id', region_id)
  } else {
    query = query.eq('target_area_id', target_area_id)
  }

  query = query.order('rank', { ascending: true})

  const { data, error } = await query

  if (error) {
    throw new ServiceError('SERVICE_ERROR', `Database error fetching candidates: ${error.message}`)
  }

  const rows = (data as unknown as BTSCandidate[]) ?? []

  // For region-wide queries, return all candidates (no minimum count requirement)
  if (isRegionQuery) {
    return rows
  }

  // For specific target area queries, enforce minimum 2 candidates (Req 4.7)
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
      'pct_good_change, villages_newly_covered, new_coverage_score, ' +
      'delta_coverage_score, snapped_lat, snapped_lon, grid_resolution_m',
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

  // before_heatmap / after_heatmap are derived by the Python backend from the
  // precomputed grid row; the thin service cannot recompute cell-level heatmaps
  // (Req 5.4). Expose the stored metrics and an empty delta for the snapshots.
  return {
    before_heatmap:         {},
    after_heatmap:          {},
    pct_good_change:        row.pct_good_change,
    villages_newly_covered: row.villages_newly_covered,
    new_coverage_score:     row.new_coverage_score,
    elapsed_ms:             0,
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

  // Note: target_area_id filtering is not yet implemented in grid_cells schema
  // For now, we filter by region_id and resolution_m only
  // TODO: Add target_area_id column to grid_cells if spatial filtering is needed

  const { data, error } = await query

  if (error) {
    throw new ServiceError('SERVICE_ERROR', `Database error fetching grid cells: ${error.message}`)
  }

  return ((data as unknown as GridCellResponse[]) ?? [])
}

// ---------------------------------------------------------------------------
// Data Production — Supporting layer lookups (Phase 4/5)
//
// These are thin pass-through reads for the layer feeds the map overlays:
// land cover tile sets, contours, villages, and BTS towers. Every row is
// region-scoped and carries an explicit data_source; an empty or status-less
// result is returned as-is so the UI reports unavailable rather than
// fabricating features (data-production/expected-outcomes.md Phase 4).
// ---------------------------------------------------------------------------

/**
 * Normalise the DB `data_source_kind` enum into the domain union. Anything
 * unrecognised maps to 'demo' so we never invent a missing status.
 */
function toDataSourceKind(status: string | undefined | null): DataSourceKind {
  if (status === 'real' || status === 'derived' || status === 'unavailable') return status
  return 'demo'
}

interface LandCoverTileSetRow {
  set_id:       string
  region_id:    string
  layer_id:     string
  tiles_url:    string | null
  attribution:  string | null
  status:       string
  created_at:   string
}

export async function getLandCoverTileSets(
  region_id: RegionId,
): Promise<LandCoverTileSet[]> {
  const supabase = await createClient()
  const { data, error } = await supabase
    .from('landcover_tile_sets')
    .select('set_id, region_id, layer_id, tiles_url, attribution, status, created_at')
    .eq('region_id', region_id)
    .order('created_at', { ascending: true })

  if (error) {
    throw new ServiceError('SERVICE_ERROR', `Database error fetching land cover tiles: ${error.message}`)
  }

  const rows = ((data as unknown as LandCoverTileSetRow[]) ?? [])
  return rows.map(row => {
    const source = toDataSourceKind(row.status)
    return {
      set_id:      row.set_id,
      region_id:   row.region_id,
      layer_id:    row.layer_id,
      tiles_url:   row.tiles_url,
      attribution: row.attribution,
      status:      source,
      data_source: source,
      created_at:  row.created_at,
    } satisfies LandCoverTileSet
  })
}

interface ContourFeatureRow {
  feature_id:    string
  region_id:     string
  kecamatan_id:  string | null
  elevation_m:   number
  status:        string
  geom_geojson:  object
}

export async function getContourFeatures(
  region_id: RegionId,
  kecamatan_id?: string,
): Promise<ContourFeature[]> {
  const supabase = await createClient()
  let query = supabase
    .from('contour_features')
    .select('feature_id, region_id, kecamatan_id, elevation_m, status, geom_geojson')
    .eq('region_id', region_id)

  if (kecamatan_id) query = query.eq('kecamatan_id', kecamatan_id)

  const { data, error } = await query
  if (error) {
    throw new ServiceError('SERVICE_ERROR', `Database error fetching contour features: ${error.message}`)
  }

  const rows = ((data as unknown as ContourFeatureRow[]) ?? [])
  return rows.map(row => {
    const source = toDataSourceKind(row.status)
    return {
      feature_id:     row.feature_id,
      region_id:      row.region_id,
      kecamatan_id:   row.kecamatan_id,
      elevation_m:    row.elevation_m,
      geom_geojson:   row.geom_geojson,
      status:         source,
      data_source:    source,
    } satisfies ContourFeature
  })
}

interface VillageFeatureRow {
  feature_id:    string
  region_id:     string
  kecamatan_id:  string | null
  village_name:  string | null
  attribution:   string | null
  status:        string
  geom_geojson:  object
}

export async function getVillageFeatures(
  region_id: RegionId,
  kecamatan_id?: string,
): Promise<VillageFeature[]> {
  const supabase = await createClient()
  let query = supabase
    .from('village_features')
    .select('feature_id, region_id, kecamatan_id, village_name, attribution, status, geom_geojson')
    .eq('region_id', region_id)

  if (kecamatan_id) query = query.eq('kecamatan_id', kecamatan_id)

  const { data, error } = await query
  if (error) {
    throw new ServiceError('SERVICE_ERROR', `Database error fetching village features: ${error.message}`)
  }

  const rows = ((data as unknown as VillageFeatureRow[]) ?? [])
  return rows.map(row => {
    const source = toDataSourceKind(row.status)
    return {
      feature_id:     row.feature_id,
      region_id:      row.region_id,
      kecamatan_id:   row.kecamatan_id,
      village_name:   row.village_name,
      attribution:    row.attribution,
      geom_geojson:   row.geom_geojson,
      status:         source,
      data_source:    source,
    } satisfies VillageFeature
  })
}

interface BTSLocationRow {
  tower_id:   string
  region_id:  string
  lat:        number
  lon:        number
  mcc:        number | null
  mnc:        number | null
  lac:        number | null
  cell_id:    number | null
  status:     string
}

export async function getBTSLocations(
  region_id: RegionId,
): Promise<BTSLocation[]> {
  const supabase = await createClient()
  const { data, error } = await supabase
    .from('bts_locations')
    .select('tower_id, region_id, lat, lon, mcc, mnc, lac, cell_id, status')
    .eq('region_id', region_id)

  if (error) {
    throw new ServiceError('SERVICE_ERROR', `Database error fetching BTS locations: ${error.message}`)
  }

  const rows = ((data as unknown as BTSLocationRow[]) ?? [])
  return rows.map(row => {
    const source = toDataSourceKind(row.status)
    return {
      tower_id:    row.tower_id,
      region_id:   row.region_id,
      lat:         row.lat,
      lon:         row.lon,
      mcc:         row.mcc,
      mnc:         row.mnc,
      lac:         row.lac,
      cell:        row.cell_id,
      status:      source,
      data_source: source,
    } satisfies BTSLocation
  })
}
