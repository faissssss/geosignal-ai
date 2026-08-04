"""Tests for offline what-if grid precomputation."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from geosignal.models import BTSCandidate
from geosignal.whatif_precompute import (
    REQUIRED_REGION_IDS,
    CandidateScenario,
    GridCellInput,
    InMemoryLOSLookup,
    InMemoryWhatIfStore,
    MissingPrecomputedLOSError,
    PrecomputationIncompleteError,
    RegionPrecomputeInput,
    SupabaseWhatIfStore,
    assert_precomputation_ready,
    precompute_all_regions,
    precompute_region_whatif,
)


def _grid(
    *,
    latitude_offset: float = 0.0,
    longitude_offset: float = 0.0,
) -> list[GridCellInput]:
    return [
        GridCellInput(
            grid_cell_id=str(uuid4()),
            coordinate=(
                -10.000 + latitude_offset,
                123.000 + longitude_offset,
            ),
            coverage_score=45.0,
            village_id="village-a",
        ),
        GridCellInput(
            grid_cell_id=str(uuid4()),
            coordinate=(
                -10.005 + latitude_offset,
                123.005 + longitude_offset,
            ),
            coverage_score=65.0,
            village_id="village-a",
        ),
        GridCellInput(
            grid_cell_id=str(uuid4()),
            coordinate=(
                -10.010 + latitude_offset,
                123.010 + longitude_offset,
            ),
            coverage_score=35.0,
            village_id="village-b",
        ),
        GridCellInput(
            grid_cell_id=str(uuid4()),
            coordinate=(
                -10.015 + latitude_offset,
                123.015 + longitude_offset,
            ),
            coverage_score=80.0,
            village_id="village-c",
        ),
    ]


def _candidate(
    coordinate: tuple[float, float],
    *,
    candidate_id: str | None = None,
) -> CandidateScenario:
    return CandidateScenario(
        candidate_id=(
            str(uuid4())
            if candidate_id is None
            else candidate_id
        ),
        candidate=BTSCandidate(
            coordinate=coordinate,
            expected_improvement=25.0,
            los_validated=True,
            confidence_tag="High",
            shap_values={
                "elevation_m": 1.0,
            },
            rank=1,
            model_version="ahp-v1.0.0",
            scoring_run_id=str(uuid4()),
        ),
    )


def _los_rows(
    *,
    region_id: str,
    scenario_coordinates: list[
        tuple[float, float]
    ],
    grid_cells: list[GridCellInput],
    clear: bool = True,
) -> list[dict]:
    return [
        {
            "region_id": region_id,
            "candidate_lat": (
                scenario_coordinate[0]
            ),
            "candidate_lon": (
                scenario_coordinate[1]
            ),
            "cell_lat": (
                cell.coordinate[0]
            ),
            "cell_lon": (
                cell.coordinate[1]
            ),
            "los_clear": clear,
        }
        for scenario_coordinate
        in scenario_coordinates
        for cell in grid_cells
    ]


def _scenario_coordinates(
    candidate: CandidateScenario,
    grid_cells: list[GridCellInput],
) -> list[tuple[float, float]]:
    return [
        candidate.candidate.coordinate,
        *[
            cell.coordinate
            for cell in grid_cells
        ],
    ]


def _region_input(
    region_id: str,
    *,
    latitude_offset: float = 0.0,
    longitude_offset: float = 0.0,
) -> tuple[
    RegionPrecomputeInput,
    CandidateScenario,
]:
    grid_cells = _grid(
        latitude_offset=latitude_offset,
        longitude_offset=longitude_offset,
    )

    candidate = _candidate(
        grid_cells[0].coordinate
    )

    los_lookup = InMemoryLOSLookup(
        _los_rows(
            region_id=region_id,
            scenario_coordinates=(
                _scenario_coordinates(
                    candidate,
                    grid_cells,
                )
            ),
            grid_cells=grid_cells,
        )
    )

    return (
        RegionPrecomputeInput(
            region_id=region_id,
            grid_cells=grid_cells,
            ranked_candidates=[
                candidate
            ],
            los_lookup=los_lookup,
            grid_resolution_m=250,
            signal_radius_m=5_000.0,
            maximum_gain=40.0,
            manual_sample_stride=1,
        ),
        candidate,
    )


def test_candidate_and_manual_scenarios_are_persisted() -> None:
    region_id = "ntt"
    grid_cells = _grid()
    candidate = _candidate(
        grid_cells[0].coordinate
    )

    los_lookup = InMemoryLOSLookup(
        _los_rows(
            region_id=region_id,
            scenario_coordinates=(
                _scenario_coordinates(
                    candidate,
                    grid_cells,
                )
            ),
            grid_cells=grid_cells,
        )
    )

    store = InMemoryWhatIfStore()

    rows = precompute_region_whatif(
        region_id=region_id,
        grid_cells=grid_cells,
        ranked_candidates=[
            candidate
        ],
        los_lookup=los_lookup,
        store=store,
        grid_resolution_m=250,
        signal_radius_m=5_000.0,
        maximum_gain=40.0,
    )

    assert rows
    assert len(store.list_whatif_rows()) == len(rows)

    assert any(
        row["candidate_id"]
        == candidate.candidate_id
        for row in rows
    )

    assert any(
        row["candidate_id"] is None
        for row in rows
    )


def test_rows_have_unique_composite_keys() -> None:
    region_input, _ = _region_input(
        "ntt"
    )
    store = InMemoryWhatIfStore()

    rows = precompute_region_whatif(
        region_id=region_input.region_id,
        grid_cells=region_input.grid_cells,
        ranked_candidates=(
            region_input.ranked_candidates
        ),
        los_lookup=region_input.los_lookup,
        store=store,
        grid_resolution_m=250,
        signal_radius_m=5_000.0,
    )

    keys = {
        (
            row["region_id"],
            row["scenario_id"],
            row["grid_cell_id"],
        )
        for row in rows
    }

    assert len(keys) == len(rows)


def test_all_required_metrics_are_finite() -> None:
    region_input, _ = _region_input(
        "ntt"
    )
    store = InMemoryWhatIfStore()

    rows = precompute_region_whatif(
        region_id=region_input.region_id,
        grid_cells=region_input.grid_cells,
        ranked_candidates=(
            region_input.ranked_candidates
        ),
        los_lookup=region_input.los_lookup,
        store=store,
        grid_resolution_m=250,
        signal_radius_m=5_000.0,
    )

    for row in rows:
        assert np.isfinite(
            row["delta_coverage_score"]
        )
        assert np.isfinite(
            row["pct_good_change"]
        )
        assert np.isfinite(
            row["new_coverage_score"]
        )
        assert (
            row["villages_newly_covered"]
            >= 0
        )
        assert (
            0.0
            <= row["new_coverage_score"]
            <= 100.0
        )


def test_blocked_los_produces_zero_delta() -> None:
    region_id = "ntt"
    grid_cells = _grid()
    candidate = _candidate(
        grid_cells[0].coordinate
    )

    los_lookup = InMemoryLOSLookup(
        _los_rows(
            region_id=region_id,
            scenario_coordinates=(
                _scenario_coordinates(
                    candidate,
                    grid_cells,
                )
            ),
            grid_cells=grid_cells,
            clear=False,
        )
    )

    rows = precompute_region_whatif(
        region_id=region_id,
        grid_cells=grid_cells,
        ranked_candidates=[
            candidate
        ],
        los_lookup=los_lookup,
        store=InMemoryWhatIfStore(),
        grid_resolution_m=250,
        signal_radius_m=5_000.0,
    )

    assert all(
        row["delta_coverage_score"]
        == 0.0
        for row in rows
    )


def test_missing_los_fails_before_any_rows_are_persisted() -> None:
    region_id = "ntt"
    grid_cells = _grid()
    candidate = _candidate(
        grid_cells[0].coordinate
    )
    store = InMemoryWhatIfStore()

    with pytest.raises(
        MissingPrecomputedLOSError,
        match="Missing precomputed LOS",
    ):
        precompute_region_whatif(
            region_id=region_id,
            grid_cells=grid_cells,
            ranked_candidates=[
                candidate
            ],
            los_lookup=(
                InMemoryLOSLookup()
            ),
            store=store,
            grid_resolution_m=250,
            signal_radius_m=5_000.0,
        )

    assert (
        store.list_whatif_rows()
        == []
    )


def test_candidate_without_los_validation_is_rejected() -> None:
    grid_cells = _grid()

    invalid_candidate = CandidateScenario(
        candidate_id=str(uuid4()),
        candidate=BTSCandidate(
            coordinate=(
                grid_cells[0].coordinate
            ),
            expected_improvement=10.0,
            los_validated=False,
            confidence_tag="Low",
            shap_values={},
            rank=1,
            model_version="ahp-v1.0.0",
            scoring_run_id=str(uuid4()),
        ),
    )

    with pytest.raises(
        ValueError,
        match="los_validated=True",
    ):
        precompute_region_whatif(
            region_id="ntt",
            grid_cells=grid_cells,
            ranked_candidates=[
                invalid_candidate
            ],
            los_lookup=(
                InMemoryLOSLookup()
            ),
            store=(
                InMemoryWhatIfStore()
            ),
            grid_resolution_m=250,
        )


def test_default_manual_sampling_uses_every_grid_cell() -> None:
    region_input, candidate = _region_input(
        "ntt"
    )
    store = InMemoryWhatIfStore()

    precompute_region_whatif(
        region_id=region_input.region_id,
        grid_cells=region_input.grid_cells,
        ranked_candidates=[
            candidate
        ],
        los_lookup=region_input.los_lookup,
        store=store,
        grid_resolution_m=250,
        signal_radius_m=5_000.0,
        manual_sample_stride=1,
    )

    manual_scenario_ids = {
        row["scenario_id"]
        for row in store.list_whatif_rows()
        if row["candidate_id"] is None
    }

    assert len(
        manual_scenario_ids
    ) == len(
        region_input.grid_cells
    )


def test_projected_scores_are_clipped_to_one_hundred() -> None:
    region_id = "ntt"

    grid_cells = [
        GridCellInput(
            grid_cell_id=str(uuid4()),
            coordinate=(-10.0, 123.0),
            coverage_score=99.0,
            village_id="village-a",
        )
    ]

    candidate = _candidate(
        grid_cells[0].coordinate
    )

    los_lookup = InMemoryLOSLookup(
        _los_rows(
            region_id=region_id,
            scenario_coordinates=(
                _scenario_coordinates(
                    candidate,
                    grid_cells,
                )
            ),
            grid_cells=grid_cells,
        )
    )

    rows = precompute_region_whatif(
        region_id=region_id,
        grid_cells=grid_cells,
        ranked_candidates=[
            candidate
        ],
        los_lookup=los_lookup,
        store=InMemoryWhatIfStore(),
        grid_resolution_m=100,
        signal_radius_m=1_000.0,
        maximum_gain=50.0,
    )

    assert all(
        row["new_coverage_score"]
        <= 100.0
        for row in rows
    )

    assert all(
        row["delta_coverage_score"]
        <= 1.0
        for row in rows
    )


def test_good_percentage_and_village_metrics_increase() -> None:
    region_input, candidate = _region_input(
        "ntt"
    )

    rows = precompute_region_whatif(
        region_id=region_input.region_id,
        grid_cells=region_input.grid_cells,
        ranked_candidates=[
            candidate
        ],
        los_lookup=region_input.los_lookup,
        store=InMemoryWhatIfStore(),
        grid_resolution_m=250,
        signal_radius_m=5_000.0,
        maximum_gain=50.0,
    )

    candidate_rows = [
        row
        for row in rows
        if row["candidate_id"]
        == candidate.candidate_id
    ]

    assert candidate_rows
    assert (
        candidate_rows[0][
            "pct_good_change"
        ]
        > 0.0
    )
    assert (
        candidate_rows[0][
            "villages_newly_covered"
        ]
        >= 1
    )


def test_repeated_batch_is_idempotent() -> None:
    region_input, candidate = _region_input(
        "ntt"
    )
    store = InMemoryWhatIfStore()

    keyword_arguments = {
        "region_id": (
            region_input.region_id
        ),
        "grid_cells": (
            region_input.grid_cells
        ),
        "ranked_candidates": [
            candidate
        ],
        "los_lookup": (
            region_input.los_lookup
        ),
        "store": store,
        "grid_resolution_m": 250,
        "signal_radius_m": 5_000.0,
    }

    first_rows = precompute_region_whatif(
        **keyword_arguments
    )

    first_count = len(
        store.list_whatif_rows()
    )

    second_rows = precompute_region_whatif(
        **keyword_arguments
    )

    assert len(first_rows) == len(
        second_rows
    )

    assert len(
        store.list_whatif_rows()
    ) == first_count


class FakeSupabaseQuery:
    def __init__(
        self,
        client: "FakeSupabaseClient",
    ) -> None:
        self.client = client

    def upsert(
        self,
        payload: list[dict],
        *,
        on_conflict: str,
    ) -> "FakeSupabaseQuery":
        self.client.payload = payload
        self.client.on_conflict = (
            on_conflict
        )
        return self

    def execute(self) -> dict:
        return {
            "data": self.client.payload,
        }


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.table_name: str | None = None
        self.payload: list[dict] = []
        self.on_conflict: str | None = None

    def table(
        self,
        table_name: str,
    ) -> FakeSupabaseQuery:
        self.table_name = table_name
        return FakeSupabaseQuery(
            self
        )


def test_supabase_store_uses_composite_conflict_key() -> None:
    client = FakeSupabaseClient()
    store = SupabaseWhatIfStore(
        client
    )

    row = {
        "region_id": "ntt",
        "scenario_id": str(uuid4()),
        "grid_cell_id": str(uuid4()),
        "candidate_id": None,
        "snapped_lat": -10.0,
        "snapped_lon": 123.0,
        "grid_resolution_m": 250,
        "delta_coverage_score": 5.0,
        "pct_good_change": 10.0,
        "villages_newly_covered": 1,
        "new_coverage_score": 75.0,
    }

    result = store.upsert_whatif_rows(
        [row]
    )

    assert client.table_name == (
        "whatif_grid"
    )

    assert client.on_conflict == (
        "region_id,"
        "scenario_id,"
        "grid_cell_id"
    )

    assert result == [row]


def test_all_three_regions_are_precomputed_and_ready() -> None:
    region_inputs = {}
    candidate_ids_by_region = {}

    offsets = {
        "ntt": (0.0, 0.0),
        "ntb": (1.0, 1.0),
        "central_kalimantan": (
            5.0,
            -10.0,
        ),
    }

    for region_id in REQUIRED_REGION_IDS:
        latitude_offset, longitude_offset = (
            offsets[region_id]
        )

        region_input, candidate = (
            _region_input(
                region_id,
                latitude_offset=(
                    latitude_offset
                ),
                longitude_offset=(
                    longitude_offset
                ),
            )
        )

        region_inputs[
            region_id
        ] = region_input

        candidate_ids_by_region[
            region_id
        ] = [
            candidate.candidate_id
        ]

    store = InMemoryWhatIfStore()

    results = precompute_all_regions(
        region_inputs,
        store=store,
    )

    assert set(results) == set(
        REQUIRED_REGION_IDS
    )

    assert all(
        results[region_id]
        for region_id
        in REQUIRED_REGION_IDS
    )

    assert_precomputation_ready(
        store=store,
        candidate_ids_by_region=(
            candidate_ids_by_region
        ),
    )


def test_all_regions_batch_rejects_missing_region() -> None:
    ntt_input, _ = _region_input(
        "ntt"
    )
    ntb_input, _ = _region_input(
        "ntb",
        latitude_offset=1.0,
    )

    with pytest.raises(
        PrecomputationIncompleteError,
        match="Missing required",
    ):
        precompute_all_regions(
            {
                "ntt": ntt_input,
                "ntb": ntb_input,
            },
            store=InMemoryWhatIfStore(),
        )


def test_readiness_gate_rejects_missing_candidate() -> None:
    region_inputs = {}
    candidate_ids_by_region = {}

    offsets = {
        "ntt": (0.0, 0.0),
        "ntb": (1.0, 1.0),
        "central_kalimantan": (
            5.0,
            -10.0,
        ),
    }

    for region_id in REQUIRED_REGION_IDS:
        latitude_offset, longitude_offset = (
            offsets[region_id]
        )

        region_input, candidate = (
            _region_input(
                region_id,
                latitude_offset=(
                    latitude_offset
                ),
                longitude_offset=(
                    longitude_offset
                ),
            )
        )

        region_inputs[
            region_id
        ] = region_input

        candidate_ids_by_region[
            region_id
        ] = [
            candidate.candidate_id
        ]

    store = InMemoryWhatIfStore()

    precompute_all_regions(
        region_inputs,
        store=store,
    )

    candidate_ids_by_region[
        "ntt"
    ].append(
        str(uuid4())
    )

    with pytest.raises(
        PrecomputationIncompleteError,
        match="Candidates without",
    ):
        assert_precomputation_ready(
            store=store,
            candidate_ids_by_region=(
                candidate_ids_by_region
            ),
        )


def test_invalid_coverage_score_is_rejected() -> None:
    invalid_grid = [
        GridCellInput(
            grid_cell_id=str(uuid4()),
            coordinate=(-10.0, 123.0),
            coverage_score=np.nan,
            village_id="village-a",
        )
    ]

    with pytest.raises(
        ValueError,
        match="coverage_score",
    ):
        precompute_region_whatif(
            region_id="ntt",
            grid_cells=invalid_grid,
            ranked_candidates=[],
            los_lookup=(
                InMemoryLOSLookup()
            ),
            store=(
                InMemoryWhatIfStore()
            ),
            grid_resolution_m=250,
        )


def test_migration_defines_cell_level_composite_key() -> None:
    repository_root = (
        Path(__file__).resolve().parents[1]
    )

    migration_path = (
        repository_root
        / "infra"
        / "migrations"
        / "003_expand_whatif_grid_per_cell.sql"
    )

    sql = migration_path.read_text(
        encoding="utf-8"
    ).lower()

    assert (
        "add column if not exists "
        "grid_cell_id uuid"
    ) in sql

    assert (
        "primary key (\n"
        "    region_id,\n"
        "    scenario_id,\n"
        "    grid_cell_id\n"
        ")"
    ) in sql

    assert (
        "idx_whatif_grid_candidate_region"
        in sql
    )