'use client'

/**
 * RegionSelector — Task 23.3 (Requirements 10.5)
 *
 * Switches active region without page reload.
 * Fetches grid cells and BTS candidates for the selected region.
 *
 * Race-condition strategy: AbortController per request + monotonic
 * requestId counter. If a stale response arrives after a newer one
 * has already been applied, the stale result is discarded.
 * On error, the previous region data is preserved.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import type { GridCell, BTSCandidate, RegionId } from '@/lib/types'
import { REGIONS } from '@/lib/types'
import { validateRegionDataCoverage, type DataCoverageStatus } from '@/lib/validation/data-coverage'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RegionData {
  regionId: RegionId
  cells: GridCell[]
  candidates: BTSCandidate[]
}

export interface RegionSelectorProps {
  /** Initially selected region. Defaults to 'ntt'. */
  initialRegion?: RegionId
  /**
   * Called whenever a new region's data is fully loaded.
   * Previous data is preserved on error — callback is NOT called on error.
   */
  onRegionChange: (data: RegionData) => void
  /**
   * Optional: override the fetch function for testing.
   * Defaults to the real /api/grid-cells and /api/recommendations fetches.
   */
  fetchRegionData?: (
    regionId: RegionId,
    signal: AbortSignal,
  ) => Promise<{ cells: GridCell[]; candidates: BTSCandidate[] }>
}

// ---------------------------------------------------------------------------
// Default fetch implementation
// ---------------------------------------------------------------------------

export async function defaultFetchRegionData(
  regionId: RegionId,
  signal: AbortSignal,
): Promise<{ cells: GridCell[]; candidates: BTSCandidate[] }> {
  // resolution_m is required by the grid-cells route (Task 25.5).
  // 100 m is the MVP grid resolution for all three regions (design.md §3.1).
  const gridUrl = `/api/grid-cells?region_id=${regionId}&resolution_m=100`

  const [cellsRes, candidatesRes] = await Promise.all([
    fetch(gridUrl, { signal }),
    // Candidates are scoped to a target_area_id in production; here we fetch
    // all for the region as an initial load (target_area filtering happens
    // in TargetAreaSelector workflow).
    fetch(`/api/recommendations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_area_id: `region:${regionId}` }),
      signal,
    }),
  ])

  if (!cellsRes.ok) {
    const body = await cellsRes.json().catch(() => ({}))
    const msg =
      body.error && typeof body.error === 'object'
        ? body.error.message
        : `Grid cells fetch failed: ${cellsRes.status}`
    throw new Error(msg)
  }
  // Candidates returning non-200 is non-fatal — return empty array
  const cells: GridCell[] = await cellsRes.json()
  const candidates: BTSCandidate[] = candidatesRes.ok
    ? await candidatesRes.json().catch(() => [])
    : []

  return { cells: Array.isArray(cells) ? cells : [], candidates }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function RegionSelector({
  initialRegion = 'ntt',
  onRegionChange,
  fetchRegionData = defaultFetchRegionData,
}: RegionSelectorProps) {
  const [activeRegion, setActiveRegion] = useState<RegionId>(initialRegion)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [coverage, setCoverage] = useState<DataCoverageStatus | null>(null)

  // AbortController for the in-flight request
  const abortRef = useRef<AbortController | null>(null)
  // Monotonic counter: only apply results from the latest request
  const requestIdRef = useRef(0)

  const loadRegion = useCallback(
    async (regionId: RegionId) => {
      // Cancel any previous in-flight request
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      // Capture the request ID for this specific call
      requestIdRef.current += 1
      const myRequestId = requestIdRef.current

      setLoading(true)
      setError(null)

      try {
        const data = await fetchRegionData(regionId, controller.signal)

        // Discard stale responses — a newer request has already been sent
        if (myRequestId !== requestIdRef.current) return

        onRegionChange({ regionId, ...data })
        setActiveRegion(regionId)
      } catch (err) {
        // AbortError means we cancelled intentionally — not an error
        if (err instanceof Error && err.name === 'AbortError') return

        // Discard stale error
        if (myRequestId !== requestIdRef.current) return

        // Preserve previous region on error (design.md Error Handling)
        setError(
          err instanceof Error ? err.message : 'Failed to load region data.',
        )
        // activeRegion intentionally NOT updated — old region is preserved
      } finally {
        if (myRequestId === requestIdRef.current) {
          setLoading(false)
        }
      }
    },
    [fetchRegionData, onRegionChange],
  )

  // Load initial region on mount
  useEffect(() => {
    loadRegion(initialRegion)
    return () => {
      abortRef.current?.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // run once on mount

  useEffect(() => {
    let active = true
    validateRegionDataCoverage(activeRegion)
      .then((status) => { if (active) setCoverage(status) })
      .catch(() => { if (active) setCoverage(null) })
    return () => { active = false }
  }, [activeRegion])

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div
      data-testid="region-selector"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 12px',
        background: 'rgba(255,255,255,0.95)',
        borderRadius: 8,
        boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
        fontFamily: 'sans-serif',
        fontSize: '0.88rem',
      }}
    >
      <label
        htmlFor="region-select"
        style={{ fontWeight: 600, color: '#374151', whiteSpace: 'nowrap' }}
      >
        Region
      </label>
      <select
        id="region-select"
        data-testid="region-select"
        value={activeRegion}
        disabled={loading}
        onChange={(e) => {
          const newRegion = e.target.value as RegionId
          loadRegion(newRegion)
        }}
        style={{
          border: '1px solid #d1d5db',
          borderRadius: 4,
          padding: '4px 8px',
          fontSize: '0.88rem',
          background: '#ffffff',
          cursor: loading ? 'not-allowed' : 'pointer',
        }}
        aria-label="Select analysis region"
      >
        {REGIONS.map((r) => (
          <option key={r.id} value={r.id}>
            {r.label}
          </option>
        ))}
      </select>

      {coverage && (
        <span
          data-testid="region-coverage-status"
          title={coverage.hasData
            ? `Heatmap data available in all ${coverage.totalKecamatan} kecamatan`
            : `${coverage.coveredKecamatan} of ${coverage.totalKecamatan} kecamatan have heatmap data${coverage.missingKecamatan.length ? `; missing: ${coverage.missingKecamatan.join(', ')}` : ''}`}
          style={{
            color: coverage.hasData ? '#15803d' : coverage.coveredKecamatan === 0 ? '#dc2626' : '#b45309',
            fontSize: '0.78rem', fontWeight: 600, whiteSpace: 'nowrap',
          }}
          aria-label={`Heatmap coverage: ${coverage.coveredKecamatan} of ${coverage.totalKecamatan} kecamatan`}
        >
          {coverage.hasData ? 'Complete' : coverage.coveredKecamatan === 0 ? 'No data' : 'Partial'} {coverage.coveredKecamatan}/{coverage.totalKecamatan}
        </span>
      )}

      {loading && (
        <span
          style={{ color: '#6b7280', fontSize: '0.8rem' }}
          data-testid="region-loading"
          aria-live="polite"
        >
          Loading…
        </span>
      )}

      {error && !loading && (
        <span
          style={{ color: '#dc2626', fontSize: '0.8rem' }}
          data-testid="region-error"
          role="alert"
        >
          {error}
        </span>
      )}
    </div>
  )
}
