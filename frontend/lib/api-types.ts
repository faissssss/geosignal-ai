/**
 * api-types.ts — Shared API request/response types for Task 25 routes.
 *
 * These types are used by both the route handlers and the unit tests.
 * They mirror the backend Python models (backend/geosignal/models.py)
 * without duplicating business logic.
 *
 * Discriminated unions let the frontend reliably distinguish success from
 * error variants without relying on HTTP status alone.
 */

import type {
  BTSCandidate,
  GridCell,
  SimulationResult,
  UnavailableScenario,
  DragDropResult,
  OutsideExtentError,
  TargetArea,
  RegionId,
  SelectionMethod,
  ConfidenceLevel,
  ShapEntry,
  ComparisonPanel,
} from '@/lib/types'

// ---------------------------------------------------------------------------
// Canonical region set — validated in every route that accepts region_id
// ---------------------------------------------------------------------------

export const VALID_REGIONS: ReadonlySet<RegionId> = new Set([
  'ntt',
  'ntb',
  'central_kalimantan',
])

export function isValidRegion(value: unknown): value is RegionId {
  return typeof value === 'string' && VALID_REGIONS.has(value as RegionId)
}

// ---------------------------------------------------------------------------
// Consistent error envelope
// ---------------------------------------------------------------------------

export interface ApiError {
  error: {
    code: string
    message: string
  }
}

/** Build a typed API error response body. */
export function makeError(code: string, message: string): ApiError {
  return { error: { code, message } }
}

// Error codes used across routes
export const ERR = {
  INVALID_REQUEST:     'INVALID_REQUEST',
  INVALID_REGION:      'INVALID_REGION',
  NOT_FOUND:           'NOT_FOUND',
  UNPROCESSABLE:       'UNPROCESSABLE',
  SERVICE_ERROR:       'SERVICE_ERROR',
  SERVICE_UNAVAILABLE: 'SERVICE_UNAVAILABLE',
} as const

// ---------------------------------------------------------------------------
// Task 25.1 — Recommendations
// ---------------------------------------------------------------------------

export interface RecommendationsRequest {
  target_area_id: string
}

/** Forwarded when the backend cannot produce ≥2 candidates (Req 4.7). */
export interface InsufficientCandidatesResult {
  insufficient_candidates: true
  surviving_count: number
  reason: string
  target_area_id: string
}

export type RecommendationsResponse =
  | BTSCandidate[]
  | InsufficientCandidatesResult

// ---------------------------------------------------------------------------
// Task 25.2 — Simulation
// ---------------------------------------------------------------------------

export interface SimulateRequest {
  candidate_id: string
  region_id: RegionId
}

// SimulationResult | UnavailableScenario already defined in lib/types.ts

// ---------------------------------------------------------------------------
// Task 25.3 — Drag-and-Drop
// ---------------------------------------------------------------------------

export interface DragDropRequest {
  lat: number
  lon: number
  region_id: RegionId
  overlay_enabled?: boolean
}

// DragDropResult | OutsideExtentError already defined in lib/types.ts

// ---------------------------------------------------------------------------
// Task 25.4 — Target Area
// ---------------------------------------------------------------------------

export interface TargetAreaRequest {
  region_id: RegionId
  selection_method: SelectionMethod
  /** GeoJSON Polygon object for drawn_polygon; kecamatan_id string for kecamatan */
  payload: object | string
}

// TargetArea already defined in lib/types.ts

// ---------------------------------------------------------------------------
// Task 25.5 — Grid Cells
// ---------------------------------------------------------------------------

export interface GridCellsQuery {
  region_id: RegionId
  resolution_m: number
  target_area_id?: string
}

/** Subset of GridCell fields required by the heatmap and side panel. */
export interface GridCellResponse {
  cell_id: string
  region_id: string
  lat: number
  lon: number
  resolution_m: number
  coverage_score: number
  confidence_tag: ConfidenceLevel
  shap_top3: ShapEntry[]
  model_version: string
  scoring_run_id: string
  /** ISO 8601 timestamp from the scoring run. Undefined when not yet available. */
  scoring_run_timestamp?: string
}

// ---------------------------------------------------------------------------
// Re-export backend model types so routes import from one place
// ---------------------------------------------------------------------------

export type {
  BTSCandidate,
  GridCell,
  SimulationResult,
  UnavailableScenario,
  DragDropResult,
  OutsideExtentError,
  TargetArea,
  RegionId,
  SelectionMethod,
  ComparisonPanel,
}
