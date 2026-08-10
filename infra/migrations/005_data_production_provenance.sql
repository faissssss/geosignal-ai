-- =============================================================================
-- GeoSignal AI — Data Production: provenance FK + promotion/rollback support
-- Migration: 005_data_production_provenance.sql
--
-- Closes the Phase 1 schema gap from 004 (which claimed source_run_id on
-- grid_cells / bts_candidates but never added it) and adds promotion/rollback
-- bookkeeping to source_runs so Phase 6 can promote a real run and remove
-- superseded demo rows transaction-safely.
--
-- Idempotent: safe to re-run.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Provenance FK on grid_cells / bts_candidates
-- ---------------------------------------------------------------------------
ALTER TABLE grid_cells
    ADD COLUMN IF NOT EXISTS source_run_id UUID REFERENCES source_runs(run_id);

ALTER TABLE bts_candidates
    ADD COLUMN IF NOT EXISTS source_run_id UUID REFERENCES source_runs(run_id);

-- ---------------------------------------------------------------------------
-- 2. Promotion / rollback bookkeeping on source_runs
-- ---------------------------------------------------------------------------
ALTER TABLE source_runs
    ADD COLUMN IF NOT EXISTS promoted_run_id UUID REFERENCES source_runs(run_id),
    ADD COLUMN IF NOT EXISTS superseded_by   UUID REFERENCES source_runs(run_id),
    ADD COLUMN IF NOT EXISTS promoted_at     TIMESTAMPTZ;

-- ---------------------------------------------------------------------------
-- 3. Demo rows stay demo: existing grid_cells / bts_candidates keep
--    data_source = 'demo' and source_run_id = NULL. They are never tied to a
--    real run and are removed only by the Phase 6 promotion workflow.
-- ---------------------------------------------------------------------------