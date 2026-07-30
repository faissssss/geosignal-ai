"""GeoSignal AI — Feature engineering.

Computes the eight Consolidated Feature Set inputs for each grid cell,
producing a list of FeatureVector instances ready for coverage scoring.

Public API
----------
compute_slope(elevation_array, resolution_m) -> np.ndarray
compute_nearest_distances(query_points, reference_points) -> np.ndarray
compute_feature_vectors(harmonised_arrays, bts_points, road_points,
                        poi_points, grid_lats, grid_lons) -> list[FeatureVector]
"""
from __future__ import annotations

import numpy as np
from sklearn.neighbors import BallTree

from geosignal.models import CONSOLIDATED_FEATURES, FeatureVector

# Earth radius in metres — used to convert haversine radian distances.
_EARTH_RADIUS_M: float = 6_371_000.0


# ---------------------------------------------------------------------------
# Slope computation
# ---------------------------------------------------------------------------


def compute_slope(elevation_array: np.ndarray, resolution_m: int) -> np.ndarray:
    """Compute slope in degrees from a 2-D elevation array.

    Uses ``np.gradient`` with a 3×3 Sobel-equivalent approach:
        dy, dx = np.gradient(elevation_array, resolution_m)
        slope = arctan(sqrt(dx² + dy²))

    Parameters
    ----------
    elevation_array:
        2-D array of elevation values (metres).
    resolution_m:
        Grid spacing in metres used as the step size for ``np.gradient``.

    Returns
    -------
    np.ndarray
        2-D array of slope values in degrees, same shape as *elevation_array*.
    """
    dy, dx = np.gradient(elevation_array.astype(float), resolution_m)
    slope_rad = np.arctan(np.sqrt(dx**2 + dy**2))
    return np.degrees(slope_rad)


# ---------------------------------------------------------------------------
# Nearest-neighbour distance computation
# ---------------------------------------------------------------------------


def compute_nearest_distances(
    query_points: np.ndarray,
    reference_points: np.ndarray,
) -> np.ndarray:
    """Compute haversine nearest-neighbour distances from query to reference.

    Parameters
    ----------
    query_points:
        (N, 2) array of (lat, lon) in **degrees**.
    reference_points:
        (M, 2) array of (lat, lon) in **degrees**.  May be empty (shape (0, 2)
        or a zero-length array).

    Returns
    -------
    np.ndarray
        (N,) array of distances in **metres**.  Returns an array of
        ``np.inf`` values when *reference_points* is empty.
    """
    n = query_points.shape[0]

    # Guard: empty reference set → absence of record.
    if reference_points.shape[0] == 0:
        return np.full(n, np.inf)

    # BallTree expects radians for haversine metric.
    query_rad = np.radians(query_points)
    ref_rad = np.radians(reference_points)

    tree = BallTree(ref_rad, metric="haversine")
    distances_rad, _ = tree.query(query_rad, k=1)

    # distances_rad is (N, 1) — flatten and convert radian distance to metres.
    return distances_rad[:, 0] * _EARTH_RADIUS_M


# ---------------------------------------------------------------------------
# Full feature vector computation
# ---------------------------------------------------------------------------


def compute_feature_vectors(
    harmonised_arrays: dict[str, np.ndarray],
    bts_points: np.ndarray,
    road_points: np.ndarray,
    poi_points: np.ndarray,
    grid_lats: np.ndarray,
    grid_lons: np.ndarray,
) -> list[FeatureVector]:
    """Compute one FeatureVector per grid cell.

    Parameters
    ----------
    harmonised_arrays:
        ``dict[str, np.ndarray]`` — field name → 2-D array at the chosen
        resolution (output of ``harmonise_rasters`` for a single resolution).
        Must contain keys: ``"elevation_m"``, ``"land_cover_class"``,
        ``"canopy_height_m"``, ``"population_density_per_km2"``.
    bts_points:
        (M, 2) array of (lat, lon) for OpenCellID towers.  May be empty.
    road_points:
        (P, 2) array of (lat, lon) for OSM road nodes.  May be empty.
    poi_points:
        (Q, 2) array of (lat, lon) for OSM POIs.  May be empty.
    grid_lats:
        (rows,) 1-D array of grid cell centroid latitudes.
    grid_lons:
        (cols,) 1-D array of grid cell centroid longitudes.

    Returns
    -------
    list[FeatureVector]
        One FeatureVector per grid cell in row-major order (rows × cols).

    Raises
    ------
    KeyError
        If a required raster key is absent from *harmonised_arrays*.
    """
    # ── Validate required keys up-front ──────────────────────────────────
    required_keys = [
        "elevation_m",
        "land_cover_class",
        "canopy_height_m",
        "population_density_per_km2",
    ]
    for key in required_keys:
        if key not in harmonised_arrays:
            raise KeyError(
                f"Required raster field '{key}' not found in harmonised_arrays. "
                f"Available keys: {list(harmonised_arrays.keys())}"
            )

    # ── Build flat (N, 2) array of grid cell (lat, lon) pairs ────────────
    lats_2d, lons_2d = np.meshgrid(grid_lats, grid_lons, indexing="ij")
    # Shape: (rows, cols) — flatten to (N, 2) in row-major order.
    grid_points = np.column_stack([lats_2d.ravel(), lons_2d.ravel()])

    # ── Raster-sourced features ───────────────────────────────────────────
    elevation_flat = harmonised_arrays["elevation_m"].ravel().astype(float)

    # Slope: derived from elevation via gradient (resolution_m=1 for normalised gradient)
    slope_2d = compute_slope(harmonised_arrays["elevation_m"], resolution_m=1)
    slope_flat = slope_2d.ravel()

    # land_cover_class: integer codes from ESA WorldCover raster
    land_cover_flat = harmonised_arrays["land_cover_class"].ravel().astype(int)

    # canopy_height_m: from OpenGeoAI canopy raster — DISTINCT from land_cover_class
    canopy_flat = harmonised_arrays["canopy_height_m"].ravel().astype(float)

    # population_density_per_km2: WorldPop raster
    pop_density_flat = harmonised_arrays["population_density_per_km2"].ravel().astype(float)

    # ── Nearest-neighbour distances — THREE INDEPENDENT BallTree calls ────
    # 1. Distance to BTS towers (OpenCellID)
    distance_to_bts = compute_nearest_distances(grid_points, bts_points)

    # 2. Distance to OSM road nodes — separate BallTree from BTS index
    road_distance = compute_nearest_distances(grid_points, road_points)

    # 3. Distance to OSM POIs — separate BallTree from road index
    facility_proximity = compute_nearest_distances(grid_points, poi_points)

    # ── Assemble FeatureVector list ───────────────────────────────────────
    n_cells = len(grid_points)
    feature_vectors: list[FeatureVector] = []

    for i in range(n_cells):
        fv = FeatureVector(
            elevation_m=float(elevation_flat[i]),
            slope_deg=float(slope_flat[i]),
            land_cover_class=int(land_cover_flat[i]),
            canopy_height_m=float(canopy_flat[i]),
            distance_to_bts_m=float(distance_to_bts[i]),
            road_distance_m=float(road_distance[i]),
            population_density_per_km2=float(pop_density_flat[i]),
            facility_proximity_m=float(facility_proximity[i]),
        )
        feature_vectors.append(fv)

    return feature_vectors
