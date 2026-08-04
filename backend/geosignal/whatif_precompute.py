"""Offline what-if grid precomputation for GeoSignal AI.

The Simulation Engine never performs live DEM, LOS, interpolation, or
extrapolation work. This module prepares every scenario result before the
demo and persists the resulting cell-level deltas to ``whatif_grid``.

Each persisted row is uniquely identified by:

    (region_id, scenario_id, grid_cell_id)

Candidate scenarios use their candidate UUID as ``scenario_id``. Manual
placement scenarios receive deterministic UUIDs generated from the region
and source grid-cell ID.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID, uuid5

import numpy as np
from sklearn.neighbors import BallTree

from geosignal.models import BTSCandidate


EARTH_RADIUS_M: float = 6_371_008.8
GOOD_SCORE_THRESHOLD: float = 70.0

REQUIRED_REGION_IDS: tuple[str, ...] = (
    "ntt",
    "ntb",
    "central_kalimantan",
)

_MANUAL_SCENARIO_NAMESPACE = UUID(
    "c6b0cb77-59f6-4f83-8cb6-47c72b274bd9"
)


class MissingPrecomputedLOSError(ValueError):
    """Raised when a scenario-cell LOS result has not been precomputed."""


class PrecomputationIncompleteError(RuntimeError):
    """Raised when the what-if grid is not ready for simulation."""


@dataclass(frozen=True)
class GridCellInput:
    """One existing Coverage Score cell used by what-if precomputation."""

    grid_cell_id: str
    coordinate: tuple[float, float]
    coverage_score: float
    village_id: str | None = None


@dataclass(frozen=True)
class CandidateScenario:
    """A persisted candidate ID paired with its canonical BTSCandidate."""

    candidate_id: str
    candidate: BTSCandidate


@dataclass(frozen=True)
class RegionPrecomputeInput:
    """All inputs required to precompute one region."""

    region_id: str
    grid_cells: Sequence[GridCellInput]
    ranked_candidates: Sequence[CandidateScenario]
    los_lookup: "LOSLookup"
    grid_resolution_m: int
    signal_radius_m: float = 10_000.0
    maximum_gain: float = 35.0
    manual_sample_stride: int = 1


@dataclass(frozen=True)
class _ScenarioDefinition:
    scenario_id: str
    candidate_id: str | None
    coordinate: tuple[float, float]


class LOSLookup(Protocol):
    """Read-only interface for the LOS results produced by Task 12.1."""

    def get_los(
        self,
        *,
        region_id: str,
        candidate_coordinate: tuple[float, float],
        cell_coordinate: tuple[float, float],
    ) -> bool | None:
        ...


class WhatIfStore(Protocol):
    """Persistence contract for the precomputed what-if grid."""

    def upsert_whatif_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        ...

    def list_whatif_rows(
        self,
        *,
        region_id: str | None = None,
    ) -> list[dict[str, Any]]:
        ...


class InMemoryLOSLookup:
    """In-memory representation of the precomputed ``los_results`` table."""

    def __init__(
        self,
        rows: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        self._rows: dict[
            tuple[
                str,
                tuple[float, float],
                tuple[float, float],
            ],
            bool,
        ] = {}

        self.lookup_count = 0

        for raw_row in rows:
            row = dict(raw_row)

            region_id = _normalise_non_empty_string(
                row.get("region_id"),
                field="region_id",
            )

            candidate_coordinate = _normalise_coordinate(
                (
                    row.get("candidate_lat"),
                    row.get("candidate_lon"),
                ),
                field="candidate_coordinate",
            )

            cell_coordinate = _normalise_coordinate(
                (
                    row.get("cell_lat"),
                    row.get("cell_lon"),
                ),
                field="cell_coordinate",
            )

            los_clear = row.get("los_clear")

            if not isinstance(los_clear, bool):
                raise TypeError(
                    "los_clear must be a boolean"
                )

            key = _los_key(
                region_id,
                candidate_coordinate,
                cell_coordinate,
            )

            if key in self._rows:
                existing_los = self._rows[key]

                if existing_los != los_clear:
                    raise ValueError(
                        "Conflicting duplicate LOS result for "
                        f"{region_id}: "
                        f"{candidate_coordinate} -> {cell_coordinate}"
                    )

                # Identical duplicate rows are idempotent and safe to ignore.
                continue

            self._rows[key] = los_clear

    def get_los(
        self,
        *,
        region_id: str,
        candidate_coordinate: tuple[float, float],
        cell_coordinate: tuple[float, float],
    ) -> bool | None:
        self.lookup_count += 1

        return self._rows.get(
            _los_key(
                region_id,
                candidate_coordinate,
                cell_coordinate,
            )
        )


class InMemoryWhatIfStore:
    """Idempotent local what-if store for testing and offline development."""

    def __init__(self) -> None:
        self._rows: dict[
            tuple[str, str, str],
            dict[str, Any],
        ] = {}

    def upsert_whatif_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        stored_rows: list[dict[str, Any]] = []

        for raw_row in rows:
            row = deepcopy(dict(raw_row))

            key = (
                str(row["region_id"]),
                str(row["scenario_id"]),
                str(row["grid_cell_id"]),
            )

            self._rows[key] = row
            stored_rows.append(
                deepcopy(row)
            )

        return stored_rows

    def list_whatif_rows(
        self,
        *,
        region_id: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = [
            deepcopy(row)
            for row in self._rows.values()
        ]

        if region_id is None:
            return rows

        return [
            row
            for row in rows
            if row["region_id"] == region_id
        ]


class SupabaseWhatIfStore:
    """Supabase persistence adapter for the ``whatif_grid`` table."""

    def __init__(
        self,
        client: Any,
    ) -> None:
        self.client = client

    def upsert_whatif_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        payload = [
            deepcopy(dict(row))
            for row in rows
        ]

        if not payload:
            return []

        response = (
            self.client
            .table("whatif_grid")
            .upsert(
                payload,
                on_conflict=(
                    "region_id,"
                    "scenario_id,"
                    "grid_cell_id"
                ),
            )
            .execute()
        )

        response_rows = _response_rows(
            response
        )

        return (
            response_rows
            if response_rows
            else payload
        )

    def list_whatif_rows(
        self,
        *,
        region_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = (
            self.client
            .table("whatif_grid")
            .select("*")
        )

        if region_id is not None:
            query = query.eq(
                "region_id",
                region_id,
            )

        return _response_rows(
            query.execute()
        )


def precompute_region_whatif(
    *,
    region_id: str,
    grid_cells: Sequence[GridCellInput],
    ranked_candidates: Sequence[CandidateScenario],
    los_lookup: LOSLookup,
    store: WhatIfStore,
    grid_resolution_m: int,
    signal_radius_m: float = 10_000.0,
    maximum_gain: float = 35.0,
    manual_sample_stride: int = 1,
) -> list[dict[str, Any]]:
    """Precompute candidate and dense manual-placement scenarios.

    No result is persisted until every required LOS lookup succeeds. This
    prevents a partially populated region from appearing ready to the
    Simulation Engine.

    Candidate scenarios use ``candidate_id`` as their ``scenario_id``.
    Manual scenarios are generated from every Nth grid-cell centroid, where
    N is controlled by ``manual_sample_stride`` and defaults to 1.
    """
    normalised_region = _normalise_non_empty_string(
        region_id,
        field="region_id",
    )

    cells = _validate_grid_cells(
        grid_cells
    )

    resolution = _positive_integer(
        grid_resolution_m,
        field="grid_resolution_m",
    )

    radius = _positive_finite_float(
        signal_radius_m,
        field="signal_radius_m",
    )

    gain = _positive_finite_float(
        maximum_gain,
        field="maximum_gain",
    )

    stride = _positive_integer(
        manual_sample_stride,
        field="manual_sample_stride",
    )

    scenarios = _build_scenarios(
        region_id=normalised_region,
        grid_cells=cells,
        ranked_candidates=ranked_candidates,
        manual_sample_stride=stride,
    )

    coordinates = np.asarray(
        [
            cell.coordinate
            for cell in cells
        ],
        dtype=np.float64,
    )

    coverage_scores = np.asarray(
        [
            cell.coverage_score
            for cell in cells
        ],
        dtype=np.float64,
    )

    spatial_index = BallTree(
        np.radians(coordinates),
        metric="haversine",
    )

    staged_rows: list[
        dict[str, Any]
    ] = []

    candidate_ids_with_rows: set[str] = set()

    for scenario in scenarios:
        scenario_rows = _compute_scenario_rows(
            region_id=normalised_region,
            scenario=scenario,
            grid_cells=cells,
            coordinates=coordinates,
            coverage_scores=coverage_scores,
            spatial_index=spatial_index,
            los_lookup=los_lookup,
            grid_resolution_m=resolution,
            signal_radius_m=radius,
            maximum_gain=gain,
        )

        if not scenario_rows:
            raise PrecomputationIncompleteError(
                "Scenario produced no what-if rows: "
                f"{scenario.scenario_id}"
            )

        staged_rows.extend(
            scenario_rows
        )

        if scenario.candidate_id is not None:
            candidate_ids_with_rows.add(
                scenario.candidate_id
            )

    expected_candidate_ids = {
        _normalise_uuid(
            item.candidate_id,
            field="candidate_id",
        )
        for item in ranked_candidates
    }

    missing_candidates = (
        expected_candidate_ids
        - candidate_ids_with_rows
    )

    if missing_candidates:
        raise PrecomputationIncompleteError(
            "Ranked candidates missing what-if rows: "
            + ", ".join(
                sorted(missing_candidates)
            )
        )

    if not staged_rows:
        raise PrecomputationIncompleteError(
            f"No what-if rows produced for {normalised_region}"
        )

    return store.upsert_whatif_rows(
        staged_rows
    )


def precompute_all_regions(
    region_inputs: Mapping[
        str,
        RegionPrecomputeInput,
    ],
    *,
    store: WhatIfStore,
) -> dict[str, list[dict[str, Any]]]:
    """Run the complete offline batch for all required demo regions."""
    missing_regions = (
        set(REQUIRED_REGION_IDS)
        - set(region_inputs)
    )

    if missing_regions:
        raise PrecomputationIncompleteError(
            "Missing required precomputation regions: "
            + ", ".join(
                sorted(missing_regions)
            )
        )

    results: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for region_id in REQUIRED_REGION_IDS:
        region_input = region_inputs[
            region_id
        ]

        if region_input.region_id != region_id:
            raise ValueError(
                "Region input key does not match "
                f"RegionPrecomputeInput.region_id: {region_id}"
            )

        rows = precompute_region_whatif(
            region_id=region_input.region_id,
            grid_cells=region_input.grid_cells,
            ranked_candidates=(
                region_input.ranked_candidates
            ),
            los_lookup=region_input.los_lookup,
            store=store,
            grid_resolution_m=(
                region_input.grid_resolution_m
            ),
            signal_radius_m=(
                region_input.signal_radius_m
            ),
            maximum_gain=(
                region_input.maximum_gain
            ),
            manual_sample_stride=(
                region_input.manual_sample_stride
            ),
        )

        if not rows:
            raise PrecomputationIncompleteError(
                f"whatif_grid is empty for {region_id}"
            )

        results[region_id] = rows

    return results


def assert_precomputation_ready(
    *,
    store: WhatIfStore,
    candidate_ids_by_region: Mapping[
        str,
        Sequence[str],
    ],
) -> None:
    """Assert Task 18 artifacts are ready before Tasks 19–20 run."""
    for region_id in REQUIRED_REGION_IDS:
        rows = store.list_whatif_rows(
            region_id=region_id
        )

        if not rows:
            raise PrecomputationIncompleteError(
                "whatif_grid is empty for required "
                f"region: {region_id}"
            )

        present_candidate_ids = {
            str(row["candidate_id"])
            for row in rows
            if row.get("candidate_id")
            is not None
        }

        expected_candidate_ids = {
            _normalise_uuid(
                candidate_id,
                field="candidate_id",
            )
            for candidate_id
            in candidate_ids_by_region.get(
                region_id,
                (),
            )
        }

        missing = (
            expected_candidate_ids
            - present_candidate_ids
        )

        if missing:
            raise PrecomputationIncompleteError(
                "Candidates without what-if entries "
                f"in {region_id}: "
                + ", ".join(
                    sorted(missing)
                )
            )


def _build_scenarios(
    *,
    region_id: str,
    grid_cells: Sequence[GridCellInput],
    ranked_candidates: Sequence[CandidateScenario],
    manual_sample_stride: int,
) -> list[_ScenarioDefinition]:
    scenarios: list[
        _ScenarioDefinition
    ] = []

    scenario_ids: set[str] = set()

    for item in ranked_candidates:
        if not isinstance(
            item,
            CandidateScenario,
        ):
            raise TypeError(
                "ranked_candidates must contain "
                "CandidateScenario objects"
            )

        if not isinstance(
            item.candidate,
            BTSCandidate,
        ):
            raise TypeError(
                "CandidateScenario.candidate must "
                "be a BTSCandidate"
            )

        candidate_id = _normalise_uuid(
            item.candidate_id,
            field="candidate_id",
        )

        if item.candidate.los_validated is not True:
            raise ValueError(
                "Every ranked BTSCandidate must have "
                "los_validated=True"
            )

        coordinate = _normalise_coordinate(
            item.candidate.coordinate,
            field="candidate.coordinate",
        )

        if candidate_id in scenario_ids:
            raise ValueError(
                "Duplicate candidate scenario ID: "
                f"{candidate_id}"
            )

        scenario_ids.add(
            candidate_id
        )

        scenarios.append(
            _ScenarioDefinition(
                scenario_id=candidate_id,
                candidate_id=candidate_id,
                coordinate=coordinate,
            )
        )

    for cell in grid_cells[
        ::manual_sample_stride
    ]:
        manual_scenario_id = str(
            uuid5(
                _MANUAL_SCENARIO_NAMESPACE,
                (
                    f"{region_id}:"
                    f"{cell.grid_cell_id}"
                ),
            )
        )

        if manual_scenario_id in scenario_ids:
            raise ValueError(
                "Manual scenario ID collided with "
                f"candidate scenario: {manual_scenario_id}"
            )

        scenario_ids.add(
            manual_scenario_id
        )

        scenarios.append(
            _ScenarioDefinition(
                scenario_id=manual_scenario_id,
                candidate_id=None,
                coordinate=cell.coordinate,
            )
        )

    return scenarios


def _compute_scenario_rows(
    *,
    region_id: str,
    scenario: _ScenarioDefinition,
    grid_cells: Sequence[GridCellInput],
    coordinates: np.ndarray,
    coverage_scores: np.ndarray,
    spatial_index: BallTree,
    los_lookup: LOSLookup,
    grid_resolution_m: int,
    signal_radius_m: float,
    maximum_gain: float,
) -> list[dict[str, Any]]:
    scenario_radians = np.radians(
        np.asarray(
            [scenario.coordinate],
            dtype=np.float64,
        )
    )

    neighbour_indices, neighbour_distances = (
        spatial_index.query_radius(
            scenario_radians,
            r=(
                signal_radius_m
                / EARTH_RADIUS_M
            ),
            return_distance=True,
            sort_results=True,
        )
    )

    affected_indices = np.asarray(
        neighbour_indices[0],
        dtype=np.int64,
    )

    affected_distances_m = (
        np.asarray(
            neighbour_distances[0],
            dtype=np.float64,
        )
        * EARTH_RADIUS_M
    )

    if len(affected_indices) == 0:
        raise PrecomputationIncompleteError(
            "Scenario has no grid cells within "
            f"signal radius: {scenario.scenario_id}"
        )

    after_scores = coverage_scores.copy()

    for cell_index, distance_m in zip(
        affected_indices,
        affected_distances_m,
        strict=True,
    ):
        cell = grid_cells[
            int(cell_index)
        ]

        los_clear = los_lookup.get_los(
            region_id=region_id,
            candidate_coordinate=(
                scenario.coordinate
            ),
            cell_coordinate=cell.coordinate,
        )

        if los_clear is None:
            raise MissingPrecomputedLOSError(
                "Missing precomputed LOS result for "
                f"region={region_id}, "
                f"scenario={scenario.scenario_id}, "
                f"cell={cell.grid_cell_id}"
            )

        if los_clear:
            distance_factor = max(
                0.0,
                1.0
                - (
                    float(distance_m)
                    / signal_radius_m
                ),
            )

            projected_gain = (
                maximum_gain
                * distance_factor
            )

            after_scores[cell_index] = min(
                100.0,
                float(
                    coverage_scores[cell_index]
                )
                + projected_gain,
            )

    pct_good_change = _percentage_good_change(
        before_scores=coverage_scores,
        after_scores=after_scores,
    )

    villages_newly_covered = (
        _count_villages_newly_covered(
            grid_cells=grid_cells,
            before_scores=coverage_scores,
            after_scores=after_scores,
        )
    )

    nearest_distance, nearest_index = (
        spatial_index.query(
            scenario_radians,
            k=1,
        )
    )

    del nearest_distance

    snapped_index = int(
        nearest_index[0][0]
    )

    snapped_latitude = float(
        coordinates[snapped_index][0]
    )
    snapped_longitude = float(
        coordinates[snapped_index][1]
    )

    new_coverage_score = float(
        after_scores[snapped_index]
    )

    rows: list[
        dict[str, Any]
    ] = []

    for cell_index in affected_indices:
        integer_index = int(
            cell_index
        )

        cell = grid_cells[
            integer_index
        ]

        delta = float(
            after_scores[integer_index]
            - coverage_scores[integer_index]
        )

        row = {
            "region_id": region_id,
            "scenario_id": (
                scenario.scenario_id
            ),
            "grid_cell_id": (
                cell.grid_cell_id
            ),
            "candidate_id": (
                scenario.candidate_id
            ),
            "snapped_lat": (
                snapped_latitude
            ),
            "snapped_lon": (
                snapped_longitude
            ),
            "grid_resolution_m": (
                grid_resolution_m
            ),
            "delta_coverage_score": (
                delta
            ),
            "pct_good_change": (
                pct_good_change
            ),
            "villages_newly_covered": (
                villages_newly_covered
            ),
            "new_coverage_score": (
                new_coverage_score
            ),
        }

        _validate_output_row(
            row
        )

        rows.append(
            row
        )

    return rows


def _percentage_good_change(
    *,
    before_scores: np.ndarray,
    after_scores: np.ndarray,
) -> float:
    before_percentage = float(
        np.mean(
            before_scores
            >= GOOD_SCORE_THRESHOLD
        )
        * 100.0
    )

    after_percentage = float(
        np.mean(
            after_scores
            >= GOOD_SCORE_THRESHOLD
        )
        * 100.0
    )

    return (
        after_percentage
        - before_percentage
    )


def _count_villages_newly_covered(
    *,
    grid_cells: Sequence[GridCellInput],
    before_scores: np.ndarray,
    after_scores: np.ndarray,
) -> int:
    village_indices: dict[
        str,
        list[int],
    ] = {}

    for index, cell in enumerate(
        grid_cells
    ):
        if cell.village_id is None:
            continue

        village_indices.setdefault(
            cell.village_id,
            [],
        ).append(index)

    newly_covered = 0

    for indices in (
        village_indices.values()
    ):
        had_good_coverage_before = bool(
            np.any(
                before_scores[indices]
                >= GOOD_SCORE_THRESHOLD
            )
        )

        has_good_coverage_after = bool(
            np.any(
                after_scores[indices]
                >= GOOD_SCORE_THRESHOLD
            )
        )

        if (
            not had_good_coverage_before
            and has_good_coverage_after
        ):
            newly_covered += 1

    return newly_covered


def _validate_grid_cells(
    grid_cells: Sequence[GridCellInput],
) -> tuple[GridCellInput, ...]:
    if isinstance(
        grid_cells,
        (str, bytes),
    ):
        raise TypeError(
            "grid_cells must be a sequence "
            "of GridCellInput objects"
        )

    cells = tuple(
        grid_cells
    )

    if not cells:
        raise ValueError(
            "grid_cells cannot be empty"
        )

    validated: list[
        GridCellInput
    ] = []

    observed_ids: set[str] = set()

    for cell in cells:
        if not isinstance(
            cell,
            GridCellInput,
        ):
            raise TypeError(
                "grid_cells must contain "
                "GridCellInput objects"
            )

        grid_cell_id = _normalise_uuid(
            cell.grid_cell_id,
            field="grid_cell_id",
        )

        if grid_cell_id in observed_ids:
            raise ValueError(
                "Duplicate grid_cell_id: "
                f"{grid_cell_id}"
            )

        observed_ids.add(
            grid_cell_id
        )

        coordinate = _normalise_coordinate(
            cell.coordinate,
            field="grid_cell.coordinate",
        )

        coverage_score = float(
            cell.coverage_score
        )

        if (
            not np.isfinite(
                coverage_score
            )
            or not (
                0.0
                <= coverage_score
                <= 100.0
            )
        ):
            raise ValueError(
                "coverage_score must be finite "
                "and within [0, 100]"
            )

        village_id = cell.village_id

        if village_id is not None:
            village_id = (
                _normalise_non_empty_string(
                    village_id,
                    field="village_id",
                )
            )

        validated.append(
            GridCellInput(
                grid_cell_id=grid_cell_id,
                coordinate=coordinate,
                coverage_score=(
                    coverage_score
                ),
                village_id=village_id,
            )
        )

    return tuple(
        validated
    )


def _validate_output_row(
    row: Mapping[str, Any],
) -> None:
    numeric_fields = (
        "snapped_lat",
        "snapped_lon",
        "delta_coverage_score",
        "pct_good_change",
        "new_coverage_score",
    )

    for field in numeric_fields:
        value = float(
            row[field]
        )

        if not np.isfinite(value):
            raise ValueError(
                f"{field} must be finite"
            )

    if not (
        0.0
        <= float(
            row["new_coverage_score"]
        )
        <= 100.0
    ):
        raise ValueError(
            "new_coverage_score must be "
            "within [0, 100]"
        )

    if (
        not isinstance(
            row["villages_newly_covered"],
            int,
        )
        or row["villages_newly_covered"]
        < 0
    ):
        raise ValueError(
            "villages_newly_covered must "
            "be a non-negative integer"
        )


def _los_key(
    region_id: str,
    candidate_coordinate: tuple[float, float],
    cell_coordinate: tuple[float, float],
) -> tuple[
    str,
    tuple[float, float],
    tuple[float, float],
]:
    return (
        region_id,
        _rounded_coordinate(
            candidate_coordinate
        ),
        _rounded_coordinate(
            cell_coordinate
        ),
    )


def _rounded_coordinate(
    coordinate: tuple[float, float],
) -> tuple[float, float]:
    return (
        round(
            float(coordinate[0]),
            7,
        ),
        round(
            float(coordinate[1]),
            7,
        ),
    )


def _normalise_coordinate(
    coordinate: Sequence[Any],
    *,
    field: str,
) -> tuple[float, float]:
    if (
        isinstance(
            coordinate,
            (str, bytes),
        )
        or len(coordinate) != 2
    ):
        raise ValueError(
            f"{field} must contain "
            "(latitude, longitude)"
        )

    latitude = float(
        coordinate[0]
    )
    longitude = float(
        coordinate[1]
    )

    if not np.isfinite(
        [latitude, longitude]
    ).all():
        raise ValueError(
            f"{field} must contain "
            "finite coordinates"
        )

    if not (
        -90.0
        <= latitude
        <= 90.0
    ):
        raise ValueError(
            f"{field} latitude is outside "
            "[-90, 90]"
        )

    if not (
        -180.0
        <= longitude
        <= 180.0
    ):
        raise ValueError(
            f"{field} longitude is outside "
            "[-180, 180]"
        )

    return (
        latitude,
        longitude,
    )


def _normalise_non_empty_string(
    value: Any,
    *,
    field: str,
) -> str:
    if not isinstance(
        value,
        str,
    ):
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


def _positive_integer(
    value: Any,
    *,
    field: str,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
    ):
        raise ValueError(
            f"{field} must be a positive integer"
        )

    return value


def _positive_finite_float(
    value: Any,
    *,
    field: str,
) -> float:
    result = float(
        value
    )

    if (
        not np.isfinite(result)
        or result <= 0.0
    ):
        raise ValueError(
            f"{field} must be positive and finite"
        )

    return result


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