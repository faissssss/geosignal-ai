# Data Production Plan

## Goal

Produce source-backed, provenance-tracked map data for every kecamatan in NTT,
NTB, and Central Kalimantan. The map must filter every applicable layer to the
selected kecamatan boundary without inventing source values or silently using
demo rows as production data.

## Scope

| Layer | Production source | Stored product | Kecamatan filter rule |
| --- | --- | --- | --- |
| Heatmap | GEE terrain/land-cover/population + OpenCellID; Ookla only as Tier-2 label | `grid_cells` + scoring run provenance | Cell centroid is within boundary |
| Land cover | GEE `ESA/WorldCover/v200` | tiled/raster-derived GeoJSON or map tiles | Geometry intersects boundary |
| Contours | GEE `USGS/SRTMGL1_003` | contour LineString features | Line intersects boundary |
| Villages | OpenStreetMap / approved government boundary source | village Polygon features | Geometry intersects boundary |
| BTS towers | OpenCellID | tower Point features | Point is within boundary |
| Candidates | ranking over real scored cells + constraints/LOS | `bts_candidates`, `whatif_grid` | Candidate point is within boundary |

## Data quality and provenance

- Each generated row records source dataset version/date, ingestion timestamp,
  region, source checksum or request identifier, model version, and scoring run.
- Ookla is a validation/training label only. It must never be inserted into the
  consolidated feature vector.
- Missing OpenCellID or Ookla records produce an explicit Low confidence state;
  they must not be interpreted as proof of zero coverage.
- A real-data run must be written separately from demo data. Demo rows are
  removed only after all 45 kecamatan pass validation.

## Storage and API contracts

1. Add tables or durable GeoJSON storage for `land_cover_features`,
   `contour_features`, `village_features`, `bts_locations`, and source runs.
2. Add region-scoped API routes for each layer. Each accepts `region_id` and
   optionally `target_area_id` or boundary geometry.
3. Keep filtering server-side for large feature sets; use the same point-in-
   polygon/intersection semantics as the heatmap.
4. Update MapView sources reactively when region or target area changes and
   preserve layer-toggle state.

## Production workflow

1. Verify Earth Engine project access and source endpoint availability.
2. Download and checksum configured Ookla fixed/mobile archives; spatially
   filter before loading into memory.
3. Ingest OpenCellID records for the three regional extents and retain source
   metadata.
4. Fetch GEE raster values at per-kecamatan analysis points, derive features,
   and calculate Tier-1 scores; train/apply Tier-2 only where sufficient Ookla
   labels exist.
5. Generate contours, land-cover features, and village/tower layers.
6. Rank candidate sites, run LOS and what-if precomputation, and persist only
   source-backed candidates.
7. Validate that every kecamatan has heatmap data and each relevant layer
   returns only features within/intersecting its selected boundary.
8. Promote the run, then remove superseded demo rows in a transaction-safe,
   recoverable operation.

## Acceptance criteria

- All 45 kecamatan return at least one real-source heatmap cell and no cell
  outside the selected boundary.
- Land cover, contours, villages, BTS towers, and candidates update when the
  selected kecamatan changes; features outside the boundary are absent.
- Every UI layer states its source and reports a clear unavailable status when
  a source has no coverage.
- Region switching clears the target-area filter and loads only that region's
  data.
- Automated tests cover boundary filtering, empty results, region switching,
  layer toggles, and provenance/no-demo-row invariants.

## Current prerequisites and risks

- Earth Engine service-account access is verified.
- The configured Ookla archives are global files (about 554 MB combined) and
  require bounded regional extraction.
- OpenCellID ingestion needs an authenticated export/query path compatible
  with the configured key; its lack of records is treated as unknown coverage.
- Village geometry needs an approved OSM or government source and attribution.
