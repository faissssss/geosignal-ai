"""GeoSignal AI — canonical data models.

All dataclasses and the CONSOLIDATED_FEATURES list are defined here and
imported by every other module.  Do NOT redefine any of these elsewhere.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import numpy as np
from sklearn.neighbors import BallTree

# ── Consolidated feature list ─────────────────────────────────────────────────
# This is the SINGLE canonical definition.  Import from here everywhere.
# Must have EXACTLY 8 entries.  NO Ookla field.  NO admin boundary field.
CONSOLIDATED_FEATURES: list[str] = [
    "elevation_m",
    "slope_deg",
    "land_cover_class",
    "canopy_height_m",
    "distance_to_bts_m",
    "road_distance_m",
    "population_density_per_km2",
    "facility_proximity_m",
]


@dataclass
class FeatureVector:
    """One row of model inputs per grid cell.

    Ookla is NOT a field here — it is the Tier 2 training label only.
    """

    elevation_m: float
    slope_deg: float
    land_cover_class: int        # ESA WorldCover class code
    canopy_height_m: float       # SEPARATE from land_cover_class
    distance_to_bts_m: float
    road_distance_m: float
    population_density_per_km2: float
    facility_proximity_m: float


@dataclass
class ConfidenceThresholds:
    """Single canonical definition of confidence distance thresholds.

    high_km: both distances must be below this to earn a High tag.
    low_km:  either distance above this (or source absent) → Low tag.
    """

    high_km: float = 2.0   # below this distance to BOTH sources → High
    low_km: float = 10.0   # above this (or either absent within) → Low


@dataclass
class DataQualityReport:
    """Summary report emitted by the Data_Pipeline after each run."""

    region_id: str
    input_record_counts: dict
    removed_records: dict
    repaired_records: dict
    anomalous_records: dict
    chosen_resolution_m: int
    confidence_thresholds: ConfidenceThresholds
    dataset_checksums: dict
    timestamp: datetime


@dataclass
class BTSCandidate:
    """A ranked BTS placement candidate produced by rank_bts_candidates."""

    coordinate: tuple[float, float]
    expected_improvement: float
    los_validated: bool
    confidence_tag: str            # "Low", "Med", "High"
    shap_values: dict[str, float]
    rank: int
    model_version: str
    scoring_run_id: str


@dataclass
class InsufficientCandidatesResult:
    """Returned instead of a list when fewer than 2 candidates survive filtering."""

    surviving_count: int       # 0 or 1
    reason: str
    target_area_id: str


@dataclass
class TargetArea:
    """Planner-specified sub-area for recommendations and simulations."""

    target_area_id: str
    region_id: str
    selection_method: Literal["drawn_polygon", "kecamatan"]
    boundary: dict             # GeoJSON
    kecamatan_id: str | None = None


@dataclass
class SimulationResult:
    """Result of a Before/After BTS placement simulation."""

    before_heatmap: "HeatmapDelta"
    after_heatmap: "HeatmapDelta"
    pct_good_change: float
    villages_newly_covered: int
    new_coverage_score: float
    elapsed_ms: int


@dataclass
class DragDropResult:
    """Result of a Drag-and-Drop placement lookup."""

    snapped_coordinate: tuple[float, float]
    grid_resolution_m: int
    coverage_score: float
    confidence_tag: str
    vs_top_candidate: "ComparisonPanel"
    elapsed_ms: int


@dataclass
class OutsideExtentError:
    """Returned when a dropped coordinate falls outside the grid extent."""

    dropped_lat: float
    dropped_lon: float
    region_id: str
    message: str = "Dropped coordinate is outside the grid extent."


@dataclass
class UnavailableScenario:
    """Returned when no precomputed scenario exists for a candidate."""

    candidate_id: str
    region_id: str
    message: str = "No precomputed scenario available for this candidate."


@dataclass
class ComparisonPanel:
    """Side-by-side comparison of a manual placement vs. the top model candidate."""

    manual_score: float
    model_score: float
    top_candidate_id: str
    top_candidate_lat: float
    top_candidate_lon: float
    manual_wins: bool


@dataclass
class HeatmapDelta:
    """Cell-level snapshot used in Before/After simulation results."""

    region_id: str
    cells: list[dict]
    snapshot_label: str


@dataclass
class WhatIfGrid:
    """Precomputed what-if grid for the Simulation_Engine."""

    region_id: str
    centroids: np.ndarray
    scenario_ids: list[str]
    grid_resolution_m: int
    spatial_index: BallTree


@dataclass(frozen=True)
class EthicalRiskEntry:
    """One entry in the Ethical Risk Register."""

    risk_id: str
    risk_description: str
    impact: str
    mitigation: str
    responsible_owner_role: str


@dataclass
class CVResult:
    """Spatial cross-validation result with per-kecamatan accuracy entries."""

    kecamatan_accuracies: dict[str, float]   # kecamatan_id → accuracy
    n_folds: int
