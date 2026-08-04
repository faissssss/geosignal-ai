"""Tests for GeoSignal AI target-area resolution."""

from __future__ import annotations

from uuid import uuid4

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Point, shape

from geosignal.models import TargetArea
from geosignal.target_area import (
    InMemoryTargetAreaStore,
    SupabaseTargetAreaStore,
    TargetAreaValidationError,
    all_grid_cells_within_target_area,
    filter_grid_cells_to_target_area,
    resolve_target_area,
)


REGION_ID = "ntt"
KECAMATAN_ID = "IDN.18.01.01_1"


def _rectangle(
    *,
    minimum_lon: float = 123.0,
    minimum_lat: float = -10.0,
    width: float = 1.0,
    height: float = 1.0,
) -> dict:
    maximum_lon = minimum_lon + width
    maximum_lat = minimum_lat + height

    return {
        "type": "Polygon",
        "coordinates": [
            [
                [
                    minimum_lon,
                    minimum_lat,
                ],
                [
                    maximum_lon,
                    minimum_lat,
                ],
                [
                    maximum_lon,
                    maximum_lat,
                ],
                [
                    minimum_lon,
                    maximum_lat,
                ],
                [
                    minimum_lon,
                    minimum_lat,
                ],
            ]
        ],
    }


def _store_with_boundary(
    *,
    region_id: str = REGION_ID,
    kecamatan_id: str = KECAMATAN_ID,
    boundary: dict | None = None,
) -> InMemoryTargetAreaStore:
    return InMemoryTargetAreaStore(
        [
            {
                "region_id": region_id,
                "kecamatan_id": kecamatan_id,
                "kecamatan_name": "Test Kecamatan",
                "boundary_geojson": (
                    _rectangle()
                    if boundary is None
                    else boundary
                ),
            }
        ]
    )


def test_drawn_polygon_is_preserved_and_persisted() -> None:
    store = InMemoryTargetAreaStore()
    polygon = _rectangle()
    target_area_id = uuid4()

    result = resolve_target_area(
        REGION_ID,
        "drawn_polygon",
        polygon,
        store=store,
        target_area_id=target_area_id,
    )

    assert isinstance(
        result,
        TargetArea,
    )

    assert result.target_area_id == str(
        target_area_id
    )
    assert result.region_id == REGION_ID
    assert (
        result.selection_method
        == "drawn_polygon"
    )
    assert result.boundary == polygon
    assert result.kecamatan_id is None

    assert len(store.target_areas) == 1

    persisted = store.target_areas[0]

    assert (
        persisted["boundary_geojson"]
        == polygon
    )
    assert persisted["kecamatan_id"] is None


def test_kecamatan_uses_exact_gadm_boundary() -> None:
    boundary = _rectangle(
        minimum_lon=124.0,
        minimum_lat=-9.0,
        width=0.5,
        height=0.75,
    )
    store = _store_with_boundary(
        boundary=boundary
    )

    result = resolve_target_area(
        REGION_ID,
        "kecamatan",
        KECAMATAN_ID,
        store=store,
    )

    assert result.boundary == boundary
    assert result.kecamatan_id == KECAMATAN_ID
    assert (
        result.selection_method
        == "kecamatan"
    )

    persisted = store.target_areas[0]

    assert (
        persisted["boundary_geojson"]
        == boundary
    )
    assert (
        persisted["kecamatan_id"]
        == KECAMATAN_ID
    )


def test_invalid_selection_method_is_rejected() -> None:
    store = InMemoryTargetAreaStore()

    with pytest.raises(
        TargetAreaValidationError,
    ) as error:
        resolve_target_area(
            REGION_ID,
            "district",
            _rectangle(),
            store=store,
        )

    assert (
        error.value.code
        == "invalid_selection_method"
    )
    assert not store.target_areas


def test_unknown_kecamatan_is_rejected() -> None:
    store = _store_with_boundary()

    with pytest.raises(
        TargetAreaValidationError,
    ) as error:
        resolve_target_area(
            REGION_ID,
            "kecamatan",
            "unknown-kecamatan",
            store=store,
        )

    assert (
        error.value.code
        == "kecamatan_not_found"
    )
    assert not store.target_areas


def test_kecamatan_payload_must_be_string() -> None:
    store = _store_with_boundary()

    with pytest.raises(
        TargetAreaValidationError,
    ) as error:
        resolve_target_area(
            REGION_ID,
            "kecamatan",
            {
                "kecamatan_id": KECAMATAN_ID
            },
            store=store,
        )

    assert (
        error.value.code
        == "invalid_kecamatan_payload"
    )


def test_drawn_polygon_payload_must_be_mapping() -> None:
    store = InMemoryTargetAreaStore()

    with pytest.raises(
        TargetAreaValidationError,
    ) as error:
        resolve_target_area(
            REGION_ID,
            "drawn_polygon",
            "not-geojson",
            store=store,
        )

    assert (
        error.value.code
        == "invalid_drawn_polygon_payload"
    )


def test_self_intersecting_polygon_is_not_repaired() -> None:
    store = InMemoryTargetAreaStore()

    bow_tie_polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [123.0, -10.0],
                [124.0, -9.0],
                [123.0, -9.0],
                [124.0, -10.0],
                [123.0, -10.0],
            ]
        ],
    }

    with pytest.raises(
        TargetAreaValidationError,
    ) as error:
        resolve_target_area(
            REGION_ID,
            "drawn_polygon",
            bow_tie_polygon,
            store=store,
        )

    assert (
        error.value.code
        == "self_intersecting_polygon"
    )

    assert (
        "reason"
        in error.value.details
    )

    # Invalid user geometry must never be auto-repaired or persisted.
    assert not store.target_areas


def test_drawn_multipolygon_is_rejected() -> None:
    store = InMemoryTargetAreaStore()

    multi_polygon = {
        "type": "MultiPolygon",
        "coordinates": [
            _rectangle()["coordinates"],
        ],
    }

    with pytest.raises(
        TargetAreaValidationError,
    ) as error:
        resolve_target_area(
            REGION_ID,
            "drawn_polygon",
            multi_polygon,
            store=store,
        )

    assert (
        error.value.code
        == "invalid_geometry_type"
    )


def test_grid_cells_are_filtered_to_boundary() -> None:
    polygon = _rectangle()

    target_area = TargetArea(
        target_area_id=str(uuid4()),
        region_id=REGION_ID,
        selection_method="drawn_polygon",
        boundary=polygon,
        kecamatan_id=None,
    )

    grid_cells = np.asarray(
        [
            [-9.5, 123.5],   # inside
            [-10.0, 123.0], # boundary
            [-8.0, 125.0],  # outside
        ],
        dtype=np.float64,
    )

    filtered = (
        filter_grid_cells_to_target_area(
            grid_cells,
            target_area,
        )
    )

    assert filtered.shape == (2, 2)

    boundary_shape = shape(
        target_area.boundary
    )

    assert all(
        boundary_shape.covers(
            Point(
                float(longitude),
                float(latitude),
            )
        )
        for latitude, longitude
        in filtered
    )

    assert all_grid_cells_within_target_area(
        filtered,
        target_area,
    )

    assert not all_grid_cells_within_target_area(
        grid_cells,
        target_area,
    )


def test_invalid_grid_cell_shape_is_rejected() -> None:
    target_area = TargetArea(
        target_area_id=str(uuid4()),
        region_id=REGION_ID,
        selection_method="drawn_polygon",
        boundary=_rectangle(),
        kecamatan_id=None,
    )

    with pytest.raises(
        TargetAreaValidationError,
    ) as error:
        filter_grid_cells_to_target_area(
            [1.0, 2.0, 3.0],
            target_area,
        )

    assert (
        error.value.code
        == "invalid_grid_cells_shape"
    )


def test_duplicate_target_area_id_is_rejected() -> None:
    store = InMemoryTargetAreaStore()
    target_area_id = uuid4()

    resolve_target_area(
        REGION_ID,
        "drawn_polygon",
        _rectangle(),
        store=store,
        target_area_id=target_area_id,
    )

    with pytest.raises(
        ValueError,
        match="already exists",
    ):
        resolve_target_area(
            REGION_ID,
            "drawn_polygon",
            _rectangle(
                minimum_lon=125.0
            ),
            store=store,
            target_area_id=target_area_id,
        )


class FakeSupabaseQuery:
    def __init__(
        self,
        client: "FakeSupabaseClient",
        table_name: str,
    ) -> None:
        self.client = client
        self.table_name = table_name
        self.operation: str | None = None
        self.filters: dict[str, object] = {}
        self.payload: dict | None = None
        self.limit_count: int | None = None

    def select(
        self,
        columns: str,
    ) -> "FakeSupabaseQuery":
        self.operation = "select"
        return self

    def eq(
        self,
        field: str,
        value: object,
    ) -> "FakeSupabaseQuery":
        self.filters[field] = value
        return self

    def limit(
        self,
        count: int,
    ) -> "FakeSupabaseQuery":
        self.limit_count = count
        return self

    def insert(
        self,
        payload: dict,
    ) -> "FakeSupabaseQuery":
        self.operation = "insert"
        self.payload = payload
        return self

    def execute(self) -> dict:
        if (
            self.table_name
            == "admin_boundaries"
        ):
            rows = [
                row
                for row in self.client.admin_boundaries
                if all(
                    row.get(field) == value
                    for field, value
                    in self.filters.items()
                )
            ]

            if self.limit_count is not None:
                rows = rows[:self.limit_count]

            return {
                "data": rows,
            }

        if (
            self.table_name
            == "target_areas"
            and self.operation == "insert"
        ):
            assert self.payload is not None

            self.client.target_areas.append(
                self.payload
            )

            return {
                "data": [self.payload],
            }

        return {
            "data": [],
        }


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.admin_boundaries = [
            {
                "region_id": REGION_ID,
                "kecamatan_id": KECAMATAN_ID,
                "boundary_geojson": (
                    _rectangle()
                ),
            }
        ]
        self.target_areas: list[dict] = []
        self.requested_tables: list[str] = []

    def table(
        self,
        table_name: str,
    ) -> FakeSupabaseQuery:
        self.requested_tables.append(
            table_name
        )

        return FakeSupabaseQuery(
            self,
            table_name,
        )


def test_supabase_store_uses_required_tables() -> None:
    client = FakeSupabaseClient()
    store = SupabaseTargetAreaStore(
        client
    )

    result = resolve_target_area(
        REGION_ID,
        "kecamatan",
        KECAMATAN_ID,
        store=store,
    )

    assert result.kecamatan_id == KECAMATAN_ID

    assert client.requested_tables == [
        "admin_boundaries",
        "target_areas",
    ]

    assert len(client.target_areas) == 1


@st.composite
def _rectangle_cases(draw):
    minimum_lon = draw(
        st.integers(
            min_value=110,
            max_value=130,
        )
    )
    minimum_lat = draw(
        st.integers(
            min_value=-11,
            max_value=-3,
        )
    )
    width = draw(
        st.integers(
            min_value=1,
            max_value=4,
        )
    )
    height = draw(
        st.integers(
            min_value=1,
            max_value=4,
        )
    )
    identifier_number = draw(
        st.integers(
            min_value=1,
            max_value=999_999,
        )
    )

    return (
        float(minimum_lon),
        float(minimum_lat),
        float(width),
        float(height),
        f"kec-{identifier_number}",
    )


# Feature: geosignal-ai, Property 25:
# Target Area Resolution Correctness
@settings(max_examples=50, deadline=None)
@given(case=_rectangle_cases())
def test_property_25_kecamatan_resolution_correctness(
    case,
) -> None:
    (
        minimum_lon,
        minimum_lat,
        width,
        height,
        kecamatan_id,
    ) = case

    boundary = _rectangle(
        minimum_lon=minimum_lon,
        minimum_lat=minimum_lat,
        width=width,
        height=height,
    )

    store = _store_with_boundary(
        kecamatan_id=kecamatan_id,
        boundary=boundary,
    )

    target_area = resolve_target_area(
        REGION_ID,
        "kecamatan",
        kecamatan_id,
        store=store,
    )

    assert target_area.boundary == boundary
    assert (
        target_area.kecamatan_id
        == kecamatan_id
    )

    grid_cells = np.asarray(
        [
            [
                minimum_lat + height / 2.0,
                minimum_lon + width / 2.0,
            ],
            [
                minimum_lat,
                minimum_lon,
            ],
            [
                minimum_lat + height + 1.0,
                minimum_lon + width + 1.0,
            ],
        ],
        dtype=np.float64,
    )

    filtered = filter_grid_cells_to_target_area(
        grid_cells,
        target_area,
    )

    assert len(filtered) == 2

    assert all_grid_cells_within_target_area(
        filtered,
        target_area,
    )


# Feature: geosignal-ai, Property 25:
# Target Area Resolution Correctness
@settings(max_examples=50, deadline=None)
@given(case=_rectangle_cases())
def test_property_25_drawn_polygon_resolution_correctness(
    case,
) -> None:
    (
        minimum_lon,
        minimum_lat,
        width,
        height,
        _,
    ) = case

    polygon = _rectangle(
        minimum_lon=minimum_lon,
        minimum_lat=minimum_lat,
        width=width,
        height=height,
    )

    store = InMemoryTargetAreaStore()

    target_area = resolve_target_area(
        REGION_ID,
        "drawn_polygon",
        polygon,
        store=store,
    )

    assert target_area.boundary == polygon
    assert target_area.kecamatan_id is None

    grid_cells = np.asarray(
        [
            [
                minimum_lat + height / 2.0,
                minimum_lon + width / 2.0,
            ],
            [
                minimum_lat,
                minimum_lon,
            ],
            [
                minimum_lat - 1.0,
                minimum_lon - 1.0,
            ],
        ],
        dtype=np.float64,
    )

    filtered = filter_grid_cells_to_target_area(
        grid_cells,
        target_area,
    )

    boundary_shape = shape(
        target_area.boundary
    )

    assert len(filtered) == 2

    assert all(
        boundary_shape.covers(
            Point(
                float(longitude),
                float(latitude),
            )
        )
        for latitude, longitude
        in filtered
    )