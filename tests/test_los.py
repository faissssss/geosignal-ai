"""Tests for offline DEM-based LOS precomputation."""

import numpy as np
import pytest
from rasterio.transform import from_origin

from geosignal.los import (
    compute_los,
    persist_los_results,
    precompute_los_grid,
)


TRANSFORM = from_origin(
    west=0.0,
    north=5.0,
    xsize=1.0,
    ysize=1.0,
)

RASTER_CRS = "EPSG:4326"

CANDIDATE = (2.5, 0.5)
TARGET = (2.5, 4.5)


def test_flat_terrain_has_clear_los() -> None:
    dem = np.zeros((5, 5), dtype=float)

    result = compute_los(
        dem=dem,
        transform=TRANSFORM,
        raster_crs=RASTER_CRS,
        candidate_coordinate=CANDIDATE,
        cell_coordinate=TARGET,
    )

    assert result is True


def test_high_ridge_blocks_los() -> None:
    dem = np.zeros((5, 5), dtype=float)
    dem[2, 2] = 25.0

    result = compute_los(
        dem=dem,
        transform=TRANSFORM,
        raster_crs=RASTER_CRS,
        candidate_coordinate=CANDIDATE,
        cell_coordinate=TARGET,
    )

    assert result is False


def test_woody_canopy_blocks_los() -> None:
    dem = np.zeros((5, 5), dtype=float)
    land_cover = np.full((5, 5), 40, dtype=int)
    canopy = np.zeros((5, 5), dtype=float)

    land_cover[2, 2] = 10
    canopy[2, 2] = 20.0

    result = compute_los(
        dem=dem,
        transform=TRANSFORM,
        raster_crs=RASTER_CRS,
        candidate_coordinate=CANDIDATE,
        cell_coordinate=TARGET,
        land_cover=land_cover,
        canopy_height=canopy,
    )

    assert result is False


def test_non_woody_class_does_not_add_canopy_obstacle() -> None:
    dem = np.zeros((5, 5), dtype=float)
    land_cover = np.full((5, 5), 40, dtype=int)
    canopy = np.zeros((5, 5), dtype=float)

    canopy[2, 2] = 20.0

    result = compute_los(
        dem=dem,
        transform=TRANSFORM,
        raster_crs=RASTER_CRS,
        candidate_coordinate=CANDIDATE,
        cell_coordinate=TARGET,
        land_cover=land_cover,
        canopy_height=canopy,
    )

    assert result is True


def test_land_cover_and_canopy_must_be_supplied_together() -> None:
    dem = np.zeros((5, 5), dtype=float)
    land_cover = np.full((5, 5), 10, dtype=int)

    with pytest.raises(
        ValueError,
        match="must be provided together",
    ):
        compute_los(
            dem=dem,
            transform=TRANSFORM,
            raster_crs=RASTER_CRS,
            candidate_coordinate=CANDIDATE,
            cell_coordinate=TARGET,
            land_cover=land_cover,
        )


def test_coordinate_outside_raster_is_rejected() -> None:
    dem = np.zeros((5, 5), dtype=float)

    with pytest.raises(
        ValueError,
        match="outside the raster extent",
    ):
        compute_los(
            dem=dem,
            transform=TRANSFORM,
            raster_crs=RASTER_CRS,
            candidate_coordinate=(20.0, 20.0),
            cell_coordinate=TARGET,
        )


def test_precompute_los_grid_returns_database_records() -> None:
    dem = np.zeros((5, 5), dtype=float)

    records = precompute_los_grid(
        region_id="ntt",
        candidate_coordinates=np.array([CANDIDATE]),
        cell_coordinates=np.array([TARGET]),
        dem=dem,
        transform=TRANSFORM,
        raster_crs=RASTER_CRS,
        max_range_m=600_000.0,
    )

    assert len(records) == 1

    record = records[0]

    assert record["region_id"] == "ntt"
    assert record["candidate_lat"] == CANDIDATE[0]
    assert record["candidate_lon"] == CANDIDATE[1]
    assert record["cell_lat"] == TARGET[0]
    assert record["cell_lon"] == TARGET[1]
    assert record["los_clear"] is True
    assert record["los_id"]
    assert record["computed_at"]


def test_precompute_excludes_cells_outside_range() -> None:
    dem = np.zeros((5, 5), dtype=float)

    records = precompute_los_grid(
        region_id="ntt",
        candidate_coordinates=np.array([CANDIDATE]),
        cell_coordinates=np.array([TARGET]),
        dem=dem,
        transform=TRANSFORM,
        raster_crs=RASTER_CRS,
        max_range_m=1_000.0,
    )

    assert records == []


class FakeInsertQuery:
    def __init__(self, client: "FakeSupabaseClient") -> None:
        self.client = client

    def insert(self, rows: list[dict]) -> "FakeInsertQuery":
        self.client.inserted_rows.extend(rows)
        return self

    def execute(self) -> dict:
        return {"data": self.client.inserted_rows}


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.table_name: str | None = None
        self.inserted_rows: list[dict] = []

    def table(self, table_name: str) -> FakeInsertQuery:
        self.table_name = table_name
        return FakeInsertQuery(self)


def test_persist_los_results_uses_correct_table() -> None:
    client = FakeSupabaseClient()

    records = [
        {
            "los_id": "los-1",
            "region_id": "ntt",
            "candidate_lat": -10.0,
            "candidate_lon": 123.0,
            "cell_lat": -10.1,
            "cell_lon": 123.1,
            "los_clear": True,
            "computed_at": "2026-08-03T00:00:00+00:00",
        }
    ]

    persist_los_results(
        supabase_client=client,
        records=records,
    )

    assert client.table_name == "los_results"
    assert client.inserted_rows == records