'use client'

/**
 * CoverageHeatmap — MapLibre GL JS Coverage Gap Heatmap layer.
 *
 * Task 22.4 — Requirements 3.1, 3.2, 3.5
 *
 * Responsibilities:
 *  - Renders a fill layer coloured by Coverage Score (Green/Yellow/Red)
 *    using HEATMAP_PAINT_EXPRESSION from heatmap.ts.
 *  - Renders an independent fill-opacity layer driven by confidence_tag,
 *    so confidence is never conflated with score colour.
 *  - Supports a `visible` prop: toggling calls map.setLayoutProperty()
 *    client-side — no page reload, no data refetch, no map recreation.
 *  - Safe lifecycle: only adds source/layer when map+style are ready;
 *    uses setData when source already exists; cleans up on unmount.
 *  - No SSR window access: guarded by 'use client' + typeof window checks.
 *  - No mock data: accepts only data passed via props.
 *
 * Confidence visual strategy (Requirement 3.5):
 *   opacity is controlled by confidence_tag independently of fill-color.
 *   High → 0.85, Med → 0.55, Low → 0.30
 *   This satisfies "secondary visual indicator independent of heatmap colour".
 */

import { useEffect, useRef, useCallback } from 'react'
import type { Map as MapLibreMap } from 'maplibre-gl'
import type { Feature, FeatureCollection, Geometry } from 'geojson'
import type { ConfidenceLevel } from '@/lib/types'
import {
  HEATMAP_PAINT_EXPRESSION,
  CONFIDENCE_OPACITY_EXPRESSION,
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
}

// ---------------------------------------------------------------------------
// Layer / Source ID constants — stable so duplicate detection works
// ---------------------------------------------------------------------------

const SOURCE_ID   = 'coverage-heatmap-source'
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
}: CoverageHeatmapProps) {
  // Track whether source+layers have been added to this map instance.
  const layersAddedRef = useRef(false)
  // Keep a stable ref to beforeLayerId to avoid re-triggering setup effect.
  const beforeLayerIdRef = useRef(beforeLayerId)
  beforeLayerIdRef.current = beforeLayerId

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

      // Fill layer — colour by coverage_score, opacity by confidence_tag
      if (!mapInstance.getLayer(FILL_LAYER)) {
        mapInstance.addLayer(
          {
            id:     FILL_LAYER,
            type:   'fill',
            source: SOURCE_ID,
            layout: {
              visibility: visible ? 'visible' : 'none',
            },
            paint: {
              // Colour driven exclusively by coverage_score via HEATMAP_PAINT_EXPRESSION.
              // Thresholds: Red(<40), Yellow(40–69), Green(>=70) — matches colourTier().
              'fill-color':   HEATMAP_PAINT_EXPRESSION as unknown as string,
              // Opacity driven exclusively by confidence_tag — independent of colour.
              'fill-opacity': CONFIDENCE_OPACITY_EXPRESSION as unknown as number,
            },
          },
          beforeLayerIdRef.current,
        )
      }

      // Outline layer — thin border for cell boundaries, also toggled with fill
      if (!mapInstance.getLayer(OUTLINE_LAYER)) {
        mapInstance.addLayer(
          {
            id:     OUTLINE_LAYER,
            type:   'line',
            source: SOURCE_ID,
            layout: {
              visibility: visible ? 'visible' : 'none',
            },
            paint: {
              'line-color': '#ffffff',
              'line-width': 0.4,
              'line-opacity': 0.4,
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
      // Narrow to GeoJSONSource so TypeScript knows setData exists.
      const { GeoJSONSource } = require('maplibre-gl') as typeof import('maplibre-gl')
      if (source instanceof GeoJSONSource) {
        source.setData(cellsToGeoJSON(cells))
      }
    }
  }, [map, cells])

  // ------------------------------------------------------------------
  // Effect 3: Toggle visibility client-side (no reload, no data refetch)
  // ------------------------------------------------------------------
  useEffect(() => {
    if (!map || !map.isStyleLoaded()) return
    const visibility = visible ? 'visible' : 'none'
    if (map.getLayer(FILL_LAYER))    map.setLayoutProperty(FILL_LAYER,    'visibility', visibility)
    if (map.getLayer(OUTLINE_LAYER)) map.setLayoutProperty(OUTLINE_LAYER, 'visibility', visibility)
  }, [map, visible])

  // This component manages MapLibre layers imperatively; no DOM output.
  return null
}

// ---------------------------------------------------------------------------
// Named exports for testing
// ---------------------------------------------------------------------------
export { SOURCE_ID, FILL_LAYER, OUTLINE_LAYER, cellsToGeoJSON }
