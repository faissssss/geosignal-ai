"""Unit tests for GeoSignal AI data models (sub-task 2.3).

Tests:
1. FeatureVector has no Ookla field.
2. CONSOLIDATED_FEATURES has exactly 8 entries.
3. ConfidenceThresholds defaults: high_km == 2.0, low_km == 10.0.
4. FeatureVector has distinct land_cover_class and canopy_height_m fields.
5. No administrative-boundary identifier field in CONSOLIDATED_FEATURES.
"""
import dataclasses

import pytest

from geosignal.models import (
    CONSOLIDATED_FEATURES,
    ConfidenceThresholds,
    FeatureVector,
)

# ── helpers ───────────────────────────────────────────────────────────────────

_FV_FIELD_NAMES: list[str] = [f.name for f in dataclasses.fields(FeatureVector)]

# Administrative-boundary identifiers that must NOT appear in CONSOLIDATED_FEATURES.
_ADMIN_BOUNDARY_TERMS = {
    "kecamatan",
    "kabupaten",
    "village",
    "regency",
    "boundary",
    "admin",
}


# ── Test 1: FeatureVector has no Ookla field ──────────────────────────────────

def test_feature_vector_has_no_ookla_field():
    """FeatureVector must not contain any field whose name includes 'ookla'."""
    ookla_fields = [
        name for name in _FV_FIELD_NAMES if "ookla" in name.lower()
    ]
    assert ookla_fields == [], (
        f"FeatureVector must not have Ookla fields, but found: {ookla_fields}"
    )


# ── Test 2: CONSOLIDATED_FEATURES has exactly 8 entries ──────────────────────

def test_consolidated_features_has_exactly_eight_entries():
    """CONSOLIDATED_FEATURES must contain exactly 8 feature names."""
    assert len(CONSOLIDATED_FEATURES) == 8, (
        f"Expected 8 features, got {len(CONSOLIDATED_FEATURES)}: {CONSOLIDATED_FEATURES}"
    )


# ── Test 3: ConfidenceThresholds defaults ─────────────────────────────────────

def test_confidence_thresholds_defaults():
    """ConfidenceThresholds() must default to high_km=2.0 and low_km=10.0."""
    thresholds = ConfidenceThresholds()
    assert thresholds.high_km == 2.0, (
        f"Expected high_km=2.0, got {thresholds.high_km}"
    )
    assert thresholds.low_km == 10.0, (
        f"Expected low_km=10.0, got {thresholds.low_km}"
    )


# ── Test 4: FeatureVector has distinct land_cover_class and canopy_height_m ───

def test_feature_vector_has_distinct_land_cover_and_canopy_fields():
    """FeatureVector must have both land_cover_class and canopy_height_m as
    separate, independent fields — neither aliases the other."""
    assert "land_cover_class" in _FV_FIELD_NAMES, (
        "FeatureVector is missing the 'land_cover_class' field."
    )
    assert "canopy_height_m" in _FV_FIELD_NAMES, (
        "FeatureVector is missing the 'canopy_height_m' field."
    )
    # Verify they map to distinct positions in the dataclass fields tuple.
    field_map = {f.name: f for f in dataclasses.fields(FeatureVector)}
    lc_field = field_map["land_cover_class"]
    ch_field = field_map["canopy_height_m"]
    assert lc_field is not ch_field, (
        "land_cover_class and canopy_height_m must be distinct fields, not the same object."
    )
    # Verify they have different types (int vs float), confirming they are not aliases.
    assert lc_field.type != ch_field.type, (
        "land_cover_class (int) and canopy_height_m (float) must have different types."
    )


# ── Test 5: No admin boundary identifier in CONSOLIDATED_FEATURES ────────────

def test_consolidated_features_has_no_admin_boundary_identifier():
    """None of the entries in CONSOLIDATED_FEATURES may contain an
    administrative-boundary term (kecamatan, kabupaten, village, regency,
    boundary, admin) — case-insensitive check."""
    violations = [
        feat
        for feat in CONSOLIDATED_FEATURES
        if any(term in feat.lower() for term in _ADMIN_BOUNDARY_TERMS)
    ]
    assert violations == [], (
        f"CONSOLIDATED_FEATURES contains administrative-boundary identifiers: {violations}. "
        "Admin boundaries are a display/label layer only and must not be scoring inputs "
        "(Requirement 2.7)."
    )
