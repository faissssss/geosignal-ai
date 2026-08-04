'use client'

/**
 * PowerOverlay — Task 24.3 (Requirements 6.5)
 *
 * Optional toggle for power / energy feasibility information.
 * Shows or hides proximity to nearest power-grid node or solar-potential rating.
 *
 * Invariants:
 *   - Toggling NEVER changes the Coverage Score.
 *   - Toggling NEVER triggers a new drag-drop or simulation request.
 *   - Missing values are shown as "Unavailable", never fabricated.
 *   - The Coverage Score field is passed in as a prop and is displayed
 *     unchanged — this component never mutates or derives a new score.
 *
 * # Feature: geosignal-ai, Property 14: Power Overlay Non-Interference
 * Validates: Requirements 6.5
 */

import { useState } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PowerFeasibilityData {
  /** Distance in km to the nearest power-grid node. null = unavailable. */
  nearest_grid_node_km: number | null
  /** Solar potential rating (e.g. 'High', 'Med', 'Low'). null = unavailable. */
  solar_potential_rating: string | null
}

export interface PowerOverlayProps {
  /**
   * The current Coverage Score from the drag-drop or simulation result.
   * Passed in read-only — this component NEVER modifies it.
   */
  coverageScore: number | null
  /**
   * Feasibility data for the current drop position.
   * null when no result is available yet.
   */
  feasibilityData: PowerFeasibilityData | null
  /**
   * Called when the toggle changes. Parent can update its own overlayEnabled
   * state without triggering a new API request.
   */
  onToggle?: (enabled: boolean) => void
  /**
   * Controlled mode: if provided, the component uses this value instead of
   * internal state. Useful for tests.
   */
  enabled?: boolean
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function PowerOverlay({
  coverageScore,
  feasibilityData,
  onToggle,
  enabled: controlledEnabled,
}: PowerOverlayProps) {
  const [internalEnabled, setInternalEnabled] = useState(false)
  // Support both controlled and uncontrolled usage
  const isEnabled =
    controlledEnabled !== undefined ? controlledEnabled : internalEnabled

  const handleToggle = () => {
    const next = !isEnabled
    if (controlledEnabled === undefined) {
      setInternalEnabled(next)
    }
    // onToggle fires but does NOT trigger any coverage recalculation
    onToggle?.(next)
  }

  const panelStyle: React.CSSProperties = {
    background: '#ffffff',
    borderRadius: 8,
    boxShadow: '0 2px 12px rgba(0,0,0,0.12)',
    padding: '12px 16px',
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

  const unavailableStyle: React.CSSProperties = {
    color: '#9ca3af',
    fontStyle: 'italic',
    fontSize: '0.82rem',
  }

  return (
    <div data-testid="power-overlay" style={panelStyle}>
      {/* Header with toggle */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <p style={{ fontWeight: 700, color: '#111827', margin: 0 }}>
          Power / Energy Feasibility
        </p>
        <label
          style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
          aria-label={isEnabled ? 'Disable power overlay' : 'Enable power overlay'}
        >
          <span style={{ fontSize: '0.78rem', color: '#6b7280' }}>
            {isEnabled ? 'On' : 'Off'}
          </span>
          <input
            type="checkbox"
            data-testid="power-overlay-toggle"
            checked={isEnabled}
            onChange={handleToggle}
            aria-label="Toggle power overlay"
            style={{ cursor: 'pointer' }}
          />
        </label>
      </div>

      {/* Coverage Score (read-only, unchanged by toggling — Req 6.5) */}
      <p style={labelStyle}>Coverage Score</p>
      <div
        data-testid="power-overlay-coverage-score"
        style={{ fontSize: '1.4rem', fontWeight: 700, color: '#111827', margin: '0 0 4px' }}
      >
        {coverageScore !== null && coverageScore !== undefined
          ? coverageScore.toFixed(1)
          : '—'}
      </div>
      <p
        style={{
          fontSize: '0.7rem',
          color: '#9ca3af',
          margin: '0 0 8px',
          fontStyle: 'italic',
        }}
        data-testid="power-coverage-note"
      >
        Coverage Score is unchanged by this overlay.
      </p>

      {/* Feasibility content — shown only when toggle is on */}
      {isEnabled && (
        <div data-testid="power-overlay-content">
          {/* Power grid proximity */}
          <p style={labelStyle}>Nearest Power Grid Node</p>
          {feasibilityData?.nearest_grid_node_km !== null &&
          feasibilityData?.nearest_grid_node_km !== undefined ? (
            <p
              data-testid="power-grid-distance"
              style={{ fontSize: '0.88rem', color: '#374151', margin: 0 }}
            >
              {feasibilityData.nearest_grid_node_km.toFixed(1)} km away
            </p>
          ) : (
            <p
              data-testid="power-grid-unavailable"
              style={unavailableStyle}
            >
              Unavailable
            </p>
          )}

          {/* Solar potential */}
          <p style={labelStyle}>Solar Potential</p>
          {feasibilityData?.solar_potential_rating !== null &&
          feasibilityData?.solar_potential_rating !== undefined ? (
            <p
              data-testid="power-solar-rating"
              style={{ fontSize: '0.88rem', color: '#374151', margin: 0 }}
            >
              {feasibilityData.solar_potential_rating}
            </p>
          ) : (
            <p
              data-testid="power-solar-unavailable"
              style={unavailableStyle}
            >
              Unavailable
            </p>
          )}
        </div>
      )}

      {/* Off state placeholder */}
      {!isEnabled && (
        <p
          data-testid="power-overlay-off-msg"
          style={{ color: '#9ca3af', fontSize: '0.8rem', margin: '4px 0 0' }}
        >
          Enable to view power and energy feasibility information.
        </p>
      )}
    </div>
  )
}
