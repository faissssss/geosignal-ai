"""Tests for Recommendation_Engine — Coverage Score and tier routing.

Includes:
  - Property 2 (Hypothesis): Tier Routing Correctness (sub-task 9.2)
  - Property 1 (Hypothesis): Coverage Score Bounds Invariant (sub-task 9.6)
  - Property 17 (Hypothesis): Equity Weighting Direction (sub-task 9.7)
  - Unit test for Tier 2 → Tier 1 fallback (sub-task 9.4a)

# Feature: geosignal-ai, Property 2: Tier Routing Correctness
# Feature: geosignal-ai, Property 1: Coverage Score Bounds Invariant
# Feature: geosignal-ai, Property 17: Equity Weighting Direction
"""
from __future__ import annotations

import sys
import os

# Ensure the backend package is importable when tests are run from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

from geosignal.models import CONSOLIDATED_FEATURES, FeatureVector
from geosignal.scoring import (
    ModelTier,
    compute_coverage_score,
    load_adapter_with_fallback,
    select_tier,
)
from geosignal.adapters import AHPAdapter


# ── Strategies ────────────────────────────────────────────────────────────────

def _feature_vector_strategy():
    """Generate FeatureVector values within Indonesia-scoped valid ranges."""
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


# ── Property 2: Tier Routing Correctness ─────────────────────────────────────
# Validates: Requirements 2.2, 2.3, 9.7

@given(st.integers(min_value=0))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_select_tier_iff_logic(ookla_tile_count):
    """select_tier returns TIER1 iff count == 0; TIER2 iff count > 0.

    **Validates: Requirements 2.2, 2.3, 9.7**
    """
    tier = select_tier("test_kecamatan", ookla_tile_count)
    if ookla_tile_count == 0:
        assert tier == ModelTier.TIER1, (
            f"Expected TIER1 when count=0, got {tier}"
        )
    else:
        assert tier == ModelTier.TIER2, (
            f"Expected TIER2 when count={ookla_tile_count}, got {tier}"
        )


# ── Property 1: Coverage Score Bounds Invariant ───────────────────────────────
# Validates: Requirements 2.1

@given(_feature_vector_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_coverage_score_bounds_ahp(fv):
    """compute_coverage_score with AHPAdapter always returns value in [0.0, 100.0].

    **Validates: Requirements 2.1**
    """
    adapter = AHPAdapter()
    score = compute_coverage_score(fv, adapter)
    assert isinstance(score, float), f"Score must be a float, got {type(score)}"
    assert 0.0 <= score <= 100.0, (
        f"Coverage score {score} is outside [0.0, 100.0] for FeatureVector {fv}"
    )


# ── Sub-task 9.4a: Fallback unit test ─────────────────────────────────────────

def test_fallback_to_tier1_when_tier2_factory_raises():
    """load_adapter_with_fallback falls back to AHPAdapter (Tier 1) when the
    Tier 2 factory raises RuntimeError.

    Asserts:
      1. Returned adapter is the AHPAdapter instance (Tier 1).
      2. Returned tier is ModelTier.TIER1.
      3. fallback_log contains exactly one entry with the kecamatan_id and a
         non-empty reason.
    """
    tier1 = AHPAdapter()
    fallback_log: list = []
    kecamatan_id = "kec_test_001"

    def _failing_factory():
        raise RuntimeError("Simulated missing XGBoost artifact")

    adapter, actual_tier = load_adapter_with_fallback(
        tier=ModelTier.TIER2,
        kecamatan_id=kecamatan_id,
        tier2_adapter_factory=_failing_factory,
        tier1_adapter=tier1,
        fallback_log=fallback_log,
    )

    # 1. Adapter should be the AHPAdapter we supplied.
    assert adapter is tier1, (
        "Expected AHPAdapter (tier1_adapter) to be returned on fallback"
    )

    # 2. Tier reported should be TIER1.
    assert actual_tier == ModelTier.TIER1, (
        f"Expected ModelTier.TIER1 after fallback, got {actual_tier}"
    )

    # 3. Fallback log should have exactly one entry with kecamatan_id and reason.
    assert len(fallback_log) == 1, (
        f"Expected exactly 1 fallback log entry, got {len(fallback_log)}"
    )
    entry = fallback_log[0]
    assert entry["kecamatan_id"] == kecamatan_id, (
        f"Expected kecamatan_id={kecamatan_id!r}, got {entry['kecamatan_id']!r}"
    )
    assert entry["reason"], "Fallback log entry must contain a non-empty reason"


def test_no_fallback_when_tier_is_tier1():
    """load_adapter_with_fallback returns Tier1 directly without calling
    the factory when tier == TIER1 (no fallback event logged)."""
    tier1 = AHPAdapter()
    fallback_log: list = []

    factory_called = []

    def _factory():
        factory_called.append(True)
        raise RuntimeError("Should not be called")

    adapter, actual_tier = load_adapter_with_fallback(
        tier=ModelTier.TIER1,
        kecamatan_id="kec_001",
        tier2_adapter_factory=_factory,
        tier1_adapter=tier1,
        fallback_log=fallback_log,
    )

    assert adapter is tier1
    assert actual_tier == ModelTier.TIER1
    assert fallback_log == [], "No fallback event should be logged when tier is TIER1"
    assert factory_called == [], "Tier 2 factory must not be called when tier is TIER1"


# ── Property 17: Equity Weighting Direction ───────────────────────────────────
# Validates: Requirements 9.1

def _make_feature_vector(**kwargs) -> FeatureVector:
    """Helper: build a FeatureVector with defaults for unspecified fields."""
    defaults = {
        "elevation_m": 100.0,
        "slope_deg": 5.0,
        "land_cover_class": 30,
        "canopy_height_m": 5.0,
        "distance_to_bts_m": 1000.0,
        "road_distance_m": 500.0,
        "population_density_per_km2": 500.0,
        "facility_proximity_m": 2000.0,
    }
    defaults.update(kwargs)
    return FeatureVector(**defaults)


@given(
    base_elevation=st.floats(min_value=-11.0, max_value=4884.0,
                             allow_nan=False, allow_infinity=False),
    base_slope=st.floats(min_value=0.0, max_value=90.0,
                         allow_nan=False, allow_infinity=False),
    base_land_cover=st.integers(min_value=10, max_value=90),
    base_canopy=st.floats(min_value=0.0, max_value=100.0,
                          allow_nan=False, allow_infinity=False),
    base_bts=st.floats(min_value=0.0, max_value=500_000.0,
                       allow_nan=False, allow_infinity=False),
    base_road=st.floats(min_value=0.0, max_value=500_000.0,
                        allow_nan=False, allow_infinity=False),
    base_pop=st.floats(min_value=1.0, max_value=50_000.0,
                       allow_nan=False, allow_infinity=False),
    prox_a=st.floats(min_value=0.0, max_value=499_999.0,
                     allow_nan=False, allow_infinity=False),
    prox_b=st.floats(min_value=1.0, max_value=500_000.0,
                     allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_equity_closer_facility_scores_higher(
    base_elevation, base_slope, base_land_cover, base_canopy,
    base_bts, base_road, base_pop, prox_a, prox_b
):
    """Pair (A, B): A has smaller facility_proximity_m → score(A) >= score(B).

    All other features are identical; population is non-zero (> 0).

    **Validates: Requirements 9.1**
    """
    assume(prox_a < prox_b)

    fv_a = FeatureVector(
        elevation_m=base_elevation,
        slope_deg=base_slope,
        land_cover_class=base_land_cover,
        canopy_height_m=base_canopy,
        distance_to_bts_m=base_bts,
        road_distance_m=base_road,
        population_density_per_km2=base_pop,
        facility_proximity_m=prox_a,
    )
    fv_b = FeatureVector(
        elevation_m=base_elevation,
        slope_deg=base_slope,
        land_cover_class=base_land_cover,
        canopy_height_m=base_canopy,
        distance_to_bts_m=base_bts,
        road_distance_m=base_road,
        population_density_per_km2=base_pop,
        facility_proximity_m=prox_b,
    )

    adapter = AHPAdapter()
    score_a = compute_coverage_score(fv_a, adapter)
    score_b = compute_coverage_score(fv_b, adapter)

    assert score_a >= score_b - 1e-9, (
        f"Equity violation: facility_proximity A={prox_a} < B={prox_b} "
        f"but score(A)={score_a:.4f} < score(B)={score_b:.4f}"
    )


@given(
    base_elevation=st.floats(min_value=-11.0, max_value=4884.0,
                             allow_nan=False, allow_infinity=False),
    base_slope=st.floats(min_value=0.0, max_value=90.0,
                         allow_nan=False, allow_infinity=False),
    base_land_cover=st.integers(min_value=10, max_value=90),
    base_canopy=st.floats(min_value=0.0, max_value=100.0,
                          allow_nan=False, allow_infinity=False),
    base_bts=st.floats(min_value=0.0, max_value=500_000.0,
                       allow_nan=False, allow_infinity=False),
    base_road=st.floats(min_value=0.0, max_value=500_000.0,
                        allow_nan=False, allow_infinity=False),
    base_prox=st.floats(min_value=0.0, max_value=500_000.0,
                        allow_nan=False, allow_infinity=False),
    pop_c=st.floats(min_value=1.0, max_value=50_000.0,
                    allow_nan=False, allow_infinity=False),
    pop_d=st.floats(min_value=0.0, max_value=49_999.0,
                    allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_equity_higher_population_scores_higher(
    base_elevation, base_slope, base_land_cover, base_canopy,
    base_bts, base_road, base_prox, pop_c, pop_d
):
    """Pair (C, D): C has higher population_density → score(C) >= score(D).

    All other features are identical.

    **Validates: Requirements 9.1**
    """
    assume(pop_c > pop_d)

    fv_c = FeatureVector(
        elevation_m=base_elevation,
        slope_deg=base_slope,
        land_cover_class=base_land_cover,
        canopy_height_m=base_canopy,
        distance_to_bts_m=base_bts,
        road_distance_m=base_road,
        population_density_per_km2=pop_c,
        facility_proximity_m=base_prox,
    )
    fv_d = FeatureVector(
        elevation_m=base_elevation,
        slope_deg=base_slope,
        land_cover_class=base_land_cover,
        canopy_height_m=base_canopy,
        distance_to_bts_m=base_bts,
        road_distance_m=base_road,
        population_density_per_km2=pop_d,
        facility_proximity_m=base_prox,
    )

    adapter = AHPAdapter()
    score_c = compute_coverage_score(fv_c, adapter)
    score_d = compute_coverage_score(fv_d, adapter)

    assert score_c >= score_d - 1e-9, (
        f"Equity violation: pop_density C={pop_c} > D={pop_d} "
        f"but score(C)={score_c:.4f} < score(D)={score_d:.4f}"
    )


# ── Additional unit tests ─────────────────────────────────────────────────────

def test_select_tier_zero_count_is_tier1():
    """select_tier(kec, 0) → TIER1."""
    assert select_tier("kec_x", 0) == ModelTier.TIER1


def test_select_tier_positive_count_is_tier2():
    """select_tier(kec, 1) → TIER2."""
    assert select_tier("kec_x", 1) == ModelTier.TIER2


def test_select_tier_large_count_is_tier2():
    """select_tier(kec, 9999) → TIER2."""
    assert select_tier("kec_x", 9999) == ModelTier.TIER2


def test_ahp_adapter_default_weights_sum_to_one():
    """Default AHP weights must sum to 1.0 after normalisation."""
    adapter = AHPAdapter()
    total = sum(adapter.weights.values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"


def test_ahp_adapter_equity_features_have_elevated_weights():
    """facility_proximity_m and population_density_per_km2 must have elevated
    weights relative to the flat baseline of 1/8 = 0.125."""
    adapter = AHPAdapter()
    flat_baseline = 1.0 / 8.0  # 0.125
    assert adapter.weights["facility_proximity_m"] > flat_baseline, (
        "facility_proximity_m weight must exceed flat baseline"
    )
    assert adapter.weights["population_density_per_km2"] > flat_baseline, (
        "population_density_per_km2 weight must exceed flat baseline"
    )


def test_ahp_predict_returns_correct_shape():
    """AHPAdapter.predict returns (N,) for (N, 8) input."""
    import numpy as np

    adapter = AHPAdapter()
    features = np.random.rand(5, 8) * 100.0
    result = adapter.predict(features)
    assert result.shape == (5,), f"Expected shape (5,), got {result.shape}"


def test_ahp_shap_values_returns_correct_shape():
    """AHPAdapter.shap_values returns (N, 8) for (N, 8) input."""
    import numpy as np

    adapter = AHPAdapter()
    features = np.random.rand(3, 8) * 100.0
    sv = adapter.shap_values(features)
    assert sv.shape == (3, 8), f"Expected shape (3, 8), got {sv.shape}"


def test_gnn_adapter_raises_not_implemented():
    """GNNAdapter raises NotImplementedError for both predict and shap_values."""
    import numpy as np
    from geosignal.adapters import GNNAdapter

    gnn = GNNAdapter()
    features = np.zeros((2, 8))
    with pytest.raises(NotImplementedError):
        gnn.predict(features)
    with pytest.raises(NotImplementedError):
        gnn.shap_values(features)


def test_xgboost_adapter_no_model_raises_runtime_error():
    """XGBoostAdapter with no model raises RuntimeError on predict."""
    import numpy as np
    from geosignal.adapters import XGBoostAdapter

    adapter = XGBoostAdapter(model_path=None)
    features = np.zeros((1, 8))
    with pytest.raises(RuntimeError, match="XGBoostAdapter has no model loaded"):
        adapter.predict(features)


def test_lightgbm_adapter_no_model_raises_runtime_error():
    """LightGBMAdapter with no model raises RuntimeError on predict."""
    import numpy as np
    from geosignal.adapters import LightGBMAdapter

    adapter = LightGBMAdapter(model_path=None)
    features = np.zeros((1, 8))
    with pytest.raises(RuntimeError, match="LightGBMAdapter has no model loaded"):
        adapter.predict(features)
