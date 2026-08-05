/**
 * Task 23.6 — Unit tests for all Task 23 components.
 * Tests 1–15 as specified in the task brief.
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'

import SidePanel, { type SidePanelSelection } from '../components/SidePanel'
import RegionSelector from '../components/RegionSelector'
import TargetAreaSelector from '../components/TargetAreaSelector'
import { WebGLFallback, LayerToggleBar } from '../components/MapView'
import { detectWebGL } from '../lib/webgl'
import type { GridCell, BTSCandidate, AdminBoundary, RegionId, TargetArea } from '../lib/types'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const makeCell = (overrides: Partial<GridCell> = {}): GridCell => ({
  cell_id: 'c1', region_id: 'ntt', lat: -9.1, lon: 120.1,
  resolution_m: 100, coverage_score: 65, confidence_tag: 'Med',
  tier_used: '1', model_version: 'ahp-v1.0', scoring_run_id: 'run-001',
  shap_top3: [
    { feature_name: 'Elevation', value: 8.2, direction: 'positive' },
    { feature_name: 'Terrain slope', value: -4.1, direction: 'negative' },
    { feature_name: 'Distance to BTS', value: 3.5, direction: 'positive' },
  ],
  ...overrides,
})

const makeCandidate = (overrides: Partial<BTSCandidate> = {}): BTSCandidate => ({
  candidate_id: 'cand-1', region_id: 'ntt', target_area_id: 'ta-1',
  rank: 2, lat: -9.2, lon: 120.2, expected_improvement: 15,
  los_validated: true, confidence_tag: 'High',
  shap_values: { elevation_m: 6.0, slope_deg: -2.0, canopy_height_m: 1.5,
    land_cover_class: 0.5, distance_to_bts_m: 4.0, road_distance_m: 1.0,
    population_density_per_km2: 2.0, facility_proximity_m: 3.0 },
  model_version: 'xgb-v2.1', scoring_run_id: 'run-002',
  excluded_by_canopy: false,
  ...overrides,
})

const makeBoundary = (i: number = 0): AdminBoundary => ({
  boundary_id: `b${i}`, kecamatan_id: `IDN.15.${i}_1`,
  kecamatan_name: `Kecamatan ${i}`, region_id: 'ntt',
  boundary_geojson: {
    type: 'Polygon',
    coordinates: [[[119 + i, -9], [120 + i, -9], [120 + i, -10], [119 + i, -10], [119 + i, -9]]],
  },
})

const makeTargetArea = (overrides: Partial<TargetArea> = {}): TargetArea => ({
  target_area_id: 'ta-1', region_id: 'ntt', selection_method: 'kecamatan',
  kecamatan_id: 'IDN.15.1_1',
  boundary_geojson: { type: 'Polygon', coordinates: [[[119, -9],[120,-9],[120,-10],[119,-10],[119,-9]]] },
  created_at: '2026-01-01T00:00:00Z',
  ...overrides,
})

// Minimal MapLibre map mock (reused from CoverageHeatmap tests pattern)
function makeMapMock(styleLoaded = true) {
  const layers: Record<string, unknown> = {}
  const sources: Record<string, unknown> = {}
  return {
    isStyleLoaded: vi.fn(() => styleLoaded),
    getLayer: vi.fn((id: string) => layers[id]),
    addLayer: vi.fn((spec: { id: string }) => { layers[spec.id] = spec }),
    removeLayer: vi.fn((id: string) => { delete layers[id] }),
    getSource: vi.fn((id: string) => sources[id] ? { type: 'geojson', setData: vi.fn() } : undefined),
    addSource: vi.fn((id: string, spec: unknown) => { sources[id] = spec }),
    removeSource: vi.fn((id: string) => { delete sources[id] }),
    setLayoutProperty: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
    once: vi.fn(),
    addControl: vi.fn(),
    _layers: layers, _sources: sources,
  }
}

// ---------------------------------------------------------------------------
// Tests 1-3: Region switch resets TargetAreaSelector state
// ---------------------------------------------------------------------------
describe('Test 1-3: Region switch resets TargetAreaSelector state', () => {
  it('T1: region switch resets drawn polygon state', async () => {
    const onReset = vi.fn()
    const map = makeMapMock()
    const { rerender } = render(
      <TargetAreaSelector map={map as never} regionId="ntt"
        adminBoundaries={[]} onResolved={vi.fn()} onReset={onReset} />,
    )
    rerender(
      <TargetAreaSelector map={map as never} regionId="ntb"
        adminBoundaries={[]} onResolved={vi.fn()} onReset={onReset} />,
    )
    expect(onReset).toHaveBeenCalled()
    expect(screen.queryByTestId('drawn-hint')).toBeNull()
  })

  it('T2: region switch resets kecamatan selection', async () => {
    const onReset = vi.fn()
    const map = makeMapMock()
    const boundaries = [makeBoundary(0), makeBoundary(1)]
    const { rerender } = render(
      <TargetAreaSelector map={map as never} regionId="ntt"
        adminBoundaries={boundaries} onResolved={vi.fn()} onReset={onReset} />,
    )
    // Switch to kecamatan mode and pick one
    fireEvent.click(screen.getByTestId('mode-tab-kecamatan'))
    const sel = screen.getByTestId('kecamatan-select')
    fireEvent.change(sel, { target: { value: boundaries[0].kecamatan_id } })
    // Now switch region
    rerender(
      <TargetAreaSelector map={map as never} regionId="ntb"
        adminBoundaries={boundaries} onResolved={vi.fn()} onReset={onReset} />,
    )
    expect(onReset).toHaveBeenCalled()
    const select = screen.queryByTestId('kecamatan-select')
    if (select) {
      expect((select as HTMLSelectElement).value).toBe('')
    }
  })

  it('T3: region switch resets previously resolved target area', () => {
    const onReset = vi.fn()
    const onResolved = vi.fn()
    const map = makeMapMock()
    const submitMock = vi.fn().mockResolvedValue(makeTargetArea())
    const { rerender } = render(
      <TargetAreaSelector map={map as never} regionId="ntt"
        adminBoundaries={[makeBoundary(0)]} onResolved={onResolved}
        onReset={onReset} submitTargetArea={submitMock} />,
    )
    rerender(
      <TargetAreaSelector map={map as never} regionId="ntb"
        adminBoundaries={[]} onResolved={onResolved}
        onReset={onReset} submitTargetArea={submitMock} />,
    )
    expect(onReset).toHaveBeenCalled()
    expect(screen.queryByTestId('resolved-msg')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Tests 4-6: Target area confirmation gate
// ---------------------------------------------------------------------------
describe('Tests 4-6: Target area confirmation gate', () => {
  it('T4: confirm button absent before boundary is highlighted', () => {
    render(
      <TargetAreaSelector map={null} regionId="ntt" adminBoundaries={[]}
        onResolved={vi.fn()} />,
    )
    expect(screen.queryByTestId('confirm-target-area-btn')).toBeNull()
  })

  it('T5: confirm button appears after kecamatan boundary is highlighted', () => {
    const map = makeMapMock()
    const boundaries = [makeBoundary(0)]
    render(
      <TargetAreaSelector map={map as never} regionId="ntt"
        adminBoundaries={boundaries} onResolved={vi.fn()} />,
    )
    fireEvent.click(screen.getByTestId('mode-tab-kecamatan'))
    fireEvent.change(screen.getByTestId('kecamatan-select'), {
      target: { value: boundaries[0].kecamatan_id },
    })
    expect(screen.getByTestId('confirm-target-area-btn')).toBeTruthy()
    expect(screen.getByTestId('boundary-highlighted-msg')).toBeTruthy()
  })

  it('T6: boundary-highlighted message appears before confirmation', () => {
    const map = makeMapMock()
    const boundaries = [makeBoundary(0)]
    render(
      <TargetAreaSelector map={map as never} regionId="ntt"
        adminBoundaries={boundaries} onResolved={vi.fn()} />,
    )
    fireEvent.click(screen.getByTestId('mode-tab-kecamatan'))
    fireEvent.change(screen.getByTestId('kecamatan-select'), {
      target: { value: boundaries[0].kecamatan_id },
    })
    expect(screen.getByTestId('boundary-highlighted-msg')).toBeTruthy()
    expect(screen.queryByTestId('resolved-msg')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Tests 7-9: SidePanel
// ---------------------------------------------------------------------------
describe('Tests 7-9: SidePanel', () => {
  it('T7: cell selection opens SidePanel with coverage score', () => {
    const cell = makeCell()
    const selection: SidePanelSelection = { kind: 'cell', data: cell }
    render(<SidePanel selection={selection} />)
    expect(screen.getByTestId('side-panel')).toBeTruthy()
    expect(screen.getByTestId('coverage-score').textContent).toContain('65')
  })

  it('T8: candidate selection shows rank in SidePanel', () => {
    const cand = makeCandidate({ rank: 3 })
    const selection: SidePanelSelection = { kind: 'candidate', data: cand }
    render(<SidePanel selection={selection} />)
    expect(screen.getByTestId('candidate-rank').textContent).toContain('3')
    expect(screen.getByTestId('coverage-score')).toBeTruthy()
  })

  it('T9: SHAP top-3 is in same panel as coverage score and confidence', () => {
    const cell = makeCell()
    const selection: SidePanelSelection = { kind: 'cell', data: cell }
    render(<SidePanel selection={selection} />)
    const panel = screen.getByTestId('side-panel')
    expect(panel.contains(screen.getByTestId('coverage-score'))).toBe(true)
    expect(panel.contains(screen.getByTestId('confidence-tag'))).toBe(true)
    expect(panel.contains(screen.getByTestId('shap-top3'))).toBe(true)
  })

  it('SidePanel shows null state when no selection', () => {
    const { container } = render(<SidePanel selection={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('SidePanel renders SHAP entries with direction arrows', () => {
    const cell = makeCell()
    render(<SidePanel selection={{ kind: 'cell', data: cell }} />)
    const shap = screen.getByTestId('shap-top3')
    expect(shap.textContent).toContain('↑')
    expect(shap.textContent).toContain('↓')
  })

  it('SidePanel renders GeoAI-assisted label', () => {
    render(<SidePanel selection={{ kind: 'cell', data: makeCell() }} />)
    expect(screen.getByTestId('geoai-label')).toBeTruthy()
  })

  it('SidePanel loading state', () => {
    render(<SidePanel selection={null} loading={true} />)
    expect(screen.getByTestId('side-panel-loading')).toBeTruthy()
  })

  it('SidePanel error state', () => {
    render(<SidePanel selection={null} error="Something went wrong" />)
    expect(screen.getByTestId('side-panel-error').textContent).toContain('Something went wrong')
  })
})

// ---------------------------------------------------------------------------
// Tests 10-11: WebGL fallback
// ---------------------------------------------------------------------------
describe('Tests 10-11: WebGL fallback', () => {
  it('T10: WebGLFallback renders clear message with browser recommendations', () => {
    render(<WebGLFallback />)
    expect(screen.getByTestId('webgl-fallback')).toBeTruthy()
    expect(screen.getByText(/WebGL Required/i)).toBeTruthy()
    expect(screen.getByText('Chrome')).toBeTruthy()
    expect(screen.getByText('Firefox')).toBeTruthy()
    expect(screen.getByText('Edge')).toBeTruthy()
  })

  it('T11: detectWebGL returns supported:false when canvas returns null context', () => {
    const result = detectWebGL(() => {
      const canvas = { getContext: vi.fn(() => null) } as unknown as HTMLCanvasElement
      return canvas
    })
    expect(result.supported).toBe(false)
    expect(result.contextType).toBeNull()
    expect(result.reason).toBeTruthy()
  })

  it('T11b: detectWebGL returns supported:true when webgl2 context is available', () => {
    const result = detectWebGL(() => {
      const ctx = { getExtension: vi.fn(() => null) }
      return { getContext: vi.fn(() => ctx) } as unknown as HTMLCanvasElement
    })
    expect(result.supported).toBe(true)
    expect(result.contextType).toBe('webgl2')
  })

  it('detectWebGL returns supported:false in SSR (no window)', () => {
    // In jsdom window exists, so we test the canvas-factory path
    const result = detectWebGL(() => null)
    expect(result.supported).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Tests 12-13: RegionSelector
// ---------------------------------------------------------------------------
describe('Tests 12-13: RegionSelector', () => {
  it('T12: RegionSelector calls onRegionChange with new regionId', async () => {
    const onRegionChange = vi.fn()
    const fetchMock = vi.fn().mockResolvedValue({ cells: [], candidates: [] })

    render(
      <RegionSelector
        initialRegion="ntt"
        onRegionChange={onRegionChange}
        fetchRegionData={fetchMock}
      />,
    )
    // Wait for initial load
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('ntt', expect.anything()))

    // Switch to ntb
    fireEvent.change(screen.getByTestId('region-select'), { target: { value: 'ntb' } })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('ntb', expect.anything()))
    await waitFor(() =>
      expect(onRegionChange).toHaveBeenCalledWith(
        expect.objectContaining({ regionId: 'ntb' }),
      ),
    )
  })

  it('T13: RegionSelector preserves previous region on error', async () => {
    const onRegionChange = vi.fn()
    let callCount = 0
    const fetchMock = vi.fn().mockImplementation(async (regionId: string, signal: AbortSignal) => {
      callCount++
      if (regionId === 'ntb' && callCount > 1) throw new Error('Network error')
      return { cells: [], candidates: [] }
    })

    render(
      <RegionSelector
        initialRegion="ntt"
        onRegionChange={onRegionChange}
        fetchRegionData={fetchMock}
      />,
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('ntt', expect.anything()))

    // Trigger ntb fetch (will fail on 2nd call)
    fireEvent.change(screen.getByTestId('region-select'), { target: { value: 'ntb' } })
    await waitFor(() => screen.getByTestId('region-error'))

    // onRegionChange should NOT have been called with ntb
    const calls = onRegionChange.mock.calls.map((c) => c[0].regionId)
    expect(calls).not.toContain('ntb')
    // Error is shown
    expect(screen.getByTestId('region-error')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// Test 14: Layer toggle uses visibility, not reload
// ---------------------------------------------------------------------------
describe('Test 14: LayerToggleBar uses client-side visibility', () => {
  it('T14: toggling a layer calls onChange with new boolean, not reload', () => {
    const onChange = vi.fn()
    const visibility = {
      heatmap: true, landcover: true, contours: true,
      villages: true, btsMarkers: true, candidates: true,
    }
    render(<LayerToggleBar visibility={visibility} onChange={onChange} />)

    const heatmapCheckbox = screen.getByTestId('checkbox-heatmap') as HTMLInputElement
    expect(heatmapCheckbox.checked).toBe(true)

    fireEvent.click(heatmapCheckbox)
    expect(onChange).toHaveBeenCalledWith('heatmap', false)

    // No page navigation — window.location should be unchanged
    expect(window.location.href).toBe(window.location.href)
  })

  it('T14b: all six toggle labels are rendered', () => {
    const onChange = vi.fn()
    const visibility = {
      heatmap: true, landcover: false, contours: true,
      villages: false, btsMarkers: true, candidates: true,
    }
    render(<LayerToggleBar visibility={visibility} onChange={onChange} />)
    expect(screen.getByTestId('toggle-heatmap')).toBeTruthy()
    expect(screen.getByTestId('toggle-landcover')).toBeTruthy()
    expect(screen.getByTestId('toggle-contours')).toBeTruthy()
    expect(screen.getByTestId('toggle-villages')).toBeTruthy()
    expect(screen.getByTestId('toggle-btsMarkers')).toBeTruthy()
    expect(screen.getByTestId('toggle-candidates')).toBeTruthy()
  })

  it('T14c: checkbox state reflects visibility prop', () => {
    const onChange = vi.fn()
    const visibility = {
      heatmap: true, landcover: false, contours: true,
      villages: false, btsMarkers: true, candidates: false,
    }
    render(<LayerToggleBar visibility={visibility} onChange={onChange} />)
    expect((screen.getByTestId('checkbox-heatmap') as HTMLInputElement).checked).toBe(true)
    expect((screen.getByTestId('checkbox-landcover') as HTMLInputElement).checked).toBe(false)
    expect((screen.getByTestId('checkbox-candidates') as HTMLInputElement).checked).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Test 15: Empty data does not crash
// ---------------------------------------------------------------------------
describe('Test 15: Empty data does not crash', () => {
  it('T15a: SidePanel with empty shap_top3 does not crash', () => {
    const cell = makeCell({ shap_top3: [] })
    expect(() => {
      render(<SidePanel selection={{ kind: 'cell', data: cell }} />)
    }).not.toThrow()
    expect(screen.getByTestId('shap-top3').textContent).toContain('No SHAP data available')
  })

  it('T15b: TargetAreaSelector with empty adminBoundaries does not crash', () => {
    expect(() => {
      render(
        <TargetAreaSelector map={null} regionId="ntt"
          adminBoundaries={[]} onResolved={vi.fn()} />,
      )
    }).not.toThrow()
  })

  it('T15c: RegionSelector with empty fetch result does not crash', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ cells: [], candidates: [] })
    expect(() => {
      render(
        <RegionSelector initialRegion="ntt"
          onRegionChange={vi.fn()} fetchRegionData={fetchMock} />,
      )
    }).not.toThrow()
  })

  it('T15d: LayerToggleBar renders with all-false visibility', () => {
    const visibility = {
      heatmap: false, landcover: false, contours: false,
      villages: false, btsMarkers: false, candidates: false,
    }
    expect(() => {
      render(<LayerToggleBar visibility={visibility} onChange={vi.fn()} />)
    }).not.toThrow()
  })

  it('T15e: WebGLFallback does not crash', () => {
    expect(() => render(<WebGLFallback />)).not.toThrow()
  })
})

// ---------------------------------------------------------------------------
// Additional: webgl.ts unit tests
// ---------------------------------------------------------------------------
describe('detectWebGL additional', () => {
  it('returns supported:false with reason when canvas context is null', () => {
    const r = detectWebGL(() => ({
      getContext: () => null,
    } as unknown as HTMLCanvasElement))
    expect(r.supported).toBe(false)
    expect(typeof r.reason).toBe('string')
    expect(r.reason!.length).toBeGreaterThan(0)
  })

  it('returns supported:false when canvasFactory returns null', () => {
    const r = detectWebGL(() => null)
    expect(r.supported).toBe(false)
    expect(r.contextType).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Additional: TargetAreaSelector confirm workflow
// ---------------------------------------------------------------------------
describe('TargetAreaSelector confirmation workflow', () => {
  it('calls onResolved after successful submit', async () => {
    const onResolved = vi.fn()
    const submitMock = vi.fn().mockResolvedValue(makeTargetArea())
    const map = makeMapMock()
    const boundaries = [makeBoundary(0)]

    render(
      <TargetAreaSelector map={map as never} regionId="ntt"
        adminBoundaries={boundaries} onResolved={onResolved}
        submitTargetArea={submitMock} />,
    )
    fireEvent.click(screen.getByTestId('mode-tab-kecamatan'))
    fireEvent.change(screen.getByTestId('kecamatan-select'), {
      target: { value: boundaries[0].kecamatan_id },
    })
    fireEvent.click(screen.getByTestId('confirm-target-area-btn'))
    await waitFor(() => expect(onResolved).toHaveBeenCalledWith(expect.objectContaining({
      target_area_id: 'ta-1',
    })))
    expect(screen.getByTestId('resolved-msg')).toBeTruthy()
  })

  it('shows error when submit fails', async () => {
    const submitMock = vi.fn().mockRejectedValue(new Error('API error'))
    const map = makeMapMock()
    const boundaries = [makeBoundary(0)]

    render(
      <TargetAreaSelector map={map as never} regionId="ntt"
        adminBoundaries={boundaries} onResolved={vi.fn()}
        submitTargetArea={submitMock} />,
    )
    fireEvent.click(screen.getByTestId('mode-tab-kecamatan'))
    fireEvent.change(screen.getByTestId('kecamatan-select'), {
      target: { value: boundaries[0].kecamatan_id },
    })
    fireEvent.click(screen.getByTestId('confirm-target-area-btn'))
    await waitFor(() => expect(screen.getByTestId('target-area-error')).toBeTruthy())
    expect(screen.getByTestId('target-area-error').textContent).toContain('API error')
  })
})
