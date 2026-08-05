'use client'

/**
 * SidePanel — Task 23.2 (Requirements 3.4, 4.6, 8.2, 8.4, 10.4, 11.3)
 *
 * Appears on cell click or BTS candidate click.
 * Shows: Coverage Score, Confidence Tag, model version, scoring run
 * timestamp, SHAP top-3 in plain language, and (for candidates) rank.
 *
 * SHAP panel is co-located with Coverage Score — no separate page navigation.
 * Never renders undefined/null/raw-object SHAP values.
 */

import type { GridCell, BTSCandidate, ShapEntry, ConfidenceLevel } from '@/lib/types'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SidePanelSelection =
  | { kind: 'cell';      data: GridCell }
  | { kind: 'candidate'; data: BTSCandidate }

export interface SidePanelProps {
  selection: SidePanelSelection | null
  loading?: boolean
  error?: string | null
  onClose?: () => void
}

// ---------------------------------------------------------------------------
// Confidence badge colours
// ---------------------------------------------------------------------------

const CONFIDENCE_COLOUR: Record<ConfidenceLevel, string> = {
  High: '#16a34a',
  Med:  '#ca8a04',
  Low:  '#dc2626',
}

// ---------------------------------------------------------------------------
// SHAP direction arrow
// ---------------------------------------------------------------------------

function shapArrow(direction: 'positive' | 'negative'): string {
  return direction === 'positive' ? '↑' : '↓'
}

function shapColour(direction: 'positive' | 'negative'): string {
  return direction === 'positive' ? '#16a34a' : '#dc2626'
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ShapRow({ entry }: { entry: ShapEntry }) {
  if (
    !entry ||
    typeof entry.feature_name !== 'string' ||
    !entry.feature_name ||
    typeof entry.value !== 'number' ||
    !['positive', 'negative'].includes(entry.direction)
  ) {
    return null
  }

  return (
    <li
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '6px',
        fontSize: '0.82rem',
        padding: '3px 0',
      }}
    >
      <span
        style={{ fontWeight: 700, color: shapColour(entry.direction), minWidth: 14 }}
        aria-label={entry.direction}
      >
        {shapArrow(entry.direction)}
      </span>
      <span style={{ flex: 1, color: '#374151' }}>{entry.feature_name}</span>
      <span style={{ color: '#6b7280', fontFamily: 'monospace', fontSize: '0.8rem' }}>
        {entry.value >= 0 ? '+' : ''}{entry.value.toFixed(2)}
      </span>
    </li>
  )
}

function ScoreBar({ score }: { score: number }) {
  const clipped = Math.max(0, Math.min(100, score))
  const colour = clipped >= 70 ? '#22c55e' : clipped >= 40 ? '#eab308' : '#ef4444'
  return (
    <div
      style={{
        background: '#e5e7eb',
        borderRadius: 4,
        height: 8,
        margin: '4px 0 8px',
        overflow: 'hidden',
      }}
      role="progressbar"
      aria-valuenow={clipped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        style={{
          width: `${clipped}%`,
          height: '100%',
          background: colour,
          borderRadius: 4,
          transition: 'width 0.3s ease',
        }}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function SidePanel({
  selection,
  loading = false,
  error = null,
  onClose,
}: SidePanelProps) {
  const isOpen = loading || error !== null || selection !== null

  if (!isOpen) return null

  const panelStyle: React.CSSProperties = {
    position: 'absolute',
    top: 16,
    right: 16,
    width: 300,
    maxHeight: 'calc(100vh - 32px)',
    overflowY: 'auto',
    background: '#ffffff',
    borderRadius: 8,
    boxShadow: '0 4px 24px rgba(0,0,0,0.18)',
    padding: '16px',
    zIndex: 10,
    fontFamily: 'sans-serif',
  }

  const labelStyle: React.CSSProperties = {
    fontSize: '0.72rem',
    fontWeight: 600,
    color: '#6b7280',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    margin: '10px 0 2px',
  }

  const valueStyle: React.CSSProperties = {
    fontSize: '0.88rem',
    color: '#111827',
  }

  const headerStyle: React.CSSProperties = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  }

  return (
    <div style={panelStyle} data-testid="side-panel">
      {/* Header */}
      <div style={headerStyle}>
        <span style={{ fontSize: '0.9rem', fontWeight: 700, color: '#111827' }}>
          {selection?.kind === 'candidate' ? 'BTS Candidate' : 'Coverage Cell'}
        </span>
        {onClose && (
          <button
            onClick={onClose}
            aria-label="Close side panel"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: '1.1rem',
              color: '#6b7280',
              padding: '0 2px',
            }}
          >
            ×
          </button>
        )}
      </div>

      {/* Loading */}
      {loading && (
        <p style={{ color: '#6b7280', fontSize: '0.88rem' }} data-testid="side-panel-loading">
          Loading…
        </p>
      )}

      {/* Error */}
      {error && !loading && (
        <p
          style={{ color: '#dc2626', fontSize: '0.88rem' }}
          data-testid="side-panel-error"
          role="alert"
        >
          {error}
        </p>
      )}

      {/* Content */}
      {selection && !loading && !error && (
        <div data-testid="side-panel-content">
          {/* Candidate rank (candidates only) */}
          {selection.kind === 'candidate' && (
            <>
              <p style={labelStyle}>Rank</p>
              <p style={valueStyle} data-testid="candidate-rank">
                #{selection.data.rank}
              </p>
            </>
          )}

          {/* Low-confidence disclaimer (Req 7.4) */}
          {selection.data.confidence_tag === 'Low' && (
            <div
              data-testid="side-panel-low-confidence-disclaimer"
              role="alert"
              style={{
                background: '#fef2f2',
                border: '1px solid #fca5a5',
                borderRadius: 6,
                padding: '8px 10px',
                marginBottom: 8,
                fontSize: '0.78rem',
                color: '#991b1b',
              }}
            >
              ⚠ <strong>Low confidence</strong> — this estimate is based on sparse data
              and should not be treated as an authoritative signal measurement.
            </div>
          )}

          {/* Coverage Score */}
          <p style={labelStyle}>Coverage Score</p>
          {(() => {
            const score = selection.kind === 'cell'
              ? selection.data.coverage_score
              : selection.data.expected_improvement  // use improvement as proxy for candidates
            return (
              <>
                <p
                  style={{ ...valueStyle, fontSize: '1.6rem', fontWeight: 700, margin: '0' }}
                  data-testid="coverage-score"
                >
                  {typeof score === 'number' ? score.toFixed(1) : '—'}
                </p>
                <ScoreBar score={typeof score === 'number' ? score : 0} />
              </>
            )
          })()}

          {/* Confidence Tag */}
          <p style={labelStyle}>Confidence</p>
          <span
            style={{
              display: 'inline-block',
              padding: '2px 10px',
              borderRadius: 12,
              background:
                CONFIDENCE_COLOUR[selection.data.confidence_tag] + '1a',
              color: CONFIDENCE_COLOUR[selection.data.confidence_tag],
              fontWeight: 700,
              fontSize: '0.82rem',
              border: `1px solid ${CONFIDENCE_COLOUR[selection.data.confidence_tag]}40`,
            }}
            data-testid="confidence-tag"
          >
            {selection.data.confidence_tag}
          </span>

          {/* GeoAI label — always visible (Requirement 9.3) */}
          <p
            style={{
              fontSize: '0.7rem',
              color: '#9ca3af',
              margin: '8px 0 4px',
              fontStyle: 'italic',
            }}
            data-testid="geoai-label"
          >
            GeoAI-assisted estimate — decision support only
          </p>

          {/* Model version */}
          <p style={labelStyle}>Model Version</p>
          <p style={valueStyle} data-testid="model-version">
            {selection.data.model_version || '—'}
          </p>

          {/* Scoring run ID */}
          <p style={labelStyle}>Scoring Run</p>
          <p style={{ ...valueStyle, fontFamily: 'monospace', fontSize: '0.8rem' }} data-testid="scoring-run">
            {selection.data.scoring_run_id || '—'}
          </p>

          {/* Scoring run timestamp — distinct from run ID (Req 11.3) */}
          <p style={labelStyle}>Scored At</p>
          <p
            style={{ ...valueStyle, fontFamily: 'monospace', fontSize: '0.8rem' }}
            data-testid="scoring-run-timestamp"
          >
            {selection.data.scoring_run_timestamp
              ? new Date(selection.data.scoring_run_timestamp).toLocaleString(undefined, {
                  dateStyle: 'medium',
                  timeStyle: 'short',
                })
              : '—'}
          </p>

          {/* SHAP top-3 — co-located in same panel (Requirement 8.4) */}
          <p style={labelStyle}>Top Factors</p>
          <ul
            style={{ listStyle: 'none', padding: 0, margin: '4px 0 0' }}
            data-testid="shap-top3"
          >
            {(() => {
              const entries: ShapEntry[] =
                selection.kind === 'cell'
                  ? (selection.data.shap_top3 ?? [])
                  : Object.entries(selection.data.shap_values ?? {})
                      .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
                      .slice(0, 3)
                      .map(([feature_name, value]) => ({
                        feature_name,
                        value,
                        direction: value >= 0 ? 'positive' : 'negative',
                      } as ShapEntry))

              if (!entries.length) {
                return (
                  <li style={{ color: '#9ca3af', fontSize: '0.82rem' }}>
                    No SHAP data available
                  </li>
                )
              }
              return entries
                .filter((e) => e && typeof e.feature_name === 'string' && e.feature_name)
                .map((entry, i) => (
                  <ShapRow key={`${entry.feature_name}-${i}`} entry={entry} />
                ))
            })()}
          </ul>
        </div>
      )}
    </div>
  )
}
