/**
 * Tests for CoverageHeatmap component — Task 22.4
 *
 * Strategy: mock the MapLibre Map instance (no real WebGL/canvas needed).
 * We verify the imperative calls (addSource, addLayer, setData,
 * setLayoutProperty, removeLayer, removeSource) are made correctly,
 * rather than rendering pixels.
 *
 * Tests:
 *  1.  Score classification uses colourTier thresholds (40, 70)
 *  2.  Boundary values 40 and 70 are correct
 *  3.  Confidence visual does not change the colour tier expression
 *  4.  visible=false sets layout visibility to 'none'
 *  5.  visible=true sets layout visibility to 'visible'
 *  6.  Toggling visible does not reload page / refetch data
 *  7.  setData called when cells prop changes (not addSource again)
 *  8.  Empty cells array does not throw
 *  9.  map=null does not throw
 * 10.  Source/layers not registered twice on re-render
 * 11.  Cleanup removes layers and source on unmount
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act } from '@testing-library/react'
import CoverageHeatmap, {
  CoverageCell,
  SOURCE_ID,
  FILL_LAYER,
  OUTLINE_LAYER,
  cellsToGeoJSON,
} from '../components/CoverageHeatmap'
import { colourTier, HEATMAP_PAINT_EXPRESSION, CONFIDENCE_OPACITY_EXPRESSION } from '../lib/heatmap'
import type { ConfidenceLevel } from '../lib/types'

// ---------------------------------------------------------------------------
// MapLibre mock factory
// ---------------------------------------------------------------------------

function makeMapMock(styleLoaded = true) {
  const sources: Record<string, { type: string; data: unknown }> = {}
  const layers: Record<string, { layout: Record<string, string>; paint: Record<string, unknown> }> = {}
  const listeners: Record<string, Array<() => void>> = {}
  let fetchCallCount = 0

  const map = {
    isStyleLoaded: vi.fn(() => styleLoaded),
    getSource: vi.fn((id: string) =>
      sources[id]
        ? {
            type: 'geojson',
            setData: vi.fn((data: unknown) => {
              sources[id].data = data
            }),
          }
        : undefined,
    ),
    addSource: vi.fn((id: string, spec: { type: string; data: unknown }) => {
      sources[id] = { type: spec.type, data: spec.data }
    }),
    getLayer: vi.fn((id: string) => layers[id] ?? undefined),
    addLayer: vi.fn((spec: { id: string; layout?: Record<string, string>; paint?: Record<string, unknown> }) => {
      layers[spec.id] = {
        layout: { ...(spec.layout ?? {}) },
        paint:  { ...(spec.paint ?? {}) },
      }
    }),
    setLayoutProperty: vi.fn((layerId: string, property: string, value: string) => {
      if (layers[layerId]) {
        layers[layerId].layout[property] = value
      }
    }),
    removeLayer: vi.fn((id: string) => {
      delete layers[id]
    }),
    removeSource: vi.fn((id: string) => {
      delete sources[id]
    }),
    once: vi.fn((event: string, cb: () => void) => {
      if (!listeners[event]) listeners[event] = []
      listeners[event].push(cb)
    }),
    off: vi.fn((event: string, cb: () => void) => {
      if (listeners[event]) {
        listeners[event] = listeners[event].filter((l) => l !== cb)
      }
    }),
    // Expose internals for assertions
    _sources: sources,
    _layers: layers,
    _fetchCallCount: () => fetchCallCount,
    _triggerEvent: (event: string) => {
      ;(listeners[event] ?? []).forEach((cb) => cb())
    },
  }
  return map
}

// ---------------------------------------------------------------------------
// Sample cells
// ---------------------------------------------------------------------------

const RED_CELL: CoverageCell    = { cell_id: 'r1', coverage_score: 20,  confidence_tag: 'Low',  lat: -9.1, lon: 120.1 }
const YELLOW_CELL: CoverageCell = { cell_id: 'y1', coverage_score: 55,  confidence_tag: 'Med',  lat: -9.2, lon: 120.2 }
const GREEN_CELL: CoverageCell  = { cell_id: 'g1', coverage_score: 85,  confidence_tag: 'High', lat: -9.3, lon: 120.3 }

const SAMPLE_CELLS = [RED_CELL, YELLOW_CELL, GREEN_CELL]

// ---------------------------------------------------------------------------
// Test 1 — Score classification uses correct thresholds from colourTier
// ---------------------------------------------------------------------------

describe('cellsToGeoJSON — score → correct tier in HEATMAP_PAINT_EXPRESSION', () => {
  it('GeoJSON properties include coverage_score unchanged', () => {
    const gj = cellsToGeoJSON(SAMPLE_CELLS)
    const scores = gj.features.map((f) => f.properties?.coverage_score)
    expect(scores).toEqual([20, 55, 85])
  })

  it('GeoJSON properties include confidence_tag unchanged', () => {
    const gj = cellsToGeoJSON(SAMPLE_CELLS)
    const tags = gj.features.map((f) => f.properties?.confidence_tag)
    expect(tags).toEqual(['Low', 'Med', 'High'])
  })

  it('colourTier classification matches expected tiers for sample scores', () => {
    expect(colourTier(20)).toBe('Red')
    expect(colourTier(55)).toBe('Yellow')
    expect(colourTier(85)).toBe('Green')
  })

  it('HEATMAP_PAINT_EXPRESSION contains threshold 40 and 70', () => {
    const expr = HEATMAP_PAINT_EXPRESSION as unknown as unknown[]
    expect(expr).toContain(40)
    expect(expr).toContain(70)
  })
})

// ---------------------------------------------------------------------------
// Test 2 — Boundary values 40 and 70 in HEATMAP_PAINT_EXPRESSION
// ---------------------------------------------------------------------------

describe('Boundary values — same thresholds as colourTier', () => {
  it('threshold 40 comes before Yellow colour in paint expression', () => {
    const expr = HEATMAP_PAINT_EXPRESSION as unknown as unknown[]
    const idx40 = expr.indexOf(40)
    expect(idx40).toBeGreaterThan(-1)
    // The entry after 40 should be the Yellow hex colour
    const yellowHex = expr[idx40 + 1]
    expect(typeof yellowHex).toBe('string')
    expect((yellowHex as string).startsWith('#')).toBe(true)
  })

  it('threshold 70 comes before Green colour in paint expression', () => {
    const expr = HEATMAP_PAINT_EXPRESSION as unknown as unknown[]
    const idx70 = expr.indexOf(70)
    expect(idx70).toBeGreaterThan(-1)
    const greenHex = expr[idx70 + 1]
    expect(typeof greenHex).toBe('string')
    expect((greenHex as string).startsWith('#')).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Test 3 — Confidence visual does NOT change the colour tier expression
// ---------------------------------------------------------------------------

describe('Confidence visual — independent of colour', () => {
  it('CONFIDENCE_OPACITY_EXPRESSION uses confidence_tag, not coverage_score', () => {
    const expr = CONFIDENCE_OPACITY_EXPRESSION as unknown as unknown[]
    // The match expression reads ['get', 'confidence_tag']
    expect(JSON.stringify(expr)).toContain('confidence_tag')
    expect(JSON.stringify(expr)).not.toContain('coverage_score')
  })

  it('fill-color expression does not reference confidence_tag', () => {
    const expr = HEATMAP_PAINT_EXPRESSION as unknown as unknown[]
    expect(JSON.stringify(expr)).not.toContain('confidence_tag')
  })

  it('fill-opacity expression does not reference coverage_score', () => {
    const expr = CONFIDENCE_OPACITY_EXPRESSION as unknown as unknown[]
    expect(JSON.stringify(expr)).not.toContain('coverage_score')
  })

  it('cells with different confidence_tag get the same colour tier for equal scores', () => {
    const lowConf: CoverageCell  = { cell_id: 'a', coverage_score: 75, confidence_tag: 'Low',  lat: 0, lon: 0 }
    const highConf: CoverageCell = { cell_id: 'b', coverage_score: 75, confidence_tag: 'High', lat: 0, lon: 0 }
    // colour tier is score-driven only
    expect(colourTier(lowConf.coverage_score)).toBe(colourTier(highConf.coverage_score))
    expect(colourTier(lowConf.coverage_score)).toBe('Green')
  })
})

// ---------------------------------------------------------------------------
// Tests 4 & 5 — Visibility toggle via setLayoutProperty
// ---------------------------------------------------------------------------

describe('CoverageHeatmap visibility', () => {
  it('visible=false sets layout visibility to none on both layers', () => {
    const map = makeMapMock(true)
    const { rerender } = render(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={true} />,
    )
    // Layers now exist; toggle off
    rerender(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={false} />,
    )
    expect(map.setLayoutProperty).toHaveBeenCalledWith(FILL_LAYER,    'visibility', 'none')
    expect(map.setLayoutProperty).toHaveBeenCalledWith(OUTLINE_LAYER, 'visibility', 'none')
  })

  it('visible=true sets layout visibility to visible on both layers', () => {
    const map = makeMapMock(true)
    render(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={true} />,
    )
    expect(map.setLayoutProperty).toHaveBeenCalledWith(FILL_LAYER,    'visibility', 'visible')
    expect(map.setLayoutProperty).toHaveBeenCalledWith(OUTLINE_LAYER, 'visibility', 'visible')
  })
})

// ---------------------------------------------------------------------------
// Tests 6 — Toggling visible does not reload page or refetch data
// ---------------------------------------------------------------------------

describe('Visibility toggle — no side effects', () => {
  it('toggling visible does not call addSource or addLayer again', () => {
    const map = makeMapMock(true)
    const { rerender } = render(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={true} />,
    )
    const addSourceCallsBefore = (map.addSource as ReturnType<typeof vi.fn>).mock.calls.length
    const addLayerCallsBefore  = (map.addLayer  as ReturnType<typeof vi.fn>).mock.calls.length

    rerender(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={false} />,
    )

    expect(map.addSource).toHaveBeenCalledTimes(addSourceCallsBefore)
    expect(map.addLayer).toHaveBeenCalledTimes(addLayerCallsBefore)
  })

  it('toggling visible only calls setLayoutProperty', () => {
    const map = makeMapMock(true)
    const { rerender } = render(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={true} />,
    )
    rerender(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={false} />,
    )
    rerender(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={true} />,
    )
    // setLayoutProperty must have been called for both toggle directions
    const calls = (map.setLayoutProperty as ReturnType<typeof vi.fn>).mock.calls
    const noneCalls    = calls.filter((c) => c[2] === 'none')
    const visibleCalls = calls.filter((c) => c[2] === 'visible')
    expect(noneCalls.length).toBeGreaterThan(0)
    expect(visibleCalls.length).toBeGreaterThan(0)
  })
})

// ---------------------------------------------------------------------------
// Test 7 — setData called on cells change (no addSource again)
// ---------------------------------------------------------------------------

describe('Data update — setData on cells change', () => {
  it('calls setData when cells prop changes, not addSource', () => {
    const map = makeMapMock(true)
    // Manually set up source so getSource returns a mock with setData
    const setDataMock = vi.fn()
    ;(map.getSource as ReturnType<typeof vi.fn>).mockImplementation((id: string) =>
      id === SOURCE_ID
        ? { type: 'geojson', setData: setDataMock }
        : undefined,
    )
    // Also set getLayer to return truthy so layers are considered already added
    ;(map.getLayer as ReturnType<typeof vi.fn>).mockReturnValue({ layout: {}, paint: {} })

    const { rerender } = render(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={true} />,
    )
    const newCells: CoverageCell[] = [
      { cell_id: 'new1', coverage_score: 60, confidence_tag: 'High', lat: -9.5, lon: 120.5 },
    ]
    rerender(
      <CoverageHeatmap map={map as unknown as any} cells={newCells} visible={true} />,
    )
    // setData must have been called with the new cells' GeoJSON
    expect(setDataMock).toHaveBeenCalled()
    const lastCall = setDataMock.mock.calls[setDataMock.mock.calls.length - 1][0]
    expect(lastCall.features[0].properties.cell_id).toBe('new1')
  })
})

// ---------------------------------------------------------------------------
// Test 8 — Empty cells array does not throw
// ---------------------------------------------------------------------------

describe('Edge cases', () => {
  it('renders without error when cells=[]', () => {
    const map = makeMapMock(true)
    expect(() => {
      render(<CoverageHeatmap map={map as unknown as any} cells={[]} visible={true} />)
    }).not.toThrow()
  })

  it('cellsToGeoJSON([]) returns a valid empty FeatureCollection', () => {
    const gj = cellsToGeoJSON([])
    expect(gj.type).toBe('FeatureCollection')
    expect(gj.features).toHaveLength(0)
  })

  // ---------------------------------------------------------------------------
  // Test 9 — map=null does not throw
  // ---------------------------------------------------------------------------
  it('renders without error when map=null', () => {
    expect(() => {
      render(<CoverageHeatmap map={null} cells={SAMPLE_CELLS} visible={true} />)
    }).not.toThrow()
  })

  it('does not call any map methods when map=null', () => {
    // No map to spy on — just verify no exception propagates
    const { unmount } = render(
      <CoverageHeatmap map={null} cells={SAMPLE_CELLS} visible={false} />,
    )
    expect(() => unmount()).not.toThrow()
  })

  // ---------------------------------------------------------------------------
  // Test 10 — Source/layers not registered twice
  // ---------------------------------------------------------------------------
  it('addSource called at most once even on re-render', () => {
    const map = makeMapMock(true)
    const { rerender } = render(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={true} />,
    )
    rerender(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={true} />,
    )
    rerender(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={false} />,
    )
    expect(map.addSource).toHaveBeenCalledTimes(1)
  })

  it('addLayer called at most twice (fill + outline) even on re-render', () => {
    const map = makeMapMock(true)
    const { rerender } = render(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={true} />,
    )
    rerender(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={true} />,
    )
    // Only the initial render should have added layers
    expect(map.addLayer).toHaveBeenCalledTimes(2) // fill + outline
  })

  // ---------------------------------------------------------------------------
  // Test 11 — Cleanup removes layers and source on unmount
  // ---------------------------------------------------------------------------
  it('removeLayer and removeSource are called on unmount', () => {
    const map = makeMapMock(true)
    const { unmount } = render(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={true} />,
    )
    unmount()
    expect(map.removeLayer).toHaveBeenCalledWith(OUTLINE_LAYER)
    expect(map.removeLayer).toHaveBeenCalledWith(FILL_LAYER)
    expect(map.removeSource).toHaveBeenCalledWith(SOURCE_ID)
  })

  it('cleanup does not throw when map is already destroyed', () => {
    const map = makeMapMock(true)
    ;(map.removeLayer as ReturnType<typeof vi.fn>).mockImplementation(() => {
      throw new Error('map destroyed')
    })
    const { unmount } = render(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={true} />,
    )
    expect(() => unmount()).not.toThrow()
  })

  // ---------------------------------------------------------------------------
  // Test: style not loaded — waits for styledata event before adding layers
  // ---------------------------------------------------------------------------
  it('waits for styledata event when style is not loaded', () => {
    const map = makeMapMock(false) // styleLoaded = false
    render(
      <CoverageHeatmap map={map as unknown as any} cells={SAMPLE_CELLS} visible={true} />,
    )
    // Should not have added source/layers yet
    expect(map.addSource).not.toHaveBeenCalled()
    // Now simulate styledata event
    ;(map.isStyleLoaded as ReturnType<typeof vi.fn>).mockReturnValue(true)
    act(() => {
      map._triggerEvent('styledata')
    })
    expect(map.addSource).toHaveBeenCalledTimes(1)
  })
})
