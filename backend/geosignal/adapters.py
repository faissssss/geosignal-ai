"""GeoSignal AI — Model adapter layer.

Defines the ScoringAdapter protocol and all concrete implementations:
  - AHPAdapter                (Tier 1 cold-start, equity-weighted)
  - XGBoostAdapter            (Tier 2 trained against Ookla ground-truth labels)
  - LightGBMAdapter           (Tier 2 alternative to XGBoost)
  - GNNAdapter                (Phase 3 stub)
  - DistributedExecutorProtocol  (Phase 3 executor abstraction — framework-agnostic)
  - DistributedScoringAdapter (Phase 3 distributed-compute stub)

IMPORTANT:
  - Ookla is NOT a feature — it is the Tier 2 training label only.
  - Admin boundary identifiers are NOT inputs.
  - Import CONSOLIDATED_FEATURES from geosignal.models; never redefine here.
  - DistributedScoringAdapter does NOT import pyspark, dask, or distributed.
    It is a Phase 3 interface stub only — no distributed workload runs in the MVP.
"""
from __future__ import annotations

import os
from typing import Any, Protocol, Sequence

import numpy as np

from geosignal.models import CONSOLIDATED_FEATURES

# ── Feature index helpers ─────────────────────────────────────────────────────
# These indices correspond to the CONSOLIDATED_FEATURES order.
_IDX = {feat: i for i, feat in enumerate(CONSOLIDATED_FEATURES)}

# Features where smaller value → better (distances); invert so smaller → larger
# normalised value.
_DISTANCE_FEATURES = {"distance_to_bts_m", "road_distance_m", "facility_proximity_m"}

# Default AHP equity weights.
# facility_proximity_m and population_density_per_km2 carry ~2× flat baseline (1/8=0.125).
# Remaining 6 features share 0.60 evenly → 0.10 each.
_DEFAULT_AHP_WEIGHTS: dict[str, float] = {
    "elevation_m": 0.10,
    "slope_deg": 0.10,
    "land_cover_class": 0.10,
    "canopy_height_m": 0.10,
    "distance_to_bts_m": 0.10,
    "road_distance_m": 0.10,
    "population_density_per_km2": 0.20,
    "facility_proximity_m": 0.20,
}


# ── ScoringAdapter protocol ───────────────────────────────────────────────────

class ScoringAdapter(Protocol):
    """Protocol that all scoring adapters must satisfy."""

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Accept (N, 8) feature array; return (N,) score array."""
        ...

    def shap_values(self, features: np.ndarray) -> np.ndarray:
        """Accept (N, 8) feature array; return (N, 8) SHAP/attribution array."""
        ...


# ── AHPAdapter ────────────────────────────────────────────────────────────────

class AHPAdapter:
    """Tier 1 AHP cold-start adapter with equity weighting.

    Equity constraints (Requirement 9.1):
      - facility_proximity_m and population_density_per_km2 have elevated weights.
      - Closer facility → smaller distance → higher score (distance inversion).
      - Higher population density → higher score (direct).
    """

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        if weights is None:
            weights = dict(_DEFAULT_AHP_WEIGHTS)

        # Normalise weights so they sum exactly to 1.0.
        total = sum(weights.values())
        if total == 0:
            raise ValueError("AHP weights must not all be zero.")
        self._weights: dict[str, float] = {k: v / total for k, v in weights.items()}

        # Build weight vector aligned to CONSOLIDATED_FEATURES order.
        self._weight_vector = np.array(
            [self._weights[feat] for feat in CONSOLIDATED_FEATURES], dtype=np.float64
        )

    # ------------------------------------------------------------------
    # Internal: feature normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_features(features: np.ndarray) -> np.ndarray:
        """Return (N, 8) normalised array in [0, 1].

        Normalisation strategy per feature:
          - Distance features (distance_to_bts_m, road_distance_m,
            facility_proximity_m): use 1/(1 + d/1000) so smaller distance →
            larger normalised value (equity constraint: closer facility = better).
          - All other features: min-max across the batch; if all values are
            identical, map to 0.5 to avoid divide-by-zero.
        """
        N, F = features.shape
        normed = np.empty_like(features, dtype=np.float64)

        for feat, idx in _IDX.items():
            col = features[:, idx].astype(np.float64)
            if feat in _DISTANCE_FEATURES:
                # Invert: smaller distance → value closer to 1.0
                normed[:, idx] = 1.0 / (1.0 + col / 1000.0)
            else:
                # Min-max within the batch
                col_min = col.min()
                col_max = col.max()
                if col_max > col_min:
                    normed[:, idx] = (col - col_min) / (col_max - col_min)
                else:
                    # All identical — use 0.5 (neutral, avoids misleading 0)
                    normed[:, idx] = 0.5

        return normed

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Return (N,) Coverage Score array in [0, 100].

        Args:
            features: (N, 8) array in CONSOLIDATED_FEATURES column order.

        Returns:
            (N,) float64 array clipped to [0.0, 100.0].
        """
        features = np.atleast_2d(np.asarray(features, dtype=np.float64))
        normed = self._normalise_features(features)
        # Weighted sum → scalar in [0, 1] (since normed ∈ [0,1] and weights sum to 1)
        raw = normed @ self._weight_vector  # (N,)
        # Map to [0, 100]
        scores = raw * 100.0
        return np.clip(scores, 0.0, 100.0)

    def shap_values(self, features: np.ndarray) -> np.ndarray:
        """Return (N, 8) pseudo-SHAP values: weight × normalised_feature_value.

        This linear attribution is used by compute_ahp_shap (Task 10).
        """
        features = np.atleast_2d(np.asarray(features, dtype=np.float64))
        normed = self._normalise_features(features)
        # Element-wise multiply each column by its weight
        return normed * self._weight_vector  # (N, 8)

    @property
    def weights(self) -> dict[str, float]:
        """Return the normalised weight dict."""
        return dict(self._weights)


# ── XGBoostAdapter ────────────────────────────────────────────────────────────

class XGBoostAdapter:
    """Tier 2 XGBoost adapter — trained against Ookla ground-truth labels.

    Ookla is the training label ONLY; it is never a scoring input feature.
    """

    def __init__(self, model_path: str | None = None) -> None:
        """Load model from path.

        If path is None or file is missing, model is None (untrained state).
        Raises RuntimeError on predict/shap_values when untrained.
        """
        self._model = None
        if model_path is not None:
            self._load(model_path)

    def _load(self, path: str) -> None:
        try:
            import xgboost as xgb  # noqa: PLC0415 — optional at import time

            booster = xgb.Booster()
            booster.load_model(path)
            self._model = booster
        except Exception as exc:  # noqa: BLE001
            # File missing, corrupt, or xgboost unavailable — stay untrained.
            self._model = None
            self._load_error = str(exc)

    @classmethod
    def from_path(cls, path: str) -> "XGBoostAdapter":
        """Convenience constructor: XGBoostAdapter.from_path('model.json')."""
        return cls(model_path=path)

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Return (N,) Coverage Score array clipped to [0, 100].

        Raises:
            RuntimeError: if no model is loaded.
        """
        if self._model is None:
            raise RuntimeError("XGBoostAdapter has no model loaded")
        import xgboost as xgb  # noqa: PLC0415

        features = np.atleast_2d(np.asarray(features, dtype=np.float32))
        dmat = xgb.DMatrix(features)
        raw = self._model.predict(dmat)
        return np.clip(raw, 0.0, 100.0).astype(np.float64)

    def shap_values(self, features: np.ndarray) -> np.ndarray:
        """Return (N, 8) SHAP values via TreeExplainer.

        Raises:
            RuntimeError: if no model is loaded.
        """
        if self._model is None:
            raise RuntimeError("XGBoostAdapter has no model loaded")
        import shap  # noqa: PLC0415

        features = np.atleast_2d(np.asarray(features, dtype=np.float32))
        explainer = shap.TreeExplainer(self._model)
        sv = explainer.shap_values(features)
        return np.asarray(sv, dtype=np.float64)


# ── LightGBMAdapter ───────────────────────────────────────────────────────────

class LightGBMAdapter:
    """Tier 2 LightGBM adapter — same structure as XGBoostAdapter.

    Trained against Ookla ground-truth labels.
    Ookla is the training label ONLY; never a scoring input.
    """

    def __init__(self, model_path: str | None = None) -> None:
        """Load model from path.

        If path is None or file is missing, model is None (untrained state).
        """
        self._model = None
        if model_path is not None:
            self._load(model_path)

    def _load(self, path: str) -> None:
        try:
            import lightgbm as lgb  # noqa: PLC0415

            self._model = lgb.Booster(model_file=path)
        except Exception as exc:  # noqa: BLE001
            self._model = None
            self._load_error = str(exc)

    @classmethod
    def from_path(cls, path: str) -> "LightGBMAdapter":
        """Convenience constructor: LightGBMAdapter.from_path('model.txt')."""
        return cls(model_path=path)

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Return (N,) Coverage Score array clipped to [0, 100].

        Raises:
            RuntimeError: if no model is loaded.
        """
        if self._model is None:
            raise RuntimeError("LightGBMAdapter has no model loaded")
        features = np.atleast_2d(np.asarray(features, dtype=np.float32))
        raw = self._model.predict(features)
        return np.clip(raw, 0.0, 100.0).astype(np.float64)

    def shap_values(self, features: np.ndarray) -> np.ndarray:
        """Return (N, 8) SHAP values via TreeExplainer.

        Raises:
            RuntimeError: if no model is loaded.
        """
        if self._model is None:
            raise RuntimeError("LightGBMAdapter has no model loaded")
        import shap  # noqa: PLC0415

        features = np.atleast_2d(np.asarray(features, dtype=np.float32))
        explainer = shap.TreeExplainer(self._model)
        sv = explainer.shap_values(features)
        return np.asarray(sv, dtype=np.float64)


# ── GNNAdapter (Phase 3 stub) ──────────────────────────────────────────────────

class GNNAdapter:
    """Phase 3 stub — Graph Neural Network adapter.

    Both methods raise NotImplementedError to signal Phase 3 placeholder status.
    """

    def predict(self, features: np.ndarray) -> np.ndarray:
        raise NotImplementedError("GNNAdapter is a Phase 3 placeholder.")

    def shap_values(self, features: np.ndarray) -> np.ndarray:
        raise NotImplementedError("GNNAdapter is a Phase 3 placeholder.")


# ── DistributedExecutorProtocol ───────────────────────────────────────────────

class DistributedExecutorProtocol(Protocol):
    """Minimal protocol for a distributed-compute executor.

    Phase 3 interface — framework-agnostic.

    Concrete implementations are NOT part of the MVP.  Future work will
    provide implementations backed by Apache Spark, Dask, or another
    distributed scheduler.  The protocol is intentionally narrow:
    callers only need to be able to map a function over a sequence of
    partitions and collect the results in order.

    This protocol does NOT import pyspark, dask, or distributed.
    It does NOT open any network connection.
    It does NOT create any cluster or scheduler.
    """

    def map(
        self,
        fn: Any,
        partitions: Sequence[np.ndarray],
    ) -> Sequence[np.ndarray]:
        """Apply *fn* to each partition and return results in the same order.

        Contract:
          - len(result) == len(partitions).
          - result[i] corresponds to partitions[i].
          - Row order within each partition is preserved.
          - No partition is duplicated or dropped.

        Phase 3 note:
          A Spark implementation would serialise *fn* via cloudpickle and
          distribute partitions across executors; a Dask implementation would
          create a task graph.  Both are out of scope for the MVP.

        Args:
            fn:         A callable that accepts a single np.ndarray partition
                        and returns a np.ndarray result.
            partitions: An ordered sequence of np.ndarray chunks.

        Returns:
            A sequence of np.ndarray results in the same order as *partitions*.
        """
        ...


# ── DistributedScoringAdapter ─────────────────────────────────────────────────

class DistributedScoringAdapter:
    """Phase 3 architectural stub for distributed-compute scoring.

    PURPOSE
    -------
    This class defines the interface boundary that allows GeoSignal AI's
    scoring pipeline to be extended to Apache Spark, Dask, or another
    distributed compute framework in Phase 3 WITHOUT changing any calling
    code (compute_coverage_score, rank_bts_candidates, spatial_cv).

    WHAT THIS IS
    ------------
    - An architectural stub only.
    - Wraps an existing ScoringAdapter as ``inner``.
    - Accepts a ``DistributedExecutorProtocol`` as ``executor``.
    - Satisfies the ScoringAdapter protocol (has predict + shap_values).
    - Constructor stores references; it does NOT invoke the executor.

    WHAT THIS IS NOT
    ----------------
    - NOT a production distributed implementation.
    - Does NOT import pyspark, dask, distributed, or any scheduler.
    - Does NOT open network connections.
    - Does NOT create clusters, threads, or processes.
    - Does NOT fall back silently to local execution.
    - Does NOT return mock predictions.

    MVP BEHAVIOUR
    -------------
    Both predict() and shap_values() raise NotImplementedError with a message
    that clearly identifies this as a Phase 3 stub.  No predictions are
    produced; no local execution occurs as a side-effect.

    PHASE 3 DESIGN (for future implementors)
    -----------------------------------------
    When implemented, the distributed execution plan is:

      predict(features):
        1. Partition ``features`` (N, 8) into K chunks along axis 0.
        2. Submit each chunk to executor.map(inner.predict, chunks).
        3. Concatenate results in original row order → shape (N,).
        4. Empty input (N=0) returns np.empty((0,), dtype=float64).

      shap_values(features):
        1. Partition ``features`` (N, 8) into K chunks.
        2. Submit each chunk to executor.map(inner.shap_values, chunks).
        3. Concatenate results in original row order → shape (N, 8).
        4. Empty input (N=0) returns np.empty((0, 8), dtype=float64).

    Invariants that the implementation must preserve:
      - Output row count == input row count (no duplication or loss).
      - Output row order == input row order.
      - inner is the sole source of scoring logic; this wrapper adds only
        the partitioning envelope.
      - overlay_enabled and kecamatan IDs are never passed to inner.predict.
      - Preprocessing (normalisation) is applied before this adapter is
        invoked; the adapter itself does not normalise.

    CALLING CODE COMPATIBILITY
    --------------------------
    The following callers work with any ScoringAdapter and require NO changes
    to support DistributedScoringAdapter:

      - compute_coverage_score(features, adapter)   — scoring.py
      - rank_bts_candidates(...)                     — uses compute_coverage_score
      - spatial_cv(...)                              — validation.py

    None of these functions import Spark, Dask, or this class by name.
    They accept any object that satisfies the ScoringAdapter protocol.
    """

    def __init__(
        self,
        inner: ScoringAdapter,
        executor: DistributedExecutorProtocol,
    ) -> None:
        """Store inner adapter and executor without invoking either.

        Args:
            inner:    Any ScoringAdapter (AHPAdapter, XGBoostAdapter, etc.).
                      Must already be initialised and ready to use.
            executor: Any object satisfying DistributedExecutorProtocol.
                      The constructor does NOT call executor.map().

        Raises:
            TypeError: if inner does not have predict and shap_values methods.
            TypeError: if executor does not have a map method.
        """
        if not (callable(getattr(inner, "predict", None))
                and callable(getattr(inner, "shap_values", None))):
            raise TypeError(
                "inner must be a ScoringAdapter with callable predict() and "
                f"shap_values() methods. Got: {type(inner)!r}"
            )
        if not callable(getattr(executor, "map", None)):
            raise TypeError(
                "executor must satisfy DistributedExecutorProtocol with a "
                f"callable map() method. Got: {type(executor)!r}"
            )
        self._inner = inner
        self._executor = executor

    # ------------------------------------------------------------------
    # ScoringAdapter interface — Phase 3 stubs
    # ------------------------------------------------------------------

    def predict(self, features: np.ndarray) -> np.ndarray:
        """[Phase 3 stub] Distribute predict() across executor partitions.

        In the MVP this method raises NotImplementedError.
        Distributed execution is a Phase 3 capability and is not implemented
        in the MVP.

        Phase 3 contract (not yet active):
          - Partitions features (N, 8) along axis 0.
          - Maps inner.predict over partitions via executor.map().
          - Concatenates results preserving row order.
          - Returns (N,) float64 array in [0, 100].

        Args:
            features: (N, 8) float64 array in CONSOLIDATED_FEATURES order.

        Raises:
            NotImplementedError: always, in the MVP.
        """
        raise NotImplementedError(
            "DistributedScoringAdapter.predict() is a Phase 3 stub. "
            "Distributed execution is a Phase 3 capability and is not "
            "implemented in the MVP. Use a local adapter (AHPAdapter, "
            "XGBoostAdapter, LightGBMAdapter) for MVP scoring."
        )

    def shap_values(self, features: np.ndarray) -> np.ndarray:
        """[Phase 3 stub] Distribute shap_values() across executor partitions.

        In the MVP this method raises NotImplementedError.
        Distributed execution is a Phase 3 capability and is not implemented
        in the MVP.

        Phase 3 contract (not yet active):
          - Partitions features (N, 8) along axis 0.
          - Maps inner.shap_values over partitions via executor.map().
          - Concatenates results preserving row order.
          - Returns (N, 8) float64 array.

        Args:
            features: (N, 8) float64 array in CONSOLIDATED_FEATURES order.

        Raises:
            NotImplementedError: always, in the MVP.
        """
        raise NotImplementedError(
            "DistributedScoringAdapter.shap_values() is a Phase 3 stub. "
            "Distributed execution is a Phase 3 capability and is not "
            "implemented in the MVP. Use a local adapter (AHPAdapter, "
            "XGBoostAdapter, LightGBMAdapter) for MVP SHAP values."
        )

    # ------------------------------------------------------------------
    # Inspection helpers (do not trigger distributed work)
    # ------------------------------------------------------------------

    @property
    def inner(self) -> ScoringAdapter:
        """Return the wrapped inner adapter (read-only, no execution)."""
        return self._inner

    @property
    def executor(self) -> DistributedExecutorProtocol:
        """Return the registered executor (read-only, no execution)."""
        return self._executor
