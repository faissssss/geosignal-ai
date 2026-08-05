"""GeoSignal AI — Simulation_Engine (Tasks 19 & 20).

Implements Before/After simulation and Drag-and-Drop lookup from precomputed
what-if grids.  NEVER performs live DEM recomputation, interpolation, or
extrapolation.

Public API
----------
simulate_bts_placement(candidate_id, region_id, whatif_rows) -> SimulationResult | UnavailableScenario
drag_drop_lookup(dropped_lat, dropped_lon, region_id, grid, ...) -> DragDropResult | OutsideExtentError

Design constraints (design.md § Simulation_Engine):
- simulate_bts_placement: read only from precomputed whatif_grid rows.
  Returns UnavailableScenario when scenario not found — never computes.
- drag_drop_lookup: snap dropped coordinate to nearest whatif_grid cell via
  BallTree. Returns OutsideExtentError when outside extent — never extrapolates.
- overlay_enabled does NOT modify coverage_score (Property 14).
- manual_wins is never suppressed (Property 24).
- elapsed_ms: ≤ 3000 ms for simulate_bts_placement, ≤ 2000 ms for drag_drop_lookup.
"""
from __future__ import annotations

import logging
import math
import time
from typing import Sequence

import numpy as np

from geosignal.confidence import tag_confidence
from geosignal.models import (
    ComparisonPanel,
    ConfidenceThresholds,
    DragDropResult,
    HeatmapDelta,
    OutsideExtentError,
    SimulationResult,
    UnavailableScenario,
    WhatIfGrid,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Earth radius in metres for haversine spatial extent checks.
_EARTH_RADIUS_M: float = 6_371_000.0

# Maximum distance (in metres) from the nearest grid centroid before a
# coordinate is considered "outside the extent".  This implements the
# spatial extent check: if the nearest centroid is farther than this,
# the coordinate is outside the grid.
DEFAULT_EXTENT_THRESHOLD_M: float = 50_000.0  # 50 km


# ---------------------------------------------------------------------------
# Task 19 — Before/After simulation
# ---------------------------------------------------------------------------


def simulate_bts_placement(
    candidate_id: str,
    region_id: str,
    whatif_rows: list[dict],
    mock_heatmap_cells: list[dict] | None = None,
) -> SimulationResult | UnavailableScenario:
    """Look up a precomputed what-if scenario and return a SimulationResult.

    Parameters
    ----------
    candidate_id:
        The scenario/candidate identifier to look up.
    region_id:
        The active region (used both for lookup and in result objects).
    whatif_rows:
        Rows from the ``whatif_grid`` Supabase table (already loaded into
        memory — no live DB call here; all lookups are O(N) dict scans).
    mock_heatmap_cells:
        Optional list of cell dicts to use as the heatmap payload in tests.
        When None, minimal synthetic heatmap objects are built.

    Returns
    -------
    SimulationResult
        When the scenario is found in whatif_rows.
    UnavailableScenario
        When no matching (candidate_id, region_id) entry exists.
        Does NOT compute, interpolate, or extrapolate.
    """
    t0 = time.monotonic()

    # ── Look up the precomputed row ───────────────────────────────────────
    row = _find_whatif_row(candidate_id, region_id, whatif_rows)

    if row is None:
        logger.info(
            "simulate_bts_placement: no precomputed entry for "
            "candidate_id=%r region_id=%r → UnavailableScenario",
            candidate_id,
            region_id,
        )
        return UnavailableScenario(
            candidate_id=candidate_id,
            region_id=region_id,
            message=(
                f"No precomputed simulation scenario is available for "
                f"candidate '{candidate_id}' in region '{region_id}'. "
                "Please run the what-if precomputation job for this region first."
            ),
        )

    # ── Build heatmap snapshots ───────────────────────────────────────────
    cells = mock_heatmap_cells if mock_heatmap_cells is not None else []

    before_heatmap = HeatmapDelta(
        region_id=region_id,
        cells=cells,
        snapshot_label="before",
    )
    after_heatmap = HeatmapDelta(
        region_id=region_id,
        cells=cells,
        snapshot_label="after",
    )

    # ── Extract metrics from the precomputed row ──────────────────────────
    pct_good_change = float(row["pct_good_change"])
    villages_newly_covered = int(row["villages_newly_covered"])
    new_coverage_score = float(row["new_coverage_score"])

    # Validate finite values (Property 23).
    if not math.isfinite(pct_good_change):
        logger.error(
            "pct_good_change is not finite for candidate_id=%r; "
            "returning UnavailableScenario",
            candidate_id,
        )
        return UnavailableScenario(
            candidate_id=candidate_id,
            region_id=region_id,
            message="Precomputed pct_good_change is not a finite number.",
        )
    if not math.isfinite(new_coverage_score):
        logger.error(
            "new_coverage_score is not finite for candidate_id=%r; "
            "returning UnavailableScenario",
            candidate_id,
        )
        return UnavailableScenario(
            candidate_id=candidate_id,
            region_id=region_id,
            message="Precomputed new_coverage_score is not a finite number.",
        )

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    result = SimulationResult(
        before_heatmap=before_heatmap,
        after_heatmap=after_heatmap,
        pct_good_change=pct_good_change,
        villages_newly_covered=villages_newly_covered,
        new_coverage_score=new_coverage_score,
        elapsed_ms=elapsed_ms,
    )

    logger.info(
        "simulate_bts_placement: candidate_id=%r region_id=%r "
        "pct_good_change=%.2f elapsed_ms=%d",
        candidate_id,
        region_id,
        pct_good_change,
        elapsed_ms,
    )
    return result


# ---------------------------------------------------------------------------
# Task 20 — Drag-and-Drop lookup
# ---------------------------------------------------------------------------


def drag_drop_lookup(
    dropped_lat: float,
    dropped_lon: float,
    region_id: str,
    grid: WhatIfGrid,
    whatif_rows: list[dict],
    top_candidate_id: str = "top-candidate-001",
    top_candidate_lat: float = 0.0,
    top_candidate_lon: float = 0.0,
    top_candidate_score: float = 50.0,
    overlay_enabled: bool = False,
    extent_threshold_m: float = DEFAULT_EXTENT_THRESHOLD_M,
    nearest_opencellid_km: float = 5.0,
    nearest_ookla_km: float = 5.0,
    confidence_thresholds: ConfidenceThresholds | None = None,
) -> DragDropResult | OutsideExtentError:
    """Snap a dropped coordinate to the nearest precomputed what-if grid cell.

    Parameters
    ----------
    dropped_lat, dropped_lon:
        The coordinate where the Planner dropped the BTS marker.
    region_id:
        The active region identifier.
    grid:
        The in-memory WhatIfGrid for this region (loaded from precomputed data).
    whatif_rows:
        Rows from the ``whatif_grid`` table for metric lookup after snapping.
    top_candidate_id, top_candidate_lat, top_candidate_lon, top_candidate_score:
        Model top-ranked candidate details for the ComparisonPanel.
    overlay_enabled:
        Power/energy feasibility overlay toggle.  Does NOT modify coverage_score
        (Property 14: power overlay non-interference).
    extent_threshold_m:
        Maximum distance (metres) from the nearest grid centroid; if the
        nearest centroid is farther, the coordinate is outside the extent.
    nearest_opencellid_km, nearest_ookla_km:
        Distances to nearest OpenCellID and Ookla records for confidence tagging.
    confidence_thresholds:
        ConfidenceThresholds instance; defaults to ConfidenceThresholds().

    Returns
    -------
    DragDropResult
        When the coordinate is within the grid extent.  ``coverage_score`` is
        read from the precomputed row — never modified by ``overlay_enabled``.
    OutsideExtentError
        When the coordinate is outside the grid extent.  No score is computed.
    """
    t0 = time.monotonic()

    if confidence_thresholds is None:
        confidence_thresholds = ConfidenceThresholds()

    # ── Validate grid is non-empty ────────────────────────────────────────
    if len(grid.centroids) == 0:
        logger.info(
            "drag_drop_lookup: empty grid for region_id=%r → OutsideExtentError",
            region_id,
        )
        return OutsideExtentError(
            dropped_lat=dropped_lat,
            dropped_lon=dropped_lon,
            region_id=region_id,
            message="No precomputed grid cells exist for this region.",
        )

    # ── Find nearest centroid ─────────────────────────────────────────────
    query_point = np.radians([[dropped_lat, dropped_lon]])
    distances, indices = grid.spatial_index.query(query_point, k=1)

    nearest_idx = int(indices[0][0])
    nearest_dist_rad = float(distances[0][0])
    nearest_dist_m = nearest_dist_rad * _EARTH_RADIUS_M

    # ── Extent check: if nearest centroid is too far → OutsideExtentError ─
    if nearest_dist_m > extent_threshold_m:
        logger.info(
            "drag_drop_lookup: coordinate (%.4f, %.4f) is %.1f m from nearest "
            "grid centroid (threshold=%.1f m) → OutsideExtentError",
            dropped_lat,
            dropped_lon,
            nearest_dist_m,
            extent_threshold_m,
        )
        return OutsideExtentError(
            dropped_lat=dropped_lat,
            dropped_lon=dropped_lon,
            region_id=region_id,
            message=(
                f"Dropped coordinate ({dropped_lat:.4f}, {dropped_lon:.4f}) is "
                f"outside the precomputed grid extent for region '{region_id}'. "
                f"Nearest grid cell is {nearest_dist_m:.0f} m away "
                f"(threshold: {extent_threshold_m:.0f} m)."
            ),
        )

    # ── Snap to nearest centroid ──────────────────────────────────────────
    snapped_lat = float(grid.centroids[nearest_idx, 0])
    snapped_lon = float(grid.centroids[nearest_idx, 1])
    snapped_scenario_id = grid.scenario_ids[nearest_idx]

    # ── Look up precomputed metrics for this scenario ─────────────────────
    row = _find_whatif_row(snapped_scenario_id, region_id, whatif_rows)

    if row is None:
        # Fallback: no row found after snap — treat as outside extent.
        logger.warning(
            "drag_drop_lookup: snapped to scenario_id=%r but no whatif_row found "
            "for region_id=%r → OutsideExtentError",
            snapped_scenario_id,
            region_id,
        )
        return OutsideExtentError(
            dropped_lat=dropped_lat,
            dropped_lon=dropped_lon,
            region_id=region_id,
            message=(
                f"No precomputed data found for snapped scenario "
                f"'{snapped_scenario_id}' in region '{region_id}'."
            ),
        )

    # ── Extract coverage score (overlay_enabled does NOT change this) ─────
    # Property 14: overlay_enabled flag must not modify coverage_score.
    coverage_score = float(row["new_coverage_score"])
    # overlay_enabled is intentionally unused in score computation — this is correct.
    _ = overlay_enabled  # acknowledged; does not affect coverage_score

    # ── Confidence tag ────────────────────────────────────────────────────
    confidence_tag = tag_confidence(
        point=(snapped_lat, snapped_lon),
        nearest_opencellid_km=nearest_opencellid_km,
        nearest_ookla_km=nearest_ookla_km,
        thresholds=confidence_thresholds,
    )

    # ── ComparisonPanel: manual vs. model top candidate ───────────────────
    # manual_wins is True when coverage_score > model_score (never suppressed).
    manual_wins = coverage_score > top_candidate_score

    comparison = ComparisonPanel(
        manual_score=coverage_score,
        model_score=top_candidate_score,
        top_candidate_id=top_candidate_id,
        top_candidate_lat=top_candidate_lat,
        top_candidate_lon=top_candidate_lon,
        manual_wins=manual_wins,
    )

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    result = DragDropResult(
        snapped_coordinate=(snapped_lat, snapped_lon),
        grid_resolution_m=grid.grid_resolution_m,
        coverage_score=coverage_score,
        confidence_tag=confidence_tag,
        vs_top_candidate=comparison,
        elapsed_ms=elapsed_ms,
    )

    logger.info(
        "drag_drop_lookup: (%.4f, %.4f) snapped to (%.4f, %.4f) "
        "scenario_id=%r coverage_score=%.1f manual_wins=%s elapsed_ms=%d",
        dropped_lat,
        dropped_lon,
        snapped_lat,
        snapped_lon,
        snapped_scenario_id,
        coverage_score,
        manual_wins,
        elapsed_ms,
    )
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_whatif_row(
    scenario_id: str,
    region_id: str,
    rows: list[dict],
) -> dict | None:
    """Return the first row matching (scenario_id, region_id), or None."""
    for row in rows:
        if (
            str(row.get("scenario_id", "")) == str(scenario_id)
            and row.get("region_id") == region_id
        ):
            return row
    return None
