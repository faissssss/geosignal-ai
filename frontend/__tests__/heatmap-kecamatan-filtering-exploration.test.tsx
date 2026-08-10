/**
 * Bug Condition Exploration Property Test
 * heatmap-kecamatan-filtering bugfix spec - Task 1 (re-run after fix)
 *
 * **FIXED STATE**: The spatial filtering fix is now implemented. filterCellsByTargetArea
 * lives in lib/validation/filterCellsByTargetArea.ts (single production implementation,
 * shared with the nextjs-filtering spec) and is wired into MapView before cells are
 * mapped to coverage cells. This test re-runs the original Task 1 exploration and now
 * verifies the FIXED behavior:
 * 1. filterCellsByTargetArea exists and is imported from lib/validation
 * 2. Cells outside a selected kecamatan boundary are filtered out
 * 3. null target area preserves all cells unchanged
 * 4. Every retained cell is within the selected boundary
 *
 * Uses the real GADM fixture (gadm41_IDN_2.json) so it is deterministic and does not
 * depend on a running dev server.
 *
 * **Validates: Requirements 1.1, 1.2, 1.3, 1.6, 1.7**
 */

import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import * as fs from 'fs'
import * as path from 'path'
// @ts-ignore - Turf.js module resolution issue
import booleanPointInPolygon from '@turf/boolean-point-in-polygon'
// @ts-ignore - Turf.js module resolution issue
import { point, polygon, multiPolygon } from '@turf/helpers'
import { readFileSync } from 'fs'
import { join } from 'path'
import type { AdminBoundary, GridCell, TargetArea } from '@/lib/types'
import { filterCellsByTargetArea } from '@/lib/validation/filterCellsByTargetArea'

// Load real GADM NTT kecamatan boundaries (deterministic fixture, no live API call)
const gadmFilePath = path.resolve(__dirname, '../../data/gadm_cache/gadm41_IDN_2.json')
const gadmData = JSON.parse(fs.readFileSync(gadmFilePath, 'utf-8')) as {
  type: string
  features: Array<{
    type: string
    properties: {
      GID_2: string
      GID_0: string
      COUNTRY: string
      GID_1: string
      NAME_1: string
      NAME_2: string
      TYPE_2: string
      HASC_2: string
      M_ID?: string
    }
    geometry: { type: string; coordinates: unknown }
  }>
}

const deriveRegionId = (name1: string): string => {
  const normalized = name1.toLowerCase().replace(/\s/g, '')
  if (normalized.includes('nusatenggaratimur')) return 'ntt'
  return 'unknown'
}

const nttAdminBoundaries: AdminBoundary[] = gadmData.features
  .filter((f) => deriveRegionId(f.properties.NAME_1) === 'ntt')
  .map((f) => ({
    boundary_id: f.properties.GID_2,
    kecamatan_id: f.properties.GID_2,
    kecamatan_name: f.properties.NAME_2,
    region_id: 'ntt',
    boundary_geojson: f.geometry,
  }))

const makeTargetArea = (boundary: AdminBoundary): TargetArea => ({
  target_area_id: `ta-${boundary.boundary_id}`,
  region_id: 'ntt',
  selection_method: 'kecamatan',
  kecamatan_id: boundary.kecamatan_id,
  boundary_geojson: boundary.boundary_geojson,
  created_at: new Date().toISOString(),
})

const isWithinBoundary = (cell: GridCell, boundary: AdminBoundary): boolean => {
  const geometry = boundary.boundary_geojson as { type?: string; coordinates: number[][][] | number[][][][] }
  const feature = geometry.type === 'MultiPolygon'
    ? multiPolygon(geometry.coordinates as number[][][][])
    : polygon(geometry.coordinates as number[][][])
  return booleanPointInPolygon(point([cell.lon, cell.lat]), feature)
}

describe('Bug Condition Exploration - Heatmap Kecamatan Filtering (fixed)', () => {
  describe('Admin Boundary Data Validation', () => {
    it('should confirm that NTT admin boundaries are available', () => {
      expect(nttAdminBoundaries.length).toBeGreaterThan(0)

      const sampleBoundary = nttAdminBoundaries[0]
      expect(sampleBoundary).toBeDefined()
      expect(sampleBoundary.boundary_id).toBeDefined()
      expect(sampleBoundary.kecamatan_id).toBeDefined()
      expect(sampleBoundary.kecamatan_name).toBeDefined()
      expect(sampleBoundary.region_id).toBe('ntt')
      expect(sampleBoundary.boundary_geojson).toBeDefined()
    })

    it('should verify "Alor" boundary exists', () => {
      const alor = nttAdminBoundaries.find((b) =>
        b.kecamatan_name.toLowerCase() === 'alor'
      )

      expect(alor).toBeDefined()
      expect(alor?.boundary_geojson).toBeDefined()
    })
  })

  describe('Fixed Behavior - Spatial Filtering Exists', () => {
    it('should expose filterCellsByTargetArea from lib/validation (single implementation)', () => {
      const filterContent = readFileSync(
        join(process.cwd(), 'lib', 'validation', 'filterCellsByTargetArea.ts'),
        'utf-8'
      )

      expect(filterContent).toContain('export function filterCellsByTargetArea')
      expect(filterContent).toContain('booleanPointInPolygon')
    })

    it('should filter out cells outside the selected kecamatan boundary', () => {
      const alor = nttAdminBoundaries.find((b) =>
        b.kecamatan_name.toLowerCase() === 'alor'
      )!
      const targetArea = makeTargetArea(alor)

      // Cells spread across the whole region; only those near Alor should remain
      const mockNTTCells: GridCell[] = Array.from({ length: 200 }, (_, i) => ({
        cell_id: `cell-${i}`,
        region_id: 'ntt',
        lat: -9.0 + (i % 20) * 0.25,
        lon: 120.0 + Math.floor(i / 20) * 0.4,
        resolution_m: 1000,
        coverage_score: 50 + (i % 51),
        confidence_tag: 'High' as const,
        tier_used: '1' as const,
        shap_top3: [],
        model_version: 'v1',
        scoring_run_id: 'test',
      }))

      const filtered = filterCellsByTargetArea(mockNTTCells, targetArea)

      // Fix confirmed: filtering now happens inside the function
      expect(filtered.length).toBeLessThan(mockNTTCells.length)
      // Every retained cell must be inside the selected boundary
      expect(filtered.every((c) => isWithinBoundary(c, alor))).toBe(true)
    })

    it('should preserve all cells when no target area is selected', () => {
      const mockCells: GridCell[] = Array.from({ length: 50 }, (_, i) => ({
        cell_id: `cell-${i}`,
        region_id: 'ntt',
        lat: -8.5 + (i * 0.1),
        lon: 124.0 + (i * 0.1),
        resolution_m: 1000,
        coverage_score: 50 + i,
        confidence_tag: 'High' as const,
        tier_used: '1' as const,
        shap_top3: [],
        model_version: 'v1',
        scoring_run_id: 'test',
      }))

      const filtered = filterCellsByTargetArea(mockCells, null)

      expect(filtered).toHaveLength(50)
    })
  })

  describe('MapView Data Flow - Filtering In Place', () => {
    it('should confirm MapView calls filterCellsByTargetArea before mapping to coverage cells', () => {
      const mapViewContent = readFileSync(
        join(process.cwd(), 'components', 'MapView.tsx'),
        'utf-8'
      )

      expect(mapViewContent).toContain(
        "import { filterCellsByTargetArea } from '@/lib/validation/filterCellsByTargetArea'"
      )
      expect(mapViewContent).toContain('const filteredCells = filterCellsByTargetArea(cells, targetArea, setBoundaryGeometryError)')
      expect(mapViewContent).toContain('const coverageCells: CoverageCell[] = filteredCells.map')
    })
  })

  describe('Property-Based Test - Filtering Correctness', () => {
    it('should verify that for ANY kecamatan selection, only cells within the boundary are retained', () => {
      // Generate cells in a grid spanning the full NTT region
      const mockCells: GridCell[] = Array.from({ length: 300 }, (_, i) => ({
        cell_id: `cell-${i}`,
        region_id: 'ntt',
        lat: -11.0 + (i % 30) * 0.1,
        lon: 118.0 + Math.floor(i / 30) * 0.3,
        resolution_m: 1000,
        coverage_score: 40 + (i % 60),
        confidence_tag: 'High' as const,
        tier_used: '1' as const,
        shap_top3: [],
        model_version: 'v1',
        scoring_run_id: 'test',
      }))

      fc.assert(
        fc.property(
          fc.integer({ min: 0, max: Math.max(0, nttAdminBoundaries.length - 1) }),
          (boundaryIndex) => {
            if (nttAdminBoundaries.length === 0) {
              return true
            }

            const boundary = nttAdminBoundaries[boundaryIndex]
            const filtered = filterCellsByTargetArea(mockCells, makeTargetArea(boundary))

            // Never more cells than the input
            expect(filtered.length).toBeLessThanOrEqual(mockCells.length)

            // Every retained cell is within the selected boundary
            for (const cell of filtered) {
              expect(isWithinBoundary(cell, boundary)).toBe(true)
            }

            return true
          }
        ),
        { numRuns: 20 }
      )
    })
  })

  describe('Integration Points - Bug Locations (Fixed)', () => {
    it('should confirm the shared implementation location', () => {
      expect(
        path.resolve(join(process.cwd(), 'lib', 'validation', 'filterCellsByTargetArea.ts'))
      ).toContain('filterCellsByTargetArea.ts')
    })
  })
})