"""Before/After simulation from precomputed GeoSignal AI data.

The Simulation Engine performs no live DEM computation, LOS analysis,
interpolation, or extrapolation. It only:

1. Looks up rows already stored in ``whatif_grid``.
2. Joins those rows to the corresponding baseline ``grid_cells``.
3. Formats the stored baseline and delta values as Before/After heatmaps.

Canonical response dataclasses are imported from ``geosignal.models``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from time import perf_counter_ns
from typing import Any, Protocol
from uuid import UUID
from sklearn.neighbors import BallTree

import numpy as np

from geosignal.models import (
    ComparisonPanel,
    DragDropResult,
    HeatmapDelta,
    OutsideExtentError,
    SimulationResult,
    UnavailableScenario,
    WhatIfGrid,
)

MAX_SIMULATION_ELAPSED_MS: int = 3_000
MAX_DRAG_DROP_ELAPSED_MS: int = 2_000

class SimulationDataError(ValueError):
    """Raised when persisted simulation data is incomplete or inconsistent."""


class SimulationLatencyError(RuntimeError):
    """Raised when a simulation exceeds the required latency budget."""


class SimulationStore(Protocol):
    """Persistence contract used by ``simulate_bts_placement``."""

    def get_candidate_scenario_rows(
        self,
        *,
        candidate_id: str,
        region_id: str,
    ) -> list[dict[str, Any]]:
        ...


class InMemorySimulationStore:
    """In-memory simulation data store for tests and local development.

    ``whatif_rows`` contain the Task 18 precomputed deltas.
    ``grid_cells`` contain the existing Coverage Score used for the
    Before heatmap.

    No spatial calculation is performed by this store.
    """

    def __init__(
        self,
        *,
        whatif_rows: Sequence[Mapping[str, Any]] = (),
        grid_cells: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        self._whatif_rows = [
            deepcopy(dict(row))
            for row in whatif_rows
        ]

        self._grid_cells: dict[str, dict[str, Any]] = {}

        for raw_cell in grid_cells:
            cell = deepcopy(dict(raw_cell))

            cell_id = _normalise_uuid(
                cell.get("cell_id"),
                field="grid_cells.cell_id",
            )

            if cell_id in self._grid_cells:
                raise ValueError(
                    f"Duplicate grid cell ID: {cell_id}"
                )

            self._grid_cells[cell_id] = cell

        self.lookup_count = 0

    def get_candidate_scenario_rows(
        self,
        *,
        candidate_id: str,
        region_id: str,
    ) -> list[dict[str, Any]]:
        self.lookup_count += 1

        matched_rows: list[dict[str, Any]] = []

        for raw_row in self._whatif_rows:
            if (
                str(raw_row.get("candidate_id"))
                != candidate_id
            ):
                continue

            if (
                str(raw_row.get("region_id"))
                != region_id
            ):
                continue

            row = deepcopy(raw_row)

            grid_cell_id = _normalise_uuid(
                row.get("grid_cell_id"),
                field="whatif_grid.grid_cell_id",
            )

            grid_cell = self._grid_cells.get(
                grid_cell_id
            )

            if grid_cell is not None:
                row["grid_cell"] = deepcopy(
                    grid_cell
                )

            matched_rows.append(row)

        return matched_rows


class SupabaseSimulationStore:
    """Supabase-backed implementation for Task 19.

    The query returns all affected what-if rows for one candidate and
    joins the baseline grid-cell coordinates and Coverage Scores.
    """

    def __init__(
        self,
        client: Any,
    ) -> None:
        self.client = client

    def get_candidate_scenario_rows(
        self,
        *,
        candidate_id: str,
        region_id: str,
    ) -> list[dict[str, Any]]:
        response = (
            self.client
            .table("whatif_grid")
            .select(
                "*,"
                "grid_cells!inner("
                "cell_id,"
                "lat,"
                "lon,"
                "coverage_score"
                ")"
            )
            .eq(
                "candidate_id",
                candidate_id,
            )
            .eq(
                "region_id",
                region_id,
            )
            .execute()
        )

        return [
            _normalise_supabase_join(row)
            for row in _response_rows(response)
        ]


def simulate_bts_placement(
    candidate_id: str,
    region_id: str,
    *,
    store: SimulationStore,
) -> SimulationResult | UnavailableScenario:
    """Return a Before/After simulation from precomputed rows only.

    Parameters
    ----------
    candidate_id:
        UUID of a ranked BTS candidate.

    region_id:
        Region containing the candidate and precomputed scenario.

    store:
        Read-only simulation data store.

    Returns
    -------
    SimulationResult | UnavailableScenario
        ``UnavailableScenario`` is returned when no precomputed rows exist.
        No fallback estimate, interpolation, extrapolation, DEM, or LOS
        computation is attempted.
    """
    started_at_ns = perf_counter_ns()

    normalised_candidate_id = _normalise_uuid(
        candidate_id,
        field="candidate_id",
    )

    normalised_region_id = _normalise_non_empty_string(
        region_id,
        field="region_id",
    )

    rows = store.get_candidate_scenario_rows(
        candidate_id=normalised_candidate_id,
        region_id=normalised_region_id,
    )

    if not rows:
        return UnavailableScenario(
            candidate_id=normalised_candidate_id,
            region_id=normalised_region_id,
            message=(
                "No precomputed what-if scenario is available for "
                f"candidate '{normalised_candidate_id}' in region "
                f"'{normalised_region_id}'. No estimate was computed."
            ),
        )

    (
        before_cells,
        after_cells,
        pct_good_change,
        villages_newly_covered,
        new_coverage_score,
    ) = _build_simulation_snapshots(
        rows=rows,
        expected_candidate_id=normalised_candidate_id,
        expected_region_id=normalised_region_id,
    )

    elapsed_ms = _elapsed_milliseconds(
        started_at_ns
    )

    if elapsed_ms > MAX_SIMULATION_ELAPSED_MS:
        raise SimulationLatencyError(
            "Before/After simulation exceeded the "
            f"{MAX_SIMULATION_ELAPSED_MS} ms latency budget: "
            f"{elapsed_ms} ms"
        )

    return SimulationResult(
        before_heatmap=HeatmapDelta(
            region_id=normalised_region_id,
            cells=before_cells,
            snapshot_label="before",
        ),
        after_heatmap=HeatmapDelta(
            region_id=normalised_region_id,
            cells=after_cells,
            snapshot_label="after",
        ),
        pct_good_change=pct_good_change,
        villages_newly_covered=villages_newly_covered,
        new_coverage_score=new_coverage_score,
        elapsed_ms=elapsed_ms,
    )


def _build_simulation_snapshots(
    *,
    rows: Sequence[Mapping[str, Any]],
    expected_candidate_id: str,
    expected_region_id: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    float,
    int,
    float,
]:
    """Validate persisted rows and create deterministic heatmap snapshots."""
    if not rows:
        raise SimulationDataError(
            "At least one precomputed row is required"
        )

    before_cells: list[dict[str, Any]] = []
    after_cells: list[dict[str, Any]] = []

    observed_grid_cell_ids: set[str] = set()
    observed_scenario_ids: set[str] = set()

    reference_pct_good_change: float | None = None
    reference_villages_newly_covered: int | None = None
    reference_new_coverage_score: float | None = None

    for raw_row in rows:
        row = dict(raw_row)

        required_fields = {
            "region_id",
            "scenario_id",
            "candidate_id",
            "grid_cell_id",
            "delta_coverage_score",
            "pct_good_change",
            "villages_newly_covered",
            "new_coverage_score",
        }

        missing_fields = sorted(
            required_fields.difference(row)
        )

        if missing_fields:
            raise SimulationDataError(
                "Precomputed what-if row is missing fields: "
                + ", ".join(missing_fields)
            )

        row_region_id = _normalise_non_empty_string(
            row["region_id"],
            field="whatif_grid.region_id",
        )

        row_candidate_id = _normalise_uuid(
            row["candidate_id"],
            field="whatif_grid.candidate_id",
        )

        scenario_id = _normalise_uuid(
            row["scenario_id"],
            field="whatif_grid.scenario_id",
        )

        grid_cell_id = _normalise_uuid(
            row["grid_cell_id"],
            field="whatif_grid.grid_cell_id",
        )

        if row_region_id != expected_region_id:
            raise SimulationDataError(
                "Precomputed row region does not match request"
            )

        if row_candidate_id != expected_candidate_id:
            raise SimulationDataError(
                "Precomputed row candidate does not match request"
            )

        # Task 18 uses candidate_id as scenario_id for ranked candidates.
        if scenario_id != expected_candidate_id:
            raise SimulationDataError(
                "Candidate scenario_id must equal candidate_id"
            )

        observed_scenario_ids.add(
            scenario_id
        )

        if grid_cell_id in observed_grid_cell_ids:
            raise SimulationDataError(
                "Duplicate grid-cell result in candidate scenario: "
                f"{grid_cell_id}"
            )

        observed_grid_cell_ids.add(
            grid_cell_id
        )

        grid_cell = _extract_joined_grid_cell(
            row
        )

        joined_cell_id = _normalise_uuid(
            grid_cell.get("cell_id"),
            field="grid_cells.cell_id",
        )

        if joined_cell_id != grid_cell_id:
            raise SimulationDataError(
                "Joined grid-cell ID does not match what-if row"
            )

        latitude = _finite_float(
            grid_cell.get("lat"),
            field="grid_cells.lat",
        )

        longitude = _finite_float(
            grid_cell.get("lon"),
            field="grid_cells.lon",
        )

        if not -90.0 <= latitude <= 90.0:
            raise SimulationDataError(
                "grid_cells.lat must be within [-90, 90]"
            )

        if not -180.0 <= longitude <= 180.0:
            raise SimulationDataError(
                "grid_cells.lon must be within [-180, 180]"
            )

        before_score = _coverage_score(
            grid_cell.get("coverage_score"),
            field="grid_cells.coverage_score",
        )

        delta_score = _finite_float(
            row["delta_coverage_score"],
            field="whatif_grid.delta_coverage_score",
        )

        after_score = before_score + delta_score

        if not -1e-9 <= after_score <= 100.0 + 1e-9:
            raise SimulationDataError(
                "Precomputed delta produces an after-score "
                "outside [0, 100]"
            )

        # Remove insignificant floating-point overflow around 0 or 100.
        after_score = float(
            np.clip(
                after_score,
                0.0,
                100.0,
            )
        )

        pct_good_change = _finite_float(
            row["pct_good_change"],
            field="whatif_grid.pct_good_change",
        )

        villages_newly_covered = (
            _non_negative_integer(
                row["villages_newly_covered"],
                field=(
                    "whatif_grid."
                    "villages_newly_covered"
                ),
            )
        )

        new_coverage_score = _coverage_score(
            row["new_coverage_score"],
            field="whatif_grid.new_coverage_score",
        )

        if reference_pct_good_change is None:
            reference_pct_good_change = (
                pct_good_change
            )
            reference_villages_newly_covered = (
                villages_newly_covered
            )
            reference_new_coverage_score = (
                new_coverage_score
            )
        else:
            if not np.isclose(
                pct_good_change,
                reference_pct_good_change,
            ):
                raise SimulationDataError(
                    "pct_good_change is inconsistent across "
                    "precomputed scenario rows"
                )

            if (
                villages_newly_covered
                != reference_villages_newly_covered
            ):
                raise SimulationDataError(
                    "villages_newly_covered is inconsistent "
                    "across precomputed scenario rows"
                )

            if not np.isclose(
                new_coverage_score,
                reference_new_coverage_score,
            ):
                raise SimulationDataError(
                    "new_coverage_score is inconsistent across "
                    "precomputed scenario rows"
                )

        common_cell_fields = {
            "cell_id": grid_cell_id,
            "lat": latitude,
            "lon": longitude,
        }

        before_cells.append(
            {
                **common_cell_fields,
                "coverage_score": before_score,
                "colour_tier": _colour_tier(
                    before_score
                ),
            }
        )

        after_cells.append(
            {
                **common_cell_fields,
                "coverage_score": after_score,
                "colour_tier": _colour_tier(
                    after_score
                ),
                "delta_coverage_score": (
                    delta_score
                ),
            }
        )

    if len(observed_scenario_ids) != 1:
        raise SimulationDataError(
            "Candidate lookup returned multiple scenario IDs"
        )

    before_cells.sort(
        key=lambda cell: cell["cell_id"]
    )

    after_cells.sort(
        key=lambda cell: cell["cell_id"]
    )

    assert reference_pct_good_change is not None
    assert reference_villages_newly_covered is not None
    assert reference_new_coverage_score is not None

    return (
        before_cells,
        after_cells,
        float(reference_pct_good_change),
        int(reference_villages_newly_covered),
        float(reference_new_coverage_score),
    )


def _extract_joined_grid_cell(
    row: Mapping[str, Any],
) -> dict[str, Any]:
    """Extract a grid-cell record from an in-memory or Supabase join."""
    joined = row.get("grid_cell")

    if joined is None:
        joined = row.get("grid_cells")

    if isinstance(joined, Sequence) and not isinstance(
        joined,
        (str, bytes, bytearray),
    ):
        joined_rows = list(joined)

        if len(joined_rows) != 1:
            raise SimulationDataError(
                "Each what-if row must join to exactly one grid cell"
            )

        joined = joined_rows[0]

    if not isinstance(joined, Mapping):
        raise SimulationDataError(
            "Precomputed row has no joined baseline grid cell"
        )

    return deepcopy(
        dict(joined)
    )


def _normalise_supabase_join(
    raw_row: Mapping[str, Any],
) -> dict[str, Any]:
    row = deepcopy(
        dict(raw_row)
    )

    if (
        "grid_cell" not in row
        and "grid_cells" in row
    ):
        row["grid_cell"] = row["grid_cells"]

    return row


def _colour_tier(
    score: float,
) -> str:
    """Return the design-specified heatmap tier."""
    if score >= 70.0:
        return "Green"

    if score >= 40.0:
        return "Yellow"

    return "Red"


def _coverage_score(
    value: Any,
    *,
    field: str,
) -> float:
    score = _finite_float(
        value,
        field=field,
    )

    if not 0.0 <= score <= 100.0:
        raise SimulationDataError(
            f"{field} must be within [0, 100]"
        )

    return score


def _finite_float(
    value: Any,
    *,
    field: str,
) -> float:
    try:
        result = float(value)
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise SimulationDataError(
            f"{field} must be numeric"
        ) from exc

    if not np.isfinite(result):
        raise SimulationDataError(
            f"{field} must be finite"
        )

    return result


def _non_negative_integer(
    value: Any,
    *,
    field: str,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise SimulationDataError(
            f"{field} must be a non-negative integer"
        )

    return value


def _normalise_non_empty_string(
    value: Any,
    *,
    field: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"{field} must be a string"
        )

    normalised = value.strip()

    if not normalised:
        raise ValueError(
            f"{field} cannot be empty"
        )

    return normalised


def _normalise_uuid(
    value: Any,
    *,
    field: str,
) -> str:
    try:
        return str(
            UUID(str(value))
        )
    except (
        TypeError,
        ValueError,
        AttributeError,
    ) as exc:
        raise ValueError(
            f"{field} must be a valid UUID"
        ) from exc


def _elapsed_milliseconds(
    started_at_ns: int,
) -> int:
    return int(
        (
            perf_counter_ns()
            - started_at_ns
        )
        / 1_000_000
    )


def _response_rows(
    response: Any,
) -> list[dict[str, Any]]:
    if hasattr(
        response,
        "data",
    ):
        data = response.data
    elif isinstance(
        response,
        Mapping,
    ):
        data = response.get(
            "data",
            [],
        )
    else:
        data = []

    return [
        deepcopy(dict(row))
        for row in (data or [])
    ]

def build_drag_drop_grid(
    *,
    region_id: str,
    cells: Sequence[Mapping[str, Any]],
    grid_resolution_m: int,
    top_candidate: Mapping[str, Any],
) -> WhatIfGrid:
    """Build the canonical WhatIfGrid used by drag-and-drop lookup.

    ``cells`` represent manual-placement scenarios produced by Task 18.
    Each row requires:

    - ``scenario_id``
    - ``lat``
    - ``lon``
    - ``coverage_score`` or ``new_coverage_score``
    - ``confidence_tag``

    Additional cell payload and top-candidate metadata are attached to the
    canonical WhatIfGrid instance without redefining that model.
    """
    normalised_region = _normalise_non_empty_string(
        region_id,
        field="region_id",
    )

    if (
        not isinstance(grid_resolution_m, int)
        or isinstance(grid_resolution_m, bool)
        or grid_resolution_m <= 0
    ):
        raise SimulationDataError(
            "grid_resolution_m must be a positive integer"
        )

    if isinstance(cells, (str, bytes, bytearray)):
        raise TypeError(
            "cells must be a sequence of mappings"
        )

    raw_cells = tuple(cells)

    if not raw_cells:
        raise SimulationDataError(
            "At least one precomputed what-if cell is required"
        )

    centroids: list[tuple[float, float]] = []
    scenario_ids: list[str] = []
    cell_payloads: list[dict[str, Any]] = []

    for index, raw_cell in enumerate(raw_cells):
        if not isinstance(raw_cell, Mapping):
            raise TypeError(
                "Every drag-and-drop cell must be a mapping"
            )

        cell = deepcopy(dict(raw_cell))

        scenario_id = _normalise_uuid(
            cell.get("scenario_id"),
            field=f"cells[{index}].scenario_id",
        )

        latitude = _finite_float(
            cell.get("lat"),
            field=f"cells[{index}].lat",
        )

        longitude = _finite_float(
            cell.get("lon"),
            field=f"cells[{index}].lon",
        )

        if not -90.0 <= latitude <= 90.0:
            raise SimulationDataError(
                f"cells[{index}].lat must be within [-90, 90]"
            )

        if not -180.0 <= longitude <= 180.0:
            raise SimulationDataError(
                f"cells[{index}].lon must be within [-180, 180]"
            )

        raw_score = cell.get(
            "coverage_score",
            cell.get("new_coverage_score"),
        )

        coverage_score = _coverage_score(
            raw_score,
            field=f"cells[{index}].coverage_score",
        )

        confidence_tag = _normalise_confidence_tag(
            cell.get("confidence_tag"),
            field=f"cells[{index}].confidence_tag",
        )

        centroids.append(
            (
                latitude,
                longitude,
            )
        )

        scenario_ids.append(
            scenario_id
        )

        cell_payloads.append(
            {
                "scenario_id": scenario_id,
                "coverage_score": coverage_score,
                "confidence_tag": confidence_tag,
            }
        )

    centroid_array = np.asarray(
        centroids,
        dtype=np.float64,
    )

    if len(
        np.unique(
            centroid_array,
            axis=0,
        )
    ) != len(centroid_array):
        raise SimulationDataError(
            "Drag-and-drop grid cannot contain duplicate centroids"
        )

    spatial_index = BallTree(
        centroid_array,
        metric="euclidean",
    )

    top_candidate_payload = (
        _normalise_top_candidate(
            top_candidate
        )
    )

    region_extent = {
        "min_lat": float(
            np.min(
                centroid_array[:, 0]
            )
        ),
        "max_lat": float(
            np.max(
                centroid_array[:, 0]
            )
        ),
        "min_lon": float(
            np.min(
                centroid_array[:, 1]
            )
        ),
        "max_lon": float(
            np.max(
                centroid_array[:, 1]
            )
        ),
    }

    grid = WhatIfGrid(
        region_id=normalised_region,
        centroids=centroid_array,
        scenario_ids=scenario_ids,
        grid_resolution_m=grid_resolution_m,
        spatial_index=spatial_index,
    )

    # WhatIfGrid is the canonical shared model. These sidecar attributes
    # contain Task 20 lookup metadata that are not canonical model fields.
    setattr(
        grid,
        "_drag_drop_cells",
        tuple(cell_payloads),
    )

    setattr(
        grid,
        "_top_candidate",
        top_candidate_payload,
    )

    setattr(
        grid,
        "_region_extent",
        region_extent,
    )

    return grid


def drag_drop_lookup(
    dropped_lat: float,
    dropped_lon: float,
    region_id: str,
    grid: WhatIfGrid,
    overlay_enabled: bool = False,
) -> DragDropResult | OutsideExtentError:
    """Serve a manual-placement result from the nearest precomputed cell.

    The dropped coordinate is never interpolated or extrapolated. A point
    within the rectangular region extent is snapped to the nearest grid
    centroid through the prebuilt BallTree.

    ``overlay_enabled`` is intentionally excluded from every Coverage Score
    operation. It is a presentation-only power/energy overlay toggle.
    """
    started_at_ns = perf_counter_ns()

    latitude = _finite_float(
        dropped_lat,
        field="dropped_lat",
    )

    longitude = _finite_float(
        dropped_lon,
        field="dropped_lon",
    )

    if not -90.0 <= latitude <= 90.0:
        raise ValueError(
            "dropped_lat must be within [-90, 90]"
        )

    if not -180.0 <= longitude <= 180.0:
        raise ValueError(
            "dropped_lon must be within [-180, 180]"
        )

    normalised_region = _normalise_non_empty_string(
        region_id,
        field="region_id",
    )

    if not isinstance(overlay_enabled, bool):
        raise TypeError(
            "overlay_enabled must be a boolean"
        )

    if not isinstance(grid, WhatIfGrid):
        raise TypeError(
            "grid must be the canonical WhatIfGrid"
        )

    if grid.region_id != normalised_region:
        raise SimulationDataError(
            "WhatIfGrid region does not match the active region"
        )

    centroids = np.asarray(
        grid.centroids,
        dtype=np.float64,
    )

    if (
        centroids.ndim != 2
        or centroids.shape[1] != 2
        or len(centroids) == 0
    ):
        raise SimulationDataError(
            "WhatIfGrid.centroids must have shape (N, 2)"
        )

    if not np.isfinite(centroids).all():
        raise SimulationDataError(
            "WhatIfGrid.centroids must contain finite coordinates"
        )

    if (
        not isinstance(grid.grid_resolution_m, int)
        or isinstance(grid.grid_resolution_m, bool)
        or grid.grid_resolution_m <= 0
    ):
        raise SimulationDataError(
            "WhatIfGrid.grid_resolution_m must be positive"
        )

    if len(grid.scenario_ids) != len(centroids):
        raise SimulationDataError(
            "WhatIfGrid scenario IDs must align with centroids"
        )

    cell_payloads = getattr(
        grid,
        "_drag_drop_cells",
        None,
    )

    if (
        not isinstance(cell_payloads, Sequence)
        or isinstance(
            cell_payloads,
            (str, bytes, bytearray),
        )
        or len(cell_payloads) != len(centroids)
    ):
        raise SimulationDataError(
            "WhatIfGrid is missing aligned drag-and-drop cell metadata"
        )

    top_candidate = getattr(
        grid,
        "_top_candidate",
        None,
    )

    if not isinstance(
        top_candidate,
        Mapping,
    ):
        raise SimulationDataError(
            "WhatIfGrid is missing top-candidate comparison metadata"
        )

    extent = getattr(
        grid,
        "_region_extent",
        None,
    )

    if not isinstance(extent, Mapping):
        extent = {
            "min_lat": float(
                np.min(centroids[:, 0])
            ),
            "max_lat": float(
                np.max(centroids[:, 0])
            ),
            "min_lon": float(
                np.min(centroids[:, 1])
            ),
            "max_lon": float(
                np.max(centroids[:, 1])
            ),
        }

    if (
        latitude < float(extent["min_lat"])
        or latitude > float(extent["max_lat"])
        or longitude < float(extent["min_lon"])
        or longitude > float(extent["max_lon"])
    ):
        return _outside_extent_result(
            dropped_lat=latitude,
            dropped_lon=longitude,
            region_id=normalised_region,
            extent=extent,
        )

    _, nearest_indices = (
        grid.spatial_index.query(
            np.asarray(
                [
                    [
                        latitude,
                        longitude,
                    ]
                ],
                dtype=np.float64,
            ),
            k=1,
        )
    )

    nearest_index = int(
        nearest_indices[0][0]
    )

    snapped_coordinate = (
        float(
            centroids[
                nearest_index,
                0,
            ]
        ),
        float(
            centroids[
                nearest_index,
                1,
            ]
        ),
    )

    cell_payload = cell_payloads[
        nearest_index
    ]

    if not isinstance(
        cell_payload,
        Mapping,
    ):
        raise SimulationDataError(
            "Nearest drag-and-drop cell metadata is invalid"
        )

    scenario_id = _normalise_uuid(
        cell_payload.get(
            "scenario_id"
        ),
        field="drag_drop_cell.scenario_id",
    )

    if scenario_id != _normalise_uuid(
        grid.scenario_ids[
            nearest_index
        ],
        field="WhatIfGrid.scenario_ids",
    ):
        raise SimulationDataError(
            "Nearest cell metadata does not match WhatIfGrid scenario ID"
        )

    coverage_score = _coverage_score(
        cell_payload.get(
            "coverage_score"
        ),
        field="drag_drop_cell.coverage_score",
    )

    confidence_tag = (
        _normalise_confidence_tag(
            cell_payload.get(
                "confidence_tag"
            ),
            field="drag_drop_cell.confidence_tag",
        )
    )

    model_score = _coverage_score(
        top_candidate.get(
            "model_score"
        ),
        field="top_candidate.model_score",
    )

    comparison = ComparisonPanel(
        manual_score=coverage_score,
        model_score=model_score,
        top_candidate_id=_normalise_uuid(
            top_candidate.get(
                "candidate_id"
            ),
            field="top_candidate.candidate_id",
        ),
        top_candidate_lat=_finite_float(
            top_candidate.get("lat"),
            field="top_candidate.lat",
        ),
        top_candidate_lon=_finite_float(
            top_candidate.get("lon"),
            field="top_candidate.lon",
        ),
        manual_wins=(
            coverage_score
            > model_score
        ),
    )

    # The overlay is presentation-only and deliberately unused.
    del overlay_enabled

    elapsed_ms = _elapsed_milliseconds(
        started_at_ns
    )

    if elapsed_ms > MAX_DRAG_DROP_ELAPSED_MS:
        raise SimulationLatencyError(
            "Drag-and-drop lookup exceeded the "
            f"{MAX_DRAG_DROP_ELAPSED_MS} ms latency budget: "
            f"{elapsed_ms} ms"
        )

    return DragDropResult(
        snapped_coordinate=snapped_coordinate,
        grid_resolution_m=(
            grid.grid_resolution_m
        ),
        coverage_score=coverage_score,
        confidence_tag=confidence_tag,
        vs_top_candidate=comparison,
        elapsed_ms=elapsed_ms,
    )


def _normalise_top_candidate(
    raw_candidate: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(
        raw_candidate,
        Mapping,
    ):
        raise TypeError(
            "top_candidate must be a mapping"
        )

    candidate = dict(
        raw_candidate
    )

    candidate_id = candidate.get(
        "candidate_id",
        candidate.get(
            "top_candidate_id"
        ),
    )

    latitude = candidate.get(
        "lat",
        candidate.get(
            "top_candidate_lat"
        ),
    )

    longitude = candidate.get(
        "lon",
        candidate.get(
            "top_candidate_lon"
        ),
    )

    model_score = candidate.get(
        "model_score",
        candidate.get(
            "coverage_score"
        ),
    )

    normalised_latitude = _finite_float(
        latitude,
        field="top_candidate.lat",
    )

    normalised_longitude = _finite_float(
        longitude,
        field="top_candidate.lon",
    )

    if not -90.0 <= normalised_latitude <= 90.0:
        raise SimulationDataError(
            "top_candidate.lat must be within [-90, 90]"
        )

    if not -180.0 <= normalised_longitude <= 180.0:
        raise SimulationDataError(
            "top_candidate.lon must be within [-180, 180]"
        )

    return {
        "candidate_id": _normalise_uuid(
            candidate_id,
            field="top_candidate.candidate_id",
        ),
        "lat": normalised_latitude,
        "lon": normalised_longitude,
        "model_score": _coverage_score(
            model_score,
            field="top_candidate.model_score",
        ),
    }


def _normalise_confidence_tag(
    value: Any,
    *,
    field: str,
) -> str:
    if not isinstance(value, str):
        raise SimulationDataError(
            f"{field} must be a string"
        )

    normalised = value.strip()

    if normalised not in {
        "Low",
        "Med",
        "High",
    }:
        raise SimulationDataError(
            f"{field} must be Low, Med, or High"
        )

    return normalised


def _outside_extent_result(
    *,
    dropped_lat: float,
    dropped_lon: float,
    region_id: str,
    extent: Mapping[str, Any],
) -> OutsideExtentError:
    normalised_extent = {
        "min_lat": float(
            extent["min_lat"]
        ),
        "max_lat": float(
            extent["max_lat"]
        ),
        "min_lon": float(
            extent["min_lon"]
        ),
        "max_lon": float(
            extent["max_lon"]
        ),
    }

    error = OutsideExtentError(
        dropped_lat=dropped_lat,
        dropped_lon=dropped_lon,
        region_id=region_id,
        message=(
            "Dropped coordinate is outside the precomputed grid "
            f"extent for region '{region_id}': "
            f"lat [{normalised_extent['min_lat']}, "
            f"{normalised_extent['max_lat']}], "
            f"lon [{normalised_extent['min_lon']}, "
            f"{normalised_extent['max_lon']}]. "
            "No interpolation or extrapolation was performed."
        ),
    )

    # OutsideExtentError is canonical and intentionally not redefined.
    # Attach the required extent payload without duplicating the model.
    setattr(
        error,
        "region_extent",
        normalised_extent,
    )

    return error