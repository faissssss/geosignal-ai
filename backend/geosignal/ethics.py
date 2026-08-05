"""GeoSignal AI — Ethical Risk Register (Task 30).

Provides:
    ETHICAL_RISK_REGISTER   Canonical list of EthicalRiskEntry objects.
    REQUIRED_RISK_IDS       Frozenset of the five mandatory risk IDs.
    get_risk_by_id()        Lookup an entry by risk_id.

The deforestation constraint (is_high_canopy) is defined in:
    geosignal.constraints

Import it from there — it is NOT redefined here.

Requirements: 9.6
"""
from __future__ import annotations

# Re-export is_high_canopy for backwards compatibility only.
# The canonical definition lives in geosignal.constraints.
from geosignal.constraints import is_high_canopy as is_high_canopy  # noqa: F401
from geosignal.models import EthicalRiskEntry


# ---------------------------------------------------------------------------
# Ethical Risk Register — five mandatory entries (Req 9.6)
# ---------------------------------------------------------------------------

ETHICAL_RISK_REGISTER: list[EthicalRiskEntry] = [
    EthicalRiskEntry(
        risk_id="digital_exclusion",
        risk_description=(
            "BTS placement recommendations may systematically favour areas with "
            "denser existing infrastructure, inadvertently excluding the most "
            "underserved 3T communities from connectivity improvements."
        ),
        impact=(
            "Communities with the greatest connectivity need may receive lower "
            "recommendation priority, widening the digital divide rather than "
            "closing it."
        ),
        mitigation=(
            "Equity weighting in AHP (facility_proximity_m and "
            "population_density_per_km2 have elevated weights). "
            "Coverage Score is validated against population density maps to "
            "ensure high-need areas receive proportional attention. "
            "Low-confidence gate requires acknowledgement before acting on "
            "sparse-data recommendations."
        ),
        responsible_owner_role="Data Scientist / Equity Lead",
    ),
    EthicalRiskEntry(
        risk_id="deforestation",
        risk_description=(
            "Recommending BTS tower placement in forested or high-canopy areas "
            "risks contributing to deforestation or habitat fragmentation if "
            "field crews clear vegetation to install towers."
        ),
        impact=(
            "Permanent loss of forest cover, biodiversity harm, and contribution "
            "to carbon emissions — contrary to Indonesia's national conservation "
            "commitments."
        ),
        mitigation=(
            "is_high_canopy() joint constraint (ESA WorldCover class 10/20 AND "
            "canopy_height_m >= 15.0 m) excludes affected sites from BTS candidate "
            "ranking. The constraint is active by default and cannot be disabled "
            "through the normal UI flow. excluded_by_canopy flag is persisted per "
            "candidate for audit purposes."
        ),
        responsible_owner_role="Environmental Compliance Officer",
    ),
    EthicalRiskEntry(
        risk_id="opencellid_sparsity_misread",
        risk_description=(
            "Sparse OpenCellID coverage in remote 3T regions may cause the "
            "model to interpret the absence of records as confirmed zero coverage, "
            "leading to over-confident or mis-directed recommendations."
        ),
        impact=(
            "Areas with no OpenCellID towers may appear as high-priority gaps "
            "when they are actually uncharted, leading to misallocation of "
            "infrastructure investment."
        ),
        mitigation=(
            "tag_confidence() treats absent OpenCellID records (None or inf) as "
            "Low confidence — never as confirmed zero coverage. "
            "Low-confidence recommendations require explicit Planner acknowledgement "
            "via ConfidenceGate before any action is taken."
        ),
        responsible_owner_role="Data Quality Lead",
    ),
    EthicalRiskEntry(
        risk_id="low_confidence_funding_decisions",
        risk_description=(
            "Planners may act on Low-confidence Coverage Score estimates when "
            "making funding and procurement decisions, treating GeoAI output as "
            "authoritative ground truth rather than a decision-support tool."
        ),
        impact=(
            "Misallocation of limited rural connectivity budgets based on "
            "unreliable estimates; potential legal or policy liability if "
            "funding decisions are later found to be based on sparse data."
        ),
        mitigation=(
            "ConfidenceGate component blocks Low-confidence actions until the "
            "Planner explicitly acknowledges the sparse-data warning. "
            "GeoAI-assisted estimate label is visible on all outputs. "
            "Acknowledgement is tied to the specific candidate and resets on "
            "candidate change — no persistent global override."
        ),
        responsible_owner_role="Product Owner / Planner Liaison",
    ),
    EthicalRiskEntry(
        risk_id="maup_resampling_mismatch",
        risk_description=(
            "Resampling geospatial layers (population, land cover, signal data) "
            "to different grid resolutions introduces the Modifiable Areal Unit "
            "Problem (MAUP): aggregate statistics at 250 m resolution do not "
            "faithfully represent conditions at 100 m resolution."
        ),
        impact=(
            "Coverage Score values may change non-trivially when the grid "
            "resolution is changed, making cross-resolution comparisons "
            "misleading and potentially biasing recommendations toward or "
            "against certain terrain types."
        ),
        mitigation=(
            "Multi-resolution harmonisation pipeline (harmonise_rasters) is "
            "run at all resolution variants before scoring. DataQualityReport "
            "records chosen_resolution_m and dataset_checksums so downstream "
            "consumers know the resolution at which scores were computed. "
            "Scores from different resolutions are not compared directly."
        ),
        responsible_owner_role="GIS / Harmonisation Engineer",
    ),
]

# Fast lookup by risk_id
_REGISTER_INDEX: dict[str, EthicalRiskEntry] = {
    e.risk_id: e for e in ETHICAL_RISK_REGISTER
}

REQUIRED_RISK_IDS: frozenset[str] = frozenset({
    "digital_exclusion",
    "deforestation",
    "opencellid_sparsity_misread",
    "low_confidence_funding_decisions",
    "maup_resampling_mismatch",
})


def get_risk_by_id(risk_id: str) -> EthicalRiskEntry:
    """Return the EthicalRiskEntry for a given risk_id.

    Raises:
        KeyError: if risk_id is not in the register.
    """
    return _REGISTER_INDEX[risk_id]
