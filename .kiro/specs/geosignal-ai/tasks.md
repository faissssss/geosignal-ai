# Implementation Plan: GeoSignal AI

## Overview

This task list implements the full GeoSignal AI system — a GeoAI-assisted decision-support
tool for detecting cellular coverage gaps and recommending optimal BTS placement sites in
Indonesia's 3T regions.

**Build order follows strict data-flow dependencies:**
- Data must exist before features can be computed
- Features must exist before models can score
- LOS precomputation must complete before BallTree candidate search
- What-if grid must be precomputed before Simulation_Engine queries it
- All offline data loads for 3 regions must complete before the final demo checkpoint

**Three target regions:** NTT Province (MVP demo), NTB Province (validation), Central Kalimantan Province (canopy-driven validation)

**Tech stack:** Python 3.11+, Next.js, MapLibre GL JS, Supabase (PostgreSQL + Storage),
Google Earth Engine, XGBoost/LightGBM, scikit-learn BallTree, SHAP, Hypothesis (PBT),
Docker

---
## Task 1: Project Scaffolding and External Account Registration

- [ ] 1. Project Scaffolding and External Account Registration
  - [ ] 1.1 Register for Google Earth Engine (GEE) non-commercial research access — approval takes 24–48 h; must be submitted on day one. Record the GEE project ID and service account credentials in .env.example (values redacted).
  - [ ] 1.2 Obtain OpenCellID API key — register at opencellid.org, download the Indonesia cell tower CSV dump, and store the key in .env.example.
  - [ ] 1.3 Confirm Ookla Open Data access — verify the Ookla fixed/mobile tile downloads for Indonesia Q1 2024 are publicly accessible via the Ookla GitHub repository; document the exact URLs and checksums in docs/data_sources.md.
  - [ ] 1.4 Initialise the monorepo directory structure:
        `
        backend/geosignal/         # Python package: pipeline, models, simulation
        frontend/                  # Next.js app
        infra/                     # Docker, Supabase migrations
        scripts/                   # Runner scripts (precompute_los.py, precompute_whatif.py, load_region.py)
        tests/                     # All Hypothesis + unit tests
        docs/                      # data_sources.md, ethical_risk_register.md
        `
  - [ ] 1.5 Create ackend/geosignal/__init__.py, pyproject.toml (Python 3.11+), and equirements.txt pinning XGBoost, LightGBM, scikit-learn, SHAP, Hypothesis, GeoPandas, Rasterio, GDAL, Shapely, and Supabase Python client.
  - [ ] 1.6 Create the Next.js frontend app with 
px create-next-app@latest frontend --typescript and install MapLibre GL JS and @maplibre/maplibre-gl-draw.
  - [ ] 1.7 Create infra/docker/Dockerfile.pipeline — Python 3.11-slim base, GDAL installed, copies ackend/ and scripts/.
  - [ ] 1.8 Create .env.example with all required keys: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY, GEE_PROJECT_ID, GEE_SERVICE_ACCOUNT_JSON, OPENCELLID_API_KEY, OOKLA_DATA_URL.

  _Requirements: 1.1, 13.3_

## Task 2: Supabase Schema and Data Models

- [ ] 2. Supabase Schema and Data Models
  - [ ] 2.1 Write Supabase SQL migration infra/migrations/001_initial_schema.sql creating all tables: grid_cells, ts_candidates, 	arget_areas, whatif_grid, model_artifacts, scoring_runs, ethical_risk_register, kecamatan_boundaries, los_results. Column definitions must exactly match the design doc schema (including ENUM types, FK constraints, and NOT NULL on LOS columns).
  - [ ] 2.2 Implement Python data models in ackend/geosignal/models.py:
        - FeatureVector dataclass with exactly eight fields: elevation_m, slope_deg, land_cover_class, canopy_height_m, distance_to_bts_m, oad_distance_m, population_density_per_km2, acility_proximity_m. No Ookla field.
        - ConfidenceThresholds dataclass (canonical, single definition) with high_km=2.0, low_km=10.0.
        - ConfidenceLevel Enum: Low, Med, High.
        - ModelTier Enum: TIER1, TIER2.
        - DataQualityReport dataclass matching design doc interface.
        - BTSCandidate, InsufficientCandidatesResult, TargetArea, SimulationResult, DragDropResult, UnavailableScenario, OutsideExtentError, EthicalRiskEntry dataclasses.
        - CONSOLIDATED_FEATURES list constant — exactly the eight field names, no admin boundary IDs, no Ookla.
        - REQUIRED_RISKS list constant with all five risk IDs.
  - [ ] 2.3 Write unit tests in 	ests/test_models.py:
        - Assert FeatureVector has land_cover_class and canopy_height_m as distinct fields (not merged).
        - Assert CONSOLIDATED_FEATURES contains exactly eight entries.
        - Assert no admin boundary ID strings (illage_id, egency_id, kecamatan_id) appear in CONSOLIDATED_FEATURES.
        - Assert ookla (case-insensitive) does not appear in any FeatureVector field name or in CONSOLIDATED_FEATURES.
        - Assert ConfidenceThresholds is importable only from geosignal.models (grep the package for duplicate definitions).
  - [ ] 2.4 Apply the migration to the local Supabase dev instance: supabase db push.

  _Requirements: 1.1, 2.1, 2.6, 2.7, 7.1, 11.2, 12.1, 12.2_

## Task 3: Data Pipeline — Geometry QC and Attribute Validation

- [ ] 3. Data Pipeline — Geometry QC and Attribute Validation
  - [ ] 3.1 Implement ackend/geosignal/pipeline/qc.py:
        - emove_null_geometries(gdf: GeoDataFrame) -> tuple[GeoDataFrame, list[LogEntry]] — removes features with null or empty geometry; logs each.
        - epair_self_intersections(gdf: GeoDataFrame) -> tuple[GeoDataFrame, list[LogEntry]] — applies uffer(0); if that produces an empty geometry, removes and logs as emoved; otherwise logs as epaired.
        - alidate_attribute_ranges(gdf: GeoDataFrame, source_name: str) -> tuple[GeoDataFrame, list[LogEntry]] — applies Indonesia-scoped bounds:
          - elevation: -11 m to 4 884 m
          - population density: = 1 000 000 per km²
          - canopy height: 0 to 100 m
          Flags out-of-range records as anomalous; excludes them from the output GeoDataFrame; logs each.
  - [ ] 3.2 Write unit tests in 	ests/test_pipeline_qc.py:
        - Null geometry rows are removed and logged.
        - Self-intersecting polygon is repaired when uffer(0) succeeds; removed and logged when it does not.
        - Elevation -12 m (below -11 floor) is flagged and excluded.
        - Elevation 4 885 m (above 4 884 ceiling) is flagged and excluded.
        - Elevation 0 m passes.
        - Population density 1 000 001 per km² is flagged; 1 000 000 passes.
        - Canopy height -0.1 m is flagged; 0.0 m passes; 100.1 m is flagged.
        - Log entry count equals the number of corrected records exactly.
  - [ ]* 3.3 Property test — Geometry QC Completeness (Property 3):
        `python
        # Feature: geosignal-ai, Property 3: Geometry QC Completeness
        @settings(max_examples=100)
        @given(feature_collections=st.lists(
            st.one_of(valid_geometry_strategy(), invalid_geometry_strategy()),
            min_size=1, max_size=50
        ))
        def test_geometry_qc_completeness(feature_collections):
            output_gdf, logs = run_geometry_qc(feature_collections)
            # All output geometries are valid
            assert all(g.is_valid and not g.is_empty for g in output_gdf.geometry)
            # Log has exactly one entry per removed or repaired input feature
            invalid_count = sum(1 for f in feature_collections if not f.geometry.is_valid or f.geometry.is_empty)
            assert len(logs) == invalid_count
        `
        **Validates: Requirements 1.2**
  - [ ]* 3.4 Property test — Attribute Range Validation (Property 4):
        `python
        # Feature: geosignal-ai, Property 4: Attribute Range Validation
        @settings(max_examples=100)
        @given(records=st.lists(attribute_record_strategy(), min_size=1, max_size=100))
        def test_attribute_range_validation(records):
            flagged_gdf, logs = validate_attribute_ranges(records, "test_source")
            out_of_range = [r for r in records if is_out_of_range(r)]
            # Flagged set equals out-of-range set
            assert set(r.id for r in flagged_gdf) == set(r.id for r in out_of_range)
            # Scoring input contains none of the flagged records
            scoring_input = [r for r in records if r not in out_of_range]
            assert not any(r in out_of_range for r in scoring_input)
        `
        **Validates: Requirements 1.3**

  _Requirements: 1.2, 1.3_

## Task 4: Data Pipeline — Harmonisation and DataQualityReport

- [ ] 4. Data Pipeline — Harmonisation and DataQualityReport
  - [ ] 4.1 Implement ackend/geosignal/pipeline/harmonise.py:
        - harmonise_rasters(sources: dict[str, rasterio.DatasetReader], resolution_variants: list[int], target_crs: str) -> dict[int, dict[str, np.ndarray]] — resamples each source raster to each resolution in esolution_variants using bilinear interpolation for continuous fields (elevation, slope, canopy height, population) and nearest-neighbour for categorical fields (land-cover class); returns a dict keyed by resolution_m then source name.
        - select_resolution(variants: dict[int, dict[str, np.ndarray]]) -> int — returns the chosen resolution (100 m default for MVP; configurable).
        - un_pipeline(region_boundary: GeoJSON, resolution_variants: list[int], output_bucket: str) -> DataQualityReport — full pipeline orchestration: QC ? harmonise ? export ? return report. Must produce outputs at = 2 resolutions.
  - [ ] 4.2 Implement DataQualityReport export: serialise to JSON and write to output_bucket/data_quality_report_{region_id}_{timestamp}.json. Include confidence_thresholds as the canonical ConfidenceThresholds instance, not hard-coded values.
  - [ ] 4.3 Write unit tests in 	ests/test_pipeline_harmonise.py:
        - un_pipeline with two resolutions produces outputs for both resolutions.
        - All output rasters share the same CRS and spatial extent across resolutions.
        - DataQualityReport contains non-null input_record_counts, emoved_records, epaired_records, chosen_resolution_m, confidence_thresholds, dataset_checksums.
        - confidence_thresholds in the report is the canonical ConfidenceThresholds from geosignal.models, not a separate instance with different class.
  - [ ]* 4.4 Property test — Multi-Resolution Output Invariant (Property 5):
        `python
        # Feature: geosignal-ai, Property 5: Multi-Resolution Output Invariant
        @settings(max_examples=50)
        @given(resolution_lists=st.lists(
            st.integers(min_value=10, max_value=1000), min_size=2, max_size=5, unique=True
        ))
        def test_multi_resolution_output(resolution_lists):
            report = run_pipeline(ntt_boundary, resolution_lists, "test_bucket")
            assert len(report.output_resolutions) >= 2
            # All resolution outputs share same CRS and extent
            crses = set(r.crs for r in report.output_resolutions.values())
            extents = set(r.extent for r in report.output_resolutions.values())
            assert len(crses) == 1
            assert len(extents) == 1
        `
        **Validates: Requirements 1.4**
  - [ ]* 4.5 Property test — DataQualityReport Completeness (Property 6):
        `python
        # Feature: geosignal-ai, Property 6: DataQualityReport Completeness
        @settings(max_examples=50)
        @given(pipeline_config=pipeline_config_strategy())
        def test_data_quality_report_completeness(pipeline_config):
            report = run_pipeline(**pipeline_config)
            assert report.input_record_counts is not None
            assert report.removed_records is not None
            assert report.repaired_records is not None
            assert report.chosen_resolution_m is not None
            assert report.confidence_thresholds is not None
            assert report.dataset_checksums is not None
            # confidence_thresholds must be the canonical type
            assert isinstance(report.confidence_thresholds, ConfidenceThresholds)
        `
        **Validates: Requirements 1.5, 7.1**
  - [ ]* 4.6 Property test — Pipeline Region Parameterisation (Property 22):
        `python
        # Feature: geosignal-ai, Property 22: Pipeline Region Parameterisation
        @settings(max_examples=30)
        @given(boundary=valid_geojson_boundary_strategy())
        def test_pipeline_region_parameterisation(boundary):
            # run_pipeline completes without error for any valid boundary GeoJSON
            report = run_pipeline(boundary, [100, 250], "test_bucket")
            assert report is not None
            assert report.region_id is not None
        `
        **Validates: Requirements 13.1**

  _Requirements: 1.4, 1.5, 1.6, 13.1_

## Task 5: GADM Level 2 Boundary Ingestion

- [ ] 5. GADM Level 2 Boundary Ingestion
  - [ ] 5.1 Download GADM Level 2 GeoPackage for Indonesia from gadm.org (gadm41_IDN_2.gpkg). Document the source URL and SHA-256 checksum in docs/data_sources.md.
  - [ ] 5.2 Implement ackend/geosignal/pipeline/boundaries.py:
        - load_gadm_level2(gpkg_path: str, region_filter: dict[str, list[str]]) -> GeoDataFrame — reads the GeoPackage and filters to the specified kabupaten/kecamatan units. egion_filter maps kabupaten name to a list of kecamatan names; pass {} to load all. For MVP, filter to kecamatan units within NTT Province, NTB Province, and Central Kalimantan Province.
        - insert_kecamatan_boundaries(gdf: GeoDataFrame, supabase_client) -> int — upserts rows into kecamatan_boundaries table (columns: kecamatan_id, kecamatan_name, kabupaten_name, province_name, egion_id, oundary_geojson); returns the count of rows upserted.
        - get_kecamatan_boundary(kecamatan_id: str, supabase_client) -> GeoJSON | None — queries kecamatan_boundaries by kecamatan_id; returns the oundary_geojson or None if not found.
  - [ ] 5.3 Write a runner script scripts/load_boundaries.py that calls load_gadm_level2 and insert_kecamatan_boundaries for all three regions (NTT Province, NTB Province, Central Kalimantan Province) and prints a summary of rows loaded per region.
  - [ ] 5.4 Write unit tests in 	ests/test_boundaries.py:
        - load_gadm_level2 with an NTT Province filter returns only NTT kecamatan units.
        - get_kecamatan_boundary returns a valid GeoJSON for a known kecamatan_id.
        - get_kecamatan_boundary returns None for an unknown kecamatan_id.
        - Each row in kecamatan_boundaries has a non-null oundary_geojson that is a valid GeoJSON polygon or multipolygon.
        - No admin boundary IDs (kecamatan_id, kabupaten_name, etc.) appear in CONSOLIDATED_FEATURES (import check).

  _Requirements: 2.4, 10.7, 13.1_

## Task 6: Feature Engineering

- [ ] 6. Feature Engineering
  - [ ] 6.1 Implement ackend/geosignal/features/terrain.py:
        - compute_slope(dem_array: np.ndarray, resolution_m: int) -> np.ndarray — computes slope in degrees from the DEM raster using the Horn (1981) method (central finite difference); returns an array of the same shape as dem_array.
  - [ ] 6.2 Implement ackend/geosignal/features/proximity.py:
        - compute_distance_to_bts(grid_centroids: np.ndarray, bts_locations: np.ndarray) -> np.ndarray — uses scikit-learn BallTree with haversine metric to compute the nearest-BTS distance (in metres) for each grid centroid. grid_centroids is (N, 2) lat/lon; ts_locations is (M, 2) lat/lon.
        - compute_road_distance(grid_centroids: np.ndarray, osm_road_lines: list[LineString]) -> np.ndarray — uses a BallTree on densified road vertices to compute the nearest OSM road distance (metres) for each centroid.
        - compute_facility_proximity(grid_centroids: np.ndarray, osm_pois: np.ndarray) -> np.ndarray — uses BallTree with haversine metric to compute distance (metres) from each grid centroid to the nearest OSM public facility POI (health, education, government categories).
  - [ ] 6.3 Implement ackend/geosignal/features/builder.py:
        - uild_feature_vectors(grid_centroids: np.ndarray, dem_array: np.ndarray, land_cover_array: np.ndarray, canopy_array: np.ndarray, population_array: np.ndarray, bts_locations: np.ndarray, osm_roads: list, osm_pois: np.ndarray, resolution_m: int) -> list[FeatureVector] — assembles all eight consolidated features into a list of FeatureVector instances aligned to grid_centroids. Calls compute_slope, compute_distance_to_bts, compute_road_distance, compute_facility_proximity internally. Writes results to grid_cells Supabase table (excluding Coverage Score fields — those are populated later by the Recommendation_Engine).
  - [ ] 6.4 Write unit tests in 	ests/test_features.py:
        - compute_slope on a flat DEM (all equal values) returns an array of zeros.
        - compute_slope on a single-direction ramp returns a uniform positive slope.
        - compute_distance_to_bts for a centroid coincident with a BTS location returns 0.0.
        - compute_distance_to_bts returns distances in metres (not degrees).
        - compute_road_distance returns 0.0 when a centroid lies exactly on a road vertex.
        - compute_facility_proximity returns finite positive values for all centroids when POIs exist.
        - uild_feature_vectors returns a list of length equal to the number of grid centroids.
        - Each FeatureVector produced has distinct land_cover_class (int) and canopy_height_m (float) fields — they are not merged or combined.

  _Requirements: 1.1, 2.1, 2.6_

## Task 7: Data Pipeline Checkpoint

- [ ] 7. Data Pipeline Checkpoint — all pipeline tests pass, QC + harmonisation + feature engineering for NTT Province MVP region produce a valid DataQualityReport and a populated grid_cells table with FeatureVector fields (Coverage Score columns left null until Task 9). GADM boundary table is populated for all three regions. No geometrically invalid features remain in any harmonised output. All property tests P3, P4, P5, P6, P22 pass.

  _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

## Task 8: Confidence Tagger

- [ ] 8. Confidence Tagger
  - [ ] 8.1 Implement ackend/geosignal/confidence.py:
        - 	ag_confidence(point: tuple[float, float], nearest_opencellid_km: float, nearest_ookla_km: float, thresholds: ConfidenceThresholds) -> ConfidenceLevel — applies the canonical tagging logic:
          - High: both distances < 	hresholds.high_km
          - Low: both distances > 	hresholds.low_km, or either record absent within 	hresholds.low_km
          - Med: all other cases
          Imports ConfidenceThresholds from geosignal.models — does not redefine it.
        - 	ag_confidence_batch(centroids: np.ndarray, opencellid_locations: np.ndarray, ookla_centroids: np.ndarray, thresholds: ConfidenceThresholds) -> list[ConfidenceLevel] — vectorised batch version using BallTree lookups for both OpenCellID and Ookla nearest-neighbour distances.
  - [ ] 8.2 Write unit tests in 	ests/test_confidence.py:
        - Distance 1.9 km / 1.9 km ? High.
        - Distance 2.0 km / 2.0 km ? Med (boundary: not strictly less than high_km).
        - Distance 1.9 km / 5.0 km ? Med (one within high, one in band).
        - Distance 5.0 km / 5.0 km ? Med (both in band 2–10).
        - Distance 10.0 km / 10.0 km ? Med (boundary: not strictly greater than low_km).
        - Distance 10.1 km / 10.1 km ? Low.
        - Either record absent ? Low.
        - Absence of record must NOT be logged or treated as confirmed zero coverage (documented in the test assertion comment).
  - [ ]* 8.3 Property test — Confidence Tag Correctness (Property 8):
        `python
        # Feature: geosignal-ai, Property 8: Confidence Tag Correctness
        @settings(max_examples=100)
        @given(
            nearest_opencellid_km=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
            nearest_ookla_km=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
        )
        def test_confidence_tag_correctness(nearest_opencellid_km, nearest_ookla_km):
            thresholds = ConfidenceThresholds()  # canonical defaults
            result = tag_confidence((0.0, 0.0), nearest_opencellid_km, nearest_ookla_km, thresholds)
            if nearest_opencellid_km < thresholds.high_km and nearest_ookla_km < thresholds.high_km:
                assert result == ConfidenceLevel.High
            elif nearest_opencellid_km > thresholds.low_km and nearest_ookla_km > thresholds.low_km:
                assert result == ConfidenceLevel.Low
            else:
                assert result == ConfidenceLevel.Med
        `
        **Validates: Requirements 7.1, 7.2, 7.5, 2.5**

  _Requirements: 7.1, 7.2, 7.5, 2.5_

## Task 9: Recommendation Engine — Coverage Score, Tier Routing, AHPAdapter, and XGBoost/LightGBM Adapters

- [ ] 9. Recommendation Engine — Coverage Score, Tier Routing, AHPAdapter, and GBM Adapters
  - [ ] 9.1 Implement ackend/geosignal/scoring.py:
        - ScoringAdapter Protocol with predict(features: np.ndarray) -> np.ndarray and shap_values(features: np.ndarray) -> np.ndarray.
        - AHPAdapter — implements ScoringAdapter. Holds a normalised weight dict over CONSOLIDATED_FEATURES. The predict method applies equity weighting per Requirement 9.1: uplifts acility_proximity_m and population_density_per_km2 weights relative to baseline. The weights are configurable per DataQualityReport / region; not hard-coded. Equity weighting is implemented HERE — Task 17 only verifies it, not re-implements it.
        - XGBoostAdapter — implements ScoringAdapter; wraps a trained XGBoost model.
        - LightGBMAdapter — implements ScoringAdapter; wraps a trained LightGBM model.
        - select_tier(kecamatan_id: str, ookla_tile_count: int) -> ModelTier — returns TIER1 if ookla_tile_count == 0, else TIER2; no other conditions.
        - compute_coverage_score(features: FeatureVector, model: ScoringAdapter) -> float — returns a float in [0.0, 100.0]; clips output to this range.
  - [ ] 9.2 Write unit tests in 	ests/test_scoring.py:
        - select_tier with ookla_tile_count=0 returns TIER1.
        - select_tier with ookla_tile_count=1 returns TIER2.
        - select_tier with ookla_tile_count=999 returns TIER2.
        - compute_coverage_score returns a float in [0.0, 100.0] for both AHPAdapter and XGBoostAdapter.
        - AHPAdapter equity weighting: a FeatureVector A with lower acility_proximity_m than B (all else equal, both non-zero population) produces score(A) >= score(B).
        - AHPAdapter equity weighting: a FeatureVector C with higher population_density_per_km2 than D (all else equal) produces score(C) >= score(D).
        - AHP baseline is recomputed per scoring run: confirm that calling AHPAdapter.set_regional_baseline(...) with different baselines produces different SHAP values; the adapter does NOT cache a stale baseline from a previous run.
  - [ ]* 9.3 Property test — Coverage Score Bounds Invariant (Property 1):
        `python
        # Feature: geosignal-ai, Property 1: Coverage Score Bounds Invariant
        @settings(max_examples=100)
        @given(
            elevation_m=st.floats(min_value=-11, max_value=4884),
            slope_deg=st.floats(min_value=0, max_value=90),
            land_cover_class=st.integers(min_value=10, max_value=95),
            canopy_height_m=st.floats(min_value=0, max_value=100),
            distance_to_bts_m=st.floats(min_value=0, max_value=200_000),
            road_distance_m=st.floats(min_value=0, max_value=200_000),
            population_density_per_km2=st.floats(min_value=0, max_value=1_000_000),
            facility_proximity_m=st.floats(min_value=0, max_value=200_000),
        )
        def test_coverage_score_bounds(elevation_m, slope_deg, land_cover_class, canopy_height_m,
                                       distance_to_bts_m, road_distance_m, population_density_per_km2,
                                       facility_proximity_m):
            fv = FeatureVector(elevation_m=elevation_m, slope_deg=slope_deg,
                               land_cover_class=land_cover_class, canopy_height_m=canopy_height_m,
                               distance_to_bts_m=distance_to_bts_m, road_distance_m=road_distance_m,
                               population_density_per_km2=population_density_per_km2,
                               facility_proximity_m=facility_proximity_m)
            for adapter in [AHPAdapter(), XGBoostAdapter()]:
                score = compute_coverage_score(fv, adapter)
                assert 0.0 <= score <= 100.0
        `
        **Validates: Requirements 2.1**
  - [ ]* 9.4 Property test — Tier Routing Correctness (Property 2):
        `python
        # Feature: geosignal-ai, Property 2: Tier Routing Correctness
        @settings(max_examples=100)
        @given(ookla_tile_count=st.integers(min_value=0))
        def test_tier_routing_correctness(ookla_tile_count):
            tier = select_tier("test_kecamatan", ookla_tile_count)
            if ookla_tile_count == 0:
                assert tier == ModelTier.TIER1
            else:
                assert tier == ModelTier.TIER2
        `
        **Validates: Requirements 2.2, 2.3, 9.7**
  - [ ]* 9.5 Property test — Equity Weighting Direction (Property 17):
        `python
        # Feature: geosignal-ai, Property 17: Equity Weighting Direction
        @settings(max_examples=100)
        @given(
            base_fv=feature_vector_strategy(),
            facility_proximity_a=st.floats(min_value=0, max_value=50_000),
            facility_proximity_b=st.floats(min_value=0, max_value=50_000),
            pop_density_c=st.floats(min_value=0.01, max_value=1_000_000),
            pop_density_d=st.floats(min_value=0.01, max_value=1_000_000),
        )
        def test_equity_weighting_direction(base_fv, facility_proximity_a, facility_proximity_b,
                                            pop_density_c, pop_density_d):
            adapter = AHPAdapter()
            # Facility proximity: A closer than B => score(A) >= score(B)
            assume(facility_proximity_a < facility_proximity_b)
            fv_a = replace(base_fv, facility_proximity_m=facility_proximity_a, population_density_per_km2=100)
            fv_b = replace(base_fv, facility_proximity_m=facility_proximity_b, population_density_per_km2=100)
            assert compute_coverage_score(fv_a, adapter) >= compute_coverage_score(fv_b, adapter)
            # Population density: C higher than D => score(C) >= score(D)
            assume(pop_density_c > pop_density_d)
            fv_c = replace(base_fv, population_density_per_km2=pop_density_c)
            fv_d = replace(base_fv, population_density_per_km2=pop_density_d)
            assert compute_coverage_score(fv_c, adapter) >= compute_coverage_score(fv_d, adapter)
        `
        **Validates: Requirements 9.1**

  _Requirements: 2.1, 2.2, 2.3, 9.1, 9.7, 13.4_

## Task 10: Recommendation Engine — SHAP for Both Tiers

- [ ] 10. Recommendation Engine — SHAP for Both Tiers
  - [ ] 10.1 Implement ackend/geosignal/shap_explainer.py:
        - compute_ahp_shap(feature_vector: FeatureVector, weights: dict[str, float], regional_baseline: dict[str, float]) -> dict[str, float] — computes SHAP for Tier 1 using the linear formula: weight_i × (feature_value_i - baseline_i) for each feature in CONSOLIDATED_FEATURES. egional_baseline is the mean of each feature across all scored grid cells in the current egion_id for this run; it must be passed in (not cached inside the function from a prior call).
        - compute_gbm_shap(feature_vectors: np.ndarray, adapter: Union[XGBoostAdapter, LightGBMAdapter]) -> np.ndarray — computes SHAP values via SHAP library's TreeExplainer.
        - ormat_shap_top3(shap_values: dict[str, float]) -> list[dict] — returns a list of exactly 3 dicts, each with eature_name: str, alue: float, direction: str (one of positive or 
egative). Sorted by absolute value descending.
  - [ ] 10.2 Write unit tests in 	ests/test_shap.py:
        - compute_ahp_shap returns a dict with exactly 8 keys matching CONSOLIDATED_FEATURES.
        - No value in the returned dict is None.
        - When egional_baseline is the same as eature_vector values, all SHAP values are 0.0.
        - ormat_shap_top3 returns exactly 3 entries.
        - Each entry has non-empty eature_name and direction in {"positive", "negative"}.
        - compute_ahp_shap with a different egional_baseline input produces different output — confirms baseline is not stale/cached.
  - [ ]* 10.3 Property test — SHAP Completeness (Property 10):
        `python
        # Feature: geosignal-ai, Property 10: SHAP Completeness
        @settings(max_examples=100)
        @given(
            fv=feature_vector_strategy(),
            baseline=regional_baseline_strategy(),
            weights=ahp_weight_strategy(),
        )
        def test_shap_completeness(fv, baseline, weights):
            shap_vals = compute_ahp_shap(fv, weights, baseline)
            assert set(shap_vals.keys()) == set(CONSOLIDATED_FEATURES)
            assert all(v is not None for v in shap_vals.values())
            # Also verify baseline contains all features
            assert set(baseline.keys()) == set(CONSOLIDATED_FEATURES)
        `
        **Validates: Requirements 4.6, 8.1, 8.3**
  - [ ]* 10.4 Property test — SHAP Top-3 Format Invariant (Property 15):
        `python
        # Feature: geosignal-ai, Property 15: SHAP Top-3 Format Invariant
        @settings(max_examples=100)
        @given(shap_dict=shap_values_dict_strategy())
        def test_shap_top3_format(shap_dict):
            top3 = format_shap_top3(shap_dict)
            assert len(top3) == 3
            for entry in top3:
                assert isinstance(entry["feature_name"], str) and entry["feature_name"] != ""
                assert entry["direction"] in {"positive", "negative"}
        `
        **Validates: Requirements 8.2**

  _Requirements: 4.6, 8.1, 8.2, 8.3, 8.5_

## Task 11: Recommendation Engine — Deforestation Constraint and Canopy Exclusion

- [ ] 11. Recommendation Engine — Deforestation Constraint and Canopy Exclusion
  - [ ] 11.1 Implement ackend/geosignal/constraints.py:
        - HIGH_CANOPY_LAND_COVER_CLASSES = {10, 20} constant.
        - CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M = 15.0 constant.
        - is_high_canopy(land_cover_class: int, canopy_height_m: float) -> bool — returns True if and only if BOTH land_cover_class in HIGH_CANOPY_LAND_COVER_CLASSES AND canopy_height_m >= CANOPY_HEIGHT_EXCLUSION_THRESHOLD_M. Both conditions required; neither alone is sufficient.
  - [ ] 11.2 Write unit tests in 	ests/test_constraints.py:
        - land_cover_class=10, canopy_height_m=15.0 ? True (both conditions met, at boundary).
        - land_cover_class=10, canopy_height_m=14.9 ? False (height below threshold).
        - land_cover_class=20, canopy_height_m=20.0 ? True.
        - land_cover_class=30, canopy_height_m=30.0 ? False (non-forest class, even with tall canopy).
        - land_cover_class=10, canopy_height_m=0.0 ? False (forest class, no canopy).
        - land_cover_class=20, canopy_height_m=14.9 ? False (shrubland below threshold — should NOT be excluded).
        - Forest class (10) with 34 m canopy ? True (explicitly documented in design doc).
        - Plantation-like: class 20 with 16 m canopy ? True (both conditions).

  _Requirements: 4.3, 9.2_

## Task 12: DEM Line-of-Sight Precomputation (Offline Batch)

- [ ] 12. DEM Line-of-Sight Precomputation (Offline Batch)
  - [ ] 12.1 Implement ackend/geosignal/los.py:
        - compute_los_grid(dem_path: str, candidate_lat: float, candidate_lon: float, radius_m: float, observer_height_m: float = 30.0) -> np.ndarray — runs GDAL gdal_viewshed to produce a binary visibility raster (1 = visible, 0 = not visible) for all grid cells within adius_m of the candidate site. Returns a numpy array aligned to the DEM grid.
        - store_los_result(candidate_id: str, region_id: str, los_array: np.ndarray, supabase_client) -> None — serialises the LOS array and upserts to the los_results Supabase table (columns: candidate_id, egion_id, los_array_blob, computed_at).
        - load_los_result(candidate_id: str, region_id: str, supabase_client) -> np.ndarray | None — retrieves and deserialises LOS array from los_results; returns None if not found.
  - [ ] 12.2 Write scripts/precompute_los.py — iterates over all BTS candidate sites in ts_candidates for the given --region argument, calls compute_los_grid, and calls store_los_result. Prints progress (candidate_id, elapsed_ms per site). Accepts --region and --dem-path CLI arguments. Designed to run offline before demo.
  - [ ] 12.3 Write unit tests in 	ests/test_los.py:
        - compute_los_grid on a flat DEM returns an array where all cells within adius_m are visible (all 1s).
        - compute_los_grid result has the same CRS and spatial extent as the input DEM within the radius.
        - store_los_result followed by load_los_result round-trips the array correctly (all values preserved).
        - load_los_result for an unknown candidate_id returns None.
        - BallTree candidate search (Task 13) must not emit a BTSCandidate whose candidate_id has no precomputed LOS entry — verify this at the los_validated field level.

  _Requirements: 4.4, 4.1_

## Task 13: Recommendation Engine — BallTree Candidate Search

- [ ] 13. Recommendation Engine — BallTree Candidate Search
  - [ ] 13.1 Implement ackend/geosignal/candidates.py:
        - ank_bts_candidates(grid_cells: np.ndarray, coverage_scores: np.ndarray, land_cover_classes: np.ndarray, canopy_heights_m: np.ndarray, n_candidates: int = 10, exclude_high_canopy: bool = True) -> list[BTSCandidate] | InsufficientCandidatesResult — BallTree-indexed search over grid_cells. Steps:
          1. Apply is_high_canopy filter (if exclude_high_canopy=True).
          2. Look up precomputed LOS for remaining candidates; exclude any without a precomputed LOS result.
          3. Rank remaining candidates by expected_improvement (mean Coverage Score delta in BTS signal radius).
          4. If fewer than 2 candidates survive, return InsufficientCandidatesResult(surviving_count=N, reason=..., target_area_id=...).
          5. Otherwise return list of BTSCandidate objects with los_validated=True for all entries.
        - compute_expected_improvement(candidate_coord: tuple, grid_cells: np.ndarray, coverage_scores: np.ndarray, signal_radius_m: float = 5000) -> float — BallTree query within radius; returns mean score delta assuming BTS placement.
  - [ ] 13.2 Write unit tests in 	ests/test_candidates.py:
        - With 10 valid non-canopy candidates, ank_bts_candidates returns list of length = 2.
        - All returned BTSCandidate have los_validated=True.
        - No BTSCandidate satisfies is_high_canopy(land_cover_class, canopy_height_m).
        - Returned list is in non-increasing order by expected_improvement.
        - Exactly 0 surviving candidates ? InsufficientCandidatesResult with surviving_count=0.
        - Exactly 1 surviving candidate ? InsufficientCandidatesResult with surviving_count=1.
        - InsufficientCandidatesResult.reason is non-empty string.
        - When all candidates are high-canopy, InsufficientCandidatesResult.reason mentions "canopy".
  - [ ]* 13.3 Property test — BTS Candidate List Invariants (Property 9):
        `python
        # Feature: geosignal-ai, Property 9: BTS Candidate List Invariants
        @settings(max_examples=100)
        @given(
            grid_data=grid_with_canopy_strategy(),   # produces grid_cells, coverage_scores,
                                                     # land_cover_classes, canopy_heights_m
                                                     # with varying proportions of canopy cells
        )
        def test_bts_candidate_list_invariants(grid_data):
            result = rank_bts_candidates(**grid_data)
            valid_count = sum(
                1 for i in range(len(grid_data["grid_cells"]))
                if not is_high_canopy(grid_data["land_cover_classes"][i], grid_data["canopy_heights_m"][i])
            )
            if valid_count < 2:
                assert isinstance(result, InsufficientCandidatesResult)
                assert result.surviving_count == valid_count
            else:
                assert isinstance(result, list)
                assert len(result) >= 2
                for i in range(len(result) - 1):
                    assert result[i].expected_improvement >= result[i+1].expected_improvement
                assert all(c.los_validated for c in result)
                assert not any(is_high_canopy(c.land_cover_class, c.canopy_height_m) for c in result)
        `
        **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.7, 9.2**

  _Requirements: 4.1, 4.2, 4.3, 4.4, 4.7, 9.2_

## Task 14: Recommendation Engine — Spatial CV and Per-Kecamatan Reporting

- [ ] 14. Recommendation Engine — Spatial CV and Per-Kecamatan Reporting
  - [ ] 14.1 Implement ackend/geosignal/model_cv.py:
        - spatial_cv(data: GeoDataFrame, kecamatan_column: str, model_cls: type, n_folds: int) -> CVResult — performs spatially-blocked cross-validation where entire kecamatan units are held out as test blocks (never random point split). Returns CVResult with per_kecamatan_metrics: dict[str, dict] containing accuracy entries for ALL kecamatan IDs in the input data.
        - CVResult dataclass with overall_rmse: float, overall_r2: float, per_kecamatan_metrics: dict[str, dict], old_assignments: dict[str, int].
  - [ ] 14.2 Write unit tests in 	ests/test_model_cv.py:
        - For each fold, the intersection of train-set and test-set kecamatan IDs is empty.
        - CVResult.per_kecamatan_metrics contains an entry for every kecamatan ID in the input data.
        - No kecamatan's accuracy is hidden behind an aggregate-only metric.
        - Fold assignments are mutually exclusive (no kecamatan in two folds simultaneously).
  - [ ]* 14.3 Property test — Spatial CV Kecamatan Disjointness (Property 7):
        `python
        # Feature: geosignal-ai, Property 7: Spatial CV Kecamatan Disjointness
        @settings(max_examples=50)
        @given(kecamatan_list=st.lists(
            st.text(min_size=1, max_size=20), min_size=4, max_size=30, unique=True
        ))
        def test_spatial_cv_disjointness(kecamatan_list):
            data = make_mock_geodataframe(kecamatan_list)
            result = spatial_cv(data, "kecamatan_id", MockModel, n_folds=min(len(kecamatan_list), 5))
            for fold_id in set(result.fold_assignments.values()):
                train_kecs = {k for k, f in result.fold_assignments.items() if f != fold_id}
                test_kecs = {k for k, f in result.fold_assignments.items() if f == fold_id}
                assert train_kecs.isdisjoint(test_kecs)
        `
        **Validates: Requirements 2.4, 13.5**
  - [ ]* 14.4 Property test — Per-Kecamatan Accuracy Reporting (Property 18):
        `python
        # Feature: geosignal-ai, Property 18: Per-Kecamatan Accuracy Reporting
        @settings(max_examples=50)
        @given(kecamatan_list=st.lists(
            st.text(min_size=1), min_size=2, max_size=20, unique=True
        ))
        def test_per_kecamatan_accuracy_reporting(kecamatan_list):
            data = make_mock_geodataframe(kecamatan_list)
            result = spatial_cv(data, "kecamatan_id", MockModel, n_folds=min(len(kecamatan_list), 5))
            for kec_id in kecamatan_list:
                assert kec_id in result.per_kecamatan_metrics, \
                    f"Kecamatan {kec_id} missing from per_kecamatan_metrics"
        `
        **Validates: Requirements 9.4**

  _Requirements: 2.4, 9.4, 13.5_

## Task 15: Recommendation Engine — Model Versioning and Audit Log

- [ ] 15. Recommendation Engine — Model Versioning and Audit Log
  - [ ] 15.1 Implement ackend/geosignal/versioning.py:
        - ssign_model_version(tier: ModelTier, algorithm: str, training_run_id: str) -> str — generates a semantic version string (e.g., hp-v1.0, xgb-v2.3) and inserts a record into model_artifacts before the model is used for any prediction.
        - log_scoring_run(run_id: str, model_version: str, tier: ModelTier, region_kecamatans: list[str], resolution_m: int, input_checksums: dict[str, str], candidate_count: int, ahp_regional_baseline: dict[str, float] | None) -> None — inserts a row into scoring_runs with all required fields including the AHP regional baseline in input_checksums JSONB (for Tier 1 runs). etained_for_months defaults to 12.
        - get_scoring_run(run_id: str) -> dict | None — retrieves a scoring run record from Supabase.
  - [ ] 15.2 Write unit tests in 	ests/test_audit.py:
        - ssign_model_version returns a non-empty string before any compute_coverage_score call.
        - log_scoring_run inserts a record retrievable by un_id.
        - The record contains non-null values for all required fields: un_id, model_version, 	ier, egion_kecamatans, esolution_m, input_checksums, candidate_count, 	imestamp.
        - For Tier 1 runs, input_checksums contains the AHP regional baseline.
        - Retaining periods: default is 12 months.
  - [ ]* 15.3 Property test — Scoring Run Log Completeness (Property 16):
        `python
        # Feature: geosignal-ai, Property 16: Scoring Run Log Completeness
        @settings(max_examples=100)
        @given(run_params=scoring_run_params_strategy())
        def test_scoring_run_log_completeness(run_params):
            run_id = str(uuid.uuid4())
            log_scoring_run(run_id=run_id, **run_params)
            record = get_scoring_run(run_id)
            assert record is not None
            for field in ["run_id", "model_version", "tier", "region_kecamatans",
                          "resolution_m", "input_checksums", "candidate_count", "timestamp"]:
                assert record[field] is not None
        `
        **Validates: Requirements 8.5, 11.2**
  - [ ]* 15.4 Property test — Model Artifact Immutability (Property 20):
        `python
        # Feature: geosignal-ai, Property 20: Model Artifact Immutability
        @settings(max_examples=20)
        @given(retraining_count=st.integers(min_value=1, max_value=5))
        def test_model_artifact_immutability(retraining_count):
            initial_count = count_model_artifacts()
            for i in range(retraining_count):
                assign_model_version(ModelTier.TIER2, "XGBoost", f"train_run_{i}")
            final_count = count_model_artifacts()
            assert final_count == initial_count + retraining_count
            # All original entries unchanged
            for original_version in get_all_version_ids()[:initial_count]:
                assert get_model_artifact(original_version) is not None
        `
        **Validates: Requirements 11.5**
  - [ ]* 15.5 Property test — Model Version Assignment Before Use (Property 21):
        `python
        # Feature: geosignal-ai, Property 21: Model Version Assignment Before Use
        @settings(max_examples=50)
        @given(fv=feature_vector_strategy())
        def test_model_version_assigned_before_use(fv):
            adapter = AHPAdapter()
            # Version must be non-empty before first predict call
            assert adapter.version_id is not None and adapter.version_id != ""
            # Compute score — version must still be same non-empty value
            compute_coverage_score(fv, adapter)
            assert adapter.version_id is not None and adapter.version_id != ""
        `
        **Validates: Requirements 11.1**

  _Requirements: 11.1, 11.2, 11.4, 11.5, 8.5_

## Task 16: Recommendation Engine Checkpoint

- [ ] 16. Recommendation Engine Checkpoint — all Recommendation_Engine tests pass. Coverage Scores are populated in grid_cells for NTT Province MVP. ts_candidates table is populated for NTT Province. SHAP values are attached to all candidates and cells. Spatial CV result exists with per-kecamatan breakdown. Equity weighting is active in AHPAdapter. Deforestation constraint (is_high_canopy) is applied by default. scoring_runs audit log contains at least one complete entry. All property tests P1, P2, P7, P8, P9, P10, P15, P16, P17, P18, P20, P21 pass.

  _Requirements: 2.1, 2.2, 2.3, 2.4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 7.1, 8.1, 8.3, 9.1, 9.2, 9.4, 9.7, 11.1, 11.2, 11.5_

## Task 17: Equity Weighting Verification, EthicalRiskRegister, and Req 13.2 Distributed Stub

- [ ] 17. Equity Weighting Verification Gate, EthicalRiskRegister, and Req 13.2 Distributed Stub
  - [ ] 17.1 Equity weighting verification gate — run the P17 property test (	est_equity_weighting_direction) against the live AHPAdapter implementation from Task 9. This task does NOT re-implement equity weighting; it is the formal acceptance gate. Document the test run result in docs/ethical_safeguard_log.md.
  - [ ] 17.2 Implement ackend/geosignal/ethics.py:
        - EthicalRiskEntry dataclass (imported from geosignal.models).
        - EthicalRiskRegister class with an entries: dict[str, EthicalRiskEntry] attribute and a alidate() method that raises ValueError if any of the five required risk IDs (digital_exclusion, deforestation, opencellid_sparsity_misread, low_confidence_funding_decisions, maup_resampling_mismatch) is absent or has empty required fields.
        - Populate all five REQUIRED_RISKS entries with complete isk_description, impact, mitigation, and esponsible_owner_role content. Owner roles must be specific role titles (e.g., "Data Science Lead", "Ethics Review Officer").
        - sync_to_supabase(register: EthicalRiskRegister, supabase_client) -> None — upserts all entries to the ethical_risk_register table.
  - [ ] 17.3 Implement the Req 13.2 distributed scoring stub in ackend/geosignal/distributed.py:
        - distribute_scoring(feature_vectors: list[FeatureVector], adapter: ScoringAdapter, region_id: str) -> list[float] — sequential implementation for MVP: iterates over feature vectors and calls compute_coverage_score. Includes a prominent # TODO Phase 3: swap sequential loop for Spark/Dask partitioned execution across 3T provinces comment above the implementation.
  - [ ] 17.4 Write unit tests in 	ests/test_ethics.py:
        - EthicalRiskRegister.validate() passes when all five entries are present and complete.
        - EthicalRiskRegister.validate() raises ValueError if any of the five required risk IDs is missing.
        - EthicalRiskRegister.validate() raises ValueError if any entry has an empty isk_description, impact, mitigation, or esponsible_owner_role.
  - [ ]* 17.5 Property test — Ethical Risk Register Completeness (Property 19):
        `python
        # Feature: geosignal-ai, Property 19: Ethical Risk Register Completeness
        def test_ethical_risk_register_completeness():
            register = EthicalRiskRegister()
            for risk_id in REQUIRED_RISKS:
                assert risk_id in register.entries, f"Missing risk: {risk_id}"
                entry = register.entries[risk_id]
                assert entry.risk_description != ""
                assert entry.impact != ""
                assert entry.mitigation != ""
                assert entry.responsible_owner_role != ""
        `
        **Validates: Requirements 9.6**

  _Requirements: 9.1, 9.6, 13.2_

## Task 18: Data Privacy Property Test (Property 26)

- [ ] 18. Data Privacy Property Test (Property 26)
  - [ ] 18.1 Implement 	ests/test_privacy.py:
        - 	est_schema_no_pii_fields — introspect the Supabase schema definition (from infra/migrations/001_initial_schema.sql) for all seven tables (grid_cells, ts_candidates, 	arget_areas, whatif_grid, model_artifacts, scoring_runs, ethical_risk_register). Assert that no column name matches PII patterns: device_id, user_id, phone_number, email, household_id, individual_id, personal_name, or any column containing aw_speedtest, aw_crowdsource.
        - 	est_feature_vector_no_ookla_field — assert that FeatureVector.__dataclass_fields__ contains no field whose name includes ookla (case-insensitive). Assert CONSOLIDATED_FEATURES contains no string matching ookla (case-insensitive).
        - 	est_data_quality_report_no_raw_crowdsourced_payloads — create a DataQualityReport instance and serialise it to JSON; assert the JSON string contains no key or value matching aw_crowdsource, individual_speedtest, device_identifier.
  - [ ]* 18.2 Property test — PII Absence Invariant (Property 26):
        `python
        # Feature: geosignal-ai, Property 26: PII Absence Invariant
        def test_pii_absence_invariant():
            # Static schema introspection — no property-generation needed
            pii_patterns = [
                "device_id", "user_id", "phone", "email", "household",
                "individual", "personal", "raw_speedtest", "raw_crowdsource",
            ]
            schema_columns = get_all_schema_column_names()  # reads from migration SQL
            for col in schema_columns:
                for pattern in pii_patterns:
                    assert pattern not in col.lower(), \
                        f"PII pattern '{pattern}' found in column '{col}'"
            # FeatureVector has no Ookla field
            fv_fields = [f.lower() for f in FeatureVector.__dataclass_fields__]
            assert not any("ookla" in f for f in fv_fields)
            # DataQualityReport export has no raw crowd-sourced payloads
            report = DataQualityReport(
                region_id="test", input_record_counts={}, removed_records={},
                repaired_records={}, anomalous_records={}, chosen_resolution_m=100,
                confidence_thresholds=ConfidenceThresholds(), dataset_checksums={},
                timestamp=datetime.utcnow()
            )
            serialised = json.dumps(dataclasses.asdict(report))
            for raw_pattern in ["raw_crowdsource", "individual_speedtest", "device_identifier"]:
                assert raw_pattern not in serialised
        `
        **Validates: Requirements 12.1, 12.2, 12.3, 12.4**

  _Requirements: 12.1, 12.2, 12.3, 12.4_

## Task 19: What-If Grid Precomputation (Offline Batch)

- [ ] 19. What-If Grid Precomputation (Offline Batch)
  - [ ] 19.1 Implement ackend/geosignal/whatif.py:
        - precompute_whatif_grid(region_id: str, candidates: list[BTSCandidate], grid_cells: np.ndarray, coverage_scores: np.ndarray, los_results: dict[str, np.ndarray], signal_radius_m: float = 5000) -> list[WhatIfScenario] — for each candidate × scenario, computes delta_coverage_score, pct_good_change, illages_newly_covered, and 
ew_coverage_score using the precomputed LOS grid (not live DEM). Returns a list of WhatIfScenario objects ready to write to whatif_grid.
        - write_whatif_grid(scenarios: list[WhatIfScenario], supabase_client) -> int — batch-upserts all scenarios to the whatif_grid Supabase table; returns count of rows written.
        - WhatIfScenario dataclass matching the whatif_grid table schema.
  - [ ] 19.2 Write scripts/precompute_whatif.py — CLI script that: loads all ts_candidates for the given --region, loads grid_cells and Coverage Scores, loads all LOS results from los_results, calls precompute_whatif_grid, and calls write_whatif_grid. Accepts --region CLI argument. Prints progress (candidate count, elapsed_ms). Designed to run offline before demo.
  - [ ] 19.3 Write unit tests in 	ests/test_whatif.py:
        - precompute_whatif_grid produces one scenario per candidate.
        - Each scenario has numerically finite pct_good_change, illages_newly_covered, and 
ew_coverage_score.
        - write_whatif_grid followed by simulate_bts_placement returns a SimulationResult (not UnavailableScenario) for written candidates.
        - simulate_bts_placement for an unwritten candidate returns UnavailableScenario.
        - precompute_whatif_grid does NOT perform any DEM computation (uses LOS array passed in, not gdal_viewshed calls).

  _Requirements: 5.1, 5.4, 6.1, 6.6_

## Task 20: Target Area Resolution

- [ ] 20. Target Area Resolution
  - [ ] 20.1 Implement ackend/geosignal/target_area.py:
        - esolve_target_area(region_id: str, selection_method: Literal["drawn_polygon", "kecamatan"], payload: GeoJSON | str) -> TargetArea — for kecamatan method, calls get_kecamatan_boundary to look up the GADM Level 2 geometry and sets TargetArea.kecamatan_id; for drawn_polygon method, accepts the GeoJSON directly and sets kecamatan_id=None. Raises a structured ValidationError if the drawn polygon is self-intersecting (does NOT auto-repair user input). Writes the resolved TargetArea to the 	arget_areas Supabase table.
        - ilter_grid_cells_to_target_area(target_area: TargetArea, grid_cells: np.ndarray) -> np.ndarray — returns only grid cell coordinates that fall within 	arget_area.boundary.
  - [ ] 20.2 Write unit tests in 	ests/test_target_area.py:
        - esolve_target_area with kecamatan method and a valid kecamatan_id returns a TargetArea whose oundary equals the GADM Level 2 geometry for that kecamatan.
        - esolve_target_area with kecamatan method sets kecamatan_id equal to the input.
        - esolve_target_area with drawn_polygon method sets kecamatan_id=None.
        - esolve_target_area with drawn_polygon method and a self-intersecting polygon raises ValidationError (not auto-repaired).
        - ilter_grid_cells_to_target_area returns only cells inside the boundary.
        - ilter_grid_cells_to_target_area returns no cells outside the boundary.
        - Switching region in the selector resets the target-area selection — verify that a TargetArea resolved for egion_id="ntt" is not reused for egion_id="ntb".
  - [ ]* 20.3 Property test — Target Area Resolution Correctness (Property 25):
        `python
        # Feature: geosignal-ai, Property 25: Target Area Resolution Correctness
        @settings(max_examples=50)
        @given(
            kecamatan_id=st.sampled_from(NTT_KECAMATAN_IDS),
            drawn_polygon=valid_polygon_geojson_strategy(),
        )
        def test_target_area_resolution_correctness(kecamatan_id, drawn_polygon):
            # Kecamatan selection
            ta_kec = resolve_target_area("ntt", "kecamatan", kecamatan_id)
            expected_boundary = get_kecamatan_boundary(kecamatan_id, mock_supabase)
            assert ta_kec.boundary == expected_boundary
            assert ta_kec.kecamatan_id == kecamatan_id

            # Drawn polygon selection
            ta_poly = resolve_target_area("ntt", "drawn_polygon", drawn_polygon)
            assert ta_poly.boundary == drawn_polygon
            assert ta_poly.kecamatan_id is None

            # grid_cells filtered to boundary
            grid = make_test_grid_cells()
            filtered = filter_grid_cells_to_target_area(ta_kec, grid)
            for coord in filtered:
                assert point_in_polygon(coord, ta_kec.boundary)
        `
        **Validates: Requirements 10.7, 10.8, 4.1, 5.1**

  _Requirements: 10.7, 10.8, 4.1, 5.1_

## Task 21: Simulation Engine — Before/After Simulation

- [ ] 21. Simulation Engine — Before/After Simulation
  - [ ] 21.1 Implement ackend/geosignal/simulation.py:
        - simulate_bts_placement(candidate_id: str, region_id: str) -> SimulationResult | UnavailableScenario — looks up the precomputed whatif_grid for (candidate_id, region_id). Returns UnavailableScenario if no entry exists; MUST NOT call any DEM computation, interpolation, or extrapolation function in that path. When found, returns SimulationResult with efore_heatmap, fter_heatmap, pct_good_change, illages_newly_covered, 
ew_coverage_score, elapsed_ms (= 3 000 ms).
  - [ ] 21.2 Write unit tests in 	ests/test_simulation.py:
        - simulate_bts_placement for a known (candidate_id, region_id) in the whatif_grid returns SimulationResult.
        - SimulationResult has finite (non-None, non-NaN, non-Inf) values for pct_good_change, illages_newly_covered, 
ew_coverage_score.
        - simulate_bts_placement for an unknown (candidate_id, region_id) returns UnavailableScenario.
        - UnavailableScenario contains a human-readable message string.
        - No DEM/GDAL function is called when returning UnavailableScenario (mock/spy verification).
  - [ ]* 21.3 Property test — Simulation Unavailability Contract (Property 12):
        `python
        # Feature: geosignal-ai, Property 12: Simulation Unavailability Contract
        @settings(max_examples=100)
        @given(
            candidate_id=st.uuids().map(str),
            region_id=st.sampled_from(["ntt", "ntb", "central_kalimantan"]),
        )
        def test_simulation_unavailability_contract(candidate_id, region_id):
            # Use a blank whatif_grid that definitely doesn't contain this candidate
            result = simulate_bts_placement(candidate_id, region_id)
            if not whatif_grid_has(candidate_id, region_id):
                assert isinstance(result, UnavailableScenario)
                # Ensure no DEM computation was triggered
                assert dem_compute_call_count() == 0
        `
        **Validates: Requirements 5.4**
  - [ ]* 21.4 Property test — Simulation Metric Completeness (Property 23):
        `python
        # Feature: geosignal-ai, Property 23: Simulation Metric Completeness
        @settings(max_examples=50)
        @given(scenario=precomputed_scenario_strategy())
        def test_simulation_metric_completeness(scenario):
            write_whatif_grid([scenario], mock_supabase)
            result = simulate_bts_placement(scenario.candidate_id, scenario.region_id)
            assert isinstance(result, SimulationResult)
            assert math.isfinite(result.pct_good_change)
            assert isinstance(result.villages_newly_covered, int)
            assert math.isfinite(result.new_coverage_score)
        `
        **Validates: Requirements 5.3**

  _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

## Task 22: Simulation Engine — Drag-and-Drop Simulation

- [ ] 22. Simulation Engine — Drag-and-Drop Simulation
  - [ ] 22.1 Implement drag_drop_lookup in ackend/geosignal/simulation.py:
        - drag_drop_lookup(dropped_lat: float, dropped_lon: float, region_id: str, grid: WhatIfGrid, overlay_enabled: bool = False) -> DragDropResult | OutsideExtentError — snaps to nearest precomputed cell using BallTree on grid centroids. Returns OutsideExtentError (with the region's extent in the payload) if outside grid extent. Returns DragDropResult with snapped_coordinate, grid_resolution_m, coverage_score, confidence_tag, s_top_candidate (including manual_wins flag), elapsed_ms (= 2 000 ms). The overlay_enabled flag MUST NOT affect coverage_score.
        - ComparisonPanel dataclass with model_score: float, manual_score: float, manual_wins: bool.
  - [ ] 22.2 Write unit tests in 	ests/test_drag_drop.py:
        - Coordinate within extent returns DragDropResult.
        - DragDropResult.snapped_coordinate equals the centroid of the nearest grid cell.
        - DragDropResult.grid_resolution_m is a positive integer.
        - Coordinate outside extent returns OutsideExtentError.
        - OutsideExtentError includes the region extent in the payload.
        - drag_drop_lookup(..., overlay_enabled=True).coverage_score == drag_drop_lookup(..., overlay_enabled=False).coverage_score for the same coordinate.
        - When manual_score > model_score, s_top_candidate.manual_wins == True.
        - When manual_score <= model_score, s_top_candidate.manual_wins == False.
  - [ ]* 22.3 Property test — Drag-and-Drop Boundary and Snap Contracts (Property 13):
        `python
        # Feature: geosignal-ai, Property 13: Drag-and-Drop Boundary and Snap Contracts
        @settings(max_examples=100)
        @given(
            coord=coordinate_strategy(),
            grid=whatif_grid_strategy(),
        )
        def test_dragdrop_boundary_and_snap(coord, grid):
            result = drag_drop_lookup(coord[0], coord[1], "ntt", grid)
            if not grid.contains(coord):
                assert isinstance(result, OutsideExtentError)
            else:
                assert isinstance(result, DragDropResult)
                nearest = grid.nearest_centroid(coord)
                assert result.snapped_coordinate == nearest
                assert isinstance(result.grid_resolution_m, int)
                assert result.grid_resolution_m > 0
        `
        **Validates: Requirements 6.6, 6.7**
  - [ ]* 22.4 Property test — Power Overlay Non-Interference (Property 14):
        `python
        # Feature: geosignal-ai, Property 14: Power Overlay Non-Interference
        @settings(max_examples=100)
        @given(
            coord=coordinate_within_extent_strategy(),
            grid=whatif_grid_strategy(),
        )
        def test_power_overlay_non_interference(coord, grid):
            result_on = drag_drop_lookup(coord[0], coord[1], "ntt", grid, overlay_enabled=True)
            result_off = drag_drop_lookup(coord[0], coord[1], "ntt", grid, overlay_enabled=False)
            if isinstance(result_on, DragDropResult) and isinstance(result_off, DragDropResult):
                assert result_on.coverage_score == result_off.coverage_score
        `
        **Validates: Requirements 6.5**
  - [ ]* 22.5 Property test — Manual Placement Comparison Correctness (Property 24):
        `python
        # Feature: geosignal-ai, Property 24: Manual Placement Comparison Correctness
        @settings(max_examples=100)
        @given(
            manual_score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
            model_score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
        )
        def test_manual_placement_comparison(manual_score, model_score):
            result = make_drag_drop_result(coverage_score=manual_score, model_top_score=model_score)
            if manual_score > model_score:
                assert result.vs_top_candidate.manual_wins is True
            else:
                assert result.vs_top_candidate.manual_wins is False
        `
        **Validates: Requirements 6.3, 6.4**

  _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

## Task 23: Simulation Engine Checkpoint

- [ ] 23. Simulation Engine Checkpoint — simulate_bts_placement returns a SimulationResult (not UnavailableScenario) for all precomputed NTT Province candidates. drag_drop_lookup returns DragDropResult for coordinates within the NTT Province extent, and OutsideExtentError for coordinates outside. Power overlay does not change Coverage Score. manual_wins flag is correct in all comparison panels. All property tests P12, P13, P14, P23, P24 pass.

  _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

## Task 24: Interactive Map — Heatmap and Colour Tier

- [ ] 24. Interactive Map — Heatmap and Colour Tier
  - [ ] 24.1 Implement rontend/lib/colourTier.ts:
        - colourTier(score: number): "Green" | "Yellow" | "Red" — returns "Green" if score >= 70, "Yellow" if 40 <= score < 70, "Red" if score < 40. No other cases.
  - [ ] 24.2 Implement the Coverage Gap Heatmap MapLibre layer in rontend/components/CoverageHeatmap.tsx:
        - Renders as a raster tile layer fetched from Supabase Storage.
        - Uses colourTier to apply the three-tier colour scheme from the tile data.
        - Layer visibility toggles within 2 seconds without page reload (client-side toggle on pre-fetched tile data).
        - Confidence overlay is a separate visual indicator (hatching or opacity or border) on a separate MapLibre layer — must not use the same colour channel as the heatmap.
  - [ ] 24.3 Write unit tests in 	ests/test_colour_tier.ts:
        - colourTier(70) ? "Green".
        - colourTier(69.99) ? "Yellow".
        - colourTier(40) ? "Yellow".
        - colourTier(39.99) ? "Red".
        - colourTier(0) ? "Red".
        - colourTier(100) ? "Green".
        - colourTier(40.01) ? "Yellow".
  - [ ]* 24.4 Property test — Colour Tier Correctness (Property 11):
        `python
        # Feature: geosignal-ai, Property 11: Colour Tier Correctness
        @settings(max_examples=100)
        @given(score=st.floats(min_value=0.0, max_value=100.0, allow_nan=False))
        def test_colour_tier_correctness(score):
            tier = colour_tier(score)
            if score >= 70:
                assert tier == "Green"
            elif 40 <= score < 70:
                assert tier == "Yellow"
            else:
                assert tier == "Red"
        `
        **Validates: Requirements 3.1**

  _Requirements: 3.1, 3.2, 3.5, 7.3_

## Task 25: Interactive Map — Layer Stack, Side Panel, and Region Selector

- [ ] 25. Interactive Map — Layer Stack, Side Panel, and Region Selector
  - [ ] 25.1 Implement the full layer stack in rontend/components/MapView.tsx — render all 8 layers simultaneously using MapLibre GL JS:
        1. Base terrain tiles
        2. ESA WorldCover land-cover overlay
        3. Terrain contours from SRTM DEM
        4. Village boundaries polygon layer
        5. Coverage Gap Heatmap (from Task 24)
        6. Confidence overlay (hatching/opacity/border — independent channel from heatmap colour)
        7. Existing BTS markers (OpenCellID point layer)
        8. BTS candidate markers (ranked, draggable)
        Layer toggles must update display within 2 seconds without page reload.
  - [ ] 25.2 Implement the side panel in rontend/components/SidePanel.tsx — displays on cell or candidate click:
        - Coverage Score (0–100)
        - Confidence Tag (Low / Med / High)
        - Model version identifier
        - Scoring run timestamp
        - Rank (for candidates only)
        - SHAP Top 3: feature name, direction arrow, plain-language label
        - "GeoAI-assisted estimate" label (always visible, per Requirement 9.3)
        SHAP panel must be co-located with the Coverage Score panel (no separate navigation).
  - [ ] 25.3 Implement region selector in rontend/components/RegionSelector.tsx — dropdown with three options: NTT Province, NTB Province, Central Kalimantan Province. Switching region triggers new grid_cells query and heatmap re-render. Switching region RESETS the target-area selection (clears any drawn polygon or selected kecamatan). No page reload on switch.
  - [ ] 25.4 Implement WebGL fallback in rontend/components/MapFallback.tsx — if WebGL is unsupported, renders a static error page with browser requirements and alternative browser suggestions (Chrome, Firefox, Edge current versions). Does NOT attempt non-WebGL rendering.
  - [ ] 25.5 Write unit/component tests in 	ests/test_map_components.tsx:
        - Side panel renders Coverage Score, Confidence Tag, model version, scoring run timestamp, and SHAP Top 3 from a mock BTSCandidate.
        - Side panel shows "GeoAI-assisted estimate" label.
        - SHAP panel is in the same component as Coverage Score (not a separate route).
        - Region switch triggers a new grid_cells query with the new egion_id.
        - Region switch resets target-area selection (target_area state is null after switch).
        - WebGL fallback renders when WebGL is unavailable.

  _Requirements: 3.3, 3.4, 3.5, 7.3, 7.4, 8.2, 8.4, 9.3, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 11.3_

## Task 26: Interactive Map — Simulation Controls, Target-Area Selector, and Low-Confidence Gate

- [ ] 26. Interactive Map — Simulation Controls, Target-Area Selector, and Low-Confidence Gate
  - [ ] 26.1 Implement simulation controls in rontend/components/SimulationControls.tsx:
        - "Simulate New BTS" button — calls /api/simulate for the selected candidate; updates heatmap within 3 seconds.
        - Drag-and-Drop — makes BTS candidate markers draggable; on drop, calls /api/dragdrop; updates side panel within 2 seconds. Shows terrain-deformed coverage ring from precomputed grid. Displays grid_resolution_m in the panel ("results shown for nearest ~{N}m grid cell").
        - Shows side-by-side comparison panel (manual vs. model top candidate); includes manual_wins indication when applicable. NEVER suppresses a case where manual > model.
  - [ ] 26.2 Implement target-area selector in rontend/components/TargetAreaSelector.tsx:
        - Draw mode: MapLibre GL Draw polygon tool; on completion, posts polygon GeoJSON to /api/target-area. Renders highlighted boundary on map before user submits recommendation.
        - Kecamatan mode: dropdown scoped to current region's kecamatan list from GADM Level 2; on selection, calls /api/target-area. Renders highlighted boundary before submission.
        - Submission of a recommendation or simulation is blocked client-side until a TargetArea has been resolved (UI enforces this).
        - Switching region resets target-area selection to null.
  - [ ] 26.3 Implement the low-confidence acknowledgement gate in rontend/components/LowConfidenceModal.tsx:
        - Modal appears when a Planner attempts to act on a Low-confidence recommendation.
        - Modal must be explicitly dismissed before the action proceeds.
        - Gate is non-bypassable — if a programmatic bypass is attempted, log a security warning and re-display the gate on the next interaction.
  - [ ] 26.4 Write unit/component tests in 	ests/test_simulation_controls.tsx:
        - "Simulate New BTS" calls /api/simulate with the correct candidate_id and egion_id.
        - Drag-and-drop drop event calls /api/dragdrop with snapped coordinate.
        - Side panel shows grid_resolution_m after drag-and-drop.
        - manual_wins=True panel clearly indicates manual placement wins (not suppressed).
        - Recommendation request is blocked if no TargetArea is resolved.
        - Target-area selection resets on region switch.
        - Low-confidence modal appears for a Low-confidence candidate.
        - Low-confidence modal cannot be bypassed — mock a programmatic bypass and verify the gate re-appears.
        - Kecamatan dropdown for region_id="ntt" contains only NTT Province kecamatan names.

  _Requirements: 5.1, 5.2, 5.5, 6.1, 6.2, 6.3, 6.4, 7.4, 9.5, 10.7, 10.8_

## Task 27: Next.js API Routes

- [ ] 27. Next.js API Routes
  - [ ] 27.1 Implement rontend/pages/api/score.ts — GET /api/score?region_id=&cell_id= — queries grid_cells and returns Coverage Score, Confidence Tag, SHAP top 3, model version, scoring run timestamp.
  - [ ] 27.2 Implement rontend/pages/api/candidates.ts — POST /api/candidates — accepts { region_id, target_area_id }; calls the Python ank_bts_candidates via subprocess or HTTP bridge; returns ranked BTSCandidate list or InsufficientCandidatesResult. Blocked if 	arget_area_id is null.
  - [ ] 27.3 Implement rontend/pages/api/simulate.ts — POST /api/simulate — accepts { candidate_id, region_id }; calls simulate_bts_placement; returns SimulationResult or UnavailableScenario. SLA: = 3 000 ms.
  - [ ] 27.4 Implement rontend/pages/api/dragdrop.ts — POST /api/dragdrop — accepts { lat, lon, region_id, overlay_enabled }; calls drag_drop_lookup; returns DragDropResult or OutsideExtentError. SLA: = 2 000 ms.
  - [ ] 27.5 Implement rontend/pages/api/target-area.ts — POST /api/target-area — accepts { region_id, selection_method, payload }; calls esolve_target_area; returns the resolved TargetArea or ValidationError. SLA: = 1 000 ms.
  - [ ] 27.6 Write API route tests in 	ests/test_api_routes.ts:
        - /api/score returns 200 with Coverage Score for a known cell.
        - /api/candidates returns 400 if 	arget_area_id is null/missing.
        - /api/simulate returns UnavailableScenario for an unknown candidate.
        - /api/dragdrop returns OutsideExtentError for out-of-bounds coordinate.
        - /api/target-area with a self-intersecting drawn polygon returns ValidationError.
        - /api/target-area with a valid kecamatan_id returns a TargetArea with correct boundary.

  _Requirements: 3.4, 4.1, 5.1, 5.5, 6.2, 6.6, 10.7, 10.8, 11.3_

## Task 28: Interactive Map and API Checkpoint

- [ ] 28. Interactive Map and API Checkpoint — all 8 map layers render simultaneously in NTT Province region. Layer toggles update within 2 seconds. Side panel shows Coverage Score, Confidence Tag, SHAP Top 3, model version, scoring run timestamp, and "GeoAI-assisted estimate" label on cell/candidate click. Region selector switches among NTT Province / NTB Province / Central Kalimantan Province without reload. Target-area selector works in both draw-polygon and kecamatan-dropdown modes. Low-confidence gate is non-bypassable. All API routes respond within SLA. Colour tier property test P11 passes.

  _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 7.3, 7.4, 8.2, 8.4, 9.3, 9.5, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 11.3_

## Task 29: Offline Data Load — All Three Regions

- [ ] 29. Offline Data Load — All Three Regions (run before demo)
  - [ ] 29.1 Write scripts/load_region.py — CLI orchestration script that runs the full offline pipeline for a given --region argument in this order:
        1. un_pipeline(region_boundary, [100, 250], output_bucket) — QC + harmonise + write DataQualityReport
        2. uild_feature_vectors(...) — populate grid_cells feature columns
        3. Score all cells (AHPAdapter or XGBoostAdapter depending on Ookla tile availability) — populate coverage_score, confidence_tag, shap_top3, model_version, scoring_run_id in grid_cells
        4. ank_bts_candidates(...) — populate ts_candidates
        5. precompute_los.py — run LOS precomputation for all candidates in ts_candidates
        6. precompute_whatif.py — run what-if grid precomputation for all candidates
        Accepts --region argument with valid values: ntt, ntb, central_kalimantan.
  - [ ] 29.2 Run scripts/load_region.py --region ntt and verify:
        - grid_cells has non-null coverage_score for all NTT Province cells.
        - ts_candidates has >= 2 ranked candidates for NTT Province.
        - los_results has an entry for every NTT Province candidate.
        - whatif_grid has entries for every NTT Province candidate.
        - DataQualityReport JSON is present in output_bucket.
        - scoring_runs has at least one complete NTT Province entry.
  - [ ] 29.3 Run scripts/load_region.py --region ntb and apply the same verification checks as 29.2 for NTB Province.
  - [ ] 29.4 Run scripts/load_region.py --region central_kalimantan and apply the same verification checks as 29.2 for Central Kalimantan Province.
  - [ ] 29.5 Document actual run times per region and per step in docs/offline_load_log.md. If any step exceeds 30 minutes, flag it and propose an optimisation.

  _Requirements: 1.6, 2.1, 4.4, 5.1, 13.1, 13.3_

## Task 30: Integration and End-to-End Tests

- [ ] 30. Integration and End-to-End Tests
  - [ ] 30.1 Write integration tests in 	ests/integration/test_pipeline_to_supabase.py:
        - Round-trip: GEE export mock ? Supabase Storage write ? un_pipeline read-back. Assert data integrity (row counts, checksums match).
        - log_scoring_run ? scoring_runs table insert ? UI retrieval via /api/score. Assert model version and timestamp are correct.
        - write_whatif_grid ? simulate_bts_placement ? SimulationResult round-trip.
  - [ ] 30.2 Write E2E tests using Playwright in 	ests/e2e/:
        - 	est_region_selector_flow.spec.ts — switch from NTT Province to NTB Province; assert new grid_cells query fires with egion_id="ntb" and heatmap re-renders.
        - 	est_target_area_kecamatan_flow.spec.ts — select a kecamatan from dropdown ? boundary highlighted ? submit recommendation ? ts_candidates displayed.
        - 	est_target_area_polygon_flow.spec.ts — draw polygon ? boundary highlighted ? submit recommendation.
        - 	est_simulation_flow.spec.ts — click a candidate ? "Simulate New BTS" ? heatmap updates ? Before/After panel shows pct_good_change.
        - 	est_dragdrop_flow.spec.ts — drag candidate marker ? drop within extent ? side panel updates with coverage_score and grid_resolution_m.
        - 	est_low_confidence_gate.spec.ts — select Low-confidence candidate ? attempt action ? modal appears ? dismiss ? action proceeds.
        - 	est_webgl_fallback.spec.ts — disable WebGL in browser ? assert fallback page renders.
        - 	est_target_area_reset_on_region_switch.spec.ts — select kecamatan in NTT Province ? switch to NTB Province ? assert target-area selection is null.
  - [ ] 30.3 Performance assertions in E2E tests (Playwright expect with timeout):
        - Layer toggle: display updates within 2 000 ms.
        - Cell click ? side panel: within 1 000 ms.
        - Simulation result: within 3 000 ms.
        - Drag-and-drop snap + panel: within 2 000 ms.
        - esolve_target_area API response: within 1 000 ms.

  _Requirements: 3.2, 5.5, 6.2, 10.3, 10.5, 10.6, 10.7, 10.8_

## Task 31: Spatial CV Acceptance Gates

- [ ] 31. Spatial CV Acceptance Gates
  - [ ] 31.1 Run spatial_cv for NTT Province and verify all four acceptance gates from the Testing Strategy:
        1. Spatial CV across all available NTT Province kecamatans completes without data leakage (P7 passes).
        2. CVResult.per_kecamatan_metrics contains entries for all NTT Province kecamatans (P18 passes).
        3. At least one elevation-driven kecamatan (NTT terrain) shows generalisation to unseen terrain (RMSE on held-out fold not worse than 1.5× training RMSE).
        4. No kecamatan's accuracy is hidden behind a passing aggregate metric — individual per-kecamatan RMSE values are logged.
  - [ ] 31.2 Run spatial_cv for Central Kalimantan Province and verify:
        1. At least one canopy-driven kecamatan shows generalisation to unseen terrain.
        2. All four acceptance gates pass for Central Kalimantan Province.
  - [ ] 31.3 Document CV results (per-kecamatan RMSE, R²) in docs/spatial_cv_results.md. Flag any kecamatan with unusually high RMSE for review.

  _Requirements: 2.4, 9.4, 13.5_

## Task 32: Pre-Demo Ethical Safeguard Checklist

- [ ] 32. Pre-Demo Ethical Safeguard Checklist — complete all items from the design doc's Ethical Safeguard Verification Checklist before any public demo or stakeholder presentation:
  - [ ] 32.1 Ethical Risk Register contains all 5 required entries (P19 confirmed passing).
  - [ ] 32.2 All UI outputs carry "GeoAI-assisted estimate" label (Requirement 9.3 — verified via E2E test in Task 30).
  - [ ] 32.3 Low-confidence acknowledgement gate is non-bypassable (Requirement 9.5 — verified via E2E test 	est_low_confidence_gate.spec.ts).
  - [ ] 32.4 Deforestation constraint (land-cover AND canopy-height jointly) is active by default (P9 confirmed passing).
  - [ ] 32.5 SHAP explanations display for both Tier 1 and Tier 2 outputs, with the AHP baseline documented per run (P10 confirmed passing).
  - [ ] 32.6 Confidence thresholds are stored in DataQualityReport (not hard-coded), and exactly one ConfidenceThresholds definition exists in the codebase (Requirement 7.1 — grep-verified in unit test from Task 2).
  - [ ] 32.7 No Supabase table or field stores PII (P26 confirmed passing — 	est_privacy.py passed in Task 18).
  - [ ] 32.8 Target-area selection (draw or kecamatan) is required and confirmed before any recommendation or simulation request (P25 confirmed passing).
  - [ ] 32.9 Log the checklist completion date and reviewer name in docs/ethical_safeguard_log.md.

  _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 7.1, 12.1, 10.7, 10.8_

## Task 33: Final Checkpoint

- [ ] 33. Final Checkpoint — system is demo-ready. All of the following are verified:
  - All 26 property tests pass (P1–P26).
  - All unit tests pass.
  - All E2E tests pass (Playwright, all flows).
  - All API route SLAs met (layer toggle = 2 s, simulation = 3 s, drag-drop = 2 s, target-area = 1 s).
  - grid_cells, ts_candidates, los_results, whatif_grid are populated for all three regions (NTT Province, NTB Province, Central Kalimantan Province) — produced by Task 29, not by this task.
  - scoring_runs audit log has at least one complete entry per region.
  - ethical_risk_register has all 5 required entries.
  - DataQualityReport JSON is present for all three regions in Supabase Storage.
  - Spatial CV acceptance gates pass for NTT Province (elevation-driven) and Central Kalimantan Province (canopy-driven).
  - Ethical safeguard checklist from Task 32 is fully signed off.
  - Docker image builds cleanly: docker build -f infra/docker/Dockerfile.pipeline .
  - Next.js frontend builds cleanly: 
pm run build in rontend/.

  _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 11.1, 11.2, 11.3, 11.4, 11.5, 12.1, 12.2, 12.3, 12.4, 13.1, 13.2, 13.3, 13.4, 13.5_
