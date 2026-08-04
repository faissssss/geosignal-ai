"""Ethical Risk Register for GeoSignal AI.

The register is a structured governance artifact containing the five
project-specific ethical risks required by Requirement 9.6.

EthicalRiskEntry is imported from geosignal.models and is never redefined
in this module.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from copy import deepcopy
from dataclasses import asdict
from typing import Any

from geosignal.models import EthicalRiskEntry


REQUIRED_RISK_IDS: tuple[str, ...] = (
    "digital_exclusion",
    "deforestation",
    "opencellid_sparsity_misread",
    "low_confidence_funding_decisions",
    "maup_resampling_mismatch",
)


def _default_risk_entries() -> tuple[EthicalRiskEntry, ...]:
    """Return the canonical five GeoSignal AI ethical risk entries."""
    return (
        EthicalRiskEntry(
            risk_id="digital_exclusion",
            risk_description=(
                "Low-population or poorly mapped communities may be "
                "systematically deprioritised even when they have genuine "
                "connectivity needs."
            ),
            impact=(
                "Remote and vulnerable communities may continue to receive "
                "lower infrastructure priority, widening the digital divide."
            ),
            mitigation=(
                "Apply explicit equity weighting through public-facility "
                "proximity and population-density indicators, and review "
                "results per kecamatan rather than relying only on aggregate "
                "performance."
            ),
            responsible_owner_role="Model/Data Lead",
        ),
        EthicalRiskEntry(
            risk_id="deforestation",
            risk_description=(
                "Recommended BTS sites may encourage clearing of forest or "
                "other high-canopy vegetation."
            ),
            impact=(
                "Infrastructure placement could contribute to habitat loss, "
                "forest degradation, and avoidable environmental damage."
            ),
            mitigation=(
                "Exclude candidates by default only when the land-cover class "
                "and canopy-height threshold jointly identify high-canopy "
                "vegetation, and require human review of final placement."
            ),
            responsible_owner_role="Model/Data Lead",
        ),
        EthicalRiskEntry(
            risk_id="opencellid_sparsity_misread",
            risk_description=(
                "The absence of a nearby OpenCellID record may be incorrectly "
                "interpreted as confirmed absence of mobile coverage."
            ),
            impact=(
                "Unknown or under-measured locations may be labelled as "
                "confirmed coverage gaps, causing investment to be directed "
                "using misleading evidence."
            ),
            mitigation=(
                "Treat missing OpenCellID or Ookla observations as "
                "low-confidence unknowns rather than confirmed poor coverage, "
                "and expose the confidence tag with every recommendation."
            ),
            responsible_owner_role="Data Lead",
        ),
        EthicalRiskEntry(
            risk_id="low_confidence_funding_decisions",
            risk_description=(
                "A stakeholder may use a low-confidence recommendation as if "
                "it were an authoritative infrastructure decision."
            ),
            impact=(
                "Public funding may be committed to an unsuitable site based "
                "on incomplete, sparse, or low-fidelity evidence."
            ),
            mitigation=(
                "Visually distinguish confidence tiers, require explicit "
                "acknowledgement before acting on low-confidence outputs, and "
                "label all results as GeoAI-assisted estimates requiring "
                "human and field validation."
            ),
            responsible_owner_role="Product/Presentation Lead",
        ),
        EthicalRiskEntry(
            risk_id="maup_resampling_mismatch",
            risk_description=(
                "Combining spatial layers with different native resolutions "
                "may produce different Coverage Scores depending on the "
                "selected analysis grid."
            ),
            impact=(
                "Candidate rankings and apparent connectivity gaps may be "
                "distorted by resampling choices rather than actual geographic "
                "conditions."
            ),
            mitigation=(
                "Generate and compare outputs at multiple grid resolutions, "
                "document the selected resolution and resampling method, and "
                "report material differences before recommendations are used."
            ),
            responsible_owner_role="Model/Data Lead",
        ),
    )


DEFAULT_RISK_ENTRIES: tuple[EthicalRiskEntry, ...] = (
    _default_risk_entries()
)


class EthicalRiskRegister:
    """Validated collection of all required GeoSignal AI ethical risks.

    The register must contain exactly one entry for each required risk ID.
    Entries are copied on input and output to prevent accidental mutation of
    the canonical governance record.
    """

    def __init__(
        self,
        entries: Iterable[EthicalRiskEntry] | None = None,
    ) -> None:
        source_entries = (
            DEFAULT_RISK_ENTRIES
            if entries is None
            else tuple(entries)
        )

        indexed: dict[str, EthicalRiskEntry] = {}

        for entry in source_entries:
            if not isinstance(entry, EthicalRiskEntry):
                raise TypeError(
                    "Every risk entry must be an EthicalRiskEntry"
                )

            self._validate_entry(entry)

            if entry.risk_id in indexed:
                raise ValueError(
                    f"Duplicate ethical risk ID: {entry.risk_id}"
                )

            indexed[entry.risk_id] = deepcopy(entry)

        expected = set(REQUIRED_RISK_IDS)
        actual = set(indexed)

        missing = expected.difference(actual)
        unexpected = actual.difference(expected)

        if missing or unexpected:
            details: list[str] = []

            if missing:
                details.append(
                    f"missing={sorted(missing)}"
                )

            if unexpected:
                details.append(
                    f"unexpected={sorted(unexpected)}"
                )

            raise ValueError(
                "EthicalRiskRegister must contain exactly the five "
                f"required risks ({'; '.join(details)})"
            )

        self._entries = {
            risk_id: indexed[risk_id]
            for risk_id in REQUIRED_RISK_IDS
        }

    @staticmethod
    def _validate_entry(
        entry: EthicalRiskEntry,
    ) -> None:
        """Validate one ethical risk entry."""
        fields = {
            "risk_id": entry.risk_id,
            "risk_description": entry.risk_description,
            "impact": entry.impact,
            "mitigation": entry.mitigation,
            "responsible_owner_role": (
                entry.responsible_owner_role
            ),
        }

        for field_name, raw_value in fields.items():
            if not isinstance(raw_value, str):
                raise TypeError(
                    f"{field_name} must be a string"
                )

            if not raw_value.strip():
                raise ValueError(
                    f"{field_name} cannot be empty"
                )

    @property
    def entries(self) -> tuple[EthicalRiskEntry, ...]:
        """Return defensive copies in canonical risk-ID order."""
        return tuple(
            deepcopy(self._entries[risk_id])
            for risk_id in REQUIRED_RISK_IDS
        )

    @property
    def risk_ids(self) -> tuple[str, ...]:
        """Return all required risk identifiers."""
        return tuple(self._entries)

    def get(
        self,
        risk_id: str,
    ) -> EthicalRiskEntry:
        """Return one risk entry by ID."""
        key = str(risk_id).strip()

        try:
            return deepcopy(self._entries[key])
        except KeyError as exc:
            raise KeyError(
                f"Unknown ethical risk ID: {key}"
            ) from exc

    def to_rows(self) -> list[dict[str, str]]:
        """Return rows compatible with the Supabase table."""
        from datetime import datetime, timezone

        reviewed_at = datetime.now(timezone.utc).isoformat()

        return [
            {
                **asdict(self._entries[risk_id]),
                "last_reviewed_at": reviewed_at,
            }
            for risk_id in REQUIRED_RISK_IDS
        ]

    def persist(
        self,
        supabase_client: Any,
    ) -> list[dict[str, str]]:
        """Upsert all five entries to ethical_risk_register."""
        rows = self.to_rows()

        (
            supabase_client
            .table("ethical_risk_register")
            .upsert(rows)
            .execute()
        )

        return rows

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[EthicalRiskEntry]:
        return iter(self.entries)

    def __contains__(self, risk_id: object) -> bool:
        return risk_id in self._entries


def seed_ethical_risk_register(
    supabase_client: Any,
) -> list[dict[str, str]]:
    """Create and persist the canonical Ethical Risk Register."""
    return EthicalRiskRegister().persist(
        supabase_client
    )