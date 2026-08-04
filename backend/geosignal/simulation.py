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

import numpy as np

from geosignal.models import (
    HeatmapDelta,
    SimulationResult,
    UnavailableScenario,
)


MAX_SIMULATION_ELAPSED_MS: int = 3_000


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