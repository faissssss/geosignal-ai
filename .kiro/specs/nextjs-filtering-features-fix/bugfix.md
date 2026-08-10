# Bugfix Requirements Document

## Introduction

The GeoSignal AI Next.js application currently experiences a critical runtime error that prevents map filtering features from functioning. The error "Cannot read properties of undefined (reading 'M_ID')" occurs during map initialization or when interacting with filtering controls, breaking the user interface and preventing essential geospatial analysis workflows. This bugfix addresses both the underlying data property mismatch and the broken UI components that depend on correctly loaded boundary data.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the application loads or WHEN a user interacts with region/filtering controls THEN the system throws "TypeError: Cannot read properties of undefined (reading 'M_ID')" in the browser console

1.2 WHEN the M_ID property error occurs THEN the following filtering UI components fail to render or respond:
- Region selection dropdown (NTT Province MVP selector)
- Land Cover checkbox toggle
- Heatmap display layer
- Target Area selection controls (Draw Polygon / Kecamatan dropdown buttons)
- BTS Towers display markers
- Candidates display markers
- Contours display layer
- Villages display layer

1.3 WHEN GADM administrative boundary data is accessed THEN the system attempts to read a property named 'M_ID' that does not exist in the GADM GeoJSON feature properties (actual properties are GID_2, GID_0, NAME_1, NAME_2, etc.)

1.4 WHEN the ESA WorldCover tile service is requested THEN the browser receives ERR_HTTP2_PROTOCOL_ERROR from services.terrascope.be/wmts/v2 endpoints, preventing land cover visualization

1.5 WHEN filtering controls are rendered THEN they appear in the DOM but do not respond to user interactions due to the upstream M_ID error breaking component initialization

### Expected Behavior (Correct)

2.1 WHEN the application loads THEN the system SHALL initialize map layers and filtering controls without throwing property access errors, using the correct GADM GeoJSON property names (GID_2, NAME_2, COUNTRY, GID_1, NAME_1, TYPE_2, HASC_2)

2.2 WHEN administrative boundary data (kecamatan boundaries from GADM Level 2) is accessed for the Target Area Selector THEN the system SHALL correctly map GADM properties to AdminBoundary interface fields:
- boundary_id ← GID_2
- kecamatan_id ← GID_2 or HASC_2  
- kecamatan_name ← NAME_2
- region_id ← derived from GID_1 or NAME_1
- boundary_geojson ← geometry object

2.3 WHEN all map layers and data sources initialize successfully THEN the Region selector dropdown SHALL be interactive and allow switching between NTT Province, NTB Province, and Central Kalimantan Province regions

2.4 WHEN a user toggles layer visibility controls (Land Cover, Heatmap, BTS Towers, Candidates, Contours, Villages checkboxes) THEN the corresponding map layers SHALL show or hide within 2 seconds without page reload

2.5 WHEN Target Area selection controls render THEN the Draw Polygon button and Kecamatan dropdown SHALL be clickable and functional, allowing the user to define analysis boundaries

2.6 WHEN the ESA WorldCover tile service is unavailable or returns protocol errors THEN the system SHALL gracefully degrade the Land Cover layer display with a user-visible warning, without blocking other map functionality

2.7 WHEN all components initialize without errors THEN BTS tower markers, candidate site markers, terrain contours, and village boundaries SHALL render on the map according to their layer visibility settings

2.8 WHEN the user opens the browser console during normal operation THEN no TypeErrors related to undefined property access SHALL be present

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the application has been fixed and initialized successfully THEN the existing Coverage Gap Heatmap rendering (Requirements 3.1-3.5 from design.md) SHALL CONTINUE TO function with green/yellow/red color thresholds

3.2 WHEN BTS candidates are displayed after the fix THEN the existing click-to-select interaction that opens the SidePanel with Coverage Score, Confidence Tag, and SHAP explanations (Requirement 10.4) SHALL CONTINUE TO work

3.3 WHEN the RegionSelector component successfully loads region data THEN the existing AbortController race-condition handling and stale-request prevention logic SHALL CONTINUE TO function

3.4 WHEN the TargetAreaSelector is used after the fix THEN the existing two-mode workflow (drawn_polygon vs kecamatan) and boundary highlighting behavior (Requirements 10.7, 10.8) SHALL CONTINUE TO operate

3.5 WHEN grid cell data and BTS candidate data are fetched THEN the existing API routes (`/api/grid-cells`, `/api/recommendations`, `/api/target-area`) SHALL CONTINUE TO return correctly formatted responses matching the GridCell, BTSCandidate, and TargetArea TypeScript interfaces

3.6 WHEN WebGL is unavailable THEN the existing WebGLFallback component SHALL CONTINUE TO display with browser recommendations

3.7 WHEN the GeoAI watermark is rendered THEN the "GeoAI-assisted estimate — decision support only" label SHALL CONTINUE TO display at the bottom center of the map (Requirement 9.3)
