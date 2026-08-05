'use client'

/**
 * TargetAreaSelector — Task 23.5 (Requirements 10.7, 10.8)
 *
 * Supports two modes:
 *   drawn_polygon — Planner draws a polygon on the map via MapLibre Draw.
 *                   The boundary is highlighted before confirmation.
 *   kecamatan     — Planner picks a kecamatan from a dropdown.
 *                   Boundary from API response is highlighted before confirmation.
 *
 * TargetArea is only "resolved" after:
 *   1. API call succeeds.
 *   2. TargetArea is received.
 *   3. Boundary is rendered/highlighted.
 *
 * This component calls the existing /api/target-area route (Task 25.4 stub).
 * For test injection, an optional submitTargetArea prop overrides the fetch.
 *
 * Region switch resets all in-progress selection state (Task 23.6 requirement).
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import type { Map as MapLibreMap, GeoJSONSource } from 'maplibre-gl'
import type { Geometry, Feature, FeatureCollection } from 'geojson'
import type { AdminBoundary, TargetArea, RegionId, SelectionMethod } from '@/lib/types'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type DrawMode = 'off' | 'drawing' | 'drawn'

export interface TargetAreaSelectorProps {
  map: MapLibreMap | null
  regionId: RegionId
  /** Admin boundaries for the active region (kecamatan dropdown). */
  adminBoundaries: AdminBoundary[]
  /** Called when a TargetArea is fully resolved and boundary highlighted. */
  onResolved: (targetArea: TargetArea) => void
  /** Called when selection is reset (e.g. on region switch). */
  onReset?: () => void
  /**
   * Override for the API call — used in tests to avoid real fetch.
   * Default: POST /api/target-area
   */
  submitTargetArea?: (payload: {
    region_id: string
    selection_method: SelectionMethod
    payload: Geometry | string
  }) => Promise<TargetArea>
  /**
   * Override for MapLibre Draw instantiation — used in tests.
   */
  drawControlFactory?: (map: MapLibreMap) => DrawControl
}

/** Minimal MapLibre Draw interface for testability. */
export interface DrawControl {
  getAll: () => { features: Feature[] }
  deleteAll: () => void
  changeMode: (mode: string) => void
}

// ---------------------------------------------------------------------------
// MapLibre GL layer IDs for the boundary highlight
// ---------------------------------------------------------------------------

const BOUNDARY_SOURCE  = 'target-area-boundary-source'
const BOUNDARY_FILL    = 'target-area-boundary-fill'
const BOUNDARY_OUTLINE = 'target-area-boundary-outline'

// ---------------------------------------------------------------------------
// Default API call
// ---------------------------------------------------------------------------

export async function defaultSubmitTargetArea(payload: {
  region_id: string
  selection_method: SelectionMethod
  payload: Geometry | string
}): Promise<TargetArea> {
  const res = await fetch('/api/target-area', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.error ?? `Target area API error: ${res.status}`)
  }
  return res.json()
}

// ---------------------------------------------------------------------------
// Default MapLibre Draw factory
// ---------------------------------------------------------------------------

function defaultDrawControlFactory(map: MapLibreMap): DrawControl {
  // Dynamically import to avoid SSR issues and keep maplibre-gl-draw optional
  // in test environments. In production this runs client-side only.
  const MapboxDraw = require('@maplibre/maplibre-gl-draw').default
  const draw = new MapboxDraw({
    displayControlsDefault: false,
    controls: { polygon: true, trash: true },
  })
  map.addControl(draw)
  return draw as DrawControl
}

// ---------------------------------------------------------------------------
// Boundary highlight helpers
// ---------------------------------------------------------------------------

function boundaryToGeoJSON(boundary: Geometry): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: [{ type: 'Feature', geometry: boundary, properties: {} }],
  }
}

function addOrUpdateBoundary(map: MapLibreMap, boundary: Geometry): void {
  const geojson = boundaryToGeoJSON(boundary)
  const existing = map.getSource(BOUNDARY_SOURCE) as GeoJSONSource | undefined

  if (existing) {
    existing.setData(geojson)
  } else {
    map.addSource(BOUNDARY_SOURCE, { type: 'geojson', data: geojson })
  }

  if (!map.getLayer(BOUNDARY_FILL)) {
    map.addLayer({
      id: BOUNDARY_FILL,
      type: 'fill',
      source: BOUNDARY_SOURCE,
      paint: { 'fill-color': '#3b82f6', 'fill-opacity': 0.15 },
    })
  }
  if (!map.getLayer(BOUNDARY_OUTLINE)) {
    map.addLayer({
      id: BOUNDARY_OUTLINE,
      type: 'line',
      source: BOUNDARY_SOURCE,
      paint: { 'line-color': '#1d4ed8', 'line-width': 2, 'line-dasharray': [4, 2] },
    })
  }
}

function removeBoundary(map: MapLibreMap): void {
  try {
    if (map.getLayer(BOUNDARY_OUTLINE)) map.removeLayer(BOUNDARY_OUTLINE)
    if (map.getLayer(BOUNDARY_FILL))    map.removeLayer(BOUNDARY_FILL)
    if (map.getSource(BOUNDARY_SOURCE)) map.removeSource(BOUNDARY_SOURCE)
  } catch {
    // Map may have been destroyed
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TargetAreaSelector({
  map,
  regionId,
  adminBoundaries,
  onResolved,
  onReset,
  submitTargetArea = defaultSubmitTargetArea,
  drawControlFactory = defaultDrawControlFactory,
}: TargetAreaSelectorProps) {
  const [mode, setMode]                 = useState<SelectionMethod>('drawn_polygon')
  const [drawState, setDrawState]       = useState<DrawMode>('off')
  const [drawnGeometry, setDrawnGeometry] = useState<Geometry | null>(null)
  const [selectedKecamatan, setSelectedKecamatan] = useState<string>('')
  const [resolvedArea, setResolvedArea] = useState<TargetArea | null>(null)
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState<string | null>(null)
  const [boundaryHighlighted, setBoundaryHighlighted] = useState(false)

  const drawControlRef = useRef<DrawControl | null>(null)

  // ── Reset when region changes ────────────────────────────────────────────
  useEffect(() => {
    resetAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [regionId])

  function resetAll() {
    setDrawState('off')
    setDrawnGeometry(null)
    setSelectedKecamatan('')
    setResolvedArea(null)
    setError(null)
    setBoundaryHighlighted(false)

    // Remove highlight from map
    if (map && map.isStyleLoaded()) removeBoundary(map)

    // Clean up draw control
    if (drawControlRef.current) {
      try {
        drawControlRef.current.deleteAll()
        drawControlRef.current.changeMode('simple_select')
      } catch { /* ignore */ }
    }

    onReset?.()
  }

  // ── Cleanup on unmount ───────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      if (map && map.isStyleLoaded()) removeBoundary(map)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map])

  // ── Start drawing ────────────────────────────────────────────────────────
  const startDraw = useCallback(() => {
    if (!map) return

    if (!drawControlRef.current) {
      try {
        drawControlRef.current = drawControlFactory(map)
      } catch (err) {
        setError('Could not initialise draw tool: ' + String(err))
        return
      }
    }

    try {
      drawControlRef.current.changeMode('draw_polygon')
    } catch { /* ignore */ }

    setDrawState('drawing')
    setDrawnGeometry(null)
    setBoundaryHighlighted(false)
    setResolvedArea(null)

    // Listen for draw.create — MapLibre fires this on the map element
    const handleDrawCreate = (e: Event) => {
      const features = (e as CustomEvent<{ features: Feature[] }>).detail
        ?.features ?? drawControlRef.current?.getAll().features ?? []
      if (features.length > 0 && features[0].geometry) {
        const geom = features[0].geometry as Geometry
        setDrawnGeometry(geom)
        setDrawState('drawn')
        // Show highlighted boundary immediately (before confirm)
        if (map.isStyleLoaded()) {
          addOrUpdateBoundary(map, geom)
          setBoundaryHighlighted(true)
        }
      }
    }

    ;(map as unknown as EventTarget).addEventListener('draw.create', handleDrawCreate)
    ;(map as unknown as EventTarget).addEventListener('draw.update', handleDrawCreate)
  }, [map, drawControlFactory])

  // ── Submit target area ───────────────────────────────────────────────────
  const handleSubmit = useCallback(async () => {
    if (!boundaryHighlighted) return
    if (loading) return

    let apiPayload: { region_id: string; selection_method: SelectionMethod; payload: Geometry | string } | null = null

    if (mode === 'drawn_polygon') {
      if (!drawnGeometry) {
        setError('Please draw a polygon on the map first.')
        return
      }
      apiPayload = { region_id: regionId, selection_method: 'drawn_polygon', payload: drawnGeometry }
    } else {
      if (!selectedKecamatan) {
        setError('Please select a kecamatan.')
        return
      }
      apiPayload = { region_id: regionId, selection_method: 'kecamatan', payload: selectedKecamatan }
    }

    setLoading(true)
    setError(null)

    try {
      const targetArea = await submitTargetArea(apiPayload)
      setResolvedArea(targetArea)

      // Show/update boundary from API response
      if (map && map.isStyleLoaded() && targetArea.boundary_geojson) {
        addOrUpdateBoundary(map, targetArea.boundary_geojson as Geometry)
        setBoundaryHighlighted(true)
      }

      onResolved(targetArea)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to resolve target area.')
    } finally {
      setLoading(false)
    }
  }, [
    mode, drawnGeometry, selectedKecamatan, regionId,
    submitTargetArea, map, onResolved, loading, boundaryHighlighted,
  ])

  // ── Kecamatan selection ──────────────────────────────────────────────────
  const handleKecamatanChange = useCallback((kecamatanId: string) => {
    setSelectedKecamatan(kecamatanId)
    setResolvedArea(null)
    setBoundaryHighlighted(false)
    setError(null)

    // Preview boundary from local adminBoundaries data
    if (!kecamatanId || !map || !map.isStyleLoaded()) return
    const boundary = adminBoundaries.find((b) => b.kecamatan_id === kecamatanId)
    if (boundary?.boundary_geojson) {
      addOrUpdateBoundary(map, boundary.boundary_geojson as Geometry)
      setBoundaryHighlighted(true)
    }
  }, [map, adminBoundaries])

  // ── Render ───────────────────────────────────────────────────────────────

  const containerStyle: React.CSSProperties = {
    background: 'rgba(255,255,255,0.95)',
    borderRadius: 8,
    boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
    padding: '12px 14px',
    fontFamily: 'sans-serif',
    fontSize: '0.88rem',
    minWidth: 240,
  }

  const resolved = resolvedArea !== null && boundaryHighlighted

  return (
    <div data-testid="target-area-selector" style={containerStyle}>
      <p style={{ fontWeight: 700, color: '#111827', margin: '0 0 10px' }}>
        Target Area
      </p>

      {/* Mode tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
        {(['drawn_polygon', 'kecamatan'] as const).map((m) => (
          <button
            key={m}
            data-testid={`mode-tab-${m}`}
            onClick={() => { setMode(m); resetAll() }}
            style={{
              padding: '3px 10px',
              borderRadius: 4,
              border: '1px solid #d1d5db',
              background: mode === m ? '#3b82f6' : '#ffffff',
              color: mode === m ? '#ffffff' : '#374151',
              fontWeight: mode === m ? 600 : 400,
              cursor: 'pointer',
              fontSize: '0.82rem',
            }}
          >
            {m === 'drawn_polygon' ? 'Draw' : 'Kecamatan'}
          </button>
        ))}
      </div>

      {/* Draw mode */}
      {mode === 'drawn_polygon' && (
        <div data-testid="draw-mode">
          {drawState === 'off' && (
            <button
              data-testid="start-draw-btn"
              onClick={startDraw}
              style={{
                padding: '5px 12px',
                background: '#3b82f6',
                color: '#fff',
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
              }}
            >
              Draw Polygon
            </button>
          )}
          {drawState === 'drawing' && (
            <p style={{ color: '#6b7280', margin: 0 }} data-testid="drawing-hint">
              Click on the map to draw a polygon. Double-click to finish.
            </p>
          )}
          {drawState === 'drawn' && (
            <p style={{ color: '#16a34a', margin: 0 }} data-testid="drawn-hint">
              ✓ Polygon drawn. Boundary highlighted.
            </p>
          )}
        </div>
      )}

      {/* Kecamatan mode */}
      {mode === 'kecamatan' && (
        <div data-testid="kecamatan-mode">
          {adminBoundaries.length === 0 ? (
            <p style={{ color: '#dc2626', margin: 0 }} data-testid="no-boundaries-msg">
              No kecamatan data available for this region.
            </p>
          ) : (
            <select
              data-testid="kecamatan-select"
              value={selectedKecamatan}
              onChange={(e) => handleKecamatanChange(e.target.value)}
              style={{
                width: '100%',
                border: '1px solid #d1d5db',
                borderRadius: 4,
                padding: '4px 8px',
                fontSize: '0.88rem',
              }}
              aria-label="Select kecamatan"
            >
              <option value="">— Select kecamatan —</option>
              {adminBoundaries.map((b) => (
                <option key={b.kecamatan_id} value={b.kecamatan_id}>
                  {b.kecamatan_name}
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {/* Boundary highlighted indicator */}
      {boundaryHighlighted && !resolved && (
        <p
          style={{ color: '#1d4ed8', fontSize: '0.82rem', margin: '8px 0 0' }}
          data-testid="boundary-highlighted-msg"
        >
          Boundary highlighted — confirm to proceed.
        </p>
      )}

      {/* Resolved indicator */}
      {resolved && (
        <p
          style={{ color: '#16a34a', fontSize: '0.82rem', margin: '8px 0 0' }}
          data-testid="resolved-msg"
        >
          ✓ Target area resolved.
        </p>
      )}

      {/* Error */}
      {error && (
        <p
          style={{ color: '#dc2626', fontSize: '0.82rem', margin: '8px 0 0' }}
          data-testid="target-area-error"
          role="alert"
        >
          {error}
        </p>
      )}

      {/* Confirm / Submit button — only shown after boundary is highlighted */}
      {boundaryHighlighted && !resolved && (
        <button
          data-testid="confirm-target-area-btn"
          onClick={handleSubmit}
          disabled={loading}
          style={{
            marginTop: 10,
            width: '100%',
            padding: '6px 0',
            background: loading ? '#93c5fd' : '#1d4ed8',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: loading ? 'not-allowed' : 'pointer',
            fontWeight: 600,
          }}
        >
          {loading ? 'Resolving…' : 'Confirm Target Area'}
        </button>
      )}

      {/* Reset */}
      {(drawState !== 'off' || selectedKecamatan || resolved) && (
        <button
          data-testid="reset-target-area-btn"
          onClick={resetAll}
          style={{
            marginTop: 6,
            width: '100%',
            padding: '5px 0',
            background: 'none',
            color: '#6b7280',
            border: '1px solid #d1d5db',
            borderRadius: 4,
            cursor: 'pointer',
            fontSize: '0.82rem',
          }}
        >
          Reset
        </button>
      )}
    </div>
  )
}

// Named exports for testing
export { BOUNDARY_SOURCE, BOUNDARY_FILL, BOUNDARY_OUTLINE, addOrUpdateBoundary, removeBoundary, boundaryToGeoJSON }
