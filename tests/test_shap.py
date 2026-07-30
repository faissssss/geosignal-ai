# Feature: geosignal-ai, Property 10: SHAP Completeness
# Feature: geosignal-ai, Property 15: SHAP Top-3 Format Invariant
"""Tests for SHAP explainability utilities (backend/geosignal/shap_utils.py).

Includes:
  - Property 10 (Hypothesis): SHAP Completeness (sub-task 10.4)
  - Property 15 (Hypothesis): SHAP Top-3 Format Invariant (sub-task 10.5)
  - Unit test: baseline staleness isolation (sub-task 10.6)
  - Unit test: batch write-back non-null shap_top3 (sub-task 10.7)
"""
from __future__ import annotations

import sys
import os

# Ensure the backend package is importable when tests run from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from geosignal.models import CONSOLIDATED_FEATURES, FeatureVector
from geosignal.shap_utils import (
    batch_compute_shap,
    compute_ahp_shap,
    format_shap_top3,
    write_shap_to_grid_cells,
)
from geosignal.adapters import AHPAdapter


# ── Shared strategies ─────────────────────────────────────────────────────────

def _feature_vector_strategy():
    """Generate FeatureVectors within Indonesia-scoped valid ranges."""
    return st.builds(
        FeatureVector,
        elevation_m=st.floats(min_value=-11.0, max_value=4884.0,
                              allow_nan=False, allow_infinity=False),
        slope_deg=st.floats(min_value=0.0, max_value=90.0,
                            allow_nan=False, allow_infinity=False),
        land_cover_class=st.integers(min_value=10, max_value=90),
        canopy_height_m=st.floats(min_value=0.0, max_value=100.0,
                                  allow_nan=False, allow_infinity=False),
        distance_to_bts_m=st.floats(min_value=0.0, max_value=500_000.0,
                                    allow_nan=False, allow_infinity=False),
        road_distance_m=st.floats(min_value=0.0, max_value=500_000.0,
                                  allow_nan=False, allow_infinity=False),
        population_density_per_km2=st.floats(min_value=0.0, max_value=50_000.0,
                                             allow_nan=False, allow_infinity=False),
        facility_proximity_m=st.floats(min_value=0.0, max_value=500_000.0,
                                       allow_nan=False, allow_infinity=False),
    )


def _float_dict_strategy(
    min_val: float = -1e6,
    max_val: float = 1e6,
) -> st.SearchStrategy:
    """Generate a dict with exactly 8 float entries keyed by CONSOLIDATED_FEATURES."""
    return st.fixed_dictionaries(
        {
            feat: st.floats(
                min_value=min_val,
                max_value=max_val,
                allow_nan=False,
                allow_infinity=False,
            )
            for feat in CONSOLIDATED_FEATURES
        }
    )


def _positive_weights_strategy() -> st.SearchStrategy:
    """Generate non-zero positive weight dicts (will be used as-is; not normalised here)."""
    return st.fixed_dictionaries(
        {
            feat: st.floats(
                min_value=1e-3,
                max_value=1.0,
                allow_nan=False,
                allow_infinity=False,
            )
            for feat in CONSOLIDATED_FEATURES
        }
    )


# ── Property 10: SHAP Completeness ───────────────────────────────────────────
# Validates: Requirements 4.6, 8.1, 8.3


@given(
    fv=_feature_vector_strategy(),
    weights=_positive_weights_strategy(),
    baseline=_float_dict_strategy(min_val=-1e4, max_val=1e6),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property_10_ahp_shap_returns_8_entries(fv, weights, baseline):
    """compute_ahp_shap returns a dict with exactly 8 entries and no None values.

    **Validates: Requirements 4.6, 8.1, 8.3**
    """
    result = compute_ahp_shap(fv, weights, baseline)

    # Exactly 8 entries
    assert len(result) == 8, (
        f"Expected 8 SHAP entries, got {len(result)}: {list(result.keys())}"
    )

    # Keys match CONSOLIDATED_FEATURES exactly
    assert set(result.keys()) == set(CONSOLIDATED_FEATURES), (
        f"SHAP keys {set(result.keys())} do not match CONSOLIDATED_FEATURES"
    )

    # No None values
    for feat, val in result.items():
        assert val is not None, f"SHAP value for '{feat}' must not be None"
        assert isinstance(val, float), (
            f"SHAP value for '{feat}' must be float, got {type(val)}"
        )


@given(
    fv=_feature_vector_strategy(),
    weights=_positive_weights_strategy(),
    baseline=_float_dict_strategy(min_val=-1e4, max_val=1e6),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property_10_ahp_shap_formula_correctness(fv, weights, baseline):
    """compute_ahp_shap values equal weight * (value - baseline) for each feature.

    **Validates: Requirements 8.1, 8.3**
    """
    result = compute_ahp_shap(fv, weights, baseline)

    for feat in CONSOLIDATED_FEATURES:
        expected = weights[feat] * (getattr(fv, feat) - baseline[feat])
        actual = result[feat]
        assert abs(actual - expected) < 1e-10, (
            f"SHAP mismatch for '{feat}': expected {expected}, got {actual}"
        )


@given(fv=_feature_vector_strategy(), weights=_positive_weights_strategy())
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_property_10_ahp_shap_raises_on_missing_baseline_feature(fv, weights):
    """compute_ahp_shap raises KeyError when regional_baseline is missing a feature.

    **Validates: Requirements 8.3**
    """
    # Build a baseline missing the last CONSOLIDATED_FEATURES entry.
    incomplete_baseline = {feat: 0.0 for feat in CONSOLIDATED_FEATURES[:-1]}

    with pytest.raises(KeyError):
        compute_ahp_shap(fv, weights, incomplete_baseline)


@given(fv=_feature_vector_strategy(), baseline=_float_dict_strategy(min_val=-1e4, max_val=1e6))
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_property_10_ahp_shap_raises_on_missing_weight_feature(fv, baseline):
    """compute_ahp_shap raises KeyError when weights dict is missing a feature.

    **Validates: Requirements 8.3**
    """
    # Build a weights dict missing the first CONSOLIDATED_FEATURES entry.
    incomplete_weights = {feat: 1.0 for feat in CONSOLIDATED_FEATURES[1:]}

    with pytest.raises(KeyError):
        compute_ahp_shap(fv, incomplete_weights, baseline)


# ── Property 15: SHAP Top-3 Format Invariant ─────────────────────────────────
# Validates: Requirements 8.2


@given(shap_values=_float_dict_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property_15_format_shap_top3_returns_exactly_3(shap_values):
    """format_shap_top3 returns exactly 3 entries for any 8-entry dict.

    **Validates: Requirements 8.2**
    """
    result = format_shap_top3(shap_values)
    assert len(result) == 3, (
        f"Expected exactly 3 entries, got {len(result)}"
    )


@given(shap_values=_float_dict_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property_15_format_shap_top3_non_empty_feature_name(shap_values):
    """format_shap_top3 returns non-empty feature_name for every entry.

    **Validates: Requirements 8.2**
    """
    result = format_shap_top3(shap_values)
    for entry in result:
        assert "feature_name" in entry, "Entry missing 'feature_name' key"
        assert isinstance(entry["feature_name"], str), (
            f"feature_name must be str, got {type(entry['feature_name'])}"
        )
        assert entry["feature_name"], (
            "feature_name must be non-empty"
        )


@given(shap_values=_float_dict_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property_15_format_shap_top3_direction_values(shap_values):
    """format_shap_top3 direction is 'positive' or 'negative' for every entry.

    **Validates: Requirements 8.2**
    """
    result = format_shap_top3(shap_values)
    for entry in result:
        assert "direction" in entry, "Entry missing 'direction' key"
        assert entry["direction"] in {"positive", "negative"}, (
            f"direction must be 'positive' or 'negative', got {entry['direction']!r}"
        )


@given(shap_values=_float_dict_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property_15_format_shap_top3_sorted_by_abs_descending(shap_values):
    """format_shap_top3 entries are sorted by abs(value) descending.

    **Validates: Requirements 8.2**
    """
    result = format_shap_top3(shap_values)
    abs_values = [abs(entry["value"]) for entry in result]
    for i in range(len(abs_values) - 1):
        assert abs_values[i] >= abs_values[i + 1], (
            f"Entry {i} abs={abs_values[i]} < entry {i+1} abs={abs_values[i+1]}; "
            f"result not sorted descending"
        )


@given(shap_values=_float_dict_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_property_15_format_shap_top3_direction_matches_sign(shap_values):
    """direction must be 'positive' iff value >= 0, 'negative' iff value < 0.

    **Validates: Requirements 8.2**
    """
    result = format_shap_top3(shap_values)
    for entry in result:
        v = entry["value"]
        if v >= 0.0:
            assert entry["direction"] == "positive", (
                f"value={v} >= 0 but direction={entry['direction']!r}"
            )
        else:
            assert entry["direction"] == "negative", (
                f"value={v} < 0 but direction={entry['direction']!r}"
            )


# ── Sub-task 10.6: Baseline staleness unit test ───────────────────────────────

def test_unit_different_baselines_produce_different_shap():
    """AHP SHAP is NOT shared across calls with different baselines.

    Calling compute_ahp_shap twice with the same FeatureVector + weights
    but different baselines must produce different SHAP dicts, proving the
    baseline is per-run and not globally cached.
    """
    fv = FeatureVector(
        elevation_m=100.0,
        slope_deg=5.0,
        land_cover_class=30,
        canopy_height_m=10.0,
        distance_to_bts_m=5000.0,
        road_distance_m=1000.0,
        population_density_per_km2=500.0,
        facility_proximity_m=3000.0,
    )
    weights = {feat: 1.0 / 8.0 for feat in CONSOLIDATED_FEATURES}

    # Baseline A: all zeros
    baseline_a = {feat: 0.0 for feat in CONSOLIDATED_FEATURES}
    # Baseline B: all 100s (clearly different)
    baseline_b = {feat: 100.0 for feat in CONSOLIDATED_FEATURES}

    result_a = compute_ahp_shap(fv, weights, baseline_a)
    result_b = compute_ahp_shap(fv, weights, baseline_b)

    # At least one feature must differ
    assert result_a != result_b, (
        "Different baselines must produce different SHAP dicts; "
        "the baseline must not be globally cached"
    )

    # Verify the values differ predictably.
    # result_a[feat] = w * (value - baseline_a[feat])
    # result_b[feat] = w * (value - baseline_b[feat])
    # result_a - result_b  = w * (baseline_b[feat] - baseline_a[feat])
    for feat in CONSOLIDATED_FEATURES:
        expected_diff = weights[feat] * (baseline_b[feat] - baseline_a[feat])
        actual_diff = result_a[feat] - result_b[feat]
        assert abs(actual_diff - expected_diff) < 1e-10, (
            f"Unexpected diff for '{feat}': expected {expected_diff}, got {actual_diff}"
        )


def test_unit_different_baselines_different_region_runs():
    """Baseline is scoped to region+run — two separate calls with region-specific
    baselines produce results reflecting each region's own distribution."""
    fv = FeatureVector(
        elevation_m=200.0,
        slope_deg=15.0,
        land_cover_class=10,
        canopy_height_m=25.0,
        distance_to_bts_m=10_000.0,
        road_distance_m=2_000.0,
        population_density_per_km2=1500.0,
        facility_proximity_m=5_000.0,
    )
    weights = {feat: 1.0 / 8.0 for feat in CONSOLIDATED_FEATURES}

    # NTT-like baseline: lower elevation mean, sparser population
    baseline_ntt = {
        "elevation_m": 80.0,
        "slope_deg": 8.0,
        "land_cover_class": 30.0,
        "canopy_height_m": 5.0,
        "distance_to_bts_m": 20_000.0,
        "road_distance_m": 4_000.0,
        "population_density_per_km2": 200.0,
        "facility_proximity_m": 8_000.0,
    }

    # Kalimantan-like baseline: higher canopy, denser coverage
    baseline_kalimantan = {
        "elevation_m": 50.0,
        "slope_deg": 3.0,
        "land_cover_class": 10.0,
        "canopy_height_m": 30.0,
        "distance_to_bts_m": 15_000.0,
        "road_distance_m": 3_000.0,
        "population_density_per_km2": 800.0,
        "facility_proximity_m": 6_000.0,
    }

    result_ntt = compute_ahp_shap(fv, weights, baseline_ntt)
    result_kalimantan = compute_ahp_shap(fv, weights, baseline_kalimantan)

    assert result_ntt != result_kalimantan, (
        "Region-specific baselines must produce different SHAP dicts"
    )


# ── Sub-task 10.7: Batch write-back unit test ─────────────────────────────────

def _make_feature_vectors(n: int) -> list[FeatureVector]:
    """Create n simple FeatureVectors for batch testing."""
    return [
        FeatureVector(
            elevation_m=float(i * 10),
            slope_deg=float(i % 30),
            land_cover_class=30,
            canopy_height_m=float(i % 20),
            distance_to_bts_m=float(1000 + i * 100),
            road_distance_m=float(500 + i * 50),
            population_density_per_km2=float(100 + i * 10),
            facility_proximity_m=float(2000 + i * 200),
        )
        for i in range(n)
    ]


def test_unit_write_shap_to_grid_cells_all_non_null_shap_top3():
    """After write_shap_to_grid_cells (supabase_client=None), every row has a
    non-null shap_top3 field with exactly 3 entries.
    """
    n = 5
    feature_vectors = _make_feature_vectors(n)
    cell_ids = [f"cell-{i:04d}" for i in range(n)]

    # Use AHPAdapter as the adapter (its shap_values method is not called by
    # the AHP path, but adapter is required for the function signature).
    adapter = AHPAdapter()

    weights = {feat: 1.0 / 8.0 for feat in CONSOLIDATED_FEATURES}
    regional_baseline = {feat: 0.0 for feat in CONSOLIDATED_FEATURES}

    rows = write_shap_to_grid_cells(
        region_id="test_region",
        feature_vectors=feature_vectors,
        cell_ids=cell_ids,
        adapter=adapter,
        supabase_client=None,
        regional_baseline=regional_baseline,
        weights=weights,
        use_ahp=True,
    )

    # Correct number of rows
    assert len(rows) == n, f"Expected {n} rows, got {len(rows)}"

    for i, row in enumerate(rows):
        # Each row has cell_id and shap_top3
        assert "cell_id" in row, f"Row {i} missing 'cell_id'"
        assert "shap_top3" in row, f"Row {i} missing 'shap_top3'"

        # Non-null
        assert row["shap_top3"] is not None, f"Row {i} shap_top3 must not be None"

        # Exactly 3 entries
        assert len(row["shap_top3"]) == 3, (
            f"Row {i} shap_top3 must have exactly 3 entries, "
            f"got {len(row['shap_top3'])}"
        )

        # Each entry has required keys
        for j, entry in enumerate(row["shap_top3"]):
            assert "feature_name" in entry, (
                f"Row {i} entry {j} missing 'feature_name'"
            )
            assert "value" in entry, f"Row {i} entry {j} missing 'value'"
            assert "direction" in entry, f"Row {i} entry {j} missing 'direction'"
            assert entry["feature_name"], (
                f"Row {i} entry {j} feature_name must be non-empty"
            )
            assert entry["direction"] in {"positive", "negative"}, (
                f"Row {i} entry {j} direction invalid: {entry['direction']!r}"
            )


def test_unit_write_shap_to_grid_cells_cell_ids_match():
    """write_shap_to_grid_cells preserves the input cell_ids in output rows."""
    n = 3
    feature_vectors = _make_feature_vectors(n)
    cell_ids = ["alpha", "beta", "gamma"]
    adapter = AHPAdapter()
    weights = {feat: 1.0 / 8.0 for feat in CONSOLIDATED_FEATURES}
    baseline = {feat: 50.0 for feat in CONSOLIDATED_FEATURES}

    rows = write_shap_to_grid_cells(
        region_id="ntt",
        feature_vectors=feature_vectors,
        cell_ids=cell_ids,
        adapter=adapter,
        supabase_client=None,
        regional_baseline=baseline,
        weights=weights,
        use_ahp=True,
    )

    returned_ids = [row["cell_id"] for row in rows]
    assert returned_ids == cell_ids, (
        f"cell_ids mismatch: expected {cell_ids}, got {returned_ids}"
    )


# ── Additional unit tests: format_shap_top3 edge cases ───────────────────────

def test_unit_format_shap_top3_all_zero_values():
    """format_shap_top3 works when all SHAP values are 0.0 (returns 3 entries)."""
    shap_values = {feat: 0.0 for feat in CONSOLIDATED_FEATURES}
    result = format_shap_top3(shap_values)
    assert len(result) == 3

    for entry in result:
        assert entry["direction"] == "positive"  # 0.0 >= 0
        assert entry["feature_name"]


def test_unit_format_shap_top3_known_values():
    """format_shap_top3 returns correct top-3 for a known input."""
    shap_values = {
        "elevation_m": 10.0,           # abs = 10  → #1
        "slope_deg": -7.5,             # abs = 7.5 → #2
        "land_cover_class": 5.0,       # abs = 5   → #3
        "canopy_height_m": 3.0,        # abs = 3   → #4
        "distance_to_bts_m": -1.0,     # abs = 1   → #5
        "road_distance_m": 0.5,        # abs = 0.5 → #6
        "population_density_per_km2": -0.1,  # abs = 0.1 → #7
        "facility_proximity_m": 0.0,   # abs = 0   → #8
    }
    result = format_shap_top3(shap_values)

    assert len(result) == 3

    # Top feature: elevation_m
    assert result[0]["feature_name"] == "Elevation"
    assert result[0]["value"] == 10.0
    assert result[0]["direction"] == "positive"

    # Second: slope_deg
    assert result[1]["feature_name"] == "Terrain slope"
    assert result[1]["value"] == -7.5
    assert result[1]["direction"] == "negative"

    # Third: land_cover_class
    assert result[2]["feature_name"] == "Land cover type"
    assert result[2]["value"] == 5.0
    assert result[2]["direction"] == "positive"


def test_unit_format_shap_top3_negative_becomes_negative_direction():
    """All-negative SHAP values produce direction='negative' for each entry."""
    shap_values = {feat: float(-i - 1) for i, feat in enumerate(CONSOLIDATED_FEATURES)}
    result = format_shap_top3(shap_values)
    for entry in result:
        assert entry["direction"] == "negative", (
            f"Expected 'negative' but got {entry['direction']!r} for value={entry['value']}"
        )


def test_unit_batch_compute_shap_ahp_length():
    """batch_compute_shap returns one dict per input FeatureVector."""
    fvs = _make_feature_vectors(4)
    adapter = AHPAdapter()
    weights = {feat: 1.0 / 8.0 for feat in CONSOLIDATED_FEATURES}
    baseline = {feat: 0.0 for feat in CONSOLIDATED_FEATURES}

    results = batch_compute_shap(fvs, adapter, regional_baseline=baseline,
                                 weights=weights, use_ahp=True)

    assert len(results) == 4
    for sv in results:
        assert len(sv) == 8
        assert set(sv.keys()) == set(CONSOLIDATED_FEATURES)


def test_unit_compute_ahp_shap_exact_formula():
    """compute_ahp_shap: each value equals weight * (feature_value - baseline)."""
    fv = FeatureVector(
        elevation_m=200.0,
        slope_deg=10.0,
        land_cover_class=30,
        canopy_height_m=8.0,
        distance_to_bts_m=5000.0,
        road_distance_m=1000.0,
        population_density_per_km2=300.0,
        facility_proximity_m=4000.0,
    )
    weights = {feat: 0.125 for feat in CONSOLIDATED_FEATURES}  # uniform 1/8
    baseline = {feat: 100.0 for feat in CONSOLIDATED_FEATURES}

    result = compute_ahp_shap(fv, weights, baseline)

    assert abs(result["elevation_m"] - (0.125 * (200.0 - 100.0))) < 1e-10
    assert abs(result["slope_deg"] - (0.125 * (10.0 - 100.0))) < 1e-10
    assert abs(result["population_density_per_km2"] - (0.125 * (300.0 - 100.0))) < 1e-10
