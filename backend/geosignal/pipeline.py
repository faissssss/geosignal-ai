"""GeoSignal AI — Data_Pipeline: geometry QC and attribute range validation.

Public API
----------
run_pipeline(region_boundary, resolution_variants, output_bucket) -> DataQualityReport
run_geometry_qc(features) -> (cleaned_features, correction_log)
run_attribute_validation(features, bounds_config) -> (valid, flagged, validation_log)

All source-specific paths and attribute bounds are parameterised — no region
names or file paths are hard-coded in core logic (Requirement 1.6 / 13.1).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from shapely.geometry import mapping, shape
from shapely.validation import make_valid

from geosignal.harmonisation import compute_dataset_checksums, harmonise_rasters
from geosignal.models import ConfidenceThresholds, DataQualityReport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default attribute bounds — Indonesia-scoped (Requirement 1.3)
# Override by passing bounds_config to run_attribute_validation.
# ---------------------------------------------------------------------------

DEFAULT_ATTRIBUTE_BOUNDS: dict[str, dict[str, Any]] = {
    "elevation_m": {
        "min": -11.0,   # Java coastal lowland / reclaimed-land floor
        "max": 4884.0,  # Puncak Jaya, Papua — Indonesia's highest point
    },
    "population_density_per_km2": {
        "max": 1_000_000,  # flag if > 1 000 000 per km²
    },
    "canopy_height_m": {
        "min": 0.0,    # flag if < 0
        "max": 100.0,  # flag if > 100
    },
}


# ---------------------------------------------------------------------------
# Geometry QC (sub-task 3.2)
# ---------------------------------------------------------------------------

def run_geometry_qc(
    features: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Remove or repair invalid geometries in a list of GeoJSON Feature dicts.

    Parameters
    ----------
    features:
        List of GeoJSON Feature dicts (each has at least a ``"geometry"`` key).

    Returns
    -------
    cleaned_features:
        Feature dicts that passed QC (including repaired ones).
    correction_log:
        One dict per correction with keys ``source``, ``feature_id``,
        ``action`` (``"removed"`` or ``"repaired"``).
    """
    cleaned: list[dict] = []
    correction_log: list[dict] = []

    for feature in features:
        feature_id = _get_feature_id(feature)
        geom_dict = feature.get("geometry")

        # ── Remove null / empty geometries ──────────────────────────────────
        if not geom_dict:
            logger.info(
                "Removing feature %s: null or empty geometry.", feature_id
            )
            correction_log.append(
                {"source": "geometry_qc", "feature_id": feature_id, "action": "removed"}
            )
            continue

        # ── Attempt to parse with Shapely ────────────────────────────────────
        try:
            geom = shape(geom_dict)
        except Exception as exc:
            logger.warning(
                "Removing feature %s: cannot parse geometry (%s).", feature_id, exc
            )
            correction_log.append(
                {"source": "geometry_qc", "feature_id": feature_id, "action": "removed"}
            )
            continue

        # ── Remove empty Shapely geometries ──────────────────────────────────
        if geom.is_empty:
            logger.info(
                "Removing feature %s: empty geometry after parsing.", feature_id
            )
            correction_log.append(
                {"source": "geometry_qc", "feature_id": feature_id, "action": "removed"}
            )
            continue

        # ── Repair self-intersecting geometries via buffer(0) ────────────────
        if not geom.is_valid:
            repaired = geom.buffer(0)
            if repaired.is_empty:
                # Fallback: try make_valid; if still empty, remove
                repaired = make_valid(geom)

            if repaired.is_empty:
                logger.info(
                    "Removing feature %s: self-intersecting geometry; "
                    "repair produced empty geometry.",
                    feature_id,
                )
                correction_log.append(
                    {"source": "geometry_qc", "feature_id": feature_id, "action": "removed"}
                )
                continue

            logger.info(
                "Repaired feature %s: self-intersecting polygon fixed via buffer(0).",
                feature_id,
            )
            correction_log.append(
                {"source": "geometry_qc", "feature_id": feature_id, "action": "repaired"}
            )
            # Rewrite the geometry in the feature copy
            feature = {**feature, "geometry": mapping(repaired)}

        cleaned.append(feature)

    return cleaned, correction_log


def _get_feature_id(feature: dict) -> str:
    """Extract a stable ID from a GeoJSON Feature, falling back to ``"unknown"``."""
    # Try top-level "id" first (RFC 7946 standard)
    if "id" in feature:
        return str(feature["id"])
    # Try properties.id
    props = feature.get("properties") or {}
    if "id" in props:
        return str(props["id"])
    # Try properties.feature_id
    if "feature_id" in props:
        return str(props["feature_id"])
    return "unknown"


# ---------------------------------------------------------------------------
# Attribute range validation (sub-task 3.4)
# ---------------------------------------------------------------------------

def run_attribute_validation(
    features: list[dict],
    bounds_config: dict | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Apply Indonesia-scoped attribute range checks to a list of GeoJSON Features.

    Parameters
    ----------
    features:
        List of GeoJSON Feature dicts whose ``properties`` are validated.
    bounds_config:
        Optional override for ``DEFAULT_ATTRIBUTE_BOUNDS``.  Keys must match
        the same structure.  Unknown keys are silently accepted (they extend
        the bounds dict, not replace it).

    Returns
    -------
    valid_features:
        Features where all *known* attributes are in range.
    flagged_features:
        Features with at least one out-of-range known attribute.
    validation_log:
        One dict per violation with keys ``feature_id``, ``field``,
        ``value``, ``reason``.
    """
    bounds = {**DEFAULT_ATTRIBUTE_BOUNDS}
    if bounds_config:
        bounds.update(bounds_config)

    valid_features: list[dict] = []
    flagged_features: list[dict] = []
    validation_log: list[dict] = []

    for feature in features:
        feature_id = _get_feature_id(feature)
        props = feature.get("properties") or {}
        feature_violations: list[dict] = []

        for field_name, value in props.items():
            if field_name not in bounds:
                # Unknown field — warn but do NOT flag
                logger.warning(
                    "Feature %s: unknown field '%s' encountered during attribute "
                    "validation; skipping.",
                    feature_id,
                    field_name,
                )
                continue

            if value is None:
                continue

            field_bounds = bounds[field_name]
            low = field_bounds.get("min")
            high = field_bounds.get("max")

            if low is not None and value < low:
                reason = (
                    f"{field_name} value {value!r} is below the minimum "
                    f"allowed value of {low}."
                )
                feature_violations.append(
                    {
                        "feature_id": feature_id,
                        "field": field_name,
                        "value": value,
                        "reason": reason,
                    }
                )

            if high is not None and value > high:
                reason = (
                    f"{field_name} value {value!r} exceeds the maximum "
                    f"allowed value of {high}."
                )
                feature_violations.append(
                    {
                        "feature_id": feature_id,
                        "field": field_name,
                        "value": value,
                        "reason": reason,
                    }
                )

        if feature_violations:
            flagged_features.append(feature)
            validation_log.extend(feature_violations)
        else:
            valid_features.append(feature)

    return valid_features, flagged_features, validation_log


# ---------------------------------------------------------------------------
# Pipeline entry point (sub-task 3.1)
# ---------------------------------------------------------------------------

def run_pipeline(
    region_boundary: dict,
    resolution_variants: list[int],
    output_bucket: str,
    config: dict | None = None,
) -> DataQualityReport:
    """Orchestrate the Data_Pipeline for a given region boundary.

    Parameters
    ----------
    region_boundary:
        GeoJSON FeatureCollection or Feature (polygon) describing the region.
    resolution_variants:
        List of ≥2 grid sizes in metres, e.g. ``[100, 250]``.
    output_bucket:
        GCS / Supabase Storage path where processed outputs are written
        (stored in the returned DataQualityReport).
    config:
        Optional configuration dict.  Supported keys:
        - ``"bounds_config"`` (dict): attribute bounds overrides.
        - ``"source_features"`` (list[dict]): pre-loaded GeoJSON features to
          process; if absent, an empty list is used (stub behaviour).

    Returns
    -------
    DataQualityReport
        Summary report with all required fields populated.

    Notes
    -----
    GEE export is currently a *stub* — it logs an info message and does not
    contact the Earth Engine API.  Real GEE calls will be added once
    credentials are available.
    """
    if config is None:
        config = {}

    # ── Derive region_id from boundary properties ─────────────────────────
    region_id = _derive_region_id(region_boundary)

    # ── Load source features (stub: use config-provided list or empty) ────
    source_features: list[dict] = config.get("source_features", [])
    input_count = len(source_features)

    # ── Step 1: Geometry QC ───────────────────────────────────────────────
    cleaned_features, geom_log = run_geometry_qc(source_features)

    removed_by_geom = sum(1 for e in geom_log if e["action"] == "removed")
    repaired_by_geom = sum(1 for e in geom_log if e["action"] == "repaired")

    # ── Step 2: Attribute range validation ───────────────────────────────
    bounds_config = config.get("bounds_config", None)
    valid_features, flagged_features, validation_log = run_attribute_validation(
        cleaned_features, bounds_config=bounds_config
    )

    anomalous_count = len(flagged_features)

    # ── Step 3: Multi-resolution harmonisation and checksum computation ──
    # If source raster arrays are provided in the config, resample them to
    # all resolution variants and compute SHA-256 checksums per field.
    # (Requirement 1.4 / 1.5; Task 4.1 / 4.3)
    source_arrays: dict | None = config.get("source_arrays", None)
    dataset_checksums: dict[str, str] = {}

    if source_arrays:
        # Default extent: fallback to a zero-size extent if not supplied, so
        # tests can pass arbitrary extents via config.
        native_extent: tuple[float, float, float, float] = config.get(
            "native_extent", (106.0, -6.5, 107.0, -5.5)
        )
        native_crs: str = config.get("native_crs", "EPSG:4326")

        # Harmonise to all requested resolutions (minimum 2 required by spec).
        # We pass the resolution_variants list directly; harmonise_rasters
        # validates that len >= 2 internally.
        harmonise_rasters(
            source_arrays=source_arrays,
            native_crs=native_crs,
            native_extent=native_extent,
            resolution_variants=resolution_variants,
        )

        # Compute SHA-256 checksums for each source array.
        dataset_checksums = compute_dataset_checksums(source_arrays)

    # ── Step 4: GEE export stub ───────────────────────────────────────────
    # Export only processed, anonymised outputs — never raw crowd-sourced
    # records (Property 26 / Requirement 12.2).
    logger.info(
        "[GEE export stub] Would export %d anonymised features to bucket '%s'. "
        "Real GEE export will be enabled once credentials are available.",
        len(valid_features),
        output_bucket,
    )

    # ── Build and return the DataQualityReport ───────────────────────────
    return DataQualityReport(
        region_id=region_id,
        input_record_counts={"total": input_count},
        removed_records={"geometry_qc": removed_by_geom},
        repaired_records={"geometry_qc": repaired_by_geom},
        anomalous_records={"attribute_validation": anomalous_count},
        chosen_resolution_m=resolution_variants[0],
        confidence_thresholds=ConfidenceThresholds(),
        dataset_checksums=dataset_checksums,
        timestamp=datetime.now(tz=timezone.utc),
    )


def _derive_region_id(region_boundary: dict) -> str:
    """Extract a region identifier from a GeoJSON Feature or FeatureCollection.

    Falls back to ``"unknown"`` when no id/name property is present.
    """
    if not region_boundary:
        return "unknown"

    geom_type = region_boundary.get("type", "")

    # FeatureCollection: try first feature's properties
    if geom_type == "FeatureCollection":
        features = region_boundary.get("features", [])
        if features:
            return _extract_id_from_feature(features[0])
        return "unknown"

    # Feature: try its properties directly
    if geom_type == "Feature":
        return _extract_id_from_feature(region_boundary)

    # Plain geometry or unknown shape — nothing useful to extract
    return "unknown"


def _extract_id_from_feature(feature: dict) -> str:
    """Extract an id string from a GeoJSON Feature dict."""
    # RFC 7946 top-level id
    if "id" in feature:
        return str(feature["id"])
    props = feature.get("properties") or {}
    for key in ("region_id", "id", "name", "NAME", "ADM1_EN"):
        if key in props and props[key]:
            return str(props[key])
    return "unknown"
