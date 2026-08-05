"""Task 29 — Phase 3 Distributed Compute Adapter Interface Tests.

Tests the DistributedScoringAdapter stub and DistributedExecutorProtocol.

All 25 required tests are present (numbered T1–T25).
No test requires Spark, Dask, or any distributed framework to be installed.

Requirements: Phase 3 extensibility, ScoringAdapter protocol compatibility.
"""
from __future__ import annotations

import sys
import os
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import importlib
import ast

import numpy as np
import pytest

from geosignal.adapters import (
    AHPAdapter,
    DistributedExecutorProtocol,
    DistributedScoringAdapter,
    GNNAdapter,
    LightGBMAdapter,
    ScoringAdapter,
    XGBoostAdapter,
)
from geosignal.models import CONSOLIDATED_FEATURES, FeatureVector
from geosignal.scoring import compute_coverage_score


# ---------------------------------------------------------------------------
# Fake executor — satisfies DistributedExecutorProtocol without any framework
# ---------------------------------------------------------------------------

class FakeExecutor:
    """Minimal executor stub for testing.

    Records calls but never actually distributes anything.
    Satisfies DistributedExecutorProtocol.map contract structurally.
    """

    def __init__(self) -> None:
        self.map_call_count = 0

    def map(self, fn, partitions):
        self.map_call_count += 1
        return [fn(p) for p in partitions]


_INNER = AHPAdapter()
_EXECUTOR = FakeExecutor()

N_FEATURES = len(CONSOLIDATED_FEATURES)  # 8


def _features(n: int = 4) -> np.ndarray:
    """Return a (n, 8) float64 feature array with valid values."""
    rng = np.random.default_rng(42)
    arr = rng.uniform(0.0, 500.0, size=(n, N_FEATURES))
    return arr.astype(np.float64)


# ===========================================================================
# T1 — DistributedScoringAdapter can be constructed with inner + executor
# ===========================================================================

def test_t1_construction_with_inner_and_executor():
    """T1: DistributedScoringAdapter(inner=AHPAdapter(), executor=fake) succeeds."""
    adapter = DistributedScoringAdapter(inner=_INNER, executor=FakeExecutor())
    assert adapter is not None


# ===========================================================================
# T2 — Constructor does NOT call executor
# ===========================================================================

def test_t2_constructor_does_not_call_executor():
    """T2: constructing the adapter never invokes executor.map()."""
    spy = FakeExecutor()
    _ = DistributedScoringAdapter(inner=_INNER, executor=spy)
    assert spy.map_call_count == 0, (
        f"T2 FAIL: executor.map() was called {spy.map_call_count} time(s) "
        "during construction."
    )


# ===========================================================================
# T3 — Object has method predict
# ===========================================================================

def test_t3_adapter_has_predict_method():
    """T3: DistributedScoringAdapter instance has a callable predict attribute."""
    adapter = DistributedScoringAdapter(inner=_INNER, executor=FakeExecutor())
    assert callable(getattr(adapter, "predict", None)), (
        "T3 FAIL: adapter.predict is not callable."
    )


# ===========================================================================
# T4 — Object has method shap_values
# ===========================================================================

def test_t4_adapter_has_shap_values_method():
    """T4: DistributedScoringAdapter instance has a callable shap_values attribute."""
    adapter = DistributedScoringAdapter(inner=_INNER, executor=FakeExecutor())
    assert callable(getattr(adapter, "shap_values", None)), (
        "T4 FAIL: adapter.shap_values is not callable."
    )


# ===========================================================================
# T5 — Object satisfies ScoringAdapter protocol
# ===========================================================================

def test_t5_adapter_satisfies_scoring_adapter_protocol():
    """T5: DistributedScoringAdapter structurally satisfies ScoringAdapter."""
    adapter = DistributedScoringAdapter(inner=_INNER, executor=FakeExecutor())
    # Protocol structural check: both required methods present and callable
    assert callable(getattr(adapter, "predict", None))
    assert callable(getattr(adapter, "shap_values", None))
    # runtime_checkable isinstance check (Protocol is not runtime_checkable by
    # default in this codebase, so we check structurally)
    import inspect
    pred_sig  = inspect.signature(adapter.predict)
    shap_sig  = inspect.signature(adapter.shap_values)
    assert "features" in pred_sig.parameters
    assert "features" in shap_sig.parameters


# ===========================================================================
# T6 — predict raises NotImplementedError on MVP
# ===========================================================================

def test_t6_predict_raises_not_implemented_error():
    """T6: predict() raises NotImplementedError in the MVP."""
    adapter = DistributedScoringAdapter(inner=_INNER, executor=FakeExecutor())
    with pytest.raises(NotImplementedError):
        adapter.predict(_features(4))


# ===========================================================================
# T7 — shap_values raises NotImplementedError on MVP
# ===========================================================================

def test_t7_shap_values_raises_not_implemented_error():
    """T7: shap_values() raises NotImplementedError in the MVP."""
    adapter = DistributedScoringAdapter(inner=_INNER, executor=FakeExecutor())
    with pytest.raises(NotImplementedError):
        adapter.shap_values(_features(4))


# ===========================================================================
# T8 — Error message mentions Phase 3 / distributed execution
# ===========================================================================

def test_t8_predict_error_message_mentions_phase3():
    """T8: NotImplementedError message from predict() references Phase 3."""
    adapter = DistributedScoringAdapter(inner=_INNER, executor=FakeExecutor())
    with pytest.raises(NotImplementedError, match=r"(?i)phase 3|distributed"):
        adapter.predict(_features(2))


def test_t8b_shap_error_message_mentions_phase3():
    """T8b: NotImplementedError message from shap_values() references Phase 3."""
    adapter = DistributedScoringAdapter(inner=_INNER, executor=FakeExecutor())
    with pytest.raises(NotImplementedError, match=r"(?i)phase 3|distributed"):
        adapter.shap_values(_features(2))


# ===========================================================================
# T9 — No mock prediction returned
# ===========================================================================

def test_t9_predict_does_not_return_mock_data():
    """T9: predict() raises — it never silently returns mock scores."""
    adapter = DistributedScoringAdapter(inner=_INNER, executor=FakeExecutor())
    raised = False
    try:
        result = adapter.predict(_features(3))
        # If no exception: fail if result is numeric (mock data)
        assert False, f"T9 FAIL: predict() returned {result!r} instead of raising."
    except NotImplementedError:
        raised = True
    assert raised, "T9 FAIL: predict() must raise NotImplementedError."


# ===========================================================================
# T10 — No silent fallback to local execution
# ===========================================================================

def test_t10_no_silent_local_fallback_on_predict():
    """T10: predict() raises; inner.predict is not called as a fallback."""
    call_log: list[str] = []

    class SpyAdapter:
        def predict(self, features):
            call_log.append("predict")
            return _INNER.predict(features)
        def shap_values(self, features):
            call_log.append("shap_values")
            return _INNER.shap_values(features)

    adapter = DistributedScoringAdapter(inner=SpyAdapter(), executor=FakeExecutor())
    with pytest.raises(NotImplementedError):
        adapter.predict(_features(4))
    assert "predict" not in call_log, (
        "T10 FAIL: inner.predict was called — silent local fallback detected."
    )


# ===========================================================================
# T11 — inner adapter not called by the stub
# ===========================================================================

def test_t11_inner_not_called_by_predict_stub():
    """T11: inner.predict is never invoked by the Phase 3 stub."""
    call_log: list[str] = []

    class TrackingInner:
        def predict(self, f):
            call_log.append("predict")
            return _INNER.predict(f)
        def shap_values(self, f):
            call_log.append("shap_values")
            return _INNER.shap_values(f)

    adapter = DistributedScoringAdapter(inner=TrackingInner(), executor=FakeExecutor())
    with pytest.raises(NotImplementedError):
        adapter.predict(_features(2))
    with pytest.raises(NotImplementedError):
        adapter.shap_values(_features(2))

    assert call_log == [], (
        f"T11 FAIL: inner methods were called: {call_log}"
    )


# ===========================================================================
# T12 — Empty array still raises structured NotImplementedError (not crash)
# ===========================================================================

def test_t12_empty_array_raises_not_implemented_not_crash():
    """T12: predict/shap_values with empty (0, 8) array raise NotImplementedError."""
    adapter = DistributedScoringAdapter(inner=_INNER, executor=FakeExecutor())
    empty = np.empty((0, N_FEATURES), dtype=np.float64)

    with pytest.raises(NotImplementedError):
        adapter.predict(empty)

    with pytest.raises(NotImplementedError):
        adapter.shap_values(empty)


# ===========================================================================
# T13 — Input shape not mutated
# ===========================================================================

def test_t13_input_shape_not_mutated():
    """T13: the input array is not modified when the stub raises."""
    adapter = DistributedScoringAdapter(inner=_INNER, executor=FakeExecutor())
    original = _features(3)
    copy = original.copy()
    with pytest.raises(NotImplementedError):
        adapter.predict(original)
    np.testing.assert_array_equal(original, copy, err_msg="T13 FAIL: predict() mutated input.")

    with pytest.raises(NotImplementedError):
        adapter.shap_values(original)
    np.testing.assert_array_equal(original, copy, err_msg="T13 FAIL: shap_values() mutated input.")


# ===========================================================================
# T14-T16 — No import of pyspark, dask, or distributed in adapters.py
# ===========================================================================

_ADAPTERS_SOURCE = open(
    os.path.join(os.path.dirname(__file__), "..", "backend", "geosignal", "adapters.py"),
    encoding="utf-8",
).read()


def test_t14_no_pyspark_import():
    """T14: adapters.py does not import pyspark."""
    tree = ast.parse(_ADAPTERS_SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else ([node.module] if node.module else [])
            )
            for name in names:
                assert not (name or "").startswith("pyspark"), (
                    f"T14 FAIL: adapters.py imports pyspark ({name!r})."
                )


def test_t15_no_dask_import():
    """T15: adapters.py does not import dask."""
    tree = ast.parse(_ADAPTERS_SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else ([node.module] if node.module else [])
            )
            for name in names:
                assert not (name or "").startswith("dask"), (
                    f"T15 FAIL: adapters.py imports dask ({name!r})."
                )


def test_t16_no_distributed_import():
    """T16: adapters.py does not import 'distributed' (Dask scheduler)."""
    tree = ast.parse(_ADAPTERS_SOURCE)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else ([node.module] if node.module else [])
            )
            for name in names:
                assert not (name or "").startswith("distributed"), (
                    f"T16 FAIL: adapters.py imports 'distributed' ({name!r})."
                )


# ===========================================================================
# T17 — No new Spark/Dask dependency in pyproject.toml
# ===========================================================================

def test_t17_no_distributed_dependency_in_pyproject():
    """T17: pyproject.toml does not list pyspark, dask, or distributed."""
    pyproject_path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "pyproject.toml"
    )
    content = open(pyproject_path, encoding="utf-8").read().lower()
    for forbidden in ("pyspark", "dask", "distributed"):
        assert forbidden not in content, (
            f"T17 FAIL: pyproject.toml contains '{forbidden}' dependency."
        )


# ===========================================================================
# T18 — compute_coverage_score still works with local adapter unchanged
# ===========================================================================

def test_t18_compute_coverage_score_works_with_local_adapter():
    """T18: compute_coverage_score behaviour is unchanged with AHPAdapter."""
    fv = FeatureVector(
        elevation_m=200.0, slope_deg=5.0, land_cover_class=30,
        canopy_height_m=5.0, distance_to_bts_m=3000.0,
        road_distance_m=800.0, population_density_per_km2=400.0,
        facility_proximity_m=1500.0,
    )
    score = compute_coverage_score(fv, _INNER)
    assert 0.0 <= score <= 100.0, f"T18 FAIL: score {score} outside [0, 100]."


# ===========================================================================
# T19 — Existing adapters still satisfy ScoringAdapter protocol
# ===========================================================================

def test_t19_ahp_adapter_satisfies_protocol():
    """T19: AHPAdapter has predict and shap_values callable methods."""
    a = AHPAdapter()
    assert callable(a.predict)
    assert callable(a.shap_values)


def test_t19b_xgboost_adapter_satisfies_protocol():
    """T19b: XGBoostAdapter (no model) has predict and shap_values."""
    a = XGBoostAdapter(model_path=None)
    assert callable(a.predict)
    assert callable(a.shap_values)


def test_t19c_lightgbm_adapter_satisfies_protocol():
    """T19c: LightGBMAdapter (no model) has predict and shap_values."""
    a = LightGBMAdapter(model_path=None)
    assert callable(a.predict)
    assert callable(a.shap_values)


# ===========================================================================
# T20 — Future wrapper does not require signature changes on compute_coverage_score
# ===========================================================================

def test_t20_compute_coverage_score_accepts_any_adapter_by_protocol():
    """T20: compute_coverage_score accepts any object with predict(); no isinstance check."""
    import inspect
    src = inspect.getsource(compute_coverage_score)
    assert "isinstance" not in src, (
        "T20 FAIL: compute_coverage_score contains isinstance() — "
        "this would reject wrapper adapters."
    )


# ===========================================================================
# T21 — Candidate ranking module does not import executor framework
# ===========================================================================

def test_t21_scoring_module_no_distributed_imports():
    """T21: scoring.py does not import pyspark, dask, or distributed."""
    scoring_path = os.path.join(
        os.path.dirname(__file__), "..", "backend", "geosignal", "scoring.py"
    )
    src = open(scoring_path, encoding="utf-8").read()
    for forbidden in ("pyspark", "dask", "distributed"):
        assert forbidden not in src, (
            f"T21 FAIL: scoring.py imports '{forbidden}'."
        )


# ===========================================================================
# T22 — Adapter stores inner and executor without running them
# ===========================================================================

def test_t22_adapter_stores_inner_reference():
    """T22: adapter.inner returns the same object passed to the constructor."""
    inner = AHPAdapter()
    adapter = DistributedScoringAdapter(inner=inner, executor=FakeExecutor())
    assert adapter.inner is inner, (
        "T22 FAIL: adapter.inner does not return the original inner object."
    )


def test_t22b_adapter_stores_executor_reference():
    """T22b: adapter.executor returns the same object passed to the constructor."""
    executor = FakeExecutor()
    adapter = DistributedScoringAdapter(inner=_INNER, executor=executor)
    assert adapter.executor is executor, (
        "T22b FAIL: adapter.executor does not return the original executor."
    )


def test_t22c_executor_not_called_after_construction():
    """T22c: executor.map() is still at 0 calls after construction."""
    spy = FakeExecutor()
    adapter = DistributedScoringAdapter(inner=_INNER, executor=spy)
    assert spy.map_call_count == 0


# ===========================================================================
# T23 — Fake executor satisfies DistributedExecutorProtocol structurally
# ===========================================================================

def test_t23_fake_executor_satisfies_protocol():
    """T23: FakeExecutor has callable map() — satisfies DistributedExecutorProtocol."""
    fake = FakeExecutor()
    assert callable(getattr(fake, "map", None)), (
        "T23 FAIL: FakeExecutor.map is not callable."
    )


# ===========================================================================
# T24 — Invalid inner rejected with TypeError
# ===========================================================================

def test_t24_invalid_inner_missing_predict_raises_type_error():
    """T24: inner without predict() raises TypeError at construction time."""
    class BadInner:
        def shap_values(self, f):
            return np.zeros((len(f), 8))
    with pytest.raises(TypeError, match="ScoringAdapter"):
        DistributedScoringAdapter(inner=BadInner(), executor=FakeExecutor())


def test_t24b_invalid_inner_missing_shap_raises_type_error():
    """T24b: inner without shap_values() raises TypeError at construction time."""
    class BadInner:
        def predict(self, f):
            return np.zeros(len(f))
    with pytest.raises(TypeError, match="ScoringAdapter"):
        DistributedScoringAdapter(inner=BadInner(), executor=FakeExecutor())


def test_t24c_inner_none_raises_type_error():
    """T24c: passing None as inner raises TypeError."""
    with pytest.raises(TypeError):
        DistributedScoringAdapter(inner=None, executor=FakeExecutor())  # type: ignore[arg-type]


# ===========================================================================
# T25 — Invalid executor rejected with TypeError
# ===========================================================================

def test_t25_invalid_executor_no_map_raises_type_error():
    """T25: executor without map() raises TypeError at construction time."""
    class BadExecutor:
        pass
    with pytest.raises(TypeError, match="DistributedExecutorProtocol"):
        DistributedScoringAdapter(inner=_INNER, executor=BadExecutor())


def test_t25b_executor_none_raises_type_error():
    """T25b: passing None as executor raises TypeError."""
    with pytest.raises(TypeError):
        DistributedScoringAdapter(inner=_INNER, executor=None)  # type: ignore[arg-type]


# ===========================================================================
# Extra — Adapter usable as ScoringAdapter type annotation at call site
# ===========================================================================

def test_extra_distributed_adapter_accepted_as_scoring_adapter_type():
    """Extra: DistributedScoringAdapter can be assigned to a ScoringAdapter-typed var.

    This verifies the architectural goal: calling code only sees ScoringAdapter.
    """
    adapter: ScoringAdapter = DistributedScoringAdapter(  # type: ignore[assignment]
        inner=AHPAdapter(),
        executor=FakeExecutor(),
    )
    # The variable is held; the assignment itself is the test.
    assert adapter is not None


def test_extra_compute_coverage_score_raises_when_given_distributed_adapter():
    """Extra: compute_coverage_score propagates NotImplementedError from stub.

    This confirms no isinstance check in compute_coverage_score silently swallows
    the error — the Phase 3 stub error surfaces correctly to the caller.
    """
    fv = FeatureVector(
        elevation_m=200.0, slope_deg=5.0, land_cover_class=30,
        canopy_height_m=5.0, distance_to_bts_m=3000.0,
        road_distance_m=800.0, population_density_per_km2=400.0,
        facility_proximity_m=1500.0,
    )
    dist_adapter = DistributedScoringAdapter(inner=_INNER, executor=FakeExecutor())
    with pytest.raises(NotImplementedError, match=r"(?i)phase 3|distributed"):
        compute_coverage_score(fv, dist_adapter)


def test_extra_gnn_adapter_still_raises_not_implemented():
    """Extra: GNNAdapter Phase 3 stub still works correctly after changes."""
    gnn = GNNAdapter()
    with pytest.raises(NotImplementedError):
        gnn.predict(np.zeros((2, 8)))
    with pytest.raises(NotImplementedError):
        gnn.shap_values(np.zeros((2, 8)))
