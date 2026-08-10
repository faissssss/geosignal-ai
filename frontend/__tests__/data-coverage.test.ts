import { afterEach, describe, expect, it, vi } from 'vitest'
import { validateRegionDataCoverage } from '@/lib/validation/data-coverage'

const boundary = {
  boundary_id: 'a', kecamatan_id: 'a', kecamatan_name: 'Alpha', region_id: 'ntt',
  boundary_geojson: { type: 'Polygon', coordinates: [[[120, -9], [121, -9], [121, -8], [120, -8], [120, -9]]] },
}
const cell = {
  cell_id: 'cell', region_id: 'ntt', lat: -8.5, lon: 120.5, resolution_m: 100,
  coverage_score: 30, confidence_tag: 'Low', tier_used: '1', shap_top3: [], model_version: 'demo', scoring_run_id: 'run',
}

afterEach(() => { vi.unstubAllGlobals() })

describe('validateRegionDataCoverage', () => {
  it('reports complete coverage when every boundary contains a cell', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [boundary] })
      .mockResolvedValueOnce({ ok: true, json: async () => [cell] }))
    await expect(validateRegionDataCoverage('ntt')).resolves.toEqual({
      hasData: true, totalKecamatan: 1, coveredKecamatan: 1, missingKecamatan: [],
    })
  })

  it('identifies boundaries with no in-boundary cell', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [boundary] })
      .mockResolvedValueOnce({ ok: true, json: async () => [] }))
    await expect(validateRegionDataCoverage('ntt')).resolves.toEqual({
      hasData: false, totalKecamatan: 1, coveredKecamatan: 0, missingKecamatan: ['Alpha'],
    })
  })
})
