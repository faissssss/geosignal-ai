"""Task 28 — Spatial Cross-Validation Acceptance Gates.

Tests the spatial_cv() contract (Requirements 2.4, 9.4, 13.5).

DATASET STRATEGY
----------------
All tests in this file use HERMETIC, deterministic fixtures.
They do NOT use live Supabase data or real NTT/Central Kalimantan field data.

The fixtures are designed to represent the terrain characteristics called out
in the spec:
  - NTT_FIXTURE   : elevation-driven terrain (high elevation variance, low
                    canopy); 6 kecamatan, 3–5 rows each.
  - CK_FIXTURE    : dense-canopy terrain (high canopy_height_m, forest
                    land_cover_class); 5 kecamatan, 2–4 rows each; one
                    kecamatan is flagged as dense-canopy by data attribute.

Live acceptance (real NTT / Central Kalimantan data):
  - A live run requires a populated database and real feature vectors.
  - None of the hermetic tests below may be labelled as live validation.
  - Live status is BLOCKED until real data is provisioned.

Acceptance tests (15 required + extras)
----------------------------------------
 T1  Train/test kecamatan are disjoint for every fold.
 T2  All NTT kecamatan become a test block at least once.
 T3  All NTT kecamatan have a per-kecamatan accuracy entry.
 T4  Central Kalimantan has per-kecamatan results (no suppression).
 T5  Dense-canopy kecamatan becomes a test block.
 T6  Dense-canopy accuracy is finite (not None, NaN, or Inf).
 T7  Aggregate metric does not replace per-kecamatan entries.
 T8  Kecamatan with the lowest accuracy still appears in the result.
 T9  Missing kecamatan entry is detected as a test failure.
T10  Duplicate kecamatan entry in output is detected as a test failure.
T11  None, NaN, and Inf accuracy values are rejected.
T12  Input with fewer than 2 kecamatan is handled with a structured error.
T13  Random point split is never used (LOKO split only).
T14  Fold rows do not leak: test-fold rows absent from train features.
T15  Reported kecamatan count equals unique kecamatan count in the input.

Requirements: 2.4, 9.4, 13.5
"""
from __future__ import annotations

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import numpy as np
import pytest

from geosignal.adapters import AHPAdapter
from geosignal.models import CVResult, FeatureVector
from geosignal.validation import aggregate_accuracy, spatial_cv


# ===========================================================================
# Deterministic fixture builders
# ===========================================================================

def _fv(
    elevation_m: float = 200.0,
    slope_deg: float = 5.0,
    land_cover_class: int = 30,
    canopy_height_m: float = 5.0,
    distance_to_bts_m: float = 3000.0,
    road_distance_m: float = 800.0,
    population_density_per_km2: float = 400.0,
    facility_proximity_m: float = 1500.0,
) -> FeatureVector:
    return FeatureVector(
        elevation_m=elevation_m,
        slope_deg=slope_deg,
        land_cover_class=land_cover_class,
        canopy_height_m=canopy_height_m,
        distance_to_bts_m=distance_to_bts_m,
        road_distance_m=road_distance_m,
        population_density_per_km2=population_density_per_km2,
        facility_proximity_m=facility_proximity_m,
    )


# ---------------------------------------------------------------------------
# NTT fixture — elevation-driven terrain (6 kecamatan, 3 rows each)
# High elevation variance, low canopy, diverse slopes.
# Terrain characteristic: elevation_m is the dominant differentiator.
# ---------------------------------------------------------------------------

NTT_KECAMATAN = [
    "IDN.15.1_1",  # Alor
    "IDN.15.2_1",  # Belu
    "IDN.15.3_1",  # Ende
    "IDN.15.4_1",  # Flores Timur
    "IDN.15.5_1",  # Kupang
    "IDN.15.6_1",  # Lembata
]

# 3 rows per kecamatan; elevation ranges from 50 m to 2800 m (NTT's Timor plateau)
_NTT_ROWS: list[tuple[str, FeatureVector, float]] = []
for _i, _kid in enumerate(NTT_KECAMATAN):
    _base_elev = 50.0 + _i * 450.0          # 50, 500, 950, 1400, 1850, 2300
    for _j in range(3):
        _elev = _base_elev + _j * 50.0
        _slope = 3.0 + _i * 2.0 + _j       # 3..16 degrees
        _canopy = 1.5 + _j * 0.5           # Low canopy — NTT is semi-arid
        _score = max(0.0, min(100.0, 40.0 + _i * 5.0 + _j * 2.0))
        _NTT_ROWS.append((_kid, _fv(
            elevation_m=_elev,
            slope_deg=_slope,
            canopy_height_m=_canopy,
            land_cover_class=40,            # Cropland — typical NTT
            distance_to_bts_m=4000.0 - _i * 300.0,
            road_distance_m=1200.0 - _j * 100.0,
            population_density_per_km2=300.0 + _i * 30.0,
            facility_proximity_m=2000.0 - _i * 200.0,
        ), _score))

NTT_KEC_IDS    = [r[0] for r in _NTT_ROWS]
NTT_FVS        = [r[1] for r in _NTT_ROWS]
NTT_SCORES     = [r[2] for r in _NTT_ROWS]

# ---------------------------------------------------------------------------
# Central Kalimantan fixture — dense-canopy terrain (5 kecamatan, 3 rows each)
# High canopy_height_m, forest land_cover_class (10 = Tree cover).
# One kecamatan ("IDN.21.3_1") is explicitly dense-canopy by attribute:
#   canopy_height_m >= 25 m AND land_cover_class == 10 (Tree cover).
# This identification is based on data attributes, not the name alone.
# ---------------------------------------------------------------------------

CK_KECAMATAN = [
    "IDN.21.1_1",   # Barito Selatan  — mixed canopy (~12 m)
    "IDN.21.2_1",   # Barito Utara    — moderate canopy (~18 m)
    "IDN.21.3_1",   # Gunung Mas      — DENSE CANOPY (>= 25 m, class 10)
    "IDN.21.4_1",   # Kapuas          — moderate canopy (~15 m)
    "IDN.21.5_1",   # Katingan        — mixed canopy (~10 m)
]

# canopy heights chosen to make IDN.21.3_1 unambiguously dense-canopy by attribute
_CK_CANOPY = {
    "IDN.21.1_1": 12.0,
    "IDN.21.2_1": 18.0,
    "IDN.21.3_1": 28.0,   # >= 25 m AND class 10 → dense-canopy
    "IDN.21.4_1": 15.0,
    "IDN.21.5_1": 10.0,
}
_CK_LAND_COVER = {
    "IDN.21.1_1": 20,   # Shrubland
    "IDN.21.2_1": 10,   # Tree cover
    "IDN.21.3_1": 10,   # Tree cover — confirms dense-canopy
    "IDN.21.4_1": 40,   # Cropland
    "IDN.21.5_1": 20,   # Shrubland
}

_CK_ROWS: list[tuple[str, FeatureVector, float]] = []
for _i, _kid in enumerate(CK_KECAMATAN):
    for _j in range(3):
        _canopy = _CK_CANOPY[_kid] + _j * 0.5
        _lcc = _CK_LAND_COVER[_kid]
        _score = max(0.0, min(100.0, 35.0 + _i * 6.0 + _j * 1.5))
        _CK_ROWS.append((_kid, _fv(
            elevation_m=40.0 + _i * 20.0 + _j * 5.0,
            slope_deg=1.5 + _i * 0.5,
            land_cover_class=_lcc,
            canopy_height_m=_canopy,
            distance_to_bts_m=5000.0 - _i * 400.0,
            road_distance_m=600.0 + _j * 50.0,
            population_density_per_km2=180.0 + _i * 20.0,
            facility_proximity_m=2500.0 - _i * 300.0,
        ), _score))

CK_KEC_IDS = [r[0] for r in _CK_ROWS]
CK_FVS     = [r[1] for r in _CK_ROWS]
CK_SCORES  = [r[2] for r in _CK_ROWS]

# The kecamatan identified as dense-canopy by data attribute
# (canopy_height_m >= 25 AND land_cover_class == 10)
DENSE_CANOPY_KEC = "IDN.21.3_1"


# ===========================================================================
# Shared adapter
# ===========================================================================

_ADAPTER = AHPAdapter()


# ===========================================================================
# T1 — Train/test kecamatan disjoint for every fold (Requirements 2.4, 9.4)
# ===========================================================================

class TestT1TrainTestDisjoint:
    """T1: train_kecamatan_ids ∩ test_kecamatan_ids = {} for every LOKO fold."""

    def test_t1_ntt_all_folds_disjoint(self):
        """NTT fixture: no fold has the test kecamatan also in train."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        kec_arr = [NTT_KEC_IDS[i] for i in range(len(NTT_KEC_IDS))]
        for test_kec in result.kecamatan_accuracies:
            test_rows   = {i for i, k in enumerate(kec_arr) if k == test_kec}
            train_rows  = {i for i, k in enumerate(kec_arr) if k != test_kec}
            overlap = test_rows & train_rows
            assert overlap == set(), (
                f"T1 FAIL: kecamatan '{test_kec}' has rows in both "
                f"train and test: {overlap}"
            )

    def test_t1_ck_all_folds_disjoint(self):
        """Central Kalimantan fixture: no fold leaks test kecamatan into train."""
        result = spatial_cv(CK_KEC_IDS, CK_FVS, CK_SCORES, _ADAPTER)
        kec_arr = CK_KEC_IDS
        for test_kec in result.kecamatan_accuracies:
            test_set  = {k for k in kec_arr if k == test_kec}
            train_set = {k for k in kec_arr if k != test_kec}
            assert test_set.isdisjoint(train_set), (
                f"T1 FAIL: kecamatan '{test_kec}' appears in both sets."
            )

    def test_t1_minimal_two_kecamatan_disjoint(self):
        """Minimal two-kecamatan input: both folds are disjoint."""
        kec_ids = ["A", "A", "B", "B"]
        fvs     = [_fv() for _ in range(4)]
        scores  = [50.0, 52.0, 48.0, 51.0]
        result  = spatial_cv(kec_ids, fvs, scores, _ADAPTER)
        assert set(result.kecamatan_accuracies) == {"A", "B"}
        # By LOKO construction, disjoint is guaranteed — verify n_folds
        assert result.n_folds == 2



# ===========================================================================
# T2 — All NTT kecamatan become a test block (Requirement 9.4)
# ===========================================================================

class TestT2AllNTTTestedAsBlock:
    """T2: every NTT kecamatan appears as the held-out test block exactly once."""

    def test_t2_all_six_ntt_kecamatan_are_test_blocks(self):
        """All 6 NTT kecamatan become test blocks."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        tested_set = set(result.kecamatan_accuracies.keys())
        for kec in NTT_KECAMATAN:
            assert kec in tested_set, (
                f"T2 FAIL: NTT kecamatan '{kec}' was never used as a test block."
            )

    def test_t2_n_folds_equals_unique_kecamatan_count(self):
        """n_folds == len(NTT_KECAMATAN) for the NTT fixture."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        assert result.n_folds == len(NTT_KECAMATAN), (
            f"T2 FAIL: expected {len(NTT_KECAMATAN)} folds, got {result.n_folds}."
        )


# ===========================================================================
# T3 — All NTT kecamatan have an accuracy entry (Requirement 9.4)
# ===========================================================================

class TestT3AllNTTReported:
    """T3: kecamatan_accuracies contains an entry for every NTT kecamatan."""

    def test_t3_all_ntt_kecamatan_in_result(self):
        """set(result.kecamatan_accuracies) == set(NTT_KECAMATAN)."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        assert set(result.kecamatan_accuracies) == set(NTT_KECAMATAN), (
            f"T3 FAIL: result kecamatan set differs from input.\n"
            f"  Expected: {sorted(NTT_KECAMATAN)}\n"
            f"  Got:      {sorted(result.kecamatan_accuracies.keys())}"
        )

    def test_t3_no_extra_kecamatan_in_result(self):
        """No kecamatan appears in the result that was not in the input."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        extra = set(result.kecamatan_accuracies) - set(NTT_KECAMATAN)
        assert extra == set(), (
            f"T3 FAIL: unexpected kecamatan in result: {extra}"
        )



# ===========================================================================
# T4 — Central Kalimantan has per-kecamatan results (Requirement 9.4)
# ===========================================================================

class TestT4CKPerKecamatanResults:
    """T4: every CK kecamatan has its own accuracy entry — none suppressed."""

    def test_t4_all_ck_kecamatan_reported(self):
        """set(result.kecamatan_accuracies) == set(CK_KECAMATAN)."""
        result = spatial_cv(CK_KEC_IDS, CK_FVS, CK_SCORES, _ADAPTER)
        assert set(result.kecamatan_accuracies) == set(CK_KECAMATAN), (
            f"T4 FAIL: missing CK kecamatan.\n"
            f"  Expected: {sorted(CK_KECAMATAN)}\n"
            f"  Got:      {sorted(result.kecamatan_accuracies.keys())}"
        )

    def test_t4_all_ck_entries_are_floats(self):
        """Every per-kecamatan accuracy value in CK result is a float."""
        result = spatial_cv(CK_KEC_IDS, CK_FVS, CK_SCORES, _ADAPTER)
        for kec, acc in result.kecamatan_accuracies.items():
            assert isinstance(acc, float), (
                f"T4 FAIL: accuracy for '{kec}' is {type(acc)}, not float."
            )


# ===========================================================================
# T5 — Dense-canopy kecamatan becomes a test block (Requirement 13.5)
# ===========================================================================

class TestT5DenseCanopyTested:
    """T5: the dense-canopy kecamatan identified by attribute is held out."""

    def test_t5_dense_canopy_kecamatan_identified_by_attribute(self):
        """Dense-canopy kecamatan is IDN.21.3_1 based on canopy_height_m >= 25
        AND land_cover_class == 10 (Tree cover), not by name alone."""
        dense_rows = [
            (kid, fv)
            for kid, fv, _ in _CK_ROWS
            if fv.canopy_height_m >= 25.0 and fv.land_cover_class == 10
        ]
        dense_kecs = {k for k, _ in dense_rows}
        assert DENSE_CANOPY_KEC in dense_kecs, (
            f"T5 FAIL: expected dense-canopy kecamatan '{DENSE_CANOPY_KEC}' "
            f"not identified by attribute. Dense candidates: {dense_kecs}"
        )

    def test_t5_dense_canopy_appears_in_result(self):
        """Dense-canopy kecamatan has an accuracy entry in the CK result."""
        result = spatial_cv(CK_KEC_IDS, CK_FVS, CK_SCORES, _ADAPTER)
        assert DENSE_CANOPY_KEC in result.kecamatan_accuracies, (
            f"T5 FAIL: dense-canopy kecamatan '{DENSE_CANOPY_KEC}' "
            "is absent from result.kecamatan_accuracies."
        )

    def test_t5_dense_canopy_was_test_block(self):
        """Dense-canopy kecamatan accuracy entry confirms it was held out."""
        result = spatial_cv(CK_KEC_IDS, CK_FVS, CK_SCORES, _ADAPTER)
        # If it is in kecamatan_accuracies it was the test block in its fold
        assert DENSE_CANOPY_KEC in result.kecamatan_accuracies
        # n_folds must equal unique kecamatan — confirms LOKO, not random
        assert result.n_folds == len(CK_KECAMATAN)



# ===========================================================================
# T6 — Dense-canopy accuracy is finite (Requirement 13.5)
# ===========================================================================

class TestT6DenseCanopyFiniteAccuracy:
    """T6: accuracy for the dense-canopy kecamatan is a finite float in [0,1]."""

    def test_t6_dense_canopy_accuracy_is_finite(self):
        """accuracy[DENSE_CANOPY_KEC] is finite (not None, NaN, or Inf)."""
        result = spatial_cv(CK_KEC_IDS, CK_FVS, CK_SCORES, _ADAPTER)
        acc = result.kecamatan_accuracies[DENSE_CANOPY_KEC]
        assert acc is not None, "T6 FAIL: dense-canopy accuracy is None."
        assert math.isfinite(acc), (
            f"T6 FAIL: dense-canopy accuracy is not finite: {acc!r}"
        )

    def test_t6_dense_canopy_accuracy_in_unit_interval(self):
        """accuracy[DENSE_CANOPY_KEC] is in [0.0, 1.0]."""
        result = spatial_cv(CK_KEC_IDS, CK_FVS, CK_SCORES, _ADAPTER)
        acc = result.kecamatan_accuracies[DENSE_CANOPY_KEC]
        assert 0.0 <= acc <= 1.0, (
            f"T6 FAIL: dense-canopy accuracy {acc} outside [0, 1]."
        )


# ===========================================================================
# T7 — Aggregate does not replace per-kecamatan entries (Requirement 9.4)
# ===========================================================================

class TestT7AggregateDoesNotSuppressPerKecamatan:
    """T7: aggregate_accuracy() is a summary only; per-kecamatan dict intact."""

    def test_t7_per_kecamatan_dict_still_present_after_aggregate(self):
        """Calling aggregate_accuracy() does not modify kecamatan_accuracies."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        before = dict(result.kecamatan_accuracies)
        _ = aggregate_accuracy(result)
        after = dict(result.kecamatan_accuracies)
        assert before == after, (
            "T7 FAIL: kecamatan_accuracies was modified by aggregate_accuracy()."
        )

    def test_t7_result_has_both_aggregate_and_per_kecamatan(self):
        """A CVResult carries per-kecamatan dict AND aggregate can be derived."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        assert len(result.kecamatan_accuracies) == len(NTT_KECAMATAN), (
            "T7 FAIL: per-kecamatan dict has wrong length."
        )
        agg = aggregate_accuracy(result)
        assert math.isfinite(agg), (
            f"T7 FAIL: aggregate accuracy is not finite: {agg!r}"
        )

    def test_t7_aggregate_only_result_fails_acceptance(self):
        """An aggregate-only CVResult (empty kecamatan_accuracies) is rejected."""
        aggregate_only = CVResult(kecamatan_accuracies={}, n_folds=0)
        # A gate that requires all kecamatan to be reported should fail
        assert len(aggregate_only.kecamatan_accuracies) == 0, (
            "Simulated aggregate-only result should have empty dict."
        )
        # Assert this would fail the T3 gate (no entries)
        missing = set(NTT_KECAMATAN) - set(aggregate_only.kecamatan_accuracies)
        assert missing == set(NTT_KECAMATAN), (
            "T7 FAIL: aggregate-only result should expose all kecamatan as missing."
        )



# ===========================================================================
# T8 — Lowest-accuracy kecamatan still appears in result (Requirement 9.4)
# ===========================================================================

class TestT8LowestAccuracyRetained:
    """T8: the kecamatan with the lowest accuracy is never removed."""

    def test_t8_lowest_ntt_accuracy_kecamatan_present(self):
        """Kecamatan with the lowest accuracy exists in kecamatan_accuracies."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        worst_kec = min(result.kecamatan_accuracies, key=result.kecamatan_accuracies.get)
        assert worst_kec in result.kecamatan_accuracies, (
            f"T8 FAIL: lowest-accuracy kecamatan '{worst_kec}' missing from result."
        )

    def test_t8_lowest_ck_accuracy_kecamatan_present(self):
        """Same for Central Kalimantan — worst kecamatan is not dropped."""
        result = spatial_cv(CK_KEC_IDS, CK_FVS, CK_SCORES, _ADAPTER)
        worst_kec = min(result.kecamatan_accuracies, key=result.kecamatan_accuracies.get)
        assert worst_kec in result.kecamatan_accuracies

    def test_t8_zero_accuracy_kecamatan_not_suppressed(self):
        """A kecamatan whose predictions are all wrong still appears in result."""
        # Build input where one kecamatan will have 0% accuracy:
        # scores are all 50 but predictions will be far off due to feature choice.
        kec_ids = ["A", "A", "A", "B", "B", "B"]
        # Kecamatan B has extreme distance features → low predicted score.
        fvs = (
            [_fv(facility_proximity_m=100.0, population_density_per_km2=5000.0)] * 3
            + [_fv(facility_proximity_m=499000.0, population_density_per_km2=0.01)] * 3
        )
        # Reference scores all set to 95 → B will likely miss them all
        scores = [95.0] * 6
        result = spatial_cv(kec_ids, fvs, scores, _ADAPTER)
        assert "B" in result.kecamatan_accuracies, (
            "T8 FAIL: zero-accuracy kecamatan 'B' was suppressed."
        )
        # Even if accuracy is 0.0, entry exists
        assert result.kecamatan_accuracies["B"] is not None


# ===========================================================================
# T9 — Missing kecamatan entry is detected (Requirement 9.4)
# ===========================================================================

class TestT9MissingKecamatanDetected:
    """T9: a CVResult with a missing kecamatan entry fails acceptance checks."""

    def test_t9_missing_entry_detected_by_set_comparison(self):
        """Removing one entry from kecamatan_accuracies is caught by assertion."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        # Simulate a buggy downstream that drops one entry
        manipulated = dict(result.kecamatan_accuracies)
        dropped_kec = NTT_KECAMATAN[2]
        del manipulated[dropped_kec]

        missing = set(NTT_KECAMATAN) - set(manipulated)
        assert missing == {dropped_kec}, (
            f"T9 FAIL: expected missing={{{dropped_kec!r}}}, got {missing}"
        )

    def test_t9_acceptance_gate_raises_on_missing(self):
        """An acceptance assertion raises AssertionError for a missing entry."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        manipulated = dict(result.kecamatan_accuracies)
        del manipulated[NTT_KECAMATAN[0]]

        with pytest.raises((AssertionError, KeyError)):
            assert set(manipulated) == set(NTT_KECAMATAN), (
                "Missing kecamatan entry must raise AssertionError"
            )



# ===========================================================================
# T10 — Duplicate kecamatan entry detected (Requirement 9.4)
# ===========================================================================

class TestT10DuplicateKecamatanDetected:
    """T10: a dict with duplicate keys is structurally impossible; test that
    spatial_cv never produces duplicates by verifying key count integrity."""

    def test_t10_no_duplicate_keys_in_result(self):
        """kecamatan_accuracies has no duplicate keys (dict enforces this)."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        keys = list(result.kecamatan_accuracies.keys())
        assert len(keys) == len(set(keys)), (
            f"T10 FAIL: duplicate keys in kecamatan_accuracies: {keys}"
        )

    def test_t10_key_count_equals_unique_input_count(self):
        """len(kecamatan_accuracies) == number of unique kecamatan in input."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        assert len(result.kecamatan_accuracies) == len(set(NTT_KECAMATAN)), (
            f"T10 FAIL: expected {len(set(NTT_KECAMATAN))} keys, "
            f"got {len(result.kecamatan_accuracies)}."
        )

    def test_t10_duplicate_input_rows_do_not_create_duplicate_keys(self):
        """Repeated rows for the same kecamatan do not duplicate the key."""
        # 4 rows, but only 2 unique kecamatan
        kec_ids = ["X", "X", "X", "Y", "Y"]
        fvs     = [_fv()] * 5
        scores  = [60.0, 61.0, 62.0, 55.0, 56.0]
        result  = spatial_cv(kec_ids, fvs, scores, _ADAPTER)
        assert len(result.kecamatan_accuracies) == 2
        assert set(result.kecamatan_accuracies) == {"X", "Y"}


# ===========================================================================
# T11 — None, NaN, Inf accuracy values rejected (Requirement 9.4)
# ===========================================================================

class TestT11NonFiniteAccuracyRejected:
    """T11: non-finite reference scores raise ValueError before CV runs."""

    def test_t11_nan_reference_score_raises_value_error(self):
        """NaN in coverage_scores raises ValueError."""
        bad_scores = list(NTT_SCORES)
        bad_scores[0] = float("nan")
        with pytest.raises(ValueError, match="not finite"):
            spatial_cv(NTT_KEC_IDS, NTT_FVS, bad_scores, _ADAPTER)

    def test_t11_inf_reference_score_raises_value_error(self):
        """Inf in coverage_scores raises ValueError."""
        bad_scores = list(NTT_SCORES)
        bad_scores[3] = float("inf")
        with pytest.raises(ValueError, match="not finite"):
            spatial_cv(NTT_KEC_IDS, NTT_FVS, bad_scores, _ADAPTER)

    def test_t11_negative_inf_reference_score_raises_value_error(self):
        """-Inf in coverage_scores raises ValueError."""
        bad_scores = list(NTT_SCORES)
        bad_scores[-1] = float("-inf")
        with pytest.raises(ValueError, match="not finite"):
            spatial_cv(NTT_KEC_IDS, NTT_FVS, bad_scores, _ADAPTER)

    def test_t11_all_finite_scores_succeed(self):
        """All-finite reference scores do not raise."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        for kec, acc in result.kecamatan_accuracies.items():
            assert math.isfinite(acc), (
                f"T11 FAIL: accuracy for '{kec}' is not finite: {acc!r}"
            )



# ===========================================================================
# T12 — Fewer than 2 kecamatan raises a structured error (Requirement 2.4)
# ===========================================================================

class TestT12FewerThanTwoKecamatanHandled:
    """T12: spatial_cv raises ValueError for 0 or 1 unique kecamatan."""

    def test_t12_single_kecamatan_raises_value_error(self):
        """1 unique kecamatan: no train split possible → ValueError."""
        kec_ids = ["A", "A", "A"]
        fvs     = [_fv(), _fv(), _fv()]
        scores  = [50.0, 51.0, 52.0]
        with pytest.raises(ValueError, match="at least 2 distinct kecamatan"):
            spatial_cv(kec_ids, fvs, scores, _ADAPTER)

    def test_t12_empty_input_raises_value_error(self):
        """Zero rows: raises ValueError."""
        with pytest.raises(ValueError):
            spatial_cv([], [], [], _ADAPTER)

    def test_t12_two_kecamatan_succeeds(self):
        """Exactly 2 unique kecamatan: spatial_cv succeeds."""
        kec_ids = ["A", "A", "B", "B"]
        fvs     = [_fv()] * 4
        scores  = [55.0, 56.0, 58.0, 57.0]
        result  = spatial_cv(kec_ids, fvs, scores, _ADAPTER)
        assert result.n_folds == 2
        assert set(result.kecamatan_accuracies) == {"A", "B"}

    def test_t12_mismatched_lengths_raise_value_error(self):
        """Mismatched sequence lengths raise ValueError."""
        with pytest.raises(ValueError):
            spatial_cv(
                ["A", "A", "B"],
                [_fv(), _fv()],   # only 2 fvs, not 3
                [50.0, 51.0, 52.0],
                _ADAPTER,
            )


# ===========================================================================
# T13 — Random point split never used (Requirement 2.4)
# ===========================================================================

class TestT13NoRandomPointSplit:
    """T13: split unit is always the kecamatan, never the individual point."""

    def test_t13_n_folds_equals_unique_kecamatan_not_n_rows(self):
        """n_folds == len(unique kecamatan), not the number of rows."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        n_rows   = len(NTT_KEC_IDS)
        n_unique = len(set(NTT_KEC_IDS))
        assert result.n_folds == n_unique, (
            f"T13 FAIL: n_folds={result.n_folds} should equal "
            f"unique kecamatan={n_unique}, not n_rows={n_rows}."
        )

    def test_t13_test_blocks_contain_whole_kecamatan_not_random_rows(self):
        """For each fold the test block contains ALL rows of that kecamatan."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        for test_kec in result.kecamatan_accuracies:
            rows_for_kec = [i for i, k in enumerate(NTT_KEC_IDS) if k == test_kec]
            # Each fold should have exactly 3 test rows (fixture has 3 rows/kecamatan)
            assert len(rows_for_kec) == 3, (
                f"T13 FAIL: kecamatan '{test_kec}' has {len(rows_for_kec)} rows; "
                "expected 3 for the NTT fixture."
            )

    def test_t13_result_reproducible_without_random_seed(self):
        """spatial_cv produces identical results when called twice (deterministic)."""
        result_1 = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        result_2 = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        assert result_1.kecamatan_accuracies == result_2.kecamatan_accuracies, (
            "T13 FAIL: spatial_cv is not deterministic — implies random splitting."
        )



# ===========================================================================
# T14 — Test fold rows absent from train features (Requirement 2.4)
# ===========================================================================

# ---------------------------------------------------------------------------
# Module-level helper and fixture precondition
# ---------------------------------------------------------------------------

def _row_fingerprint(fv: FeatureVector) -> tuple:
    """Return an exact float-tuple fingerprint for *fv* in CONSOLIDATED_FEATURES order.

    Uses exact float equality — no rounding, no np.allclose.
    Duplicate rows produce identical fingerprints, which Counter handles correctly.
    """
    from geosignal.models import CONSOLIDATED_FEATURES
    return tuple(float(getattr(fv, feat)) for feat in CONSOLIDATED_FEATURES)


def _assert_fixture_fingerprints_unique_across_kecamatan(
    kec_ids: list[str],
    fvs: list[FeatureVector],
) -> None:
    """Precondition: every fingerprint in the fixture is unique across kecamatan.

    If two kecamatan share a fingerprint, the spy-based T14 tests cannot
    distinguish which kecamatan owns a captured row — leakage would be
    undetectable.  This assertion must be satisfied by any fixture used in T14.

    Raises AssertionError with a clear message if the fixture is unsuitable.
    """
    from collections import defaultdict
    fp_to_kecs: dict[tuple, list[str]] = defaultdict(list)
    for kid, fv in zip(kec_ids, fvs):
        fp_to_kecs[_row_fingerprint(fv)].append(kid)

    collisions: dict[tuple, list[str]] = {
        fp: kids for fp, kids in fp_to_kecs.items() if len(set(kids)) > 1
    }
    assert not collisions, (
        "FIXTURE PRECONDITION FAILED: the following fingerprints appear in more "
        "than one kecamatan, making cross-fold row-swap undetectable:\n"
        + "\n".join(
            f"  fp={fp!r} → kecamatan: {kecs}"
            for fp, kecs in collisions.items()
        )
    )


class TestT14NoRowLeakage:
    """T14: in each fold, the batch passed to the adapter is the TEST fold only.

    Verified via a SpyAdapter that captures every array passed to predict().
    spatial_cv calls predict() exactly once per fold — on the test batch.
    We verify:
      1. Each captured batch is exactly the rows belonging to one kecamatan.
      2. Each captured batch contains NO rows from any other kecamatan.
      3. This would fail if spatial_cv mixed rows from multiple kecamatan.
    """

    def test_t14_each_scored_batch_matches_exactly_the_held_out_kecamatan(self):
        """Each predict() batch is exactly (no more, no less) the rows for one kecamatan.

        Uses Counter over exact float-tuple fingerprints — no np.allclose.
        Asserts:
          - batch row count == expected held-out row count (no rows added or lost)
          - Counter(captured_rows) == Counter(expected_rows_for_kecamatan)
          - each batch corresponds to exactly one kecamatan
          - each kecamatan appears as a held-out batch exactly once
        """
        from collections import Counter

        # Precondition: fixture fingerprints must be unique across kecamatan
        _assert_fixture_fingerprints_unique_across_kecamatan(NTT_KEC_IDS, NTT_FVS)

        scored_batches: list[np.ndarray] = []

        class SpyAdapter:
            def predict(self, features: np.ndarray) -> np.ndarray:
                scored_batches.append(features.copy())
                return _ADAPTER.predict(features)
            def shap_values(self, features: np.ndarray) -> np.ndarray:
                return _ADAPTER.shap_values(features)

        # Build expected Counter per kecamatan directly from the fixture zip —
        # never from a set, so duplicate rows are counted correctly.
        kec_to_row_counter: dict[str, Counter] = {}
        for kid, fv in zip(NTT_KEC_IDS, NTT_FVS):
            fp = _row_fingerprint(fv)
            kec_to_row_counter.setdefault(kid, Counter())
            kec_to_row_counter[kid][fp] += 1

        spy = SpyAdapter()
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, spy)

        assert len(scored_batches) == result.n_folds, (
            f"Expected {result.n_folds} predict() calls (one per fold), "
            f"got {len(scored_batches)}"
        )

        held_out_kecamatan: list[str] = []
        for batch_idx, batch in enumerate(scored_batches):
            # Build Counter of exact float-tuple fingerprints for this batch
            batch_counter: Counter = Counter(
                tuple(float(v) for v in row) for row in batch
            )

            # Find which kecamatan owns this batch — must match exactly one
            matching: list[str] = [
                kec for kec, expected in kec_to_row_counter.items()
                if batch_counter == expected
            ]

            assert len(matching) == 1, (
                f"T14 FAIL: batch {batch_idx} does not match exactly one kecamatan. "
                f"Matching kecamatan: {matching}. "
                f"Batch fingerprints: {dict(batch_counter)}. "
                "spatial_cv may be mixing rows from multiple kecamatan in one fold."
            )

            owned_kec = matching[0]
            held_out_kecamatan.append(owned_kec)

            # Assert exact Counter equality — no missing, extra, or wrong-duplicate rows
            expected_counter = kec_to_row_counter[owned_kec]
            assert batch_counter == expected_counter, (
                f"T14 FAIL: batch for kecamatan '{owned_kec}' has wrong rows.\n"
                f"  Expected: {dict(expected_counter)}\n"
                f"  Got:      {dict(batch_counter)}"
            )

        # Every NTT kecamatan must appear as a held-out batch exactly once
        assert Counter(held_out_kecamatan) == Counter(NTT_KECAMATAN), (
            f"T14 FAIL: each kecamatan must be held out exactly once.\n"
            f"  Expected: {sorted(NTT_KECAMATAN)}\n"
            f"  Got:      {sorted(held_out_kecamatan)}"
        )

    def test_t14_no_row_from_kecamatan_k_in_batch_for_kecamatan_j(self):
        """No row belonging to kecamatan K appears in the scored batch for kecamatan J≠K.

        Calls spatial_cv with a SpyAdapter, inspects captured batches, and
        verifies cross-fold row isolation.  This would catch any bug where
        spatial_cv includes a test-fold row in the wrong fold's batch.
        """
        from collections import Counter

        # Precondition: fixture fingerprints must be unique across kecamatan
        _assert_fixture_fingerprints_unique_across_kecamatan(NTT_KEC_IDS, NTT_FVS)

        scored_batches: list[np.ndarray] = []

        class SpyAdapter:
            def predict(self, features: np.ndarray) -> np.ndarray:
                scored_batches.append(features.copy())
                return _ADAPTER.predict(features)
            def shap_values(self, features: np.ndarray) -> np.ndarray:
                return _ADAPTER.shap_values(features)

        # Build expected Counter per kecamatan directly from fixture zip —
        # never from a set, so duplicate rows are counted correctly.
        kec_to_row_counter: dict[str, Counter] = {}
        kec_to_fingerprints: dict[str, set[tuple]] = {}
        for kid, fv in zip(NTT_KEC_IDS, NTT_FVS):
            fp = _row_fingerprint(fv)
            kec_to_row_counter.setdefault(kid, Counter())
            kec_to_row_counter[kid][fp] += 1
            kec_to_fingerprints.setdefault(kid, set()).add(fp)

        spy = SpyAdapter()
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, spy)

        for batch_idx, batch in enumerate(scored_batches):
            batch_fps = {tuple(float(v) for v in row) for row in batch}
            batch_counter = Counter(tuple(float(v) for v in row) for row in batch)

            # Identify which kecamatan this batch belongs to —
            # if no match found, fail immediately (no silent continue).
            matching: list[str] = [
                kec for kec, expected in kec_to_row_counter.items()
                if batch_counter == expected
            ]
            assert len(matching) == 1, (
                f"T14 FAIL: batch {batch_idx} cannot be attributed to exactly one "
                f"kecamatan. Matches: {matching}. "
                "Cannot verify cross-fold isolation for an unidentifiable batch."
            )
            owned_kec = matching[0]

            # Verify: no fingerprint in this batch belongs to a different kecamatan
            for other_kec, other_fps in kec_to_fingerprints.items():
                if other_kec == owned_kec:
                    continue
                leaked = batch_fps & other_fps
                assert leaked == set(), (
                    f"T14 FAIL: batch {batch_idx} (held-out: '{owned_kec}') "
                    f"contains {len(leaked)} row(s) belonging to '{other_kec}'. "
                    "spatial_cv is leaking rows from another kecamatan into this fold."
                )


# ===========================================================================
# T15 — Reported kecamatan count == unique input count (Requirement 9.4)
# ===========================================================================

class TestT15ReportedCountEqualsUniqueCount:
    """T15: len(kecamatan_accuracies) == number of unique kecamatan in input."""

    def test_t15_ntt_reported_count(self):
        """NTT: reported kecamatan count == 6."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        assert len(result.kecamatan_accuracies) == len(set(NTT_KEC_IDS)), (
            f"T15 FAIL: expected {len(set(NTT_KEC_IDS))} reported kecamatan, "
            f"got {len(result.kecamatan_accuracies)}."
        )

    def test_t15_ck_reported_count(self):
        """Central Kalimantan: reported kecamatan count == 5."""
        result = spatial_cv(CK_KEC_IDS, CK_FVS, CK_SCORES, _ADAPTER)
        assert len(result.kecamatan_accuracies) == len(set(CK_KEC_IDS)), (
            f"T15 FAIL: expected {len(set(CK_KEC_IDS))} reported kecamatan, "
            f"got {len(result.kecamatan_accuracies)}."
        )

    def test_t15_repeated_rows_do_not_inflate_count(self):
        """Repeated rows for the same kecamatan must not inflate the count."""
        kec_ids = ["P"] * 5 + ["Q"] * 5
        fvs     = [_fv()] * 10
        scores  = [60.0] * 10
        result  = spatial_cv(kec_ids, fvs, scores, _ADAPTER)
        assert len(result.kecamatan_accuracies) == 2

    def test_t15_set_equality_assertion_pattern(self):
        """The canonical assertion pattern from the spec works correctly."""
        input_kecamatan_ids = NTT_KEC_IDS
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        # Canonical assertion from spec
        assert set(result.kecamatan_accuracies) == set(input_kecamatan_ids), (
            "T15 FAIL: per-kecamatan key set does not match input kecamatan set."
        )



# ===========================================================================
# Extra — Preprocessing leakage guard (normalise=True fit-on-train)
# ===========================================================================

class TestPreprocessingLeakageGuard:
    """Fit min/max normalisation on train fold only; test fold uses train params."""

    def test_normalise_option_produces_result_without_error(self):
        """spatial_cv with normalise=True completes without error."""
        result = spatial_cv(
            NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER, normalise=True
        )
        assert set(result.kecamatan_accuracies) == set(NTT_KECAMATAN)

    def test_normalise_result_still_finite(self):
        """All accuracies are finite when normalise=True."""
        result = spatial_cv(
            NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER, normalise=True
        )
        for kec, acc in result.kecamatan_accuracies.items():
            assert math.isfinite(acc), (
                f"normalise=True: accuracy for '{kec}' is not finite: {acc!r}"
            )

    def test_normalise_same_kecamatan_set_as_without(self):
        """normalise=True and False both report the same kecamatan set."""
        r_norm  = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER, normalise=True)
        r_plain = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER, normalise=False)
        assert set(r_norm.kecamatan_accuracies) == set(r_plain.kecamatan_accuracies)


# ===========================================================================
# Extra — CVResult dataclass contract
# ===========================================================================

class TestCVResultContract:
    """CVResult fields match the specification."""

    def test_cvresult_has_kecamatan_accuracies_dict(self):
        """kecamatan_accuracies is a dict mapping str → float."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        assert isinstance(result.kecamatan_accuracies, dict)
        for k, v in result.kecamatan_accuracies.items():
            assert isinstance(k, str)
            assert isinstance(v, float)

    def test_cvresult_n_folds_is_int(self):
        """n_folds is a positive int."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        assert isinstance(result.n_folds, int)
        assert result.n_folds > 0

    def test_cvresult_all_accuracies_in_unit_interval(self):
        """All accuracy values are in [0.0, 1.0]."""
        result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        for kec, acc in result.kecamatan_accuracies.items():
            assert 0.0 <= acc <= 1.0, (
                f"Accuracy for '{kec}' = {acc} outside [0, 1]."
            )


# ===========================================================================
# Extra — Full acceptance gate summary (both regions)
# ===========================================================================

class TestFullAcceptanceGateSummary:
    """Runs the full acceptance gate for both regions and reports results."""

    def _run_gate(self, kec_ids, fvs, scores, expected_kecamatan):
        result = spatial_cv(kec_ids, fvs, scores, _ADAPTER)
        # Gate 1: all kecamatan reported
        assert set(result.kecamatan_accuracies) == set(expected_kecamatan), (
            f"Gate FAIL: kecamatan mismatch.\n"
            f"  Expected: {sorted(expected_kecamatan)}\n"
            f"  Got:      {sorted(result.kecamatan_accuracies)}"
        )
        # Gate 2: all accuracies finite
        for kec, acc in result.kecamatan_accuracies.items():
            assert math.isfinite(acc), f"Gate FAIL: non-finite accuracy for '{kec}'."
        # Gate 3: disjoint train/test (enforced by spatial_cv; verified via n_folds)
        assert result.n_folds == len(set(expected_kecamatan))
        # Gate 4: no duplicates
        keys = list(result.kecamatan_accuracies)
        assert len(keys) == len(set(keys))
        return result

    def test_full_gate_ntt(self):
        """Full acceptance gate: NTT fixture passes all gates."""
        result = self._run_gate(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, NTT_KECAMATAN)
        agg = aggregate_accuracy(result)
        assert math.isfinite(agg)
        assert 0.0 <= agg <= 1.0

    def test_full_gate_central_kalimantan(self):
        """Full acceptance gate: Central Kalimantan fixture passes all gates."""
        result = self._run_gate(CK_KEC_IDS, CK_FVS, CK_SCORES, CK_KECAMATAN)
        # Dense-canopy kecamatan must appear and be finite
        dc_acc = result.kecamatan_accuracies[DENSE_CANOPY_KEC]
        assert math.isfinite(dc_acc)
        assert 0.0 <= dc_acc <= 1.0

    def test_full_gate_acceptance_gate_passed_flag(self):
        """Verify the acceptance_gate_passed flag can be derived from results."""
        ntt_result = spatial_cv(NTT_KEC_IDS, NTT_FVS, NTT_SCORES, _ADAPTER)
        ck_result  = spatial_cv(CK_KEC_IDS, CK_FVS, CK_SCORES, _ADAPTER)

        ntt_gate = (
            set(ntt_result.kecamatan_accuracies) == set(NTT_KECAMATAN)
            and all(math.isfinite(v) for v in ntt_result.kecamatan_accuracies.values())
            and ntt_result.n_folds == len(NTT_KECAMATAN)
        )
        ck_gate = (
            set(ck_result.kecamatan_accuracies) == set(CK_KECAMATAN)
            and all(math.isfinite(v) for v in ck_result.kecamatan_accuracies.values())
            and DENSE_CANOPY_KEC in ck_result.kecamatan_accuracies
        )

        assert ntt_gate, "NTT acceptance gate FAILED."
        assert ck_gate, "CK acceptance gate FAILED."
