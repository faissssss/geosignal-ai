# Feature: geosignal-ai, Property 4: Attribute Range Validation
"""Property 4 — Attribute Range Validation (sub-task 3.5).

Validates: Requirements 1.3

Uses Hypothesis to assert that run_attribute_validation:
1. The flagged set equals the out-of-range set — every feature with at least
   one out-of-range known attribute ends up in flagged_features, and no
   in-range feature is flagged.
2. valid_features and flagged_features are disjoint (no feature appears in
   both).
"""
from __future__ import annotations

import sys
import os

# Ensure the backend package is importable when running from the project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from hypothesis import HealthCheck, given, settings, strategies as st

from geosignal.pipeline import DEFAULT_ATTRIBUTE_BOUNDS, run_attribute_validation

# ---------------------------------------------------------------------------
# Bounds reference (mirrors DEFAULT_ATTRIBUTE_BOUNDS exactly)
# ---------------------------------------------------------------------------

_ELEV_MIN = DEFAULT_ATTRIBUTE_BOUNDS["elevation_m"]["min"]          # -11.0
_ELEV_MAX = DEFAULT_ATTRIBUTE_BOUNDS["elevation_m"]["max"]          # 4884.0
_POP_MAX  = DEFAULT_ATTRIBUTE_BOUNDS["population_density_per_km2"]["max"]  # 1_000_000
_CAN_MIN  = DEFAULT_ATTRIBUTE_BOUNDS["canopy_height_m"]["min"]      # 0.0
_CAN_MAX  = DEFAULT_ATTRIBUTE_BOUNDS["canopy_height_m"]["max"]      # 100.0

# Fields whose bounds we test
_VALIDATED_FIELDS = list(DEFAULT_ATTRIBUTE_BOUNDS.keys())


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

def _is_out_of_range(field: str, value: float) -> bool:
    """Return True if *value* falls outside the default bounds for *field*."""
    b = DEFAULT_ATTRIBUTE_BOUNDS[field]
    low = b.get("min")
    high = b.get("max")
    if low is not None and value < low:
        return True
    if high is not None and value > high:
        return True
    return False


@st.composite
def feature_record_list(draw: st.DrawFn) -> tuple[list[dict], set[str]]:
    """Draw a list of feature records with mixed in-range and out-of-range values.

    Returns
    -------
    (features, expected_flagged_ids)
        ``expected_flagged_ids`` is the set of feature IDs that should appear
        in ``flagged_features`` because they have at least one out-of-range
        known attribute.
    """
    n_features = draw(st.integers(min_value=1, max_value=20))

    features: list[dict] = []
    expected_flagged_ids: set[str] = set()

    for i in range(n_features):
        fid = f"feat_{i}"
        props: dict[str, float] = {}
        has_violation = False

        # Randomly include a subset of the three validated fields
        include_elev = draw(st.booleans())
        include_pop  = draw(st.booleans())
        include_can  = draw(st.booleans())

        # Ensure at least one field is included per feature so the feature is
        # not trivially valid (no properties to check → always valid, which is
        # correct but makes the test trivial).
        if not (include_elev or include_pop or include_can):
            include_elev = True

        if include_elev:
            # Draw a value that may or may not be in range
            value = draw(
                st.one_of(
                    # In-range
                    st.floats(min_value=_ELEV_MIN, max_value=_ELEV_MAX,
                              allow_nan=False, allow_infinity=False),
                    # Out-of-range: below min
                    st.floats(min_value=-10_000.0, max_value=_ELEV_MIN - 0.001,
                              allow_nan=False, allow_infinity=False),
                    # Out-of-range: above max
                    st.floats(min_value=_ELEV_MAX + 0.001, max_value=10_000.0,
                              allow_nan=False, allow_infinity=False),
                )
            )
            props["elevation_m"] = value
            if _is_out_of_range("elevation_m", value):
                has_violation = True

        if include_pop:
            value = draw(
                st.one_of(
                    # In-range (0 to max inclusive)
                    st.floats(min_value=0.0, max_value=_POP_MAX,
                              allow_nan=False, allow_infinity=False),
                    # Out-of-range: above max
                    st.floats(min_value=_POP_MAX + 0.001, max_value=2_000_000.0,
                              allow_nan=False, allow_infinity=False),
                )
            )
            props["population_density_per_km2"] = value
            if _is_out_of_range("population_density_per_km2", value):
                has_violation = True

        if include_can:
            value = draw(
                st.one_of(
                    # In-range
                    st.floats(min_value=_CAN_MIN, max_value=_CAN_MAX,
                              allow_nan=False, allow_infinity=False),
                    # Out-of-range: below 0
                    st.floats(min_value=-200.0, max_value=_CAN_MIN - 0.001,
                              allow_nan=False, allow_infinity=False),
                    # Out-of-range: above 100
                    st.floats(min_value=_CAN_MAX + 0.001, max_value=500.0,
                              allow_nan=False, allow_infinity=False),
                )
            )
            props["canopy_height_m"] = value
            if _is_out_of_range("canopy_height_m", value):
                has_violation = True

        features.append({
            "type": "Feature",
            "id": fid,
            "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
            "properties": props,
        })

        if has_violation:
            expected_flagged_ids.add(fid)

    return features, expected_flagged_ids


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

@given(feature_record_list())
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_attribute_range_validation(
    data: tuple[list[dict], set[str]],
) -> None:
    """Property 4: Attribute Range Validation.

    1. The flagged set equals the expected out-of-range set.
    2. valid_features and flagged_features are disjoint.
    """
    features, expected_flagged_ids = data

    valid_features, flagged_features, validation_log = run_attribute_validation(features)

    # ── Extract IDs from returned lists ─────────────────────────────────
    def _get_id(feat: dict) -> str:
        if "id" in feat:
            return str(feat["id"])
        return str((feat.get("properties") or {}).get("id", "unknown"))

    actual_flagged_ids = {_get_id(f) for f in flagged_features}
    actual_valid_ids   = {_get_id(f) for f in valid_features}

    # ── Assert 1: flagged set equals out-of-range set ───────────────────
    assert actual_flagged_ids == expected_flagged_ids, (
        f"Flagged IDs mismatch.\n"
        f"  Expected flagged : {sorted(expected_flagged_ids)}\n"
        f"  Actual flagged   : {sorted(actual_flagged_ids)}\n"
        f"  Diff (missing)   : {sorted(expected_flagged_ids - actual_flagged_ids)}\n"
        f"  Diff (extra)     : {sorted(actual_flagged_ids - expected_flagged_ids)}"
    )

    # ── Assert 2: valid and flagged sets are disjoint ───────────────────
    overlap = actual_valid_ids & actual_flagged_ids
    assert not overlap, (
        f"valid_features and flagged_features must be disjoint, "
        f"but these IDs appear in both: {sorted(overlap)}"
    )

    # ── Sanity: every input feature appears in exactly one output list ──
    all_output_ids = actual_valid_ids | actual_flagged_ids
    all_input_ids  = {_get_id(f) for f in features}
    assert all_output_ids == all_input_ids, (
        f"Some features are missing from both output lists: "
        f"{sorted(all_input_ids - all_output_ids)}"
    )
