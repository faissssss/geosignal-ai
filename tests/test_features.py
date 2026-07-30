"""Unit tests for feature engineering — sub-task 7.2.

Tests:
1. Independent nearest-neighbour indices: BTS and road distances differ when
   points are at different locations.
2. Distinct source rasters: land_cover_class values are int, canopy_height_m
   are float, and they can differ between cells.
3. All 8 CONSOLIDATED_FEATURES populated: every returned FeatureVector has all
   8 fields — no AttributeError, no None values.
4. BallTree uses haversine: known pair of lat/lon → distance ≈ correct.
5. Empty reference points: compute_nearest_distances returns np.inf array.
"""
from __future__ import annotations

import math
import sys
import os

# Ensure the backend package is importable when running from the project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import numpy as np
import pytest

from geosignal.features import compute_feature_vectors, compute_nearest_distances
from geosignal.models import CONSOLIDATED_FEATURES, FeatureVector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_harmonised_arrays(rows: int = 3, cols: int = 3) -> dict[str, np.ndarray]:
    """Build a minimal set of harmonised raster arrays for testing."""
    rng = np.random.default_rng(42)
    return {
        "elevation_m": rng.uniform(0.0, 500.0, size=(rows, cols)).astype(np.float32),
        "land_cover_class": rng.integers(10, 90, size=(rows, cols)).astype(np.int32),
        "canopy_height_m": rng.uniform(0.0, 30.0, size=(rows, cols)).astype(np.float32),
        "population_density_per_km2": rng.uniform(0.0, 1000.0, size=(rows, cols)).astype(np.float32),
    }


def _make_grid(rows: int = 3, cols: int = 3):
    """Return (grid_lats, grid_lons) arrays for a small 3×3 grid near Jakarta."""
    grid_lats = np.linspace(-6.5, -6.2, rows)
    grid_lons = np.linspace(106.7, 107.0, cols)
    return grid_lats, grid_lons


# ---------------------------------------------------------------------------
# Test 1 — Independent nearest-neighbour indices
# ---------------------------------------------------------------------------


def test_independent_nearest_neighbour_indices() -> None:
    """distance_to_bts_m and road_distance_m must use independent indices.

    Place BTS points to the north-west and road points to the south-east of the
    grid so that each cell has a measurably different distance to each set.
    The resulting distances should differ, proving independent BallTrees are used.
    """
    arrays = _make_harmonised_arrays(rows=3, cols=3)
    grid_lats, grid_lons = _make_grid(rows=3, cols=3)

    # BTS far to the north-west of the grid
    bts_points = np.array([[0.0, 100.0]])   # far north-west

    # Road nodes far to the south-east of the grid
    road_points = np.array([[-10.0, 112.0]])  # far south-east

    # POI points somewhere neutral
    poi_points = np.array([[-6.35, 106.85]])

    fvs = compute_feature_vectors(
        harmonised_arrays=arrays,
        bts_points=bts_points,
        road_points=road_points,
        poi_points=poi_points,
        grid_lats=grid_lats,
        grid_lons=grid_lons,
    )

    # For every cell, BTS distance and road distance must differ
    for fv in fvs:
        assert fv.distance_to_bts_m != fv.road_distance_m, (
            f"distance_to_bts_m ({fv.distance_to_bts_m:.1f}) equals "
            f"road_distance_m ({fv.road_distance_m:.1f}) — indices may be shared."
        )

    # Also verify facility_proximity_m differs from both road and bts distances
    # (since POI is at yet another location)
    bts_distances = {fv.distance_to_bts_m for fv in fvs}
    road_distances = {fv.road_distance_m for fv in fvs}
    facility_distances = {fv.facility_proximity_m for fv in fvs}

    # The three sets of distances should not all be identical
    assert not (bts_distances == road_distances == facility_distances), (
        "All three distance fields returned identical values — "
        "they may be sharing a single BallTree index."
    )


# ---------------------------------------------------------------------------
# Test 2 — Distinct source rasters
# ---------------------------------------------------------------------------


def test_distinct_source_rasters_types_and_values() -> None:
    """land_cover_class must be int; canopy_height_m must be float.

    Also assert that at least two cells can have differing values for each
    field, confirming no aliasing between the two source arrays.
    """
    # Use distinct integer and float arrays so the values cannot match by accident.
    rows, cols = 4, 4
    land_cover_arr = np.array(
        [[10, 20, 30, 40],
         [50, 60, 70, 80],
         [10, 20, 30, 40],
         [50, 60, 70, 80]], dtype=np.int32
    )
    canopy_arr = np.array(
        [[0.5, 1.5, 2.5, 3.5],
         [4.5, 5.5, 6.5, 7.5],
         [8.5, 9.5, 10.5, 11.5],
         [12.5, 13.5, 14.5, 15.5]], dtype=np.float32
    )
    arrays = {
        "elevation_m": np.ones((rows, cols), dtype=np.float32) * 100.0,
        "land_cover_class": land_cover_arr,
        "canopy_height_m": canopy_arr,
        "population_density_per_km2": np.ones((rows, cols), dtype=np.float32) * 50.0,
    }
    grid_lats, grid_lons = np.linspace(-6.5, -6.2, rows), np.linspace(106.7, 107.0, cols)
    bts_points = np.array([[0.0, 106.0]])
    road_points = np.array([[-5.0, 108.0]])
    poi_points = np.array([[-6.3, 106.8]])

    fvs = compute_feature_vectors(
        harmonised_arrays=arrays,
        bts_points=bts_points,
        road_points=road_points,
        poi_points=poi_points,
        grid_lats=grid_lats,
        grid_lons=grid_lons,
    )

    for fv in fvs:
        # land_cover_class must be an integer type
        assert isinstance(fv.land_cover_class, int), (
            f"land_cover_class should be int, got {type(fv.land_cover_class)}"
        )
        # canopy_height_m must be a float type
        assert isinstance(fv.canopy_height_m, float), (
            f"canopy_height_m should be float, got {type(fv.canopy_height_m)}"
        )

    # Values must differ between cells (not aliased/collapsed to one value)
    land_cover_values = [fv.land_cover_class for fv in fvs]
    canopy_values = [fv.canopy_height_m for fv in fvs]

    assert len(set(land_cover_values)) > 1, (
        "All land_cover_class values are identical — source raster may not be read correctly."
    )
    assert len(set(canopy_values)) > 1, (
        "All canopy_height_m values are identical — source raster may not be read correctly."
    )

    # Confirm the two fields are sourced from distinct arrays (values differ between fields)
    # land_cover integers cannot equal float decimals
    for fv in fvs:
        # canopy values are fractional; land cover values are multiples of 10
        assert fv.canopy_height_m != fv.land_cover_class or fv.canopy_height_m % 1 != 0, (
            "canopy_height_m and land_cover_class appear to share the same source value."
        )


# ---------------------------------------------------------------------------
# Test 3 — All 8 CONSOLIDATED_FEATURES populated
# ---------------------------------------------------------------------------


def test_all_eight_consolidated_features_populated() -> None:
    """Every returned FeatureVector must have all 8 CONSOLIDATED_FEATURES set.

    No field may be None; all fields must be accessible without AttributeError.
    """
    rows, cols = 2, 2
    arrays = _make_harmonised_arrays(rows=rows, cols=cols)
    grid_lats, grid_lons = _make_grid(rows=rows, cols=cols)

    bts_points = np.array([[-6.35, 106.85]])
    road_points = np.array([[-6.40, 106.90]])
    poi_points = np.array([[-6.30, 106.80]])

    fvs = compute_feature_vectors(
        harmonised_arrays=arrays,
        bts_points=bts_points,
        road_points=road_points,
        poi_points=poi_points,
        grid_lats=grid_lats,
        grid_lons=grid_lons,
    )

    assert len(fvs) == rows * cols, (
        f"Expected {rows * cols} FeatureVectors, got {len(fvs)}"
    )

    for i, fv in enumerate(fvs):
        for feature_name in CONSOLIDATED_FEATURES:
            # Must be accessible without AttributeError
            value = getattr(fv, feature_name)
            assert value is not None, (
                f"FeatureVector[{i}].{feature_name} is None — field was not populated."
            )
            # Must be a numeric value (not NaN is not enforced here, but None is)
            assert isinstance(value, (int, float)), (
                f"FeatureVector[{i}].{feature_name} = {value!r} is not a number."
            )


# ---------------------------------------------------------------------------
# Test 4 — BallTree uses haversine (distance accuracy check)
# ---------------------------------------------------------------------------


def test_compute_nearest_distances_haversine_accuracy() -> None:
    """Two points 1° apart in longitude at the equator should be ≈ 111 320 m.

    We use a query point at (0°, 0°) and a reference point at (0°, 1°).
    The expected haversine distance is 1° × 111 320 m/° = 111 320 m.
    We allow ±1% tolerance.
    """
    query_points = np.array([[0.0, 0.0]])    # (lat=0, lon=0)
    reference_points = np.array([[0.0, 1.0]])  # (lat=0, lon=1) — 1° to the east

    distances = compute_nearest_distances(query_points, reference_points)

    expected_m = 111_320.0  # 1° of longitude at equator in metres
    tolerance = 0.01        # 1% tolerance

    assert distances.shape == (1,), (
        f"Expected shape (1,), got {distances.shape}"
    )
    assert abs(distances[0] - expected_m) / expected_m <= tolerance, (
        f"Expected distance ≈ {expected_m:.0f} m (±1%), "
        f"got {distances[0]:.0f} m — haversine metric may not be used."
    )


def test_compute_nearest_distances_known_pair() -> None:
    """Nairobi → Mombasa distance: approx 440 km (well-known geographic pair).

    Nairobi: (-1.286, 36.817)
    Mombasa: (-4.043, 39.668)
    Approx great-circle: ~440 km
    """
    query = np.array([[-1.286, 36.817]])
    ref = np.array([[-4.043, 39.668]])

    distances = compute_nearest_distances(query, ref)

    # Expect somewhere in the range 430–460 km
    expected_km = 440.0
    tolerance_km = 20.0

    assert abs(distances[0] / 1000 - expected_km) <= tolerance_km, (
        f"Nairobi→Mombasa distance: expected ≈ {expected_km} km, "
        f"got {distances[0] / 1000:.1f} km."
    )


# ---------------------------------------------------------------------------
# Test 5 — Empty reference points → np.inf
# ---------------------------------------------------------------------------


def test_compute_nearest_distances_empty_reference_returns_inf() -> None:
    """When reference_points is empty, all returned distances must be np.inf."""
    query_points = np.array([
        [-6.2, 106.8],
        [-6.3, 106.9],
        [-6.4, 107.0],
    ])
    # Empty reference array — shape (0, 2)
    empty_ref = np.empty((0, 2))

    distances = compute_nearest_distances(query_points, empty_ref)

    assert distances.shape == (3,), (
        f"Expected shape (3,), got {distances.shape}"
    )
    assert np.all(np.isinf(distances)), (
        f"Expected all np.inf, got: {distances}"
    )


def test_compute_nearest_distances_empty_reference_zero_query() -> None:
    """Edge case: 1-row query, empty reference → single np.inf."""
    query = np.array([[0.0, 0.0]])
    empty_ref = np.empty((0, 2))

    distances = compute_nearest_distances(query, empty_ref)

    assert distances.shape == (1,)
    assert np.isinf(distances[0])


# ---------------------------------------------------------------------------
# Test 6 — KeyError for missing required raster fields
# ---------------------------------------------------------------------------


def test_compute_feature_vectors_raises_keyerror_on_missing_field() -> None:
    """compute_feature_vectors must raise KeyError with a clear message
    when a required raster key is absent from harmonised_arrays."""
    incomplete_arrays = {
        "elevation_m": np.ones((3, 3), dtype=np.float32),
        # "land_cover_class" is intentionally omitted
        "canopy_height_m": np.ones((3, 3), dtype=np.float32),
        "population_density_per_km2": np.ones((3, 3), dtype=np.float32),
    }
    grid_lats = np.array([-6.5, -6.35, -6.2])
    grid_lons = np.array([106.7, 106.85, 107.0])
    bts_pts = np.array([[0.0, 106.0]])
    road_pts = np.array([[-5.0, 108.0]])
    poi_pts = np.array([[-6.3, 106.8]])

    with pytest.raises(KeyError, match="land_cover_class"):
        compute_feature_vectors(
            harmonised_arrays=incomplete_arrays,
            bts_points=bts_pts,
            road_points=road_pts,
            poi_points=poi_pts,
            grid_lats=grid_lats,
            grid_lons=grid_lons,
        )


# ---------------------------------------------------------------------------
# Test 7 — Row-major ordering (rows × cols)
# ---------------------------------------------------------------------------


def test_compute_feature_vectors_returns_correct_count() -> None:
    """compute_feature_vectors must return rows × cols FeatureVectors."""
    rows, cols = 5, 4
    arrays = _make_harmonised_arrays(rows=rows, cols=cols)
    grid_lats = np.linspace(-6.5, -6.2, rows)
    grid_lons = np.linspace(106.7, 107.0, cols)
    bts_pts = np.array([[-6.35, 106.85]])
    road_pts = np.array([[-6.40, 106.90]])
    poi_pts = np.array([[-6.30, 106.80]])

    fvs = compute_feature_vectors(
        harmonised_arrays=arrays,
        bts_points=bts_pts,
        road_points=road_pts,
        poi_points=poi_pts,
        grid_lats=grid_lats,
        grid_lons=grid_lons,
    )

    assert len(fvs) == rows * cols, (
        f"Expected {rows * cols} FeatureVectors for a {rows}×{cols} grid, got {len(fvs)}"
    )
    # Every element must be a FeatureVector
    for fv in fvs:
        assert isinstance(fv, FeatureVector), (
            f"Expected FeatureVector, got {type(fv)}"
        )
