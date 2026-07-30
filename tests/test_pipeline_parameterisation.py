# Feature: geosignal-ai, Property 22: Pipeline Region Parameterisation
"""Property 22 — Pipeline Region Parameterisation (sub-task 4.5).

Validates: Requirements 13.1

Uses Hypothesis to assert that run_pipeline:
- Completes without error for any valid GeoJSON region boundary.
- Returns a DataQualityReport whose chosen_resolution_m equals
  resolution_variants[0].
- Handles varying Feature ids and region_id properties without code
  modification — demonstrating province-parameterised behaviour.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from hypothesis import HealthCheck, given, settings, strategies as st

from geosignal.models import DataQualityReport
from geosignal.pipeline import run_pipeline

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_VALID_RESOLUTIONS = [50, 100, 150, 200, 250, 300, 500, 1000]

_SAFE_TEXT = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(
        whitelist_categories=("Ll", "Lu", "Nd"),
        whitelist_characters="_-",
    ),
)


@st.composite
def geojson_polygon_feature(draw: st.DrawFn) -> dict:
    """Draw a GeoJSON Feature with a simple rectangular polygon boundary.

    Varies: top-level id, properties.region_id, bounding box location.
    """
    feature_id = draw(_SAFE_TEXT)
    region_name = draw(_SAFE_TEXT)

    # Draw a small bounding box anywhere within Indonesian lon/lat bounds
    min_lon = draw(st.floats(min_value=95.0, max_value=139.0,
                             allow_nan=False, allow_infinity=False))
    min_lat = draw(st.floats(min_value=-11.0, max_value=5.5,
                             allow_nan=False, allow_infinity=False))
    max_lon = min_lon + draw(st.floats(min_value=0.1, max_value=2.0,
                                       allow_nan=False, allow_infinity=False))
    max_lat = min_lat + draw(st.floats(min_value=0.1, max_value=2.0,
                                       allow_nan=False, allow_infinity=False))

    feature_type = draw(st.sampled_from(["Feature", "FeatureCollection", "unknown"]))

    if feature_type == "FeatureCollection":
        return {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "id": feature_id,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [min_lon, min_lat],
                        [max_lon, min_lat],
                        [max_lon, max_lat],
                        [min_lon, max_lat],
                        [min_lon, min_lat],
                    ]],
                },
                "properties": {"region_id": region_name},
            }],
        }
    elif feature_type == "Feature":
        return {
            "type": "Feature",
            "id": feature_id,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [min_lon, min_lat],
                    [max_lon, min_lat],
                    [max_lon, max_lat],
                    [min_lon, max_lat],
                    [min_lon, min_lat],
                ]],
            },
            "properties": {"region_id": region_name},
        }
    else:
        # Unknown type — pipeline should still return a report (uses "unknown" region_id)
        return {
            "type": "unknown",
            "id": feature_id,
            "properties": {"region_id": region_name},
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


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

@given(
    region_boundary=geojson_polygon_feature(),
    resolution_variants=resolution_variants_strategy(),
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_pipeline_region_parameterisation(
    region_boundary: dict,
    resolution_variants: list[int],
) -> None:
    """Property 22: Pipeline Region Parameterisation.

    run_pipeline completes without error for any region boundary and returns
    a DataQualityReport with chosen_resolution_m == resolution_variants[0].
    """
    report = run_pipeline(
        region_boundary=region_boundary,
        resolution_variants=resolution_variants,
        output_bucket="gs://test-bucket/output",
        config={},
    )

    # ── Must return a DataQualityReport without raising ───────────────────
    assert isinstance(report, DataQualityReport), (
        f"run_pipeline must return a DataQualityReport for any region boundary; "
        f"got {type(report)}"
    )

    # ── chosen_resolution_m == resolution_variants[0] ─────────────────────
    assert report.chosen_resolution_m == resolution_variants[0], (
        f"chosen_resolution_m {report.chosen_resolution_m} != "
        f"resolution_variants[0] {resolution_variants[0]}"
    )

    # ── region_id is a string (not None) ─────────────────────────────────
    assert isinstance(report.region_id, str), (
        f"report.region_id must be a str; got {type(report.region_id)}"
    )
