"""GeoSignal AI — Recommendation_Engine scoring utilities.

Defines:
  - ModelTier           enum (TIER1=AHP, TIER2=XGBoost/LightGBM)
  - select_tier         selects tier based on ookla_tile_count
  - compute_coverage_score   computes float in [0, 100] for a FeatureVector
  - load_adapter_with_fallback  Tier2 → Tier1 fallback with structured logging

IMPORTANT:
  - Ookla is NOT a feature — it is the Tier 2 training label only.
  - CONSOLIDATED_FEATURES and FeatureVector are imported from geosignal.models.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

import numpy as np

from geosignal.models import CONSOLIDATED_FEATURES, FeatureVector

if TYPE_CHECKING:
    from geosignal.adapters import AHPAdapter, ScoringAdapter


# ── ModelTier ─────────────────────────────────────────────────────────────────

class ModelTier(Enum):
    """Two-tier model selector.

    TIER1 = "1"  — AHP cold-start (used when no Ookla tiles exist)
    TIER2 = "2"  — XGBoost / LightGBM (used when Ookla tiles are available)
    """

    TIER1 = "1"
    TIER2 = "2"


# ── Tier selection ─────────────────────────────────────────────────────────────

def select_tier(kecamatan_id: str, ookla_tile_count: int) -> ModelTier:
    """Return TIER1 when ookla_tile_count == 0, else TIER2.

    The two tiers are exhaustive and mutually exclusive — no other tiers exist.

    Args:
        kecamatan_id:      Administrative unit identifier (for logging; not used
                           in the tier decision itself).
        ookla_tile_count:  Number of Ookla speed-test tiles available for this
                           kecamatan.  Must be ≥ 0.

    Returns:
        ModelTier.TIER1 when count == 0, ModelTier.TIER2 when count > 0.
    """
    if ookla_tile_count == 0:
        return ModelTier.TIER1
    return ModelTier.TIER2


# ── Coverage Score computation ────────────────────────────────────────────────

def compute_coverage_score(features: FeatureVector, adapter: "ScoringAdapter") -> float:
    """Return a Coverage Score in [0.0, 100.0] for a single FeatureVector.

    Works for both AHPAdapter and XGBoostAdapter/LightGBMAdapter — any object
    that implements the ScoringAdapter protocol.

    Args:
        features: A single grid-cell FeatureVector.
        adapter:  Any ScoringAdapter (AHPAdapter, XGBoostAdapter, etc.).

    Returns:
        float clipped to [0.0, 100.0].
    """
    # Build a (1, 8) array in CONSOLIDATED_FEATURES order.
    features_array = np.array(
        [[getattr(features, feat) for feat in CONSOLIDATED_FEATURES]],
        dtype=np.float64,
    )

    raw = adapter.predict(features_array)

    # raw is (N,) or scalar; take the first element.
    score = float(np.squeeze(raw))
    return float(np.clip(score, 0.0, 100.0))


# ── Tier 2 → Tier 1 fallback ─────────────────────────────────────────────────

def load_adapter_with_fallback(
    tier: ModelTier,
    kecamatan_id: str,
    tier2_adapter_factory: callable,
    tier1_adapter: "AHPAdapter",
    fallback_log: list,
) -> tuple["ScoringAdapter", ModelTier]:
    """Try to load the Tier 2 adapter; fall back to Tier 1 on failure.

    When a Tier 2 model artifact is missing, corrupt, or fails to load for a
    kecamatan, this function automatically falls back to the provided
    ``tier1_adapter`` (AHPAdapter) and records the event.

    Args:
        tier:                  The requested ModelTier (TIER1 or TIER2).
        kecamatan_id:          The administrative unit being scored.
        tier2_adapter_factory: A zero-argument callable that returns a
                               ScoringAdapter or raises an exception.
        tier1_adapter:         The AHPAdapter instance to use as the fallback.
        fallback_log:          A mutable list to which fallback event dicts are
                               appended.  Each dict has keys:
                                 - "kecamatan_id"
                                 - "reason"
                                 - "model_version_attempted"

    Returns:
        (adapter, actual_tier_used) — a tuple of the chosen ScoringAdapter and
        the ModelTier that was actually used.
    """
    if tier == ModelTier.TIER1:
        # No Tier 2 attempted; return Tier 1 directly.
        return tier1_adapter, ModelTier.TIER1

    # Attempt Tier 2.
    model_version_attempted: str | None = None
    try:
        adapter = tier2_adapter_factory()
        return adapter, ModelTier.TIER2
    except Exception as exc:  # noqa: BLE001
        reason = f"{type(exc).__name__}: {exc}"
        fallback_log.append(
            {
                "kecamatan_id": kecamatan_id,
                "reason": reason,
                "model_version_attempted": model_version_attempted,
            }
        )
        return tier1_adapter, ModelTier.TIER1
