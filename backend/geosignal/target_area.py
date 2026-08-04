"""Target-area resolution for GeoSignal AI.

A Planner can select a target area using either:

1. A GADM kecamatan identifier already stored in ``admin_boundaries``.
2. A user-drawn polygon GeoJSON.

Resolved areas are persisted to ``target_areas`` and used to restrict grid
cells before candidate ranking or BTS-placement simulation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

import numpy as np
from shapely.geometry import Point, shape
from shapely.validation import explain_validity

from geosignal.models import TargetArea


SelectionMethod = Literal[
    "drawn_polygon",
    "kecamatan",
]


class TargetAreaValidationError(ValueError):
    """Structured validation error for target-area requests."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        field: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)

        self.code = code
        self.message = message
        self.field = field
        self.details = dict(details or {})

    def to_dict(self) -> dict[str, Any]:
        """Return an API-compatible structured error payload."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "field": self.field,
                "details": deepcopy(self.details),
            }
        }


class TargetAreaStore(Protocol):
    """Persistence contract required by ``resolve_target_area``."""

    def get_admin_boundary(
        self,
        *,
        region_id: str,
        kecamatan_id: str,
    ) -> dict[str, Any] | None:
        ...

    def insert_target_area(
        self,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        ...


class InMemoryTargetAreaStore:
    """In-memory target-area store for tests and offline development."""

    def __init__(
        self,
        admin_boundaries: Sequence[
            Mapping[str, Any]
        ] = (),
    ) -> None:
        self._admin_boundaries: dict[
            tuple[str, str],
            dict[str, Any],
        ] = {}

        self._target_areas: dict[
            str,
            dict[str, Any],
        ] = {}

        for raw_record in admin_boundaries:
            record = deepcopy(dict(raw_record))

            region_id = str(
                record.get("region_id", "")
            ).strip()

            kecamatan_id = str(
                record.get("kecamatan_id", "")
            ).strip()

            if not region_id or not kecamatan_id:
                raise ValueError(
                    "Admin boundary records require "
                    "region_id and kecamatan_id"
                )

            key = (
                region_id,
                kecamatan_id,
            )

            if key in self._admin_boundaries:
                raise ValueError(
                    "Duplicate admin boundary: "
                    f"{region_id}/{kecamatan_id}"
                )

            self._admin_boundaries[key] = record

    @property
    def target_areas(self) -> list[dict[str, Any]]:
        """Return defensive copies of persisted target areas."""
        return [
            deepcopy(record)
            for record in self._target_areas.values()
        ]

    def get_admin_boundary(
        self,
        *,
        region_id: str,
        kecamatan_id: str,
    ) -> dict[str, Any] | None:
        record = self._admin_boundaries.get(
            (
                region_id,
                kecamatan_id,
            )
        )

        return (
            None
            if record is None
            else deepcopy(record)
        )

    def insert_target_area(
        self,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        target_area_id = str(
            record["target_area_id"]
        )

        if target_area_id in self._target_areas:
            raise ValueError(
                "Target area already exists: "
                f"{target_area_id}"
            )

        stored = deepcopy(dict(record))

        self._target_areas[target_area_id] = stored

        return deepcopy(stored)


class SupabaseTargetAreaStore:
    """Supabase implementation of target-area persistence."""

    def __init__(
        self,
        client: Any,
    ) -> None:
        self.client = client

    def get_admin_boundary(
        self,
        *,
        region_id: str,
        kecamatan_id: str,
    ) -> dict[str, Any] | None:
        response = (
            self.client
            .table("admin_boundaries")
            .select("*")
            .eq("region_id", region_id)
            .eq("kecamatan_id", kecamatan_id)
            .limit(1)
            .execute()
        )

        rows = _response_rows(response)

        return rows[0] if rows else None

    def insert_target_area(
        self,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        response = (
            self.client
            .table("target_areas")
            .insert(dict(record))
            .execute()
        )

        rows = _response_rows(response)

        return (
            rows[0]
            if rows
            else deepcopy(dict(record))
        )


def resolve_target_area(
    region_id: str,
    selection_method: SelectionMethod,
    payload: Mapping[str, Any] | str,
    *,
    store: TargetAreaStore,
    target_area_id: str | UUID | None = None,
    created_at: datetime | None = None,
) -> TargetArea:
    """Resolve and persist a Planner-selected target area.

    Parameters
    ----------
    region_id:
        Region containing the selected area.

    selection_method:
        Either ``"drawn_polygon"`` or ``"kecamatan"``.

    payload:
        A polygon GeoJSON mapping for ``drawn_polygon`` or a kecamatan ID
        string for ``kecamatan``.

    store:
        Persistence implementation used to read ``admin_boundaries`` and
        insert into ``target_areas``.

    target_area_id:
        Optional UUID supplied by the caller. A new UUID is generated when
        omitted.

    created_at:
        Optional timezone-aware creation timestamp.

    Returns
    -------
    TargetArea
        Canonical target-area model imported from ``geosignal.models``.
    """
    normalised_region = _normalise_non_empty_string(
        region_id,
        field="region_id",
    )

    if selection_method not in {
        "drawn_polygon",
        "kecamatan",
    }:
        raise TargetAreaValidationError(
            code="invalid_selection_method",
            message=(
                "selection_method must be "
                "'drawn_polygon' or 'kecamatan'"
            ),
            field="selection_method",
            details={
                "received": selection_method,
            },
        )

    if selection_method == "kecamatan":
        boundary, kecamatan_id = (
            _resolve_kecamatan_boundary(
                region_id=normalised_region,
                payload=payload,
                store=store,
            )
        )
    else:
        boundary = _resolve_drawn_polygon(
            payload
        )
        kecamatan_id = None

    resolved_id = _normalise_uuid(
        target_area_id
        if target_area_id is not None
        else uuid4(),
        field="target_area_id",
    )

    target_area = TargetArea(
        target_area_id=resolved_id,
        region_id=normalised_region,
        selection_method=selection_method,
        boundary=deepcopy(boundary),
        kecamatan_id=kecamatan_id,
    )

    persistence_record = {
        "target_area_id": (
            target_area.target_area_id
        ),
        "region_id": target_area.region_id,
        "selection_method": (
            target_area.selection_method
        ),
        "kecamatan_id": (
            target_area.kecamatan_id
        ),
        "boundary_geojson": deepcopy(
            target_area.boundary
        ),
        "created_at": _utc_iso(created_at),
    }

    store.insert_target_area(
        persistence_record
    )

    return target_area


def filter_grid_cells_to_target_area(
    grid_cells: Sequence[
        Sequence[float]
    ] | np.ndarray,
    target_area: TargetArea,
) -> np.ndarray:
    """Return only grid-cell coordinates covered by a target area.

    Grid cells use the project's canonical ``(latitude, longitude)`` order.
    GeoJSON and Shapely use ``(longitude, latitude)``, so the coordinate
    order is deliberately reversed when constructing each point.

    Points lying exactly on the polygon boundary are retained through
    ``covers`` rather than excluded through ``contains``.
    """
    if not isinstance(target_area, TargetArea):
        raise TypeError(
            "target_area must be a TargetArea"
        )

    try:
        coordinates = np.asarray(
            grid_cells,
            dtype=np.float64,
        )
    except (TypeError, ValueError) as exc:
        raise TargetAreaValidationError(
            code="invalid_grid_cells",
            message=(
                "grid_cells must contain numeric "
                "(latitude, longitude) pairs"
            ),
            field="grid_cells",
        ) from exc

    if (
        coordinates.ndim != 2
        or coordinates.shape[1] != 2
    ):
        raise TargetAreaValidationError(
            code="invalid_grid_cells_shape",
            message=(
                "grid_cells must have shape (N, 2)"
            ),
            field="grid_cells",
            details={
                "shape": list(
                    coordinates.shape
                ),
            },
        )

    if not np.isfinite(coordinates).all():
        raise TargetAreaValidationError(
            code="non_finite_grid_cells",
            message=(
                "grid_cells must contain only "
                "finite coordinates"
            ),
            field="grid_cells",
        )

    polygon = _parse_polygon_geometry(
        target_area.boundary,
        allow_multipolygon=True,
        field="boundary",
    )

    included = np.asarray(
        [
            polygon.covers(
                Point(
                    float(longitude),
                    float(latitude),
                )
            )
            for latitude, longitude
            in coordinates
        ],
        dtype=bool,
    )

    return coordinates[included].copy()


def all_grid_cells_within_target_area(
    grid_cells: Sequence[
        Sequence[float]
    ] | np.ndarray,
    target_area: TargetArea,
) -> bool:
    """Return whether every supplied grid cell is covered by the boundary."""
    try:
        coordinates = np.asarray(
            grid_cells,
            dtype=np.float64,
        )
    except (TypeError, ValueError):
        return False

    if (
        coordinates.ndim != 2
        or coordinates.shape[1] != 2
        or not np.isfinite(coordinates).all()
    ):
        return False

    filtered = filter_grid_cells_to_target_area(
        coordinates,
        target_area,
    )

    return len(filtered) == len(coordinates)


def _resolve_kecamatan_boundary(
    *,
    region_id: str,
    payload: Mapping[str, Any] | str,
    store: TargetAreaStore,
) -> tuple[dict[str, Any], str]:
    if not isinstance(payload, str):
        raise TargetAreaValidationError(
            code="invalid_kecamatan_payload",
            message=(
                "The kecamatan selection payload "
                "must be a kecamatan_id string"
            ),
            field="payload",
        )

    kecamatan_id = _normalise_non_empty_string(
        payload,
        field="payload",
    )

    record = store.get_admin_boundary(
        region_id=region_id,
        kecamatan_id=kecamatan_id,
    )

    if record is None:
        raise TargetAreaValidationError(
            code="kecamatan_not_found",
            message=(
                "No GADM boundary was found for "
                f"kecamatan '{kecamatan_id}' "
                f"in region '{region_id}'"
            ),
            field="payload",
            details={
                "region_id": region_id,
                "kecamatan_id": kecamatan_id,
            },
        )

    boundary = _extract_boundary(
        record
    )

    _parse_polygon_geometry(
        boundary,
        allow_multipolygon=True,
        field="admin_boundaries.boundary",
    )

    # Return the exact stored GADM GeoJSON rather than reconstructing it.
    return deepcopy(boundary), kecamatan_id


def _resolve_drawn_polygon(
    payload: Mapping[str, Any] | str,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise TargetAreaValidationError(
            code="invalid_drawn_polygon_payload",
            message=(
                "The drawn_polygon payload must be "
                "a polygon GeoJSON mapping"
            ),
            field="payload",
        )

    boundary = deepcopy(dict(payload))

    _parse_polygon_geometry(
        boundary,
        allow_multipolygon=False,
        field="payload",
    )

    # Preserve the exact submitted GeoJSON.
    return boundary


def _extract_boundary(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    for field_name in (
        "boundary_geojson",
        "boundary",
        "geometry",
    ):
        value = record.get(field_name)

        if value is not None:
            if not isinstance(value, Mapping):
                raise TargetAreaValidationError(
                    code="invalid_admin_boundary",
                    message=(
                        "Stored GADM boundary must "
                        "be a GeoJSON mapping"
                    ),
                    field=field_name,
                )

            return deepcopy(dict(value))

    raise TargetAreaValidationError(
        code="missing_admin_boundary",
        message=(
            "The admin boundary record does not "
            "contain a boundary geometry"
        ),
        field="admin_boundaries",
    )


def _parse_polygon_geometry(
    geojson: Mapping[str, Any],
    *,
    allow_multipolygon: bool,
    field: str,
):
    if not isinstance(geojson, Mapping):
        raise TargetAreaValidationError(
            code="invalid_geojson",
            message=(
                "Boundary must be a GeoJSON mapping"
            ),
            field=field,
        )

    geometry_type = geojson.get("type")

    allowed_types = (
        {"Polygon", "MultiPolygon"}
        if allow_multipolygon
        else {"Polygon"}
    )

    if geometry_type not in allowed_types:
        raise TargetAreaValidationError(
            code="invalid_geometry_type",
            message=(
                "Boundary geometry type must be "
                + " or ".join(
                    sorted(allowed_types)
                )
            ),
            field=field,
            details={
                "received_type": geometry_type,
            },
        )

    try:
        geometry = shape(
            deepcopy(dict(geojson))
        )
    except Exception as exc:
        raise TargetAreaValidationError(
            code="malformed_geojson",
            message=(
                "Boundary could not be parsed "
                "as valid GeoJSON"
            ),
            field=field,
        ) from exc

    if geometry.is_empty:
        raise TargetAreaValidationError(
            code="empty_polygon",
            message=(
                "Boundary polygon cannot be empty"
            ),
            field=field,
        )

    if not geometry.is_valid:
        validity_reason = explain_validity(
            geometry
        )

        is_self_intersection = (
            "self-intersection"
            in validity_reason.lower()
        )

        raise TargetAreaValidationError(
            code=(
                "self_intersecting_polygon"
                if is_self_intersection
                else "invalid_polygon"
            ),
            message=(
                "Boundary polygon is invalid and "
                "will not be automatically repaired"
            ),
            field=field,
            details={
                "reason": validity_reason,
            },
        )

    return geometry


def _normalise_non_empty_string(
    value: Any,
    *,
    field: str,
) -> str:
    if not isinstance(value, str):
        raise TargetAreaValidationError(
            code="invalid_string",
            message=f"{field} must be a string",
            field=field,
        )

    normalised = value.strip()

    if not normalised:
        raise TargetAreaValidationError(
            code="empty_value",
            message=f"{field} cannot be empty",
            field=field,
        )

    return normalised


def _normalise_uuid(
    value: str | UUID,
    *,
    field: str,
) -> str:
    try:
        return str(
            UUID(str(value))
        )
    except (
        TypeError,
        ValueError,
        AttributeError,
    ) as exc:
        raise TargetAreaValidationError(
            code="invalid_uuid",
            message=(
                f"{field} must be a valid UUID"
            ),
            field=field,
        ) from exc


def _utc_iso(
    value: datetime | None,
) -> str:
    timestamp = (
        datetime.now(timezone.utc)
        if value is None
        else value
    )

    if timestamp.tzinfo is None:
        raise TargetAreaValidationError(
            code="timezone_required",
            message=(
                "created_at must include timezone "
                "information"
            ),
            field="created_at",
        )

    return timestamp.astimezone(
        timezone.utc
    ).isoformat()


def _response_rows(
    response: Any,
) -> list[dict[str, Any]]:
    if hasattr(response, "data"):
        data = response.data
    elif isinstance(response, Mapping):
        data = response.get(
            "data",
            [],
        )
    else:
        data = []

    return [
        deepcopy(dict(row))
        for row in (data or [])
    ]