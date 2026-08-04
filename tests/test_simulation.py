"""Tests for GeoSignal AI Before/After simulation."""

from __future__ import annotations

from uuid import uuid4

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from geosignal.models import (
    HeatmapDelta,
    SimulationResult,
    UnavailableScenario,
)
from geosignal.simulation import (
    MAX_SIMULATION_ELAPSED_MS,
    InMemorySimulationStore,
    SimulationDataError,
    SupabaseSimulationStore,
    _colour_tier,
    simulate_bts_placement,
)


REGION_ID = "ntt"


def _scenario_data(
    *,
    candidate_id: str | None = None,
    pct_good_change: float = 25.0,
    villages_newly_covered: int = 2,
    new_coverage_score: float = 85.0,
) -> tuple[
    str,
    list[dict],
    list[dict],
]:
    resolved_candidate_id = (
        str(uuid4())
        if candidate_id is None
        else candidate_id
    )

    grid_cells = [
        {
            "cell_id": str(uuid4()),
            "region_id": REGION_ID,
            "lat": -10.000,
            "lon": 123.000,
            "coverage_score": 35.0,
        },
        {
            "cell_id": str(uuid4()),
            "region_id": REGION_ID,
            "lat": -10.005,
            "lon": 123.005,
            "coverage_score": 65.0,
        },
        {
            "cell_id": str(uuid4()),
            "region_id": REGION_ID,
            "lat": -10.010,
            "lon": 123.010,
            "coverage_score": 80.0,
        },
    ]

    deltas = [
        20.0,
        15.0,
        0.0,
    ]

    whatif_rows = [
        {
            "region_id": REGION_ID,
            "scenario_id": (
                resolved_candidate_id
            ),
            "candidate_id": (
                resolved_candidate_id
            ),
            "grid_cell_id": (
                grid_cell["cell_id"]
            ),
            "snapped_lat": -10.0,
            "snapped_lon": 123.0,
            "grid_resolution_m": 250,
            "delta_coverage_score": delta,
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
        for grid_cell, delta
        in zip(
            grid_cells,
            deltas,
            strict=True,
        )
    ]

    return (
        resolved_candidate_id,
        grid_cells,
        whatif_rows,
    )


def _store_with_scenario(
    *,
    candidate_id: str | None = None,
    pct_good_change: float = 25.0,
    villages_newly_covered: int = 2,
    new_coverage_score: float = 85.0,
) -> tuple[
    str,
    InMemorySimulationStore,
]:
    (
        resolved_candidate_id,
        grid_cells,
        whatif_rows,
    ) = _scenario_data(
        candidate_id=candidate_id,
        pct_good_change=pct_good_change,
        villages_newly_covered=(
            villages_newly_covered
        ),
        new_coverage_score=(
            new_coverage_score
        ),
    )

    return (
        resolved_candidate_id,
        InMemorySimulationStore(
            whatif_rows=whatif_rows,
            grid_cells=grid_cells,
        ),
    )


def test_missing_scenario_returns_unavailable_result() -> None:
    candidate_id = str(uuid4())
    store = InMemorySimulationStore()

    result = simulate_bts_placement(
        candidate_id,
        REGION_ID,
        store=store,
    )

    assert isinstance(
        result,
        UnavailableScenario,
    )

    assert result.candidate_id == candidate_id
    assert result.region_id == REGION_ID
    assert "No precomputed" in result.message
    assert "No estimate was computed" in result.message
    assert store.lookup_count == 1


def test_valid_scenario_returns_canonical_result() -> None:
    candidate_id, store = (
        _store_with_scenario()
    )

    result = simulate_bts_placement(
        candidate_id,
        REGION_ID,
        store=store,
    )

    assert isinstance(
        result,
        SimulationResult,
    )

    assert isinstance(
        result.before_heatmap,
        HeatmapDelta,
    )

    assert isinstance(
        result.after_heatmap,
        HeatmapDelta,
    )

    assert (
        result.before_heatmap.snapshot_label
        == "before"
    )

    assert (
        result.after_heatmap.snapshot_label
        == "after"
    )


def test_before_and_after_heatmap_scores_are_correct() -> None:
    candidate_id, store = (
        _store_with_scenario()
    )

    result = simulate_bts_placement(
        candidate_id,
        REGION_ID,
        store=store,
    )

    assert isinstance(
        result,
        SimulationResult,
    )

    before_by_id = {
        cell["cell_id"]: cell
        for cell in result.before_heatmap.cells
    }

    after_by_id = {
        cell["cell_id"]: cell
        for cell in result.after_heatmap.cells
    }

    assert set(before_by_id) == set(
        after_by_id
    )

    before_scores = sorted(
        cell["coverage_score"]
        for cell in before_by_id.values()
    )

    after_scores = sorted(
        cell["coverage_score"]
        for cell in after_by_id.values()
    )

    assert before_scores == [
        35.0,
        65.0,
        80.0,
    ]

    assert after_scores == [
        55.0,
        80.0,
        80.0,
    ]


@pytest.mark.parametrize(
    ("score", "expected_tier"),
    [
        (0.0, "Red"),
        (39.99, "Red"),
        (40.0, "Yellow"),
        (69.99, "Yellow"),
        (70.0, "Green"),
        (100.0, "Green"),
    ],
)
def test_heatmap_cells_use_correct_colour_tiers(
    score: float,
    expected_tier: str,
) -> None:
    assert _colour_tier(score) == expected_tier


def test_simulation_returns_precomputed_metrics() -> None:
    candidate_id, store = (
        _store_with_scenario(
            pct_good_change=33.5,
            villages_newly_covered=4,
            new_coverage_score=91.25,
        )
    )

    result = simulate_bts_placement(
        candidate_id,
        REGION_ID,
        store=store,
    )

    assert isinstance(
        result,
        SimulationResult,
    )

    assert result.pct_good_change == 33.5
    assert result.villages_newly_covered == 4
    assert result.new_coverage_score == 91.25


def test_simulation_meets_three_second_latency_budget() -> None:
    candidate_id, store = (
        _store_with_scenario()
    )

    result = simulate_bts_placement(
        candidate_id,
        REGION_ID,
        store=store,
    )

    assert isinstance(
        result,
        SimulationResult,
    )

    assert isinstance(
        result.elapsed_ms,
        int,
    )

    assert (
        0
        <= result.elapsed_ms
        <= MAX_SIMULATION_ELAPSED_MS
    )


def test_inconsistent_aggregate_metrics_are_rejected() -> None:
    (
        candidate_id,
        grid_cells,
        whatif_rows,
    ) = _scenario_data()

    whatif_rows[1][
        "pct_good_change"
    ] = 99.0

    store = InMemorySimulationStore(
        whatif_rows=whatif_rows,
        grid_cells=grid_cells,
    )

    with pytest.raises(
        SimulationDataError,
        match="pct_good_change is inconsistent",
    ):
        simulate_bts_placement(
            candidate_id,
            REGION_ID,
            store=store,
        )


def test_missing_baseline_grid_cell_is_rejected() -> None:
    (
        candidate_id,
        grid_cells,
        whatif_rows,
    ) = _scenario_data()

    incomplete_grid_cells = (
        grid_cells[:-1]
    )

    store = InMemorySimulationStore(
        whatif_rows=whatif_rows,
        grid_cells=incomplete_grid_cells,
    )

    with pytest.raises(
        SimulationDataError,
        match="no joined baseline grid cell",
    ):
        simulate_bts_placement(
            candidate_id,
            REGION_ID,
            store=store,
        )


def test_duplicate_grid_cell_result_is_rejected() -> None:
    (
        candidate_id,
        grid_cells,
        whatif_rows,
    ) = _scenario_data()

    whatif_rows.append(
        dict(whatif_rows[0])
    )

    store = InMemorySimulationStore(
        whatif_rows=whatif_rows,
        grid_cells=grid_cells,
    )

    with pytest.raises(
        SimulationDataError,
        match="Duplicate grid-cell result",
    ):
        simulate_bts_placement(
            candidate_id,
            REGION_ID,
            store=store,
        )


class FakeSupabaseQuery:
    def __init__(
        self,
        client: "FakeSupabaseClient",
    ) -> None:
        self.client = client

    def select(
        self,
        columns: str,
    ) -> "FakeSupabaseQuery":
        self.client.selected_columns = (
            columns
        )
        return self

    def eq(
        self,
        field: str,
        value: object,
    ) -> "FakeSupabaseQuery":
        self.client.filters[
            field
        ] = value
        return self

    def execute(self) -> dict:
        return {
            "data": self.client.rows,
        }


class FakeSupabaseClient:
    def __init__(
        self,
        rows: list[dict],
    ) -> None:
        self.rows = rows
        self.table_name: str | None = None
        self.selected_columns: str | None = None
        self.filters: dict[
            str,
            object,
        ] = {}

    def table(
        self,
        table_name: str,
    ) -> FakeSupabaseQuery:
        self.table_name = table_name
        return FakeSupabaseQuery(
            self
        )


def test_supabase_store_queries_candidate_and_region() -> None:
    candidate_id = str(uuid4())
    grid_cell_id = str(uuid4())

    client = FakeSupabaseClient(
        [
            {
                "region_id": REGION_ID,
                "scenario_id": candidate_id,
                "candidate_id": candidate_id,
                "grid_cell_id": grid_cell_id,
                "delta_coverage_score": 10.0,
                "pct_good_change": 5.0,
                "villages_newly_covered": 1,
                "new_coverage_score": 75.0,
                "grid_cells": {
                    "cell_id": grid_cell_id,
                    "lat": -10.0,
                    "lon": 123.0,
                    "coverage_score": 65.0,
                },
            }
        ]
    )

    store = SupabaseSimulationStore(
        client
    )

    rows = (
        store.get_candidate_scenario_rows(
            candidate_id=candidate_id,
            region_id=REGION_ID,
        )
    )

    assert client.table_name == (
        "whatif_grid"
    )

    assert client.filters == {
        "candidate_id": candidate_id,
        "region_id": REGION_ID,
    }

    assert (
        "grid_cells!inner"
        in client.selected_columns
    )

    assert len(rows) == 1
    assert rows[0]["grid_cell"] == (
        client.rows[0]["grid_cells"]
    )


class GuardedUnavailableStore:
    """Store whose forbidden computation methods must never be called."""

    def __init__(self) -> None:
        self.lookup_count = 0
        self.forbidden_call_count = 0

    def get_candidate_scenario_rows(
        self,
        *,
        candidate_id: str,
        region_id: str,
    ) -> list[dict]:
        self.lookup_count += 1
        return []

    def compute_dem(self) -> None:
        self.forbidden_call_count += 1
        raise AssertionError(
            "Live DEM computation was called"
        )

    def interpolate(self) -> None:
        self.forbidden_call_count += 1
        raise AssertionError(
            "Interpolation was called"
        )

    def extrapolate(self) -> None:
        self.forbidden_call_count += 1
        raise AssertionError(
            "Extrapolation was called"
        )


# Feature: geosignal-ai, Property 12:
# Simulation Unavailability Contract
@settings(max_examples=100, deadline=None)
@given(
    candidate_id=st.uuids().map(str),
    region_id=st.sampled_from(
        [
            "ntt",
            "ntb",
            "central_kalimantan",
        ]
    ),
)
def test_property_12_simulation_unavailability_contract(
    candidate_id: str,
    region_id: str,
) -> None:
    store = GuardedUnavailableStore()

    result = simulate_bts_placement(
        candidate_id,
        region_id,
        store=store,
    )

    assert isinstance(
        result,
        UnavailableScenario,
    )

    assert store.lookup_count == 1
    assert store.forbidden_call_count == 0


# Feature: geosignal-ai, Property 23:
# Simulation Metric Completeness
@settings(max_examples=100, deadline=None)
@given(
    pct_good_change=st.floats(
        min_value=-100.0,
        max_value=100.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    villages_newly_covered=st.integers(
        min_value=0,
        max_value=10_000,
    ),
    new_coverage_score=st.floats(
        min_value=0.0,
        max_value=100.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_property_23_simulation_metric_completeness(
    pct_good_change: float,
    villages_newly_covered: int,
    new_coverage_score: float,
) -> None:
    candidate_id, store = (
        _store_with_scenario(
            pct_good_change=pct_good_change,
            villages_newly_covered=(
                villages_newly_covered
            ),
            new_coverage_score=(
                new_coverage_score
            ),
        )
    )

    result = simulate_bts_placement(
        candidate_id,
        REGION_ID,
        store=store,
    )

    assert isinstance(
        result,
        SimulationResult,
    )

    assert result.pct_good_change is not None
    assert (
        result.villages_newly_covered
        is not None
    )
    assert (
        result.new_coverage_score
        is not None
    )

    assert np.isfinite(
        result.pct_good_change
    )

    assert np.isfinite(
        result.new_coverage_score
    )

    assert isinstance(
        result.villages_newly_covered,
        int,
    )

    assert (
        result.villages_newly_covered
        >= 0
    )