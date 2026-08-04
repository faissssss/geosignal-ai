-- =============================================================================
-- GeoSignal AI — Seed Ethical Risk Register
-- Migration: 002_seed_ethical_risk_register.sql
-- Requirement: 9.6
-- =============================================================================

INSERT INTO ethical_risk_register (
    risk_id,
    risk_description,
    impact,
    mitigation,
    responsible_owner_role,
    last_reviewed_at
)
VALUES
(
    'digital_exclusion',
    'Low-population or poorly mapped communities may be systematically deprioritised even when they have genuine connectivity needs.',
    'Remote and vulnerable communities may continue to receive lower infrastructure priority, widening the digital divide.',
    'Apply explicit equity weighting through public-facility proximity and population-density indicators, and review results per kecamatan rather than relying only on aggregate performance.',
    'Model/Data Lead',
    NOW()
),
(
    'deforestation',
    'Recommended BTS sites may encourage clearing of forest or other high-canopy vegetation.',
    'Infrastructure placement could contribute to habitat loss, forest degradation, and avoidable environmental damage.',
    'Exclude candidates by default only when land-cover class and canopy-height jointly identify high-canopy vegetation, and require human review of final placement.',
    'Model/Data Lead',
    NOW()
),
(
    'opencellid_sparsity_misread',
    'The absence of a nearby OpenCellID record may be incorrectly interpreted as confirmed absence of mobile coverage.',
    'Unknown or under-measured locations may be labelled as confirmed coverage gaps, causing investment to be directed using misleading evidence.',
    'Treat missing OpenCellID or Ookla observations as low-confidence unknowns rather than confirmed poor coverage, and expose the confidence tag with every recommendation.',
    'Data Lead',
    NOW()
),
(
    'low_confidence_funding_decisions',
    'A stakeholder may use a low-confidence recommendation as if it were an authoritative infrastructure decision.',
    'Public funding may be committed to an unsuitable site based on incomplete, sparse, or low-fidelity evidence.',
    'Visually distinguish confidence tiers, require explicit acknowledgement before acting on low-confidence outputs, and label all results as GeoAI-assisted estimates requiring human and field validation.',
    'Product/Presentation Lead',
    NOW()
),
(
    'maup_resampling_mismatch',
    'Combining spatial layers with different native resolutions may produce different Coverage Scores depending on the selected analysis grid.',
    'Candidate rankings and apparent connectivity gaps may be distorted by resampling choices rather than actual geographic conditions.',
    'Generate and compare outputs at multiple grid resolutions, document the selected resolution and resampling method, and report material differences before recommendations are used.',
    'Model/Data Lead',
    NOW()
)
ON CONFLICT (risk_id)
DO UPDATE SET
    risk_description = EXCLUDED.risk_description,
    impact = EXCLUDED.impact,
    mitigation = EXCLUDED.mitigation,
    responsible_owner_role = EXCLUDED.responsible_owner_role,
    last_reviewed_at = EXCLUDED.last_reviewed_at;