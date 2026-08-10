-- =============================================================================
-- GeoSignal AI — LOS upsert unique constraint
-- Migration: 006_los_unique_constraint.sql
--
-- geosignal.los.persist_los_results upserts on
-- (region_id, candidate_lat, candidate_lon, cell_lat, cell_lon), which
-- requires a matching unique constraint.  Migration 001 created only a
-- non-unique index; this closes the gap so Phase D LOS precompute can
-- persist idempotently.
--
-- Idempotent: safe to re-run.
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'los_results_region_candidate_cell_key'
          AND conrelid = 'los_results'::regclass
    ) THEN
        ALTER TABLE los_results
            ADD CONSTRAINT los_results_region_candidate_cell_key
            UNIQUE (region_id, candidate_lat, candidate_lon, cell_lat, cell_lon);
    END IF;
END $$;