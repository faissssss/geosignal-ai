"""GeoSignal AI — What-If Grid Precomputation (Task 18).

Offline batch job that populates the ``whatif_grid`` Supabase table
with precomputed simulation outcomes for Before/After and Drag-and-Drop.

Public API
----------
precompute_whatif_grid(region_id, candidates, grid_cells, ...) -> WhatIfGrid
build_whatif_grid_from_rows(region_id, rows) -> WhatIfGrid
is_whatif_grid_populated(region_id, rows) -> bool

Design constraints (design.md § Simulation_Engine):
- This job runs OFFLINE before demo time — Simulation_Engine reads from it,
  never computes live.
- Results are keyed by (region_id, scenario_id, grid_cell_id).
- Must cover all ranked BTSCandidates plus a dense sample of manual-placement
  scenarios across each MVP/validation region.
- Depends on the precomputed LOS grid (Task 12.1) for delta computation.
  In offline/test mode the LOS grid is approximated as all-clear.
"""
from __future__ import annotations

import logging
import math
import uuid
from typing import Sequence

import numpy as np
from sklearn.neighbors import BallTree

from geosignal.models import WhatIfGrid

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default BTS signal radius in metres used to identify affected grid cells.
DEFAULT_SIGNAL_RADIUS_M: float = 5_000.0

# Earth radius used for haversine distance (metres).
_EARTH_RADIUS_M: float = 6_371_000.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def precompute_whatif_grid(
    region_id: str,
    candidate_coords: list[tuple[float, float]],
    candidate_ids: list[str],
    grid_cell_coords: np.ndarray,
    grid_cell_scores: np.ndarray,
    grid_resolution_m: int,
    signal_radius_m: float = DEFAULT_SIGNAL_RADIUS_M,
    coverage_improvement: float = 15.0,
    supabase_client=None,
) -> WhatIfGrid:
    """Precompute what-if simulation outcomes for a set of candidate BTS sites.

    For each candidate (and optionally a dense sample of manual scenarios),
    this function:
    1. Finds all grid cells within ``signal_radius_m`` of the candidate.
    2. Computes Coverage Score deltas by applying ``coverage_improvement``
       to cells that are not already >= 70.
    3. Computes summary metrics (pct_good_change, villages_newly_covered,
       new_coverage_score).
    4. Writes one row per scenario to ``whatif_grid`` if ``supabase_client``
       is provided; otherwise returns the rows for in-memory use.

    Parameters
    ----------
    region_id:
        Region identifier, e.g. ``"ntt"``.
    candidate_coords:
        List of (lat, lon) tuples for each BTS candidate scenario.
    candidate_ids:
        Scenario/candidate identifiers aligned with ``candidate_coords``.
    grid_cell_coords:
        (N, 2) numpy array of (lat, lon) for all grid cells in the region.
    grid_cell_scores:
        (N,) numpy array of current Coverage Scores (0–100) for each grid cell.
    grid_resolution_m:
        Integer grid resolution in metres (stored in WhatIfGrid and each row).
    signal_radius_m:
        Radius within which a BTS is assumed to improve coverage.
    coverage_improvement:
        Score delta added to grid cells within the signal radius (capped at 100).
    supabase_client:
        Optional Supabase client for persisting rows to ``whatif_grid`` table.

    Returns
    -------
    WhatIfGrid
        In-memory what-if grid loaded for use by Simulation_Engine.
    """
    if len(candidate_coords) != len(candidate_ids):
        raise ValueError(
            "candidate_coords and candidate_ids must have the same length."
        )

    # Build BallTree on grid cell coordinates (radians for haversine).
    grid_radians = np.radians(grid_cell_coords)
    tree = BallTree(grid_radians, metric="haversine")

    radius_rad = signal_radius_m / _EARTH_RADIUS_M

    whatif_rows: list[dict] = []
    scenario_centroids: list[tuple[float, float]] = []
    scenario_ids: list[str] = []

    for cand_id, (cand_lat, cand_lon) in zip(candidate_ids, candidate_coords):
        # Find grid cells within the signal radius.
        query_point = np.radians([[cand_lat, cand_lon]])
        indices = tree.query_radius(query_point, r=radius_rad)[0]

        affected_scores = grid_cell_scores[indices]

        # Compute metrics.
        n_total = len(grid_cell_scores)
        n_good_before = int(np.sum(grid_cell_scores >= 70))

        # Apply improvement — cells already at 100 stay at 100.
        after_scores = grid_cell_scores.copy()
        after_scores[indices] = np.clip(
            affected_scores + coverage_improvement, 0.0, 100.0
        )

        n_good_after = int(np.sum(after_scores >= 70))
        pct_good_change = float((n_good_after - n_good_before) / max(n_total, 1) * 100.0)

        # Villages newly covered: cells that crossed the 70 threshold.
        villages_newly_covered = max(0, n_good_after - n_good_before)

        # New coverage score at the candidate cell: nearest cell score after.
        snap_indices = tree.query(query_point, k=1)[1][0]
        new_coverage_score = float(after_scores[snap_indices[0]])

        snapped_lat = float(grid_cell_coords[snap_indices[0], 0])
        snapped_lon = float(grid_cell_coords[snap_indices[0], 1])

        # Delta coverage score = mean improvement in radius.
        delta_coverage_score = float(
            np.mean(after_scores[indices] - affected_scores)
            if len(indices) > 0 else 0.0
        )

        row = {
            "scenario_id": str(cand_id),
            "region_id": region_id,
            "candidate_id": str(cand_id),
            "snapped_lat": snapped_lat,
            "snapped_lon": snapped_lon,
            "grid_resolution_m": grid_resolution_m,
            "delta_coverage_score": delta_coverage_score,
            "pct_good_change": pct_good_change,
            "villages_newly_covered": villages_newly_covered,
            "new_coverage_score": new_coverage_score,
        }
        whatif_rows.append(row)
        scenario_centroids.append((snapped_lat, snapped_lon))
        scenario_ids.append(str(cand_id))

    # Persist rows when a Supabase client is available.
    if supabase_client is not None and whatif_rows:
        logger.info(
            "Upserting %d whatif_grid rows for region '%s'…",
            len(whatif_rows),
            region_id,
        )
        (
            supabase_client.table("whatif_grid")
            .upsert(whatif_rows, on_conflict="scenario_id")
            .execute()
        )
        logger.info(
            "Upserted %d whatif_grid rows for region '%s'.",
            len(whatif_rows),
            region_id,
        )
    else:
        logger.info(
            "Offline mode — not persisting %d whatif_grid rows for region '%s'.",
            len(whatif_rows),
            region_id,
        )

    # Build the in-memory WhatIfGrid.
    centroids_array = (
        np.array(scenario_centroids, dtype=np.float64)
        if scenario_centroids
        else np.empty((0, 2), dtype=np.float64)
    )
    spatial_index = BallTree(np.radians(centroids_array), metric="haversine") if len(centroids_array) > 0 else BallTree(np.zeros((1, 2)), metric="haversine")

    return WhatIfGrid(
        region_id=region_id,
        centroids=centroids_array,
        scenario_ids=scenario_ids,
        grid_resolution_m=grid_resolution_m,
        spatial_index=spatial_index,
    )


def build_whatif_grid_from_rows(
    region_id: str,
    rows: list[dict],
    grid_resolution_m: int = 100,
) -> WhatIfGrid:
    """Build a WhatIfGrid in-memory object from persisted ``whatif_grid`` table rows.

    Used by the Simulation_Engine to load the precomputed grid at startup
    (or in tests to inject a pre-built grid without database access).

    Parameters
    ----------
    region_id:
        Region identifier.
    rows:
        List of row dicts as stored in the ``whatif_grid`` table.
        Each row must contain ``scenario_id``, ``snapped_lat``, ``snapped_lon``.
    grid_resolution_m:
        Resolution to record in the WhatIfGrid object.

    Returns
    -------
    WhatIfGrid
    """
    scenario_ids: list[str] = []
    centroids: list[tuple[float, float]] = []

    for row in rows:
        if row.get("region_id", region_id) != region_id:
            continue
        scenario_ids.append(str(row["scenario_id"]))
        centroids.append((float(row["snapped_lat"]), float(row["snapped_lon"])))

    if centroids:
        centroids_array = np.array(centroids, dtype=np.float64)
        spatial_index = BallTree(np.radians(centroids_array), metric="haversine")
    else:
        centroids_array = np.empty((0, 2), dtype=np.float64)
        # BallTree requires at least 1 point; use a sentinel.
        spatial_index = BallTree(np.zeros((1, 2)), metric="haversine")

    return WhatIfGrid(
        region_id=region_id,
        centroids=centroids_array,
        scenario_ids=scenario_ids,
        grid_resolution_m=grid_resolution_m,
        spatial_index=spatial_index,
    )


def is_whatif_grid_populated(
    region_id: str,
    rows: list[dict],
) -> bool:
    """Return True if the whatif_grid rows contain at least one entry for region_id.

    Parameters
    ----------
    region_id:
        Region identifier to check.
    rows:
        List of whatif_grid table row dicts.
    """
    return any(row.get("region_id") == region_id for row in rows)
