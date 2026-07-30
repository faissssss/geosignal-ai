# Feature: geosignal-ai, Property 26: PII Absence Invariant
"""Property 26 — PII Absence Invariant (sub-task 2.4).

Validates: Requirements 12.1, 12.2, 12.3, 12.4

Statically audits:
1. The SQL migration file — asserts no column name contains a PII-indicative term
   (with an allow-list for legitimately named columns).
2. CONSOLIDATED_FEATURES — asserts no Ookla field is present.
3. FeatureVector dataclass — asserts no field name contains "ookla".
"""
import dataclasses
import pathlib
import re

import pytest

from geosignal.models import CONSOLIDATED_FEATURES, FeatureVector

# ---------------------------------------------------------------------------
# PII terms to flag in SQL column definitions
# ---------------------------------------------------------------------------

_PII_TERMS: set[str] = {
    "name",
    "email",
    "phone",
    "address",
    "device_id",
    "imei",
    "imsi",
    "user_id",
    "person",
    "household",
    "individual",
}

# Columns that are legitimately named despite containing a PII-adjacent term.
# These are exact column-name strings (lower-cased) that should not be flagged.
_ALLOWLIST: set[str] = {
    "kecamatan_name",       # administrative label, not a person's name
    "responsible_owner_role",  # role label, not a personal identifier
    "region_id",            # region identifier, not a user/person identifier
    "scoring_run_id",       # run identifier
    "candidate_id",         # candidate site identifier
    "boundary_id",          # spatial boundary identifier
    "target_area_id",       # area identifier
    "los_id",               # line-of-sight result identifier
    "run_id",               # scoring run identifier
    "training_run_id",      # model training run identifier
    "risk_id",              # ethical risk entry identifier
    "cell_id",              # grid cell identifier
    "model_version",        # model artifact version
}

# ---------------------------------------------------------------------------
# Helper: extract column names from SQL migration file
# ---------------------------------------------------------------------------

_MIGRATION_PATH = (
    pathlib.Path(__file__).parent.parent / "infra" / "migrations" / "001_initial_schema.sql"
)

# Pattern: matches `column_name  TYPE ...` lines inside CREATE TABLE blocks.
# Captures the first identifier on each non-blank, non-comment content line
# that does not start with a SQL keyword (CREATE, PRIMARY, CONSTRAINT, UNIQUE, etc.).
_COLUMN_LINE_RE = re.compile(
    r"""
    ^\s+                          # leading whitespace (column is indented)
    (?!--)                        # not a comment line
    (?!CREATE|PRIMARY|CONSTRAINT  # not a DDL keyword
      |UNIQUE|CHECK|FOREIGN|REFERENCES
      |INDEX|ALTER|COMMENT|DROP|DO
      |BEGIN|END|EXCEPTION|WHEN|NULL
      |RAISE|IF|RETURN|OLD|NEW
    )
    ([a-z_][a-z0-9_]*)           # capture the column name
    \s+                           # followed by whitespace
    (?!AS\b)                      # not an alias (AS keyword)
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _extract_column_names_from_sql(sql_text: str) -> list[str]:
    """Extract column names from a SQL CREATE TABLE migration file.

    Returns a deduplicated list of lower-cased column-name candidates.
    """
    column_names: list[str] = []
    inside_create_table = False

    for raw_line in sql_text.splitlines():
        line = raw_line.strip()

        # Track entering/leaving CREATE TABLE blocks.
        if re.match(r"^CREATE\s+TABLE\b", line, re.IGNORECASE):
            inside_create_table = True
            continue
        if inside_create_table and re.match(r"^\)\s*;", line):
            inside_create_table = False
            continue

        if not inside_create_table:
            continue

        match = _COLUMN_LINE_RE.match(raw_line)
        if match:
            col_name = match.group(1).lower()
            column_names.append(col_name)

    return column_names


# ---------------------------------------------------------------------------
# Test 1 — SQL migration: no PII-indicative column names
# ---------------------------------------------------------------------------

def test_sql_migration_has_no_pii_columns():
    """No column in the Supabase schema migration should have a name that
    contains a PII-indicative term, except for explicitly allow-listed names.
    """
    assert _MIGRATION_PATH.exists(), (
        f"Migration file not found at {_MIGRATION_PATH}. "
        "Run sub-task 2.1 to create it."
    )

    sql_text = _MIGRATION_PATH.read_text(encoding="utf-8")
    column_names = _extract_column_names_from_sql(sql_text)

    assert column_names, "No column names were extracted from the migration file — check the parser."

    violations: list[str] = []
    for col in column_names:
        # Skip allow-listed columns.
        if col in _ALLOWLIST:
            continue
        # Check if any PII term appears as a substring of the column name.
        for term in _PII_TERMS:
            if term in col:
                violations.append(f"column '{col}' contains PII term '{term}'")
                break  # one report per column

    assert violations == [], (
        "PII-indicative column names found in the schema migration:\n"
        + "\n".join(f"  • {v}" for v in violations)
        + "\n\nReview the schema and rename or move these columns. "
        "Population data must be referenced only through aggregated raster paths, "
        "never disaggregated to individual or household records (Requirement 12.1)."
    )


# ---------------------------------------------------------------------------
# Test 2 — CONSOLIDATED_FEATURES: no Ookla field
# ---------------------------------------------------------------------------

def test_consolidated_features_has_no_ookla_field():
    """CONSOLIDATED_FEATURES must not contain any Ookla-related entry.

    Ookla is the Tier 2 training label only — it is never a scoring input.
    """
    ookla_entries = [feat for feat in CONSOLIDATED_FEATURES if "ookla" in feat.lower()]
    assert ookla_entries == [], (
        f"CONSOLIDATED_FEATURES contains Ookla entry/entries: {ookla_entries}. "
        "Ookla is the Tier 2 label only and must not appear in the feature list."
    )


# ---------------------------------------------------------------------------
# Test 3 — FeatureVector: no field named with "ookla"
# ---------------------------------------------------------------------------

def test_feature_vector_has_no_ookla_field():
    """No field on the FeatureVector dataclass may have a name containing 'ookla'."""
    fv_fields = [f.name for f in dataclasses.fields(FeatureVector)]
    ookla_fields = [name for name in fv_fields if "ookla" in name.lower()]
    assert ookla_fields == [], (
        f"FeatureVector has Ookla field(s): {ookla_fields}. "
        "Ookla signal quality is the Tier 2 label only and must not be a model input field."
    )
