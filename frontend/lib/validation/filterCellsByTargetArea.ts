/**
 * filterCellsByTargetArea — Spatial filtering for heatmap cells (Task 3.2).
 *
 * The single production implementation shared by MapView and the filter tests,
 * extracted to avoid the two-spec duplication noted in the heatmap-kecamatan /
 * nextjs-filtering specs. Uses Turf point-in-polygon with GeoJSON [lon, lat]
 * coordinate order.
 *
 * @param cells      Grid cells with lat/lon centroids.
 * @param targetArea Selected target area with boundary_geojson, or null.
 * @param onError    Optional callback; cleared on success, set on invalid
 *                   geometry so the UI can show a boundary error banner.
 * @returns Filtered cells when a target area is active; the full cell list
 *          otherwise (preservation: no target area → no filtering).
 */

// @ts-ignore - Turf.js module resolution issue
import booleanPointInPolygon from '@turf/boolean-point-in-polygon'
// @ts-ignore - Turf.js module resolution issue
import { point, polygon, multiPolygon } from '@turf/helpers'
import type { GridCell, TargetArea } from '@/lib/types'

export function filterCellsByTargetArea(
  cells: GridCell[],
  targetArea: TargetArea | null,
  onError?: (error: string | null) => void
): GridCell[] {
  // Preservation: No target area selected → return all cells unchanged
  if (!targetArea || !targetArea.boundary_geojson) {
    // Clear any previous error when no target area is selected
    onError?.(null)
    return cells
  }

  try {
    // Extract boundary feature from target area GeoJSON. GADM boundaries are
    // MultiPolygon; plain polygons also supported. boundary_geojson is a geometry
    // object with a coordinates array in GeoJSON [longitude, latitude] order.
    const geometry = targetArea.boundary_geojson as { type?: string; coordinates: unknown }
    const isMultiPolygon = geometry.type === 'MultiPolygon'
    const boundaryFeature = isMultiPolygon
      ? multiPolygon(geometry.coordinates as number[][][][])
      : polygon(geometry.coordinates as number[][][])

    // Filter cells using point-in-polygon check
    // GeoJSON uses [longitude, latitude] order
    const filtered = cells.filter((cell) => {
      const cellPoint = point([cell.lon, cell.lat])
      return booleanPointInPolygon(cellPoint, boundaryFeature)
    })

    // Clear error on successful filtering
    onError?.(null)
    return filtered
  } catch (error) {
    console.error(
      '[MapView] Invalid boundary geometry for target area',
      targetArea.target_area_id,
      error
    )

    // Report error to UI
    onError?.('Unable to filter cells - invalid boundary data')

    // Fall back to showing all region cells (no filtering)
    return cells
  }
}