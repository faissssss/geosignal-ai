"""Tests for the GeoSignal AI Ethical Risk Register."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from geosignal.ethics import (
    DEFAULT_RISK_ENTRIES,
    REQUIRED_RISK_IDS,
    EthicalRiskRegister,
    seed_ethical_risk_register,
)
from geosignal.models import EthicalRiskEntry


def test_register_contains_exactly_five_required_risks() -> None:
    register = EthicalRiskRegister()

    assert len(register) == 5
    assert register.risk_ids == REQUIRED_RISK_IDS
    assert set(register.risk_ids) == set(REQUIRED_RISK_IDS)


def test_all_required_fields_are_non_empty() -> None:
    register = EthicalRiskRegister()

    for entry in register:
        assert entry.risk_id.strip()
        assert entry.risk_description.strip()
        assert entry.impact.strip()
        assert entry.mitigation.strip()
        assert entry.responsible_owner_role.strip()


def test_register_lookup_returns_correct_entry() -> None:
    register = EthicalRiskRegister()

    entry = register.get(
        "opencellid_sparsity_misread"
    )

    assert isinstance(entry, EthicalRiskEntry)
    assert (
        entry.risk_id
        == "opencellid_sparsity_misread"
    )
    assert "OpenCellID" in entry.risk_description


def test_register_rejects_duplicate_risk_ids() -> None:
    duplicated = (
        list(DEFAULT_RISK_ENTRIES)
        + [DEFAULT_RISK_ENTRIES[0]]
    )

    with pytest.raises(
        ValueError,
        match="Duplicate ethical risk ID",
    ):
        EthicalRiskRegister(duplicated)


def test_register_rejects_missing_required_risk() -> None:
    incomplete = DEFAULT_RISK_ENTRIES[:-1]

    with pytest.raises(
        ValueError,
        match="must contain exactly",
    ):
        EthicalRiskRegister(incomplete)


def test_register_rejects_empty_required_field() -> None:
    invalid_entries = list(DEFAULT_RISK_ENTRIES)

    invalid_entries[0] = EthicalRiskEntry(
        risk_id="digital_exclusion",
        risk_description="",
        impact="Impact",
        mitigation="Mitigation",
        responsible_owner_role="Model/Data Lead",
    )

    with pytest.raises(
        ValueError,
        match="risk_description cannot be empty",
    ):
        EthicalRiskRegister(invalid_entries)


class FakeUpsertQuery:
    def __init__(
        self,
        client: "FakeSupabaseClient",
    ) -> None:
        self.client = client

    def upsert(
        self,
        rows: list[dict],
    ) -> "FakeUpsertQuery":
        self.client.upserted_rows = rows
        return self

    def execute(self) -> dict:
        return {
            "data": self.client.upserted_rows
        }


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.table_name: str | None = None
        self.upserted_rows: list[dict] = []

    def table(
        self,
        table_name: str,
    ) -> FakeUpsertQuery:
        self.table_name = table_name
        return FakeUpsertQuery(self)


def test_seed_persists_all_entries_to_correct_table() -> None:
    client = FakeSupabaseClient()

    rows = seed_ethical_risk_register(client)

    assert client.table_name == (
        "ethical_risk_register"
    )

    assert len(rows) == 5
    assert client.upserted_rows == rows

    assert {
        row["risk_id"]
        for row in rows
    } == set(REQUIRED_RISK_IDS)


def test_rows_match_supabase_schema_fields() -> None:
    rows = EthicalRiskRegister().to_rows()

    expected_fields = {
        "risk_id",
        "risk_description",
        "impact",
        "mitigation",
        "responsible_owner_role",
        "last_reviewed_at",
    }

    assert all(
        set(row) == expected_fields
        for row in rows
    )


def test_seed_migration_contains_all_five_risk_ids() -> None:
    repository_root = (
        Path(__file__).resolve().parents[1]
    )

    migration_path = (
        repository_root
        / "infra"
        / "migrations"
        / "002_seed_ethical_risk_register.sql"
    )

    sql = migration_path.read_text(
        encoding="utf-8"
    )

    for risk_id in REQUIRED_RISK_IDS:
        assert f"'{risk_id}'" in sql

    assert (
        "INSERT INTO ethical_risk_register"
        in sql
    )
    assert "ON CONFLICT (risk_id)" in sql


# Feature: geosignal-ai, Property 19:
# Ethical Risk Register Completeness
@settings(max_examples=50, deadline=None)
@given(
    entry_order=st.permutations(
        DEFAULT_RISK_ENTRIES
    )
)
def test_property_19_ethical_risk_register_completeness(
    entry_order,
) -> None:
    register = EthicalRiskRegister(
        entry_order
    )

    assert set(register.risk_ids) == set(
        REQUIRED_RISK_IDS
    )

    assert len(register) == len(
        REQUIRED_RISK_IDS
    )

    for entry in register:
        assert isinstance(
            entry,
            EthicalRiskEntry,
        )

        assert entry.risk_description.strip()
        assert entry.impact.strip()
        assert entry.mitigation.strip()
        assert entry.responsible_owner_role.strip()