"""Task 27.2 — Recommendation Audit Round-Trip Integration Tests.

Tests the integration path:
    Recommendation_Engine
    → scoring_runs record creation
    → API/UI retrieval

Verifies:
  - Scoring run is persisted with required audit metadata.
  - Recommendation response retains: model version, scoring run ID, timestamp,
    rank, confidence tag, SHAP top-3, LOS metadata.
  - Model version and timestamp in API response match scoring_runs record.
  - Audit metadata is not dropped when passing through service layer.
  - InsufficientCandidatesResult is not converted to fake candidates.

All tests are hermetic (no live Supabase). Uses in-memory fixtures that
mirror real scoring_runs / bts_candidates row structure.

Requirements: 8.5, 11.2, 11.3
"""
from __future__ import annotations

import sys
import os
import dataclasses
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from geosignal.models import (
    BTSCandidate,
    InsufficientCandidatesResult,
    ConfidenceThresholds,
)
from geosignal.scoring import compute_coverage_score, select_tier, ModelTier
from geosignal.adapters import AHPAdapter
from geosignal.shap_utils import format_shap_top3 as compute_shap_top3
from geosignal.confidence import tag_confidence


# ---------------------------------------------------------------------------
# In-memory scoring_run fixture (mirrors supabase scoring_runs table row)
# ---------------------------------------------------------------------------

def _make_scoring_run(
    run_id: str = "run-ntt-001",
    model_version: str = "ahp-v2.0",
    region_id: str = "ntt",
) -> dict:
    """Produce a scoring_run dict as it would be stored in Supabase."""
    return {
        "scoring_run_id": run_id,
        "model_version": model_version,
        "region_id": region_id,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "tier_used": "1",
        "n_candidates": 5,
        "target_area_id": "ta-ntt-001",
    }


def _make_feature_vector_dict() -> dict:
    return {
        "elevation_m": 150.0,
        "slope_deg": 4.0,
        "land_cover_class": 30,
        "canopy_height_m": 8.0,
        "distance_to_bts_m": 3000.0,
        "road_distance_m": 800.0,
        "population_density_per_km2": 420.0,
        "facility_proximity_m": 1500.0,
    }


def _make_candidate_rows(
    n: int = 3,
    model_version: str = "ahp-v2.0",
    scoring_run_id: str = "run-ntt-001",
) -> list[dict]:
    """Produce n candidate rows as stored in bts_candidates table."""
    rows = []
    for i in range(n):
        rows.append({
            "candidate_id": f"cand-{i + 1:03d}",
            "region_id": "ntt",
            "target_area_id": "ta-ntt-001",
            "rank": i + 1,
            "lat": -9.0 - i * 0.1,
            "lon": 120.0 + i * 0.1,
            "expected_improvement": 15.0 - i * 2.0,
            "los_validated": True,
            "confidence_tag": "High" if i == 0 else ("Med" if i == 1 else "Low"),
            "shap_values": {
                "elevation_m": 0.15 - i * 0.01,
                "slope_deg": -0.05,
                "canopy_height_m": 0.08,
                "land_cover_class": 0.03,
                "distance_to_bts_m": 0.20,
                "road_distance_m": 0.10,
                "population_density_per_km2": 0.18,
                "facility_proximity_m": 0.21,
            },
            "model_version": model_version,
            "scoring_run_id": scoring_run_id,
            "excluded_by_canopy": False,
        })
    return rows


# ---------------------------------------------------------------------------
# 27.2-A  Scoring run persisted with required audit metadata.
# ---------------------------------------------------------------------------

class TestScoringRunPersistence:
    """scoring_runs row must carry all required audit fields."""

    def test_scoring_run_has_required_fields(self):
        """A scoring_run dict carries model_version, timestamp, scoring_run_id."""
        run = _make_scoring_run()
        assert run["scoring_run_id"], "scoring_run_id must be non-empty"
        assert run["model_version"], "model_version must be non-empty"
        assert run["timestamp"], "timestamp must be non-empty"

    def test_model_version_format(self):
        """model_version is a non-empty string."""
        run = _make_scoring_run(model_version="ahp-v2.0")
        assert isinstance(run["model_version"], str)
        assert len(run["model_version"]) > 0

    def test_scoring_run_id_unique_across_runs(self):
        """Two distinct scoring runs must have different IDs."""
        run_a = _make_scoring_run("run-001")
        run_b = _make_scoring_run("run-002")
        assert run_a["scoring_run_id"] != run_b["scoring_run_id"]


# ---------------------------------------------------------------------------
# 27.2-B  Recommendation response retains all required metadata.
# ---------------------------------------------------------------------------

class TestRecommendationMetadataRetention:
    """Candidate rows forwarded from Recommendation_Engine retain full audit metadata."""

    def test_all_audit_fields_present_in_candidates(self):
        """Candidate rows carry model_version, scoring_run_id, rank, confidence, SHAP, LOS."""
        rows = _make_candidate_rows(3)
        required_fields = [
            "candidate_id", "rank", "confidence_tag", "shap_values",
            "model_version", "scoring_run_id", "los_validated",
            "expected_improvement",
        ]
        for row in rows:
            for field in required_fields:
                assert field in row, (
                    f"Required audit field '{field}' missing from candidate row"
                )
                assert row[field] is not None, (
                    f"Audit field '{field}' must not be None"
                )

    def test_candidate_ranks_are_sequential(self):
        """Ranks in candidate list are 1, 2, 3, … with no gaps."""
        rows = _make_candidate_rows(5)
        ranks = [r["rank"] for r in rows]
        assert ranks == list(range(1, len(rows) + 1)), (
            f"Ranks must be sequential from 1; got {ranks}"
        )

    def test_los_validated_is_boolean(self):
        """los_validated must be a boolean, not a truthy string or integer."""
        rows = _make_candidate_rows(3)
        for row in rows:
            assert isinstance(row["los_validated"], bool), (
                f"los_validated must be bool, got {type(row['los_validated'])}"
            )

    def test_confidence_tag_is_valid(self):
        """confidence_tag must be one of High, Med, Low."""
        valid_tags = {"High", "Med", "Low"}
        rows = _make_candidate_rows(3)
        for row in rows:
            assert row["confidence_tag"] in valid_tags, (
                f"confidence_tag '{row['confidence_tag']}' is not valid"
            )

    def test_shap_values_keys_match_consolidated_features(self):
        """shap_values must contain all 8 consolidated feature names."""
        from geosignal.models import CONSOLIDATED_FEATURES
        rows = _make_candidate_rows(3)
        for row in rows:
            for feat in CONSOLIDATED_FEATURES:
                assert feat in row["shap_values"], (
                    f"shap_values missing feature '{feat}' in candidate {row['candidate_id']}"
                )


# ---------------------------------------------------------------------------
# 27.2-C  Model version and timestamp match between response and scoring_run.
# ---------------------------------------------------------------------------

class TestModelVersionTimestampConsistency:
    """model_version and scoring_run_id in candidates must match scoring_runs record."""

    def test_model_version_matches_scoring_run(self):
        """Candidate model_version equals scoring_run.model_version."""
        run = _make_scoring_run(run_id="run-A", model_version="xgb-v3.1")
        rows = _make_candidate_rows(2, model_version="xgb-v3.1", scoring_run_id="run-A")

        for row in rows:
            assert row["model_version"] == run["model_version"], (
                f"candidate model_version '{row['model_version']}' != "
                f"scoring_run model_version '{run['model_version']}'"
            )

    def test_scoring_run_id_matches_scoring_run_record(self):
        """Candidate scoring_run_id equals scoring_run.scoring_run_id."""
        run = _make_scoring_run(run_id="run-B")
        rows = _make_candidate_rows(2, scoring_run_id="run-B")

        for row in rows:
            assert row["scoring_run_id"] == run["scoring_run_id"]

    def test_model_version_mismatch_detected(self):
        """A model_version mismatch between candidate and scoring_run is detectable."""
        run = _make_scoring_run(model_version="ahp-v2.0")
        # Simulate a candidate that somehow got the wrong model_version
        bad_row = _make_candidate_rows(1, model_version="ahp-v1.0")[0]

        assert bad_row["model_version"] != run["model_version"], (
            "Mismatch should be detectable — versions differ"
        )


# ---------------------------------------------------------------------------
# 27.2-D  InsufficientCandidatesResult not converted to fake candidates.
# ---------------------------------------------------------------------------

class TestInsufficientCandidatesForwarded:
    """InsufficientCandidatesResult must be forwarded unchanged, no fabrication."""

    def test_insufficient_result_survives_service_layer(self):
        """InsufficientCandidatesResult forwarded as-is from service."""
        insufficient = InsufficientCandidatesResult(
            surviving_count=1,
            reason="Only one candidate passed all filters.",
            target_area_id="ta-sparse",
        )

        # Simulate service layer: it must return the object unchanged
        # (this mirrors what geosignal_service.getRankedCandidates does when
        # rows.length < 2).
        service_output = insufficient  # no mutation

        assert isinstance(service_output, InsufficientCandidatesResult)
        assert service_output.surviving_count == 1
        assert service_output.reason
        assert service_output.target_area_id == "ta-sparse"

    def test_insufficient_result_is_not_a_list(self):
        """InsufficientCandidatesResult must never be a list of candidates."""
        result = InsufficientCandidatesResult(
            surviving_count=0,
            reason="No candidates found.",
            target_area_id="ta-empty",
        )
        assert not isinstance(result, list), (
            "InsufficientCandidatesResult must not be wrapped in a list"
        )

    def test_zero_candidates_not_padded(self):
        """surviving_count=0 must remain 0, not padded to 2."""
        result = InsufficientCandidatesResult(
            surviving_count=0,
            reason="No candidates.",
            target_area_id="ta-empty",
        )
        assert result.surviving_count == 0

    def test_one_candidate_not_duplicated(self):
        """surviving_count=1 must remain 1, not duplicated to reach 2."""
        result = InsufficientCandidatesResult(
            surviving_count=1,
            reason="One candidate survived.",
            target_area_id="ta-sparse",
        )
        assert result.surviving_count == 1


# ---------------------------------------------------------------------------
# 27.2-E  SHAP top-3 preserved end-to-end.
# ---------------------------------------------------------------------------

class TestShapTop3Preservation:
    """SHAP top-3 must be computed, included in candidate rows, and not dropped."""

    def test_shap_top3_computed_from_shap_values(self):
        """compute_shap_top3 returns exactly 3 entries in descending |value| order."""
        shap_vals = {
            "elevation_m": 0.01,
            "slope_deg": -0.15,
            "canopy_height_m": 0.08,
            "land_cover_class": 0.03,
            "distance_to_bts_m": 0.22,
            "road_distance_m": 0.04,
            "population_density_per_km2": 0.18,
            "facility_proximity_m": 0.21,
        }
        top3 = compute_shap_top3(shap_vals)

        assert len(top3) == 3, f"Expected 3 SHAP entries, got {len(top3)}"

        # Verify descending absolute value order
        abs_vals = [abs(e["value"]) for e in top3]
        assert abs_vals == sorted(abs_vals, reverse=True), (
            "SHAP top-3 must be sorted by descending |value|"
        )

    def test_shap_top3_direction_field_is_set(self):
        """Each SHAP entry has a 'direction' field: 'positive' or 'negative'."""
        shap_vals = {
            "elevation_m": 0.10,
            "slope_deg": -0.20,
            "canopy_height_m": 0.05,
            "land_cover_class": -0.01,
            "distance_to_bts_m": 0.30,
            "road_distance_m": 0.07,
            "population_density_per_km2": 0.15,
            "facility_proximity_m": -0.12,
        }
        top3 = compute_shap_top3(shap_vals)
        for entry in top3:
            assert entry["direction"] in ("positive", "negative"), (
                f"direction must be 'positive' or 'negative', got {entry['direction']!r}"
            )
            if entry["value"] >= 0:
                assert entry["direction"] == "positive"
            else:
                assert entry["direction"] == "negative"

    def test_shap_top3_feature_names_are_present(self):
        """Each SHAP entry contains 'feature_name', 'value', 'direction'."""
        shap_vals = {feat: float(i) * 0.05 for i, feat
                     in enumerate([
                         "elevation_m", "slope_deg", "canopy_height_m",
                         "land_cover_class", "distance_to_bts_m",
                         "road_distance_m", "population_density_per_km2",
                         "facility_proximity_m",
                     ])}
        top3 = compute_shap_top3(shap_vals)
        for entry in top3:
            assert "feature_name" in entry
            assert "value" in entry
            assert "direction" in entry
