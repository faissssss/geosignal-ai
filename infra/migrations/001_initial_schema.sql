-- =============================================================================
-- GeoSignal AI — Initial Supabase/PostgreSQL Schema
-- Migration: 001_initial_schema.sql
-- =============================================================================

-- ---------------------------------------------------------------------------
-- ENUM types
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE confidence_level AS ENUM ('Low', 'Med', 'High');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE model_tier AS ENUM ('1', '2');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE selection_method AS ENUM ('drawn_polygon', 'kecamatan');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- Tables
-- Note: CREATE TABLE order avoids forward-reference FK violations.
-- Circular references (grid_cells ↔ model_artifacts, scoring_runs) are handled
-- by creating the FK constraints via ALTER TABLE after both tables exist.
-- ---------------------------------------------------------------------------

-- 1. model_artifacts (no FK dependencies)
CREATE TABLE IF NOT EXISTS model_artifacts (
    version_id    VARCHAR PRIMARY KEY,
    tier          model_tier NOT NULL,
    algorithm     VARCHAR NOT NULL,
    training_run_id UUID,
    artifact_path VARCHAR NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 2. scoring_runs (no FK dependencies on tables not yet created)
CREATE TABLE IF NOT EXISTS scoring_runs (
    run_id              UUID PRIMARY KEY,
    model_version       VARCHAR NOT NULL,
    tier                model_tier NOT NULL,
    region_kecamatans   TEXT[],
    resolution_m        INT NOT NULL,
    input_checksums     JSONB,
    candidate_count     INT,
    timestamp           TIMESTAMPTZ DEFAULT NOW(),
    retained_for_months INT DEFAULT 12
);

-- 3. target_areas (no FK dependencies)
CREATE TABLE IF NOT EXISTS target_areas (
    target_area_id   UUID PRIMARY KEY,
    region_id        VARCHAR NOT NULL,
    selection_method selection_method NOT NULL,
    kecamatan_id     VARCHAR,       -- NULL unless selection_method = 'kecamatan'
    boundary_geojson JSONB NOT NULL,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- 4. grid_cells (FKs to model_artifacts and scoring_runs — both exist now)
CREATE TABLE IF NOT EXISTS grid_cells (
    cell_id         UUID PRIMARY KEY,
    region_id       VARCHAR NOT NULL,
    lat             DOUBLE PRECISION NOT NULL,
    lon             DOUBLE PRECISION NOT NULL,
    resolution_m    INT NOT NULL,
    coverage_score  FLOAT,
    confidence_tag  confidence_level,
    tier_used       model_tier,
    shap_top3       JSONB,
    model_version   VARCHAR REFERENCES model_artifacts(version_id),
    scoring_run_id  UUID REFERENCES scoring_runs(run_id)
);

-- 5. bts_candidates (FK to target_areas — exists now)
CREATE TABLE IF NOT EXISTS bts_candidates (
    candidate_id         UUID PRIMARY KEY,
    region_id            VARCHAR NOT NULL,
    target_area_id       UUID REFERENCES target_areas(target_area_id),
    rank                 INT NOT NULL,
    lat                  DOUBLE PRECISION NOT NULL,
    lon                  DOUBLE PRECISION NOT NULL,
    expected_improvement FLOAT NOT NULL,
    los_validated        BOOLEAN NOT NULL,  -- NOT NULL: inserted only after LOS computed
    confidence_tag       confidence_level,
    shap_values          JSONB,
    model_version        VARCHAR,
    scoring_run_id       UUID,
    excluded_by_canopy   BOOLEAN
);

-- 6. whatif_grid (FK to bts_candidates — exists now)
CREATE TABLE IF NOT EXISTS whatif_grid (
    scenario_id          UUID PRIMARY KEY,
    region_id            VARCHAR NOT NULL,
    candidate_id         UUID REFERENCES bts_candidates(candidate_id),
    snapped_lat          DOUBLE PRECISION NOT NULL,
    snapped_lon          DOUBLE PRECISION NOT NULL,
    grid_resolution_m    INT NOT NULL,
    delta_coverage_score FLOAT,
    pct_good_change      FLOAT,
    villages_newly_covered INT,
    new_coverage_score   FLOAT
);

-- 7. ethical_risk_register (no FK dependencies)
CREATE TABLE IF NOT EXISTS ethical_risk_register (
    risk_id               VARCHAR PRIMARY KEY,
    risk_description      TEXT NOT NULL,
    impact                TEXT NOT NULL,
    mitigation            TEXT NOT NULL,
    responsible_owner_role VARCHAR NOT NULL,
    last_reviewed_at      TIMESTAMPTZ
);

-- 8. admin_boundaries (no FK dependencies)
CREATE TABLE IF NOT EXISTS admin_boundaries (
    boundary_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kecamatan_id     VARCHAR NOT NULL UNIQUE,
    kecamatan_name   VARCHAR NOT NULL,
    region_id        VARCHAR NOT NULL,
    boundary_geojson JSONB NOT NULL
);

-- 9. los_results (no FK dependencies)
CREATE TABLE IF NOT EXISTS los_results (
    los_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region_id     VARCHAR NOT NULL,
    candidate_lat DOUBLE PRECISION NOT NULL,
    candidate_lon DOUBLE PRECISION NOT NULL,
    cell_lat      DOUBLE PRECISION NOT NULL,
    cell_lon      DOUBLE PRECISION NOT NULL,
    los_clear     BOOLEAN NOT NULL,
    computed_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_grid_cells_region_id
    ON grid_cells(region_id);

CREATE INDEX IF NOT EXISTS idx_bts_candidates_region_id
    ON bts_candidates(region_id);

CREATE INDEX IF NOT EXISTS idx_los_results_region_candidate
    ON los_results(region_id, candidate_lat, candidate_lon);

CREATE INDEX IF NOT EXISTS idx_admin_boundaries_region_id
    ON admin_boundaries(region_id);

-- ---------------------------------------------------------------------------
-- 12-month retention policy on scoring_runs
-- Prevents DELETE of rows younger than 12 months.
-- ---------------------------------------------------------------------------

-- Trigger function: raises an exception if a DELETE is attempted on a
-- scoring_runs row whose timestamp is within the last 12 months.
CREATE OR REPLACE FUNCTION prevent_recent_scoring_run_delete()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.timestamp > NOW() - INTERVAL '12 months' THEN
        RAISE EXCEPTION
            'Cannot delete scoring_run % — it is younger than 12 months (timestamp: %). '
            'Retention policy requires rows to be kept for at least % months.',
            OLD.run_id, OLD.timestamp, OLD.retained_for_months
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_scoring_runs_retention ON scoring_runs;
CREATE TRIGGER trg_scoring_runs_retention
    BEFORE DELETE ON scoring_runs
    FOR EACH ROW
    EXECUTE FUNCTION prevent_recent_scoring_run_delete();

-- Comment documenting the retention policy for operators:
COMMENT ON TABLE scoring_runs IS
    'Audit log of every batch scoring run. '
    'Rows younger than 12 months are protected from DELETE by the '
    'trg_scoring_runs_retention trigger (prevent_recent_scoring_run_delete). '
    'The retained_for_months column records the agreed retention period per row '
    '(default 12). This satisfies Requirement 11.4.';
