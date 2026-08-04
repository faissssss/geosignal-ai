"""Tests for model versioning and scoring-run auditability."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from geosignal.adapters import AHPAdapter
from geosignal.models import (
    CONSOLIDATED_FEATURES,
    FeatureVector,
)
from geosignal.scoring import ModelTier
from geosignal.versioning import (
    RETENTION_MONTHS,
    InMemoryAuditStore,
    assign_model_version,
    build_input_checksums,
    log_scoring_run,
    score_with_registered_model,
)


def _baseline() -> dict[str, float]:
    return {
        feature: float(index + 1)
        for index, feature
        in enumerate(CONSOLIDATED_FEATURES)
    }


def _feature_vector() -> FeatureVector:
    return FeatureVector(
        elevation_m=100.0,
        slope_deg=5.0,
        land_cover_class=40,
        canopy_height_m=2.0,
        distance_to_bts_m=4_000.0,
        road_distance_m=500.0,
        population_density_per_km2=250.0,
        facility_proximity_m=700.0,
    )


def _register_ahp(
    store: InMemoryAuditStore,
) -> dict:
    return assign_model_version(
        algorithm="AHP",
        tier=ModelTier.TIER1,
        artifact_path="models/ahp/weights.json",
        training_run_id=uuid4(),
        store=store,
    )


def _checksum_bundle(
    *,
    include_baseline: bool = True,
) -> dict:
    return build_input_checksums(
        {
            "srtm_dem": b"dem-content",
            "worldpop": b"population-content",
            "worldcover": b"land-cover-content",
        },
        regional_baseline=(
            _baseline()
            if include_baseline
            else None
        ),
    )


def _log_run(
    store: InMemoryAuditStore,
    artifact: dict,
    *,
    timestamp: datetime | None = None,
    run_id=None,
) -> dict:
    return log_scoring_run(
        model_version=artifact["version_id"],
        tier=artifact["tier"],
        region_kecamatans=[
            "NTT-KUPANG-01",
            "NTT-KUPANG-02",
        ],
        resolution_m=250,
        input_checksums=_checksum_bundle(),
        candidate_count=10,
        store=store,
        timestamp=timestamp,
        run_id=run_id,
    )


def test_first_model_version_is_semantic_and_persisted() -> None:
    store = InMemoryAuditStore()

    artifact = _register_ahp(store)

    assert artifact["version_id"] == "ahp-v1.0.0"
    assert artifact["tier"] == "1"
    assert artifact["algorithm"] == "AHP"
    assert artifact["artifact_path"]
    assert artifact["training_run_id"]
    assert artifact["created_at"]

    assert store.get_model_artifact(
        artifact["version_id"]
    ) == artifact


def test_sequential_versions_increment_without_overwrite() -> None:
    store = InMemoryAuditStore()

    first = assign_model_version(
        algorithm="XGBoost",
        tier="2",
        artifact_path="models/xgb/model-1.json",
        training_run_id=uuid4(),
        store=store,
    )
    first_snapshot = deepcopy(first)

    second = assign_model_version(
        algorithm="XGBoost",
        tier="2",
        artifact_path="models/xgb/model-2.json",
        training_run_id=uuid4(),
        store=store,
    )

    assert first["version_id"] == "xgb-v1.0.0"
    assert second["version_id"] == "xgb-v1.0.1"
    assert len(store.model_artifacts) == 2

    assert store.get_model_artifact(
        first["version_id"]
    ) == first_snapshot


def test_duplicate_requested_version_is_rejected() -> None:
    store = InMemoryAuditStore()

    assign_model_version(
        algorithm="LightGBM",
        tier="2",
        artifact_path="models/lgbm/model-1.txt",
        training_run_id=uuid4(),
        requested_version="lgbm-v2.1.0",
        store=store,
    )

    with pytest.raises(
        ValueError,
        match="already exists",
    ):
        assign_model_version(
            algorithm="LightGBM",
            tier="2",
            artifact_path="models/lgbm/model-2.txt",
            training_run_id=uuid4(),
            requested_version="lgbm-v2.1.0",
            store=store,
        )


def test_model_artifact_delete_is_forbidden() -> None:
    store = InMemoryAuditStore()
    artifact = _register_ahp(store)

    with pytest.raises(
        PermissionError,
        match="immutable",
    ):
        store.delete_model_artifact(
            artifact["version_id"]
        )


def test_score_requires_registered_model_version() -> None:
    store = InMemoryAuditStore()

    class SpyAdapter:
        def __init__(self) -> None:
            self.called = False

        def predict(self, features):
            self.called = True
            return np.array([50.0])

    adapter = SpyAdapter()

    with pytest.raises(
        ValueError,
        match="persisted before scoring",
    ):
        score_with_registered_model(
            _feature_vector(),
            adapter,
            model_version="ahp-v9.9.9",
            store=store,
        )

    assert adapter.called is False


def test_score_with_registered_version_calls_scoring() -> None:
    store = InMemoryAuditStore()
    artifact = _register_ahp(store)

    score = score_with_registered_model(
        _feature_vector(),
        AHPAdapter(),
        model_version=artifact["version_id"],
        store=store,
    )

    assert isinstance(score, float)
    assert 0.0 <= score <= 100.0


def test_checksum_bundle_is_deterministic_and_stores_baseline() -> None:
    first = _checksum_bundle()
    second = _checksum_bundle()

    assert first == second

    assert set(first["sources"]) == {
        "srtm_dem",
        "worldpop",
        "worldcover",
    }

    assert all(
        len(checksum) == 64
        for checksum in first["sources"].values()
    )

    assert first["regional_baseline"] == _baseline()


def test_scoring_run_persists_all_required_fields() -> None:
    store = InMemoryAuditStore()
    artifact = _register_ahp(store)

    run = _log_run(store, artifact)

    required_fields = {
        "run_id",
        "model_version",
        "tier",
        "region_kecamatans",
        "resolution_m",
        "input_checksums",
        "candidate_count",
        "timestamp",
        "retained_for_months",
    }

    assert set(run) == required_fields

    assert all(
        run[field] is not None
        for field in required_fields
    )

    assert run["model_version"] == artifact["version_id"]
    assert run["retained_for_months"] == 12
    assert run["input_checksums"]["regional_baseline"]


def test_tier1_scoring_log_requires_regional_baseline() -> None:
    store = InMemoryAuditStore()
    artifact = _register_ahp(store)

    with pytest.raises(
        ValueError,
        match="regional baseline",
    ):
        log_scoring_run(
            model_version=artifact["version_id"],
            tier="1",
            region_kecamatans=["NTT-KUPANG-01"],
            resolution_m=250,
            input_checksums=_checksum_bundle(
                include_baseline=False
            ),
            candidate_count=5,
            store=store,
        )


def test_duplicate_scoring_run_id_is_rejected() -> None:
    store = InMemoryAuditStore()
    artifact = _register_ahp(store)
    run_id = uuid4()

    _log_run(
        store,
        artifact,
        run_id=run_id,
    )

    with pytest.raises(
        ValueError,
        match="already exists",
    ):
        _log_run(
            store,
            artifact,
            run_id=run_id,
        )


def test_recent_scoring_run_cannot_be_deleted() -> None:
    store = InMemoryAuditStore()
    artifact = _register_ahp(store)
    now = datetime(
        2026,
        8,
        4,
        3,
        0,
        tzinfo=timezone.utc,
    )

    run = _log_run(
        store,
        artifact,
        timestamp=now - timedelta(days=30),
    )

    with pytest.raises(
        PermissionError,
        match="younger than",
    ):
        store.delete_scoring_run(
            run["run_id"],
            now=now,
        )

    assert store.get_scoring_run(
        run["run_id"]
    ) is not None


def test_old_scoring_run_can_be_deleted() -> None:
    store = InMemoryAuditStore()
    artifact = _register_ahp(store)
    now = datetime(
        2026,
        8,
        4,
        3,
        0,
        tzinfo=timezone.utc,
    )

    run = _log_run(
        store,
        artifact,
        timestamp=now - timedelta(days=370),
    )

    deleted = store.delete_scoring_run(
        run["run_id"],
        now=now,
    )

    assert deleted is True

    assert store.get_scoring_run(
        run["run_id"]
    ) is None


def test_schema_contains_twelve_month_retention_trigger() -> None:
    repository_root = Path(__file__).resolve().parents[1]

    migration_path = (
        repository_root
        / "infra"
        / "migrations"
        / "001_initial_schema.sql"
    )

    sql = migration_path.read_text(
        encoding="utf-8"
    ).lower()

    assert "prevent_recent_scoring_run_delete" in sql
    assert "before delete on scoring_runs" in sql
    assert "interval '12 months'" in sql
    assert "trg_scoring_runs_retention" in sql


# Feature: geosignal-ai, Property 21:
# Model Version Assignment Before Use
@settings(max_examples=100, deadline=None)
@given(
    algorithm_and_tier=st.sampled_from(
        [
            ("AHP", "1"),
            ("XGBoost", "2"),
            ("LightGBM", "2"),
        ]
    )
)
def test_property_21_model_version_assignment_before_use(
    algorithm_and_tier,
) -> None:
    algorithm, tier = algorithm_and_tier
    store = InMemoryAuditStore()

    artifact = assign_model_version(
        algorithm=algorithm,
        tier=tier,
        artifact_path=(
            f"models/{algorithm.lower()}/artifact.bin"
        ),
        training_run_id=uuid4(),
        store=store,
    )

    observed: dict[str, bool] = {}

    def guarded_score(features, adapter) -> float:
        observed["registered_before_call"] = (
            store.get_model_artifact(
                artifact["version_id"]
            )
            is not None
        )
        return 50.0

    result = score_with_registered_model(
        _feature_vector(),
        object(),
        model_version=artifact["version_id"],
        store=store,
        score_fn=guarded_score,
    )

    assert observed["registered_before_call"] is True
    assert result == 50.0


# Feature: geosignal-ai, Property 16:
# Scoring Run Log Completeness
@settings(max_examples=100, deadline=None)
@given(
    resolution_m=st.integers(
        min_value=50,
        max_value=2_000,
    ),
    candidate_count=st.integers(
        min_value=0,
        max_value=10_000,
    ),
    kecamatan_count=st.integers(
        min_value=1,
        max_value=15,
    ),
)
def test_property_16_scoring_run_log_completeness(
    resolution_m: int,
    candidate_count: int,
    kecamatan_count: int,
) -> None:
    store = InMemoryAuditStore()
    artifact = _register_ahp(store)

    run = log_scoring_run(
        model_version=artifact["version_id"],
        tier="1",
        region_kecamatans=[
            f"kec_{index:03d}"
            for index in range(kecamatan_count)
        ],
        resolution_m=resolution_m,
        input_checksums=_checksum_bundle(),
        candidate_count=candidate_count,
        store=store,
    )

    required_fields = {
        "run_id",
        "model_version",
        "tier",
        "region_kecamatans",
        "resolution_m",
        "input_checksums",
        "candidate_count",
        "timestamp",
        "retained_for_months",
    }

    assert all(
        field in run and run[field] is not None
        for field in required_fields
    )

    assert run["region_kecamatans"]
    assert run["input_checksums"]["sources"]

    assert (
        run["input_checksums"]["regional_baseline"]
        is not None
    )

    assert run["retained_for_months"] == RETENTION_MONTHS


# Feature: geosignal-ai, Property 20:
# Model Artifact Immutability
@settings(max_examples=100, deadline=None)
@given(
    retraining_count=st.integers(
        min_value=1,
        max_value=20,
    )
)
def test_property_20_model_artifact_immutability(
    retraining_count: int,
) -> None:
    store = InMemoryAuditStore()
    snapshots: dict[str, dict] = {}

    for index in range(retraining_count):
        before_count = len(store.model_artifacts)

        artifact = assign_model_version(
            algorithm="XGBoost",
            tier="2",
            artifact_path=(
                f"models/xgb/retraining-{index}.json"
            ),
            training_run_id=uuid4(),
            store=store,
        )

        assert len(store.model_artifacts) == (
            before_count + 1
        )

        snapshots[artifact["version_id"]] = deepcopy(
            artifact
        )

        for version_id, snapshot in snapshots.items():
            assert store.get_model_artifact(
                version_id
            ) == snapshot

    assert len(store.model_artifacts) == retraining_count