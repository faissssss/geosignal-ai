// GeoSignal AI — TypeScript types mirroring backend/geosignal/models.py

export type ConfidenceLevel = 'Low' | 'Med' | 'High'
export type ModelTier = '1' | '2'
export type SelectionMethod = 'drawn_polygon' | 'kecamatan'
export type DataSourceKind = 'demo' | 'real' | 'derived' | 'unavailable'

export interface ShapEntry {
  feature_name: string
  value: number
  direction: 'positive' | 'negative'
}

export interface GridCell {
  cell_id: string
  region_id: string
  lat: number
  lon: number
  resolution_m: number
  coverage_score: number
  confidence_tag: ConfidenceLevel
  tier_used: ModelTier
  shap_top3: ShapEntry[]
  model_version: string
  scoring_run_id: string
  /** ISO 8601 timestamp from the scoring run. Undefined when not yet available. */
  scoring_run_timestamp?: string
}

export interface BTSCandidate {
  candidate_id: string
  region_id: string
  target_area_id: string
  rank: number
  lat: number
  lon: number
  expected_improvement: number
  los_validated: boolean
  confidence_tag: ConfidenceLevel
  shap_values: Record<string, number>
  model_version: string
  scoring_run_id: string
  /** ISO 8601 timestamp from the scoring run. Undefined when not yet available. */
  scoring_run_timestamp?: string
  excluded_by_canopy: boolean
}

export interface AdminBoundary {
  boundary_id: string
  kecamatan_id: string
  kecamatan_name: string
  region_id: string
  boundary_geojson: object
}

export interface TargetArea {
  target_area_id: string
  region_id: string
  selection_method: SelectionMethod
  kecamatan_id: string | null
  boundary_geojson: object
  created_at: string
}

export interface ComparisonPanel {
  manual_score: number
  model_score: number
  top_candidate_id: string
  top_candidate_lat: number
  top_candidate_lon: number
  manual_wins: boolean
}

export interface SimulationResult {
  before_heatmap: object
  after_heatmap: object
  pct_good_change: number
  villages_newly_covered: number
  new_coverage_score: number
  elapsed_ms: number
}

export interface UnavailableScenario {
  unavailable: true
  candidate_id: string
  region_id: string
  message: string
}

export interface DragDropResult {
  snapped_coordinate: [number, number]
  grid_resolution_m: number
  coverage_score: number
  confidence_tag: ConfidenceLevel
  vs_top_candidate: ComparisonPanel
  elapsed_ms: number
}

export interface OutsideExtentError {
  outside_extent: true
  dropped_lat: number
  dropped_lon: number
  region_id: string
  message: string
}

// ---------------------------------------------------------------------------
// Data Production — supporting map layers (Phase 4/5, data-production/plan.md)
// Each row is region-scoped and carries an explicit data_source so the UI can
// distinguish real / derived / demo / unavailable without inventing values.
// ---------------------------------------------------------------------------

/** browser-efficient GEE-published land-cover tile set metadata */
export interface LandCoverTileSet {
  set_id: string
  region_id: string
  layer_id: string
  tiles_url: string | null
  attribution: string | null
  status: DataSourceKind
  data_source: DataSourceKind
  created_at: string
}

/** SRTM-derived contour LineString feature */
export interface ContourFeature {
  feature_id: string
  region_id: string
  kecamatan_id: string | null
  elevation_m: number
  geom_geojson: object
  status: DataSourceKind
  data_source: DataSourceKind
}

/** approved OSM / government village Polygon feature */
export interface VillageFeature {
  feature_id: string
  region_id: string
  kecamatan_id: string | null
  village_name: string | null
  attribution: string | null
  geom_geojson: object
  status: DataSourceKind
  data_source: DataSourceKind
}

/** OpenCellID BTS tower point */
export interface BTSLocation {
  tower_id: string
  region_id: string
  lat: number
  lon: number
  mcc: number | null
  mnc: number | null
  lac: number | null
  cell: number | null
  status: DataSourceKind
  data_source: DataSourceKind
}

// Region IDs for the three MVP/validation regions
export type RegionId = 'ntt' | 'ntb' | 'central_kalimantan'

export const REGIONS: { id: RegionId; label: string }[] = [
  { id: 'ntt', label: 'NTT Province (MVP)' },
  { id: 'ntb', label: 'NTB Province (Validation)' },
  { id: 'central_kalimantan', label: 'Central Kalimantan (Validation)' },
]

// ---------------------------------------------------------------------------
// Layer visibility state (shared by LayerToggleBar and LayersButton)
// ---------------------------------------------------------------------------

export interface LayerVisibility {
  heatmap:    boolean
  landcover:  boolean
  contours:   boolean
  villages:   boolean
  btsMarkers: boolean
  candidates: boolean
}
