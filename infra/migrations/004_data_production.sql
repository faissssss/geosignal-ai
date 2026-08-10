-- =============================================================================
-- GeoSignal AI — Data Production: provenance, demo segregation, and map layers
-- Migration: 004_data_production.sql
--
-- Aligns with .kiro/specs/data-production/plan.md and expected-outcomes.md.
--   - Every generated row records a source dataset + ingestion run (Phase 1).
--   - Row lifecycle distinguishes demo / real / derived / unavailable.
--   - New durable tables for land-cover tiles, contours, villages, BTS towers.
--   - grid_cells / bts_candidates gain kecamatan_id, data_source, source_run_id
--     so the heatmap/candidates can be filtered to a selected boundary and
--     traced to a promoted (non-demo) run.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE data_source_kind AS ENUM ('demo', 'real', 'derived', 'unavailable');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- 1. source_runs — durable provenance record for each ingestion/scoring step
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS source_runs (
    run_id             UUID PRIMARY KEY,
    dataset            VARCHAR NOT NULL,
    region_id          VARCHAR,
    source_url         VARCHAR,
    source_version     VARCHAR,
    source_date        DATE,
    checksum_sha256    VARCHAR,
    ingested_at        TIMESTAMPTZ DEFAULT NOW(),
    records_count      INT,
    metadata           JSONB,
    status             VARCHAR NOT NULL DEFAULT 'ok'   -- ok | partial | unavailable
);

CREATE INDEX IF NOT EXISTS idx_source_runs_dataset
    ON source_runs(dataset);

CREATE INDEX IF NOT EXISTS idx_source_runs_region
    ON source_runs(region_id);

-- ---------------------------------------------------------------------------
-- 2. Land-cover tile sets (browser-efficient GEE-published raster tiles)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS landcover_tile_sets (
    set_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region_id       VARCHAR NOT NULL,
    layer_id        VARCHAR NOT NULL DEFAULT 'worldcover',
    source_run_id   UUID REFERENCES source_runs(run_id),
    tiles_url       VARCHAR,
    attribution     VARCHAR,
    status          data_source_kind NOT NULL DEFAULT 'unavailable',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_landcover_tile_sets_region
    ON landcover_tile_sets(region_id);

-- ---------------------------------------------------------------------------
-- 3. Contour features — SRTM-derived LineStrings
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contour_features (
    feature_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region_id       VARCHAR NOT NULL,
    kecamatan_id    VARCHAR,
    elevation_m     DOUBLE PRECISION NOT NULL,
    source_run_id   UUID REFERENCES source_runs(run_id),
    status          data_source_kind NOT NULL DEFAULT 'unavailable',
    geom_geojson    JSONB
);

CREATE INDEX IF NOT EXISTS idx_contour_features_region
    ON contour_features(region_id);

-- ---------------------------------------------------------------------------
-- 4. Village polygons (approved OSM / government source)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS village_features (
    feature_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region_id       VARCHAR NOT NULL,
    kecamatan_id    VARCHAR,
    village_name    VARCHAR,
    attribution     VARCHAR,
    source_run_id   UUID REFERENCES source_runs(run_id),
    status          data_source_kind NOT NULL DEFAULT 'unavailable',
    geom_geojson    JSONB
);

CREATE INDEX IF NOT EXISTS idx_village_features_region
    ON village_features(region_id);

-- ---------------------------------------------------------------------------
-- 5. BTS tower locations (OpenCellID bulk export)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bts_locations (
    tower_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region_id       VARCHAR NOT NULL,
    lat             DOUBLE PRECISION NOT NULL,
    lon             DOUBLE PRECISION NOT NULL,
    mcc             INT,
    mnc             INT,
    lac             INT,
    cell_id         INT,
    source_run_id   UUID REFERENCES source_runs(run_id),
    status          data_source_kind NOT NULL DEFAULT 'unavailable'
);

CREATE INDEX IF NOT EXISTS idx_bts_locations_region
    ON bts_locations(region_id);

-- ---------------------------------------------------------------------------
-- 6. Enrich grid_cells / bts_candidates with provenance + kecamatan scoping
-- ---------------------------------------------------------------------------
ALTER TABLE grid_cells
    ADD COLUMN IF NOT EXISTS kecamatan_id   VARCHAR,
    ADD COLUMN IF NOT EXISTS data_source    data_source_kind NOT NULL DEFAULT 'unavailable';

ALTER TABLE bts_candidates
    ADD COLUMN IF NOT EXISTS kecamatan_id   VARCHAR,
    ADD COLUMN IF NOT EXISTS data_source    data_source_kind NOT NULL DEFAULT 'unavailable';

-- ---------------------------------------------------------------------------
-- 7. Backfill existing rows as clearly-labelled demo data.
--    Demo rows are kept (safe, recoverable) but are never merged into a
--    promoted real-data run.
-- ---------------------------------------------------------------------------
UPDATE grid_cells
   SET data_source = 'demo'
 WHERE data_source = 'unavailable';

UPDATE bts_candidates
   SET data_source = 'demo'
 WHERE data_source = 'unavailable';

-- ---------------------------------------------------------------------------
-- 8. Release note: the 12-month scoring_runs retention trigger stays intact
-- (documented in 001_initial_schema.sql). Promotion workflows archive demo
-- rows through the API-backed archive helper, never by deleting recent runs.
-- ---------------------------------------------------------------------------