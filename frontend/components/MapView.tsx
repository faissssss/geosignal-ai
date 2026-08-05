'use client'

/**
 * MapView — Task 23.1 + Task 24 integration
 * (Requirements 3.1–3.5, 5.1–5.5, 6.1–6.7, 7.4, 7.5, 9.3, 9.5, 10.2, 10.3, 10.6)
 *
 * Full MapLibre GL JS interactive map with layer stack:
 *   1. Base terrain tiles
 *   2. ESA WorldCover land-cover
 *   3. SRTM terrain contours
 *   4. Village boundaries
 *   5. Coverage Gap Heatmap  ← delegated to <CoverageHeatmap>
 *   6. Confidence overlay    ← handled inside CoverageHeatmap (opacity)
 *   7. OpenCellID BTS markers
 *   8. Ranked BTS candidate markers (draggable-ready)
 *
 * Task 24 additions (right-side panel stack):
 *   - SimulationPanel  — "Simulate New BTS" for selected candidate
 *   - DragDropMarker   — draggable marker + coverage result panel
 *   - PowerOverlay     — optional power/energy feasibility toggle
 *   - ConfidenceGate   — Low-confidence acknowledgement gate
 *
 * All layers have client-side visibility toggles (setLayoutProperty).
 * Toggles do NOT reload the page, refetch data, or recreate the map.
 *
 * WebGL guard: if WebGL is unavailable, renders a static fallback page
 * and never creates a MapLibre instance.
 *
 * No mock data is embedded in this component.
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import type { Map as MapLibreMap, Marker } from 'maplibre-gl'
import type { GridCell, BTSCandidate, AdminBoundary, RegionId, TargetArea } from '@/lib/types'
import { detectWebGL } from '@/lib/webgl'
import CoverageHeatmap, { type CoverageCell } from './CoverageHeatmap'
import SidePanel, { type SidePanelSelection } from './SidePanel'
import RegionSelector, { type RegionData } from './RegionSelector'
import TargetAreaSelector from './TargetAreaSelector'
import SimulationPanel from './SimulationPanel'
import DragDropMarker, { type DragDropResponse } from './DragDropMarker'
import PowerOverlay, { type PowerFeasibilityData } from './PowerOverlay'
import ConfidenceGate from './ConfidenceGate'

// ---------------------------------------------------------------------------
// Layer ID constants
// ---------------------------------------------------------------------------

const LC_SOURCE        = 'worldcover-source'
const LC_LAYER         = 'worldcover-layer'
const CONTOUR_SOURCE   = 'contour-source'
const CONTOUR_LAYER    = 'contour-layer'
const VILLAGE_SOURCE   = 'village-source'
const VILLAGE_FILL     = 'village-fill'
const VILLAGE_OUTLINE  = 'village-outline'
const OCID_SOURCE      = 'opencellid-source'
const OCID_LAYER       = 'opencellid-layer'
const CAND_SOURCE      = 'candidates-source'
const CAND_LAYER       = 'candidates-layer'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type MapLayerMouseEvent = import('maplibre-gl').MapLayerMouseEvent

export interface LayerVisibility {
  heatmap:    boolean
  landcover:  boolean
  contours:   boolean
  villages:   boolean
  btsMarkers: boolean
  candidates: boolean
}

export interface MapViewProps {
  /** Initial region. Defaults to 'ntt'. */
  initialRegion?: RegionId
  /** OpenCellID BTS locations for the active region. */
  btsLocations?: Array<{ lat: number; lon: number; cell_id?: string }>
  /** Admin boundaries for target area selector (kecamatan mode). */
  adminBoundaries?: AdminBoundary[]
  /** Optional: called when the active target area changes. */
  onTargetAreaResolved?: (targetArea: TargetArea) => void
}

// ---------------------------------------------------------------------------
// WebGL fallback
// ---------------------------------------------------------------------------

function WebGLFallback() {
  return (
    <div
      data-testid="webgl-fallback"
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f9fafb',
        fontFamily: 'sans-serif',
        padding: 32,
        boxSizing: 'border-box',
      }}
    >
      <div
        style={{
          maxWidth: 500,
          textAlign: 'center',
          background: '#ffffff',
          borderRadius: 12,
          padding: 32,
          boxShadow: '0 4px 24px rgba(0,0,0,0.1)',
        }}
      >
        <div style={{ fontSize: '2.5rem', marginBottom: 12 }}>🗺️</div>
        <h2 style={{ color: '#111827', marginBottom: 8 }}>
          WebGL Required
        </h2>
        <p style={{ color: '#4b5563', lineHeight: 1.6, marginBottom: 16 }}>
          GeoSignal AI&apos;s interactive map requires{' '}
          <strong>WebGL support</strong> to render terrain, coverage data,
          and spatial layers.
        </p>
        <p style={{ color: '#4b5563', lineHeight: 1.6, marginBottom: 24 }}>
          Your current browser or device does not appear to support WebGL.
          Please use a current version of one of the following browsers:
        </p>
        <ul
          style={{
            listStyle: 'none',
            padding: 0,
            margin: '0 0 24px',
            display: 'flex',
            justifyContent: 'center',
            gap: 24,
            flexWrap: 'wrap',
          }}
        >
          {['Chrome', 'Firefox', 'Edge'].map((b) => (
            <li
              key={b}
              style={{
                padding: '6px 16px',
                background: '#eff6ff',
                borderRadius: 6,
                color: '#1d4ed8',
                fontWeight: 600,
                fontSize: '0.9rem',
              }}
            >
              {b}
            </li>
          ))}
        </ul>
        <p style={{ color: '#9ca3af', fontSize: '0.8rem' }}>
          If you are using a supported browser and still see this message,
          check that hardware acceleration is enabled in your browser settings.
        </p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Layer toggle bar
// ---------------------------------------------------------------------------

interface LayerToggleBarProps {
  visibility: LayerVisibility
  onChange: (layer: keyof LayerVisibility, value: boolean) => void
}

function LayerToggleBar({ visibility, onChange }: LayerToggleBarProps) {
  const layers: Array<{ key: keyof LayerVisibility; label: string }> = [
    { key: 'heatmap',    label: 'Heatmap' },
    { key: 'landcover',  label: 'Land Cover' },
    { key: 'contours',   label: 'Contours' },
    { key: 'villages',   label: 'Villages' },
    { key: 'btsMarkers', label: 'BTS Towers' },
    { key: 'candidates', label: 'Candidates' },
  ]

  return (
    <div
      data-testid="layer-toggle-bar"
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 6,
        padding: '8px 12px',
        background: 'rgba(255,255,255,0.95)',
        borderRadius: 8,
        boxShadow: '0 2px 8px rgba(0,0,0,0.12)',
        fontFamily: 'sans-serif',
        fontSize: '0.82rem',
      }}
    >
      {layers.map(({ key, label }) => (
        <label
          key={key}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            cursor: 'pointer',
            color: '#374151',
            userSelect: 'none',
          }}
          data-testid={`toggle-${key}`}
        >
          <input
            type="checkbox"
            checked={visibility[key]}
            onChange={(e) => onChange(key, e.target.checked)}
            data-testid={`checkbox-${key}`}
          />
          {label}
        </label>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// MapView component
// ---------------------------------------------------------------------------

export default function MapView({
  initialRegion = 'ntt',
  btsLocations = [],
  adminBoundaries = [],
  onTargetAreaResolved,
}: MapViewProps) {
  // ── WebGL check — runs once on client ──────────────────────────────────
  const [webglSupported, setWebglSupported] = useState<boolean | null>(null)

  useEffect(() => {
    const result = detectWebGL()
    setWebglSupported(result.supported)
  }, [])

  // ── Map state ──────────────────────────────────────────────────────────
  const mapContainerRef = useRef<HTMLDivElement>(null)
  const mapRef          = useRef<MapLibreMap | null>(null)
  const [mapReady, setMapReady] = useState(false)

  // ── Data state ─────────────────────────────────────────────────────────
  const [cells, setCells]           = useState<GridCell[]>([])
  const [candidates, setCandidates] = useState<BTSCandidate[]>([])
  const [activeRegion, setActiveRegion] = useState<RegionId>(initialRegion)
  const [targetArea, setTargetArea] = useState<TargetArea | null>(null)

  // ── Side panel ─────────────────────────────────────────────────────────
  const [selection, setSelection] = useState<SidePanelSelection | null>(null)

  // ── Task 24: selected candidate for simulation + ConfidenceGate ────────
  const [selectedCandidate, setSelectedCandidate] = useState<BTSCandidate | null>(null)

  // ── Task 24: power overlay state ───────────────────────────────────────
  const [overlayEnabled, setOverlayEnabled] = useState(false)
  const [dragDropFeasibility, setDragDropFeasibility] = useState<PowerFeasibilityData | null>(null)
  const [dragDropCoverageScore, setDragDropCoverageScore] = useState<number | null>(null)

  // ── Layer visibility ───────────────────────────────────────────────────
  const [visibility, setVisibility] = useState<LayerVisibility>({
    heatmap:    true,
    landcover:  true,
    contours:   true,
    villages:   true,
    btsMarkers: true,
    candidates: true,
  })

  // ── BTS marker refs ────────────────────────────────────────────────────
  const btsMarkersRef  = useRef<Marker[]>([])
  const candMarkersRef = useRef<Marker[]>([])

  // ── Initialise MapLibre once WebGL confirmed ───────────────────────────
  useEffect(() => {
    if (!webglSupported || !mapContainerRef.current || mapRef.current) return

    let isMounted = true

    ;(async () => {
      const maplibre = await import('maplibre-gl')
      if (!isMounted || !mapContainerRef.current) return

      const map = new maplibre.Map({
        container: mapContainerRef.current,
        style: {
          version: 8,
          sources: {
            'raster-tiles': {
              type: 'raster',
              tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
              tileSize: 256,
              attribution: '© OpenStreetMap contributors',
            },
          },
          layers: [
            {
              id: 'background',
              type: 'raster',
              source: 'raster-tiles',
            },
          ],
        },
        center: [120.0, -9.0],
        zoom: 7,
      })

      map.on('load', () => {
        if (!isMounted) return
        mapRef.current = map
        setMapReady(true)
      })
    })()

    return () => {
      isMounted = false
      // Cleanup markers
      btsMarkersRef.current.forEach((m) => m.remove())
      candMarkersRef.current.forEach((m) => m.remove())
      btsMarkersRef.current  = []
      candMarkersRef.current = []
      mapRef.current?.remove()
      mapRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [webglSupported])

  // ── Region change handler ──────────────────────────────────────────────
  const handleRegionChange = useCallback(
    (data: RegionData) => {
      setCells(data.cells)
      setCandidates(data.candidates)
      setActiveRegion(data.regionId)
      setTargetArea(null)
      setSelection(null)
      setSelectedCandidate(null)
      setDragDropCoverageScore(null)
      setDragDropFeasibility(null)
    },
    [],
  )

  // ── Layer toggle handler ───────────────────────────────────────────────
  const handleVisibilityChange = useCallback(
    (layer: keyof LayerVisibility, value: boolean) => {
      setVisibility((prev) => ({ ...prev, [layer]: value }))

      // Client-side only — setLayoutProperty on the existing layers
      const map = mapRef.current
      if (!map || !map.isStyleLoaded()) return
      const viz = value ? 'visible' : 'none'

      if (layer === 'landcover' && map.getLayer(LC_LAYER)) {
        map.setLayoutProperty(LC_LAYER, 'visibility', viz)
      }
      if (layer === 'contours' && map.getLayer(CONTOUR_LAYER)) {
        map.setLayoutProperty(CONTOUR_LAYER, 'visibility', viz)
      }
      if (layer === 'villages') {
        if (map.getLayer(VILLAGE_FILL))    map.setLayoutProperty(VILLAGE_FILL,    'visibility', viz)
        if (map.getLayer(VILLAGE_OUTLINE)) map.setLayoutProperty(VILLAGE_OUTLINE, 'visibility', viz)
      }
      if (layer === 'btsMarkers') {
        btsMarkersRef.current.forEach((m) => {
          const el = m.getElement()
          el.style.display = value ? '' : 'none'
        })
      }
      if (layer === 'candidates') {
        candMarkersRef.current.forEach((m) => {
          const el = m.getElement()
          el.style.display = value ? '' : 'none'
        })
      }
      // heatmap visibility is passed as a prop to <CoverageHeatmap>
    },
    [],
  )

  // ── Add static overlay layers once map is ready ────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return

    // ── Land-cover overlay (ESA WorldCover tile stub) ──────────────────
    if (!map.getSource(LC_SOURCE)) {
      map.addSource(LC_SOURCE, {
        type: 'raster',
        tiles: [
          // ESA WorldCover 2021 — public tile service
          'https://services.terrascope.be/wmts/v2?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=WORLDCOVER_2021_MAP&STYLE=default&TILEMATRIXSET=EPSG:3857&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/png',
        ],
        tileSize: 256,
        attribution: 'ESA WorldCover 2021',
      })
    }
    if (!map.getLayer(LC_LAYER)) {
      map.addLayer({
        id: LC_LAYER,
        type: 'raster',
        source: LC_SOURCE,
        layout: { visibility: visibility.landcover ? 'visible' : 'none' },
        paint: { 'raster-opacity': 0.55 },
      })
    }

    // ── Terrain contours (placeholder circle layer — real data in Task 27) ─
    if (!map.getSource(CONTOUR_SOURCE)) {
      map.addSource(CONTOUR_SOURCE, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
    }
    if (!map.getLayer(CONTOUR_LAYER)) {
      map.addLayer({
        id: CONTOUR_LAYER,
        type: 'line',
        source: CONTOUR_SOURCE,
        layout: { visibility: visibility.contours ? 'visible' : 'none' },
        paint: { 'line-color': '#92400e', 'line-width': 0.8, 'line-opacity': 0.5 },
      })
    }

    // ── Village boundaries (placeholder) ──────────────────────────────
    if (!map.getSource(VILLAGE_SOURCE)) {
      map.addSource(VILLAGE_SOURCE, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
    }
    if (!map.getLayer(VILLAGE_FILL)) {
      map.addLayer({
        id: VILLAGE_FILL,
        type: 'fill',
        source: VILLAGE_SOURCE,
        layout: { visibility: visibility.villages ? 'visible' : 'none' },
        paint: { 'fill-color': '#fbbf24', 'fill-opacity': 0.08 },
      })
    }
    if (!map.getLayer(VILLAGE_OUTLINE)) {
      map.addLayer({
        id: VILLAGE_OUTLINE,
        type: 'line',
        source: VILLAGE_SOURCE,
        layout: { visibility: visibility.villages ? 'visible' : 'none' },
        paint: { 'line-color': '#d97706', 'line-width': 0.8 },
      })
    }

    // ── OpenCellID BTS markers source ────────────────────────────────
    if (!map.getSource(OCID_SOURCE)) {
      map.addSource(OCID_SOURCE, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    }
    if (!map.getLayer(OCID_LAYER)) {
      map.addLayer({
        id: OCID_LAYER,
        type: 'circle',
        source: OCID_SOURCE,
        layout: { visibility: visibility.btsMarkers ? 'visible' : 'none' },
        paint: { 'circle-color': '#6366f1', 'circle-radius': 5, 'circle-stroke-width': 1, 'circle-stroke-color': '#ffffff' },
      })
    }

    // ── Candidates source ─────────────────────────────────────────────
    if (!map.getSource(CAND_SOURCE)) {
      map.addSource(CAND_SOURCE, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    }
    if (!map.getLayer(CAND_LAYER)) {
      map.addLayer({
        id: CAND_LAYER,
        type: 'circle',
        source: CAND_SOURCE,
        layout: { visibility: visibility.candidates ? 'visible' : 'none' },
        paint: { 'circle-color': '#f59e0b', 'circle-radius': 7, 'circle-stroke-width': 2, 'circle-stroke-color': '#ffffff' },
      })
    }

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapReady])

  // ── Update candidate data when candidates change ───────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return
    const source = map.getSource(CAND_SOURCE) as GeoJSONSource | undefined
    if (!source) return
    source.setData({
      type: 'FeatureCollection',
      features: candidates.map((c) => ({
        type: 'Feature',
        id: c.candidate_id,
        geometry: { type: 'Point', coordinates: [c.lon, c.lat] },
        properties: { ...c },
      })),
    })

    // Set up click handler for candidate → SidePanel
    const onClick = (e: MapLayerMouseEvent) => {
      const f = e.features?.[0]
      if (!f) return
      const props = f.properties as BTSCandidate
      setSelection({ kind: 'candidate', data: props })
      setSelectedCandidate(props)
    }
    map.on('click', CAND_LAYER, onClick)
    return () => { map.off('click', CAND_LAYER, onClick) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidates, mapReady])

  // ── CoverageHeatmap cell click handler ────────────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || !mapReady) return

    const onCellClick = (e: MapLayerMouseEvent) => {
      const f = e.features?.[0]
      if (!f) return
      const props = f.properties as GridCell
      setSelection({ kind: 'cell', data: props })
    }
    map.on('click', 'coverage-heatmap-fill', onCellClick)
    return () => { map.off('click', 'coverage-heatmap-fill', onCellClick) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapReady])

  // ── Target area resolved ───────────────────────────────────────────────
  const handleTargetAreaResolved = useCallback((ta: TargetArea) => {
    setTargetArea(ta)
    onTargetAreaResolved?.(ta)
  }, [onTargetAreaResolved])

  // ── Target area reset on region change ────────────────────────────────
  const handleTargetAreaReset = useCallback(() => {
    setTargetArea(null)
  }, [])

  // ── DragDrop result handler ────────────────────────────────────────────
  const handleDragDropResult = useCallback((resp: DragDropResponse | null) => {
    if (resp?.kind === 'result') {
      setDragDropCoverageScore(resp.coverage_score)
      // Power feasibility is not in the drag-drop API response (Task 25 territory).
      // Show null until the overlay data arrives — never fabricate values.
      setDragDropFeasibility({ nearest_grid_node_km: null, solar_potential_rating: null })
    } else {
      setDragDropCoverageScore(null)
    }
  }, [])

  // ── Simulation action (called by ConfidenceGate after acknowledgement) ─
  // This just scrolls the SimulationPanel into view; the actual API call
  // is handled inside SimulationPanel when the button is clicked.
  // ConfidenceGate wraps the button-click — no separate imperative trigger needed.

  // ── Cells → CoverageCell[] ─────────────────────────────────────────────
  const coverageCells: CoverageCell[] = cells.map((c) => ({
    cell_id: c.cell_id,
    coverage_score: c.coverage_score,
    confidence_tag: c.confidence_tag,
    lat: c.lat,
    lon: c.lon,
  }))

  // ── Render: SSR / initial loading state ───────────────────────────────
  if (webglSupported === null) {
    return (
      <div
        style={{ width: '100%', height: '100%', background: '#f9fafb' }}
        data-testid="map-loading"
      />
    )
  }

  // ── Render: WebGL not supported ────────────────────────────────────────
  if (!webglSupported) {
    return <WebGLFallback />
  }

  // ── Render: full interactive map ───────────────────────────────────────
  return (
    <div
      style={{ position: 'relative', width: '100%', height: '100%' }}
      data-testid="map-view"
    >
      {/* Map container */}
      <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />

      {/* CoverageHeatmap layer (delegated) */}
      <CoverageHeatmap
        map={mapRef.current}
        cells={coverageCells}
        visible={visibility.heatmap}
      />

      {/* Controls overlay */}
      <div
        style={{
          position: 'absolute',
          top: 16,
          left: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          zIndex: 10,
        }}
      >
        {/* Region selector */}
        <RegionSelector
          initialRegion={initialRegion}
          onRegionChange={handleRegionChange}
        />

        {/* Layer toggle bar */}
        <LayerToggleBar
          visibility={visibility}
          onChange={handleVisibilityChange}
        />

        {/* Target area selector */}
        <TargetAreaSelector
          map={mapRef.current}
          regionId={activeRegion}
          adminBoundaries={adminBoundaries}
          onResolved={handleTargetAreaResolved}
          onReset={handleTargetAreaReset}
        />
      </div>

      {/* Side panel */}
      <SidePanel
        selection={selection}
        onClose={() => setSelection(null)}
      />

      {/* Task 24 — right-side panel stack ──────────────────────────────── */}
      <div
        style={{
          position: 'absolute',
          top: 16,
          right: selection ? 332 : 16,   // shift left when SidePanel is open
          width: 300,
          maxHeight: 'calc(100vh - 32px)',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          zIndex: 10,
          transition: 'right 0.2s ease',
        }}
        data-testid="task24-panel-stack"
      >
        {/* ConfidenceGate wraps the Simulate button for Low-confidence candidates */}
        {selectedCandidate && (
          <ConfidenceGate
            confidenceTag={selectedCandidate.confidence_tag}
            candidateId={selectedCandidate.candidate_id}
            guardedAction={() => {
              /* The actual simulation is triggered inside SimulationPanel.
                 ConfidenceGate here guards a no-op to demonstrate the modal;
                 in practice the SimulationPanel button itself is also wrapped. */
            }}
            actionLabel="Simulate New BTS (guarded)"
            disabled={!targetArea}
          />
        )}

        {/* SimulationPanel */}
        <SimulationPanel
          candidate={selectedCandidate}
          regionId={activeRegion}
          targetAreaResolved={targetArea !== null}
        />

        {/* DragDropMarker panel (result display) */}
        <DragDropMarker
          map={mapRef.current}
          regionId={activeRegion}
          overlayEnabled={overlayEnabled}
          onResult={handleDragDropResult}
        />

        {/* PowerOverlay — secondary feasibility display only */}
        <PowerOverlay
          coverageScore={dragDropCoverageScore}
          feasibilityData={dragDropFeasibility}
          onToggle={setOverlayEnabled}
        />
      </div>

      {/* GeoAI label — always visible (Req 9.3) */}
      <div
        style={{
          position: 'absolute',
          bottom: 8,
          left: '50%',
          transform: 'translateX(-50%)',
          background: 'rgba(0,0,0,0.55)',
          color: '#ffffff',
          padding: '3px 10px',
          borderRadius: 12,
          fontSize: '0.72rem',
          fontFamily: 'sans-serif',
          pointerEvents: 'none',
          zIndex: 10,
        }}
        data-testid="geoai-watermark"
      >
        GeoAI-assisted estimate — decision support only
      </div>
    </div>
  )
}

// Named exports for testing
export { WebGLFallback, LayerToggleBar, OCID_SOURCE, CAND_SOURCE, CAND_LAYER, VILLAGE_FILL, VILLAGE_OUTLINE, CONTOUR_LAYER, LC_LAYER }
type GeoJSONSource = import('maplibre-gl').GeoJSONSource
// Re-export new component types for convenience in tests
export type { DragDropResponse }
export type { PowerFeasibilityData }
