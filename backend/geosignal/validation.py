"""Spatially blocked cross-validation for GeoSignal AI.

Tier 2 models are validated by holding out complete kecamatan groups.
Random point-level splitting is intentionally prohibited because nearby
grid cells are spatially correlated and could cause data leakage.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score
from sklearn.model_selection import GroupKFold

from geosignal.models import CONSOLIDATED_FEATURES, CVResult


AccuracyFunction = Callable[[np.ndarray, np.ndarray], float]


def spatial_cv(
    data: pd.DataFrame,
    kecamatan_column: str,
    model_cls: type,
    n_folds: int,
    *,
    target_column: str = "observed_mobile_performance",
    feature_columns: Sequence[str] | None = None,
    model_kwargs: dict[str, Any] | None = None,
    accuracy_fn: AccuracyFunction | None = None,
) -> CVResult:
    """Run spatial cross-validation using complete kecamatan test blocks.

    The first four parameters preserve the public interface defined in the
    GeoSignal AI design document. Additional configuration is keyword-only.

    Parameters
    ----------
    data:
        DataFrame or GeoDataFrame containing model features, the Tier 2
        training target, and a kecamatan identifier.

    kecamatan_column:
        Name of the column containing kecamatan identifiers.

    model_cls:
        Trainable model class implementing ``fit`` and ``predict``.

    n_folds:
        Number of spatial folds. Must be between 2 and the number of unique
        kecamatan identifiers, inclusive.

    target_column:
        Tier 2 ground-truth target. The target is never included in the
        Consolidated Feature Set.

    feature_columns:
        Input feature columns. Defaults to the canonical eight
        ``CONSOLIDATED_FEATURES``.

    model_kwargs:
        Optional arguments passed to ``model_cls`` during each fold.

    accuracy_fn:
        Per-kecamatan metric function accepting ``y_true`` and ``y_pred``.
        Defaults to finite R-squared.

    Returns
    -------
    CVResult
        One finite accuracy value for every kecamatan and the executed
        number of folds.
    """
    if not isinstance(data, pd.DataFrame):
        raise TypeError("data must be a pandas DataFrame or GeoDataFrame")

    if data.empty:
        raise ValueError("data cannot be empty")

    if not isinstance(kecamatan_column, str) or not kecamatan_column.strip():
        raise ValueError("kecamatan_column cannot be empty")

    if not isinstance(target_column, str) or not target_column.strip():
        raise ValueError("target_column cannot be empty")

    selected_features = (
        list(CONSOLIDATED_FEATURES)
        if feature_columns is None
        else list(feature_columns)
    )

    if not selected_features:
        raise ValueError("feature_columns cannot be empty")

    if len(selected_features) != len(set(selected_features)):
        raise ValueError("feature_columns cannot contain duplicates")

    if target_column in selected_features:
        raise ValueError(
            "target_column cannot also be an input feature"
        )

    required_columns = {
        kecamatan_column,
        target_column,
        *selected_features,
    }
    missing_columns = sorted(
        required_columns.difference(data.columns)
    )

    if missing_columns:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing_columns)
        )

    kecamatan_ids = _normalise_kecamatan_ids(
        data[kecamatan_column].to_numpy()
    )

    features = _to_finite_numeric_matrix(
        data[selected_features],
        name="feature data",
    )
    targets = _to_finite_numeric_vector(
        data[target_column],
        name="target data",
    )

    if len(features) != len(kecamatan_ids):
        raise ValueError(
            "Feature rows must align with kecamatan identifiers"
        )

    unique_kecamatan, counts = np.unique(
        kecamatan_ids,
        return_counts=True,
    )

    if len(unique_kecamatan) < 2:
        raise ValueError(
            "At least two unique kecamatan are required"
        )

    sparse_kecamatan = unique_kecamatan[counts < 2]

    if len(sparse_kecamatan) > 0:
        names = ", ".join(
            str(value) for value in sparse_kecamatan
        )
        raise ValueError(
            "Each kecamatan requires at least two observations "
            f"for per-kecamatan accuracy: {names}"
        )

    folds = _build_spatial_folds(
        kecamatan_ids=kecamatan_ids,
        n_folds=n_folds,
    )

    metric = (
        _default_accuracy
        if accuracy_fn is None
        else accuracy_fn
    )
    constructor_kwargs = dict(model_kwargs or {})

    kecamatan_accuracies: dict[str, float] = {}

    for train_indices, test_indices in folds:
        model = model_cls(**constructor_kwargs)

        if not callable(getattr(model, "fit", None)):
            raise TypeError(
                "model_cls instances must implement fit(X, y)"
            )

        if not callable(getattr(model, "predict", None)):
            raise TypeError(
                "model_cls instances must implement predict(X)"
            )

        fitted_model = model.fit(
            features[train_indices],
            targets[train_indices],
        )

        predictor = (
            fitted_model
            if callable(getattr(fitted_model, "predict", None))
            else model
        )

        predictions = np.asarray(
            predictor.predict(features[test_indices]),
            dtype=np.float64,
        ).reshape(-1)

        if len(predictions) != len(test_indices):
            raise ValueError(
                "Model prediction count does not match test rows"
            )

        if not np.isfinite(predictions).all():
            raise ValueError(
                "Model predictions must contain only finite values"
            )

        fold_groups = kecamatan_ids[test_indices]
        fold_targets = targets[test_indices]

        for kecamatan_id in np.unique(fold_groups):
            group_mask = fold_groups == kecamatan_id

            accuracy = float(
                metric(
                    fold_targets[group_mask],
                    predictions[group_mask],
                )
            )

            if not np.isfinite(accuracy):
                raise ValueError(
                    "Per-kecamatan accuracy must be finite for "
                    f"{kecamatan_id}"
                )

            key = str(kecamatan_id)

            if key in kecamatan_accuracies:
                raise RuntimeError(
                    "A kecamatan appeared in more than one test fold: "
                    f"{key}"
                )

            kecamatan_accuracies[key] = accuracy

    expected_keys = {
        str(value) for value in unique_kecamatan
    }

    if set(kecamatan_accuracies) != expected_keys:
        missing = sorted(
            expected_keys.difference(kecamatan_accuracies)
        )
        raise RuntimeError(
            "Cross-validation did not report every kecamatan: "
            + ", ".join(missing)
        )

    return CVResult(
        kecamatan_accuracies=dict(
            sorted(kecamatan_accuracies.items())
        ),
        n_folds=n_folds,
    )


def _build_spatial_folds(
    kecamatan_ids: Sequence[object],
    n_folds: int,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Construct the actual group-blocked folds used by ``spatial_cv``.

    Every kecamatan is assigned to exactly one test fold. No kecamatan may
    occur in both train and test within the same fold.
    """
    groups = _normalise_kecamatan_ids(kecamatan_ids)
    unique_groups = np.unique(groups)
    unique_count = len(unique_groups)

    if not isinstance(n_folds, int) or isinstance(n_folds, bool):
        raise TypeError("n_folds must be an integer")

    if n_folds < 2:
        raise ValueError("n_folds must be at least 2")

    if unique_count < 2:
        raise ValueError(
            "At least two unique kecamatan are required"
        )

    if n_folds > unique_count:
        raise ValueError(
            "n_folds cannot exceed the number of unique kecamatan"
        )

    splitter = GroupKFold(n_splits=n_folds)
    placeholder_features = np.zeros(
        (len(groups), 1),
        dtype=np.float64,
    )

    folds: list[tuple[np.ndarray, np.ndarray]] = []
    test_group_occurrences: dict[str, int] = {
        str(group): 0
        for group in unique_groups
    }

    for train_indices, test_indices in splitter.split(
        placeholder_features,
        groups=groups,
    ):
        train_indices = np.asarray(
            train_indices,
            dtype=np.int64,
        )
        test_indices = np.asarray(
            test_indices,
            dtype=np.int64,
        )

        train_groups = {
            str(value)
            for value in groups[train_indices]
        }
        test_groups = {
            str(value)
            for value in groups[test_indices]
        }

        if not train_groups.isdisjoint(test_groups):
            raise RuntimeError(
                "Spatial fold contains overlapping train and test "
                "kecamatan identifiers"
            )

        for group in test_groups:
            test_group_occurrences[group] += 1

        folds.append((train_indices, test_indices))

    invalid_occurrences = {
        group: occurrence_count
        for group, occurrence_count
        in test_group_occurrences.items()
        if occurrence_count != 1
    }

    if invalid_occurrences:
        raise RuntimeError(
            "Every kecamatan must appear in exactly one test fold"
        )

    return folds


def _normalise_kecamatan_ids(
    kecamatan_ids: Sequence[object],
) -> np.ndarray:
    """Return non-null, non-empty kecamatan identifiers as strings."""
    raw = np.asarray(
        list(kecamatan_ids),
        dtype=object,
    )

    if raw.ndim != 1:
        raise ValueError(
            "kecamatan identifiers must be one-dimensional"
        )

    if len(raw) == 0:
        raise ValueError(
            "kecamatan identifiers cannot be empty"
        )

    if pd.isna(raw).any():
        raise ValueError(
            "kecamatan identifiers cannot contain null values"
        )

    normalised = np.asarray(
        [
            str(value).strip()
            for value in raw
        ],
        dtype=object,
    )

    if any(not value for value in normalised):
        raise ValueError(
            "kecamatan identifiers cannot contain empty values"
        )

    return normalised


def _to_finite_numeric_matrix(
    values: pd.DataFrame,
    *,
    name: str,
) -> np.ndarray:
    """Convert feature columns to a finite two-dimensional float matrix."""
    try:
        array = values.to_numpy(
            dtype=np.float64,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{name} must contain only numeric values"
        ) from exc

    if array.ndim != 2:
        raise ValueError(
            f"{name} must be two-dimensional"
        )

    if not np.isfinite(array).all():
        raise ValueError(
            f"{name} must contain only finite values"
        )

    return array


def _to_finite_numeric_vector(
    values: pd.Series,
    *,
    name: str,
) -> np.ndarray:
    """Convert the target column to a finite one-dimensional float vector."""
    try:
        array = values.to_numpy(
            dtype=np.float64,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{name} must contain only numeric values"
        ) from exc

    if array.ndim != 1:
        raise ValueError(
            f"{name} must be one-dimensional"
        )

    if not np.isfinite(array).all():
        raise ValueError(
            f"{name} must contain only finite values"
        )

    return array


def _default_accuracy(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> float:
    """Return finite R-squared for one held-out kecamatan."""
    return float(
        r2_score(
            y_true,
            y_pred,
            force_finite=True,
        )
    )