"""Model versioning and scoring-run audit utilities for GeoSignal AI.

Every model artifact receives an immutable semantic version before it can
produce a Coverage Score. Every batch scoring run records reproducibility
metadata and is retained for at least twelve months.
"""

from __future__ import annotations

import hashlib
import re
from calendar import monthrange
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

import numpy as np

from geosignal.models import CONSOLIDATED_FEATURES, FeatureVector
from geosignal.scoring import ModelTier, compute_coverage_score


RETENTION_MONTHS: int = 12

_SEMANTIC_VERSION_PATTERN = re.compile(
    r"^(?P<prefix>[a-z0-9]+)-v"
    r"(?P<major>\d+)\."
    r"(?P<minor>\d+)\."
    r"(?P<patch>\d+)$"
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_ALGORITHM_ALIASES: dict[str, tuple[str, str]] = {
    "ahp": ("AHP", "ahp"),
    "xgboost": ("XGBoost", "xgb"),
    "xgb": ("XGBoost", "xgb"),
    "lightgbm": ("LightGBM", "lgbm"),
    "lgbm": ("LightGBM", "lgbm"),
    "gnn": ("GNN", "gnn"),
}


class AuditStore(Protocol):
    """Persistence contract used by model versioning and scoring logs."""

    def list_model_artifacts(
        self,
        algorithm: str | None = None,
    ) -> list[dict[str, Any]]:
        ...

    def get_model_artifact(
        self,
        version_id: str,
    ) -> dict[str, Any] | None:
        ...

    def insert_model_artifact(
        self,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        ...

    def insert_scoring_run(
        self,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        ...

    def get_scoring_run(
        self,
        run_id: str,
    ) -> dict[str, Any] | None:
        ...

    def delete_scoring_run(
        self,
        run_id: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        ...


class InMemoryAuditStore:
    """Deterministic local store used for tests and offline development.

    Model artifacts are append-only. Scoring-run deletion follows the same
    twelve-month rule enforced by the PostgreSQL trigger.
    """

    def __init__(self) -> None:
        self._model_artifacts: dict[str, dict[str, Any]] = {}
        self._scoring_runs: dict[str, dict[str, Any]] = {}

    @property
    def model_artifacts(self) -> list[dict[str, Any]]:
        return [
            deepcopy(record)
            for record in self._model_artifacts.values()
        ]

    @property
    def scoring_runs(self) -> list[dict[str, Any]]:
        return [
            deepcopy(record)
            for record in self._scoring_runs.values()
        ]

    def list_model_artifacts(
        self,
        algorithm: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.model_artifacts

        if algorithm is None:
            return rows

        return [
            row
            for row in rows
            if row["algorithm"] == algorithm
        ]

    def get_model_artifact(
        self,
        version_id: str,
    ) -> dict[str, Any] | None:
        record = self._model_artifacts.get(version_id)
        return None if record is None else deepcopy(record)

    def insert_model_artifact(
        self,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        version_id = str(record["version_id"])

        if version_id in self._model_artifacts:
            raise ValueError(
                f"Model version already exists: {version_id}"
            )

        stored = deepcopy(dict(record))
        self._model_artifacts[version_id] = stored
        return deepcopy(stored)

    def delete_model_artifact(
        self,
        version_id: str,
    ) -> None:
        """Artifacts are immutable and can never be deleted."""
        raise PermissionError(
            f"Model artifact {version_id} is immutable"
        )

    def insert_scoring_run(
        self,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        run_id = str(record["run_id"])

        if run_id in self._scoring_runs:
            raise ValueError(
                f"Scoring run already exists: {run_id}"
            )

        stored = deepcopy(dict(record))
        self._scoring_runs[run_id] = stored
        return deepcopy(stored)

    def get_scoring_run(
        self,
        run_id: str,
    ) -> dict[str, Any] | None:
        record = self._scoring_runs.get(run_id)
        return None if record is None else deepcopy(record)

    def delete_scoring_run(
        self,
        run_id: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        record = self._scoring_runs.get(run_id)

        if record is None:
            return False

        reference_time = (
            datetime.now(timezone.utc)
            if now is None
            else _ensure_aware_datetime(now)
        )

        timestamp = _parse_timestamp(record["timestamp"])
        retention_months = int(record["retained_for_months"])

        cutoff = _subtract_months(
            reference_time,
            retention_months,
        )

        # Mirrors the SQL trigger:
        # timestamp > NOW() - INTERVAL '12 months'
        if timestamp > cutoff:
            raise PermissionError(
                "Cannot delete a scoring run younger than "
                f"{retention_months} months"
            )

        del self._scoring_runs[run_id]
        return True


class SupabaseAuditStore:
    """Supabase implementation of the audit persistence contract."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def list_model_artifacts(
        self,
        algorithm: str | None = None,
    ) -> list[dict[str, Any]]:
        query = (
            self.client
            .table("model_artifacts")
            .select("*")
        )

        if algorithm is not None:
            query = query.eq("algorithm", algorithm)

        return _response_rows(query.execute())

    def get_model_artifact(
        self,
        version_id: str,
    ) -> dict[str, Any] | None:
        response = (
            self.client
            .table("model_artifacts")
            .select("*")
            .eq("version_id", version_id)
            .limit(1)
            .execute()
        )

        rows = _response_rows(response)
        return rows[0] if rows else None

    def insert_model_artifact(
        self,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        response = (
            self.client
            .table("model_artifacts")
            .insert(dict(record))
            .execute()
        )

        rows = _response_rows(response)
        return rows[0] if rows else dict(record)

    def insert_scoring_run(
        self,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        response = (
            self.client
            .table("scoring_runs")
            .insert(dict(record))
            .execute()
        )

        rows = _response_rows(response)
        return rows[0] if rows else dict(record)

    def get_scoring_run(
        self,
        run_id: str,
    ) -> dict[str, Any] | None:
        response = (
            self.client
            .table("scoring_runs")
            .select("*")
            .eq("run_id", run_id)
            .limit(1)
            .execute()
        )

        rows = _response_rows(response)
        return rows[0] if rows else None

    def delete_scoring_run(
        self,
        run_id: str,
        *,
        now: datetime | None = None,
    ) -> bool:
        # Retention is enforced by the PostgreSQL trigger. A recent row
        # causes Supabase/PostgreSQL to raise a permission-style error.
        response = (
            self.client
            .table("scoring_runs")
            .delete()
            .eq("run_id", run_id)
            .execute()
        )

        return bool(_response_rows(response))


def assign_model_version(
    *,
    algorithm: str,
    tier: ModelTier | str | int,
    artifact_path: str,
    training_run_id: str | UUID,
    store: AuditStore,
    requested_version: str | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Assign and persist an immutable semantic model version.

    Automatically generated versions use:

    ``<algorithm-prefix>-v<major>.<minor>.<patch>``

    Examples: ``ahp-v1.0.0`` and ``xgb-v1.0.2``.
    """
    canonical_algorithm, prefix = _normalise_algorithm(
        algorithm
    )
    normalised_tier = _normalise_tier(tier)

    _validate_algorithm_tier(
        canonical_algorithm,
        normalised_tier,
    )

    path = str(artifact_path).strip()

    if not path:
        raise ValueError("artifact_path cannot be empty")

    training_id = _normalise_uuid(
        training_run_id,
        name="training_run_id",
    )

    existing = store.list_model_artifacts(
        canonical_algorithm
    )

    if requested_version is None:
        version_id = _next_semantic_version(
            prefix=prefix,
            existing_artifacts=existing,
        )
    else:
        version_id = str(requested_version).strip()
        _parse_semantic_version(
            version_id,
            expected_prefix=prefix,
        )

    if store.get_model_artifact(version_id) is not None:
        raise ValueError(
            f"Model version already exists: {version_id}"
        )

    record = {
        "version_id": version_id,
        "tier": normalised_tier,
        "algorithm": canonical_algorithm,
        "training_run_id": training_id,
        "artifact_path": path,
        "created_at": _utc_iso(created_at),
    }

    return store.insert_model_artifact(record)


def score_with_registered_model(
    features: FeatureVector,
    adapter: Any,
    *,
    model_version: str,
    store: AuditStore,
    score_fn: Callable[[FeatureVector, Any], float] = (
        compute_coverage_score
    ),
) -> float:
    """Score only after confirming that the model version is registered."""
    version_id = str(model_version).strip()

    if not version_id:
        raise ValueError(
            "model_version must be assigned before scoring"
        )

    if store.get_model_artifact(version_id) is None:
        raise ValueError(
            "Model version must be persisted before scoring: "
            f"{version_id}"
        )

    score = float(score_fn(features, adapter))

    if not np.isfinite(score):
        raise ValueError("Coverage Score must be finite")

    return score


def build_input_checksums(
    source_payloads: Mapping[
        str,
        bytes | bytearray | memoryview | str,
    ],
    *,
    regional_baseline: Mapping[str, float] | None = None,
    fallback_events: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the reproducibility payload stored in input_checksums.

    Each source payload is hashed with SHA-256. The AHP regional baseline
    is stored in the same JSON object so Tier 1 SHAP can be reproduced.
    """
    if not source_payloads:
        raise ValueError(
            "At least one input source is required"
        )

    checksums: dict[str, str] = {}

    for raw_name, payload in source_payloads.items():
        name = str(raw_name).strip()

        if not name:
            raise ValueError(
                "Input source names cannot be empty"
            )

        if isinstance(payload, str):
            content = payload.encode("utf-8")
        else:
            content = bytes(payload)

        checksums[name] = hashlib.sha256(
            content
        ).hexdigest()

    baseline = (
        None
        if regional_baseline is None
        else _validate_regional_baseline(
            regional_baseline
        )
    )

    return {
        "sources": dict(sorted(checksums.items())),
        "regional_baseline": baseline,
        "fallback_events": [
            deepcopy(dict(event))
            for event in (fallback_events or [])
        ],
    }


def log_scoring_run(
    *,
    model_version: str,
    tier: ModelTier | str | int,
    region_kecamatans: Sequence[str],
    resolution_m: int,
    input_checksums: Mapping[str, Any],
    candidate_count: int,
    store: AuditStore,
    run_id: str | UUID | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Persist one complete batch-scoring audit record."""
    version_id = str(model_version).strip()

    if not version_id:
        raise ValueError("model_version cannot be empty")

    if store.get_model_artifact(version_id) is None:
        raise ValueError(
            "model_version must reference a registered artifact"
        )

    normalised_tier = _normalise_tier(tier)
    kecamatans = _normalise_kecamatans(region_kecamatans)

    if (
        not isinstance(resolution_m, int)
        or isinstance(resolution_m, bool)
        or resolution_m <= 0
    ):
        raise ValueError(
            "resolution_m must be a positive integer"
        )

    if (
        not isinstance(candidate_count, int)
        or isinstance(candidate_count, bool)
        or candidate_count < 0
    ):
        raise ValueError(
            "candidate_count must be a non-negative integer"
        )

    checksum_payload = _validate_input_checksums(
        input_checksums
    )

    if (
        normalised_tier == ModelTier.TIER1.value
        and checksum_payload["regional_baseline"] is None
    ):
        raise ValueError(
            "Tier 1 scoring runs require a regional baseline"
        )

    normalised_run_id = (
        str(uuid4())
        if run_id is None
        else _normalise_uuid(run_id, name="run_id")
    )

    record = {
        "run_id": normalised_run_id,
        "model_version": version_id,
        "tier": normalised_tier,
        "region_kecamatans": kecamatans,
        "resolution_m": resolution_m,
        "input_checksums": checksum_payload,
        "candidate_count": candidate_count,
        "timestamp": _utc_iso(timestamp),
        "retained_for_months": RETENTION_MONTHS,
    }

    return store.insert_scoring_run(record)


def _next_semantic_version(
    *,
    prefix: str,
    existing_artifacts: Sequence[Mapping[str, Any]],
) -> str:
    parsed_versions: list[tuple[int, int, int]] = []

    for artifact in existing_artifacts:
        parsed_versions.append(
            _parse_semantic_version(
                str(artifact["version_id"]),
                expected_prefix=prefix,
            )
        )

    if not parsed_versions:
        next_parts = (1, 0, 0)
    else:
        major, minor, patch = max(parsed_versions)
        next_parts = (major, minor, patch + 1)

    return (
        f"{prefix}-v"
        f"{next_parts[0]}."
        f"{next_parts[1]}."
        f"{next_parts[2]}"
    )


def _parse_semantic_version(
    version_id: str,
    *,
    expected_prefix: str,
) -> tuple[int, int, int]:
    match = _SEMANTIC_VERSION_PATTERN.fullmatch(
        version_id
    )

    if match is None:
        raise ValueError(
            "version_id must use semantic format "
            "'<prefix>-vMAJOR.MINOR.PATCH'"
        )

    if match.group("prefix") != expected_prefix:
        raise ValueError(
            "version_id prefix does not match algorithm"
        )

    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )


def _normalise_algorithm(
    algorithm: str,
) -> tuple[str, str]:
    key = str(algorithm).strip().lower()

    try:
        return _ALGORITHM_ALIASES[key]
    except KeyError as exc:
        raise ValueError(
            "algorithm must be AHP, XGBoost, "
            "LightGBM, or GNN"
        ) from exc


def _normalise_tier(
    tier: ModelTier | str | int,
) -> str:
    raw_value = (
        tier.value
        if isinstance(tier, ModelTier)
        else str(tier)
    )

    value = raw_value.strip()

    if value not in {
        ModelTier.TIER1.value,
        ModelTier.TIER2.value,
    }:
        raise ValueError("tier must be '1' or '2'")

    return value


def _validate_algorithm_tier(
    algorithm: str,
    tier: str,
) -> None:
    if algorithm == "AHP" and tier != ModelTier.TIER1.value:
        raise ValueError("AHP must use Tier 1")

    if algorithm != "AHP" and tier != ModelTier.TIER2.value:
        raise ValueError(
            f"{algorithm} must use Tier 2"
        )


def _validate_regional_baseline(
    baseline: Mapping[str, float],
) -> dict[str, float]:
    expected = set(CONSOLIDATED_FEATURES)
    actual = set(baseline)

    if actual != expected:
        raise ValueError(
            "regional_baseline must contain exactly "
            "the eight CONSOLIDATED_FEATURES"
        )

    result = {
        feature: float(baseline[feature])
        for feature in CONSOLIDATED_FEATURES
    }

    if not np.isfinite(list(result.values())).all():
        raise ValueError(
            "regional_baseline values must be finite"
        )

    return result


def _validate_input_checksums(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise TypeError(
            "input_checksums must be a mapping"
        )

    sources = payload.get("sources")

    if not isinstance(sources, Mapping) or not sources:
        raise ValueError(
            "input_checksums.sources cannot be empty"
        )

    validated_sources: dict[str, str] = {}

    for raw_name, raw_digest in sources.items():
        name = str(raw_name).strip()
        digest = str(raw_digest).strip().lower()

        if not name:
            raise ValueError(
                "Checksum source names cannot be empty"
            )

        if _SHA256_PATTERN.fullmatch(digest) is None:
            raise ValueError(
                "Every source checksum must be a "
                "64-character SHA-256 hex digest"
            )

        validated_sources[name] = digest

    baseline_raw = payload.get("regional_baseline")

    baseline = (
        None
        if baseline_raw is None
        else _validate_regional_baseline(
            baseline_raw
        )
    )

    fallback_events_raw = payload.get(
        "fallback_events",
        [],
    )

    if not isinstance(
        fallback_events_raw,
        Sequence,
    ) or isinstance(
        fallback_events_raw,
        (str, bytes),
    ):
        raise ValueError(
            "fallback_events must be a sequence"
        )

    return {
        "sources": dict(
            sorted(validated_sources.items())
        ),
        "regional_baseline": baseline,
        "fallback_events": [
            deepcopy(dict(event))
            for event in fallback_events_raw
        ],
    }


def _normalise_kecamatans(
    values: Sequence[str],
) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise ValueError(
            "region_kecamatans must be a sequence"
        )

    result: list[str] = []
    seen: set[str] = set()

    for raw_value in values:
        value = str(raw_value).strip()

        if not value:
            raise ValueError(
                "Kecamatan identifiers cannot be empty"
            )

        if value not in seen:
            result.append(value)
            seen.add(value)

    if not result:
        raise ValueError(
            "At least one kecamatan is required"
        )

    return result


def _normalise_uuid(
    value: str | UUID,
    *,
    name: str,
) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(
            f"{name} must be a valid UUID"
        ) from exc


def _utc_iso(
    value: datetime | None,
) -> str:
    timestamp = (
        datetime.now(timezone.utc)
        if value is None
        else _ensure_aware_datetime(value)
    )

    return timestamp.astimezone(
        timezone.utc
    ).isoformat()


def _ensure_aware_datetime(
    value: datetime,
) -> datetime:
    if value.tzinfo is None:
        raise ValueError(
            "datetime values must include timezone information"
        )

    return value


def _parse_timestamp(
    value: str | datetime,
) -> datetime:
    if isinstance(value, datetime):
        return _ensure_aware_datetime(value)

    parsed = datetime.fromisoformat(
        str(value).replace("Z", "+00:00")
    )

    return _ensure_aware_datetime(parsed)


def _subtract_months(
    value: datetime,
    months: int,
) -> datetime:
    month_index = value.year * 12 + value.month - 1 - months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(value.day, monthrange(year, month)[1])

    return value.replace(
        year=year,
        month=month,
        day=day,
    )


def _response_rows(
    response: Any,
) -> list[dict[str, Any]]:
    if hasattr(response, "data"):
        data = response.data
    elif isinstance(response, Mapping):
        data = response.get("data", [])
    else:
        data = []

    return [
        dict(row)
        for row in (data or [])
    ]