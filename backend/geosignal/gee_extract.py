"""GeoSignal AI — GEE raster extraction for production heatmap scoring.

Phase 2 of .kiro/specs/data-production/: bound GEE sampling to the stored
kecamatan polygons and extract real raster values (SRTM elevation, ESA
WorldCover land cover, canopy height, WorldPop population) at per-kecamatan
analysis points.

Public API
----------
generate_analysis_points(boundary_geojson, spacing_m, max_points) -> list[(lat, lon)]
sample_gee_at_points(points, scale_m) -> list[dict]
extract_kecamatan(boundary_geojson, spacing_m, max_points, scale_m) -> list[dict]

All dataset IDs are module-level constants so tests can monkeypatch them.
"""
from __future__ import annotations

import logging
import math
from typing import Any

import ee
from shapely.geometry import Point, shape

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GEE dataset configuration (verified live 2026-08-10)
# ---------------------------------------------------------------------------

SRTM_IMAGE_ID = "USGS/SRTMGL1_003"
WORLDCOVER_COLLECTION_ID = "ESA/WorldCover/v200"
CANOPY_IMAGE_ID = "users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1"
WORLDPOP_COLLECTION_ID = "WorldPop/GP/100m/pop"
WORLDPOP_YEAR = 2020

# Output band names (canonical, used by features.py / scoring.py)
BAND_ELEVATION = "elevation_m"
BAND_SLOPE = "slope_deg"
BAND_LAND_COVER = "land_cover_class"
BAND_CANOPY = "canopy_height_m"
BAND_POPULATION = "population_density_per_km2"

_initialized = False


def initialize_gee() -> None:
    """Initialise the Earth Engine client from environment variables.

    Uses ``GEE_SERVICE_ACCOUNT_EMAIL``, ``GEE_SERVICE_ACCOUNT_JSON_PATH`` and
    ``GEE_PROJECT_ID``.  Idempotent.
    """
    global _initialized
    if _initialized:
        return
    import os

    email = os.environ.get("GEE_SERVICE_ACCOUNT_EMAIL", "")
    json_path = os.environ.get("GEE_SERVICE_ACCOUNT_JSON_PATH", "")
    project = os.environ.get("GEE_PROJECT_ID", "")
    if not email or not json_path or not project:
        raise RuntimeError(
            "GEE env vars incomplete: need GEE_SERVICE_ACCOUNT_EMAIL, "
            "GEE_SERVICE_ACCOUNT_JSON_PATH, GEE_PROJECT_ID."
        )
    creds = ee.ServiceAccountCredentials(email, json_path)
    ee.Initialize(creds, project=project)
    _initialized = True


def _gee_image() -> ee.Image:
    """Build the combined GEE image with canonical band names."""
    srtm = ee.Image(SRTM_IMAGE_ID).select("elevation").rename(BAND_ELEVATION)
    slope = ee.Terrain.slope(ee.Image(SRTM_IMAGE_ID)).select("slope").rename(BAND_SLOPE)

    worldcover = (
        ee.ImageCollection(WORLDCOVER_COLLECTION_ID)
        .first()
        .select("Map")
        .rename(BAND_LAND_COVER)
    )

    canopy = ee.Image(CANOPY_IMAGE_ID).select("b1").rename(BAND_CANOPY)

    worldpop = (
        ee.ImageCollection(WORLDPOP_COLLECTION_ID)
        .filter(ee.Filter.eq("country", "IDN"))
        .filter(ee.Filter.eq("year", WORLDPOP_YEAR))
        .first()
        .select("population")
        .rename(BAND_POPULATION)
    )

    return srtm.addBands(slope).addBands(worldcover).addBands(canopy).addBands(worldpop)


def generate_analysis_points(
    boundary_geojson: dict,
    spacing_m: float = 500.0,
    max_points: int = 3000,
) -> list[tuple[float, float]]:
    """Generate (lat, lon) analysis points inside a kecamatan polygon.

    Uses a regular lat/lon grid at *spacing_m* (approximated via degrees at
    the polygon centroid latitude) and keeps only points covered by the
    polygon.  Capped at *max_points* to keep GEE requests bounded.

    Parameters
    ----------
    boundary_geojson:
        GeoJSON geometry (Polygon or MultiPolygon) of the kecamatan.
    spacing_m:
        Approximate grid spacing in metres.
    max_points:
        Maximum number of points to return (sampled evenly from the grid).

    Returns
    -------
    list[(lat, lon)]
        Points strictly inside the boundary, in (lat, lon) order.
    """
    geom = shape(boundary_geojson)
    if geom.is_empty or not geom.is_valid:
        logger.warning("Invalid/empty boundary geometry; returning no points.")
        return []

    minx, miny, maxx, maxy = geom.bounds
    center_lat = (miny + maxy) / 2.0
    # 1 degree of latitude ~ 111,320 m; longitude shrinks by cos(lat).
    lat_step = spacing_m / 111_320.0
    lon_step = spacing_m / (111_320.0 * max(0.2, abs(math.cos(math.radians(center_lat)))))

    points: list[tuple[float, float]] = []
    lat = miny
    while lat <= maxy and len(points) < max_points:
        lon = minx
        while lon <= maxx and len(points) < max_points:
            if geom.covers(Point(lon, lat)):
                points.append((lat, lon))
            lon += lon_step
        lat += lat_step

    if len(points) > max_points:
        # Evenly subsample to the cap.
        step = len(points) / max_points
        points = [points[int(i * step)] for i in range(max_points)]

    logger.info("Generated %d analysis points (spacing=%sm, cap=%d)", len(points), spacing_m, max_points)
    return points


def sample_gee_at_points(
    points: list[tuple[float, float]],
    scale_m: int = 100,
) -> list[dict]:
    """Sample the combined GEE image at the given (lat, lon) points.

    Parameters
    ----------
    points:
        List of (lat, lon) tuples.
    scale_m:
        GEE sampling scale in metres.

    Returns
    -------
    list[dict]
        One dict per point with keys ``lat``, ``lon`` and the four canonical
        band names.  Missing raster values are ``None`` (never invented).
    """
    if not points:
        return []

    initialize_gee()
    image = _gee_image()
    fc = ee.FeatureCollection(
        [
            ee.Feature(ee.Geometry.Point([lon, lat]), {"idx": i})
            for i, (lat, lon) in enumerate(points)
        ]
    )

    sampled = image.sampleRegions(
        collection=fc,
        scale=scale_m,
        geometries=False,
    )

    info = sampled.getInfo() or {}
    features = info.get("features", [])
    results: list[dict] = []
    for feat in features:
        props = feat.get("properties", {})
        idx = props.get("idx")
        if idx is None:
            continue
        lat, lon = points[int(idx)]
        results.append(
            {
                "lat": lat,
                "lon": lon,
                BAND_ELEVATION: props.get(BAND_ELEVATION),
                BAND_SLOPE: props.get(BAND_SLOPE),
                BAND_LAND_COVER: props.get(BAND_LAND_COVER),
                BAND_CANOPY: props.get(BAND_CANOPY),
                BAND_POPULATION: props.get(BAND_POPULATION),
            }
        )
    return results


def extract_kecamatan(
    boundary_geojson: dict,
    spacing_m: float = 500.0,
    max_points: int = 3000,
    scale_m: int = 100,
) -> list[dict]:
    """Generate analysis points for a kecamatan and sample GEE at them.

    Returns a list of sampled records (see ``sample_gee_at_points``).  A
    kecamatan with no valid geometry yields an empty list — never fabricated
    values.
    """
    points = generate_analysis_points(boundary_geojson, spacing_m, max_points)
    return sample_gee_at_points(points, scale_m)