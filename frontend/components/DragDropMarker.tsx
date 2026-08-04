'use client'

/**
 * DragDropMarker — Task 24.2 (Requirements 6.1–6.7, 9.3)
 *
 * Manages a draggable BTS candidate marker on the MapLibre map.
 * When dropped, calls POST /api/drag-drop with:
 *   - dropped latitude
 *   - dropped longitude
 *   - active region_id
 *   - current overlay_enabled state
 *
 * Displays on success:
 *   - Snapped/precomputed coordinate
 *   - Coverage Score
 *   - Confidence Tag
 *   - Grid resolution explanation
 *   - Comparison vs. model top candidate (including manual win case)
 *   - Coverage ring placeholder (terrain-deformed ring is rendered via map layer)
 *
 * When API returns OutsideExtentError: shows message, no Coverage Score.
 * All outputs carry "GeoAI-assisted estimate" label (Req 9.3).
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import type { Map as MapLibreMap, Marker } from 'maplibre-gl'
import type {
  DragDropResult,
  OutsideExtentError,
  ConfidenceLevel,
  RegionId,
} from '@/lib/types'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type DragDropResponse =
  | ({ kind: 'result' } & DragDropResult)
  | ({ kind: 'outside_extent' } & OutsideExtentError)

export interface DragDropMarkerProps {
  /** MapLibre map instance. null = inactive. */
  map: MapLibreMap | null
  /** Active region ID. */
  regionId: RegionId
  /** Whether the power overlay is currently enabled. */
  overlayEnabled: boolean
  /** Initial marker position. Defaults to map centre-ish. */
  initialLat?: number
  initialLon?: number
  /**
   * Override for the POST /api/drag-drop fetch — used in tests.
   */
  submitDragDrop?: (
    lat: number,
    lon: number,
    regionId: RegionId,
    overlayEnabled: boolean,
  ) => Promise<DragDropResponse>
  /**
   * Called when a result (or error) arrives.
   */
  onResult?: (result: DragDropResponse | null) => void
}

// ---------------------------------------------------------------------------
// Default API call
// ---------------------------------------------------------------------------

export async function defaultSubmitDragDrop(
  lat: number,
  lon: number,
  regionId: RegionId,
  overlayEnabled: boolean,
): Promise<DragDropResponse> {
  const res = await fetch('/api/drag-drop', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lat, lon, region_id: regionId, overlay_enabled: overlayEnabled }),
  })

  // HTTP 422 means OutsideExtentError — parse and return as a discriminated
  // result so the panel can display the message without a Coverage Score.
  // Do NOT throw: 422 is an expected semantic response, not a transport error.
  if (res.status === 422) {
    const body = await res.json().catch(() => ({}))
    if (body.outside_extent === true) {
      return { kind: 'outside_extent', ...body } as DragDropResponse
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(
      (body.error && typeof body.error === 'object' ? body.error.message : body.error) ??
      `Drag-drop API error: ${res.status}`,
    )
  }

  const data = await res.json()
  if (data.outside_extent === true) {
    return { kind: 'outside_extent', ...data } as DragDropResponse
  }
  return { kind: 'result', ...data } as DragDropResponse
}

// ---------------------------------------------------------------------------
// Confidence badge colour
// ---------------------------------------------------------------------------

const CONFIDENCE_COLOUR: Record<ConfidenceLevel, string> = {
  High: '#16a34a',
  Med:  '#ca8a04',
  Low:  '#dc2626',
}

// ---------------------------------------------------------------------------
// DragDropMarker component
// ---------------------------------------------------------------------------

export default function DragDropMarker({
  map,
  regionId,
  overlayEnabled,
  initialLat = -9.0,
  initialLon = 120.0,
  submitDragDrop = defaultSubmitDragDrop,
  onResult,
}: DragDropMarkerProps) {
  const markerRef = useRef<Marker | null>(null)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<string | null>(null)
  const [result, setResult]     = useState<DragDropResponse | null>(null)
  const [markerPos, setMarkerPos] = useState<{ lat: number; lon: number } | null>(null)

  // ── Handle a drop event ──────────────────────────────────────────────────
  const handleDrop = useCallback(
    async (lat: number, lon: number) => {
      setLoading(true)
      setError(null)
      setResult(null)
      setMarkerPos({ lat, lon })
      try {
        const resp = await submitDragDrop(lat, lon, regionId, overlayEnabled)
        setResult(resp)
        onResult?.(resp)
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Drag-drop request failed.'
        setError(msg)
        onResult?.(null)
      } finally {
        setLoading(false)
      }
    },
    [regionId, overlayEnabled, submitDragDrop, onResult],
  )

  // ── Create/update MapLibre marker ────────────────────────────────────────
  useEffect(() => {
    if (!map) return

    let isMounted = true

    ;(async () => {
      const maplibre = await import('maplibre-gl')
      if (!isMounted || !map) return

      // Create a custom draggable marker element
      const el = document.createElement('div')
      el.setAttribute('data-testid', 'drag-drop-marker-element')
      el.setAttribute('aria-label', 'Draggable BTS candidate marker')
      el.setAttribute('role', 'button')
      el.style.cssText = [
        'width:24px',
        'height:24px',
        'border-radius:50%',
        'background:#f59e0b',
        'border:3px solid #ffffff',
        'box-shadow:0 2px 6px rgba(0,0,0,0.4)',
        'cursor:grab',
        'display:flex',
        'align-items:center',
        'justify-content:center',
        'font-size:12px',
      ].join(';')
      el.textContent = '📡'

      const marker = new maplibre.Marker({ element: el, draggable: true })
        .setLngLat([initialLon, initialLat])
        .addTo(map)

      marker.on('dragend', () => {
        if (!isMounted) return
        const { lat, lng } = marker.getLngLat()
        handleDrop(lat, lng)
      })

      markerRef.current = marker
    })()

    return () => {
      isMounted = false
      markerRef.current?.remove()
      markerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map])

  // ── Expose handleDrop for tests (via data attribute on container) ────────

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
    <div
      data-testid="drag-drop-panel"
      style={panelStyle}
      // Expose handleDrop for testing purposes
      ref={(el) => {
        if (el) {
          // Store handler on DOM node for test access
          ;(el as unknown as Record<string, unknown>).__handleDrop = handleDrop
        }
      }}
    >
      <p style={{ fontWeight: 700, color: '#111827', margin: '0 0 6px' }}>
        Drag-and-Drop Placement
      </p>
      <p style={{ color: '#6b7280', fontSize: '0.8rem', margin: '0 0 10px' }}>
        Drag the marker on the map to any location to see its projected coverage.
      </p>

      {/* Loading */}
      {loading && (
        <p
          data-testid="dragdrop-loading"
          style={{ color: '#6b7280', fontSize: '0.82rem', margin: '0' }}
          role="status"
          aria-live="polite"
        >
          Computing coverage…
        </p>
      )}

      {/* Request error */}
      {error && !loading && (
        <p
          data-testid="dragdrop-error"
          style={{ color: '#dc2626', fontSize: '0.82rem', margin: '0' }}
          role="alert"
        >
          {error}
        </p>
      )}

      {/* OutsideExtentError */}
      {result?.kind === 'outside_extent' && (
        <div
          data-testid="dragdrop-outside-extent"
          style={{
            padding: '10px 12px',
            background: '#fef2f2',
            border: '1px solid #fca5a5',
            borderRadius: 6,
            color: '#991b1b',
          }}
          role="alert"
        >
          <strong>Outside coverage area</strong>
          <p style={{ margin: '4px 0 0', fontSize: '0.82rem' }}>
            {result.message}
          </p>
        </div>
      )}

      {/* Successful DragDropResult */}
      {result?.kind === 'result' && (
        <div data-testid="dragdrop-result">
          {/* Snapped coordinate */}
          <p style={labelStyle}>Snapped Position</p>
          <p
            data-testid="dragdrop-snapped-coord"
            style={{ fontSize: '0.82rem', color: '#374151', fontFamily: 'monospace', margin: '0' }}
          >
            {result.snapped_coordinate[0].toFixed(5)},{' '}
            {result.snapped_coordinate[1].toFixed(5)}
          </p>

          {/* Grid resolution explanation (Req 6.6) */}
          <p
            data-testid="dragdrop-grid-resolution"
            style={{
              fontSize: '0.75rem',
              color: '#6b7280',
              margin: '4px 0 8px',
              fontStyle: 'italic',
            }}
          >
            Results shown for nearest ~{result.grid_resolution_m} m grid cell
          </p>

          {/* Coverage Score */}
          <p style={labelStyle}>Coverage Score</p>
          <div
            data-testid="dragdrop-coverage-score"
            style={{ fontSize: '1.5rem', fontWeight: 700, color: '#111827', margin: '0 0 4px' }}
          >
            {result.coverage_score.toFixed(1)}
          </div>

          {/* Confidence Tag */}
          <p style={labelStyle}>Confidence</p>
          <span
            data-testid="dragdrop-confidence-tag"
            style={{
              display: 'inline-block',
              padding: '2px 10px',
              borderRadius: 12,
              background: CONFIDENCE_COLOUR[result.confidence_tag] + '1a',
              color: CONFIDENCE_COLOUR[result.confidence_tag],
              fontWeight: 700,
              fontSize: '0.82rem',
              border: `1px solid ${CONFIDENCE_COLOUR[result.confidence_tag]}40`,
            }}
          >
            {result.confidence_tag}
          </span>

          {/* Coverage ring placeholder */}
          <div
            data-testid="dragdrop-coverage-ring"
            aria-label="Terrain-deformed coverage ring for dropped position"
            style={{
              margin: '10px 0',
              height: 60,
              background: 'radial-gradient(circle, rgba(59,130,246,0.18) 0%, rgba(59,130,246,0.04) 70%, transparent 100%)',
              borderRadius: '50%',
              border: '2px dashed #93c5fd',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '0.72rem',
              color: '#6b7280',
            }}
          >
            Coverage ring (precomputed)
          </div>

          {/* Comparison vs. model top candidate (Req 6.3, 6.4) */}
          <p style={labelStyle}>vs. Model Top Candidate</p>
          <div
            data-testid="dragdrop-comparison"
            style={{
              background: '#f9fafb',
              borderRadius: 6,
              padding: '8px 10px',
              fontSize: '0.82rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ color: '#6b7280' }}>Your placement:</span>
              <span
                data-testid="dragdrop-manual-score"
                style={{ fontWeight: 700, color: '#111827' }}
              >
                {result.vs_top_candidate.manual_score.toFixed(1)}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ color: '#6b7280' }}>Model top candidate:</span>
              <span
                data-testid="dragdrop-model-score"
                style={{ fontWeight: 700, color: '#111827' }}
              >
                {result.vs_top_candidate.model_score.toFixed(1)}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ color: '#6b7280' }}>Top candidate location:</span>
              <span
                data-testid="dragdrop-top-candidate-coord"
                style={{ fontFamily: 'monospace', fontSize: '0.78rem', color: '#374151' }}
              >
                {result.vs_top_candidate.top_candidate_lat.toFixed(4)},{' '}
                {result.vs_top_candidate.top_candidate_lon.toFixed(4)}
              </span>
            </div>

            {/* Manual win indicator (Req 6.3, 6.4 — never suppressed) */}
            {result.vs_top_candidate.manual_wins && (
              <div
                data-testid="dragdrop-manual-wins"
                style={{
                  marginTop: 6,
                  padding: '5px 8px',
                  background: '#dcfce7',
                  borderRadius: 4,
                  color: '#15803d',
                  fontWeight: 600,
                  fontSize: '0.82rem',
                  border: '1px solid #86efac',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
                role="status"
                aria-label="Manual placement outperforms model recommendation"
              >
                <span aria-hidden="true">✓</span>
                Your placement outperforms the model recommendation
              </div>
            )}

            {/* Manual does not win */}
            {!result.vs_top_candidate.manual_wins && (
              <div
                data-testid="dragdrop-model-wins"
                style={{
                  marginTop: 6,
                  padding: '5px 8px',
                  background: '#eff6ff',
                  borderRadius: 4,
                  color: '#1d4ed8',
                  fontSize: '0.82rem',
                }}
              >
                Model top candidate scores higher at this time.
              </div>
            )}
          </div>

          {/* GeoAI label — required by Req 9.3 */}
          <p
            data-testid="dragdrop-geoai-label"
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
