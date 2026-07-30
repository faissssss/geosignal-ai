"""GeoSignal AI — Model adapter layer.

Defines the ScoringAdapter protocol and all concrete implementations:
  - AHPAdapter      (Tier 1 cold-start, equity-weighted)
  - XGBoostAdapter  (Tier 2 trained against Ookla ground-truth labels)
  - LightGBMAdapter (Tier 2 alternative to XGBoost)
  - GNNAdapter      (Phase 3 stub)

IMPORTANT:
  - Ookla is NOT a feature — it is the Tier 2 training label only.
  - Admin boundary identifiers are NOT inputs.
  - Import CONSOLIDATED_FEATURES from geosignal.models; never redefine here.
"""
from __future__ import annotations

import os
from typing import Protocol

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
