"""Tests for BTS candidate filtering and ranking."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from geosignal.candidates import rank_bts_candidates
from geosignal.constraints import is_high_canopy
from geosignal.models import (
    CONSOLIDATED_FEATURES,
    BTSCandidate,
    InsufficientCandidatesResult,
)


REGION_ID = "ntt"
TARGET_AREA_ID = "target-ntt-001"
MODEL_VERSION = "ahp-v1.0"
SCORING_RUN_ID = "run-001"


def _shap_values(count: int) -> list[dict[str, float]]:
    return [
        {
            feature: float(index + feature_index)
            for feature_index, feature in enumerate(
                CONSOLIDATED_FEATURES
            )
        }
        for index in range(count)
    ]


def _self_los_records(
    coordinates: np.ndarray,
    *,
    region_id: str = REGION_ID,
    included_indices: set[int] | None = None,
) -> list[dict]:
    if included_indices is None:
        included_indices = set(range(len(coordinates)))

    records: list[dict] = []

    for index, coordinate in enumerate(coordinates):
        if index not in included_indices:
            continue

        records.append(
            {
                "region_id": region_id,
                "candidate_lat": float(coordinate[0]),
                "candidate_lon": float(coordinate[1]),
                "cell_lat": float(coordinate[0]),
                "cell_lon": float(coordinate[1]),
                "los_clear": True,
            }
        )

    return records


def _all_pair_los_records(
    coordinates: np.ndarray,
    *,
    region_id: str = REGION_ID,
) -> list[dict]:
    return [
        {
            "region_id": region_id,
            "candidate_lat": float(candidate[0]),
            "candidate_lon": float(candidate[1]),
            "cell_lat": float(cell[0]),
            "cell_lon": float(cell[1]),
            "los_clear": True,
        }
        for candidate in coordinates
        for cell in coordinates
    ]


def _rank(
    coordinates: np.ndarray,
    scores: np.ndarray,
    land_cover: np.ndarray,
    canopy: np.ndarray,
    los_records: list[dict],
    *,
    n_candidates: int = 10,
):
    count = len(coordinates)

    return rank_bts_candidates(
        grid_cells=coordinates,
        coverage_scores=scores,
        land_cover_classes=land_cover,
        canopy_heights_m=canopy,
        los_records=los_records,
        shap_values_by_cell=_shap_values(count),
        region_id=REGION_ID,
        target_area_id=TARGET_AREA_ID,
        model_version=MODEL_VERSION,
        scoring_run_id=SCORING_RUN_ID,
        nearest_opencellid_km=[1.0] * count,
        nearest_ookla_km=[1.0] * count,
        n_candidates=n_candidates,
        signal_radius_m=20_000.0,
    )


def test_candidate_without_precomputed_los_is_never_emitted() -> None:
    """Task 12.2: a coordinate without LOS data cannot become a candidate."""
    coordinates = np.array(
        [
            [-10.00, 123.00],
            [-10.00, 123.01],
            [-10.00, 123.02],
        ]
    )

    result = _rank(
        coordinates=coordinates,
        scores=np.array([20.0, 30.0, 40.0]),
        land_cover=np.array([40, 40, 40]),
        canopy=np.array([0.0, 0.0, 0.0]),
        los_records=_self_los_records(
            coordinates,
            included_indices={0, 1},
        ),
    )

    assert isinstance(result, list)
    assert len(result) == 2

    emitted_coordinates = {
        candidate.coordinate
        for candidate in result
    }

    assert (-10.00, 123.00) in emitted_coordinates
    assert (-10.00, 123.01) in emitted_coordinates
    assert (-10.00, 123.02) not in emitted_coordinates


def test_candidates_are_ranked_by_expected_improvement() -> None:
    coordinates = np.array(
        [
            [-10.00, 123.00],
            [-10.00, 123.01],
            [-10.00, 123.02],
        ]
    )

    # Each candidate only has a clear LOS record to its own grid cell.
    # Expected deficits: 90, 60, 20.
    result = _rank(
        coordinates=coordinates,
        scores=np.array([10.0, 40.0, 80.0]),
        land_cover=np.array([40, 40, 40]),
        canopy=np.array([0.0, 0.0, 0.0]),
        los_records=_self_los_records(coordinates),
    )

    assert isinstance(result, list)

    assert [
        candidate.expected_improvement
        for candidate in result
    ] == [90.0, 60.0, 20.0]

    assert [
        candidate.rank
        for candidate in result
    ] == [1, 2, 3]


def test_high_canopy_candidate_is_excluded() -> None:
    coordinates = np.array(
        [
            [-10.00, 123.00],
            [-10.00, 123.01],
            [-10.00, 123.02],
        ]
    )

    result = _rank(
        coordinates=coordinates,
        scores=np.array([10.0, 30.0, 50.0]),
        land_cover=np.array([10, 40, 40]),
        canopy=np.array([20.0, 0.0, 0.0]),
        los_records=_self_los_records(coordinates),
    )

    assert isinstance(result, list)

    assert all(
        candidate.coordinate != (-10.00, 123.00)
        for candidate in result
    )


def test_all_emitted_candidates_have_complete_metadata() -> None:
    coordinates = np.array(
        [
            [-10.00, 123.00],
            [-10.00, 123.01],
        ]
    )

    result = _rank(
        coordinates=coordinates,
        scores=np.array([20.0, 40.0]),
        land_cover=np.array([40, 40]),
        canopy=np.array([0.0, 0.0]),
        los_records=_self_los_records(coordinates),
    )

    assert isinstance(result, list)

    for candidate in result:
        assert isinstance(candidate, BTSCandidate)
        assert candidate.los_validated is True
        assert candidate.confidence_tag == "High"
        assert candidate.model_version == MODEL_VERSION
        assert candidate.scoring_run_id == SCORING_RUN_ID
        assert set(candidate.shap_values) == set(
            CONSOLIDATED_FEATURES
        )
        assert len(candidate.shap_values) == 8


def test_exactly_zero_surviving_candidates_returns_result() -> None:
    """Task 12.5: zero surviving candidates must not produce a list."""
    coordinates = np.array(
        [
            [-10.00, 123.00],
            [-10.00, 123.01],
        ]
    )

    result = _rank(
        coordinates=coordinates,
        scores=np.array([20.0, 30.0]),
        land_cover=np.array([10, 20]),
        canopy=np.array([20.0, 20.0]),
        los_records=_self_los_records(coordinates),
    )

    assert isinstance(result, InsufficientCandidatesResult)
    assert result.surviving_count == 0
    assert result.target_area_id == TARGET_AREA_ID


def test_exactly_one_surviving_candidate_returns_result() -> None:
    """Task 12.5: one survivor must not produce a one-item list."""
    coordinates = np.array(
        [
            [-10.00, 123.00],
            [-10.00, 123.01],
        ]
    )

    result = _rank(
        coordinates=coordinates,
        scores=np.array([20.0, 30.0]),
        land_cover=np.array([40, 10]),
        canopy=np.array([0.0, 20.0]),
        los_records=_self_los_records(coordinates),
    )

    assert isinstance(result, InsufficientCandidatesResult)
    assert result.surviving_count == 1
    assert result.target_area_id == TARGET_AREA_ID


def test_n_candidates_must_be_at_least_two() -> None:
    coordinates = np.array(
        [
            [-10.00, 123.00],
            [-10.00, 123.01],
        ]
    )

    with pytest.raises(
        ValueError,
        match="at least 2",
    ):
        _rank(
            coordinates=coordinates,
            scores=np.array([20.0, 30.0]),
            land_cover=np.array([40, 40]),
            canopy=np.array([0.0, 0.0]),
            los_records=_self_los_records(coordinates),
            n_candidates=1,
        )


def test_candidate_with_computed_but_blocked_los_has_zero_improvement() -> None:
    coordinates = np.array(
        [
            [-10.00, 123.00],
            [-10.00, 123.01],
        ]
    )

    records = [
        {
            "region_id": REGION_ID,
            "candidate_lat": float(candidate[0]),
            "candidate_lon": float(candidate[1]),
            "cell_lat": float(candidate[0]),
            "cell_lon": float(candidate[1]),
            "los_clear": False,
        }
        for candidate in coordinates
    ]

    result = _rank(
        coordinates=coordinates,
        scores=np.array([20.0, 30.0]),
        land_cover=np.array([40, 40]),
        canopy=np.array([0.0, 0.0]),
        los_records=records,
    )

    assert isinstance(result, list)

    assert all(
        candidate.expected_improvement == 0.0
        for candidate in result
    )


@st.composite
def _candidate_cases(draw):
    count = draw(
        st.integers(
            min_value=2,
            max_value=10,
        )
    )

    scores = draw(
        st.lists(
            st.floats(
                min_value=0.0,
                max_value=100.0,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=count,
            max_size=count,
        )
    )

    land_cover = draw(
        st.lists(
            st.sampled_from([10, 20, 30, 40, 50]),
            min_size=count,
            max_size=count,
        )
    )

    canopy = draw(
        st.lists(
            st.floats(
                min_value=0.0,
                max_value=30.0,
                allow_nan=False,
                allow_infinity=False,
            ),
            min_size=count,
            max_size=count,
        )
    )

    return (
        count,
        np.asarray(scores, dtype=float),
        np.asarray(land_cover, dtype=int),
        np.asarray(canopy, dtype=float),
    )


@settings(max_examples=100, deadline=None)
@given(case=_candidate_cases())
def test_property_9_bts_candidate_list_invariants(case) -> None:
    """Property 9: BTS Candidate List Invariants."""
    count, scores, land_cover, canopy = case

    coordinates = np.array(
        [
            [-10.0, 123.0 + index * 0.01]
            for index in range(count)
        ],
        dtype=float,
    )

    result = _rank(
        coordinates=coordinates,
        scores=scores,
        land_cover=land_cover,
        canopy=canopy,
        los_records=_self_los_records(coordinates),
    )

    valid_indices = [
        index
        for index in range(count)
        if not is_high_canopy(
            land_cover_class=int(land_cover[index]),
            canopy_height_m=float(canopy[index]),
        )
    ]

    if len(valid_indices) < 2:
        assert isinstance(
            result,
            InsufficientCandidatesResult,
        )
        assert result.surviving_count == len(valid_indices)
        return

    assert isinstance(result, list)
    assert len(result) >= 2

    improvements = [
        candidate.expected_improvement
        for candidate in result
    ]

    assert improvements == sorted(
        improvements,
        reverse=True,
    )

    assert all(
        candidate.los_validated is True
        for candidate in result
    )

    coordinate_to_index = {
        (
            float(coordinate[0]),
            float(coordinate[1]),
        ): index
        for index, coordinate in enumerate(coordinates)
    }

    for candidate in result:
        index = coordinate_to_index[candidate.coordinate]

        assert not is_high_canopy(
            land_cover_class=int(land_cover[index]),
            canopy_height_m=float(canopy[index]),
        )