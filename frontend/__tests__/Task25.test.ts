/**
 * Task 25 unit tests — Next.js API routes
 *
 * Strategy:
 *  - vi.mock the service module so no real Supabase calls are made.
 *  - Construct NextRequest with the helpers below.
 *  - Call route handlers directly and inspect the NextResponse JSON + status.
 *
 * Tests are numbered to match the task spec (1–26).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

// ---------------------------------------------------------------------------
// Mock the service boundary — all DB calls are isolated here
// ---------------------------------------------------------------------------
vi.mock('@/lib/server/geosignal-service', () => ({
  getRankedCandidates:  vi.fn(),
  simulateBTSPlacement: vi.fn(),
  dragDropLookup:       vi.fn(),
  resolveTargetArea:    vi.fn(),
  getGridCells:         vi.fn(),
  ServiceError: class ServiceError extends Error {
    code: string
    constructor(code: string, message: string) {
      super(message)
      this.name = 'ServiceError'
      this.code = code
    }
  },
}))

import * as svc from '@/lib/server/geosignal-service'

// Route handlers — imported after mock is registered
import { POST as recoPOST }       from '@/app/api/recommendations/route'
import { POST as simulatePOST }   from '@/app/api/simulate/route'
import { POST as dragDropPOST }   from '@/app/api/drag-drop/route'
import { POST as targetAreaPOST } from '@/app/api/target-area/route'
import { GET  as gridCellsGET }   from '@/app/api/grid-cells/route'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makePostRequest(body: unknown, url = 'http://localhost/api/test'): NextRequest {
  return new NextRequest(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

function makeGetRequest(params: Record<string, string>, url = 'http://localhost/api/grid-cells'): NextRequest {
  const u = new URL(url)
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v)
  return new NextRequest(u.toString(), { method: 'GET' })
}

async function json(res: Response) {
  return res.json()
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const CANDIDATE = {
  candidate_id: 'cand-1', region_id: 'ntt', target_area_id: 'ta-1',
  rank: 1, lat: -9.2, lon: 120.2, expected_improvement: 15,
  los_validated: true, confidence_tag: 'High',
  shap_values: { elevation_m: 6 }, model_version: 'xgb-v2.1',
  scoring_run_id: 'run-001', excluded_by_canopy: false,
}

const INSUFFICIENT = {
  insufficient_candidates: true, surviving_count: 1,
  reason: 'Only one candidate survived.', target_area_id: 'ta-empty',
}

const SIM_RESULT = {
  before_heatmap: {}, after_heatmap: {}, pct_good_change: 12.5,
  villages_newly_covered: 3, new_coverage_score: 74.2, elapsed_ms: 450,
}

const UNAVAILABLE = {
  unavailable: true, candidate_id: 'cand-1', region_id: 'ntt',
  message: 'No precomputed scenario available.',
}

const DRAGDROP_RESULT = {
  snapped_coordinate: [-9.21, 120.21] as [number, number],
  grid_resolution_m: 100, coverage_score: 55.0,
  confidence_tag: 'Med',
  vs_top_candidate: {
    manual_score: 55.0, model_score: 68.0, top_candidate_id: 'cand-1',
    top_candidate_lat: -9.2, top_candidate_lon: 120.2, manual_wins: false,
  },
  elapsed_ms: 300,
}

const OUTSIDE_EXTENT = {
  outside_extent: true, dropped_lat: -1.0, dropped_lon: 110.0,
  region_id: 'ntt', message: 'Outside precomputed grid extent.',
}

const TARGET_AREA = {
  target_area_id: 'ta-new', region_id: 'ntt', selection_method: 'kecamatan',
  kecamatan_id: 'IDN.15.1_1',
  boundary_geojson: { type: 'Polygon', coordinates: [[[119,-9],[120,-9],[120,-10],[119,-10],[119,-9]]] },
  created_at: '2026-01-01T00:00:00Z',
}

const VALID_POLYGON = {
  type: 'Polygon',
  coordinates: [[[119, -9], [120, -9], [120, -10], [119, -10], [119, -9]]],
}

const GRID_CELLS = [
  {
    cell_id: 'c1', region_id: 'ntt', lat: -9.1, lon: 120.1,
    resolution_m: 100, coverage_score: 65, confidence_tag: 'Med',
    shap_top3: [], model_version: 'ahp-v1.0', scoring_run_id: 'run-001',
  },
]

// ---------------------------------------------------------------------------
// Typed mock helpers
// ---------------------------------------------------------------------------

const mockGetCandidates  = svc.getRankedCandidates  as ReturnType<typeof vi.fn>
const mockSimulate       = svc.simulateBTSPlacement as ReturnType<typeof vi.fn>
const mockDragDrop       = svc.dragDropLookup       as ReturnType<typeof vi.fn>
const mockResolveTA      = svc.resolveTargetArea     as ReturnType<typeof vi.fn>
const mockGetCells       = svc.getGridCells          as ReturnType<typeof vi.fn>

// Helper to throw a ServiceError from a mock
function serviceError(code: string, msg: string) {
  const E = (svc as unknown as { ServiceError: new (c: string, m: string) => Error }).ServiceError
  return new E(code, msg)
}

beforeEach(() => {
  vi.clearAllMocks()
})


// ===========================================================================
// Recommendations — Tests 1–5
// ===========================================================================

describe('POST /api/recommendations', () => {
  // Test 1: valid request calls service with target_area_id
  it('T1: valid request calls getRankedCandidates with target_area_id', async () => {
    mockGetCandidates.mockResolvedValue([CANDIDATE, { ...CANDIDATE, candidate_id: 'cand-2', rank: 2 }])
    const req = makePostRequest({ target_area_id: 'ta-1' })
    const res = await recoPOST(req)
    expect(res.status).toBe(200)
    expect(mockGetCandidates).toHaveBeenCalledWith('ta-1')
  })

  // Test 2: empty target_area_id → 400
  it('T2: empty target_area_id returns 400', async () => {
    const req = makePostRequest({ target_area_id: '' })
    const res = await recoPOST(req)
    expect(res.status).toBe(400)
    const body = await json(res)
    expect(body.error.code).toBe('INVALID_REQUEST')
    expect(mockGetCandidates).not.toHaveBeenCalled()
  })

  // Test 3: response includes all required candidate metadata
  it('T3: ranked candidate response forwarded without losing metadata', async () => {
    const cand2 = { ...CANDIDATE, candidate_id: 'cand-2', rank: 2 }
    mockGetCandidates.mockResolvedValue([CANDIDATE, cand2])
    const req = makePostRequest({ target_area_id: 'ta-1' })
    const res = await recoPOST(req)
    const body = await json(res)
    expect(Array.isArray(body)).toBe(true)
    expect(body[0].candidate_id).toBe('cand-1')
    expect(body[0].model_version).toBe('xgb-v2.1')
    expect(body[0].scoring_run_id).toBe('run-001')
    expect(body[0].los_validated).toBe(true)
    expect(body[0].confidence_tag).toBe('High')
    expect(body[0].shap_values).toBeTruthy()
  })

  // Test 4: InsufficientCandidatesResult forwarded without fake candidates
  it('T4: InsufficientCandidatesResult forwarded as-is, no fabricated candidates', async () => {
    mockGetCandidates.mockResolvedValue(INSUFFICIENT)
    const req = makePostRequest({ target_area_id: 'ta-empty' })
    const res = await recoPOST(req)
    expect(res.status).toBe(200)
    const body = await json(res)
    expect(body.insufficient_candidates).toBe(true)
    expect(body.surviving_count).toBe(1)
    expect(Array.isArray(body)).toBe(false)
  })

  // Test 5: service error handled — no stack trace leaked
  it('T5: service error returns 500 without leaking internals', async () => {
    mockGetCandidates.mockRejectedValue(serviceError('SERVICE_ERROR', 'DB connection failed'))
    const req = makePostRequest({ target_area_id: 'ta-1' })
    const res = await recoPOST(req)
    expect(res.status).toBe(500)
    const body = await json(res)
    expect(body.error).toBeTruthy()
    expect(body.error.code).toBe('SERVICE_ERROR')
    // Must not contain stack trace or raw DB error
    expect(JSON.stringify(body)).not.toContain('at Object')
  })

  // Extra: missing target_area_id entirely
  it('T5-extra: missing target_area_id returns 400', async () => {
    const req = makePostRequest({})
    const res = await recoPOST(req)
    expect(res.status).toBe(400)
  })

  // Extra: invalid JSON body
  it('T5-extra-2: invalid JSON body returns 400', async () => {
    const req = new NextRequest('http://localhost/api/recommendations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: 'not-json{{{',
    })
    const res = await recoPOST(req)
    expect(res.status).toBe(400)
  })
})


// ===========================================================================
// Simulate — Tests 6–10
// ===========================================================================

describe('POST /api/simulate', () => {
  // Test 6: valid request calls service with candidate_id and region_id
  it('T6: valid request calls simulateBTSPlacement with candidate_id and region_id', async () => {
    mockSimulate.mockResolvedValue(SIM_RESULT)
    const req = makePostRequest({ candidate_id: 'cand-1', region_id: 'ntt' })
    const res = await simulatePOST(req)
    expect(res.status).toBe(200)
    expect(mockSimulate).toHaveBeenCalledWith('cand-1', 'ntt')
  })

  // Test 7: invalid region_id → 400
  it('T7: invalid region_id returns 400', async () => {
    const req = makePostRequest({ candidate_id: 'cand-1', region_id: 'invalid-region' })
    const res = await simulatePOST(req)
    expect(res.status).toBe(400)
    const body = await json(res)
    expect(body.error.code).toBe('INVALID_REGION')
    expect(mockSimulate).not.toHaveBeenCalled()
  })

  // Test 8: SimulationResult forwarded completely
  it('T8: SimulationResult forwarded with all required fields', async () => {
    mockSimulate.mockResolvedValue(SIM_RESULT)
    const req = makePostRequest({ candidate_id: 'cand-1', region_id: 'ntt' })
    const res = await simulatePOST(req)
    const body = await json(res)
    expect(body.pct_good_change).toBe(12.5)
    expect(body.villages_newly_covered).toBe(3)
    expect(body.new_coverage_score).toBe(74.2)
    expect(body.before_heatmap).toBeDefined()
    expect(body.after_heatmap).toBeDefined()
    expect(body.elapsed_ms).toBe(450)
  })

  // Test 9: UnavailableScenario forwarded — no fallback estimate
  it('T9: UnavailableScenario returns 404 without fallback data', async () => {
    mockSimulate.mockResolvedValue(UNAVAILABLE)
    const req = makePostRequest({ candidate_id: 'cand-1', region_id: 'ntt' })
    const res = await simulatePOST(req)
    // UnavailableScenario must be 404, not 200 (review finding #2)
    expect(res.status).toBe(404)
    const body = await json(res)
    expect(body.unavailable).toBe(true)
    expect(body.message).toBeTruthy()
    // No interpolated metrics in the response
    expect(body.pct_good_change).toBeUndefined()
    expect(body.new_coverage_score).toBeUndefined()
  })

  // Test 10: invalid JSON body handled
  it('T10: invalid JSON body returns 400', async () => {
    const req = new NextRequest('http://localhost/api/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{broken',
    })
    const res = await simulatePOST(req)
    expect(res.status).toBe(400)
    const body = await json(res)
    expect(body.error.code).toBe('INVALID_REQUEST')
  })

  // Extra: missing candidate_id
  it('T10-extra: missing candidate_id returns 400', async () => {
    const req = makePostRequest({ region_id: 'ntt' })
    const res = await simulatePOST(req)
    expect(res.status).toBe(400)
    expect(mockSimulate).not.toHaveBeenCalled()
  })
})


// ===========================================================================
// Drag-drop — Tests 11–15
// ===========================================================================

describe('POST /api/drag-drop', () => {
  // Test 11: valid request calls service with all parameters
  it('T11: valid request calls dragDropLookup with lat, lon, region_id, overlay_enabled', async () => {
    mockDragDrop.mockResolvedValue(DRAGDROP_RESULT)
    const req = makePostRequest({ lat: -9.2, lon: 120.2, region_id: 'ntt', overlay_enabled: false })
    const res = await dragDropPOST(req)
    expect(res.status).toBe(200)
    expect(mockDragDrop).toHaveBeenCalledWith(-9.2, 120.2, 'ntt', false)
  })

  // Test 12: invalid latitude → 400
  it('T12a: non-finite lat returns 400', async () => {
    const req = makePostRequest({ lat: 'bad', lon: 120.2, region_id: 'ntt' })
    const res = await dragDropPOST(req)
    expect(res.status).toBe(400)
    expect(mockDragDrop).not.toHaveBeenCalled()
  })

  it('T12b: lat out of range (-90..90) returns 400', async () => {
    const req = makePostRequest({ lat: 95, lon: 120.2, region_id: 'ntt' })
    const res = await dragDropPOST(req)
    expect(res.status).toBe(400)
    const body = await json(res)
    expect(body.error.code).toBe('INVALID_REQUEST')
  })

  it('T12c: lon out of range (-180..180) returns 400', async () => {
    const req = makePostRequest({ lat: -9.2, lon: 200, region_id: 'ntt' })
    const res = await dragDropPOST(req)
    expect(res.status).toBe(400)
  })

  // Test 13: DragDropResult manual_wins preserved
  it('T13: DragDropResult forwards manual_wins unchanged', async () => {
    const winResult = {
      ...DRAGDROP_RESULT,
      coverage_score: 82.0,
      vs_top_candidate: { ...DRAGDROP_RESULT.vs_top_candidate, manual_score: 82.0, manual_wins: true },
    }
    mockDragDrop.mockResolvedValue(winResult)
    const req = makePostRequest({ lat: -9.2, lon: 120.2, region_id: 'ntt', overlay_enabled: false })
    const res = await dragDropPOST(req)
    const body = await json(res)
    expect(body.vs_top_candidate.manual_wins).toBe(true)
    expect(body.coverage_score).toBe(82.0)
  })

  // Test 14: OutsideExtentError → 422, no Coverage Score
  it('T14: OutsideExtentError returns 422 and does not contain coverage_score', async () => {
    mockDragDrop.mockResolvedValue(OUTSIDE_EXTENT)
    const req = makePostRequest({ lat: -1.0, lon: 110.0, region_id: 'ntt', overlay_enabled: false })
    const res = await dragDropPOST(req)
    // OutsideExtentError must be 422, not 200 (review finding #3)
    expect(res.status).toBe(422)
    const body = await json(res)
    expect(body.outside_extent).toBe(true)
    expect(body.message).toBeTruthy()
    // Must not contain coverage_score — no interpolated or fallback result
    expect(body.coverage_score).toBeUndefined()
  })

  // Test 15: overlay_enabled forwarded as boolean
  it('T15a: overlay_enabled=true forwarded as boolean true', async () => {
    mockDragDrop.mockResolvedValue(DRAGDROP_RESULT)
    const req = makePostRequest({ lat: -9.2, lon: 120.2, region_id: 'ntt', overlay_enabled: true })
    await dragDropPOST(req)
    expect(mockDragDrop).toHaveBeenCalledWith(-9.2, 120.2, 'ntt', true)
  })

  it('T15b: overlay_enabled=false forwarded as boolean false', async () => {
    mockDragDrop.mockResolvedValue(DRAGDROP_RESULT)
    const req = makePostRequest({ lat: -9.2, lon: 120.2, region_id: 'ntt', overlay_enabled: false })
    await dragDropPOST(req)
    expect(mockDragDrop).toHaveBeenCalledWith(-9.2, 120.2, 'ntt', false)
  })

  it('T15c: non-boolean overlay_enabled returns 400', async () => {
    const req = makePostRequest({ lat: -9.2, lon: 120.2, region_id: 'ntt', overlay_enabled: 'yes' })
    const res = await dragDropPOST(req)
    expect(res.status).toBe(400)
  })

  // Extra: missing region_id → 400
  it('T15-extra: missing region_id returns 400', async () => {
    const req = makePostRequest({ lat: -9.2, lon: 120.2 })
    const res = await dragDropPOST(req)
    expect(res.status).toBe(400)
  })

  // Review finding #4a: service does NOT perform Euclidean snap or business calculation.
  // The mock is called with the raw coords; the service is expected to throw
  // SERVICE_UNAVAILABLE until the Python bridge is wired (Task 26+).
  it('T-snap: dragDropLookup is called with raw coords — no TS-side snap', async () => {
    mockDragDrop.mockResolvedValue(DRAGDROP_RESULT)
    const req = makePostRequest({ lat: -9.2, lon: 120.2, region_id: 'ntt', overlay_enabled: false })
    await dragDropPOST(req)
    // Verify the service was called with exactly the raw input coordinates —
    // no pre-processing, rounding, or snapping applied by the route.
    expect(mockDragDrop).toHaveBeenCalledWith(-9.2, 120.2, 'ntt', false)
    expect(mockDragDrop).toHaveBeenCalledTimes(1)
  })

  // Review finding #4b: backend bridge unavailable → structured 503 SERVICE_UNAVAILABLE.
  it('T-503: SERVICE_UNAVAILABLE from service returns structured 503', async () => {
    mockDragDrop.mockRejectedValue(serviceError('SERVICE_UNAVAILABLE',
      'Drag-and-drop snap requires the Python backend bridge, which is not yet integrated.'))
    const req = makePostRequest({ lat: -9.2, lon: 120.2, region_id: 'ntt', overlay_enabled: false })
    const res = await dragDropPOST(req)
    expect(res.status).toBe(503)
    const body = await json(res)
    expect(body.error.code).toBe('SERVICE_UNAVAILABLE')
    expect(body.error.message).toBeTruthy()
    // Must NOT be a mock success response — no coverage_score, no snapped_coordinate
    expect(body.coverage_score).toBeUndefined()
    expect(body.snapped_coordinate).toBeUndefined()
  })
})


// ===========================================================================
// Target Area — Tests 16–20
// ===========================================================================

describe('POST /api/target-area', () => {
  // Test 16: drawn polygon forwarded to service
  it('T16: valid drawn_polygon forwarded to resolveTargetArea', async () => {
    mockResolveTA.mockResolvedValue({ ...TARGET_AREA, selection_method: 'drawn_polygon', kecamatan_id: null })
    const req = makePostRequest({
      region_id: 'ntt',
      selection_method: 'drawn_polygon',
      payload: VALID_POLYGON,
    })
    const res = await targetAreaPOST(req)
    expect(res.status).toBe(200)
    expect(mockResolveTA).toHaveBeenCalledWith('ntt', 'drawn_polygon', VALID_POLYGON)
  })

  // Test 17: empty/invalid polygon rejected with 422
  it('T17a: Polygon with empty coordinates returns 422', async () => {
    const req = makePostRequest({
      region_id: 'ntt',
      selection_method: 'drawn_polygon',
      payload: { type: 'Polygon', coordinates: [] },
    })
    const res = await targetAreaPOST(req)
    expect(res.status).toBe(422)
    expect(mockResolveTA).not.toHaveBeenCalled()
  })

  it('T17b: wrong GeoJSON type returns 422', async () => {
    const req = makePostRequest({
      region_id: 'ntt',
      selection_method: 'drawn_polygon',
      payload: { type: 'Point', coordinates: [120, -9] },
    })
    const res = await targetAreaPOST(req)
    expect(res.status).toBe(422)
    const body = await json(res)
    expect(body.error.code).toBe('UNPROCESSABLE')
    expect(mockResolveTA).not.toHaveBeenCalled()
  })

  it('T17c: non-object polygon payload returns 400', async () => {
    const req = makePostRequest({
      region_id: 'ntt',
      selection_method: 'drawn_polygon',
      payload: 'not-a-polygon',
    })
    const res = await targetAreaPOST(req)
    expect(res.status).toBe(400)
    expect(mockResolveTA).not.toHaveBeenCalled()
  })

  // Test 18: kecamatan payload forwarded to service
  it('T18: valid kecamatan payload forwarded to resolveTargetArea', async () => {
    mockResolveTA.mockResolvedValue(TARGET_AREA)
    const req = makePostRequest({
      region_id: 'ntt',
      selection_method: 'kecamatan',
      payload: 'IDN.15.1_1',
    })
    const res = await targetAreaPOST(req)
    expect(res.status).toBe(200)
    expect(mockResolveTA).toHaveBeenCalledWith('ntt', 'kecamatan', 'IDN.15.1_1')
    const body = await json(res)
    expect(body.target_area_id).toBeTruthy()
  })

  // Test 19: invalid selection_method → 400
  it('T19: invalid selection_method returns 400', async () => {
    const req = makePostRequest({
      region_id: 'ntt',
      selection_method: 'manual_click',
      payload: VALID_POLYGON,
    })
    const res = await targetAreaPOST(req)
    expect(res.status).toBe(400)
    const body = await json(res)
    expect(body.error.code).toBe('INVALID_REQUEST')
    expect(mockResolveTA).not.toHaveBeenCalled()
  })

  // Test 20: service failure means target area not resolved
  it('T20: service NOT_FOUND returns 404 — target area not treated as resolved', async () => {
    mockResolveTA.mockRejectedValue(serviceError('NOT_FOUND', 'Kecamatan not found'))
    const req = makePostRequest({
      region_id: 'ntt',
      selection_method: 'kecamatan',
      payload: 'IDN.UNKNOWN',
    })
    const res = await targetAreaPOST(req)
    expect(res.status).toBe(404)
    const body = await json(res)
    expect(body.error.code).toBe('NOT_FOUND')
    // No target_area_id in error response
    expect(body.target_area_id).toBeUndefined()
  })

  // Extra: invalid region_id
  it('T20-extra: invalid region_id returns 400', async () => {
    const req = makePostRequest({
      region_id: 'papua',
      selection_method: 'kecamatan',
      payload: 'IDN.15.1_1',
    })
    const res = await targetAreaPOST(req)
    expect(res.status).toBe(400)
    expect(mockResolveTA).not.toHaveBeenCalled()
  })

  // Extra: empty kecamatan_id
  it('T20-extra-2: empty kecamatan payload returns 400', async () => {
    const req = makePostRequest({
      region_id: 'ntt',
      selection_method: 'kecamatan',
      payload: '',
    })
    const res = await targetAreaPOST(req)
    expect(res.status).toBe(400)
  })
})


// ===========================================================================
// Grid Cells — Tests 21–26
// ===========================================================================

describe('GET /api/grid-cells', () => {
  // Test 21: valid query uses region_id and resolution_m filter
  it('T21: valid query calls getGridCells with region and resolution', async () => {
    mockGetCells.mockResolvedValue(GRID_CELLS)
    const req = makeGetRequest({ region_id: 'ntt', resolution_m: '100' })
    const res = await gridCellsGET(req)
    expect(res.status).toBe(200)
    expect(mockGetCells).toHaveBeenCalledWith('ntt', 100, undefined)
  })

  // Test 22: target_area_id applied when provided
  it('T22: target_area_id is passed through to getGridCells when provided', async () => {
    mockGetCells.mockResolvedValue(GRID_CELLS)
    const req = makeGetRequest({ region_id: 'ntt', resolution_m: '100', target_area_id: 'ta-1' })
    const res = await gridCellsGET(req)
    expect(res.status).toBe(200)
    expect(mockGetCells).toHaveBeenCalledWith('ntt', 100, 'ta-1')
  })

  // Test 23: invalid region_id → 400
  it('T23: invalid region_id returns 400', async () => {
    const req = makeGetRequest({ region_id: 'unknown', resolution_m: '100' })
    const res = await gridCellsGET(req)
    expect(res.status).toBe(400)
    const body = await json(res)
    expect(body.error.code).toBe('INVALID_REGION')
    expect(mockGetCells).not.toHaveBeenCalled()
  })

  // Test 24: invalid resolution_m → 400
  it('T24a: non-integer resolution_m returns 400', async () => {
    const req = makeGetRequest({ region_id: 'ntt', resolution_m: '99.5' })
    const res = await gridCellsGET(req)
    expect(res.status).toBe(400)
    const body = await json(res)
    expect(body.error.code).toBe('INVALID_REQUEST')
    expect(mockGetCells).not.toHaveBeenCalled()
  })

  it('T24b: zero resolution_m returns 400', async () => {
    const req = makeGetRequest({ region_id: 'ntt', resolution_m: '0' })
    const res = await gridCellsGET(req)
    expect(res.status).toBe(400)
  })

  it('T24c: negative resolution_m returns 400', async () => {
    const req = makeGetRequest({ region_id: 'ntt', resolution_m: '-100' })
    const res = await gridCellsGET(req)
    expect(res.status).toBe(400)
  })

  it('T24d: missing resolution_m returns 400', async () => {
    const req = makeGetRequest({ region_id: 'ntt' })
    const res = await gridCellsGET(req)
    expect(res.status).toBe(400)
    expect(mockGetCells).not.toHaveBeenCalled()
  })

  // Test 25: empty data returns 200 with empty array
  it('T25: empty grid returns 200 with empty array, not an error', async () => {
    mockGetCells.mockResolvedValue([])
    const req = makeGetRequest({ region_id: 'ntb', resolution_m: '250' })
    const res = await gridCellsGET(req)
    expect(res.status).toBe(200)
    const body = await json(res)
    expect(Array.isArray(body)).toBe(true)
    expect(body).toHaveLength(0)
  })

  // Test 26: Supabase error handled without leaking internal details
  it('T26: Supabase error returns 500 without internal details', async () => {
    mockGetCells.mockRejectedValue(serviceError('SERVICE_ERROR', 'connection timeout — pg pool exhausted'))
    const req = makeGetRequest({ region_id: 'ntt', resolution_m: '100' })
    const res = await gridCellsGET(req)
    expect(res.status).toBe(500)
    const body = await json(res)
    expect(body.error).toBeTruthy()
    expect(body.error.code).toBe('SERVICE_ERROR')
    // Internal DB detail must not appear in the response body
    expect(JSON.stringify(body)).not.toContain('pg pool')
    expect(JSON.stringify(body)).not.toContain('connection timeout')
  })

  // Extra: response contains required heatmap fields
  it('T26-extra: response cells contain all required heatmap fields', async () => {
    mockGetCells.mockResolvedValue(GRID_CELLS)
    const req = makeGetRequest({ region_id: 'ntt', resolution_m: '100' })
    const res = await gridCellsGET(req)
    const body = await json(res)
    expect(body[0].cell_id).toBeTruthy()
    expect(body[0].coverage_score).toBeDefined()
    expect(body[0].confidence_tag).toBeDefined()
    expect(body[0].shap_top3).toBeDefined()
    expect(body[0].model_version).toBeTruthy()
    expect(body[0].scoring_run_id).toBeTruthy()
  })
})
