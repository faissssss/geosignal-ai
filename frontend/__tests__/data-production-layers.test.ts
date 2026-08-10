/**
 * Data Production layer route tests (Phase 5 — supporting map layers)
 *
 * Strategy mirrors Task25.test.ts: the service boundary is mocked, routes are
 * called directly, and the response JSON + status are inspected. Tests cover:
 *  - valid region returns the service payload (including empty arrays)
 *  - missing / invalid region returns 400 with INVALID_REGION
 *  - service errors are mapped to 500 without leaking internals
 *  - kecamatan_id scoping is forwarded for contours and villages
 *  - provenance fields (data_source/status) are preserved
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

vi.mock('@/lib/server/geosignal-service', () => ({
  getLandCoverTileSets: vi.fn(),
  getContourFeatures:   vi.fn(),
  getVillageFeatures:   vi.fn(),
  getBTSLocations:      vi.fn(),
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
import { GET as landCoverGET } from '@/app/api/land-cover/route'
import { GET as contoursGET } from '@/app/api/contours/route'
import { GET as villagesGET } from '@/app/api/villages/route'
import { GET as btsGET } from '@/app/api/bts-locations/route'

const mockLandCover = svc.getLandCoverTileSets as ReturnType<typeof vi.fn>
const mockContours  = svc.getContourFeatures as ReturnType<typeof vi.fn>
const mockVillages  = svc.getVillageFeatures as ReturnType<typeof vi.fn>
const mockBTS       = svc.getBTSLocations as ReturnType<typeof vi.fn>

function makeGetRequest(params: Record<string, string>, url = 'http://localhost/api/layer'): NextRequest {
  const u = new URL(url)
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v)
  return new NextRequest(u.toString(), { method: 'GET' })
}

async function json(res: Response) {
  return res.json()
}

function serviceError(code: string, msg: string) {
  const E = (svc as unknown as { ServiceError: new (c: string, m: string) => Error }).ServiceError
  return new E(code, msg)
}

const LAND_COVER = [
  {
    set_id: 'set-1', region_id: 'ntt', layer_id: 'worldcover',
    tiles_url: 'https://example.com/tiles/{z}/{x}/{y}', attribution: 'ESA',
    status: 'real', data_source: 'real', created_at: '2026-01-01T00:00:00Z',
  },
]

const CONTOUR = [
  {
    feature_id: 'f-1', region_id: 'ntt', kecamatan_id: 'IDN.15.1_1', elevation_m: 500,
    geom_geojson: { type: 'LineString', coordinates: [[119, -9.2], [119.1, -9.2]] },
    status: 'derived', data_source: 'derived',
  },
]

const VILLAGE = [
  {
    feature_id: 'v-1', region_id: 'ntt', kecamatan_id: 'IDN.15.1_1', village_name: 'Foo',
    attribution: 'OSM', geom_geojson: { type: 'Polygon', coordinates: [[[119, -9], [120, -9], [120, -10], [119, -10], [119, -9]]] },
    status: 'real', data_source: 'real',
  },
]

const BTS = [
  {
    tower_id: 't-1', region_id: 'ntt', lat: -9.12, lon: 120.2,
    mcc: 510, mnc: 10, lac: 1, cell: 42,
    status: 'real', data_source: 'real',
  },
]

beforeEach(() => {
  vi.clearAllMocks()
  mockLandCover.mockResolvedValue([])
  mockContours.mockResolvedValue([])
  mockVillages.mockResolvedValue([])
  mockBTS.mockResolvedValue([])
})

// ===========================================================================
// /api/land-cover
// ===========================================================================

describe('GET /api/land-cover', () => {
  it('L1: valid region returns service payload with provenance fields', async () => {
    mockLandCover.mockResolvedValue(LAND_COVER)
    const res = await landCoverGET(makeGetRequest({ region_id: 'ntt' }))
    expect(res.status).toBe(200)
    const body = await json(res)
    expect(body).toHaveLength(1)
    expect(body[0].layer_id).toBe('worldcover')
    expect(body[0].status).toBe('real')
    expect(body[0].data_source).toBe('real')
    expect(mockLandCover).toHaveBeenCalledWith('ntt')
  })

  it('L2: empty result returns [] — not an error', async () => {
    mockLandCover.mockResolvedValue([])
    const res = await landCoverGET(makeGetRequest({ region_id: 'ntb' }))
    expect(res.status).toBe(200)
    expect(await json(res)).toEqual([])
  })

  it('L3: missing region → 400 INVALID_REGION', async () => {
    const res = await landCoverGET(makeGetRequest({}))
    expect(res.status).toBe(400)
    const body = await json(res)
    expect(body.error.code).toBe('INVALID_REGION')
  })

  it('L4: service failure → 500 without leaking internals', async () => {
    mockLandCover.mockRejectedValue(serviceError('SERVICE_ERROR', 'secret DB detail'))
    const res = await landCoverGET(makeGetRequest({ region_id: 'ntt' }))
    expect(res.status).toBe(500)
    const body = await json(res)
    expect(body.error.code).toBe('SERVICE_ERROR')
    expect(body.error.message).not.toContain('secret DB detail')
  })
})

// =========================================================================
describe('GET /api/contours', () => {
  it('C1: valid region + kecamatan scoping forwarded', async () => {
    mockContours.mockResolvedValue(CONTOUR)
    const res = await contoursGET(makeGetRequest({ region_id: 'ntt', kecamatan_id: 'IDN.15.1_1' }))
    expect(res.status).toBe(200)
    const body = await json(res)
    expect(body).toHaveLength(1)
    expect(body[0].elevation_m).toBe(500)
    expect(mockContours).toHaveBeenCalledWith('ntt', 'IDN.15.1_1')
  })

  it('C2: empty region returns []', async () => {
    mockContours.mockResolvedValue([])
    const res = await contoursGET(makeGetRequest({ region_id: 'ntt' }))
    expect(res.status).toBe(200)
    expect(await json(res)).toEqual([])
  })

  it('C3: invalid region → 400', async () => {
    const res = await contoursGET(makeGetRequest({ region_id: 'papua' }))
    expect(res.status).toBe(400)
    expect((await json(res)).error.code).toBe('INVALID_REGION')
  })

  it('C4: service error → 500', async () => {
    mockContours.mockRejectedValue(serviceError('SERVICE_ERROR', 'boom'))
    const res = await contoursGET(makeGetRequest({ region_id: 'ntt' }))
    expect(res.status).toBe(500)
  })
})

// =========================================================================
describe('GET /api/villages', () => {
  it('V1: village features returned with attribution', async () => {
    mockVillages.mockResolvedValue(VILLAGE)
    const res = await villagesGET(makeGetRequest({ region_id: 'ntt', kecamatan_id: 'IDN.15.1_1' }))
    expect(res.status).toBe(200)
    const body = await json(res)
    expect(body).toHaveLength(1)
    expect(body[0].village_name).toBe('Foo')
    expect(mockVillages).toHaveBeenCalledWith('ntt', 'IDN.15.1_1')
  })

  it('V2: empty region returns []', async () => {
    mockVillages.mockResolvedValue([])
    const res = await villagesGET(makeGetRequest({ region_id: 'central_kalimantan' }))
    expect(res.status).toBe(200)
    expect(await json(res)).toEqual([])
  })

  it('V3: missing region → 400', async () => {
    const res = await villagesGET(makeGetRequest({}))
    expect(res.status).toBe(400)
  })

  it('V4: service error → 500', async () => {
    mockVillages.mockRejectedValue(serviceError('SERVICE_ERROR', 'boom'))
    const res = await villagesGET(makeGetRequest({ region_id: 'ntt' }))
    expect(res.status).toBe(500)
  })
})

// =========================================================================
describe('GET /api/bts-locations', () => {
  it('B1: tower points returned with cell identifiers', async () => {
    mockBTS.mockResolvedValue(BTS)
    const res = await btsGET(makeGetRequest({ region_id: 'ntt' }))
    expect(res.status).toBe(200)
    const body = await json(res)
    expect(body).toHaveLength(1)
    expect(body[0].mcc).toBe(510)
    expect(body[0].cell).toBe(42)
    expect(mockBTS).toHaveBeenCalledWith('ntt')
  })

  it('B2: empty region returns []', async () => {
    mockBTS.mockResolvedValue([])
    const res = await btsGET(makeGetRequest({ region_id: 'central_kalimantan' }))
    expect(res.status).toBe(200)
    expect(await json(res)).toEqual([])
  })

  it('B3: invalid region → 400', async () => {
    const res = await btsGET(makeGetRequest({ region_id: 'jawa_barat' }))
    expect(res.status).toBe(400)
  })

  it('B4: service error → 500', async () => {
    mockBTS.mockRejectedValue(serviceError('SERVICE_ERROR', 'boom'))
    const res = await btsGET(makeGetRequest({ region_id: 'ntt' }))
    expect(res.status).toBe(500)
  })
})