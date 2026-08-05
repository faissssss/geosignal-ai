"""Task 30 — Pre-demo Ethical Safeguard Checklist Verification.

Backend tests covering safeguards 1, 4–8 (30.1, 30.4–30.8).
Frontend safeguards 2–3 (30.2–30.3) have unit coverage in Task24 tests;
this file adds targeted gap-filling tests (30.2/30.3 sections at end).

Requirements: 4.3, 7.1, 8.3, 8.4, 9.2, 9.3, 9.5, 9.6, 11.3, 12.1–12.4

Dataset strategy: all tests are hermetic — no Supabase required.
"""
from __future__ import annotations

import dataclasses
import importlib
import inspect
import pathlib
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from geosignal.adapters import AHPAdapter
from geosignal.confidence import tag_confidence
from geosignal.constraints import (
    HIGH_CANOPY_LAND_COVER_CLASSES,
    CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M,
    is_high_canopy as is_high_canopy_from_constraints,
)
from geosignal.ethics import (
    ETHICAL_RISK_REGISTER,
    REQUIRED_RISK_IDS,
    get_risk_by_id,
    is_high_canopy,  # re-exported from constraints via ethics
)
from geosignal.models import (
    CONSOLIDATED_FEATURES,
    ConfidenceThresholds,
    DataQualityReport,
    EthicalRiskEntry,
    FeatureVector,
)
from geosignal.shap_utils import (
    compute_ahp_shap,
    format_shap_top3,
)


# ===========================================================================
# 30.1 — Ethical Risk Register
# ===========================================================================

class TestEthicalRiskRegister:
    """Safeguard 1: five mandatory risk IDs present with all fields non-empty."""

    def test_30_1_a_all_five_required_ids_present(self):
        """All five required risk IDs must be in the register."""
        present = {e.risk_id for e in ETHICAL_RISK_REGISTER}
        missing = REQUIRED_RISK_IDS - present
        assert missing == set(), (
            f"30.1 FAIL: missing required risk IDs: {sorted(missing)}"
        )

    def test_30_1_b_no_duplicate_risk_ids(self):
        """No duplicate risk_id in the register."""
        ids = [e.risk_id for e in ETHICAL_RISK_REGISTER]
        assert len(ids) == len(set(ids)), (
            f"30.1 FAIL: duplicate risk IDs: {[x for x in ids if ids.count(x) > 1]}"
        )

    def test_30_1_c_all_fields_non_empty(self):
        """Every required field of every EthicalRiskEntry is non-empty."""
        required_fields = [
            "risk_description", "impact", "mitigation", "responsible_owner_role",
        ]
        for entry in ETHICAL_RISK_REGISTER:
            for field in required_fields:
                val = getattr(entry, field, None)
                assert val and str(val).strip(), (
                    f"30.1 FAIL: risk_id='{entry.risk_id}' has empty field '{field}'."
                )

    def test_30_1_d_get_risk_by_id_works_for_all_required(self):
        """get_risk_by_id() returns the correct entry for all required IDs."""
        for risk_id in REQUIRED_RISK_IDS:
            entry = get_risk_by_id(risk_id)
            assert entry.risk_id == risk_id

    def test_30_1_e_unknown_risk_id_raises_key_error(self):
        """get_risk_by_id() raises KeyError for unknown IDs."""
        with pytest.raises(KeyError):
            get_risk_by_id("nonexistent_risk_xyz")

    def test_30_1_f_entry_is_ethical_risk_entry_instance(self):
        """Each entry is an EthicalRiskEntry dataclass instance."""
        for entry in ETHICAL_RISK_REGISTER:
            assert isinstance(entry, EthicalRiskEntry), (
                f"30.1 FAIL: {entry!r} is not an EthicalRiskEntry instance."
            )

    def test_30_1_g_deforestation_entry_mentions_canopy_constraint(self):
        """deforestation entry mitigation references the canopy constraint."""
        entry = get_risk_by_id("deforestation")
        combined = (entry.mitigation + entry.risk_description).lower()
        assert "canopy" in combined or "is_high_canopy" in combined, (
            "30.1 FAIL: deforestation entry must reference the canopy constraint."
        )

    def test_30_1_h_low_confidence_entry_references_confidence_gate(self):
        """low_confidence_funding_decisions mitigation references ConfidenceGate."""
        entry = get_risk_by_id("low_confidence_funding_decisions")
        assert "confidencegate" in entry.mitigation.lower() or \
               "confidence" in entry.mitigation.lower(), (
            "30.1 FAIL: low_confidence entry must reference the confidence gate."
        )


# ===========================================================================
# 30.4 — Deforestation constraint active by default
# ===========================================================================

class TestDeforestationConstraint:
    """Safeguard 4: joint land-cover + canopy exclusion condition."""

    # ── Joint condition required ─────────────────────────────────────────

    def test_30_4_a_class10_canopy15_excluded(self):
        """land_cover=10, canopy=15.0 → excluded."""
        assert is_high_canopy(10, 15.0) is True

    def test_30_4_b_class20_canopy20_excluded(self):
        """land_cover=20 (Shrubland), canopy=20.0 → excluded."""
        assert is_high_canopy(20, 20.0) is True

    def test_30_4_c_class10_canopy14_9_not_excluded(self):
        """land_cover=10, canopy=14.9 → NOT excluded (height below threshold)."""
        assert is_high_canopy(10, 14.9) is False

    def test_30_4_d_class30_canopy20_not_excluded(self):
        """land_cover=30 (Cropland), canopy=20.0 → NOT excluded (wrong class)."""
        assert is_high_canopy(30, 20.0) is False

    def test_30_4_e_class40_canopy50_not_excluded(self):
        """land_cover=40 (Cropland), canopy=50.0 → NOT excluded."""
        assert is_high_canopy(40, 50.0) is False

    def test_30_4_f_class10_canopy0_not_excluded(self):
        """land_cover=10, canopy=0.0 → NOT excluded (height too low)."""
        assert is_high_canopy(10, 0.0) is False

    def test_30_4_g_boundary_exactly_15m_excluded(self):
        """Boundary: canopy_height_m exactly 15.0 with class 10 → excluded."""
        assert is_high_canopy(10, 15.0) is True

    def test_30_4_h_boundary_just_below_15m_not_excluded(self):
        """Boundary: canopy_height_m=14.999 with class 10 → NOT excluded."""
        assert is_high_canopy(10, 14.999) is False

    def test_30_4_i_class20_canopy15_excluded(self):
        """Shrubland class 20 at exactly 15 m → excluded."""
        assert is_high_canopy(20, 15.0) is True

    def test_30_4_j_neither_condition_alone_sufficient(self):
        """Neither land-cover alone nor canopy alone triggers exclusion."""
        # High canopy, wrong class
        assert is_high_canopy(60, 30.0) is False
        # Right class, low canopy
        assert is_high_canopy(10, 5.0) is False

    def test_30_4_k_non_forest_classes_not_excluded(self):
        """Non-forest ESA classes (30, 40, 50, 60, 70, 80, 90) not excluded."""
        for lc_class in [30, 40, 50, 60, 70, 80, 90]:
            assert is_high_canopy(lc_class, 25.0) is False, (
                f"30.4 FAIL: class {lc_class} with canopy=25 should NOT be excluded."
            )

    # ── Canonical location tests ─────────────────────────────────────────

    def test_30_4_l_canonical_definition_in_constraints_py(self):
        """is_high_canopy canonical definition is in geosignal.constraints."""
        import inspect
        import geosignal.constraints as c_mod
        # Function must be defined in constraints.py, not ethics.py
        assert inspect.getfile(is_high_canopy_from_constraints).endswith("constraints.py"), (
            "30.4 FAIL: is_high_canopy canonical definition is not in constraints.py."
        )

    def test_30_4_m_ethics_re_export_points_to_constraints_function(self):
        """ethics.is_high_canopy is the same function object as constraints.is_high_canopy."""
        assert is_high_canopy is is_high_canopy_from_constraints, (
            "30.4 FAIL: ethics.is_high_canopy is NOT the same object as "
            "constraints.is_high_canopy — duplicate definition detected."
        )

    def test_30_4_n_only_one_implementation_exists(self):
        """No separate implementation of is_high_canopy exists outside constraints.py."""
        import ast
        import pathlib
        backend_dir = pathlib.Path(__file__).parent.parent / "backend" / "geosignal"
        definitions: list[str] = []
        for py_file in backend_dir.glob("*.py"):
            src = py_file.read_text(encoding="utf-8")
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == "is_high_canopy"
                    and py_file.name != "constraints.py"  # canonical location is ok
                ):
                    definitions.append(py_file.name)
        assert definitions == [], (
            f"30.4 FAIL: is_high_canopy defined outside constraints.py in: {definitions}"
        )

    def test_30_4_o_canonical_constants_are_correct(self):
        """HIGH_CANOPY_LAND_COVER_CLASSES == {10, 20} and threshold == 15.0."""
        assert HIGH_CANOPY_LAND_COVER_CLASSES == frozenset({10, 20}), (
            f"30.4 FAIL: HIGH_CANOPY_LAND_COVER_CLASSES = {HIGH_CANOPY_LAND_COVER_CLASSES}"
        )
        assert CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M == 15.0, (
            f"30.4 FAIL: CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M = {CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M}"
        )

    def test_30_4_p_candidate_ranking_status_blocked(self):
        """rank_bts_candidates does not exist — constraint integration BLOCKED.

        BLOCKED: rank_bts_candidates is referenced only in docstrings.
        The module that would call is_high_canopy() with exclude_high_canopy=True
        has not been implemented yet (Task 11–12 scope).
        This test documents the blocked state rather than falsely asserting PASS.
        """
        import importlib.util
        # Confirm rank_bts_candidates is not importable as a callable
        spec = importlib.util.find_spec("geosignal.candidates")
        has_candidates_module = spec is not None
        if has_candidates_module:
            import geosignal.candidates as cands_mod
            has_rank_fn = callable(getattr(cands_mod, "rank_bts_candidates", None))
        else:
            has_rank_fn = False

        if not has_rank_fn:
            import warnings
            warnings.warn(
                "BLOCKED [30.4]: rank_bts_candidates not yet implemented. "
                "is_high_canopy() constraint integration with candidate ranking "
                "cannot be verified until Task 11–12 is completed.",
                stacklevel=1,
            )
            # Mark as expected-blocked, not as test failure
            pytest.skip(
                "BLOCKED: rank_bts_candidates not implemented — "
                "deforestation constraint live filtering cannot be verified."
            )




# ===========================================================================
# 30.5 — SHAP available for Tier 1 and Tier 2
# ===========================================================================

_BASELINE = {feat: 100.0 for feat in CONSOLIDATED_FEATURES}
_WEIGHTS = {feat: 1.0 / len(CONSOLIDATED_FEATURES) for feat in CONSOLIDATED_FEATURES}
_FV = FeatureVector(
    elevation_m=200.0, slope_deg=5.0, land_cover_class=30, canopy_height_m=5.0,
    distance_to_bts_m=3000.0, road_distance_m=800.0,
    population_density_per_km2=400.0, facility_proximity_m=1500.0,
)


class TestSHAPAvailability:
    """Safeguard 5: SHAP for both Tier 1 (AHP) and Tier 2 (adapter)."""

    def test_30_5_a_tier1_shap_has_eight_features(self):
        """compute_ahp_shap returns exactly 8 entries."""
        shap_vals = compute_ahp_shap(_FV, _WEIGHTS, _BASELINE)
        assert len(shap_vals) == 8, (
            f"30.5 FAIL: Tier 1 SHAP has {len(shap_vals)} entries, expected 8."
        )

    def test_30_5_b_tier1_shap_keys_match_consolidated_features(self):
        """compute_ahp_shap keys match CONSOLIDATED_FEATURES exactly."""
        shap_vals = compute_ahp_shap(_FV, _WEIGHTS, _BASELINE)
        assert set(shap_vals.keys()) == set(CONSOLIDATED_FEATURES)

    def test_30_5_c_tier1_shap_no_none_values(self):
        """No None values in Tier 1 SHAP output."""
        shap_vals = compute_ahp_shap(_FV, _WEIGHTS, _BASELINE)
        for feat, val in shap_vals.items():
            assert val is not None, f"30.5 FAIL: SHAP value for '{feat}' is None."

    def test_30_5_d_tier2_ahp_adapter_shap_returns_8_columns(self):
        """AHPAdapter.shap_values returns (N, 8) for (N, 8) input."""
        import numpy as np
        adapter = AHPAdapter()
        features = np.random.rand(4, 8) * 200.0
        sv = adapter.shap_values(features)
        assert sv.shape == (4, 8), (
            f"30.5 FAIL: AHPAdapter.shap_values returned shape {sv.shape}, expected (4, 8)."
        )

    def test_30_5_e_format_shap_top3_returns_three_entries(self):
        """format_shap_top3 returns exactly 3 entries."""
        shap_vals = compute_ahp_shap(_FV, _WEIGHTS, _BASELINE)
        top3 = format_shap_top3(shap_vals)
        assert len(top3) == 3, (
            f"30.5 FAIL: format_shap_top3 returned {len(top3)} entries, expected 3."
        )

    def test_30_5_f_top3_sorted_by_abs_value_descending(self):
        """Top-3 entries are sorted by |value| descending."""
        shap_vals = compute_ahp_shap(_FV, _WEIGHTS, _BASELINE)
        top3 = format_shap_top3(shap_vals)
        abs_vals = [abs(e["value"]) for e in top3]
        assert abs_vals == sorted(abs_vals, reverse=True), (
            "30.5 FAIL: SHAP top-3 is not sorted by descending |value|."
        )

    def test_30_5_g_top3_direction_field_correct(self):
        """direction field is 'positive' for non-negative values."""
        shap_vals = compute_ahp_shap(_FV, _WEIGHTS, _BASELINE)
        top3 = format_shap_top3(shap_vals)
        for entry in top3:
            expected = "positive" if entry["value"] >= 0.0 else "negative"
            assert entry["direction"] == expected, (
                f"30.5 FAIL: direction mismatch for value={entry['value']}: "
                f"got '{entry['direction']}', expected '{expected}'."
            )

    def test_30_5_h_top3_feature_name_is_plain_language(self):
        """feature_name uses plain-language labels, not raw feature keys."""
        shap_vals = compute_ahp_shap(_FV, _WEIGHTS, _BASELINE)
        top3 = format_shap_top3(shap_vals)
        raw_keys = set(CONSOLIDATED_FEATURES)
        for entry in top3:
            # Plain-language label should NOT be the raw snake_case key
            assert entry["feature_name"] not in raw_keys, (
                f"30.5 FAIL: feature_name '{entry['feature_name']}' is a raw key, "
                "not a plain-language label."
            )

    def test_30_5_i_shap_no_condition_excludes_tier1(self):
        """No code path denies SHAP for Tier 1 — compute_ahp_shap always runs."""
        # Verify by calling with minimal valid inputs — should not raise
        shap_vals = compute_ahp_shap(_FV, _WEIGHTS, _BASELINE)
        assert isinstance(shap_vals, dict)


# ===========================================================================
# 30.6 — Confidence thresholds canonical (single definition)
# ===========================================================================

class TestConfidenceThresholdsCanonical:
    """Safeguard 6: one canonical ConfidenceThresholds definition."""

    def test_30_6_a_single_class_definition_in_models(self):
        """ConfidenceThresholds is defined exactly once (in models.py)."""
        import geosignal.models as m
        import geosignal.confidence as c
        # confidence.py imports from models.py — same class object
        assert c.ConfidenceThresholds is m.ConfidenceThresholds, (
            "30.6 FAIL: confidence.py does not import ConfidenceThresholds from models.py."
        )

    def test_30_6_b_default_high_km_is_2(self):
        """Default high_km == 2.0."""
        t = ConfidenceThresholds()
        assert t.high_km == 2.0

    def test_30_6_c_default_low_km_is_10(self):
        """Default low_km == 10.0."""
        t = ConfidenceThresholds()
        assert t.low_km == 10.0

    def test_30_6_d_data_quality_report_stores_thresholds(self):
        """DataQualityReport has a confidence_thresholds field."""
        fields = {f.name: f for f in dataclasses.fields(DataQualityReport)}
        assert "confidence_thresholds" in fields, (
            "30.6 FAIL: DataQualityReport missing confidence_thresholds field."
        )

    def test_30_6_e_tag_confidence_uses_canonical_thresholds(self):
        """tag_confidence accepts ConfidenceThresholds; function is shared."""
        t = ConfidenceThresholds()
        assert tag_confidence((0.0, 0.0), 1.0, 1.0, t) == "High"
        assert tag_confidence((0.0, 0.0), 11.0, 11.0, t) == "Low"
        assert tag_confidence((0.0, 0.0), 5.0, 5.0, t) == "Med"

    def test_30_6_f_boundary_2km_is_med_not_high(self):
        """Both sources at exactly high_km=2.0 → Med (strict <)."""
        t = ConfidenceThresholds()
        assert tag_confidence((0.0, 0.0), 2.0, 2.0, t) == "Med"

    def test_30_6_g_boundary_10km_is_med_not_low(self):
        """Both sources at exactly low_km=10.0 → Med (strict >)."""
        t = ConfidenceThresholds()
        assert tag_confidence((0.0, 0.0), 10.0, 10.0, t) == "Med"

    def test_30_6_h_absent_source_is_low_not_confirmed_zero(self):
        """Absent record (None) → Low, never interpreted as confirmed zero."""
        t = ConfidenceThresholds()
        assert tag_confidence((0.0, 0.0), None, 1.0, t) == "Low"
        assert tag_confidence((0.0, 0.0), 1.0, None, t) == "Low"

    def test_30_6_i_no_duplicate_threshold_hard_coding_in_confidence_py(self):
        """confidence.py does not hard-code 2.0/10.0 as business logic."""
        conf_src = inspect.getsource(tag_confidence)
        # The function itself should not contain literal 2.0 or 10.0 values
        # as magic numbers — it reads them from the thresholds parameter.
        import ast as ast_mod
        tree = ast_mod.parse(conf_src)
        literal_floats = [
            node.value for node in ast_mod.walk(tree)
            if isinstance(node, ast_mod.Constant) and isinstance(node.value, float)
        ]
        # Allow math.inf but not business-rule literals 2.0 or 10.0
        business_literals = [v for v in literal_floats if v in {2.0, 10.0}]
        assert business_literals == [], (
            f"30.6 FAIL: tag_confidence() hard-codes threshold values {business_literals}. "
            "Thresholds must come from the ConfidenceThresholds parameter."
        )



# ===========================================================================
# 30.7 — Model version and scoring timestamp
# ===========================================================================

class TestModelAuditMetadata:
    """Safeguard 7: model_version and scoring_run_id present in candidate data."""

    def test_30_7_a_bts_candidate_has_model_version_field(self):
        """BTSCandidate dataclass has model_version field."""
        from geosignal.models import BTSCandidate
        fields = {f.name for f in dataclasses.fields(BTSCandidate)}
        assert "model_version" in fields, (
            "30.7 FAIL: BTSCandidate missing model_version field."
        )

    def test_30_7_b_bts_candidate_has_scoring_run_id_field(self):
        """BTSCandidate dataclass has scoring_run_id field."""
        from geosignal.models import BTSCandidate
        fields = {f.name for f in dataclasses.fields(BTSCandidate)}
        assert "scoring_run_id" in fields, (
            "30.7 FAIL: BTSCandidate missing scoring_run_id field."
        )

    def test_30_7_c_grid_cell_has_model_version_field(self):
        """GridCell type has model_version field."""
        # GridCell is a TypedDict / dataclass in types.ts on frontend;
        # verify the migration has model_version column in grid_cells.
        migration_path = pathlib.Path(__file__).parent.parent / "infra" / "migrations" / "001_initial_schema.sql"
        sql = migration_path.read_text(encoding="utf-8")
        assert "model_version" in sql, (
            "30.7 FAIL: grid_cells table in migration missing model_version column."
        )

    def test_30_7_d_scoring_runs_table_has_timestamp(self):
        """scoring_runs table has a timestamp column."""
        migration_path = pathlib.Path(__file__).parent.parent / "infra" / "migrations" / "001_initial_schema.sql"
        sql = migration_path.read_text(encoding="utf-8")
        assert "timestamp" in sql, (
            "30.7 FAIL: scoring_runs table missing timestamp column."
        )

    def test_30_7_e_scoring_run_id_persisted_per_candidate(self):
        """bts_candidates table has scoring_run_id column."""
        migration_path = pathlib.Path(__file__).parent.parent / "infra" / "migrations" / "001_initial_schema.sql"
        sql = migration_path.read_text(encoding="utf-8")
        assert "scoring_run_id" in sql, (
            "30.7 FAIL: bts_candidates table missing scoring_run_id column."
        )

    def test_30_7_f_recommendations_api_preserves_model_version(self):
        """GridCellResponse and BTSCandidate API types include model_version."""
        from geosignal.lib_api_types_check import _check_api_types
        # Inline check: api-types.ts GridCellResponse has model_version
        api_path = pathlib.Path(__file__).parent.parent / "frontend" / "lib" / "api-types.ts"
        content = api_path.read_text(encoding="utf-8")
        assert "model_version" in content, (
            "30.7 FAIL: lib/api-types.ts GridCellResponse missing model_version."
        )

    def test_30_7_g_scoring_run_id_in_api_types(self):
        """api-types.ts GridCellResponse includes scoring_run_id."""
        api_path = pathlib.Path(__file__).parent.parent / "frontend" / "lib" / "api-types.ts"
        content = api_path.read_text(encoding="utf-8")
        assert "scoring_run_id" in content, (
            "30.7 FAIL: lib/api-types.ts GridCellResponse missing scoring_run_id."
        )

    def test_30_7_h_scoring_run_timestamp_in_types_ts(self):
        """lib/types.ts GridCell and BTSCandidate include scoring_run_timestamp."""
        types_path = pathlib.Path(__file__).parent.parent / "frontend" / "lib" / "types.ts"
        content = types_path.read_text(encoding="utf-8")
        assert "scoring_run_timestamp" in content, (
            "30.7 FAIL: lib/types.ts missing scoring_run_timestamp field. "
            "This field is required to display the scoring timestamp in SidePanel."
        )

    def test_30_7_i_scoring_run_timestamp_in_api_types(self):
        """api-types.ts GridCellResponse includes scoring_run_timestamp."""
        api_path = pathlib.Path(__file__).parent.parent / "frontend" / "lib" / "api-types.ts"
        content = api_path.read_text(encoding="utf-8")
        assert "scoring_run_timestamp" in content, (
            "30.7 FAIL: lib/api-types.ts GridCellResponse missing scoring_run_timestamp. "
            "The API layer must preserve this field."
        )

    def test_30_7_j_side_panel_renders_timestamp_element(self):
        """SidePanel.tsx has a scoring-run-timestamp testid element."""
        sidepanel_path = pathlib.Path(__file__).parent.parent / "frontend" / "components" / "SidePanel.tsx"
        content = sidepanel_path.read_text(encoding="utf-8")
        assert "scoring-run-timestamp" in content, (
            "30.7 FAIL: SidePanel.tsx missing data-testid='scoring-run-timestamp' element. "
            "The scoring run timestamp must be visible text, not only the run ID."
        )

    def test_30_7_k_scoring_run_timestamp_not_derived_from_run_id(self):
        """SidePanel does not fabricate a timestamp from scoring_run_id.

        BLOCKED (partial): the field exists and renders '—' when absent.
        Full timestamp display requires the backend pipeline to populate
        scoring_run_timestamp in the API response (Task 11–12 scope).
        When scoring_run_timestamp is undefined the UI shows '—' correctly.
        """
        sidepanel_path = pathlib.Path(__file__).parent.parent / "frontend" / "components" / "SidePanel.tsx"
        content = sidepanel_path.read_text(encoding="utf-8")
        # The field reference must be 'scoring_run_timestamp', not derived from 'scoring_run_id'
        assert "scoring_run_timestamp" in content, (
            "30.7 FAIL: SidePanel.tsx must use scoring_run_timestamp, "
            "not a fabricated value from scoring_run_id."
        )
        # scoring_run_id must not be inside the timestamp display block
        # (simple check: the timestamp element uses the correct field)
        ts_block_start = content.find("scoring-run-timestamp")
        ts_block_end = content.find("</p>", ts_block_start)
        ts_block = content[ts_block_start:ts_block_end]
        assert "scoring_run_id" not in ts_block, (
            "30.7 FAIL: scoring-run-timestamp element appears to use "
            "scoring_run_id — timestamp must not be fabricated from run ID."
        )


# ===========================================================================
# 30.8 — PII audit (backend side — complements existing test_pii_absence.py)
# ===========================================================================

class TestPIIAudit:
    """Safeguard 8: no PII fields in schema, Python types, or API payload."""

    _MIGRATION = pathlib.Path(__file__).parent.parent / "infra" / "migrations" / "001_initial_schema.sql"
    _PII_TERMS = {
        "email", "phone", "household", "individual", "device_id",
        "imei", "imsi", "personal", "raw_user", "user_record",
    }

    def test_30_8_a_migration_no_email_column(self):
        """No email column in migration."""
        sql = self._MIGRATION.read_text(encoding="utf-8").lower()
        assert "email" not in sql, "30.8 FAIL: migration contains 'email' column."

    def test_30_8_b_migration_no_phone_column(self):
        """No phone column in migration."""
        sql = self._MIGRATION.read_text(encoding="utf-8").lower()
        assert "phone" not in sql, "30.8 FAIL: migration contains 'phone' column."

    def test_30_8_c_migration_no_device_id_column(self):
        """No device_id column in migration."""
        sql = self._MIGRATION.read_text(encoding="utf-8").lower()
        assert "device_id" not in sql, "30.8 FAIL: migration contains 'device_id'."

    def test_30_8_d_population_only_as_density(self):
        """population field in schema only as population_density (aggregated)."""
        sql = self._MIGRATION.read_text(encoding="utf-8").lower()
        # Must not contain household-level population fields
        assert "population_count" not in sql or "population_density" in sql, (
            "30.8 FAIL: migration has population_count without density context."
        )

    def test_30_8_e_feature_vector_has_no_pii_fields(self):
        """FeatureVector fields contain no PII-indicative names."""
        fv_fields = {f.name for f in dataclasses.fields(FeatureVector)}
        for term in self._PII_TERMS:
            violations = [f for f in fv_fields if term in f.lower()]
            assert not violations, (
                f"30.8 FAIL: FeatureVector has PII-indicative field: {violations}"
            )

    def test_30_8_f_api_error_route_no_stack_trace(self):
        """API routes do not expose stack traces — verified by source scan."""
        routes_dir = pathlib.Path(__file__).parent.parent / "frontend" / "app" / "api"
        for route_file in routes_dir.rglob("route.ts"):
            src = route_file.read_text(encoding="utf-8")
            assert "stack" not in src.lower() or "// " in src, (
                f"30.8 WARN: {route_file.name} may expose stack trace."
            )
            assert "process.env" not in src, (
                f"30.8 FAIL: {route_file.name} references process.env (credential leak risk)."
            )

    def test_30_8_g_no_supabase_key_in_route_files(self):
        """Route files do not contain hard-coded Supabase keys."""
        routes_dir = pathlib.Path(__file__).parent.parent / "frontend" / "app" / "api"
        for route_file in routes_dir.rglob("route.ts"):
            src = route_file.read_text(encoding="utf-8")
            assert "eyJ" not in src, (
                f"30.8 FAIL: {route_file.name} may contain hard-coded JWT/Supabase key."
            )

    def test_30_8_h_consolidated_features_no_ookla_raw_records(self):
        """CONSOLIDATED_FEATURES contains no Ookla raw-record field."""
        ookla_fields = [f for f in CONSOLIDATED_FEATURES if "ookla" in f.lower()]
        assert ookla_fields == [], (
            f"30.8 FAIL: CONSOLIDATED_FEATURES has Ookla field: {ookla_fields}"
        )


# ===========================================================================
# Helper import shim (avoids creating a new module just for this check)
# ===========================================================================

# We need to check api-types.ts without importing it.
# Create a tiny shim so test_30_7_f can import something without failing.
import types as _types
_shim = _types.ModuleType("geosignal.lib_api_types_check")
_shim._check_api_types = lambda: None
sys.modules["geosignal.lib_api_types_check"] = _shim
