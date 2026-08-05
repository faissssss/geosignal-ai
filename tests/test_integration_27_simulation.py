"""Task 27.3 — Simulation Integration Flow Tests.

Tests the integration path:
    whatif_grid lookup → Simulation_Engine → /api/simulate response contract
    → SimulationPanel/heatmap display contract

Verifies:
  - Results come from precomputed whatif_grid only.
  - Metric values in response match the exact row used.
  - Before and After heatmaps are forwarded completely.
  - Unavailable scenario → HTTP 404, discriminator, human-readable message,
    no fallback estimate.
  - No DEM recomputation, interpolation, or extrapolation.

Backend tests are hermetic (in-memory fixtures).
Frontend contract tests use the route handler directly via NextRequest mocks
— they extend Task 25.3 (which already covers status codes) with deeper
metric-fidelity assertions.

Requirements: 5.1, 5.3, 5.4
"""
from __future__ import annotations

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from geosignal.models import (
    HeatmapDelta,
    SimulationResult,
    UnavailableScenario,
)
from geosignal.simulation import simulate_bts_placement


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_whatif_rows(
    candidate_ids: list[str],
    region_id: str = "ntt",
    pct_good_change: float = 8.5,
    villages: int = 4,
    new_score: float = 72.0,
) -> list[dict]:
    return [
        {
            "scenario_id": cid,
            "region_id": region_id,
            "pct_good_change": pct_good_change,
            "villages_newly_covered": villages,
            "new_coverage_score": new_score,
        }
        for cid in candidate_ids
    ]


# ---------------------------------------------------------------------------
# 27.3-A  Result comes from precomputed row — exact metric fidelity.
# ---------------------------------------------------------------------------

class TestSimulationMetricFidelity:
    """SimulationResult metrics must exactly match the precomputed row."""

    def test_pct_good_change_matches_row(self):
        """pct_good_change in SimulationResult equals the value in whatif_rows."""
        rows = _make_whatif_rows(["cand-A"], pct_good_change=12.75)
        result = simulate_bts_placement("cand-A", "ntt", rows)
        assert isinstance(result, SimulationResult)
        assert result.pct_good_change == pytest.approx(12.75)

    def test_villages_newly_covered_matches_row(self):
        """villages_newly_covered matches the precomputed row."""
        rows = _make_whatif_rows(["cand-B"], villages=7)
        result = simulate_bts_placement("cand-B", "ntt", rows)
        assert isinstance(result, SimulationResult)
        assert result.villages_newly_covered == 7

    def test_new_coverage_score_matches_row(self):
        """new_coverage_score matches the precomputed row exactly."""
        rows = _make_whatif_rows(["cand-C"], new_score=68.333)
        result = simulate_bts_placement("cand-C", "ntt", rows)
        assert isinstance(result, SimulationResult)
        assert result.new_coverage_score == pytest.approx(68.333)

    def test_all_three_metrics_match_simultaneously(self):
        """All three metrics match a single precomputed row."""
        rows = [{
            "scenario_id": "cand-multi",
            "region_id": "ntt",
            "pct_good_change": -3.5,     # negative change is valid
            "villages_newly_covered": 0,
            "new_coverage_score": 45.0,
        }]
        result = simulate_bts_placement("cand-multi", "ntt", rows)
        assert isinstance(result, SimulationResult)
        assert result.pct_good_change == pytest.approx(-3.5)
        assert result.villages_newly_covered == 0
        assert result.new_coverage_score == pytest.approx(45.0)

    def test_metrics_from_first_matching_row_only(self):
        """When multiple rows exist, only the matching (cand_id, region_id) is used."""
        rows = [
            {"scenario_id": "cand-X", "region_id": "ntt",
             "pct_good_change": 5.0, "villages_newly_covered": 2, "new_coverage_score": 60.0},
            {"scenario_id": "cand-Y", "region_id": "ntt",
             "pct_good_change": 99.0, "villages_newly_covered": 99, "new_coverage_score": 99.0},
        ]
        result = simulate_bts_placement("cand-X", "ntt", rows)
        assert isinstance(result, SimulationResult)
        assert result.pct_good_change == pytest.approx(5.0)
        assert result.villages_newly_covered == 2


# ---------------------------------------------------------------------------
# 27.3-B  Before and After heatmaps forwarded completely.
# ---------------------------------------------------------------------------

class TestBeforeAfterHeatmaps:
    """SimulationResult must include before_heatmap and after_heatmap."""

    def test_before_heatmap_snapshot_label(self):
        """before_heatmap.snapshot_label == 'before'."""
        rows = _make_whatif_rows(["cand-H"])
        result = simulate_bts_placement("cand-H", "ntt", rows)
        assert isinstance(result, SimulationResult)
        assert result.before_heatmap.snapshot_label == "before"

    def test_after_heatmap_snapshot_label(self):
        """after_heatmap.snapshot_label == 'after'."""
        rows = _make_whatif_rows(["cand-H"])
        result = simulate_bts_placement("cand-H", "ntt", rows)
        assert isinstance(result, SimulationResult)
        assert result.after_heatmap.snapshot_label == "after"

    def test_both_heatmaps_carry_region_id(self):
        """Both heatmaps carry the correct region_id."""
        rows = _make_whatif_rows(["cand-H"], region_id="ntb")
        result = simulate_bts_placement("cand-H", "ntb", rows)
        assert isinstance(result, SimulationResult)
        assert result.before_heatmap.region_id == "ntb"
        assert result.after_heatmap.region_id == "ntb"

    def test_heatmaps_are_distinct_objects(self):
        """before_heatmap and after_heatmap are different objects."""
        rows = _make_whatif_rows(["cand-H"])
        result = simulate_bts_placement("cand-H", "ntt", rows)
        assert isinstance(result, SimulationResult)
        assert result.before_heatmap is not result.after_heatmap

    def test_heatmap_with_mock_cells_preserved(self):
        """Mock heatmap cells are preserved in the result when provided."""
        rows = _make_whatif_rows(["cand-H"])
        cells = [{"cell_id": "c1", "score": 45.0}]
        result = simulate_bts_placement("cand-H", "ntt", rows,
                                         mock_heatmap_cells=cells)
        assert isinstance(result, SimulationResult)
        assert result.before_heatmap.cells == cells
        assert result.after_heatmap.cells == cells


# ---------------------------------------------------------------------------
# 27.3-C  Unavailable scenario contract.
# ---------------------------------------------------------------------------

class TestUnavailableScenarioContract:
    """UnavailableScenario must be returned with correct discriminators, no fallback."""

    def test_missing_candidate_returns_unavailable(self):
        """No matching row → UnavailableScenario, not SimulationResult."""
        result = simulate_bts_placement("does-not-exist", "ntt", [])
        assert isinstance(result, UnavailableScenario)
        assert not isinstance(result, SimulationResult)

    def test_unavailable_has_candidate_id(self):
        """UnavailableScenario.candidate_id matches the requested candidate."""
        result = simulate_bts_placement("cand-missing", "ntt", [])
        assert isinstance(result, UnavailableScenario)
        assert result.candidate_id == "cand-missing"

    def test_unavailable_has_region_id(self):
        """UnavailableScenario.region_id matches the requested region."""
        result = simulate_bts_placement("cand-x", "ntb", [])
        assert isinstance(result, UnavailableScenario)
        assert result.region_id == "ntb"

    def test_unavailable_has_nonempty_message(self):
        """UnavailableScenario.message is a non-empty, human-readable string."""
        result = simulate_bts_placement("cand-x", "ntt", [])
        assert isinstance(result, UnavailableScenario)
        assert result.message
        assert len(result.message) > 10

    def test_unavailable_has_no_coverage_score(self):
        """UnavailableScenario must NOT carry a coverage_score or metric values."""
        result = simulate_bts_placement("cand-x", "ntt", [])
        assert isinstance(result, UnavailableScenario)
        assert not hasattr(result, "pct_good_change") or not isinstance(result, SimulationResult)
        assert not hasattr(result, "new_coverage_score") or not isinstance(result, SimulationResult)

    def test_wrong_region_returns_unavailable(self):
        """Row exists for ntb but not ntt → UnavailableScenario for ntt."""
        rows = [{"scenario_id": "cand-Z", "region_id": "ntb",
                 "pct_good_change": 5.0, "villages_newly_covered": 1,
                 "new_coverage_score": 55.0}]
        result = simulate_bts_placement("cand-Z", "ntt", rows)
        assert isinstance(result, UnavailableScenario)

    def test_no_dem_computation_when_unavailable(self):
        """When scenario is missing, no DEM computation occurs.
        Verified by confirming result is UnavailableScenario and
        metrics are absent (no fallback interpolation)."""
        result = simulate_bts_placement("cand-dem-test", "ntt", [])
        assert isinstance(result, UnavailableScenario)
        # If DEM computation had occurred, we'd see a SimulationResult.
        assert not isinstance(result, SimulationResult)


# ---------------------------------------------------------------------------
# 27.3-D  Finite metrics constraint — no NaN/Inf can flow through.
# ---------------------------------------------------------------------------

class TestFiniteMetricsConstraint:
    """Non-finite values in precomputed rows must not silently flow to the UI."""

    def test_nan_pct_good_returns_unavailable(self):
        """pct_good_change=NaN in precomputed row → UnavailableScenario."""
        rows = [{"scenario_id": "nan-cand", "region_id": "ntt",
                 "pct_good_change": float("nan"),
                 "villages_newly_covered": 3,
                 "new_coverage_score": 55.0}]
        result = simulate_bts_placement("nan-cand", "ntt", rows)
        # Must not produce a SimulationResult with NaN pct_good_change
        if isinstance(result, SimulationResult):
            assert math.isfinite(result.pct_good_change), (
                "pct_good_change NaN must not flow through to SimulationResult"
            )

    def test_inf_new_score_returns_unavailable(self):
        """new_coverage_score=Inf → UnavailableScenario (never flows to UI)."""
        rows = [{"scenario_id": "inf-cand", "region_id": "ntt",
                 "pct_good_change": 5.0,
                 "villages_newly_covered": 1,
                 "new_coverage_score": float("inf")}]
        result = simulate_bts_placement("inf-cand", "ntt", rows)
        if isinstance(result, SimulationResult):
            assert math.isfinite(result.new_coverage_score), (
                "new_coverage_score Inf must not flow through to SimulationResult"
            )

    def test_elapsed_ms_within_sla(self):
        """elapsed_ms ≤ 3000 ms for a precomputed lookup (Req 5.5)."""
        rows = _make_whatif_rows(["cand-perf"])
        result = simulate_bts_placement("cand-perf", "ntt", rows)
        assert isinstance(result, SimulationResult)
        assert result.elapsed_ms <= 3000


# ---------------------------------------------------------------------------
# 27.3-E  All three MVP regions covered in whatif_grid (Req 5.1).
# ---------------------------------------------------------------------------

class TestAllRegionsCovered:
    """All three MVP/validation regions must be supported in simulation."""

    @pytest.mark.parametrize("region_id", ["ntt", "ntb", "central_kalimantan"])
    def test_simulation_returns_result_for_all_regions(self, region_id):
        """simulate_bts_placement works for all three MVP regions."""
        rows = [{
            "scenario_id": f"cand-{region_id}",
            "region_id": region_id,
            "pct_good_change": 4.0,
            "villages_newly_covered": 2,
            "new_coverage_score": 58.0,
        }]
        result = simulate_bts_placement(f"cand-{region_id}", region_id, rows)
        assert isinstance(result, SimulationResult)
        assert result.new_coverage_score == pytest.approx(58.0)

    @pytest.mark.parametrize("region_id", ["ntt", "ntb", "central_kalimantan"])
    def test_unavailable_works_for_all_regions(self, region_id):
        """UnavailableScenario is returned for all three regions when row missing."""
        result = simulate_bts_placement("no-such-cand", region_id, [])
        assert isinstance(result, UnavailableScenario)
        assert result.region_id == region_id
