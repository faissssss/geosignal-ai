# Feature: geosignal-ai, Property 6: DataQualityReport Completeness
"""Property 6 — DataQualityReport Completeness (sub-task 4.4).

Validates: Requirements 1.5, 7.1

Uses Hypothesis to assert that run_pipeline:
- Returns a DataQualityReport with ALL required fields non-null.
- chosen_resolution_m equals resolution_variants[0].
- confidence_thresholds is a ConfidenceThresholds with high_km=2.0, low_km=10.0.
- dataset_checksums is a non-null dict (may be empty when no source_arrays given,
  or non-empty when source_arrays provided).
- timestamp is not None.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import numpy as np
from datetime import datetime
from hypothesis import HealthCheck, given, settings, strategies as st

from geosignal.models import ConfidenceThresholds, DataQualityReport
from geosignal.pipeline import run_pipeline

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_VALID_RESOLUTIONS = [50, 100, 150, 200, 250, 300, 500, 1000]


@st.composite
def region_boundary_strategy(draw: st.DrawFn) -> dict:
    """Draw a simple GeoJSON Feature with a polygon boundary."""
    region_id = draw(st.text(min_size=1, max_size=20, alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd"),
        whitelist_characters="_-",
    )))
    # Simple bounding box polygon around Jakarta area
    lon_offset = draw(st.floats(min_value=100.0, max_value=140.0, allow_nan=False))
    lat_offset = draw(st.floats(min_value=-10.0, max_value=5.0, allow_nan=False))
    return {
        "type": "Feature",
        "id": region_id,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [lon_offset, lat_offset],
                [lon_offset + 1.0, lat_offset],
                [lon_offset + 1.0, lat_offset + 1.0],
                [lon_offset, lat_offset + 1.0],
                [lon_offset, lat_offset],
            ]],
        },
        "properties": {"region_id": region_id},
    }


@st.composite
def resolution_variants_strategy(draw: st.DrawFn) -> list[int]:
    """Draw a list of ≥ 2 distinct resolutions."""
    length = draw(st.integers(min_value=2, max_value=4))
    chosen = draw(st.lists(
        st.sampled_from(_VALID_RESOLUTIONS),
        min_size=length,
        max_size=length,
        unique=True,
    ))
    return sorted(chosen)


@st.composite
def valid_geojson_features(draw: st.DrawFn) -> list[dict]:
    """Draw a small list of valid GeoJSON point features with in-range attributes."""
    n = draw(st.integers(min_value=0, max_value=5))
    features = []
    for i in range(n):
        features.append({
            "type": "Feature",
            "id": f"f_{i}",
            "geometry": {
                "type": "Point",
                "coordinates": [
                    draw(st.floats(min_value=100.0, max_value=141.0, allow_nan=False)),
                    draw(st.floats(min_value=-11.0, max_value=6.0, allow_nan=False)),
                ],
            },
            "properties": {
                "elevation_m": draw(st.floats(min_value=-11.0, max_value=4884.0,
                                              allow_nan=False, allow_infinity=False)),
            },
        })
    return features


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

@given(
    region_boundary=region_boundary_strategy(),
    resolution_variants=resolution_variants_strategy(),
    source_features=valid_geojson_features(),
)
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_data_quality_report_completeness(
    region_boundary: dict,
    resolution_variants: list[int],
    source_features: list[dict],
) -> None:
    """Property 6: DataQualityReport Completeness.

    All required DataQualityReport fields are non-null on a successful run.
    """
    config = {"source_features": source_features}

    report = run_pipeline(
        region_boundary=region_boundary,
        resolution_variants=resolution_variants,
        output_bucket="gs://test-bucket/output",
        config=config,
    )

    # Must return a DataQualityReport
    assert isinstance(report, DataQualityReport), (
        f"run_pipeline must return a DataQualityReport; got {type(report)}"
    )

    # ── region_id is not None ─────────────────────────────────────────────
    assert report.region_id is not None, "report.region_id must not be None"

    # ── input_record_counts is not None and is a dict ────────────────────
    assert report.input_record_counts is not None
    assert isinstance(report.input_record_counts, dict), (
        f"input_record_counts must be a dict; got {type(report.input_record_counts)}"
    )

    # ── removed_records is not None and is a dict ────────────────────────
    assert report.removed_records is not None
    assert isinstance(report.removed_records, dict)

    # ── repaired_records is not None and is a dict ───────────────────────
    assert report.repaired_records is not None
    assert isinstance(report.repaired_records, dict)

    # ── anomalous_records is not None and is a dict ──────────────────────
    assert report.anomalous_records is not None
    assert isinstance(report.anomalous_records, dict)

    # ── chosen_resolution_m equals resolution_variants[0] ────────────────
    assert report.chosen_resolution_m == resolution_variants[0], (
        f"chosen_resolution_m {report.chosen_resolution_m} != "
        f"resolution_variants[0] {resolution_variants[0]}"
    )

    # ── confidence_thresholds is ConfidenceThresholds with correct defaults
    assert isinstance(report.confidence_thresholds, ConfidenceThresholds), (
        f"confidence_thresholds must be a ConfidenceThresholds instance; "
        f"got {type(report.confidence_thresholds)}"
    )
    assert report.confidence_thresholds.high_km == 2.0, (
        f"high_km must be 2.0; got {report.confidence_thresholds.high_km}"
    )
    assert report.confidence_thresholds.low_km == 10.0, (
        f"low_km must be 10.0; got {report.confidence_thresholds.low_km}"
    )

    # ── dataset_checksums is not None and is a dict ───────────────────────
    assert report.dataset_checksums is not None
    assert isinstance(report.dataset_checksums, dict), (
        f"dataset_checksums must be a dict; got {type(report.dataset_checksums)}"
    )

    # ── timestamp is not None ────────────────────────────────────────────
    assert report.timestamp is not None, "report.timestamp must not be None"
    assert isinstance(report.timestamp, datetime), (
        f"report.timestamp must be a datetime; got {type(report.timestamp)}"
    )


# ---------------------------------------------------------------------------
# Additional: checksums populated when source_arrays provided
# ---------------------------------------------------------------------------

def test_dataset_checksums_populated_with_source_arrays() -> None:
    """When source_arrays are provided, dataset_checksums must be non-empty."""
    source_arrays = {
        "elevation_m": np.random.uniform(0, 1000, (5, 5)).astype(np.float32),
        "land_cover_class": np.random.randint(0, 20, (5, 5)).astype(np.int32),
    }
    report = run_pipeline(
        region_boundary={"type": "Feature", "id": "test", "geometry": None, "properties": {}},
        resolution_variants=[100, 250],
        output_bucket="gs://test",
        config={
            "source_arrays": source_arrays,
            "native_extent": (106.0, -6.5, 107.0, -5.5),
        },
    )
    assert len(report.dataset_checksums) == 2
    for field_name, checksum in report.dataset_checksums.items():
        assert len(checksum) == 64, (
            f"SHA-256 hex digest for '{field_name}' should be 64 chars; got {len(checksum)}"
        )
