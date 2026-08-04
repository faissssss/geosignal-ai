"""Tests for GeoSignal AI drag-and-drop placement simulation."""

from __future__ import annotations

from uuid import uuid4

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from geosignal.models import (
    ComparisonPanel,
    DragDropResult,
    OutsideExtentError,
    WhatIfGrid,
)
from geosignal.simulation import (
    MAX_DRAG_DROP_ELAPSED_MS,
    SimulationDataError,
    build_drag_drop_grid,
    drag_drop_lookup,
)


REGION_ID = "ntt"


def _cells(
    *,
    first_score: float = 75.0,
    first_confidence: str = "High",
) -> list[dict]:
    return [
        {
            "scenario_id": str(uuid4()),
            "lat": -10.00,
            "lon": 123.00,
            "new_coverage_score": first_score,
            "confidence_tag": first_confidence,
        },
        {
            "scenario_id": str(uuid4()),
            "lat": -10.00,
            "lon": 123.02,
            "new_coverage_score": 65.0,
            "confidence_tag": "Med",
        },
        {
            "scenario_id": str(uuid4()),
            "lat": -9.98,
            "lon": 123.00,
            "new_coverage_score": 55.0,
            "confidence_tag": "Med",
        },
        {
            "scenario_id": str(uuid4()),
            "lat": -9.98,
            "lon": 123.02,
            "new_coverage_score": 45.0,
            "confidence_tag": "Low",
        },
    ]


def _top_candidate(
    *,
    model_score: float = 70.0,
) -> dict:
    return {
        "candidate_id": str(uuid4()),
        "lat": -10.005,
        "lon": 123.005,
        "model_score": model_score,
    }


def _grid(
    *,
    first_score: float = 75.0,
    model_score: float = 70.0,
) -> WhatIfGrid:
    return build_drag_drop_grid(
        region_id=REGION_ID,
        cells=_cells(
            first_score=first_score
        ),
        grid_resolution_m=250,
        top_candidate=_top_candidate(
            model_score=model_score
        ),
    )


def test_build_drag_drop_grid_constructs_canonical_model() -> None:
    grid = _grid()

    assert isinstance(
        grid,
        WhatIfGrid,
    )

    assert grid.region_id == REGION_ID
    assert grid.centroids.shape == (4, 2)
    assert len(grid.scenario_ids) == 4
    assert grid.grid_resolution_m == 250
    assert callable(
        getattr(
            grid.spatial_index,
            "query",
            None,
        )
    )


def test_lookup_snaps_to_nearest_cell() -> None:
    grid = _grid()

    result = drag_drop_lookup(
        -9.999,
        123.019,
        REGION_ID,
        grid,
    )

    assert isinstance(
        result,
        DragDropResult,
    )

    assert result.snapped_coordinate == (
        -10.00,
        123.02,
    )

    assert result.coverage_score == 65.0
    assert result.confidence_tag == "Med"
    assert result.grid_resolution_m == 250


def test_outside_extent_returns_error_with_extent_payload() -> None:
    grid = _grid()

    result = drag_drop_lookup(
        -11.0,
        123.01,
        REGION_ID,
        grid,
    )

    assert isinstance(
        result,
        OutsideExtentError,
    )

    assert result.region_id == REGION_ID
    assert "No interpolation" in result.message

    assert result.region_extent == {
        "min_lat": -10.0,
        "max_lat": -9.98,
        "min_lon": 123.0,
        "max_lon": 123.02,
    }


def test_overlay_flag_does_not_change_coverage_score() -> None:
    grid = _grid()

    without_overlay = drag_drop_lookup(
        -10.0,
        123.0,
        REGION_ID,
        grid,
        overlay_enabled=False,
    )

    with_overlay = drag_drop_lookup(
        -10.0,
        123.0,
        REGION_ID,
        grid,
        overlay_enabled=True,
    )

    assert isinstance(
        without_overlay,
        DragDropResult,
    )

    assert isinstance(
        with_overlay,
        DragDropResult,
    )

    assert (
        without_overlay.coverage_score
        == with_overlay.coverage_score
    )


def test_manual_wins_true_when_score_is_higher() -> None:
    grid = _grid(
        first_score=85.0,
        model_score=70.0,
    )

    result = drag_drop_lookup(
        -10.0,
        123.0,
        REGION_ID,
        grid,
    )

    assert isinstance(
        result,
        DragDropResult,
    )

    assert isinstance(
        result.vs_top_candidate,
        ComparisonPanel,
    )

    assert (
        result.vs_top_candidate.manual_score
        == 85.0
    )

    assert (
        result.vs_top_candidate.model_score
        == 70.0
    )

    assert (
        result.vs_top_candidate.manual_wins
        is True
    )


def test_manual_wins_false_when_score_is_not_higher() -> None:
    grid = _grid(
        first_score=65.0,
        model_score=70.0,
    )

    result = drag_drop_lookup(
        -10.0,
        123.0,
        REGION_ID,
        grid,
    )

    assert isinstance(
        result,
        DragDropResult,
    )

    assert (
        result.vs_top_candidate.manual_wins
        is False
    )


def test_result_fields_and_latency_budget() -> None:
    grid = _grid()

    result = drag_drop_lookup(
        -10.0,
        123.0,
        REGION_ID,
        grid,
    )

    assert isinstance(
        result,
        DragDropResult,
    )

    assert np.isfinite(
        result.coverage_score
    )

    assert result.confidence_tag in {
        "Low",
        "Med",
        "High",
    }

    assert (
        result.grid_resolution_m
        > 0
    )

    assert (
        0
        <= result.elapsed_ms
        <= MAX_DRAG_DROP_ELAPSED_MS
    )


def test_extent_boundary_is_inclusive() -> None:
    grid = _grid()

    result = drag_drop_lookup(
        -9.98,
        123.02,
        REGION_ID,
        grid,
    )

    assert isinstance(
        result,
        DragDropResult,
    )

    assert result.snapped_coordinate == (
        -9.98,
        123.02,
    )


def test_region_mismatch_is_rejected() -> None:
    grid = _grid()

    with pytest.raises(
        SimulationDataError,
        match="region does not match",
    ):
        drag_drop_lookup(
            -10.0,
            123.0,
            "ntb",
            grid,
        )


def test_invalid_confidence_tag_is_rejected() -> None:
    cells = _cells()
    cells[0]["confidence_tag"] = "Very High"

    with pytest.raises(
        SimulationDataError,
        match="Low, Med, or High",
    ):
        build_drag_drop_grid(
            region_id=REGION_ID,
            cells=cells,
            grid_resolution_m=250,
            top_candidate=_top_candidate(),
        )


def test_duplicate_centroids_are_rejected() -> None:
    cells = _cells()
    cells[1]["lat"] = cells[0]["lat"]
    cells[1]["lon"] = cells[0]["lon"]

    with pytest.raises(
        SimulationDataError,
        match="duplicate centroids",
    ):
        build_drag_drop_grid(
            region_id=REGION_ID,
            cells=cells,
            grid_resolution_m=250,
            top_candidate=_top_candidate(),
        )


# Feature: geosignal-ai, Property 13:
# Drag-and-Drop Boundary and Snap Contracts
@settings(max_examples=100, deadline=None)
@given(
    latitude_offset=st.floats(
        min_value=0.001,
        max_value=10.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    longitude=st.floats(
        min_value=123.0,
        max_value=123.02,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_property_13_outside_extent_contract(
    latitude_offset: float,
    longitude: float,
) -> None:
    grid = _grid()

    result = drag_drop_lookup(
        -10.0 - latitude_offset,
        longitude,
        REGION_ID,
        grid,
    )

    assert isinstance(
        result,
        OutsideExtentError,
    )

    assert not isinstance(
        result,
        DragDropResult,
    )

    assert hasattr(
        result,
        "region_extent",
    )


# Feature: geosignal-ai, Property 13:
# Drag-and-Drop Boundary and Snap Contracts
@settings(max_examples=100, deadline=None)
@given(
    latitude=st.floats(
        min_value=-9.9999,
        max_value=-9.9801,
        allow_nan=False,
        allow_infinity=False,
    ),
    longitude=st.floats(
        min_value=123.0001,
        max_value=123.0199,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_property_13_inside_snap_contract(
    latitude: float,
    longitude: float,
) -> None:
    grid = _grid()

    distances = np.sum(
        (
            grid.centroids
            - np.asarray(
                [
                    latitude,
                    longitude,
                ],
                dtype=np.float64,
            )
        )
        ** 2,
        axis=1,
    )

    ordered_distances = np.sort(
        distances
    )

    # Exclude exact equidistant positions because more than one nearest
    # centroid is mathematically valid in that case.
    assume(
        not np.isclose(
            ordered_distances[0],
            ordered_distances[1],
        )
    )

    expected_index = int(
        np.argmin(distances)
    )

    expected_coordinate = (
        float(
            grid.centroids[
                expected_index,
                0,
            ]
        ),
        float(
            grid.centroids[
                expected_index,
                1,
            ]
        ),
    )

    result = drag_drop_lookup(
        latitude,
        longitude,
        REGION_ID,
        grid,
    )

    assert isinstance(
        result,
        DragDropResult,
    )

    assert (
        result.snapped_coordinate
        == expected_coordinate
    )

    assert (
        result.grid_resolution_m
        == grid.grid_resolution_m
    )

    assert result.grid_resolution_m > 0


# Feature: geosignal-ai, Property 14:
# Power Overlay Non-Interference
@settings(max_examples=100, deadline=None)
@given(
    latitude=st.floats(
        min_value=-9.999,
        max_value=-9.981,
        allow_nan=False,
        allow_infinity=False,
    ),
    longitude=st.floats(
        min_value=123.001,
        max_value=123.019,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_property_14_power_overlay_non_interference(
    latitude: float,
    longitude: float,
) -> None:
    grid = _grid()

    overlay_disabled = drag_drop_lookup(
        latitude,
        longitude,
        REGION_ID,
        grid,
        overlay_enabled=False,
    )

    overlay_enabled = drag_drop_lookup(
        latitude,
        longitude,
        REGION_ID,
        grid,
        overlay_enabled=True,
    )

    assert isinstance(
        overlay_disabled,
        DragDropResult,
    )

    assert isinstance(
        overlay_enabled,
        DragDropResult,
    )

    assert (
        overlay_disabled.coverage_score
        == overlay_enabled.coverage_score
    )


# Feature: geosignal-ai, Property 24:
# Manual Placement Comparison Correctness
@settings(max_examples=100, deadline=None)
@given(
    model_score=st.floats(
        min_value=0.0,
        max_value=99.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    score_advantage=st.floats(
        min_value=0.0001,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_property_24_manual_placement_comparison_correctness(
    model_score: float,
    score_advantage: float,
) -> None:
    maximum_advantage = (
        100.0
        - model_score
    )

    assume(
        maximum_advantage
        > 0.0
    )

    manual_score = (
        model_score
        + min(
            score_advantage,
            maximum_advantage,
        )
    )

    assume(
        manual_score
        > model_score
    )

    grid = _grid(
        first_score=manual_score,
        model_score=model_score,
    )

    result = drag_drop_lookup(
        -10.0,
        123.0,
        REGION_ID,
        grid,
    )

    assert isinstance(
        result,
        DragDropResult,
    )

    assert (
        result.coverage_score
        > result.vs_top_candidate.model_score
    )

    assert (
        result.vs_top_candidate.manual_wins
        is True
    )