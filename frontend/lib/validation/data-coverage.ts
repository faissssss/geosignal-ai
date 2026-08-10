import type { AdminBoundary, GridCell, RegionId } from '@/lib/types'
// @ts-ignore Turf v6 package does not expose declarations in this project.
import booleanPointInPolygon from '@turf/boolean-point-in-polygon'
// @ts-ignore Turf v6 package does not expose declarations in this project.
import { point, polygon, multiPolygon } from '@turf/helpers'

export interface DataCoverageStatus {
  hasData: boolean
  totalKecamatan: number
  coveredKecamatan: number
  missingKecamatan: string[]
}

function cellIsWithinBoundary(cell: GridCell, boundary: AdminBoundary): boolean {
  const geometry = boundary.boundary_geojson as { type?: string; coordinates?: number[][][] | number[][][][] }
  const feature = geometry.type === 'MultiPolygon'
    ? multiPolygon(geometry.coordinates as number[][][][])
    : polygon(geometry.coordinates as number[][][])
  return booleanPointInPolygon(point([cell.lon, cell.lat]), feature)
}

/** Fetch and spatially validate heatmap coverage for one map region. */
export async function validateRegionDataCoverage(regionId: RegionId): Promise<DataCoverageStatus> {
  const [boundariesResponse, cellsResponse] = await Promise.all([
    fetch(`/api/admin-boundaries?region_id=${regionId}`),
    fetch(`/api/grid-cells?region_id=${regionId}&resolution_m=100`),
  ])
  if (!boundariesResponse.ok || !cellsResponse.ok) throw new Error('Unable to validate heatmap data coverage.')
  const boundaries = (await boundariesResponse.json()) as AdminBoundary[]
  const cells = (await cellsResponse.json()) as GridCell[]
  const missingKecamatan = boundaries
    .filter((boundary) => !cells.some((cell) => cellIsWithinBoundary(cell, boundary)))
    .map((boundary) => boundary.kecamatan_name)
  return {
    hasData: cells.length > 0 && missingKecamatan.length === 0,
    totalKecamatan: boundaries.length,
    coveredKecamatan: boundaries.length - missingKecamatan.length,
    missingKecamatan,
  }
}
