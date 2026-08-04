"""Tests for spatially blocked cross-validation by kecamatan."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sklearn.dummy import DummyRegressor

from geosignal.models import (
    CONSOLIDATED_FEATURES,
    CVResult,
)
from geosignal.validation import (
    _build_spatial_folds,
    spatial_cv,
)


KECAMATAN_COLUMN = "kecamatan_id"
TARGET_COLUMN = "observed_mobile_performance"


def _make_dataset(
    n_kecamatan: int = 4,
    samples_per_kecamatan: int = 4,
) -> pd.DataFrame:
    """Create deterministic Tier 2 validation data."""
    rows: list[dict] = []

    for group_index in range(n_kecamatan):
        kecamatan_id = f"kec_{group_index:02d}"

        for sample_index in range(samples_per_kecamatan):
            base = float(
                group_index * samples_per_kecamatan
                + sample_index
                + 1
            )

            rows.append(
                {
                    KECAMATAN_COLUMN: kecamatan_id,
                    "elevation_m": 50.0 + base,
                    "slope_deg": 1.0 + base * 0.1,
                    "land_cover_class": float(
                        [10, 20, 30, 40][
                            sample_index % 4
                        ]
                    ),
                    "canopy_height_m": 2.0 + base * 0.2,
                    "distance_to_bts_m": 500.0 + base * 20.0,
                    "road_distance_m": 100.0 + base * 5.0,
                    "population_density_per_km2": (
                        80.0 + base * 3.0
                    ),
                    "facility_proximity_m": (
                        200.0 + base * 4.0
                    ),
                    TARGET_COLUMN: (
                        30.0
                        + group_index * 5.0
                        + sample_index * 1.25
                    ),
                }
            )

    return pd.DataFrame(rows)


def test_spatial_cv_returns_all_kecamatan_accuracies() -> None:
    data = _make_dataset(
        n_kecamatan=4,
        samples_per_kecamatan=4,
    )

    result = spatial_cv(
        data=data,
        kecamatan_column=KECAMATAN_COLUMN,
        model_cls=DummyRegressor,
        n_folds=2,
        model_kwargs={"strategy": "mean"},
    )

    assert isinstance(result, CVResult)
    assert result.n_folds == 2

    assert set(result.kecamatan_accuracies) == {
        "kec_00",
        "kec_01",
        "kec_02",
        "kec_03",
    }

    assert all(
        isinstance(value, float)
        and np.isfinite(value)
        for value in result.kecamatan_accuracies.values()
    )


def test_spatial_folds_hold_out_complete_disjoint_groups() -> None:
    data = _make_dataset(
        n_kecamatan=6,
        samples_per_kecamatan=3,
    )
    groups = data[KECAMATAN_COLUMN].to_numpy()

    folds = _build_spatial_folds(
        kecamatan_ids=groups,
        n_folds=3,
    )

    for train_indices, test_indices in folds:
        train_groups = set(groups[train_indices])
        test_groups = set(groups[test_indices])

        assert train_groups.isdisjoint(test_groups)

        for group in np.unique(groups):
            group_indices = set(
                np.flatnonzero(groups == group)
            )

            assert (
                group_indices.issubset(set(train_indices))
                or group_indices.issubset(set(test_indices))
            )


def test_each_kecamatan_appears_in_test_exactly_once() -> None:
    data = _make_dataset(
        n_kecamatan=7,
        samples_per_kecamatan=3,
    )
    groups = data[KECAMATAN_COLUMN].to_numpy()

    folds = _build_spatial_folds(
        kecamatan_ids=groups,
        n_folds=3,
    )

    occurrences = {
        str(group): 0
        for group in np.unique(groups)
    }

    for _, test_indices in folds:
        for group in np.unique(groups[test_indices]):
            occurrences[str(group)] += 1

    assert set(occurrences) == set(
        data[KECAMATAN_COLUMN].unique()
    )
    assert all(
        count == 1
        for count in occurrences.values()
    )


@pytest.mark.parametrize("n_folds", [0, 1])
def test_spatial_cv_rejects_fewer_than_two_folds(
    n_folds: int,
) -> None:
    data = _make_dataset()

    with pytest.raises(
        ValueError,
        match="at least 2",
    ):
        spatial_cv(
            data=data,
            kecamatan_column=KECAMATAN_COLUMN,
            model_cls=DummyRegressor,
            n_folds=n_folds,
        )


def test_spatial_cv_rejects_more_folds_than_kecamatan() -> None:
    data = _make_dataset(
        n_kecamatan=3,
        samples_per_kecamatan=3,
    )

    with pytest.raises(
        ValueError,
        match="cannot exceed",
    ):
        spatial_cv(
            data=data,
            kecamatan_column=KECAMATAN_COLUMN,
            model_cls=DummyRegressor,
            n_folds=4,
        )


@pytest.mark.parametrize(
    ("column_to_remove", "expected_name"),
    [
        (
            KECAMATAN_COLUMN,
            KECAMATAN_COLUMN,
        ),
        (
            TARGET_COLUMN,
            TARGET_COLUMN,
        ),
        (
            CONSOLIDATED_FEATURES[0],
            CONSOLIDATED_FEATURES[0],
        ),
    ],
)
def test_spatial_cv_rejects_missing_required_columns(
    column_to_remove: str,
    expected_name: str,
) -> None:
    data = _make_dataset().drop(
        columns=[column_to_remove]
    )

    with pytest.raises(
        ValueError,
        match=expected_name,
    ):
        spatial_cv(
            data=data,
            kecamatan_column=KECAMATAN_COLUMN,
            model_cls=DummyRegressor,
            n_folds=2,
        )


@pytest.mark.parametrize(
    "invalid_value",
    [None, "   "],
)
def test_spatial_cv_rejects_invalid_kecamatan_ids(
    invalid_value,
) -> None:
    data = _make_dataset()
    data.loc[0, KECAMATAN_COLUMN] = invalid_value

    with pytest.raises(
        ValueError,
        match="kecamatan identifiers",
    ):
        spatial_cv(
            data=data,
            kecamatan_column=KECAMATAN_COLUMN,
            model_cls=DummyRegressor,
            n_folds=2,
        )


@pytest.mark.parametrize(
    ("column_name", "invalid_value"),
    [
        ("elevation_m", np.inf),
        (TARGET_COLUMN, np.nan),
    ],
)
def test_spatial_cv_rejects_non_finite_values(
    column_name: str,
    invalid_value: float,
) -> None:
    data = _make_dataset()
    data.loc[0, column_name] = invalid_value

    with pytest.raises(
        ValueError,
        match="finite values",
    ):
        spatial_cv(
            data=data,
            kecamatan_column=KECAMATAN_COLUMN,
            model_cls=DummyRegressor,
            n_folds=2,
        )


def test_spatial_cv_rejects_one_observation_per_kecamatan() -> None:
    data = _make_dataset(
        n_kecamatan=3,
        samples_per_kecamatan=1,
    )

    with pytest.raises(
        ValueError,
        match="at least two observations",
    ):
        spatial_cv(
            data=data,
            kecamatan_column=KECAMATAN_COLUMN,
            model_cls=DummyRegressor,
            n_folds=2,
        )


@st.composite
def _spatial_cv_cases(draw):
    n_kecamatan = draw(
        st.integers(
            min_value=2,
            max_value=15,
        )
    )
    samples_per_kecamatan = draw(
        st.integers(
            min_value=2,
            max_value=8,
        )
    )
    n_folds = draw(
        st.integers(
            min_value=2,
            max_value=n_kecamatan,
        )
    )

    return (
        n_kecamatan,
        samples_per_kecamatan,
        n_folds,
    )


# Feature: geosignal-ai, Property 7:
# Spatial CV Kecamatan Disjointness
@settings(max_examples=50, deadline=None)
@given(case=_spatial_cv_cases())
def test_property_7_spatial_cv_kecamatan_disjointness(
    case,
) -> None:
    n_kecamatan, samples_per_kecamatan, n_folds = case

    data = _make_dataset(
        n_kecamatan=n_kecamatan,
        samples_per_kecamatan=samples_per_kecamatan,
    )
    groups = data[KECAMATAN_COLUMN].to_numpy()

    folds = _build_spatial_folds(
        kecamatan_ids=groups,
        n_folds=n_folds,
    )

    all_test_groups: list[str] = []

    for train_indices, test_indices in folds:
        train_groups = {
            str(group)
            for group in groups[train_indices]
        }
        test_groups = {
            str(group)
            for group in groups[test_indices]
        }

        assert train_groups.isdisjoint(test_groups)

        all_test_groups.extend(test_groups)

    assert set(all_test_groups) == {
        str(group)
        for group in np.unique(groups)
    }

    assert len(all_test_groups) == len(
        np.unique(groups)
    )


# Feature: geosignal-ai, Property 18:
# Per-Kecamatan Accuracy Reporting
@settings(max_examples=50, deadline=None)
@given(case=_spatial_cv_cases())
def test_property_18_per_kecamatan_accuracy_reporting(
    case,
) -> None:
    n_kecamatan, samples_per_kecamatan, n_folds = case

    data = _make_dataset(
        n_kecamatan=n_kecamatan,
        samples_per_kecamatan=samples_per_kecamatan,
    )

    result = spatial_cv(
        data=data,
        kecamatan_column=KECAMATAN_COLUMN,
        model_cls=DummyRegressor,
        n_folds=n_folds,
        model_kwargs={"strategy": "mean"},
    )

    expected_kecamatan = {
        str(value)
        for value in data[KECAMATAN_COLUMN].unique()
    }

    assert isinstance(result, CVResult)

    assert set(
        result.kecamatan_accuracies
    ) == expected_kecamatan

    assert len(
        result.kecamatan_accuracies
    ) == n_kecamatan

    assert all(
        isinstance(accuracy, float)
        and np.isfinite(accuracy)
        for accuracy
        in result.kecamatan_accuracies.values()
    )