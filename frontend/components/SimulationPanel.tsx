'use client'

/**
 * SimulationPanel — Task 24.1 (Requirements 5.1–5.5, 9.3)
 *
 * Provides the "Simulate New BTS" action for the currently selected
 * BTS candidate. Calls POST /api/simulate and displays Before/After
 * heatmap metrics with:
 *   - % Good cells change
 *   - Villages newly covered
 *   - Updated Coverage Score
 *
 * When the scenario is unavailable, shows the UnavailableScenario message.
 * Never fabricates or displays a fallback estimate for unavailable scenarios.
 *
 * Disabled when:
 *   - no candidate is selected
 *   - no target area has been resolved
 *   - a request is already in flight
 *
 * All outputs carry the visible "GeoAI-assisted estimate" label (Req 9.3).
 */

import { useState, useCallback } from 'react'
import type { BTSCandidate, SimulationResult, UnavailableScenario, RegionId } from '@/lib/types'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SimulationResponse =
  | ({ kind: 'result' } & SimulationResult)
  | ({ kind: 'unavailable' } & UnavailableScenario)

export interface SimulationPanelProps {
  /** Currently selected BTS candidate. null = disabled. */
  candidate: BTSCandidate | null
  /** Active region ID. */
  regionId: RegionId
  /** Whether a target area has been resolved. Disables action when false. */
  targetAreaResolved: boolean
  /**
   * Override for the POST /api/simulate fetch — used in tests.
   * Default: real fetch to /api/simulate.
   */
  submitSimulate?: (candidateId: string, regionId: RegionId) => Promise<SimulationResponse>
}

// ---------------------------------------------------------------------------
// Default API call
// ---------------------------------------------------------------------------

export async function defaultSubmitSimulate(
  candidateId: string,
  regionId: RegionId,
): Promise<SimulationResponse> {
  const res = await fetch('/api/simulate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ candidate_id: candidateId, region_id: regionId }),
  })

  // HTTP 404 means UnavailableScenario — parse the body and return it as a
  // discriminated result so the panel can display the human-readable message.
  // Do NOT throw here: 404 is an expected semantic response, not a transport error.
  if (res.status === 404) {
    const body = await res.json().catch(() => ({}))
    if (body.unavailable === true) {
      return { kind: 'unavailable', ...body } as SimulationResponse
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(
      (body.error && typeof body.error === 'object' ? body.error.message : body.error) ??
      `Simulate API error: ${res.status}`,
    )
  }

  const data = await res.json()
  // Discriminate: UnavailableScenario has `unavailable: true`
  if (data.unavailable === true) {
    return { kind: 'unavailable', ...data } as SimulationResponse
  }
  return { kind: 'result', ...data } as SimulationResponse
}

// ---------------------------------------------------------------------------
// Metric display helpers
// ---------------------------------------------------------------------------

function MetricCard({
  label,
  value,
  testId,
}: {
  label: string
  value: string
  testId: string
}) {
  return (
    <div
      data-testid={testId}
      style={{
        background: '#f9fafb',
        borderRadius: 6,
        padding: '8px 12px',
        textAlign: 'center',
        flex: 1,
        minWidth: 80,
      }}
    >
      <div
        style={{ fontSize: '1.2rem', fontWeight: 700, color: '#111827' }}
      >
        {value}
      </div>
      <div style={{ fontSize: '0.72rem', color: '#6b7280', marginTop: 2 }}>
        {label}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SimulationPanel component
// ---------------------------------------------------------------------------

export default function SimulationPanel({
  candidate,
  regionId,
  targetAreaResolved,
  submitSimulate = defaultSubmitSimulate,
}: SimulationPanelProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)
  const [result, setResult]   = useState<SimulationResponse | null>(null)

  const isDisabled =
    !candidate || !targetAreaResolved || loading

  const handleSimulate = useCallback(async () => {
    if (!candidate || !targetAreaResolved || loading) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const resp = await submitSimulate(candidate.candidate_id, regionId)
      setResult(resp)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Simulation failed.')
    } finally {
      setLoading(false)
    }
  }, [candidate, regionId, targetAreaResolved, loading, submitSimulate])

  const panelStyle: React.CSSProperties = {
    background: '#ffffff',
    borderRadius: 8,
    boxShadow: '0 2px 12px rgba(0,0,0,0.12)',
    padding: '14px 16px',
    fontFamily: 'sans-serif',
    fontSize: '0.88rem',
  }

  const labelStyle: React.CSSProperties = {
    fontSize: '0.72rem',
    fontWeight: 600,
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    margin: '10px 0 4px',
  }

  return (
    <div data-testid="simulation-panel" style={panelStyle}>
      <p style={{ fontWeight: 700, color: '#111827', margin: '0 0 10px' }}>
        Simulate New BTS
      </p>

      {/* Simulate button */}
      <button
        data-testid="simulate-btn"
        onClick={handleSimulate}
        disabled={isDisabled}
        aria-label={
          !candidate
            ? 'No candidate selected'
            : !targetAreaResolved
            ? 'No target area resolved'
            : loading
            ? 'Simulation in progress'
            : 'Simulate BTS placement'
        }
        style={{
          width: '100%',
          padding: '8px 0',
          background: isDisabled ? '#d1d5db' : '#1d4ed8',
          color: isDisabled ? '#9ca3af' : '#ffffff',
          border: 'none',
          borderRadius: 4,
          cursor: isDisabled ? 'not-allowed' : 'pointer',
          fontWeight: 600,
          fontSize: '0.88rem',
        }}
      >
        {loading ? 'Simulating…' : 'Simulate New BTS'}
      </button>

      {/* Disabled hint */}
      {!candidate && (
        <p
          style={{ color: '#9ca3af', fontSize: '0.78rem', margin: '6px 0 0' }}
          data-testid="simulate-no-candidate"
        >
          Select a BTS candidate to simulate.
        </p>
      )}
      {candidate && !targetAreaResolved && (
        <p
          style={{ color: '#9ca3af', fontSize: '0.78rem', margin: '6px 0 0' }}
          data-testid="simulate-no-target"
        >
          Resolve a target area first.
        </p>
      )}

      {/* Loading */}
      {loading && (
        <p
          style={{ color: '#6b7280', fontSize: '0.82rem', margin: '8px 0 0' }}
          data-testid="simulate-loading"
          role="status"
          aria-live="polite"
        >
          Computing simulation…
        </p>
      )}

      {/* Request error */}
      {error && !loading && (
        <p
          style={{ color: '#dc2626', fontSize: '0.82rem', margin: '8px 0 0' }}
          data-testid="simulate-error"
          role="alert"
        >
          {error}
        </p>
      )}

      {/* UnavailableScenario */}
      {result?.kind === 'unavailable' && (
        <div
          data-testid="simulate-unavailable"
          style={{
            marginTop: 10,
            padding: '10px 12px',
            background: '#fef3c7',
            border: '1px solid #fbbf24',
            borderRadius: 6,
            color: '#92400e',
          }}
          role="alert"
        >
          <strong>Scenario unavailable</strong>
          <p style={{ margin: '4px 0 0', fontSize: '0.82rem' }}>
            {result.message}
          </p>
        </div>
      )}

      {/* Successful SimulationResult */}
      {result?.kind === 'result' && (
        <div data-testid="simulate-result" style={{ marginTop: 12 }}>
          {/* Before / After header */}
          <div
            style={{
              display: 'flex',
              gap: 8,
              marginBottom: 10,
            }}
          >
            <div
              data-testid="simulate-before-label"
              style={{
                flex: 1,
                textAlign: 'center',
                padding: '4px 0',
                background: '#f3f4f6',
                borderRadius: 4,
                fontWeight: 600,
                fontSize: '0.82rem',
                color: '#374151',
              }}
            >
              Before
            </div>
            <div
              data-testid="simulate-after-label"
              style={{
                flex: 1,
                textAlign: 'center',
                padding: '4px 0',
                background: '#dbeafe',
                borderRadius: 4,
                fontWeight: 600,
                fontSize: '0.82rem',
                color: '#1d4ed8',
              }}
            >
              After
            </div>
          </div>

          {/* Metrics */}
          <p style={labelStyle}>Projected Impact</p>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <MetricCard
              label="% Good cells change"
              value={
                result.pct_good_change >= 0
                  ? `+${result.pct_good_change.toFixed(1)}%`
                  : `${result.pct_good_change.toFixed(1)}%`
              }
              testId="simulate-pct-good"
            />
            <MetricCard
              label="Villages newly covered"
              value={String(result.villages_newly_covered)}
              testId="simulate-villages"
            />
            <MetricCard
              label="Updated Coverage Score"
              value={result.new_coverage_score.toFixed(1)}
              testId="simulate-new-score"
            />
          </div>

          {/* GeoAI label — required by Req 9.3 */}
          <p
            data-testid="simulate-geoai-label"
            style={{
              fontSize: '0.7rem',
              color: '#9ca3af',
              margin: '10px 0 0',
              fontStyle: 'italic',
            }}
          >
            GeoAI-assisted estimate — decision support only
          </p>
        </div>
      )}
    </div>
  )
}
