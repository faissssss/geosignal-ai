'use client'

/**
 * LayersButton — Google-Maps-style "Layers" control (plan Phase 5).
 *
 * A compact button that opens a non-overlapping panel containing:
 *   - All six overlay toggles (Heatmap, Land Cover, Contours, Villages,
 *     BTS Towers, Candidates) — the same state the checkbox strip drives.
 *   - Base map selection (Default / Satellite / Terrain).
 *   - Coverage visualization mode (Thermal / Gaps / Confidence).
 *   - Display options (heatmap opacity slider, legend toggle).
 *
 * The panel opens downward inside the left control stack and scrolls
 * internally. It never overlaps the right-side planning panels.
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import type { LayerVisibility } from '@/lib/types'
import type { HeatmapMode } from '@/lib/heatmap'
import { BASE_MAPS, BASE_MAP_MODES, type BaseMapMode } from '@/lib/map/baseMaps'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface LayersButtonProps {
  /** Current visibility state for every overlay. */
  visibility: LayerVisibility
  /** Called when an overlay toggle changes. */
  onVisibilityChange: (layer: keyof LayerVisibility, value: boolean) => void
  /** Active base map mode. */
  baseMapMode: BaseMapMode
  /** Called when the base map mode changes. */
  onBaseMapModeChange: (mode: BaseMapMode) => void
  /** Active heatmap coverage mode. */
  coverageMode: HeatmapMode
  /** Called when the coverage mode changes. */
  onCoverageModeChange: (mode: HeatmapMode) => void
  /** Master heatmap opacity (0..1). */
  heatmapOpacity: number
  /** Called when the heatmap opacity changes. */
  onHeatmapOpacityChange: (opacity: number) => void
  /** Whether the heatmap legend is visible. */
  showLegend: boolean
  /** Called when the legend toggle changes. */
  onShowLegendChange: (show: boolean) => void
}

const OVERLAY_LABELS: Array<{ key: keyof LayerVisibility; label: string }> = [
  { key: 'heatmap',    label: 'Heatmap' },
  { key: 'landcover',  label: 'Land Cover' },
  { key: 'contours',   label: 'Contours' },
  { key: 'villages',   label: 'Villages' },
  { key: 'btsMarkers', label: 'BTS Towers' },
  { key: 'candidates', label: 'Candidates' },
]

const COVERAGE_MODES: Array<{ key: HeatmapMode; label: string }> = [
  { key: 'thermal',    label: 'Coverage thermal' },
  { key: 'gap',        label: 'Coverage gaps' },
  { key: 'confidence', label: 'Confidence' },
]

// ---------------------------------------------------------------------------
// LayersButton
// ---------------------------------------------------------------------------

export default function LayersButton({
  visibility,
  onVisibilityChange,
  baseMapMode,
  onBaseMapModeChange,
  coverageMode,
  onCoverageModeChange,
  heatmapOpacity,
  onHeatmapOpacityChange,
  showLegend,
  onShowLegendChange,
}: LayersButtonProps) {
  const [open, setOpen] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  // Close on outside click
  const onButtonClick = useCallback(() => setOpen((o) => !o), [])
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  return (
    <div ref={panelRef} style={{ display: 'flex', flexDirection: 'column', gap: 6, alignSelf: 'flex-start' }}>
      <button
        type="button"
        data-testid="layers-button"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={onButtonClick}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '8px 14px',
          background: 'rgba(255,255,255,0.95)',
          border: '1px solid #d1d5db',
          borderRadius: 8,
          boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
          cursor: 'pointer',
          fontFamily: 'sans-serif',
          fontSize: '0.85rem',
          fontWeight: 600,
          color: '#1f2937',
        }}
      >
        <span aria-hidden style={{ fontSize: '1rem' }}>🗺️</span>
        Layers
        <span aria-hidden style={{ marginLeft: 4, fontSize: '0.7rem', color: '#6b7280' }}>
          {open ? '▲' : '▼'}
        </span>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Map layers and display options"
          data-testid="layers-panel"
          style={{
            width: 260,
            maxHeight: 480,
            overflowY: 'auto',
            background: 'rgba(255,255,255,0.97)',
            border: '1px solid #e5e7eb',
            borderRadius: 10,
            boxShadow: '0 6px 20px rgba(0,0,0,0.16)',
            padding: '12px 14px',
            fontFamily: 'sans-serif',
            fontSize: '0.8rem',
            color: '#374151',
          }}
        >
          {/* ── Overlays ─────────────────────────────────────────────── */}
          <div style={{ fontWeight: 700, marginBottom: 8, color: '#111827' }}>Overlays</div>
          {OVERLAY_LABELS.map(({ key, label }) => (
            <label
              key={key}
              data-testid={`layer-option-${key}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '5px 0',
                cursor: 'pointer',
                userSelect: 'none',
              }}
            >
              <input
                type="checkbox"
                checked={visibility[key]}
                onChange={(e) => onVisibilityChange(key, e.target.checked)}
                data-testid={`layers-checkbox-${key}`}
              />
              {label}
            </label>
          ))}

          <hr style={{ border: 'none', borderTop: '1px solid #e5e7eb', margin: '10px 0' }} />

          {/* ── Base map ─────────────────────────────────────────────── */}
          <div style={{ fontWeight: 700, marginBottom: 6, color: '#111827' }}>Base map</div>
          {BASE_MAP_MODES.map((m) => {
            const cfg = BASE_MAPS[m]
            const disabled = !cfg.available
            return (
              <label
                key={m}
                data-testid={`basemap-option-${m}`}
                title={disabled ? cfg.unavailableHint : undefined}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '4px 0',
                  cursor: disabled ? 'not-allowed' : 'pointer',
                  userSelect: 'none',
                  opacity: disabled ? 0.55 : 1,
                }}
              >
                <input
                  type="radio"
                  name="basemap"
                  checked={baseMapMode === m}
                  disabled={disabled}
                  onChange={() => onBaseMapModeChange(m)}
                  data-testid={`basemap-radio-${m}`}
                />
                {cfg.label}
                {disabled && <span style={{ marginLeft: 'auto', fontSize: '0.68rem', color: '#9ca3af' }}>—</span>}
              </label>
            )
          })}

          <hr style={{ border: 'none', borderTop: '1px solid #e5e7eb', margin: '10px 0' }} />

          {/* ── Coverage visualization ───────────────────────────────── */}
          <div style={{ fontWeight: 700, marginBottom: 6, color: '#111827' }}>Coverage visualization</div>
          {COVERAGE_MODES.map(({ key, label }) => (
            <label
              key={key}
              data-testid={`coverage-option-${key}`}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '4px 0',
                cursor: 'pointer',
                userSelect: 'none',
              }}
            >
              <input
                type="radio"
                name="coverage"
                checked={coverageMode === key}
                onChange={() => onCoverageModeChange(key)}
                data-testid={`coverage-radio-${key}`}
              />
              {label}
            </label>
          ))}

          <hr style={{ border: 'none', borderTop: '1px solid #e5e7eb', margin: '10px 0' }} />

          {/* ── Display ──────────────────────────────────────────────── */}
          <div style={{ fontWeight: 700, marginBottom: 6, color: '#111827' }}>Display</div>
          <div style={{ marginBottom: 8 }}>
            <div style={{ marginBottom: 4 }}>
              Heatmap opacity{' '}
              <span style={{ color: '#6b7280' }}>{Math.round(heatmapOpacity * 100)}%</span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={heatmapOpacity}
              onChange={(e) => onHeatmapOpacityChange(Number(e.target.value))}
              data-testid="heatmap-opacity-slider"
              style={{ width: '100%' }}
            />
          </div>
          <label
            data-testid="legend-option"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '4px 0',
              cursor: 'pointer',
              userSelect: 'none',
            }}
          >
            <input
              type="checkbox"
              checked={showLegend}
              onChange={(e) => onShowLegendChange(e.target.checked)}
              data-testid="legend-checkbox"
            />
            Show legend
          </label>
        </div>
      )}
    </div>
  )
}
