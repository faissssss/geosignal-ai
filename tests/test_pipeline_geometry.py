# Feature: geosignal-ai, Property 3: Geometry QC Completeness
"""Property 3 — Geometry QC Completeness (sub-task 3.3).

Validates: Requirements 1.2

Uses Hypothesis to assert that run_geometry_qc:
1. Produces zero invalid geometries in its output (no null, no empty, no
   self-intersecting).
2. Returns exactly one correction-log entry per removed or repaired feature.
"""
from __future__ import annotations

import math
import sys
import os

# Ensure the backend package is importable when running from the project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st
from shapely.geometry import mapping, Polygon

from geosignal.pipeline import run_geometry_qc

# ---------------------------------------------------------------------------
# Geometry generators
# ---------------------------------------------------------------------------

def _make_valid_polygon_feature(coords: list[tuple[float, float]], fid: str) -> dict:
    """Return a valid GeoJSON Feature dict from a list of coordinate tuples."""
    # Ensure the ring is closed
    ring = list(coords)
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return {
        "type": "Feature",
        "id": fid,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[(x, y) for x, y in ring]],
        },
        "properties": {},
    }


def _make_self_intersecting_feature(fid: str) -> dict:
    """Return a GeoJSON Feature whose polygon is self-intersecting (bowtie)."""
    # Classic bowtie: (0,0)→(2,2)→(2,0)→(0,2)→(0,0)
    return {
        "type": "Feature",
        "id": fid,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)]],
        },
        "properties": {},
    }


def _make_null_geometry_feature(fid: str) -> dict:
    """Return a GeoJSON Feature with a null geometry."""
    return {
        "type": "Feature",
        "id": fid,
        "geometry": None,
        "properties": {},
    }


def _make_empty_geometry_feature(fid: str) -> dict:
    """Return a GeoJSON Feature with an empty geometry dict."""
    return {
        "type": "Feature",
        "id": fid,
        "geometry": {},
        "properties": {},
    }


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

def _simple_triangle(offset: float) -> list[tuple[float, float]]:
    """Return a simple triangle shifted by offset to avoid degenerate polygons."""
    o = offset % 180.0  # keep within longitude bounds
    return [(o, 0.0), (o + 1.0, 0.0), (o + 0.5, 1.0)]


@st.composite
def geojson_feature_list(draw: st.DrawFn) -> tuple[list[dict], int]:
    """Draw a mixed list of valid and invalid GeoJSON Feature dicts.

    Returns
    -------
    (features, expected_invalid_count)
        ``expected_invalid_count`` is the number of features that should
        appear in the correction log (null-geometry, empty-geometry, and
        self-intersecting counts combined).
    """
    # How many valid features?
    n_valid = draw(st.integers(min_value=1, max_value=10))
    # How many of each invalid type to inject?
    n_null = draw(st.integers(min_value=0, max_value=3))
    n_empty = draw(st.integers(min_value=0, max_value=3))
    n_bad = draw(st.integers(min_value=0, max_value=3))

    features: list[dict] = []
    idx = 0

    for i in range(n_valid):
        coords = _simple_triangle(float(i * 2))
        features.append(_make_valid_polygon_feature(coords, fid=f"valid_{idx}"))
        idx += 1

    for _ in range(n_null):
        features.append(_make_null_geometry_feature(fid=f"null_{idx}"))
        idx += 1

    for _ in range(n_empty):
        features.append(_make_empty_geometry_feature(fid=f"empty_{idx}"))
        idx += 1

    for _ in range(n_bad):
        features.append(_make_self_intersecting_feature(fid=f"bad_{idx}"))
        idx += 1

    # Shuffle so order doesn't matter
    features = draw(st.permutations(features))

    expected_invalid = n_null + n_empty
    # Self-intersecting features are either repaired or removed — both count as 1 log entry
    expected_log_entries = n_null + n_empty + n_bad

    return features, expected_log_entries


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

@given(geojson_feature_list())
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_geometry_qc_completeness(feature_data: tuple[list[dict], int]) -> None:
    """Property 3: Geometry QC Completeness.

    After run_geometry_qc:
    1. Every output feature has a non-null, non-empty, valid Shapely geometry.
    2. The correction log has exactly one entry per invalid feature injected.
    """
    features, expected_log_entries = feature_data

    cleaned, correction_log = run_geometry_qc(features)

    # ── Assert 1: zero invalid geometries in output ─────────────────────
    from shapely.geometry import shape as shapely_shape

    for feat in cleaned:
        geom_dict = feat.get("geometry")
        assert geom_dict, (
            f"Output feature {feat.get('id', '?')} has null/empty geometry dict."
        )
        geom = shapely_shape(geom_dict)
        assert not geom.is_empty, (
            f"Output feature {feat.get('id', '?')} has an empty Shapely geometry."
        )
        assert geom.is_valid, (
            f"Output feature {feat.get('id', '?')} has an invalid (self-intersecting) "
            f"geometry after QC."
        )

    # ── Assert 2: correction log has exactly one entry per invalid feature ─
    assert len(correction_log) == expected_log_entries, (
        f"Expected {expected_log_entries} correction-log entries, "
        f"got {len(correction_log)}.\nLog: {correction_log}"
    )

    # Each log entry must have the required keys and a valid action value
    for entry in correction_log:
        assert "source" in entry, f"Log entry missing 'source': {entry}"
        assert "feature_id" in entry, f"Log entry missing 'feature_id': {entry}"
        assert "action" in entry, f"Log entry missing 'action': {entry}"
        assert entry["action"] in {"removed", "repaired"}, (
            f"Unexpected action value: {entry['action']!r}"
        )
