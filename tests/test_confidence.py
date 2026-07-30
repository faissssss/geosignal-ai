# Feature: geosignal-ai, Property 8: Confidence Tag Correctness
"""Tests for the Confidence_Tagger (backend/geosignal/confidence.py).

Includes:
  - Property 8 (Hypothesis): if-and-only-if correctness over all float inputs.
  - Unit tests for boundary values (Task 8.3).
"""
from __future__ import annotations

import math
import sys
import os

# Ensure the backend package is importable when tests are run from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from geosignal.confidence import tag_confidence
from geosignal.models import ConfidenceThresholds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_RESULTS = {"High", "Med", "Low"}


def _thresholds_strategy():
    """Build ConfidenceThresholds with low_km strictly > high_km."""
    return st.builds(
        ConfidenceThresholds,
        high_km=st.floats(min_value=0.1, max_value=5.0, allow_nan=False, allow_infinity=False),
        low_km=st.floats(min_value=5.1, max_value=50.0, allow_nan=False, allow_infinity=False),
    ).filter(lambda t: t.low_km > t.high_km)


# ---------------------------------------------------------------------------
# Property 8 — Confidence Tag Correctness
# Validates: Requirements 7.1, 7.2, 7.5, 2.5
# ---------------------------------------------------------------------------

@given(
    ocid=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    ookla=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    thresholds=_thresholds_strategy(),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_property_8_confidence_tag_valid_result(ocid, ookla, thresholds):
    """tag_confidence always returns exactly one of High / Med / Low."""
    result = tag_confidence((0.0, 0.0), ocid, ookla, thresholds)
    assert result in VALID_RESULTS, f"Unexpected result {result!r}"


@given(
    ocid=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    ookla=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    thresholds=_thresholds_strategy(),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_property_8_high_iff_logic(ocid, ookla, thresholds):
    """result == "High"  ↔  ocid < high_km AND ookla < high_km."""
    result = tag_confidence((0.0, 0.0), ocid, ookla, thresholds)
    expected_high = (ocid < thresholds.high_km) and (ookla < thresholds.high_km)
    if expected_high:
        assert result == "High", (
            f"Expected High but got {result!r} "
            f"(ocid={ocid}, ookla={ookla}, thresholds={thresholds})"
        )
    else:
        assert result != "High", (
            f"Expected not-High but got {result!r} "
            f"(ocid={ocid}, ookla={ookla}, thresholds={thresholds})"
        )


@given(
    ocid=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    ookla=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    thresholds=_thresholds_strategy(),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_property_8_low_iff_logic(ocid, ookla, thresholds):
    """result == "Low"  ↔  (ocid > low_km AND ookla > low_km) or either absent."""
    result = tag_confidence((0.0, 0.0), ocid, ookla, thresholds)
    expected_low = (ocid > thresholds.low_km) and (ookla > thresholds.low_km)
    # Neither is inf in this strategy (allow_infinity=False), so absent = not applicable here.
    if expected_low:
        assert result == "Low", (
            f"Expected Low but got {result!r} "
            f"(ocid={ocid}, ookla={ookla}, thresholds={thresholds})"
        )
    else:
        assert result != "Low", (
            f"Expected not-Low but got {result!r} "
            f"(ocid={ocid}, ookla={ookla}, thresholds={thresholds})"
        )


@given(
    ocid=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    ookla=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    thresholds=_thresholds_strategy(),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_property_8_med_iff_logic(ocid, ookla, thresholds):
    """result == "Med"  ↔  neither High nor Low."""
    result = tag_confidence((0.0, 0.0), ocid, ookla, thresholds)
    is_high = (ocid < thresholds.high_km) and (ookla < thresholds.high_km)
    is_low = (ocid > thresholds.low_km) and (ookla > thresholds.low_km)
    expected_med = not is_high and not is_low
    if expected_med:
        assert result == "Med", (
            f"Expected Med but got {result!r} "
            f"(ocid={ocid}, ookla={ookla}, thresholds={thresholds})"
        )
    else:
        assert result != "Med", (
            f"Expected not-Med but got {result!r} "
            f"(ocid={ocid}, ookla={ookla}, thresholds={thresholds})"
        )


@given(
    ocid=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    thresholds=_thresholds_strategy(),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_property_8_ookla_absent_always_low(ocid, thresholds):
    """nearest_ookla_km=float('inf') always returns 'Low' (absent record)."""
    result = tag_confidence((0.0, 0.0), ocid, float("inf"), thresholds)
    assert result == "Low", (
        f"Expected Low for absent ookla but got {result!r} "
        f"(ocid={ocid}, thresholds={thresholds})"
    )


@given(
    ookla=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    thresholds=_thresholds_strategy(),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_property_8_ocid_absent_always_low(ookla, thresholds):
    """nearest_opencellid_km=float('inf') always returns 'Low' (absent record)."""
    result = tag_confidence((0.0, 0.0), float("inf"), ookla, thresholds)
    assert result == "Low", (
        f"Expected Low for absent ocid but got {result!r} "
        f"(ookla={ookla}, thresholds={thresholds})"
    )


@given(
    thresholds=_thresholds_strategy(),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_property_8_none_absent_always_low(thresholds):
    """None for either distance is treated same as absent → always Low."""
    assert tag_confidence((0.0, 0.0), None, 0.1, thresholds) == "Low"
    assert tag_confidence((0.0, 0.0), 0.1, None, thresholds) == "Low"
    assert tag_confidence((0.0, 0.0), None, None, thresholds) == "Low"


# ---------------------------------------------------------------------------
# Unit tests — Task 8.3: Boundary values
# ---------------------------------------------------------------------------

# Default thresholds: high_km=2.0, low_km=10.0
_DEFAULT = ConfidenceThresholds()


def test_unit_both_exactly_high_km_is_med():
    """Both distances exactly 2.0 km (= high_km) → Med (boundary is strict <)."""
    assert tag_confidence((0.0, 0.0), 2.0, 2.0, _DEFAULT) == "Med"


def test_unit_both_exactly_low_km_is_med():
    """Both distances exactly 10.0 km (= low_km) → Med (boundary is strict >)."""
    assert tag_confidence((0.0, 0.0), 10.0, 10.0, _DEFAULT) == "Med"


def test_unit_both_within_high_km_is_high():
    """Both distances 1.9 km (< high_km) → High."""
    assert tag_confidence((0.0, 0.0), 1.9, 1.9, _DEFAULT) == "High"


def test_unit_both_beyond_low_km_is_low():
    """Both distances 10.1 km (> low_km) → Low."""
    assert tag_confidence((0.0, 0.0), 10.1, 10.1, _DEFAULT) == "Low"


def test_unit_one_within_high_other_absent_is_low():
    """One within high_km, other absent (inf) → Low (absence dominates)."""
    assert tag_confidence((0.0, 0.0), 1.9, float("inf"), _DEFAULT) == "Low"


def test_unit_both_absent_is_low():
    """Both distances absent (inf) → Low."""
    assert tag_confidence((0.0, 0.0), float("inf"), float("inf"), _DEFAULT) == "Low"


def test_unit_one_within_high_other_between_high_and_low_is_med():
    """One within high_km (1.9), other between high_km and low_km (5.0) → Med."""
    assert tag_confidence((0.0, 0.0), 1.9, 5.0, _DEFAULT) == "Med"


def test_unit_custom_thresholds_high():
    """Custom thresholds high_km=1.0, low_km=5.0 — both 0.9 km → High."""
    t = ConfidenceThresholds(high_km=1.0, low_km=5.0)
    assert tag_confidence((0.0, 0.0), 0.9, 0.9, t) == "High"


def test_unit_custom_thresholds_boundary_at_high():
    """Custom thresholds: both exactly at high_km=1.0 → Med (strict <)."""
    t = ConfidenceThresholds(high_km=1.0, low_km=5.0)
    assert tag_confidence((0.0, 0.0), 1.0, 1.0, t) == "Med"


def test_unit_custom_thresholds_boundary_at_low():
    """Custom thresholds: both exactly at low_km=5.0 → Med (strict >)."""
    t = ConfidenceThresholds(high_km=1.0, low_km=5.0)
    assert tag_confidence((0.0, 0.0), 5.0, 5.0, t) == "Med"


def test_unit_custom_thresholds_beyond_low():
    """Custom thresholds: both 5.1 km > low_km=5.0 → Low."""
    t = ConfidenceThresholds(high_km=1.0, low_km=5.0)
    assert tag_confidence((0.0, 0.0), 5.1, 5.1, t) == "Low"


def test_unit_none_treated_as_absent():
    """None distances always produce Low regardless of thresholds."""
    assert tag_confidence((0.0, 0.0), None, 1.0, _DEFAULT) == "Low"
    assert tag_confidence((0.0, 0.0), 1.0, None, _DEFAULT) == "Low"
    assert tag_confidence((0.0, 0.0), None, None, _DEFAULT) == "Low"
