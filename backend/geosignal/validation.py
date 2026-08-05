"""GeoSignal AI — Spatial Cross-Validation (Task 28).

Provides:
    spatial_cv   — leave-one-kecamatan-out spatial cross-validation.

Design constraints (Requirements 2.4, 9.4, 13.5):
    - Split unit is the kecamatan, never the individual point.
    - Train and test kecamatan sets are always disjoint.
    - Every kecamatan becomes a test block exactly once (LOKO: Leave-One-
      Kecamatan-Out).
    - Per-kecamatan accuracy is reported for every kecamatan in the input;
      no kecamatan is collapsed into an "others" label.
    - Aggregate accuracy is derived from the per-kecamatan entries and never
      replaces them.
    - Preprocessing (feature normalisation) is fit on the train fold only and
      transforms the test fold separately — no leakage.
    - Kecamatan IDs are never passed to the scoring adapter as features.
    - Random point split is never used as a fallback.

The scoring adapter is passed in from the caller; this module does not create
or modify any adapter, weights, or coverage-score formula.
"""
from __future__ import annotations

import math
import time
from typing import Sequence

import numpy as np

from geosignal.models import (
    CONSOLIDATED_FEATURES,
    CVResult,
    FeatureVector,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fv_to_array(fv: FeatureVector) -> np.ndarray:
    """Convert a FeatureVector to a (8,) float64 array in CONSOLIDATED_FEATURES order.

    Kecamatan ID is deliberately excluded — it is never a model feature.
    """
    return np.array(
        [float(getattr(fv, feat)) for feat in CONSOLIDATED_FEATURES],
        dtype=np.float64,
    )


def _compute_accuracy(
    true_scores: np.ndarray,
    pred_scores: np.ndarray,
    tolerance: float = 5.0,
) -> float:
    """Return the fraction of predictions within *tolerance* of the ground truth.

    Args:
        true_scores:  (N,) array of reference Coverage Scores.
        pred_scores:  (N,) array of predicted Coverage Scores.
        tolerance:    Acceptable absolute error (default 5 score points).

    Returns:
        float in [0.0, 1.0] — proportion of predictions within tolerance.
        Returns 0.0 for empty arrays.
    """
    if len(true_scores) == 0:
        return 0.0
    within = np.abs(pred_scores - true_scores) <= tolerance
    return float(within.sum()) / float(len(true_scores))


def _fit_normaliser(train_features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fit min/max normalisation parameters on the training fold.

    Args:
        train_features: (N_train, 8) array.

    Returns:
        (col_min, col_range) — each shape (8,).
        For constant columns, col_range is set to 1.0 to avoid division by zero.
    """
    col_min = train_features.min(axis=0)
    col_max = train_features.max(axis=0)
    col_range = col_max - col_min
    # Avoid divide-by-zero for constant columns
    col_range = np.where(col_range == 0.0, 1.0, col_range)
    return col_min, col_range


def _apply_normaliser(
    features: np.ndarray,
    col_min: np.ndarray,
    col_range: np.ndarray,
) -> np.ndarray:
    """Apply train-fold normalisation parameters to any split (train or test).

    Fit was done on train only; this function applies those parameters.
    """
    return (features - col_min) / col_range


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def spatial_cv(
    kecamatan_ids: Sequence[str],
    feature_vectors: Sequence[FeatureVector],
    coverage_scores: Sequence[float],
    adapter,
    *,
    tolerance: float = 5.0,
    normalise: bool = False,
) -> CVResult:
    """Leave-one-kecamatan-out (LOKO) spatial cross-validation.

    For each unique kecamatan K:
        train = all rows whose kecamatan_id != K
        test  = all rows whose kecamatan_id == K

    The adapter is evaluated on the test fold using its predict() method.
    Accuracy for kecamatan K is the proportion of predictions within
    *tolerance* score points of the reference coverage_scores.

    Preprocessing leakage guard: when normalise=True, the min/max parameters
    are fit ONLY on the train fold and applied to the test fold — the test
    fold never influences the normalisation.

    Kecamatan IDs are not forwarded to the adapter.

    Args:
        kecamatan_ids:    Sequence of kecamatan IDs, one per row.
        feature_vectors:  Sequence of FeatureVector, one per row.
        coverage_scores:  Sequence of reference Coverage Scores, one per row.
        adapter:          Any ScoringAdapter (AHPAdapter etc.).
        tolerance:        Maximum acceptable absolute error (score points).
        normalise:        If True, apply train-fold min/max normalisation
                          before scoring.  Fit is on train fold only.

    Returns:
        CVResult with:
            kecamatan_accuracies — dict mapping every unique kecamatan_id
                                   in the input to its accuracy float.
            n_folds              — number of unique kecamatan (= number of
                                   LOKO folds).

    Raises:
        ValueError:  If fewer than 2 kecamatan are present (cannot form a
                     meaningful train/test split).
        ValueError:  If any sequence lengths do not match.
        ValueError:  If any coverage_score is not finite.
    """
    # ── Input validation ────────────────────────────────────────────────────
    n = len(kecamatan_ids)
    if len(feature_vectors) != n or len(coverage_scores) != n:
        raise ValueError(
            f"kecamatan_ids, feature_vectors, and coverage_scores must all have "
            f"the same length. Got {n}, {len(feature_vectors)}, {len(coverage_scores)}."
        )

    # Reject non-finite reference scores immediately
    for i, s in enumerate(coverage_scores):
        if not math.isfinite(float(s)):
            raise ValueError(
                f"coverage_scores[{i}] = {s!r} is not finite. "
                "Non-finite reference scores are not accepted."
            )

    unique_kecamatan: list[str] = list(dict.fromkeys(kecamatan_ids))  # insertion-order, deduped

    if len(unique_kecamatan) < 2:
        raise ValueError(
            f"spatial_cv requires at least 2 distinct kecamatan for a meaningful "
            f"train/test split. Got {len(unique_kecamatan)}: {unique_kecamatan!r}."
        )

    # Convert to numpy for indexing
    kec_arr   = np.array(kecamatan_ids, dtype=object)
    feat_arr  = np.array([_fv_to_array(fv) for fv in feature_vectors], dtype=np.float64)
    score_arr = np.array([float(s) for s in coverage_scores], dtype=np.float64)

    # ── LOKO folds ───────────────────────────────────────────────────────────
    kecamatan_accuracies: dict[str, float] = {}

    for test_kecamatan in unique_kecamatan:
        test_mask  = kec_arr == test_kecamatan
        train_mask = ~test_mask

        # Disjoint check (invariant — always true by construction, but verify)
        assert not np.any(train_mask & test_mask), (
            f"Data-leakage detected: kecamatan '{test_kecamatan}' appears in both "
            "train and test masks."
        )

        train_features = feat_arr[train_mask]
        test_features  = feat_arr[test_mask]
        test_scores    = score_arr[test_mask]

        # ── Preprocessing leakage guard ─────────────────────────────────────
        if normalise:
            if train_features.shape[0] == 0:
                # Edge case: all rows belong to this kecamatan (caught by
                # the <2 kecamatan check above, but defensive)
                col_min   = np.zeros(feat_arr.shape[1], dtype=np.float64)
                col_range = np.ones(feat_arr.shape[1], dtype=np.float64)
            else:
                col_min, col_range = _fit_normaliser(train_features)

            # Test fold is transformed with train parameters — never leaks
            test_features = _apply_normaliser(test_features, col_min, col_range)

        # ── Score the test fold ─────────────────────────────────────────────
        if test_features.shape[0] == 0:
            kecamatan_accuracies[test_kecamatan] = 0.0
            continue

        pred_scores = adapter.predict(test_features)
        pred_scores = np.asarray(pred_scores, dtype=np.float64).ravel()

        # Verify predicted scores are finite (reject NaN / Inf)
        if not np.all(np.isfinite(pred_scores)):
            raise ValueError(
                f"Adapter returned non-finite predictions for kecamatan "
                f"'{test_kecamatan}': {pred_scores!r}. "
                "Non-finite accuracy is not accepted."
            )

        acc = _compute_accuracy(test_scores, pred_scores, tolerance=tolerance)
        kecamatan_accuracies[test_kecamatan] = acc

    # ── Verify completeness ──────────────────────────────────────────────────
    # Every unique kecamatan in the input must have exactly one accuracy entry.
    missing = set(unique_kecamatan) - set(kecamatan_accuracies)
    if missing:
        raise RuntimeError(
            f"spatial_cv internal error: missing accuracy entries for "
            f"kecamatan: {sorted(missing)}. This is a bug in spatial_cv."
        )

    return CVResult(
        kecamatan_accuracies=kecamatan_accuracies,
        n_folds=len(unique_kecamatan),
    )


# ---------------------------------------------------------------------------
# Convenience: aggregate accuracy from a CVResult
# ---------------------------------------------------------------------------

def aggregate_accuracy(cv_result: CVResult) -> float:
    """Return the mean accuracy across all kecamatan in a CVResult.

    This is a convenience summary only. It does NOT replace per-kecamatan
    entries, and callers must check cv_result.kecamatan_accuracies for the
    full picture (Requirement 9.4).

    Returns:
        float — mean of all per-kecamatan accuracy values.
        0.0 for an empty result.
    """
    values = list(cv_result.kecamatan_accuracies.values())
    if not values:
        return 0.0
    return float(sum(values) / len(values))
