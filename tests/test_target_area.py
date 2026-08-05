"""Tests for Target Area Resolution — Task 17.

Includes:
  - Property 25 (Hypothesis): Target Area Resolution Correctness (sub-task 17.2)
  - Unit tests: kecamatan mode, drawn_polygon mode, self-intersecting rejection,
    grid-cell containment.

# Feature: geosignal-ai, Property 25: Target Area Resolution Correctness
"""
from __future__ import annotations

import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from geosignal.models import TargetArea
from geosignal.target_area import (
    filter_grid_cells_to_target_area,
    resolve_target_area,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_POLYGON = {
    "type": "Polygon",
    "coordinates": [[
        [120.0, -9.0],
        [120.5, -9.0],
        [120.5, -9.5],
        [120.0, -9.5],
        [120.0, -9.0],
    ]],
}

_SELF_INTERSECTING_POLYGON = {
    "type": "Polygon",
    "coordinates": [[
        [0.0, 0.0],
        [1.0, 1.0],
        [1.0, 0.0],
        [0.0, 1.0],
        [0.0, 0.0],
    ]],
}


def _make_admin_boundaries(n: int = 3) -> list[dict]:
    """Create n fake admin boundary rows. Each is a 1-degree square polygon."""
    rows = []
    for i in range(n):
        lon_base = 119.0 + i * 2.0
        rows.append({
            "kecamatan_id": f"IDN.15.{i + 1}_1",
            "kecamatan_name": f"Kecamatan-{i + 1}",
            "region_id": "ntt",
            "boundary_geojson": {
                "type": "Polygon",
                "coordinates": [[
                    [lon_base,       -9.0],
                    [lon_base + 1.0, -9.0],
                    [lon_base + 1.0, -10.0],
                    [lon_base,       -10.0],
                    [lon_base,       -9.0],
                ]],
            },
        })
    return rows


# ---------------------------------------------------------------------------
# Property 25 — Target Area Resolution Correctness
# Validates: Requirements 10.7, 10.8, 4.1, 5.1
# ---------------------------------------------------------------------------

@given(kecamatan_index=st.integers(min_value=0, max_value=2))
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_property_25_kecamatan_boundary_equals_gadm(kecamatan_index):
    """kecamatan mode: boundary equals GADM geometry and kecamatan_id is set.

    # Feature: geosignal-ai, Property 25: Target Area Resolution Correctness
    **Validates: Requirements 10.7, 10.8, 4.1, 5.1**
    """
    admin_boundaries = _make_admin_boundaries(3)
    row = admin_boundaries[kecamatan_index]
    kecamatan_id = row["kecamatan_id"]
    expected_boundary = row["boundary_geojson"]

    ta = resolve_target_area(
        region_id="ntt",
        selection_method="kecamatan",
        payload=kecamatan_id,
        admin_boundaries=admin_boundaries,
    )

    assert isinstance(ta, TargetArea)
    assert ta.selection_method == "kecamatan"
    assert ta.kecamatan_id == kecamatan_id
    assert ta.boundary == expected_boundary
    assert ta.region_id == "ntt"
    assert ta.target_area_id  # non-empty string


@given(
    lon_min=st.floats(min_value=95.0, max_value=139.0,
                      allow_nan=False, allow_infinity=False),
    lat_min=st.floats(min_value=-11.0, max_value=-1.5,
                      allow_nan=False, allow_infinity=False),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_property_25_drawn_polygon_boundary_equals_input(lon_min, lat_min):
    """drawn_polygon mode: boundary equals input polygon and kecamatan_id is None.

    # Feature: geosignal-ai, Property 25: Target Area Resolution Correctness
    **Validates: Requirements 10.7, 10.8, 4.1, 5.1**
    """
    polygon = {
        "type": "Polygon",
        "coordinates": [[
            [lon_min,       lat_min],
            [lon_min + 0.5, lat_min],
            [lon_min + 0.5, lat_min - 0.5],
            [lon_min,       lat_min - 0.5],
            [lon_min,       lat_min],
        ]],
    }

    ta = resolve_target_area(
        region_id="ntt",
        selection_method="drawn_polygon",
        payload=polygon,
    )

    assert isinstance(ta, TargetArea)
    assert ta.selection_method == "drawn_polygon"
    assert ta.kecamatan_id is None
    assert ta.boundary == polygon
    assert ta.region_id == "ntt"
    assert ta.target_area_id


@given(kecamatan_index=st.integers(min_value=0, max_value=2))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_property_25_grid_cells_inside_boundary_pass_filter(kecamatan_index):
    """Cells that fall inside the resolved boundary are retained by filter;
    cells outside are excluded.

    # Feature: geosignal-ai, Property 25: Target Area Resolution Correctness
    **Validates: Requirements 4.1, 5.1**
    """
    admin_boundaries = _make_admin_boundaries(3)
    row = admin_boundaries[kecamatan_index]
    kecamatan_id = row["kecamatan_id"]
    lon_base = 119.0 + kecamatan_index * 2.0

    ta = resolve_target_area(
        region_id="ntt",
        selection_method="kecamatan",
        payload=kecamatan_id,
        admin_boundaries=admin_boundaries,
    )

    # A cell clearly inside: centroid of the polygon
    inside_cell = (-9.5, lon_base + 0.5)
    # A cell clearly outside: far from all polygons
    outside_cell = (10.0, 10.0)

    filtered = filter_grid_cells_to_target_area(
        [inside_cell, outside_cell], ta
    )

    assert inside_cell in filtered, "Cell inside the boundary must be retained"
    assert outside_cell not in filtered, "Cell outside the boundary must be excluded"


# ---------------------------------------------------------------------------
# Unit tests — kecamatan mode
# ---------------------------------------------------------------------------

def test_unit_kecamatan_returns_gadm_boundary():
    """kecamatan mode returns the GADM boundary verbatim."""
    boundaries = _make_admin_boundaries(1)
    kid = boundaries[0]["kecamatan_id"]
    expected = boundaries[0]["boundary_geojson"]

    ta = resolve_target_area(
        region_id="ntt",
        selection_method="kecamatan",
        payload=kid,
        admin_boundaries=boundaries,
    )

    assert ta.boundary == expected
    assert ta.kecamatan_id == kid


def test_unit_kecamatan_id_is_populated():
    """kecamatan_id is not None in kecamatan mode."""
    boundaries = _make_admin_boundaries(2)
    kid = boundaries[1]["kecamatan_id"]

    ta = resolve_target_area(
        region_id="ntt",
        selection_method="kecamatan",
        payload=kid,
        admin_boundaries=boundaries,
    )

    assert ta.kecamatan_id is not None
    assert ta.kecamatan_id == kid


def test_unit_kecamatan_unknown_id_raises_key_error():
    """KeyError raised when kecamatan_id is not found."""
    boundaries = _make_admin_boundaries(2)

    with pytest.raises(KeyError):
        resolve_target_area(
            region_id="ntt",
            selection_method="kecamatan",
            payload="DOES.NOT.EXIST",
            admin_boundaries=boundaries,
        )


def test_unit_kecamatan_none_boundaries_raises_key_error():
    """KeyError raised when admin_boundaries is None."""
    with pytest.raises(KeyError):
        resolve_target_area(
            region_id="ntt",
            selection_method="kecamatan",
            payload="IDN.15.1_1",
            admin_boundaries=None,
        )


# ---------------------------------------------------------------------------
# Unit tests — drawn_polygon mode
# ---------------------------------------------------------------------------

def test_unit_drawn_polygon_returns_input_boundary():
    """drawn_polygon mode: boundary equals the input GeoJSON."""
    ta = resolve_target_area(
        region_id="ntt",
        selection_method="drawn_polygon",
        payload=_VALID_POLYGON,
    )

    assert ta.boundary == _VALID_POLYGON
    assert ta.kecamatan_id is None
    assert ta.selection_method == "drawn_polygon"


def test_unit_drawn_polygon_kecamatan_id_is_none():
    """kecamatan_id is always None in drawn_polygon mode."""
    ta = resolve_target_area(
        region_id="ntb",
        selection_method="drawn_polygon",
        payload=_VALID_POLYGON,
    )
    assert ta.kecamatan_id is None


def test_unit_drawn_polygon_target_area_id_is_nonempty():
    """target_area_id is a non-empty string (UUID)."""
    ta = resolve_target_area(
        region_id="ntt",
        selection_method="drawn_polygon",
        payload=_VALID_POLYGON,
    )
    assert ta.target_area_id
    # Must be parseable as UUID
    parsed = uuid.UUID(ta.target_area_id)
    assert str(parsed) == ta.target_area_id


def test_unit_drawn_polygon_self_intersecting_raises_value_error():
    """Self-intersecting drawn polygon is rejected with ValueError.
    User polygons are NOT auto-repaired (unlike pipeline source-data QC).
    """
    with pytest.raises(ValueError, match="self-intersecting|invalid"):
        resolve_target_area(
            region_id="ntt",
            selection_method="drawn_polygon",
            payload=_SELF_INTERSECTING_POLYGON,
        )


def test_unit_drawn_polygon_non_dict_payload_raises_value_error():
    """Non-dict payload in drawn_polygon mode raises ValueError."""
    with pytest.raises(ValueError):
        resolve_target_area(
            region_id="ntt",
            selection_method="drawn_polygon",
            payload="not a geojson dict",  # type: ignore[arg-type]
        )


def test_unit_drawn_polygon_wrong_geometry_type_raises_value_error():
    """Non-Polygon geometry type raises ValueError."""
    point_geom = {"type": "Point", "coordinates": [120.0, -9.0]}
    with pytest.raises(ValueError):
        resolve_target_area(
            region_id="ntt",
            selection_method="drawn_polygon",
            payload=point_geom,
        )


def test_unit_unknown_selection_method_raises_value_error():
    """Unknown selection_method raises ValueError."""
    with pytest.raises(ValueError):
        resolve_target_area(
            region_id="ntt",
            selection_method="invalid_method",  # type: ignore[arg-type]
            payload=_VALID_POLYGON,
        )


# ---------------------------------------------------------------------------
# Unit tests — filter_grid_cells_to_target_area
# ---------------------------------------------------------------------------

def test_unit_filter_cells_inside_polygon():
    """Cells inside the polygon pass the filter."""
    ta = resolve_target_area(
        region_id="ntt",
        selection_method="drawn_polygon",
        payload=_VALID_POLYGON,
    )
    # _VALID_POLYGON spans lon 120.0–120.5, lat -9.0 to -9.5
    cells_inside = [(-9.25, 120.25), (-9.1, 120.1)]
    cells_outside = [(0.0, 0.0), (-9.25, 119.0)]

    filtered = filter_grid_cells_to_target_area(
        cells_inside + cells_outside, ta
    )

    for c in cells_inside:
        assert c in filtered, f"Cell {c} should be inside the polygon"
    for c in cells_outside:
        assert c not in filtered, f"Cell {c} should be outside the polygon"


def test_unit_filter_cells_empty_input():
    """Empty grid cell list returns empty list."""
    ta = resolve_target_area(
        region_id="ntt",
        selection_method="drawn_polygon",
        payload=_VALID_POLYGON,
    )
    assert filter_grid_cells_to_target_area([], ta) == []
