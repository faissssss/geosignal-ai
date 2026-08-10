"""GeoSignal AI — GADM Level 2 administrative boundary ingestion.

This module downloads, caches, filters, parses, and upserts GADM Level 2
(kabupaten/kecamatan) boundary polygons for the three MVP/validation regions
(NTT, NTB, Central Kalimantan).

IMPORTANT CONSTRAINTS:
- GADM boundaries are a labeling/display layer ONLY.
- They are NEVER used as Coverage Score inputs.
- Do NOT import CONSOLIDATED_FEATURES from models.py — it is irrelevant here.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Region → GADM province name filter
# ---------------------------------------------------------------------------

# Maps the project's region_id strings to the GADM NAME_1 (province) value used
# in the Indonesia Level 2 GeoJSON.  Matching is case-insensitive substring.
REGION_PROVINCE_FILTERS: dict[str, str] = {
    "ntt": "nusatenggaratimur",
    "ntb": "nusatenggarabarat",
    "central_kalimantan": "kalimantantengah",
}

# GADM 4.1 Level 2 Indonesia — full province-level file (~50 MB).
# Exposed as a module-level constant so tests can monkeypatch it easily.
GADM_IDN_LEVEL2_URL: str = (
    "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_IDN_2.json"
)
_DEFAULT_CACHE_FILENAME = "gadm41_IDN_2.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def download_gadm_boundaries(
    region_id: str,
    cache_dir: str = "data/gadm_cache",
    url: str = GADM_IDN_LEVEL2_URL,
) -> list[dict]:
    """Download (or load from cache) GADM 4.1 Level 2 Indonesia and return
    features matching *region_id*.

    Parameters
    ----------
    region_id:
        One of ``"ntt"``, ``"ntb"``, or ``"central_kalimantan"``.
    cache_dir:
        Local directory used to cache the full Indonesia GeoJSON file.
        The directory is created automatically if it does not exist.
    url:
        URL of the GADM file.  Override in tests to avoid real HTTP calls.

    Returns
    -------
    list[dict]
        GeoJSON Feature dicts whose ``properties.NAME_1`` matches the province
        filter for *region_id* (case-insensitive substring).
    """
    if region_id not in REGION_PROVINCE_FILTERS:
        raise ValueError(
            f"Unknown region_id '{region_id}'. "
            f"Valid values: {list(REGION_PROVINCE_FILTERS.keys())}"
        )

    province_filter = REGION_PROVINCE_FILTERS[region_id]

    # ── Ensure cache directory exists ────────────────────────────────────────
    cache_path = Path(cache_dir) / _DEFAULT_CACHE_FILENAME
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Load or download the full Indonesia file ──────────────────────────────
    if cache_path.exists():
        logger.info("Loading GADM data from cache: %s", cache_path)
        with cache_path.open("r", encoding="utf-8") as fh:
            geojson = json.load(fh)
    else:
        logger.info(
            "Cache miss — downloading GADM Level 2 Indonesia from %s", url
        )
        geojson = _http_get_json(url)
        with cache_path.open("w", encoding="utf-8") as fh:
            json.dump(geojson, fh)
        logger.info("GADM data cached to %s", cache_path)

    # ── Filter features to the requested province ─────────────────────────────
    all_features: list[dict] = geojson.get("features", [])
    matched: list[dict] = [
        f
        for f in all_features
        if province_filter
        in (f.get("properties", {}).get("NAME_1") or "").replace(" ", "").lower()
    ]

    logger.info(
        "Region '%s': %d features matched province filter '%s' (from %d total)",
        region_id,
        len(matched),
        province_filter,
        len(all_features),
    )
    return matched


def parse_gadm_features(features: list[dict], region_id: str) -> list[dict]:
    """Convert raw GADM Feature dicts to ``admin_boundaries`` table row format.

    Parameters
    ----------
    features:
        List of GeoJSON Feature dicts (already filtered to a single province).
    region_id:
        The project region identifier (e.g. ``"ntt"``).

    Returns
    -------
    list[dict]
        Each dict has the keys required by the ``admin_boundaries`` table:
        ``kecamatan_id``, ``kecamatan_name``, ``region_id``,
        ``boundary_geojson``.  Features with missing/null ``GID_2``,
        ``NAME_2``, or geometry are skipped (each skip is logged).
    """
    rows: list[dict] = []

    for feature in features:
        props: dict[str, Any] = feature.get("properties") or {}
        geometry: dict | None = feature.get("geometry")

        gid2: str | None = props.get("GID_2")
        name2: str | None = props.get("NAME_2")

        # ── Validate required fields ──────────────────────────────────────────
        if not gid2:
            logger.warning(
                "Skipping feature: missing or null GID_2 (NAME_2=%r, region_id=%r)",
                name2,
                region_id,
            )
            continue

        if not name2:
            logger.warning(
                "Skipping feature: missing or null NAME_2 (GID_2=%r, region_id=%r)",
                gid2,
                region_id,
            )
            continue

        if not geometry:
            logger.warning(
                "Skipping feature: missing or null geometry "
                "(GID_2=%r, NAME_2=%r, region_id=%r)",
                gid2,
                name2,
                region_id,
            )
            continue

        rows.append(
            {
                "kecamatan_id": str(gid2),
                "kecamatan_name": str(name2),
                "region_id": region_id,
                "boundary_geojson": geometry,
            }
        )

    logger.debug(
        "parse_gadm_features: %d rows parsed, %d features skipped (region_id=%r)",
        len(rows),
        len(features) - len(rows),
        region_id,
    )
    return rows


def ingest_admin_boundaries(
    region_id: str,
    supabase_client=None,
    cache_dir: str = "data/gadm_cache",
) -> list[dict]:
    """Download, parse, and optionally upsert GADM Level 2 boundaries.

    Parameters
    ----------
    region_id:
        One of ``"ntt"``, ``"ntb"``, or ``"central_kalimantan"``.
    supabase_client:
        An initialised ``supabase.Client`` instance.  When ``None``
        (offline / test mode) the parsed rows are returned without any
        database writes.
    cache_dir:
        Local cache directory for the raw GADM GeoJSON file.

    Returns
    -------
    list[dict]
        Parsed boundary rows in ``admin_boundaries`` table format.
    """
    features = download_gadm_boundaries(region_id, cache_dir=cache_dir)
    rows = parse_gadm_features(features, region_id)

    if supabase_client is not None:
        logger.info(
            "Upserting %d admin boundary rows for region '%s' …",
            len(rows),
            region_id,
        )
        # Upsert on kecamatan_id (the UNIQUE constraint on the table).
        (
            supabase_client.table("admin_boundaries")
            .upsert(rows, on_conflict="kecamatan_id")
            .execute()
        )
        logger.info(
            "Upserted %d admin boundaries for region '%s'.",
            len(rows),
            region_id,
        )
    else:
        logger.info(
            "Offline mode — skipping DB upsert. "
            "Returning %d parsed rows for region '%s'.",
            len(rows),
            region_id,
        )

    logger.info(
        "ingest_admin_boundaries complete: %d boundaries ingested for region '%s'.",
        len(rows),
        region_id,
    )
    return rows


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _http_get_json(url: str) -> dict:
    """Fetch *url* and return the parsed JSON body.

    Tries ``requests`` first (it is a transitive dependency of ``supabase``);
    falls back to ``urllib.request`` from the stdlib if ``requests`` is not
    importable.
    """
    try:
        import requests  # type: ignore[import-untyped]

        resp = requests.get(url, timeout=300)
        resp.raise_for_status()
        return resp.json()
    except ImportError:
        pass

    # stdlib fallback
    import urllib.request

    with urllib.request.urlopen(url, timeout=300) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))
