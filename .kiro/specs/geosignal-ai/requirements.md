# Requirements Document

## Introduction

GeoSignal AI is a GeoAI-assisted decision-support system that helps telecom planners detect
coverage gaps and recommend optimal BTS (Base Transceiver Station) placement sites in
Indonesia's 3T (underserved) regions. The system fuses multi-source geospatial datasets —
including elevation, land cover, canopy height, population density, and crowd-sourced signal
quality data — to answer the core planning question: *"Can people in this location actually
receive a usable signal?"*

The MVP targets **NTT (Kabupaten Kupang)** as the primary live demo region, with
**NTB/Bima** and **Lamandau, Central Kalimantan** used as secondary generalization
validation. Every recommendation is framed explicitly as decision-support for a human planner,
backed by SHAP explainability and a Low/Med/High confidence tag system.

---

## Glossary

- **BTS (Base Transceiver Station)**: A fixed radio infrastructure node that provides wireless
  connectivity to a defined geographic area.
- **3T Regions**: Terdepan, Terluar, Tertinggal — Indonesia's officially designated frontier,
  outer-island, and underdeveloped regions.
- **Blank-spot**: A village or location with no functional cellular connectivity.
- **Coverage Score**: A 0–100 composite score estimating the quality of cellular coverage at
  a given grid cell, computed from the Consolidated Feature Set.
- **Confidence Tag**: A Low/Med/High label assigned to each Coverage Score and BTS
  recommendation, based on proximity to the nearest OpenCellID tower record and nearest
  Ookla tile, using the distance thresholds defined in Requirement 7.1 (High: within 2 km
  of both; Med: within 2 km of one or 2–10 km of both; Low: beyond 10 km of both).
- **Coverage Gap Heatmap**: A spatial raster layer that visualises Coverage Score values
  across the map using a three-tier colour scheme (Green = Good, Yellow = Moderate,
  Red = Poor).
- **AHP (Analytic Hierarchy Process)**: A weighted multi-criteria scoring method used as the
  Tier 1 cold-start model for regions with zero Ookla ground-truth data.
- **XGBoost/LightGBM**: Gradient-boosted tree models used as the Tier 2 trained model,
  fitted against Ookla Open Data signal quality labels.
- **BallTree**: A spatial indexing structure (scikit-learn) used to efficiently rank BTS
  candidate coordinates within large point clouds.
- **SHAP**: SHapley Additive exPlanations — a model-interpretability method that attributes
  each feature's contribution to an individual prediction.
- **DEM (Digital Elevation Model)**: A raster representation of terrain surface elevation,
  sourced from SRTM at 30 m resolution.
- **Line-of-Sight (LOS)**: A precomputed DEM-based assessment of whether a direct
  propagation path exists between a candidate BTS site and surrounding grid cells.
- **GEE (Google Earth Engine)**: A cloud-based geospatial platform used for multi-source
  data fusion, harmonisation, and export.
- **Kecamatan**: An Indonesian administrative sub-district; the unit of spatial blocking used
  in cross-validation.
- **MAUP (Modifiable Areal Unit Problem)**: Statistical distortion that can arise when
  multi-resolution raster layers are combined at a single grid resolution.
- **OpenCellID**: An open crowd-sourced database of cell tower locations.
- **Ookla Open Data**: Publicly available network speed/quality tiles from Speedtest by Ookla.
- **SRTM DEM**: Shuttle Radar Topography Mission Digital Elevation Model; 30 m resolution.
- **ESA WorldCover**: European Space Agency 10 m global land-cover classification map.
- **WorldPop**: Open population density raster dataset at 100 m resolution.
- **OSM**: OpenStreetMap — open vector data used for road network and POI layers.
- **BAKTI Komdigi**: Indonesia's Ministry of Communication and Digital agency responsible
  for 3T connectivity programs.
- **Planner**: A human telecom or government analyst who uses GeoSignal AI to make or
  inform BTS deployment decisions.
- **Recommendation_Engine**: The combined pipeline (AHP + XGBoost + BallTree + LOS)
  that produces ranked BTS candidate sites and Coverage Scores.
- **Data_Pipeline**: The GEE-based fusion and harmonisation step (Step 0) that ingests,
  validates, and exports all geospatial inputs.
- **Simulation_Engine**: The component that reads from precomputed what-if grids to power
  Before/After and Drag-and-Drop simulation features.
- **Interactive_Map**: The Next.js/MapLibre frontend component that renders all spatial
  layers and enables planner interaction.
- **Confidence_Tagger**: The subsystem that computes and attaches Low/Med/High tags to
  every Coverage Score cell and BTS recommendation.

---

## Requirements

### Requirement 1: Geospatial Data Ingestion and Quality Assurance

**User Story:** As a telecom planner, I want all input datasets to be validated and
harmonised before analysis, so that Coverage Scores and recommendations are not corrupted
by noisy or misaligned source data.

#### Acceptance Criteria

1. THE Data_Pipeline SHALL ingest the following data sources: SRTM DEM (30 m elevation
   and slope), ESA WorldCover (10 m land-cover classification), OpenGeoAI canopy height
   (30 m), OpenCellID BTS locations, OSM road network and POI data, WorldPop population
   density (100 m), and Ookla Open Data signal quality tiles.
2. WHEN a data source contains geometrically invalid features (e.g., self-intersecting
   polygons, null geometries), THE Data_Pipeline SHALL remove or repair those features and
   log each corrected record before proceeding to fusion.
3. WHEN attribute values for any feature fall outside the physically plausible range for that
   field (e.g., negative elevation in non-coastal areas, population density above 1,000,000
   per km²), THE Data_Pipeline SHALL flag those records as anomalous and exclude them from
   scoring inputs.
4. THE Data_Pipeline SHALL harmonise all raster layers to a consistent analysis grid
   resolution, and THE Data_Pipeline SHALL produce Coverage Score outputs at a minimum of
   two distinct grid resolutions to enable MAUP sensitivity testing before a final resolution
   is selected.
5. WHEN harmonisation is complete, THE Data_Pipeline SHALL export a data quality report
   that records the input record count, the number of records removed or repaired, and the
   chosen analysis grid resolution, so that a Planner can review data provenance.
6. THE Data_Pipeline SHALL process the MVP demo region (Kabupaten Kupang, NTT) as the
   primary dataset, with NTB/Bima and Lamandau (Central Kalimantan) available as secondary
   validation datasets using the same pipeline configuration.

---

### Requirement 2: Two-Tier Coverage Scoring Model

**User Story:** As a telecom planner, I want a reliable Coverage Score for every grid cell
in the target region, so that I can identify where signal quality is poor even when no
direct measurement data exists.

#### Acceptance Criteria

1. THE Recommendation_Engine SHALL compute a Coverage Score between 0 and 100 for each
   grid cell using the eight geospatial input features from the Consolidated Feature Set:
   elevation, slope, land-cover class, canopy height, distance-to-BTS, road distance,
   population density, and public facility proximity. Ookla signal quality SHALL NOT be
   used as a Coverage Score input feature; it SHALL be used only as the Tier 2 training
   label (Requirement 2.3) and as a Confidence_Tagger input (Requirement 7), to avoid
   leaking the training target into the score itself.
2. WHEN no Ookla ground-truth tiles are available within a target sub-district (kecamatan),
   THE Recommendation_Engine SHALL compute the Coverage Score using the Tier 1 AHP model
   with weighted geospatial drivers derived from the Consolidated Feature Set.
3. WHEN Ookla ground-truth tiles are available for a target kecamatan, THE
   Recommendation_Engine SHALL compute the Coverage Score using the Tier 2 XGBoost or
   LightGBM model trained on those Ookla labels.
4. THE Recommendation_Engine SHALL validate Tier 2 model performance using
   spatially-blocked cross-validation, where entire kecamatan units are held out as test
   blocks, so that reported accuracy reflects generalisation to unseen terrain rather than
   spatial autocorrelation leakage from a random point split.
5. IF an OpenCellID record is absent for a grid cell, THEN THE Recommendation_Engine SHALL
   treat that cell as having unknown signal status rather than confirmed zero coverage, and
   THE Confidence_Tagger SHALL assign a Low confidence tag to that cell.
6. THE Recommendation_Engine SHALL use land-cover class and canopy height as distinct
   separate input features and SHALL NOT conflate them into a single "dense vegetation"
   parameter, in accordance with the Consolidated Feature Set.
7. THE Recommendation_Engine SHALL NOT use administrative boundary identifiers (village or
   regency labels) as scoring inputs; administrative labels are display-only fields.

---

### Requirement 3: Coverage Gap Heatmap Visualisation

**User Story:** As a telecom planner, I want to see a dynamic heatmap that shows coverage
quality across the terrain, so that I can quickly identify where the worst gaps are.

#### Acceptance Criteria

1. THE Interactive_Map SHALL render a Coverage Gap Heatmap layer over the target region
   using a three-tier colour scheme: green for Coverage Score ≥ 70 (Good), yellow for
   Coverage Score 40–69 (Moderate), and red for Coverage Score < 40 (Poor).
2. WHEN a Planner toggles the heatmap layer on or off, THE Interactive_Map SHALL update
   the heatmap display within 2 seconds without reloading the page.
3. THE Interactive_Map SHALL overlay BTS locations, village boundaries, terrain contours,
   and the Coverage Gap Heatmap simultaneously in a single unified view.
4. WHEN a Planner clicks on any heatmap cell, THE Interactive_Map SHALL display the
   Coverage Score (0–100), the Confidence Tag (Low/Med/High), and the top three SHAP
   feature contributions for that cell.
5. THE Interactive_Map SHALL visually distinguish Low, Med, and High Confidence Tag cells
   through a secondary visual indicator (e.g., hatching, opacity, or border pattern)
   independent of the heatmap colour, so that confidence is not conflated with score.

---

### Requirement 4: BTS Placement Recommendation Engine

**User Story:** As a telecom planner, I want the system to automatically recommend the
highest-impact candidate BTS sites, so that I can evaluate data-driven placement options
alongside my own expertise.

#### Acceptance Criteria

1. WHEN a Planner requests BTS placement recommendations for a target area, THE
   Recommendation_Engine SHALL return a ranked list of candidate BTS coordinates, with
   each candidate scored using the full Consolidated Feature Set via BallTree-indexed
   candidate search.
2. THE Recommendation_Engine SHALL rank candidates by the expected Coverage Score
   improvement across the surrounding grid cells if a BTS were placed at that coordinate.
3. THE Recommendation_Engine SHALL apply a land-cover and canopy-height constraint that
   excludes candidate sites classified as high-canopy forest by default, to reduce the
   risk of recommending sites that would require significant deforestation.
4. WHEN a candidate BTS site is generated, THE Recommendation_Engine SHALL run a
   precomputed DEM-based line-of-sight validation for that site and include the LOS result
   in the candidate's metadata.
5. THE Confidence_Tagger SHALL assign a Low, Med, or High confidence tag to each
   recommended candidate based on proximity to the nearest OpenCellID tower record and
   the nearest Ookla tile, following the same tagging rules applied to Coverage Score cells.
6. THE Recommendation_Engine SHALL provide SHAP feature importance values for each
   recommended candidate, identifying the top contributing factors in plain language
   accessible to a non-technical Planner.
7. THE Recommendation_Engine SHALL return at least two distinct ranked candidates per
   target area so that a Planner can compare options.

---

### Requirement 5: Before/After Coverage Simulation

**User Story:** As a telecom planner, I want to see how a proposed BTS placement would
change the coverage heatmap before any infrastructure decision is made, so that I can
evaluate impact without committing to a site.

#### Acceptance Criteria

1. WHEN a Planner selects a recommended candidate and clicks "Simulate New BTS", THE
   Simulation_Engine SHALL update the Coverage Gap Heatmap to reflect the projected
   coverage improvement, reading from a precomputed what-if grid rather than performing
   live DEM recomputation.
2. THE Simulation_Engine SHALL display a side-by-side or overlay comparison of the
   before-simulation and after-simulation heatmap states.
3. THE Simulation_Engine SHALL show quantified metric improvements alongside the updated
   heatmap, including the percentage change in grid cells classified as Good (≥ 70), the
   change in the number of villages within improved coverage area, and the updated
   Coverage Score for the simulated BTS location.
4. IF a requested simulation scenario has not been precomputed, THEN THE Simulation_Engine
   SHALL inform the Planner that the scenario is unavailable rather than returning a
   computed estimate of unknown accuracy.
5. THE Simulation_Engine SHALL complete the heatmap update and display metric improvements
   within 3 seconds of the Planner's simulation request under normal browser conditions.

---

### Requirement 6: Drag-and-Drop Manual Placement Simulation

**User Story:** As a telecom planner, I want to drag a candidate BTS marker to any
location on the map and immediately see the projected coverage impact, so that I can
explore placements beyond the system's automatic suggestions.

#### Acceptance Criteria

1. WHEN a Planner drags a candidate BTS marker to a new coordinate on the Interactive_Map,
   THE Simulation_Engine SHALL display a terrain-deformed coverage ring for that position
   derived from the precomputed what-if grid.
2. WHEN a Planner drops a marker at a new coordinate, THE Interactive_Map SHALL display
   a live Coverage Score and Confidence Tag panel for that position within 2 seconds.
3. THE Interactive_Map SHALL show a side-by-side comparison between the Planner's
   manually placed position and the Recommendation_Engine's top-ranked candidate for that
   area, including cases where the manual placement produces a higher Coverage Score than
   the model's suggestion.
4. WHEN the Planner's manually placed position produces a higher Coverage Score than the
   Recommendation_Engine's top-ranked candidate, THE Interactive_Map SHALL clearly
   indicate this outcome to the Planner rather than suppressing it.
5. WHERE the optional power and energy feasibility overlay is enabled by the Planner, THE
   Interactive_Map SHALL display a proximity indicator to the nearest power grid node or
   solar potential rating for the dropped marker position; this overlay SHALL NOT modify
   the Coverage Score computation.
6. THE Simulation_Engine SHALL serve drag-and-drop results by snapping the dropped
   coordinate to the nearest cell in the precomputed what-if grid and SHALL display the
   grid resolution (e.g., "results shown for nearest ~100m grid cell") alongside the
   Coverage Score panel, so the Planner understands the result reflects the nearest
   precomputed cell rather than the exact dropped point.
7. IF a Planner drops a marker outside the precomputed what-if grid's spatial extent for
   the active region, THEN THE Simulation_Engine SHALL inform the Planner that no
   precomputed data exists for that location rather than returning an extrapolated or
   interpolated estimate of unknown accuracy, consistent with Requirement 5.4.

---

### Requirement 7: Confidence Tagging System

**User Story:** As a telecom planner, I want every recommendation and heatmap cell to
carry an explicit confidence level, so that I can weight high-confidence outputs more
heavily in real investment decisions.

#### Acceptance Criteria

1. THE Confidence_Tagger SHALL assign a confidence tag of Low, Med, or High to every
   Coverage Score grid cell and every recommended BTS candidate based on two factors:
   proximity to the nearest OpenCellID tower record, and proximity to the nearest Ookla
   tile, using the following distance thresholds measured from the cell centroid or
   candidate coordinate:
   - **High**: within 2 km of both a nearest OpenCellID tower record AND a nearest Ookla
     tile.
   - **Med**: within 2 km of at least one of the two (OpenCellID tower record or Ookla
     tile), but not both; OR within 2–10 km of both.
   - **Low**: beyond 10 km from both an OpenCellID tower record and an Ookla tile, OR no
     record of either type exists within 10 km.

   THE Data_Pipeline's data quality report (Requirement 1.5) SHALL record these threshold
   values so they remain reviewable and adjustable per region without being hard-coded
   into application logic.
2. WHEN no OpenCellID tower record and no Ookla tile exist within the proximity threshold
   for a given cell, THE Confidence_Tagger SHALL assign a Low confidence tag to that cell
   and SHALL NOT interpret the absence of records as confirmed zero-signal coverage.
3. THE Interactive_Map SHALL visually distinguish Low, Med, and High confidence cells
   using a secondary visual indicator that is independent of the Coverage Score colour
   (green/yellow/red) heatmap.
4. WHEN a Planner views a Low-confidence recommendation, THE Interactive_Map SHALL
   display a visible disclaimer stating that the estimate is based on sparse data and
   should not be treated as authoritative signal measurement.
5. THE Confidence_Tagger SHALL apply the same proximity-based tagging rules consistently
   across Coverage Score cells, BTS recommendations, and Drag-and-Drop simulation outputs.

---

### Requirement 8: SHAP Explainability for Recommendations

**User Story:** As a government stakeholder, I want to understand why the system
recommended a particular BTS site, so that I can assess the recommendation's validity and
defend investment decisions to auditors.

#### Acceptance Criteria

1. THE Recommendation_Engine SHALL compute SHAP values for every recommended BTS
   candidate and every Coverage Score cell surfaced to a Planner.
2. WHEN a Planner views a recommendation, THE Interactive_Map SHALL display the top three
   contributing SHAP features in plain language, identifying both the feature name and
   whether it contributed positively or negatively to the Coverage Score.
3. THE Recommendation_Engine SHALL produce SHAP explanations for both Tier 1 (AHP) and
   Tier 2 (XGBoost/LightGBM) outputs, so that explainability is not limited to regions
   with Ookla ground truth.
4. THE Interactive_Map SHALL make SHAP explanations accessible from within the same panel
   that displays the Coverage Score and Confidence Tag, without requiring a Planner to
   navigate to a separate page.
5. THE Recommendation_Engine SHALL log SHAP values alongside the model version and
   scoring run identifier for every batch of recommendations, so that changes in
   recommendation rationale can be audited retrospectively.

---

### Requirement 9: Ethical Risk Controls and Responsible AI Guardrails

**User Story:** As a BAKTI Komdigi stakeholder, I want the system to apply built-in
ethical safeguards, so that recommendations do not inadvertently disadvantage vulnerable
communities or drive environmentally harmful siting decisions.

#### Acceptance Criteria

1. THE Recommendation_Engine SHALL apply an equity weighting in the AHP scoring that
   elevates the relative priority of grid cells and candidates with high public facility
   proximity and non-zero population density, so that low-population clusters with genuine
   service need are not systematically deprioritised.
2. THE Recommendation_Engine SHALL apply a land-cover and canopy-height constraint that
   excludes candidate BTS sites classified as high-canopy forest by default, reducing the
   risk that a recommendation encourages unnecessary deforestation.
3. THE Interactive_Map SHALL display all system outputs with labels and framing that
   identify the output as a "GeoAI-assisted estimate" and decision-support tool, not an
   authoritative signal measurement or an auto-executed placement.
4. THE Recommendation_Engine SHALL evaluate Coverage Score accuracy per sub-region
   (kecamatan) separately — including regions with sparse data such as dense-canopy areas
   — so that strong aggregate performance does not mask poor performance in
   under-represented areas.
5. IF a Planner attempts to act on a Low-confidence recommendation without acknowledging
   the confidence disclaimer, THEN THE Interactive_Map SHALL require explicit
   acknowledgement before proceeding, to reduce the risk of low-fidelity data driving
   real funding decisions.
6. THE Recommendation_Engine SHALL maintain an Ethical Risk Register entry for each of
   the following identified risks: digital exclusion, deforestation, OpenCellID sparsity
   misread as confirmed no coverage, low-confidence scores driving funding decisions, and
   MAUP resampling mismatch; each entry SHALL include the risk description, impact,
   mitigation, and a named responsible owner role.
7. THE Recommendation_Engine SHALL default to the Tier 1 (AHP) model rather than
   triggering Tier 2 (XGBoost/LightGBM) training or inference for any kecamatan lacking
   Ookla ground-truth tiles, so that model training and compute cost scale with actual
   data availability rather than defaulting to the heavier model everywhere; this
   satisfies the Sustainability dimension of the 7-dimension ethics self-audit alongside
   Fairness (9.4), Accountability (9.6), Transparency (Requirement 8), and Human Oversight
   (9.3, 9.5).

---

### Requirement 10: Interactive Map Interface

**User Story:** As a telecom planner, I want a single unified map interface that combines
all spatial layers and simulation controls, so that I can explore coverage data without
switching between separate tools.

#### Acceptance Criteria

1. THE Interactive_Map SHALL render in a web browser without requiring any local software
   installation beyond a modern browser, using the Next.js frontend served from Supabase.
2. THE Interactive_Map SHALL simultaneously display the following layers: existing BTS
   locations (from OpenCellID), village boundaries, terrain contours derived from SRTM
   DEM, land-cover classification from ESA WorldCover, the Coverage Gap Heatmap, and
   BTS candidate markers.
3. WHEN a Planner toggles individual map layers on or off, THE Interactive_Map SHALL
   update the display within 2 seconds.
4. WHEN a Planner clicks on a BTS candidate marker, THE Interactive_Map SHALL display
   the candidate's Coverage Score, Confidence Tag, rank among all candidates, and top
   three SHAP feature contributions in a side panel.
5. THE Interactive_Map SHALL provide region-selector controls that allow a Planner to
   switch the active analysis region between Kabupaten Kupang (MVP demo), NTB/Bima
   (validation), and Lamandau (validation) without reloading the application.
6. IF the Planner's browser cannot render the interactive map (e.g., WebGL unsupported),
   THEN THE Interactive_Map SHALL display a clear error message explaining the requirement
   and suggesting an alternative browser.
7. THE Interactive_Map SHALL allow a Planner to specify a target area for BTS placement
   recommendations (Requirement 4) and Before/After simulation (Requirement 5) by either
   drawing a bounding polygon directly on the map or selecting a kecamatan from a
   dropdown list scoped to the currently active region (Kabupaten Kupang, NTB/Bima, or
   Lamandau, per Requirement 10.5).
8. WHEN a Planner selects a target area by either method in Requirement 10.7, THE
   Interactive_Map SHALL visually highlight the selected boundary on the map before the
   Planner requests recommendations, so the Planner can confirm the intended area prior
   to submission.

---

### Requirement 11: Model Versioning and Auditability

**User Story:** As a BAKTI Komdigi accountability reviewer, I want every scoring run and
model version to be logged and reproducible, so that I can answer "why did this score
change?" months after a recommendation was produced.

#### Acceptance Criteria

1. THE Recommendation_Engine SHALL assign a unique version identifier to each trained
   model artifact (Tier 1 AHP weight configuration and Tier 2 XGBoost/LightGBM model
   file) before that model is used to produce recommendations.
2. THE Recommendation_Engine SHALL log the following metadata for every scoring run: model
   version identifier, input dataset checksums, analysis grid resolution, timestamp,
   target region (kecamatan identifiers), and the number of candidate sites evaluated.
3. WHEN a Planner views a recommendation, THE Interactive_Map SHALL display the model
   version identifier and scoring run timestamp associated with that recommendation.
4. THE Recommendation_Engine SHALL retain all scoring run logs for a minimum of 12 months
   so that historical recommendations remain auditable.
5. WHERE the Tier 2 model is retrained on updated Ookla data, THE Recommendation_Engine
   SHALL produce a new version identifier and SHALL NOT overwrite or delete the prior
   model artifact, preserving full version history.

---

### Requirement 12: Data Privacy and Aggregation Controls

**User Story:** As a system administrator, I want to ensure that no personally
identifiable information is stored or exposed, so that the system complies with data
privacy principles.

#### Acceptance Criteria

1. THE Data_Pipeline SHALL ingest only aggregated, non-PII geospatial datasets: WorldPop
   population density grids (not individual records), OpenCellID tower locations (not
   device identifiers), and Ookla signal quality tiles (not individual speed-test records).
2. THE Data_Pipeline SHALL NOT store any household-level location data, individual device
   identifiers, or personal contact information at any stage of processing.
3. THE Recommendation_Engine SHALL reference population data exclusively through the
   WorldPop density raster at 100 m resolution and SHALL NOT disaggregate or reconstruct
   individual-level records from that raster.
4. WHEN data is exported from Google Earth Engine to downstream storage, THE Data_Pipeline
   SHALL transmit only processed, anonymised raster and vector outputs and SHALL NOT
   include raw user-generated crowd-sourced records in exported payloads.

---

### Requirement 13: Phase 3 Scalability Pathway (National Scale)

**User Story:** As a BAKTI Komdigi national planning lead, I want the system architecture
to support eventual expansion to all of Indonesia's 3T regions without requiring a full
rebuild, so that the proven MVP approach can scale to national coverage.

#### Acceptance Criteria

1. THE Data_Pipeline SHALL be configurable by region parameter so that the same Step 0
   quality-check and fusion workflow executes for a new province by supplying a new
   administrative boundary file without modifying core pipeline code.
2. THE Recommendation_Engine SHALL be designed so that the BallTree candidate search and
   Coverage Score computation can be distributed across multiple compute nodes via
   Spark or Dask, enabling parallel execution across all 3T provinces simultaneously.
3. THE Data_Pipeline SHALL containerise each province's processing step using Docker so
   that the validated Step 0 quality checks run consistently across all provinces without
   manual intervention.
4. THE Recommendation_Engine SHALL support a future transition from XGBoost/LightGBM to
   Graph Neural Networks (GNN) for national-scale spatial topology modelling by exposing
   the scoring interface through an abstracted model adapter layer that does not depend on
   a specific algorithm implementation.
5. WHEN the system is deployed for a new province, THE Recommendation_Engine SHALL apply
   spatially-blocked cross-validation using that province's kecamatan boundaries before
   publishing recommendations, ensuring the same validation standard is enforced at
   national scale.