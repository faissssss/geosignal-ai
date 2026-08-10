/**
 * Unit tests for filterCellsByTargetArea function
 * Task 3.2: Implement filterCellsByTargetArea function in MapView
 */

import { describe, it, expect } from 'vitest'
import type { GridCell, TargetArea } from '@/lib/types'
import { filterCellsByTargetArea } from '@/lib/validation/filterCellsByTargetArea'

describe('filterCellsByTargetArea', () => {
  const mockCells: GridCell[] = [
    {
      cell_id: 'cell-1',
      region_id: 'ntt',
      lat: -8.5,
      lon: 120.0,
      resolution_m: 1000,
      coverage_score: 45,
      confidence_tag: 'High',
      tier_used: '1',
      shap_top3: [],
      model_version: '1.0',
      scoring_run_id: 'run-1',
    },
    {
      cell_id: 'cell-2',
      region_id: 'ntt',
      lat: -8.6,
      lon: 120.1,
      resolution_m: 1000,
      coverage_score: 55,
      confidence_tag: 'Med',
      tier_used: '1',
      shap_top3: [],
      model_version: '1.0',
      scoring_run_id: 'run-1',
    },
    {
      cell_id: 'cell-3',
      region_id: 'ntt',
      lat: -9.0,
      lon: 121.0,
      resolution_m: 1000,
      coverage_score: 65,
      confidence_tag: 'Low',
      tier_used: '1',
      shap_top3: [],
      model_version: '1.0',
      scoring_run_id: 'run-1',
    },
  ]

  it('returns all cells when targetArea is null', () => {
    const result = filterCellsByTargetArea(mockCells, null)
    expect(result).toEqual(mockCells)
    expect(result.length).toBe(3)
  })

  it('returns all cells when targetArea has no boundary_geojson', () => {
    const targetArea: TargetArea = {
      target_area_id: 'ta-1',
      region_id: 'ntt',
      selection_method: 'kecamatan',
      kecamatan_id: 'kec-1',
      boundary_geojson: null as any,
      created_at: '2024-01-01T00:00:00Z',
    }
    const result = filterCellsByTargetArea(mockCells, targetArea)
    expect(result).toEqual(mockCells)
  })

  it('filters cells based on point-in-polygon check', () => {
    // Create a polygon that only includes cell-1 and cell-2
    const targetArea: TargetArea = {
      target_area_id: 'ta-2',
      region_id: 'ntt',
      selection_method: 'kecamatan',
      kecamatan_id: 'kec-2',
      boundary_geojson: {
        type: 'Polygon',
        coordinates: [
          [
            [119.8, -8.7], // bottom-left
            [120.3, -8.7], // bottom-right
            [120.3, -8.3], // top-right
            [119.8, -8.3], // top-left
            [119.8, -8.7], // close polygon
          ],
        ],
      },
      created_at: '2024-01-01T00:00:00Z',
    }

    const result = filterCellsByTargetArea(mockCells, targetArea)
    
    // Should only include cell-1 (-8.5, 120.0) and cell-2 (-8.6, 120.1)
    // cell-3 (-9.0, 121.0) is outside the polygon
    expect(result.length).toBe(2)
    expect(result.map(c => c.cell_id)).toEqual(['cell-1', 'cell-2'])
  })

  it('returns empty array when no cells fall within boundary', () => {
    // Create a polygon far from all cells
    const targetArea: TargetArea = {
      target_area_id: 'ta-3',
      region_id: 'ntt',
      selection_method: 'kecamatan',
      kecamatan_id: 'kec-3',
      boundary_geojson: {
        type: 'Polygon',
        coordinates: [
          [
            [125.0, -5.0],
            [126.0, -5.0],
            [126.0, -4.0],
            [125.0, -4.0],
            [125.0, -5.0],
          ],
        ],
      },
      created_at: '2024-01-01T00:00:00Z',
    }

    const result = filterCellsByTargetArea(mockCells, targetArea)
    expect(result).toEqual([])
    expect(result.length).toBe(0)
  })

  it('handles invalid boundary geometry gracefully', () => {
    const targetArea: TargetArea = {
      target_area_id: 'ta-4',
      region_id: 'ntt',
      selection_method: 'kecamatan',
      kecamatan_id: 'kec-4',
      boundary_geojson: {
        type: 'InvalidType',
        coordinates: 'invalid',
      } as any,
      created_at: '2024-01-01T00:00:00Z',
    }

    // Should fall back to returning all cells on error
    const result = filterCellsByTargetArea(mockCells, targetArea)
    expect(result).toEqual(mockCells)
  })

  it('calls error callback when boundary geometry is invalid', () => {
    const targetArea: TargetArea = {
      target_area_id: 'ta-invalid',
      region_id: 'ntt',
      selection_method: 'kecamatan',
      kecamatan_id: 'kec-invalid',
      boundary_geojson: {
        type: 'InvalidType',
        coordinates: 'not-an-array',
      } as any,
      created_at: '2024-01-01T00:00:00Z',
    }

    let capturedError: string | null = null
    const onError = (error: string | null) => {
      capturedError = error
    }

    const result = filterCellsByTargetArea(mockCells, targetArea, onError)
    
    // Should return all cells as fallback
    expect(result).toEqual(mockCells)
    
    // Should have called error callback with error message
    expect(capturedError).toBe('Unable to filter cells - invalid boundary data')
  })

  it('clears error when targetArea is null', () => {
    let capturedError: string | null = 'previous error'
    const onError = (error: string | null) => {
      capturedError = error
    }

    const result = filterCellsByTargetArea(mockCells, null, onError)
    
    // Should return all cells
    expect(result).toEqual(mockCells)
    
    // Should clear error
    expect(capturedError).toBeNull()
  })

  it('clears error on successful filtering', () => {
    const targetArea: TargetArea = {
      target_area_id: 'ta-valid',
      region_id: 'ntt',
      selection_method: 'kecamatan',
      kecamatan_id: 'kec-valid',
      boundary_geojson: {
        type: 'Polygon',
        coordinates: [
          [
            [119.8, -8.7],
            [120.3, -8.7],
            [120.3, -8.3],
            [119.8, -8.3],
            [119.8, -8.7],
          ],
        ],
      },
      created_at: '2024-01-01T00:00:00Z',
    }

    let capturedError: string | null = 'previous error'
    const onError = (error: string | null) => {
      capturedError = error
    }

    const result = filterCellsByTargetArea(mockCells, targetArea, onError)
    
    // Should filter cells
    expect(result.length).toBe(2)
    
    // Should clear error
    expect(capturedError).toBeNull()
  })

  it('handles empty cells array', () => {
    const targetArea: TargetArea = {
      target_area_id: 'ta-5',
      region_id: 'ntt',
      selection_method: 'kecamatan',
      kecamatan_id: 'kec-5',
      boundary_geojson: {
        type: 'Polygon',
        coordinates: [
          [
            [119.8, -8.7],
            [120.3, -8.7],
            [120.3, -8.3],
            [119.8, -8.3],
            [119.8, -8.7],
          ],
        ],
      },
      created_at: '2024-01-01T00:00:00Z',
    }

    const result = filterCellsByTargetArea([], targetArea)
    expect(result).toEqual([])
  })
})
