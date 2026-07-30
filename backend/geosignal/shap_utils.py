"""GeoSignal AI — SHAP explainability utilities (both tiers).

Provides:
  - compute_ahp_shap       Tier 1 SHAP attribution using AHP weights
  - compute_gbm_shap       Tier 2 SHAP values via TreeExplainer
  - format_shap_top3       Format top-3 SHAP features for display
  - batch_compute_shap     Batch SHAP over a list of FeatureVectors
  - write_shap_to_grid_cells  Batch compute + write back to grid_cells table

IMPORTANT:
  - CONSOLIDATED_FEATURES is imported from geosignal.models — never redefined here.
  - Regional baseline is always passed as a parameter — never globally cached.
  - Returns dicts with exactly 8 entries, one per CONSOLIDATED_FEATURES entry.
"""
from __future__ import annotations

import numpy as np

from geosignal.models import CONSOLIDATED_FEATURES, FeatureVector

# ── Plain-language label mapping ──────────────────────────────────────────────

_FEATURE_LABELS: dict[str, str] = {
    "elevation_m": "Elevation",
    "slope_deg": "Terrain slope",
    "land_cover_class": "Land cover type",
    "canopy_height_m": "Canopy height",
    "distance_to_bts_m": "Distance to nearest BTS tower",
    "road_distance_m": "Distance to nearest road",
    "population_density_per_km2": "Population density",
    "facility_proximity_m": "Distance to nearest facility",
}


# ── Tier 1: AHP SHAP ──────────────────────────────────────────────────────────

def compute_ahp_shap(
    feature_vector: FeatureVector,
    weights: dict[str, float],
    regional_baseline: dict[str, float],
) -> dict[str, float]:
    """Compute SHAP-style attribution for a single FeatureVector using AHP weights.

    Formula: shap[feature] = weights[feature] * (feature_value - baseline[feature])

    Returns a dict with exactly 8 entries (one per CONSOLIDATED_FEATURES entry).
    No None values. Requires regional_baseline to have a value for every feature.

    Args:
        feature_vector:    The grid cell whose SHAP values are being computed.
        weights:           Normalised AHP weight per feature (must have all 8 keys).
        regional_baseline: Mean of each feature across all scored cells in this
                           region+run (must have all 8 keys).  Passed as a parameter —
                           never globally cached.

    Returns:
        Dict mapping each feature name → float SHAP value.

    Raises:
        KeyError: if any CONSOLIDATED_FEATURES entry is missing from ``weights``
                  or ``regional_baseline``.
    """
    result: dict[str, float] = {}
    for feat in CONSOLIDATED_FEATURES:
        w = weights[feat]               # raises KeyError if missing
        b = regional_baseline[feat]     # raises KeyError if missing
        value = getattr(feature_vector, feat)
        result[feat] = w * (value - b)
    return result


# ── Tier 2: GBM SHAP ──────────────────────────────────────────────────────────

def compute_gbm_shap(
    feature_vector: FeatureVector,
    adapter,
) -> dict[str, float]:
    """Compute SHAP values for a single FeatureVector using TreeExplainer.

    Converts the FeatureVector to a (1, 8) numpy array in CONSOLIDATED_FEATURES
    order, calls ``adapter.shap_values(features_array)`` to obtain a (1, 8) or
    (N, 8) array, takes the first row, and zips with CONSOLIDATED_FEATURES.

    Returns a dict with exactly 8 entries matching CONSOLIDATED_FEATURES.

    Args:
        feature_vector: The grid cell to explain.
        adapter:        XGBoostAdapter or LightGBMAdapter with a loaded model.

    Returns:
        Dict mapping each feature name → float SHAP value.

    Raises:
        RuntimeError: propagated from the adapter when it has no model loaded.
    """
    features_array = np.array(
        [[getattr(feature_vector, feat) for feat in CONSOLIDATED_FEATURES]],
        dtype=np.float64,
    )
    sv = adapter.shap_values(features_array)   # (1, 8) or (N, 8)
    first_row = np.asarray(sv, dtype=np.float64)[0]
    return {feat: float(first_row[i]) for i, feat in enumerate(CONSOLIDATED_FEATURES)}


# ── Top-3 formatter ───────────────────────────────────────────────────────────

def format_shap_top3(shap_values: dict[str, float]) -> list[dict]:
    """Return the top-3 SHAP features sorted by absolute value descending.

    Each entry has:
      - ``feature_name``: plain-language label (non-empty string)
      - ``value``:        raw SHAP float value
      - ``direction``:    ``"positive"`` if value >= 0, else ``"negative"``

    Exactly 3 entries are returned (even if some values are 0.0).

    Args:
        shap_values: Dict mapping raw feature names → float SHAP values.
                     Must contain at least 3 keys with mappings in _FEATURE_LABELS.

    Returns:
        List of exactly 3 dicts, sorted by abs(value) descending.
    """
    # Sort all features by absolute SHAP value descending, take top 3.
    sorted_items = sorted(shap_values.items(), key=lambda kv: abs(kv[1]), reverse=True)
    top3 = sorted_items[:3]

    return [
        {
            "feature_name": _FEATURE_LABELS[feat],
            "value": value,
            "direction": "positive" if value >= 0.0 else "negative",
        }
        for feat, value in top3
    ]


# ── Batch SHAP ────────────────────────────────────────────────────────────────

def batch_compute_shap(
    feature_vectors: list[FeatureVector],
    adapter,
    regional_baseline: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
    use_ahp: bool = True,
) -> list[dict[str, float]]:
    """Compute SHAP values for a list of FeatureVectors.

    If ``use_ahp=True``: calls ``compute_ahp_shap`` for each vector
    (requires ``weights`` and ``regional_baseline``).

    If ``use_ahp=False``: calls ``compute_gbm_shap`` for each vector
    (uses the adapter's TreeExplainer).

    Args:
        feature_vectors:   List of FeatureVectors to explain.
        adapter:           ScoringAdapter (used for GBM path; ignored by AHP path).
        regional_baseline: Required when ``use_ahp=True``.
        weights:           Required when ``use_ahp=True``.
        use_ahp:           Selects the computation path.

    Returns:
        List of shap_value dicts, one per feature vector.
    """
    results: list[dict[str, float]] = []
    for fv in feature_vectors:
        if use_ahp:
            sv = compute_ahp_shap(fv, weights, regional_baseline)
        else:
            sv = compute_gbm_shap(fv, adapter)
        results.append(sv)
    return results


# ── Batch write-back ──────────────────────────────────────────────────────────

def write_shap_to_grid_cells(
    region_id: str,
    feature_vectors: list[FeatureVector],
    cell_ids: list[str],
    adapter,
    supabase_client=None,
    regional_baseline: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
    use_ahp: bool = True,
) -> list[dict]:
    """Compute SHAP top-3 for all cells and write back to the grid_cells table.

    After ``compute_coverage_score`` runs for all cells in a region, this function:
      1. Calls ``batch_compute_shap`` for every cell.
      2. Calls ``format_shap_top3`` on each result.
      3. If ``supabase_client`` is provided: upserts ``{cell_id, shap_top3}``
         to the ``grid_cells`` table.
      4. If ``supabase_client`` is None: returns the list of
         ``{cell_id, shap_top3}`` dicts for testing without a live DB.

    Args:
        region_id:         Identifier of the region being processed (used in
                           logging / upsert context).
        feature_vectors:   List of FeatureVectors, one per grid cell.
        cell_ids:          List of cell UUIDs aligned to ``feature_vectors``.
        adapter:           ScoringAdapter (passed through to batch_compute_shap).
        supabase_client:   Optional live Supabase client.  None → dry-run mode.
        regional_baseline: AHP baseline dict (required when ``use_ahp=True``).
        weights:           AHP weight dict (required when ``use_ahp=True``).
        use_ahp:           Selects AHP vs. GBM SHAP path.

    Returns:
        List of ``{"cell_id": str, "shap_top3": list[dict]}`` dicts.
    """
    shap_results = batch_compute_shap(
        feature_vectors,
        adapter,
        regional_baseline=regional_baseline,
        weights=weights,
        use_ahp=use_ahp,
    )

    rows: list[dict] = []
    for cell_id, sv in zip(cell_ids, shap_results):
        top3 = format_shap_top3(sv)
        rows.append({"cell_id": cell_id, "shap_top3": top3})

    if supabase_client is not None:
        for row in rows:
            (
                supabase_client
                .table("grid_cells")
                .upsert({"cell_id": row["cell_id"], "shap_top3": row["shap_top3"]})
                .execute()
            )

    return rows
