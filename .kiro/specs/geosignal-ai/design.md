# Design Document — GeoSignal AI

## Overview

GeoSignal AI is a GeoAI-assisted decision-support system for detecting cellular coverage
gaps and recommending optimal BTS (Base Transceiver Station) placement sites in
Indonesia's 3T regions. The system fuses multi-source geospatial data to answer:
*"Can people in this location actually receive a usable signal?"*

### Design Goals

- Provide reliable Coverage Scores (0–100) for every grid cell in a target region using a
  two-tier model (AHP cold-start + XGBoost/LightGBM trained on Ookla ground truth).
- Surface ranked BTS placement candidates with SHAP explainability and Low/Med/High
  confidence tags.
- Enable Before/After and Drag-and-Drop coverage simulations via precomputed what-if
  grids (no live DEM recomputation at demo time).
- Uphold ethical safeguards: equity weighting, deforestation constraints, Low-confidence
  acknowledgement gates, and a maintained Ethical Risk Register.
- Stay within hackathon compute and latency budgets while establishing a scalable
  architecture pathway to national coverage.

### Out of Scope (MVP)

- Live RF signal propagation modelling (Okumura-Hata or similar commercial tools).
- Real-time crowd-sourced signal ingestion.
- Full Papua/Maluku province coverage (Phase 3 target).
- Operator-grade spectrum planning or frequency coordination.

---

## Architecture

### System Context

```
┌─────────────────────────────────────────────────────────────────────┐
│                         External Data Sources                       │
│  SRTM DEM · ESA WorldCover · OpenGeoAI Canopy · OpenCellID         │
│  OSM Roads/POI · WorldPop · Ookla Open Data                        │
└────────────────────────┬────────────────────────────────────────────┘
                         │ (scheduled GEE export)
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  Step 0 — Data_Pipeline (GEE + Python)              │
│  • Geometry QC (invalid / null feature repair or removal)           │
│  • Attribute range validation (elevation, pop-density bounds)       │
│  • Multi-resolution raster harmonisation (MAUP grid resolution)     │
│  • Data quality report export (record counts, checksums)            │
│  • Province-parameterised: same code, new boundary file per region  │
└────────────────────────┬────────────────────────────────────────────┘
                         │
          ┌──────────────┴──────────────┐
          │                             │
          ▼                             ▼
┌──────────────────┐         ┌──────────────────────────────────────┐
│ Tier 1 — AHP     │         │ Tier 2 — XGBoost / LightGBM          │
│ (cold-start)     │         │ (trained against Ookla ground truth) │
│ Used when no     │         │ Used when Ookla tiles available      │
│ Ookla tiles      │         │ Spatially-blocked CV by kecamatan    │
│ exist for a      │         │                                      │
│ kecamatan        │         │                                      │
└────────┬─────────┘         └──────────────────┬───────────────────┘
         └──────────────┬───────────────────────┘
                        │  Coverage Score (0–100) per grid cell
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│               Recommendation_Engine (Python)                        │
│  • BallTree candidate search → ranked BTS coordinates              │
│  • DEM-based LOS validation (precomputed)                           │
│  • SHAP value computation (both tiers)                              │
│  • Confidence_Tagger (OpenCellID + Ookla proximity thresholds)     │
│  • Ethical constraints (equity weighting, canopy exclusion)        │
│  • Model versioning + scoring run log                               │
└────────────────────────┬────────────────────────────────────────────┘
                         │ Precomputed outputs stored in Supabase
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│             Simulation_Engine (Python / Next.js API routes)         │
│  • Before/After heatmap lookup from precomputed what-if grid       │
│  • Drag-and-Drop: snap to nearest precomputed grid cell            │
│  • Metric delta computation (% Good cells, village count change)   │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│              Interactive_Map — Next.js + MapLibre + Supabase        │
│  • Coverage Gap Heatmap (Green/Yellow/Red + confidence overlay)    │
│  • Layer toggles (BTS, villages, contours, land cover, heatmap)    │
│  • Side panel: Coverage Score, Confidence Tag, SHAP top-3          │
│  • Simulation controls (Simulate New BTS, Drag-and-Drop)           │
│  • Region selector (Kupang MVP, NTB/Bima, Lamandau validation)     │
│  • Target-area selector (draw polygon / kecamatan dropdown)        │
│  • Low-confidence acknowledgement gate                              │
└─────────────────────────────────────────────────────────────────────┘
```

### Deployment Overview

| Layer | Technology | Notes |
|---|---|---|
| Geospatial fusion | Google Earth Engine | Scheduled batch export; not real-time |
| Modelling | Python 3.11+ | XGBoost, LightGBM, scikit-learn BallTree, SHAP |
| Backend API | Next.js API routes | Thin REST layer; business logic lives in Python |
| Database / Storage | Supabase (PostgreSQL + Storage) | Grid tiles, model artifacts, scoring logs |
| Frontend map | Next.js + MapLibre GL JS | WebGL-based tile rendering |
| Containerisation | Docker | One container per province pipeline step |
| Distributed compute (Phase 3) | Spark / Dask adapter | Abstracted behind model adapter layer |

---

## Components and Interfaces

### 1. Data_Pipeline

**Responsibility:** Ingest, validate, harmonise, and export all geospatial inputs.

**Key interfaces:**
```python
def run_pipeline(
    region_boundary: GeoJSON,        # Province/kabupaten boundary file
    resolution_variants: list[int],  # ≥2 grid sizes for MAUP testing, e.g. [100, 250]
    output_bucket: str,              # GCS / Supabase Storage path
) -> DataQualityReport

@dataclass
class DataQualityReport:
    region_id: str
    input_record_counts: dict[str, int]   # per data source
    removed_records: dict[str, int]
    repaired_records: dict[str, int]
    anomalous_records: dict[str, int]
    chosen_resolution_m: int
    confidence_thresholds: ConfidenceThresholds  # stored here; not hard-coded
    dataset_checksums: dict[str, str]
    timestamp: datetime
```

**Geometry QC rules:**
- Remove features with null or empty geometries.
- Repair self-intersecting polygons via `buffer(0)` with fallback to removal.
- Log each corrected record (source, feature ID, action taken).

**Attribute range rules (configurable per source, Indonesia-scoped):**
- Elevation: valid range −11 m (Java coastal lowland/reclaimed land floor) to 4 884 m
  (Puncak Jaya, Papua — Indonesia's highest point). Flag values outside this range;
  note the upper bound is Indonesia-specific and deliberately tighter than a global
  DEM bound (e.g. Everest's ~8,850 m) so implausible values for this country are
  actually caught rather than silently passing.
- Population density: flag values > 1 000 000 per km².
- Canopy height: flag values < 0 or > 100 m.

**Multi-resolution harmonisation:**
All source rasters are resampled to the analysis grid via bilinear interpolation (continuous
fields: elevation, slope, canopy height, population) or nearest-neighbour (categorical:
land-cover class). The pipeline produces outputs at ≥2 resolutions (e.g., 100 m and 250 m)
before the final resolution is selected.

---

### 2. Recommendation_Engine

**Responsibility:** Compute Coverage Scores, rank BTS candidates, attach SHAP values and
confidence tags, enforce ethical constraints, log every scoring run.

**Coverage Score computation:**

```python
CONSOLIDATED_FEATURES = [
    "elevation_m",
    "slope_deg",
    "land_cover_class",   # ESA WorldCover integer code
    "canopy_height_m",    # kept separate from land_cover_class — never merged
    "distance_to_bts_m",
    "road_distance_m",
    "population_density_per_km2",
    "facility_proximity_m",
]
# Ookla is NOT in this list — it is the Tier 2 training label only.

def compute_coverage_score(
    features: FeatureVector,
    model: Union[AHPModel, GBMModel],
) -> float:   # returns 0.0 – 100.0
    ...

def select_tier(kecamatan_id: str, ookla_tile_count: int) -> ModelTier:
    """Return Tier1 (AHP) if ookla_tile_count == 0, else Tier2 (XGBoost/LightGBM)."""
    ...
```

**Deforestation / canopy exclusion constraint:**

The exclusion rule filters on **both** `land_cover_class` and `canopy_height_m` — these
were deliberately kept as two separate features (see `CONSOLIDATED_FEATURES` above)
precisely so a categorical land-cover label ("forest") and a continuous canopy height
("this specific cell has 34 m of vertical canopy") can both gate candidate selection.
Land-cover class alone cannot distinguish a low-scrub "forest" pixel from a tall closed-
canopy pixel of the same class code, and canopy height alone cannot distinguish
plantation forest (generally a lower deforestation-risk siting choice) from primary/dense
forest of similar height. Both signals are required together:

```python
# ESA WorldCover class codes treated as forest/tree-cover for this constraint.
# 10 = Tree cover, 20 = Shrubland (included only when canopy_height_m confirms
# tall woody cover is actually present at that cell — shrubland alone is not excluded).
HIGH_CANOPY_LAND_COVER_CLASSES = {10, 20}

# Height threshold above which a candidate site is treated as requiring meaningful
# clearing to install a BTS + access road. Derived from typical secondary-growth
# canopy height in Indonesian forest-monitoring literature; configurable per region.
CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M = 15.0

def is_high_canopy(land_cover_class: int, canopy_height_m: float) -> bool:
    """
    A candidate site is excluded by the deforestation constraint if BOTH:
      1. land_cover_class is in HIGH_CANOPY_LAND_COVER_CLASSES, AND
      2. canopy_height_m >= CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M

    This two-factor check is intentional: land-cover class alone over-excludes
    (e.g., low shrubland classified under the same code as tall forest), and canopy
    height alone under-excludes (a tall isolated tree in a non-forest cell would
    incorrectly block an otherwise-fine candidate). Both features must agree.
    """
    return (
        land_cover_class in HIGH_CANOPY_LAND_COVER_CLASSES
        and canopy_height_m >= CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M
    )
```

**BallTree candidate search:**

```python
def rank_bts_candidates(
    grid_cells: np.ndarray,          # (N, 2) lat/lon array, pre-filtered to the
                                      # Planner's target area (see TargetArea below)
    coverage_scores: np.ndarray,     # (N,) current scores
    land_cover_classes: np.ndarray,  # (N,) ESA WorldCover codes, aligned to grid_cells
    canopy_heights_m: np.ndarray,    # (N,) canopy height, aligned to grid_cells
    n_candidates: int = 10,          # must return ≥ 2 when any valid candidates exist
    exclude_high_canopy: bool = True, # applies is_high_canopy() using BOTH arrays above
) -> list[BTSCandidate] | InsufficientCandidatesResult

@dataclass
class BTSCandidate:
    coordinate: tuple[float, float]  # (lat, lon)
    expected_improvement: float      # mean delta Coverage Score in radius
    los_validated: bool              # from precomputed DEM LOS grid; never None —
                                      # a candidate without a precomputed LOS result
                                      # is not emitted as a BTSCandidate at all (see
                                      # Error Handling)
    confidence_tag: ConfidenceLevel  # Low / Med / High
    shap_values: dict[str, float]    # feature → SHAP contribution
    rank: int
    model_version: str
    scoring_run_id: str

@dataclass
class InsufficientCandidatesResult:
    """Returned instead of a list when fewer than 2 candidates survive filtering."""
    surviving_count: int             # 0 or 1
    reason: str                      # e.g. "all candidates excluded by canopy constraint"
    target_area_id: str
```

**Target area specification:**

Every call to `rank_bts_candidates` and every Before/After simulation request
(`simulate_bts_placement`) operates on a `TargetArea`, which is how the Interactive_Map's
Planner-facing selection (Requirement 10.7) is translated into the `grid_cells` array
consumed by the backend:

```python
@dataclass
class TargetArea:
    target_area_id: str
    region_id: str                     # e.g. "ntt_kupang"
    selection_method: Literal["drawn_polygon", "kecamatan"]
    boundary: GeoJSON                  # drawn polygon geometry, OR the selected
                                        # kecamatan's boundary geometry looked up
                                        # from GADM Level 2
    kecamatan_id: str | None           # populated only when selection_method ==
                                        # "kecamatan"

def resolve_target_area(
    region_id: str,
    selection_method: Literal["drawn_polygon", "kecamatan"],
    payload: GeoJSON | str,   # drawn polygon GeoJSON, or a kecamatan_id string
) -> TargetArea:
    """
    Called by the Next.js API route backing the map's target-area selector
    (Requirement 10.7/10.8) before any recommendation or simulation request.
    Resolves a kecamatan_id to its GADM Level 2 boundary, or accepts a drawn
    polygon directly. The resulting TargetArea.boundary is what filters
    grid_cells before rank_bts_candidates or simulate_bts_placement runs.
    """
    ...
```

**Model adapter layer (Phase 3 extensibility):**

```python
class ScoringAdapter(Protocol):
    def predict(self, features: np.ndarray) -> np.ndarray: ...
    def shap_values(self, features: np.ndarray) -> np.ndarray: ...

# Concrete implementations: AHPAdapter, XGBoostAdapter, LightGBMAdapter, GNNAdapter (future)
```

**Spatially-blocked cross-validation:**

```python
def spatial_cv(
    data: GeoDataFrame,
    kecamatan_column: str,
    model_cls: type,
    n_folds: int,
) -> CVResult:
    """Hold out entire kecamatan units as test blocks — never random point split."""
    ...
```

**SHAP for Tier 1 (AHP):**

AHP does not produce native SHAP values. For Tier 1, SHAP is computed by treating the
normalised AHP weight vector as a linear model; each feature's SHAP value equals
`weight_i × (feature_value_i − baseline_i)`. This ensures explainability is available
in all regions regardless of data availability.

**Baseline definition:** `baseline_i` is the **regional mean of feature `i` across all
scored grid cells within the same `region_id`** (e.g., all Kupang cells, computed once
per scoring run and cached for that run's duration), not a national mean and not a
per-kecamatan mean. This choice is deliberate:
- A per-cell or per-kecamatan baseline would make SHAP values incomparable between
  neighbouring cells within the same region, defeating the purpose of "why is this cell
  worse than that one" explanations.
- A national baseline would dilute the comparison for regions with systematically
  different terrain profiles (e.g., Lamandau's canopy-driven scores vs. NTT's
  elevation-driven scores), making cross-region SHAP values misleading if compared.
- The regional mean is recomputed and versioned alongside each scoring run (stored in
  `scoring_runs.input_checksums` metadata) so a stale baseline is never silently reused
  across runs with different input data.

```python
def compute_ahp_shap(
    feature_vector: FeatureVector,
    weights: dict[str, float],           # normalised AHP weight per feature
    regional_baseline: dict[str, float],  # baseline_i per feature, this region+run
) -> dict[str, float]:
    return {
        feature: weights[feature] * (getattr(feature_vector, feature) - regional_baseline[feature])
        for feature in CONSOLIDATED_FEATURES
    }
```

**Scoring run log (Supabase `scoring_runs` table):**

| Column | Type | Description |
|---|---|---|
| run_id | UUID | Unique identifier for the run |
| model_version | VARCHAR | Semantic version of the model artifact |
| tier | ENUM(1,2) | AHP or XGBoost/LightGBM |
| region_kecamatans | TEXT[] | Array of kecamatan IDs scored |
| resolution_m | INT | Grid resolution used |
| input_checksums | JSONB | Per-source SHA-256 checksums; also stores the AHP
  regional feature-mean baseline used for that run's SHAP computation |
| candidate_count | INT | Number of BTS candidates evaluated |
| timestamp | TIMESTAMPTZ | UTC timestamp |
| retained_for_months | INT | Default 12 |

---

### 3. Confidence_Tagger

**Responsibility:** Assign Low/Med/High confidence tags using OpenCellID and Ookla
proximity, consistently across heatmap cells, BTS candidates, and Drag-and-Drop outputs.

There is exactly **one** `ConfidenceThresholds` definition in this system — see
[Confidence Thresholds](#confidence-thresholds-canonical-definition) in the Data Models
section below. It is imported here, not redefined:

```python
from geosignal.models import ConfidenceThresholds  # single canonical definition

def tag_confidence(
    point: tuple[float, float],
    nearest_opencellid_km: float,
    nearest_ookla_km: float,
    thresholds: ConfidenceThresholds,
) -> ConfidenceLevel:
    """
    High  : nearest_opencellid_km < thresholds.high_km
              AND nearest_ookla_km < thresholds.high_km
    Med   : (nearest_opencellid_km < thresholds.high_km
               OR nearest_ookla_km < thresholds.high_km)
              but not both; OR (thresholds.high_km ≤ both ≤ thresholds.low_km)
    Low   : nearest_opencellid_km > thresholds.low_km
              AND nearest_ookla_km > thresholds.low_km
              OR either record absent within thresholds.low_km
    Absence of record ≠ confirmed zero coverage.
    """
    ...
```

Thresholds are stored in the `DataQualityReport` (Requirement 1.5) so they can be
reviewed and adjusted per region without touching application code.

---

### 4. Simulation_Engine

**Responsibility:** Serve Before/After and Drag-and-Drop simulation results from
precomputed what-if grids. Never performs live DEM recomputation.

```python
def simulate_bts_placement(
    candidate_id: str,
    region_id: str,
) -> SimulationResult | UnavailableScenario:
    """
    Looks up precomputed what-if grid for (candidate_id, region_id).
    Returns UnavailableScenario if no precomputed entry exists — never interpolates.
    """
    ...

def drag_drop_lookup(
    dropped_lat: float,
    dropped_lon: float,
    region_id: str,
    grid: WhatIfGrid,
    overlay_enabled: bool = False,   # power/energy feasibility overlay toggle;
                                      # see Property 14 — must not affect coverage_score
) -> DragDropResult | OutsideExtentError:
    """
    Snaps to nearest precomputed cell (BallTree index on grid centroids).
    Returns OutsideExtentError if outside grid extent — never extrapolates.
    Grid resolution is included in result metadata.
    """
    ...

@dataclass
class SimulationResult:
    before_heatmap: HeatmapDelta     # cell-level score changes
    after_heatmap: HeatmapDelta
    pct_good_change: float           # Δ % cells ≥ 70
    villages_newly_covered: int
    new_coverage_score: float
    elapsed_ms: int                  # must be ≤ 3 000 ms

@dataclass
class DragDropResult:
    snapped_coordinate: tuple[float, float]
    grid_resolution_m: int           # displayed to Planner
    coverage_score: float
    confidence_tag: ConfidenceLevel
    vs_top_candidate: ComparisonPanel  # includes case where manual > model
    elapsed_ms: int                  # must be ≤ 2 000 ms
```

**What-if grid precomputation** (offline, run before demo):
For each candidate site × scenario, the Recommendation_Engine computes the expected
Coverage Score delta across all grid cells within the BTS signal radius using the
precomputed DEM LOS grid. Results are stored in Supabase as a flat table keyed by
`(region_id, scenario_id, grid_cell_id)`.

---

### 5. Interactive_Map

**Responsibility:** Browser-rendered unified map interface (Next.js + MapLibre GL JS).

**Layer stack (rendered simultaneously):**
1. Base terrain tiles (Mapbox/MapLibre raster DEM)
2. ESA WorldCover land-cover classification overlay
3. Terrain contours derived from SRTM DEM
4. Village boundaries (polygon layer, GeoJSON)
5. Coverage Gap Heatmap (raster tile, 3-tier colour)
6. Confidence overlay (secondary visual indicator — hatching/opacity/border, independent
   of heatmap colour so confidence is not conflated with score)
7. Existing BTS markers (OpenCellID point layer)
8. BTS candidate markers (ranked, draggable)

**Heatmap colour thresholds:**
- Green: Coverage Score ≥ 70 (Good)
- Yellow: Coverage Score 40–69 (Moderate)
- Red: Coverage Score < 40 (Poor)

**Layer toggle SLA:** All toggle actions update the display within 2 seconds without
page reload (client-side layer visibility toggle on pre-fetched tile data).

**Target-area selector (Requirement 10.7/10.8):**

A dedicated map control, distinct from the region selector, lets the Planner define the
specific sub-area that `rank_bts_candidates` and `simulate_bts_placement` operate on:

- **Draw mode:** a MapLibre GL Draw polygon tool lets the Planner sketch a bounding
  area directly on the map. On completion, the polygon GeoJSON is posted to
  `resolve_target_area(region_id, "drawn_polygon", polygon_geojson)`.
- **Kecamatan mode:** a dropdown, scoped to the currently active region (Kupang /
  NTB-Bima / Lamandau), lists kecamatan names sourced from GADM Level 2 boundaries. On
  selection, `resolve_target_area(region_id, "kecamatan", kecamatan_id)` is called.
- In both modes, the resolved `TargetArea.boundary` is rendered as a highlighted outline
  on the map (per Requirement 10.8) before the Planner can submit a recommendation or
  simulation request — this is a confirm-before-submit step, not an automatic action.
- The target-area selector state is independent of, and layered on top of, the region
  selector: switching region resets the target-area selection.

**Side panel content on cell/candidate click:**
```
Coverage Score:   [0–100]
Confidence Tag:   [Low | Med | High]
Model version:    [v1.2.0]
Scoring run:      [2025-06-01T08:32:11Z]
Rank:             [#1 of N candidates]   (candidates only)
SHAP Top 3:
  ↑ elevation_m: +12.4  ("High elevation reduces path-loss probability")
  ↓ canopy_height_m: −8.1  ("Dense canopy attenuates signal")
  ↑ distance_to_bts_m: +6.7  ("Far from nearest BTS — high unserved demand")
```

**Low-confidence acknowledgement gate:**
When a Planner attempts to act on a Low-confidence recommendation, the UI presents a
modal that must be explicitly dismissed before the action proceeds. This is non-bypassable.

**WebGL fallback:** If WebGL is unavailable, a static error page is shown with browser
requirements and recommended alternatives (Chrome, Firefox, Edge current versions).

**Region selector:** Switches active analysis region among Kupang (MVP), NTB/Bima
(validation), and Lamandau (validation) without reloading the application.

---

## Data Models

### Supabase Schema

#### `grid_cells`
Stores Coverage Scores and confidence tags for every cell in every region.

| Column | Type | Notes |
|---|---|---|
| cell_id | UUID PK | |
| region_id | VARCHAR | e.g., `ntt_kupang`, `ntb_bima`, `lamandau` |
| lat | DOUBLE PRECISION | Cell centroid |
| lon | DOUBLE PRECISION | Cell centroid |
| resolution_m | INT | Grid resolution |
| coverage_score | FLOAT | 0.0–100.0 |
| confidence_tag | ENUM | `Low`, `Med`, `High` |
| tier_used | ENUM | `1` (AHP) or `2` (GBM) |
| shap_top3 | JSONB | `[{feature, value, direction}, ...]` |
| model_version | VARCHAR | FK → `model_artifacts.version_id` |
| scoring_run_id | UUID | FK → `scoring_runs.run_id` |

#### `bts_candidates`
Ranked BTS candidate sites output by the Recommendation_Engine.

| Column | Type | Notes |
|---|---|---|
| candidate_id | UUID PK | |
| region_id | VARCHAR | |
| target_area_id | UUID | FK → `target_areas.target_area_id` |
| rank | INT | 1 = highest expected improvement |
| lat | DOUBLE PRECISION | |
| lon | DOUBLE PRECISION | |
| expected_improvement | FLOAT | Mean Coverage Score delta in radius |
| los_validated | BOOLEAN | From precomputed DEM LOS grid; a row is only inserted
  once LOS has been computed, so this column is never NULL |
| confidence_tag | ENUM | `Low`, `Med`, `High` |
| shap_values | JSONB | Full SHAP dict per feature |
| model_version | VARCHAR | |
| scoring_run_id | UUID | |
| excluded_by_canopy | BOOLEAN | True if filtered out by `is_high_canopy()`
  (land_cover_class AND canopy_height_m jointly) |

#### `target_areas`
Planner-specified target areas (Requirement 10.7), resolved from either a drawn polygon
or a kecamatan selection. Referenced by `bts_candidates` and simulation requests.

| Column | Type | Notes |
|---|---|---|
| target_area_id | UUID PK | |
| region_id | VARCHAR | |
| selection_method | ENUM | `drawn_polygon`, `kecamatan` |
| kecamatan_id | VARCHAR | NULL unless `selection_method = kecamatan` |
| boundary_geojson | JSONB | Resolved polygon geometry |
| created_at | TIMESTAMPTZ | |

#### `whatif_grid`
Precomputed simulation outcomes for Before/After and Drag-and-Drop.

| Column | Type | Notes |
|---|---|---|
| scenario_id | UUID PK | Identifies a specific placed-BTS scenario |
| region_id | VARCHAR | |
| candidate_id | UUID | FK → `bts_candidates` (may be NULL for manual placements) |
| snapped_lat | DOUBLE PRECISION | Nearest grid cell centroid |
| snapped_lon | DOUBLE PRECISION | |
| grid_resolution_m | INT | Shown to Planner in UI |
| delta_coverage_score | FLOAT | Per-cell score improvement |
| pct_good_change | FLOAT | Δ % cells ≥ 70 |
| villages_newly_covered | INT | |
| new_coverage_score | FLOAT | Score at the placed location |

#### `model_artifacts`
Immutable registry of model versions. Artifacts are never deleted.

| Column | Type | Notes |
|---|---|---|
| version_id | VARCHAR PK | Semantic version, e.g., `ahp-v1.0`, `xgb-v2.3` |
| tier | ENUM | `1`, `2` |
| algorithm | VARCHAR | `AHP`, `XGBoost`, `LightGBM`, `GNN` |
| training_run_id | UUID | Links to the training run that produced this artifact |
| artifact_path | VARCHAR | Supabase Storage path |
| created_at | TIMESTAMPTZ | |

#### `scoring_runs`
Audit log of every batch scoring run. Retained ≥ 12 months.

*(Full schema listed under Recommendation_Engine interface above.)*

#### `ethical_risk_register`
Structured storage of the Ethical Risk Register entries.

| Column | Type | Notes |
|---|---|---|
| risk_id | VARCHAR PK | Slug, e.g., `digital_exclusion` |
| risk_description | TEXT | |
| impact | TEXT | |
| mitigation | TEXT | |
| responsible_owner_role | VARCHAR | |
| last_reviewed_at | TIMESTAMPTZ | |

### Feature Vector

```python
@dataclass
class FeatureVector:
    elevation_m: float
    slope_deg: float
    land_cover_class: int            # ESA WorldCover class code
    canopy_height_m: float           # SEPARATE from land_cover_class; also feeds
                                      # is_high_canopy() jointly with land_cover_class
    distance_to_bts_m: float
    road_distance_m: float
    population_density_per_km2: float
    facility_proximity_m: float
    # Ookla signal quality is NOT a field here — it is the Tier 2 label only.
```

### Confidence Thresholds (canonical definition)

This is the **only** definition of `ConfidenceThresholds` in the codebase. All other
components (Confidence_Tagger, DataQualityReport, drag-and-drop tagging) import this one
— it is not redeclared anywhere else.

```python
@dataclass
class ConfidenceThresholds:
    high_km: float = 2.0    # below this distance to BOTH sources → High
    low_km: float = 10.0    # above this distance to BOTH sources (or either absent
                             # within this radius) → Low; the band between high_km
                             # and low_km, or being within high_km of only one
                             # source, is Med
```

### Ethical Risk Register (Python representation)

```python
@dataclass
class EthicalRiskEntry:
    risk_id: str
    risk_description: str
    impact: str
    mitigation: str
    responsible_owner_role: str

REQUIRED_RISKS = [
    "digital_exclusion",
    "deforestation",
    "opencellid_sparsity_misread",
    "low_confidence_funding_decisions",
    "maup_resampling_mismatch",
]
```

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid
executions of a system — essentially, a formal statement about what the system should do.
Properties serve as the bridge between human-readable specifications and
machine-verifiable correctness guarantees.*

---

### Property 1: Coverage Score Bounds Invariant

*For any* valid `FeatureVector` (using the eight Consolidated Feature Set inputs, without
Ookla signal quality), `compute_coverage_score` SHALL return a value in the closed interval
[0.0, 100.0], regardless of which tier is active.

**Validates: Requirements 2.1**

---

### Property 2: Tier Routing Correctness

*For any* kecamatan with `ookla_tile_count == 0`, `select_tier` SHALL return `ModelTier.TIER1`.
*For any* kecamatan with `ookla_tile_count > 0`, `select_tier` SHALL return `ModelTier.TIER2`.
These cases are exhaustive and mutually exclusive.

**Validates: Requirements 2.2, 2.3, 9.7**

---

### Property 3: Geometry QC Completeness

*For any* input feature collection containing a mix of valid and geometrically invalid
features (null geometries, self-intersecting polygons), the Data_Pipeline output SHALL
contain zero geometrically invalid features, and the pipeline log SHALL contain exactly
one entry per removed or repaired feature.

**Validates: Requirements 1.2**

---

### Property 4: Attribute Range Validation

*For any* set of feature records where some attributes fall outside their defined
physically plausible range (per the Indonesia-scoped bounds in Data_Pipeline, Section 1),
the set of records flagged by the Data_Pipeline SHALL equal the set of out-of-range
records, and the scoring input set SHALL contain none of those flagged records.

**Validates: Requirements 1.3**

---

### Property 5: Multi-Resolution Output Invariant

*For any* valid `run_pipeline` execution, the number of resolution variants produced
SHALL be ≥ 2, and all output raster layers across all variants SHALL share the same
coordinate reference system (CRS) and spatial extent.

**Validates: Requirements 1.4**

---

### Property 6: DataQualityReport Completeness

*For any* `run_pipeline` execution that completes without fatal error, the resulting
`DataQualityReport` SHALL contain non-null values for all required fields: input record
counts per source, removed record counts, repaired record counts, chosen analysis grid
resolution, confidence thresholds (the single canonical `ConfidenceThresholds` instance),
and dataset checksums.

**Validates: Requirements 1.5, 7.1**

---

### Property 7: Spatial CV Kecamatan Disjointness

*For any* fold produced by `spatial_cv`, the intersection of the train-set kecamatan
identifiers and the test-set kecamatan identifiers SHALL be the empty set — no kecamatan
unit may appear in both train and test within a single fold.

**Validates: Requirements 2.4, 13.5**

---

### Property 8: Confidence Tag Correctness

*For any* pair of distances `(nearest_opencellid_km, nearest_ookla_km)` and any
canonical `ConfidenceThresholds` configuration, `tag_confidence` SHALL return:
- `High` if and only if `nearest_opencellid_km < thresholds.high_km` AND
  `nearest_ookla_km < thresholds.high_km`
- `Low` if and only if `nearest_opencellid_km > thresholds.low_km` AND
  `nearest_ookla_km > thresholds.low_km`, or either record is absent within
  `thresholds.low_km`. Absence of a record SHALL NOT be treated as confirmed zero
  coverage.
- `Med` in all other cases.

The same `tag_confidence` function SHALL be called for heatmap cells, BTS candidates,
and drag-and-drop outputs — no separate implementations per context.

**Validates: Requirements 7.1, 7.2, 7.5, 2.5**

---

### Property 9: BTS Candidate List Invariants

*For any* valid target area where at least 2 candidates survive the `is_high_canopy`
and LOS filters, `rank_bts_candidates` SHALL return a list `L` such that:
1. `len(L) ≥ 2`
2. `L[i].expected_improvement ≥ L[i+1].expected_improvement` for all valid `i`
   (non-increasing order by improvement)
3. `L[i].los_validated` is `True` for all `i` — candidates without a precomputed LOS
   result are excluded from `L` entirely rather than included with a null LOS value
4. No element of `L` satisfies `is_high_canopy(land_cover_class, canopy_height_m)`,
   i.e. the joint land-cover-and-canopy-height check, not land-cover alone

*For any* target area where fewer than 2 candidates survive filtering,
`rank_bts_candidates` SHALL return an `InsufficientCandidatesResult` instead of a list,
and SHALL NOT fabricate additional candidates to satisfy the ≥ 2 count.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.7, 9.2**

---

### Property 10: SHAP Completeness

*For any* `BTSCandidate` or scored grid cell produced by the Recommendation_Engine
(from either Tier 1 AHP or Tier 2 XGBoost/LightGBM), the `shap_values` dictionary
SHALL contain exactly one entry for each of the eight features in `CONSOLIDATED_FEATURES`,
and no entry's value SHALL be `None`. For Tier 1, this requires `regional_baseline` to
contain a value for every feature in `CONSOLIDATED_FEATURES` for the scoring run's region.

**Validates: Requirements 4.6, 8.1, 8.3**

---

### Property 11: Colour Tier Correctness

*For any* float value `score` in [0.0, 100.0], the `colour_tier(score)` function SHALL
return:
- `Green` if and only if `score ≥ 70`
- `Yellow` if and only if `40 ≤ score < 70`
- `Red` if and only if `score < 40`

These three cases are exhaustive, mutually exclusive, and boundary-inclusive as specified.

**Validates: Requirements 3.1**

---

### Property 12: Simulation Unavailability Contract

*For any* `(candidate_id, region_id)` pair that does not exist in the precomputed
what-if grid, `simulate_bts_placement` SHALL return an `UnavailableScenario` result and
SHALL NOT call any DEM computation, interpolation, or extrapolation function.

**Validates: Requirements 5.4**

---

### Property 13: Drag-and-Drop Boundary and Snap Contracts

*For any* coordinate outside the precomputed what-if grid's spatial extent for the
active region, `drag_drop_lookup` SHALL return `OutsideExtentError` and SHALL NOT return
a `DragDropResult` containing an interpolated or extrapolated coverage score.

*For any* coordinate within the spatial extent, `drag_drop_lookup` SHALL return a
`DragDropResult` where `snapped_coordinate` equals the centroid of the nearest grid cell
(by Euclidean distance), and `grid_resolution_m` SHALL be a positive integer matching the
active grid resolution.

**Validates: Requirements 6.6, 6.7**

---

### Property 14: Power Overlay Non-Interference

*For any* dropped coordinate and any `overlay_enabled` boolean value,
`drag_drop_lookup(..., overlay_enabled=True).coverage_score` SHALL equal
`drag_drop_lookup(..., overlay_enabled=False).coverage_score`. The power/energy
feasibility overlay SHALL NOT modify the Coverage Score computation.

**Validates: Requirements 6.5**

---

### Property 15: SHAP Top-3 Format Invariant

*For any* `shap_values` dict with entries for all eight consolidated features,
`format_shap_top3(shap_values)` SHALL return a list of exactly three entries, where each
entry has a non-empty `feature_name` string and a `direction` value in `{positive, negative}`.

**Validates: Requirements 8.2**

---

### Property 16: Scoring Run Log Completeness

*For any* scoring run, the resulting `ScoringRunLog` entry persisted to Supabase SHALL
contain non-null values for all of: `run_id`, `model_version`, `tier`,
`region_kecamatans`, `resolution_m`, `input_checksums`, `candidate_count`, and
`timestamp`.

**Validates: Requirements 8.5, 11.2**

---

### Property 17: Equity Weighting Direction

*For any* two `FeatureVector` instances `A` and `B` that are identical in all fields
except that `A.facility_proximity_m < B.facility_proximity_m` (i.e., A is closer to
public facilities) and both have non-zero `population_density_per_km2`, the AHP Coverage
Score with equity weighting SHALL assign `score(A) ≥ score(B)` — higher-facility-proximity
cells SHALL NOT be systematically deprioritised over lower-proximity cells.

*Separately, for any* two `FeatureVector` instances `C` and `D` identical in all fields
except that `C.population_density_per_km2 > D.population_density_per_km2` and both have
identical `facility_proximity_m`, the AHP Coverage Score with equity weighting SHALL
assign `score(C) ≥ score(D)` — this covers the population-density half of the equity
weighting independently of the facility-proximity half, since Requirement 9.1 names both
factors and neither is a proxy for the other.

**Validates: Requirements 9.1**

---

### Property 18: Per-Kecamatan Accuracy Reporting

*For any* `spatial_cv` result involving `N` distinct kecamatan units, `CVResult` SHALL
contain per-kecamatan accuracy entries for all `N` kecamatan identifiers in the input
dataset — no kecamatan's accuracy SHALL be merged into an aggregate-only metric that
hides sub-region performance.

**Validates: Requirements 9.4**

---

### Property 19: Ethical Risk Register Completeness

*For any* instance of the `EthicalRiskRegister`, it SHALL contain entries for all five
required risk IDs (`digital_exclusion`, `deforestation`,
`opencellid_sparsity_misread`, `low_confidence_funding_decisions`,
`maup_resampling_mismatch`), and each entry SHALL have non-empty `risk_description`,
`impact`, `mitigation`, and `responsible_owner_role` fields.

**Validates: Requirements 9.6**

---

### Property 20: Model Artifact Immutability

*For any* Tier 2 retraining operation on updated Ookla data, the number of entries in
`model_artifacts` SHALL increase by exactly one, and all previously existing entries
(identified by their `version_id`) SHALL remain present and unmodified.

**Validates: Requirements 11.5**

---

### Property 21: Model Version Assignment Before Use

*For any* scoring run, the model artifact used to compute Coverage Scores SHALL have a
non-empty `version_id` assigned before the first call to `compute_coverage_score` in
that run — no prediction SHALL be produced from an unversioned model artifact.

**Validates: Requirements 11.1**

---

### Property 22: Pipeline Region Parameterisation

*For any* valid GeoJSON representing a provincial or kabupaten boundary, `run_pipeline`
SHALL complete without error and produce output rasters and vectors scoped to that
boundary — without any modification to core pipeline code.

**Validates: Requirements 13.1**

---

### Property 23: Simulation Metric Completeness

*For any* `SimulationResult` returned by `simulate_bts_placement`, the fields
`pct_good_change`, `villages_newly_covered`, and `new_coverage_score` SHALL all be
present and numerically finite (not `None`, `NaN`, or infinite).

**Validates: Requirements 5.3**

---

### Property 24: Manual Placement Comparison Correctness

*For any* `DragDropResult` where `coverage_score > vs_top_candidate.model_score`,
`vs_top_candidate.manual_wins` SHALL be `True`. The system SHALL never suppress or
reclassify a case where the Planner's manual placement outperforms the model's
top-ranked suggestion.

**Validates: Requirements 6.3, 6.4**

---

### Property 25: Target Area Resolution Correctness

*For any* `resolve_target_area` call with `selection_method = "kecamatan"` and a valid
`kecamatan_id`, the returned `TargetArea.boundary` SHALL exactly equal that kecamatan's
GADM Level 2 boundary geometry, and `TargetArea.kecamatan_id` SHALL equal the input
`kecamatan_id`.

*For any* `resolve_target_area` call with `selection_method = "drawn_polygon"` and a
valid polygon GeoJSON, the returned `TargetArea.boundary` SHALL exactly equal the input
polygon, and `TargetArea.kecamatan_id` SHALL be `None`.

*For any* resolved `TargetArea`, every coordinate in the `grid_cells` array passed to a
subsequent `rank_bts_candidates` or `simulate_bts_placement` call for that
`target_area_id` SHALL fall within `TargetArea.boundary`.

**Validates: Requirements 10.7, 10.8, 4.1, 5.1**

---

### Property 26: PII Absence Invariant

*For any* Supabase table schema in this system (`grid_cells`, `bts_candidates`,
`target_areas`, `whatif_grid`, `model_artifacts`, `scoring_runs`,
`ethical_risk_register`), no column name or stored value SHALL correspond to a
household-level location record, individual device identifier, or personal contact
field. Population data SHALL be referenced exclusively through aggregated WorldPop
density rasters, never disaggregated to individual-level records.

**Validates: Requirements 12.1, 12.2, 12.3, 12.4**

---

## Error Handling

### Data_Pipeline Errors

| Error condition | Behaviour |
|---|---|
| Data source unavailable (GEE timeout, 404) | Log the source and error; skip that source for this run; include in DataQualityReport under `unavailable_sources`; do not abort other sources |
| All sources unavailable | Abort run; emit structured error with run context |
| Geometry repair fails (buffer(0) produces empty geometry) | Remove feature; log as `removed`; do not attempt further repair |
| Attribute validation cannot determine range (unknown field) | Log warning; do not flag or exclude the record; include warning in DataQualityReport |
| Resolution harmonisation produces mismatched extents | Abort run; log the mismatched source and resolution pair |

### Recommendation_Engine Errors

| Error condition | Behaviour |
|---|---|
| Fewer than 2 candidates survive deforestation + LOS filters | Return `InsufficientCandidatesResult` with `surviving_count` and a human-readable `reason`; never fabricate a candidate to reach the minimum of 2; surfaced to the Planner as a caveated partial result, not a silent empty state |
| SHAP computation fails for a cell/candidate | Log error with cell_id; omit cell from results rather than returning null SHAP values; do not surface the cell to Planner |
| Tier 2 model artifact missing or corrupt | Fall back to Tier 1 (AHP) for that kecamatan; log the fallback with reason; include in scoring run log |
| Scoring run exceeds time budget | Log partial results; mark run as incomplete in `scoring_runs` table; do not publish incomplete results to Planner UI |
| `resolve_target_area` receives an invalid or self-intersecting drawn polygon | Reject the request with a structured validation error; do not attempt to auto-repair the Planner's drawn shape (unlike Data_Pipeline's own ingestion QC, which repairs source data, not live user input) |

### Simulation_Engine Errors

| Error condition | Behaviour |
|---|---|
| Precomputed scenario missing | Return `UnavailableScenario` with a human-readable message; never compute or interpolate |
| Dropped coordinate outside grid extent | Return `OutsideExtentError` with the active region's extent in the error payload |
| BallTree snap fails (empty grid) | Return `OutsideExtentError`; log the failure |

### Confidence_Tagger Errors

| Error condition | Behaviour |
|---|---|
| Distance to nearest OpenCellID or Ookla tile cannot be computed (spatial index missing) | Default to `Low` confidence and log a warning; absence of data ≠ high confidence |

### Interactive_Map Errors

| Error condition | Behaviour |
|---|---|
| WebGL not supported | Display a static fallback page explaining browser requirements; do not attempt a non-WebGL rendering |
| Tile fetch failure (network error) | Display a retry button; do not show a blank map silently |
| Region switch fails (no data for region) | Display an error banner with the unavailable region name; retain the previously loaded region |
| Low-confidence gate bypassed programmatically | Log a security warning; re-display the gate on next interaction |
| Target-area selector: kecamatan dropdown has no boundary data for a selected id | Display an error inline in the selector; do not submit a recommendation request with an unresolved target area |

---

## Testing Strategy

### Dual Testing Approach

GeoSignal AI uses two complementary test layers:

1. **Property-based tests** — verify universal correctness properties across a wide range
   of generated inputs. Each property maps 1:1 to a Correctness Property in this document.
2. **Unit/example-based tests** — verify specific scenarios, edge cases, structural
   invariants, and integration points.

### Property-Based Testing Library

**Language:** Python  
**Library:** [Hypothesis](https://hypothesis.readthedocs.io/)  
**Minimum iterations per property:** 100 (Hypothesis default `max_examples=100`)  
**Tag format:** Each test is tagged with a comment:
`# Feature: geosignal-ai, Property N: <property_text>`

Each of the 26 Correctness Properties defined above maps to exactly one Hypothesis test.

### Property Test Configuration

```python
from hypothesis import given, settings
from hypothesis import strategies as st

@settings(max_examples=100)
@given(
    elevation_m=st.floats(min_value=-11, max_value=4884),   # Indonesia-scoped bound
    slope_deg=st.floats(min_value=0, max_value=90),
    land_cover_class=st.integers(min_value=10, max_value=95),   # ESA WorldCover codes
    canopy_height_m=st.floats(min_value=0, max_value=100),
    distance_to_bts_m=st.floats(min_value=0, max_value=200_000),
    road_distance_m=st.floats(min_value=0, max_value=200_000),
    population_density_per_km2=st.floats(min_value=0, max_value=1_000_000),
    facility_proximity_m=st.floats(min_value=0, max_value=200_000),
)
def test_coverage_score_bounds(
    elevation_m, slope_deg, land_cover_class, canopy_height_m,
    distance_to_bts_m, road_distance_m, population_density_per_km2, facility_proximity_m
):
    # Feature: geosignal-ai, Property 1: Coverage Score Bounds Invariant
    fv = FeatureVector(...)
    for tier in [AHPAdapter(), XGBoostAdapter()]:
        score = compute_coverage_score(fv, tier)
        assert 0.0 <= score <= 100.0
```

### Property Test Coverage Map

| Property | Test file | Hypothesis strategy |
|---|---|---|
| P1: Coverage Score bounds | `test_scoring.py` | Random FeatureVectors within Indonesia-scoped valid ranges |
| P2: Tier routing | `test_scoring.py` | `st.integers(min_value=0)` for ookla_tile_count |
| P3: Geometry QC completeness | `test_pipeline.py` | Random GeoJSON with st.lists of valid/invalid geometries |
| P4: Attribute range validation | `test_pipeline.py` | Random records with some attributes outside plausible range |
| P5: Multi-resolution output | `test_pipeline.py` | Various resolution_variants lists of len ≥ 2 |
| P6: DataQualityReport completeness | `test_pipeline.py` | Random pipeline configs |
| P7: Spatial CV disjointness | `test_model.py` | Random kecamatan lists; st.lists of IDs |
| P8: Confidence tag correctness | `test_confidence.py` | `st.floats(min_value=0)` for distances, canonical ConfidenceThresholds |
| P9: BTS candidate list invariants | `test_candidates.py` | Random grid arrays with land-cover + canopy-height variety, including all-excluded cases |
| P10: SHAP completeness | `test_shap.py` | Random FeatureVectors; both tier adapters; random regional baselines |
| P11: Colour tier correctness | `test_heatmap.py` | `st.floats(min_value=0.0, max_value=100.0)` |
| P12: Simulation unavailability contract | `test_simulation.py` | Random (candidate_id, region_id) not in grid |
| P13: Drag-drop boundary/snap | `test_simulation.py` | Coordinates inside and outside grid extent |
| P14: Power overlay non-interference | `test_simulation.py` | Random coordinates × overlay boolean |
| P15: SHAP top-3 format | `test_shap.py` | Random SHAP value dicts |
| P16: Scoring run log completeness | `test_audit.py` | Random scoring run parameters |
| P17: Equity weighting direction | `test_scoring.py` | Pairs of FeatureVectors differing in facility_proximity; pairs differing in population_density |
| P18: Per-kecamatan accuracy reporting | `test_model.py` | Random kecamatan sets of varying sizes |
| P19: Ethical Risk Register completeness | `test_ethics.py` | Constructor-level verification |
| P20: Model artifact immutability | `test_audit.py` | Sequential retraining simulations |
| P21: Model version assignment | `test_audit.py` | Any scoring run |
| P22: Pipeline region parameterisation | `test_pipeline.py` | Random valid boundary GeoJSON |
| P23: Simulation metric completeness | `test_simulation.py` | Random simulation inputs |
| P24: Manual placement comparison | `test_simulation.py` | DragDropResults where manual > model score |
| P25: Target area resolution correctness | `test_target_area.py` | Random kecamatan_ids and drawn polygons |
| P26: PII absence invariant | `test_privacy.py` | Static schema introspection across all Supabase table definitions |

### Unit / Example Tests

**Focus areas for example-based tests:**
- Specific edge cases at Coverage Score threshold boundaries (39.99, 40.0, 40.01, 69.99,
  70.0, 70.01)
- Confidence tag boundaries (exactly 2.0 km, exactly 10.0 km)
- Canopy exclusion boundary (exactly 15.0 m canopy height, forest class with 14.9 m
  canopy that should NOT be excluded, shrubland class with 20 m canopy that SHOULD be
  excluded)
- Exactly 0 and exactly 1 surviving candidate after filtering (InsufficientCandidatesResult)
- Low-confidence acknowledgement gate: modal must appear and must not be bypassable
- Region selector switching behaviour
- Target-area selector: switching region resets target-area selection
- Target-area selector: submitting a recommendation request with no target area resolved is blocked client-side
- WebGL fallback rendering
- Admin boundary IDs absent from CONSOLIDATED_FEATURES
- Ookla absent from CONSOLIDATED_FEATURES
- FeatureVector has distinct `land_cover_class` and `canopy_height_m` fields
- AHP SHAP baseline is recomputed per region per scoring run, not reused stale across runs
- SHAP panel co-located with Coverage Score panel in the UI
- Model version and run timestamp displayed in recommendation panel
- Data sources: only aggregated, non-PII inputs (PII field names absent from schema)

### Integration Tests

**Key integration touchpoints:**
- GEE export → Supabase Storage write → Data_Pipeline read-back (round-trip data integrity)
- Recommendation_Engine → `scoring_runs` table insert → UI retrieval (audit log round-trip)
- `whatif_grid` precomputed lookup → Simulation_Engine → MapLibre heatmap update (e2e simulation flow)
- Region selector change → API region filter → new grid_cells query → heatmap re-render
- Target-area selector (draw or kecamatan) → `resolve_target_area` → `target_areas` insert → `grid_cells` filtered query → `rank_bts_candidates` call (e2e target-area flow)

### Cross-Validation Acceptance Criteria

Before publishing recommendations for any region, the following acceptance gates must pass:

1. Spatial CV across all available kecamatans completes without data leakage (Property 7).
2. Per-kecamatan accuracy report contains entries for all kecamatans (Property 18).
3. At least one kecamatan per terrain type (elevation-driven: NTT; canopy-driven: Lamandau)
   shows generalisation to unseen terrain.
4. No kecamatan's accuracy is hidden behind a passing aggregate metric.

### Performance Benchmarks

| Operation | SLA |
|---|---|
| Layer toggle update | ≤ 2 s |
| Cell click → side panel render | ≤ 1 s |
| Before/After simulation result | ≤ 3 s |
| Drag-and-drop snap + panel update | ≤ 2 s |
| `rank_bts_candidates` (batch, MVP region) | ≤ 30 s (offline, pre-demo) |
| `resolve_target_area` (draw or kecamatan lookup) | ≤ 1 s |

Performance is verified via E2E tests using Playwright on the MVP region data.

### Ethical Safeguard Verification Checklist

Before any public demo or stakeholder presentation, verify:

- [ ] Ethical Risk Register contains all 5 required entries (Property 19)
- [ ] All UI outputs carry "GeoAI-assisted estimate" label (Requirement 9.3)
- [ ] Low-confidence acknowledgement gate is non-bypassable (Requirement 9.5)
- [ ] Deforestation constraint (land-cover AND canopy-height, jointly) is active by default (Property 9)
- [ ] SHAP explanations display for both Tier 1 and Tier 2 outputs, with a documented AHP baseline definition (Property 10)
- [ ] Confidence thresholds are stored in DataQualityReport, not hard-coded, and only one `ConfidenceThresholds` definition exists in the codebase (Requirement 7.1)
- [ ] No Supabase table or field stores PII (Property 26)
- [ ] Target-area selection (draw or kecamatan) is required and confirmed before any recommendation or simulation request (Property 25)