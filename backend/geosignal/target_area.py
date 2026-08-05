"""GeoSignal AI — Target Area Resolution (Task 17).

Public API
----------
resolve_target_area(region_id, selection_method, payload) -> TargetArea

Rules (from design.md / requirements.md):
- ``kecamatan`` mode: look up GADM Level 2 boundary from admin_boundaries;
  populate kecamatan_id; TargetArea.boundary equals that kecamatan's GADM geometry.
- ``drawn_polygon`` mode: accept polygon GeoJSON directly; kecamatan_id is None;
  reject self-intersecting polygons with a structured validation error.
  Do NOT auto-repair user-drawn shapes (unlike pipeline QC which repairs source data).
- Persist the resolved TargetArea to the target_areas table (offline/test: return only).
- All grid_cells coordinates for a resolved target_area_id must fall within boundary.

Error handling:
- Invalid or self-intersecting drawn polygon → raise ValueError with structured message.
- kecamatan_id not found in admin_boundaries → raise KeyError.
"""
from __future__ import annotations

import uuid
import logging
from typing import Literal

from shapely.geometry import shape

from geosignal.models import TargetArea

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_target_area(
    region_id: str,
    selection_method: Literal["drawn_polygon", "kecamatan"],
    payload: dict | str,
    admin_boundaries: list[dict] | None = None,
    supabase_client=None,
) -> TargetArea:
    """Resolve a Planner's target-area selection to a TargetArea.

    Parameters
    ----------
    region_id:
        The active region identifier, e.g. ``"ntt"``.
    selection_method:
        Either ``"drawn_polygon"`` or ``"kecamatan"``.
    payload:
        - For ``"drawn_polygon"``: a GeoJSON dict with ``"type"`` and
          ``"coordinates"`` (a valid polygon geometry).
        - For ``"kecamatan"``: a string kecamatan_id (``GID_2`` value from GADM).
    admin_boundaries:
        List of admin boundary row dicts (``kecamatan_id``, ``kecamatan_name``,
        ``region_id``, ``boundary_geojson``).  Required for ``"kecamatan"`` mode.
        When ``None`` and mode is ``"kecamatan"``, a KeyError is raised.
    supabase_client:
        Optional Supabase client for persisting to ``target_areas`` table.
        When ``None`` (offline/test mode), the TargetArea is returned without
        any database writes.

    Returns
    -------
    TargetArea

    Raises
    ------
    ValueError
        If ``selection_method`` is unknown, or if a ``drawn_polygon`` payload is
        self-intersecting or geometrically invalid.
    KeyError
        If ``selection_method == "kecamatan"`` and the given kecamatan_id is not
        found in ``admin_boundaries``.
    """
    if selection_method == "drawn_polygon":
        boundary, kecamatan_id = _resolve_drawn_polygon(payload)
    elif selection_method == "kecamatan":
        boundary, kecamatan_id = _resolve_kecamatan(payload, admin_boundaries, region_id)
    else:
        raise ValueError(
            f"Unknown selection_method {selection_method!r}. "
            "Must be 'drawn_polygon' or 'kecamatan'."
        )

    target_area_id = str(uuid.uuid4())

    target_area = TargetArea(
        target_area_id=target_area_id,
        region_id=region_id,
        selection_method=selection_method,
        boundary=boundary,
        kecamatan_id=kecamatan_id,
    )

    # Persist to Supabase when a client is provided.
    if supabase_client is not None:
        _persist_target_area(target_area, supabase_client)

    logger.info(
        "Resolved TargetArea id=%s region=%s method=%s kecamatan_id=%s",
        target_area_id,
        region_id,
        selection_method,
        kecamatan_id,
    )
    return target_area


# ---------------------------------------------------------------------------
# Grid-cell containment check
# ---------------------------------------------------------------------------


def filter_grid_cells_to_target_area(
    grid_cells: list[tuple[float, float]],
    target_area: TargetArea,
) -> list[tuple[float, float]]:
    """Return only those grid-cell coordinates that fall within target_area.boundary.

    Parameters
    ----------
    grid_cells:
        List of (lat, lon) tuples.
    target_area:
        A resolved TargetArea.

    Returns
    -------
    list[tuple[float, float]]
        Subset of grid_cells whose coordinates lie inside the boundary polygon.
    """
    from shapely.geometry import Point

    boundary_shape = shape(target_area.boundary)
    inside = [
        cell
        for cell in grid_cells
        if boundary_shape.contains(Point(cell[1], cell[0]))  # Point(lon, lat)
    ]
    return inside


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_drawn_polygon(
    payload: dict,
) -> tuple[dict, None]:
    """Validate and return the drawn polygon GeoJSON.

    Does NOT auto-repair self-intersecting geometries — user-drawn shapes are
    rejected with a ValueError (unlike Data_Pipeline's source-data QC).
    """
    if not isinstance(payload, dict):
        raise ValueError(
            "drawn_polygon payload must be a GeoJSON geometry dict, "
            f"got {type(payload).__name__}."
        )

    geom_type = payload.get("type", "")
    if geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError(
            f"drawn_polygon payload must be a Polygon or MultiPolygon geometry, "
            f"got type={geom_type!r}."
        )

    try:
        geom = shape(payload)
    except Exception as exc:
        raise ValueError(
            f"drawn_polygon payload is not a valid GeoJSON geometry: {exc}"
        ) from exc

    if geom.is_empty:
        raise ValueError("drawn_polygon payload produced an empty geometry.")

    if not geom.is_valid:
        raise ValueError(
            "drawn_polygon payload is self-intersecting or invalid. "
            "Please redraw the polygon. "
            f"(Shapely validation: {geom.is_valid})"
        )

    return payload, None


def _resolve_kecamatan(
    kecamatan_id: str,
    admin_boundaries: list[dict] | None,
    region_id: str,
) -> tuple[dict, str]:
    """Look up the kecamatan boundary from admin_boundaries rows.

    Parameters
    ----------
    kecamatan_id:
        The GID_2 value from GADM (e.g. ``"IDN.15.1_1"``).
    admin_boundaries:
        Rows from the admin_boundaries table.
    region_id:
        Used in error messages.

    Returns
    -------
    (boundary_geojson, kecamatan_id)
    """
    if admin_boundaries is None:
        raise KeyError(
            f"kecamatan_id={kecamatan_id!r} not found: "
            "no admin_boundaries data provided (admin_boundaries=None)."
        )

    for row in admin_boundaries:
        if row.get("kecamatan_id") == kecamatan_id:
            boundary = row["boundary_geojson"]
            return boundary, kecamatan_id

    raise KeyError(
        f"kecamatan_id={kecamatan_id!r} not found in admin_boundaries "
        f"for region_id={region_id!r}."
    )


def _persist_target_area(target_area: TargetArea, supabase_client) -> None:
    """Insert the TargetArea into the Supabase target_areas table."""
    row = {
        "target_area_id": target_area.target_area_id,
        "region_id": target_area.region_id,
        "selection_method": target_area.selection_method,
        "kecamatan_id": target_area.kecamatan_id,
        "boundary_geojson": target_area.boundary,
    }
    (
        supabase_client.table("target_areas")
        .insert(row)
        .execute()
    )
    logger.info(
        "Persisted TargetArea id=%s to Supabase target_areas table.",
        target_area.target_area_id,
    )
