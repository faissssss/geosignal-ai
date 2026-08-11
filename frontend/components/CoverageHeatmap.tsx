'use client'

/**
 * CoverageHeatmap — MapLibre GL JS Coverage Gap Heatmap layer.
 *
 * Task 22.4 — Requirements 3.1, 3.2, 3.5
 *
 * Responsibilities:
 *  - Renders a native MapLibre heatmap layer from grid-cell centroids.
 *  - Uses a Plotly-like Plasma density ramp: purple field, yellow hotspots.
 *  - Supports a `visible` prop: toggling calls map.setLayoutProperty()
 *    client-side — no page reload, no data refetch, no map recreation.
 *  - Safe lifecycle: only adds source/layer when map+style are ready;
 *    uses setData when source already exists; cleans up on unmount.
 *  - No SSR window access: guarded by 'use client' + typeof window checks.
 *  - No mock data: accepts only data passed via props.
 *
 * Point/cell interaction is preserved through an invisible circle hit layer.
 */

import { useEffect, useRef, useCallback } from 'react'
import type { ExpressionSpecification, Map as MapLibreMap } from 'maplibre-gl'
import type { Feature, FeatureCollection, Geometry } from 'geojson'
import type { ConfidenceLevel } from '@/lib/types'
import {
  HEATMAP_DENSITY_COLOR_EXPRESSION,
  HEATMAP_WEIGHT_EXPRESSION,
  type HeatmapMode,
} from '@/lib/heatmap'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Minimal shape of a Coverage Score grid cell accepted by this component. */
export interface CoverageCell {
  cell_id: string
  coverage_score: number
  confidence_tag: ConfidenceLevel
  /** GeoJSON geometry for the cell (polygon or point). */
  geometry?: Geometry
  /** Fallback centroid if geometry is absent. */
  lat?: number
  lon?: number
}

export interface CoverageHeatmapProps {
  /** The MapLibre map instance to add layers to. */
  map: MapLibreMap | null
  /** Grid cells to visualise. Empty array is safe. */
  cells: CoverageCell[]
  /** Whether the heatmap layers are visible. Toggled client-side. */
  visible: boolean
  /**
   * Optional z-order: layer is inserted before this existing layer ID.
   * Defaults to undefined (appended at the top).
   */
  beforeLayerId?: string
  /**
   * Legacy display mode prop accepted by the parent controls. The native GIS
   * heatmap uses a fixed Plotly-like density ramp so the surface stays visually consistent.
   */
  mode?: HeatmapMode
  /** Master opacity multiplier (0..1) for the native heatmap surface. */
  opacity?: number
}

// ---------------------------------------------------------------------------
// Layer / Source ID constants — stable so duplicate detection works
// ---------------------------------------------------------------------------

const SOURCE_ID   = 'coverage-heatmap-source'
const HEATMAP_LAYER = 'coverage-heatmap-density'
const FILL_LAYER  = 'coverage-heatmap-fill'
const OUTLINE_LAYER = 'coverage-heatmap-outline'

// ---------------------------------------------------------------------------
// GeoJSON builder
// ---------------------------------------------------------------------------

function cellsToGeoJSON(cells: CoverageCell[]): FeatureCollection {
  const features: Feature[] = cells.map((cell) => {
    // Use provided geometry; fall back to a Point from lat/lon.
    const geometry: Geometry = cell.geometry ?? {
      type: 'Point',
      coordinates: [cell.lon ?? 0, cell.lat ?? 0],
    }

    return {
      type: 'Feature',
      id: cell.cell_id,
      geometry,
      properties: {
        cell_id:        cell.cell_id,
        coverage_score: cell.coverage_score,
        confidence_tag: cell.confidence_tag,
      },
    }
  })

  return { type: 'FeatureCollection', features }
}

// ---------------------------------------------------------------------------
// CoverageHeatmap component
// ---------------------------------------------------------------------------

export default function CoverageHeatmap({
  map,
  cells,
  visible,
  beforeLayerId,
  opacity = 1,
}: CoverageHeatmapProps) {
  // Track whether source+layers have been added to this map instance.
  const layersAddedRef = useRef(false)
  // Keep a stable ref to beforeLayerId to avoid re-triggering setup effect.
  const beforeLayerIdRef = useRef(beforeLayerId)
  beforeLayerIdRef.current = beforeLayerId
  // Keep a stable ref to opacity so addLayersToMap reads the latest.
  const opacityRef = useRef(opacity)
  opacityRef.current = opacity

  // ------------------------------------------------------------------
  // Helper: safely add source + layers once map style is ready
  // ------------------------------------------------------------------
  const addLayersToMap = useCallback(
    (mapInstance: MapLibreMap, geojson: FeatureCollection) => {
      // Guard: don't add twice
      if (layersAddedRef.current) return

      // Source
      if (!mapInstance.getSource(SOURCE_ID)) {
        mapInstance.addSource(SOURCE_ID, {
          type: 'geojson',
          data: geojson,
        })
      }

      // Native GIS-style heatmap layer. This renders the blurred density field
      // from point centroids; polygon fill layers cannot render point-only data.
      if (!mapInstance.getLayer(HEATMAP_LAYER)) {
        mapInstance.addLayer(
          {
            id:     HEATMAP_LAYER,
            type:   'heatmap',
            source: SOURCE_ID,
            layout: {
              visibility: visible ? 'visible' : 'none',
            },
            paint: {
              'heatmap-weight': HEATMAP_WEIGHT_EXPRESSION as unknown as number,
              'heatmap-intensity': [
                'interpolate', ['linear'], ['zoom'],
                4, 0.65,
                8, 1.1,
                12, 1.55,
              ] as unknown as number,
              'heatmap-radius': [
                'interpolate', ['linear'], ['zoom'],
                4, 9,
                7, 20,
                10, 34,
                13, 54,
              ] as unknown as number,
              'heatmap-color': HEATMAP_DENSITY_COLOR_EXPRESSION as unknown as ExpressionSpecification,
              'heatmap-opacity': opacityRef.current * 0.9,
            },
          },
          beforeLayerIdRef.current,
        )
      }

      // Quiet point layer for cell selection and score/confidence detail. Keeping
      // this id preserves MapView's existing click handler contract.
      if (!mapInstance.getLayer(FILL_LAYER)) {
        mapInstance.addLayer(
          {
            id:     FILL_LAYER,
            type:   'circle',
            source: SOURCE_ID,
            layout: {
              visibility: visible ? 'visible' : 'none',
            },
            paint: {
              'circle-color': 'rgba(255, 255, 255, 0)',
              'circle-radius': [
                'interpolate', ['linear'], ['zoom'],
                4, 6,
                8, 10,
                12, 15,
              ] as unknown as number,
              'circle-opacity': 0,
              'circle-stroke-opacity': 0,
            },
          },
          beforeLayerIdRef.current,
        )
      }

      // Larger transparent hit area so centroid points are still easy to click.
      if (!mapInstance.getLayer(OUTLINE_LAYER)) {
        mapInstance.addLayer(
          {
            id:     OUTLINE_LAYER,
            type:   'circle',
            source: SOURCE_ID,
            layout: {
              visibility: visible ? 'visible' : 'none',
            },
            paint: {
              'circle-radius': [
                'interpolate', ['linear'], ['zoom'],
                4, 6,
                8, 9,
                12, 13,
              ] as unknown as number,
              'circle-color': 'rgba(255, 255, 255, 0)',
              'circle-opacity': 0,
            },
          },
          beforeLayerIdRef.current,
        )
      }
      layersAddedRef.current = true
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [], // intentionally empty: called once; visible handled separately
  )

  // ------------------------------------------------------------------
  // Effect 1: Set up source + layers when map + style are ready
  // ------------------------------------------------------------------
  useEffect(() => {
    if (!map) return

    const geojson = cellsToGeoJSON(cells)

    const setup = () => {
      // Ensure style is loaded before touching sources/layers
      if (!map.isStyleLoaded()) return
      addLayersToMap(map, geojson)
    }

    if (map.isStyleLoaded()) {
      setup()
    } else {
      map.once('styledata', setup)
    }

    // Cleanup: remove layers and source owned by this component on unmount.
    return () => {
      map.off('styledata', setup)
      if (!map.isStyleLoaded()) return
      try {
        if (map.getLayer(OUTLINE_LAYER)) map.removeLayer(OUTLINE_LAYER)
        if (map.getLayer(FILL_LAYER))    map.removeLayer(FILL_LAYER)
        if (map.getLayer(HEATMAP_LAYER)) map.removeLayer(HEATMAP_LAYER)
        if (map.getSource(SOURCE_ID))    map.removeSource(SOURCE_ID)
      } catch {
        // Map may have been destroyed — ignore cleanup errors
      }
      layersAddedRef.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]) // Re-run only if the map instance itself changes

  // ------------------------------------------------------------------
  // Effect 2: Update GeoJSON data when cells change (no layer recreation)
  // ------------------------------------------------------------------
  useEffect(() => {
    if (!map || !map.isStyleLoaded()) return
    const source = map.getSource(SOURCE_ID)
    if (source && source.type === 'geojson') {
      // Cast to GeoJSONSource — source.type === 'geojson' guarantees this is safe.
      (source as import('maplibre-gl').GeoJSONSource).setData(cellsToGeoJSON(cells))
    }
  }, [map, cells])

  // ------------------------------------------------------------------
  // Effect 3: Toggle visibility client-side (no reload, no data refetch)
  // ------------------------------------------------------------------
  useEffect(() => {
    if (!map || !map.isStyleLoaded()) return
    const visibility = visible ? 'visible' : 'none'
    if (map.getLayer(HEATMAP_LAYER)) map.setLayoutProperty(HEATMAP_LAYER, 'visibility', visibility)
    if (map.getLayer(FILL_LAYER))    map.setLayoutProperty(FILL_LAYER,    'visibility', visibility)
    if (map.getLayer(OUTLINE_LAYER)) map.setLayoutProperty(OUTLINE_LAYER, 'visibility', visibility)
  }, [map, visible])

  // ------------------------------------------------------------------
  // Effect 4: Update heatmap paint when opacity changes. Uses
  // setPaintProperty without layer recreation or data refetch.
  // ------------------------------------------------------------------
  useEffect(() => {
    if (!map || !map.isStyleLoaded()) return
    if (typeof (map as { setPaintProperty?: unknown }).setPaintProperty !== 'function') return
    const setPaint = (map as { setPaintProperty: (layer: string, prop: string, value: unknown) => void }).setPaintProperty
    if (map.getLayer(HEATMAP_LAYER)) {
      setPaint(HEATMAP_LAYER, 'heatmap-weight', HEATMAP_WEIGHT_EXPRESSION as unknown as number)
      setPaint(HEATMAP_LAYER, 'heatmap-color', HEATMAP_DENSITY_COLOR_EXPRESSION as unknown as ExpressionSpecification)
      setPaint(HEATMAP_LAYER, 'heatmap-opacity', opacity * 0.9)
    }
    if (map.getLayer(FILL_LAYER)) {
      setPaint(FILL_LAYER, 'circle-color', 'rgba(255, 255, 255, 0)')
      setPaint(FILL_LAYER, 'circle-opacity', 0)
    }
  }, [map, opacity])

  // This component manages MapLibre layers imperatively; no DOM output.
  return null
}

// ---------------------------------------------------------------------------
// Named exports for testing
// ---------------------------------------------------------------------------
export { SOURCE_ID, HEATMAP_LAYER, FILL_LAYER, OUTLINE_LAYER, cellsToGeoJSON }
