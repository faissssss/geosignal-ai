"""Offline DEM-based line-of-sight precomputation for GeoSignal AI.

This module provides a lightweight terrain-aware LOS approximation for the
hackathon MVP. It does not replace operator-grade RF propagation modelling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import numpy as np
from affine import Affine
from pyproj import CRS, Transformer
from rasterio.transform import rowcol
from sklearn.neighbors import BallTree

from geosignal.constraints import HIGH_CANOPY_LAND_COVER_CLASSES


EARTH_RADIUS_M: float = 6_371_008.8


def compute_los(
    dem: np.ndarray,
    transform: Affine,
    raster_crs: str | CRS,
    candidate_coordinate: tuple[float, float],
    cell_coordinate: tuple[float, float],
    *,
    land_cover: np.ndarray | None = None,
    canopy_height: np.ndarray | None = None,
    observer_height_m: float = 30.0,
    receiver_height_m: float = 1.5,
    clearance_margin_m: float = 0.0,
) -> bool:
    """Check terrain-aware LOS between a BTS candidate and one grid cell.

    Coordinates must use ``(latitude, longitude)`` order.

    LOS is clear when every intermediate terrain or vegetation obstacle lies
    below the straight line connecting the BTS antenna and receiver.
    """
    _validate_rasters(
        dem=dem,
        land_cover=land_cover,
        canopy_height=canopy_height,
    )

    if observer_height_m <= 0:
        raise ValueError("observer_height_m must be positive")

    if receiver_height_m < 0:
        raise ValueError("receiver_height_m cannot be negative")

    if clearance_margin_m < 0:
        raise ValueError("clearance_margin_m cannot be negative")

    start_row, start_col = _coordinate_to_row_col(
        coordinate=candidate_coordinate,
        transform=transform,
        raster_crs=raster_crs,
    )
    end_row, end_col = _coordinate_to_row_col(
        coordinate=cell_coordinate,
        transform=transform,
        raster_crs=raster_crs,
    )

    _validate_position(
        row=start_row,
        col=start_col,
        raster_shape=dem.shape,
        label="candidate",
    )
    _validate_position(
        row=end_row,
        col=end_col,
        raster_shape=dem.shape,
        label="cell",
    )

    rows, cols = _sample_line_indices(
        start_row=start_row,
        start_col=start_col,
        end_row=end_row,
        end_col=end_col,
    )

    # Same pixel or adjacent pixels have no intermediate obstacle.
    if len(rows) <= 2:
        return True

    surface_profile = dem[rows, cols].astype(np.float64)

    if land_cover is not None and canopy_height is not None:
        sampled_classes = land_cover[rows, cols]
        sampled_canopy = canopy_height[rows, cols].astype(np.float64)

        woody_mask = np.isin(
            sampled_classes,
            list(HIGH_CANOPY_LAND_COVER_CLASSES),
        )

        surface_profile = surface_profile + np.where(
            woody_mask,
            sampled_canopy,
            0.0,
        )

    observer_elevation = (
        float(dem[start_row, start_col]) + observer_height_m
    )
    receiver_elevation = (
        float(dem[end_row, end_col]) + receiver_height_m
    )

    sight_line = np.linspace(
        observer_elevation,
        receiver_elevation,
        num=len(rows),
        dtype=np.float64,
    )

    intermediate_surface = surface_profile[1:-1]
    intermediate_sight_line = sight_line[1:-1]

    return bool(
        np.all(
            intermediate_surface
            < intermediate_sight_line - clearance_margin_m
        )
    )


def precompute_los_grid(
    region_id: str,
    candidate_coordinates: np.ndarray,
    cell_coordinates: np.ndarray,
    dem: np.ndarray,
    transform: Affine,
    raster_crs: str | CRS,
    *,
    land_cover: np.ndarray | None = None,
    canopy_height: np.ndarray | None = None,
    max_range_m: float = 10_000.0,
    observer_height_m: float = 30.0,
    receiver_height_m: float = 1.5,
    clearance_margin_m: float = 0.0,
    supabase_client: Any | None = None,
    batch_size: int = 500,
) -> list[dict]:
    """Precompute LOS records for candidate-cell pairs inside BTS range.

    A Haversine BallTree limits LOS calculation to cells inside
    ``max_range_m``. Generated records can optionally be persisted to the
    Supabase ``los_results`` table.
    """
    candidates = _validate_coordinates(
        candidate_coordinates,
        name="candidate_coordinates",
    )
    cells = _validate_coordinates(
        cell_coordinates,
        name="cell_coordinates",
    )

    if not region_id.strip():
        raise ValueError("region_id cannot be empty")

    if max_range_m <= 0:
        raise ValueError("max_range_m must be positive")

    if len(candidates) == 0 or len(cells) == 0:
        return []

    cell_tree = BallTree(
        np.radians(cells),
        metric="haversine",
    )

    radius_radians = max_range_m / EARTH_RADIUS_M
    computed_at = datetime.now(timezone.utc).isoformat()

    records: list[dict] = []

    for candidate in candidates:
        neighbour_indices = cell_tree.query_radius(
            np.radians(candidate.reshape(1, -1)),
            r=radius_radians,
            return_distance=False,
        )[0]

        candidate_lat = float(candidate[0])
        candidate_lon = float(candidate[1])

        for cell_index in neighbour_indices:
            cell = cells[int(cell_index)]
            cell_lat = float(cell[0])
            cell_lon = float(cell[1])

            los_clear = compute_los(
                dem=dem,
                transform=transform,
                raster_crs=raster_crs,
                candidate_coordinate=(candidate_lat, candidate_lon),
                cell_coordinate=(cell_lat, cell_lon),
                land_cover=land_cover,
                canopy_height=canopy_height,
                observer_height_m=observer_height_m,
                receiver_height_m=receiver_height_m,
                clearance_margin_m=clearance_margin_m,
            )

            records.append(
                {
                    "los_id": str(uuid4()),
                    "region_id": region_id,
                    "candidate_lat": candidate_lat,
                    "candidate_lon": candidate_lon,
                    "cell_lat": cell_lat,
                    "cell_lon": cell_lon,
                    "los_clear": los_clear,
                    "computed_at": computed_at,
                }
            )

    if supabase_client is not None and records:
        persist_los_results(
            supabase_client=supabase_client,
            records=records,
            batch_size=batch_size,
        )

    return records


def persist_los_results(
    supabase_client: Any,
    records: list[dict],
    *,
    batch_size: int = 500,
) -> None:
    """Insert LOS records into Supabase in bounded batches."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]

        (
            supabase_client
            .table("los_results")
            .insert(batch)
            .execute()
        )


def _validate_rasters(
    dem: np.ndarray,
    land_cover: np.ndarray | None,
    canopy_height: np.ndarray | None,
) -> None:
    if dem.ndim != 2:
        raise ValueError("dem must be a two-dimensional array")

    if not np.isfinite(dem).all():
        raise ValueError("dem must contain only finite values")

    if (land_cover is None) != (canopy_height is None):
        raise ValueError(
            "land_cover and canopy_height must be provided together"
        )

    if land_cover is not None and land_cover.shape != dem.shape:
        raise ValueError("land_cover must have the same shape as dem")

    if canopy_height is not None:
        if canopy_height.shape != dem.shape:
            raise ValueError(
                "canopy_height must have the same shape as dem"
            )

        if not np.isfinite(canopy_height).all():
            raise ValueError(
                "canopy_height must contain only finite values"
            )

        if np.any(canopy_height < 0):
            raise ValueError(
                "canopy_height cannot contain negative values"
            )


def _validate_coordinates(
    coordinates: np.ndarray,
    *,
    name: str,
) -> np.ndarray:
    array = np.asarray(coordinates, dtype=np.float64)

    if array.ndim != 2 or array.shape[1] != 2:
        raise ValueError(f"{name} must have shape (N, 2)")

    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite values")

    if np.any((array[:, 0] < -90) | (array[:, 0] > 90)):
        raise ValueError(f"{name} contains invalid latitude values")

    if np.any((array[:, 1] < -180) | (array[:, 1] > 180)):
        raise ValueError(f"{name} contains invalid longitude values")

    return array


def _coordinate_to_row_col(
    coordinate: tuple[float, float],
    transform: Affine,
    raster_crs: str | CRS,
) -> tuple[int, int]:
    latitude, longitude = coordinate

    transformer = Transformer.from_crs(
        "EPSG:4326",
        raster_crs,
        always_xy=True,
    )

    x, y = transformer.transform(longitude, latitude)
    row, col = rowcol(transform, x, y)

    return int(row), int(col)


def _validate_position(
    row: int,
    col: int,
    raster_shape: tuple[int, int],
    *,
    label: str,
) -> None:
    height, width = raster_shape

    if not (0 <= row < height and 0 <= col < width):
        raise ValueError(
            f"{label} coordinate falls outside the raster extent"
        )


def _sample_line_indices(
    start_row: int,
    start_col: int,
    end_row: int,
    end_col: int,
) -> tuple[np.ndarray, np.ndarray]:
    sample_count = (
        max(
            abs(end_row - start_row),
            abs(end_col - start_col),
        )
        + 1
    )

    rows = np.rint(
        np.linspace(start_row, end_row, sample_count)
    ).astype(int)

    cols = np.rint(
        np.linspace(start_col, end_col, sample_count)
    ).astype(int)

    # Remove consecutive duplicate raster cells caused by rounding.
    keep = np.ones(len(rows), dtype=bool)

    if len(rows) > 1:
        keep[1:] = (
            (rows[1:] != rows[:-1])
            | (cols[1:] != cols[:-1])
        )

    return rows[keep], cols[keep]