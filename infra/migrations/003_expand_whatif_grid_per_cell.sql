-- =============================================================================
-- GeoSignal AI — What-if grid cell-level expansion
-- Migration: 003_expand_whatif_grid_per_cell.sql
--
-- Task 18 requires multiple affected grid-cell rows for one scenario.
-- The revised key is:
--
--     (region_id, scenario_id, grid_cell_id)
--
-- Existing what-if results can be regenerated because this is an offline,
-- reproducible precomputation artifact.
-- =============================================================================

ALTER TABLE whatif_grid
ADD COLUMN IF NOT EXISTS grid_cell_id UUID
REFERENCES grid_cells(cell_id)
ON DELETE CASCADE;

-- Rows from the older one-row-per-scenario schema cannot be safely mapped to
-- an affected grid cell. Remove them before enforcing the revised structure.
-- The Task 18 offline batch regenerates them.
DELETE FROM whatif_grid
WHERE grid_cell_id IS NULL;

ALTER TABLE whatif_grid
ALTER COLUMN grid_cell_id SET NOT NULL;

ALTER TABLE whatif_grid
DROP CONSTRAINT IF EXISTS whatif_grid_pkey;

ALTER TABLE whatif_grid
ADD CONSTRAINT whatif_grid_pkey
PRIMARY KEY (
    region_id,
    scenario_id,
    grid_cell_id
);

CREATE INDEX IF NOT EXISTS
idx_whatif_grid_candidate_region
ON whatif_grid (
    candidate_id,
    region_id
);

CREATE INDEX IF NOT EXISTS
idx_whatif_grid_manual_snap
ON whatif_grid (
    region_id,
    snapped_lat,
    snapped_lon
);