"""GeoSignal AI — Multi-resolution raster harmonisation.

Public API
----------
harmonise_rasters(source_arrays, native_crs, native_extent, resolution_variants,
                  continuous_fields, categorical_fields)
    -> dict[int, dict[str, np.ndarray]]

compute_dataset_checksums(source_arrays)
    -> dict[str, str]
"""
from __future__ import annotations

import hashlib

import numpy as np
from scipy.ndimage import zoom

# ---------------------------------------------------------------------------
# Canonical field lists
# ---------------------------------------------------------------------------

DEFAULT_CONTINUOUS_FIELDS: list[str] = [
    "elevation_m",
    "slope_deg",
    "canopy_height_m",
    "population_density_per_km2",
]

DEFAULT_CATEGORICAL_FIELDS: list[str] = [
    "land_cover_class",
]

# Approximate metres per degree of latitude/longitude at equatorial latitudes
# (Indonesia spans roughly 0–10 °S — 1° ≈ 111 320 m is accurate to < 0.3 %).
_METRES_PER_DEGREE: float = 111_320.0


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def harmonise_rasters(
    source_arrays: dict[str, np.ndarray],
    native_crs: str,
    native_extent: tuple[float, float, float, float],
    resolution_variants: list[int],
    continuous_fields: list[str] | None = None,
    categorical_fields: list[str] | None = None,
) -> dict[int, dict[str, np.ndarray]]:
    """Resample source rasters to multiple target resolutions.

    Parameters
    ----------
    source_arrays:
        Mapping of field_name → 2-D numpy array at native resolution.
    native_crs:
        CRS of the input arrays as an EPSG string, e.g. ``"EPSG:4326"``.
    native_extent:
        ``(min_lon, min_lat, max_lon, max_lat)`` bounding box for the arrays.
    resolution_variants:
        List of target resolutions in metres.  Must have at least 2 entries.
    continuous_fields:
        Fields to resample using bilinear interpolation (``order=1``).
        Defaults to :data:`DEFAULT_CONTINUOUS_FIELDS`.
    categorical_fields:
        Fields to resample using nearest-neighbour (``order=0``).
        Defaults to :data:`DEFAULT_CATEGORICAL_FIELDS`.

    Returns
    -------
    dict[int, dict[str, np.ndarray]]
        Outer key: resolution in metres.
        Inner key: field name.
        Inner value: resampled 2-D array at that resolution.

    Raises
    ------
    ValueError
        If ``resolution_variants`` has fewer than 2 entries, or if any
        field in ``source_arrays`` is not 2-D.
    """
    if len(resolution_variants) < 2:
        raise ValueError(
            "resolution_variants must contain at least 2 entries; "
            f"got {len(resolution_variants)}."
        )

    if continuous_fields is None:
        continuous_fields = DEFAULT_CONTINUOUS_FIELDS
    if categorical_fields is None:
        categorical_fields = DEFAULT_CATEGORICAL_FIELDS

    # Validate that all source arrays are 2-D
    for field_name, arr in source_arrays.items():
        if arr.ndim != 2:
            raise ValueError(
                f"source_arrays['{field_name}'] must be a 2-D array; "
                f"got shape {arr.shape}."
            )

    min_lon, min_lat, max_lon, max_lat = native_extent
    lat_range = abs(max_lat - min_lat)
    lon_range = abs(max_lon - min_lon)

    output: dict[int, dict[str, np.ndarray]] = {}

    for target_res_m in resolution_variants:
        # Compute target grid shape from geographic extent and target resolution
        target_rows = max(1, round(lat_range * _METRES_PER_DEGREE / target_res_m))
        target_cols = max(1, round(lon_range * _METRES_PER_DEGREE / target_res_m))

        resampled: dict[str, np.ndarray] = {}

        for field_name, arr in source_arrays.items():
            src_rows, src_cols = arr.shape

            # Zoom factors: how much bigger/smaller is the output vs. input?
            row_factor = target_rows / src_rows
            col_factor = target_cols / src_cols

            if field_name in categorical_fields:
                # Nearest-neighbour: order=0
                resampled_arr = zoom(arr.astype(float), (row_factor, col_factor), order=0)
            else:
                # Bilinear: order=1  (default for all other/continuous fields)
                resampled_arr = zoom(arr.astype(float), (row_factor, col_factor), order=1)

            resampled[field_name] = resampled_arr

        output[target_res_m] = resampled

    return output


def compute_dataset_checksums(
    source_arrays: dict[str, np.ndarray],
) -> dict[str, str]:
    """Return a SHA-256 hex digest for each source array.

    Parameters
    ----------
    source_arrays:
        Mapping of field_name → numpy array (any shape).

    Returns
    -------
    dict[str, str]
        Mapping of field_name → 64-character SHA-256 hex digest.
    """
    return {
        field_name: hashlib.sha256(arr.tobytes()).hexdigest()
        for field_name, arr in source_arrays.items()
    }
