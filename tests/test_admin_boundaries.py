"""Unit tests for GADM admin boundary ingestion — sub-task 5.2.

Tests:
1. parse_gadm_features returns correct rows for all three MVP regions.
2. Features with missing GID_2 or NAME_2 are skipped.
3. Features with missing geometry are skipped.
4. CONSOLIDATED_FEATURES contains no admin boundary reference.
5. REGION_PROVINCE_FILTERS covers all three MVP regions.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from geosignal.admin_boundaries import (
    REGION_PROVINCE_FILTERS,
    download_gadm_boundaries,
    parse_gadm_features,
)
from geosignal.models import CONSOLIDATED_FEATURES

# ---------------------------------------------------------------------------
# Helpers — minimal fake GADM Feature dicts
# ---------------------------------------------------------------------------

_FAKE_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[120.0, -9.0], [120.1, -9.0], [120.1, -9.1], [120.0, -9.0]]],
}


def _make_feature(
    gid2: str | None,
    name2: str | None,
    name1: str,
    geometry: dict | None = _FAKE_GEOMETRY,
) -> dict:
    """Build a minimal GeoJSON Feature dict that mimics a GADM Level 2 record."""
    return {
        "type": "Feature",
        "properties": {
            "GID_2": gid2,
            "NAME_2": name2,
            "NAME_1": name1,
        },
        "geometry": geometry,
    }


# ---------------------------------------------------------------------------
# Test 1 & 2 & 3 — parse_gadm_features
# ---------------------------------------------------------------------------


class TestParseGadmFeatures(unittest.TestCase):
    """Tests for parse_gadm_features with mock GADM Feature dicts."""

    # ── NTT ──────────────────────────────────────────────────────────────────

    def test_ntt_returns_correct_row(self):
        features = [
            _make_feature("IDN.15.1_1", "Alor", "Nusa Tenggara Timur"),
        ]
        rows = parse_gadm_features(features, "ntt")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["kecamatan_id"], "IDN.15.1_1")
        self.assertEqual(row["kecamatan_name"], "Alor")
        self.assertEqual(row["region_id"], "ntt")
        self.assertEqual(row["boundary_geojson"], _FAKE_GEOMETRY)

    # ── NTB ──────────────────────────────────────────────────────────────────

    def test_ntb_returns_correct_row(self):
        features = [
            _make_feature("IDN.28.2_1", "Dompu", "Nusa Tenggara Barat"),
        ]
        rows = parse_gadm_features(features, "ntb")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["kecamatan_id"], "IDN.28.2_1")
        self.assertEqual(row["kecamatan_name"], "Dompu")
        self.assertEqual(row["region_id"], "ntb")
        self.assertEqual(row["boundary_geojson"], _FAKE_GEOMETRY)

    # ── Central Kalimantan ────────────────────────────────────────────────────

    def test_central_kalimantan_returns_correct_row(self):
        features = [
            _make_feature("IDN.5.1_1", "Barito Selatan", "Kalimantan Tengah"),
        ]
        rows = parse_gadm_features(features, "central_kalimantan")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["kecamatan_id"], "IDN.5.1_1")
        self.assertEqual(row["kecamatan_name"], "Barito Selatan")
        self.assertEqual(row["region_id"], "central_kalimantan")
        self.assertEqual(row["boundary_geojson"], _FAKE_GEOMETRY)

    # ── Multiple features → multiple rows ────────────────────────────────────

    def test_multiple_features_all_returned(self):
        features = [
            _make_feature("IDN.15.1_1", "Alor", "Nusa Tenggara Timur"),
            _make_feature("IDN.15.2_1", "Belu", "Nusa Tenggara Timur"),
            _make_feature("IDN.15.3_1", "Ende", "Nusa Tenggara Timur"),
        ]
        rows = parse_gadm_features(features, "ntt")
        self.assertEqual(len(rows), 3)
        ids = [r["kecamatan_id"] for r in rows]
        self.assertIn("IDN.15.1_1", ids)
        self.assertIn("IDN.15.2_1", ids)
        self.assertIn("IDN.15.3_1", ids)

    # ── Skip: missing GID_2 ───────────────────────────────────────────────────

    def test_missing_gid2_is_skipped(self):
        features = [
            _make_feature(None, "Alor", "Nusa Tenggara Timur"),
            _make_feature("IDN.15.2_1", "Belu", "Nusa Tenggara Timur"),
        ]
        rows = parse_gadm_features(features, "ntt")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kecamatan_id"], "IDN.15.2_1")

    def test_empty_gid2_is_skipped(self):
        features = [
            _make_feature("", "Alor", "Nusa Tenggara Timur"),
            _make_feature("IDN.15.2_1", "Belu", "Nusa Tenggara Timur"),
        ]
        rows = parse_gadm_features(features, "ntt")
        self.assertEqual(len(rows), 1)

    # ── Skip: missing NAME_2 ──────────────────────────────────────────────────

    def test_missing_name2_is_skipped(self):
        features = [
            _make_feature("IDN.15.1_1", None, "Nusa Tenggara Timur"),
            _make_feature("IDN.15.2_1", "Belu", "Nusa Tenggara Timur"),
        ]
        rows = parse_gadm_features(features, "ntt")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kecamatan_name"], "Belu")

    def test_empty_name2_is_skipped(self):
        features = [
            _make_feature("IDN.15.1_1", "", "Nusa Tenggara Timur"),
            _make_feature("IDN.15.2_1", "Belu", "Nusa Tenggara Timur"),
        ]
        rows = parse_gadm_features(features, "ntt")
        self.assertEqual(len(rows), 1)

    # ── Skip: missing geometry ────────────────────────────────────────────────

    def test_missing_geometry_is_skipped(self):
        features = [
            _make_feature("IDN.15.1_1", "Alor", "Nusa Tenggara Timur", geometry=None),
            _make_feature("IDN.15.2_1", "Belu", "Nusa Tenggara Timur"),
        ]
        rows = parse_gadm_features(features, "ntt")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kecamatan_id"], "IDN.15.2_1")

    # ── Empty input ───────────────────────────────────────────────────────────

    def test_empty_feature_list_returns_empty(self):
        rows = parse_gadm_features([], "ntt")
        self.assertEqual(rows, [])

    # ── All skipped ───────────────────────────────────────────────────────────

    def test_all_features_invalid_returns_empty(self):
        features = [
            _make_feature(None, None, "Nusa Tenggara Timur"),
            _make_feature("IDN.15.1_1", "Alor", "Nusa Tenggara Timur", geometry=None),
        ]
        rows = parse_gadm_features(features, "ntt")
        self.assertEqual(rows, [])


# ---------------------------------------------------------------------------
# Test 4 — CONSOLIDATED_FEATURES has no admin boundary reference
# ---------------------------------------------------------------------------

# Terms that must NOT appear (case-insensitive) in any CONSOLIDATED_FEATURES entry.
_ADMIN_BOUNDARY_TERMS = {
    "kecamatan",
    "kabupaten",
    "boundary",
    "admin",
    "NAME_1",
    "NAME_2",
    "GID_2",
}


class TestConsolidatedFeaturesNoAdminBoundaryReference(unittest.TestCase):
    """Assert CONSOLIDATED_FEATURES contains no admin boundary reference."""

    def test_no_admin_boundary_term_in_consolidated_features(self):
        violations = [
            feat
            for feat in CONSOLIDATED_FEATURES
            if any(term.lower() in feat.lower() for term in _ADMIN_BOUNDARY_TERMS)
        ]
        self.assertEqual(
            violations,
            [],
            msg=(
                "CONSOLIDATED_FEATURES must not contain any admin-boundary "
                f"identifier, but found violations: {violations}. "
                "Admin boundaries are a display/label layer only and must "
                "never be scoring inputs (Requirement 2.7)."
            ),
        )


# ---------------------------------------------------------------------------
# Test 5 — REGION_PROVINCE_FILTERS covers all three MVP regions
# ---------------------------------------------------------------------------


class TestRegionProvinceFiltersCoverage(unittest.TestCase):
    """Assert that all three MVP regions are present in REGION_PROVINCE_FILTERS."""

    def test_ntt_present(self):
        self.assertIn(
            "ntt",
            REGION_PROVINCE_FILTERS,
            "REGION_PROVINCE_FILTERS must have a key for 'ntt'.",
        )

    def test_ntb_present(self):
        self.assertIn(
            "ntb",
            REGION_PROVINCE_FILTERS,
            "REGION_PROVINCE_FILTERS must have a key for 'ntb'.",
        )

    def test_central_kalimantan_present(self):
        self.assertIn(
            "central_kalimantan",
            REGION_PROVINCE_FILTERS,
            "REGION_PROVINCE_FILTERS must have a key for 'central_kalimantan'.",
        )

    def test_all_three_regions_present_at_once(self):
        required = {"ntt", "ntb", "central_kalimantan"}
        missing = required - set(REGION_PROVINCE_FILTERS.keys())
        self.assertEqual(
            missing,
            set(),
            f"REGION_PROVINCE_FILTERS is missing regions: {missing}",
        )


# ---------------------------------------------------------------------------
# Test 6 — download_gadm_boundaries filters correctly (no real HTTP)
# ---------------------------------------------------------------------------


class TestDownloadGadmBoundaries(unittest.TestCase):
    """Tests for download_gadm_boundaries using mocked HTTP and a tmp cache."""

    def _make_fake_geojson(self) -> dict:
        """Build a minimal fake GADM FeatureCollection with features for all
        three regions plus one unrelated province."""
        return {
            "type": "FeatureCollection",
            "features": [
                _make_feature("IDN.15.1_1", "Alor", "Nusa Tenggara Timur"),
                _make_feature("IDN.15.2_1", "Belu", "Nusa Tenggara Timur"),
                _make_feature("IDN.28.1_1", "Bima", "Nusa Tenggara Barat"),
                _make_feature("IDN.5.1_1", "Barito Selatan", "Kalimantan Tengah"),
                _make_feature(
                    "IDN.99.1_1", "SomeCity", "Jawa Barat"
                ),  # unrelated
            ],
        }

    def test_filters_ntt_only(self, tmp_path=None):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_geojson = self._make_fake_geojson()

            with patch(
                "geosignal.admin_boundaries._http_get_json",
                return_value=fake_geojson,
            ):
                features = download_gadm_boundaries(
                    "ntt", cache_dir=tmp_dir
                )

        names = [f["properties"]["NAME_1"] for f in features]
        self.assertTrue(
            all("nusa tenggara timur" in n.lower() for n in names),
            f"Expected only NTT features but got NAME_1 values: {names}",
        )
        self.assertEqual(len(features), 2)

    def test_filters_ntb_only(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_geojson = self._make_fake_geojson()

            with patch(
                "geosignal.admin_boundaries._http_get_json",
                return_value=fake_geojson,
            ):
                features = download_gadm_boundaries(
                    "ntb", cache_dir=tmp_dir
                )

        self.assertEqual(len(features), 1)
        self.assertIn(
            "nusa tenggara barat",
            features[0]["properties"]["NAME_1"].lower(),
        )

    def test_filters_central_kalimantan_only(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_geojson = self._make_fake_geojson()

            with patch(
                "geosignal.admin_boundaries._http_get_json",
                return_value=fake_geojson,
            ):
                features = download_gadm_boundaries(
                    "central_kalimantan", cache_dir=tmp_dir
                )

        self.assertEqual(len(features), 1)
        self.assertIn(
            "kalimantan tengah",
            features[0]["properties"]["NAME_1"].lower(),
        )

    def test_uses_cache_on_second_call(self):
        """After the first download the file is cached; _http_get_json should
        not be called again for subsequent requests with the same cache_dir."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_geojson = self._make_fake_geojson()

            with patch(
                "geosignal.admin_boundaries._http_get_json",
                return_value=fake_geojson,
            ) as mock_http:
                # First call — should hit HTTP
                download_gadm_boundaries("ntt", cache_dir=tmp_dir)
                # Second call — should read from cache
                download_gadm_boundaries("ntb", cache_dir=tmp_dir)

            # HTTP should have been called exactly once
            self.assertEqual(mock_http.call_count, 1)

    def test_invalid_region_id_raises_value_error(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ValueError):
                download_gadm_boundaries("invalid_region", cache_dir=tmp_dir)


if __name__ == "__main__":
    unittest.main()
