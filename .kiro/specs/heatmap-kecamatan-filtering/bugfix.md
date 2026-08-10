# Bugfix Requirements Document: Heatmap Kecamatan Filtering

## Introduction

The coverage heatmap layer does not filter when a kecamatan (district) is selected from the target area selector. Users in NTT, NTB, and Central Kalimantan expect to select any kecamatan and see only the heatmap coverage data for that specific administrative boundary. Currently, selecting different kecamatan has no effect on the displayed heatmap - all grid cells for the entire region remain visible.

Additionally, the system lacks proper data validation and completeness guarantees. **All three provinces (NTT, NTB, Central Kalimantan) and ALL kecamatan within them must have complete heatmap data coverage**, but the current implementation does not validate or ensure this requirement is met.

This breaks the core planning workflow where planners need to focus on specific districts to assess coverage gaps and recommend BTS tower placements within targeted administrative areas.

**Impact**: 
1. Planners cannot effectively analyze coverage for specific districts, making the target area selection feature incomplete
2. Missing data validation means some provinces/kecamatan may have no data to display, breaking the user experience
3. Lack of data completeness guarantees undermines the application's reliability for nationwide network planning

---

## Bug Analysis

### Current Behavior (Defect)

**1. No Spatial Filtering**

1.1 WHEN a planner selects a kecamatan from the TargetAreaSelector dropdown THEN the system continues to display all grid cells for the entire region without filtering

1.2 WHEN the target area boundary is highlighted on the map after kecamatan selection THEN the heatmap cells outside that boundary remain visible and are not filtered out

1.3 WHEN a planner switches between different kecamatan in the same region THEN the heatmap display does not change at all

**2. Missing Spatial Query Logic**

1.4 WHEN `getGridCells()` is called in `frontend/lib/server/geosignal-service.ts` THEN it only filters by `region_id` and `resolution_m` with no spatial/geometric filtering capability

1.5 WHEN TargetAreaSelector emits a target area resolved event with boundary geometry THEN MapView does not refetch grid cells or apply any spatial filtering

**3. Data Layer Disconnection**

1.6 WHEN MapView renders the CoverageHeatmap component THEN it passes all cells for the region without filtering based on the active target area

1.7 WHEN a target area is resolved with boundary geometry THEN no spatial point-in-polygon test is performed to determine which grid cells fall within the boundary

**4. Missing Data Validation**

1.8 WHEN grid cells data exists for all three provinces (NTT, NTB, Central Kalimantan) THEN the system does not validate that all provinces have heatmap data to visualize

1.9 WHEN all kecamatan in all provinces have associated grid cells THEN the system does not ensure that every kecamatan can display heatmap data when selected

1.10 WHEN a kecamatan is selected from any province THEN the system may fail to display heatmap data if data is missing, without proper validation or error messaging

---

### Expected Behavior (Correct)

**1. Spatial Filtering After Kecamatan Selection**

2.1 WHEN a planner selects a kecamatan from the dropdown THEN the system SHALL filter the heatmap to show ONLY grid cells whose coordinates fall within that kecamatan's boundary polygon

2.2 WHEN the target area boundary is highlighted on the map THEN the system SHALL display heatmap cells exclusively within the highlighted boundary area

2.3 WHEN a planner switches from one kecamatan to another THEN the system SHALL update the heatmap display to show only cells within the newly selected kecamatan's boundary

**2. Spatial Query Logic Implementation**

2.4 WHEN `getGridCells()` receives a target area with boundary geometry THEN the system SHALL perform spatial point-in-polygon filtering to return only cells within that boundary

2.5 WHEN TargetAreaSelector calls `onResolved` with a target area THEN MapView SHALL refetch grid cells with the target area filter applied

2.6 WHEN performing spatial filtering THEN the system SHALL use either PostGIS spatial queries (backend) OR Turf.js point-in-polygon checks (frontend) to determine cell inclusion

**3. Empty Results Handling**

2.7 WHEN a kecamatan is selected that has no grid cells in the database THEN the system SHALL display an informative message indicating missing data for that kecamatan

2.8 WHEN filtering results in zero cells due to missing data THEN the system SHALL still show the kecamatan boundary highlight and display a warning message

**4. Data Coverage Validation**

2.9 WHEN the application loads THEN the system SHALL validate that heatmap data exists for all three provinces (NTT, NTB, Central Kalimantan)

2.10 WHEN displaying the kecamatan dropdown for any province THEN the system SHALL ensure every kecamatan has associated grid cells available for visualization

2.11 WHEN a province has incomplete data coverage THEN the system SHALL display a warning indicator in the region selector showing which provinces lack complete data

2.12 WHEN a kecamatan is selected THEN the system SHALL verify grid cells exist for that kecamatan and display appropriate messaging if data is missing

2.13 WHEN grid cells are missing for a selected area THEN the system SHALL provide actionable guidance (e.g., "Data not yet processed for this area" or "Contact administrator")

---

### Unchanged Behavior (Regression Prevention)

**1. Region-Wide Display**

3.1 WHEN no specific target area is selected (initial load or after reset) THEN the system SHALL CONTINUE TO display all grid cells for the selected region

3.2 WHEN switching between regions (NTT, NTB, Central Kalimantan) without selecting a kecamatan THEN the system SHALL CONTINUE TO show all cells for the new region

**2. Heatmap Visualization**

3.3 WHEN heatmap cells are displayed THEN the system SHALL CONTINUE TO use the correct color coding (Green ≥70, Yellow 40-69, Red <40)

3.4 WHEN heatmap cells are displayed THEN the system SHALL CONTINUE TO apply confidence-based opacity (High 0.85, Med 0.55, Low 0.30)

3.5 WHEN a grid cell is clicked THEN the system SHALL CONTINUE TO open the side panel with cell details (coverage score, confidence, SHAP values)

**3. Layer Toggle Behavior**

3.6 WHEN the heatmap layer is toggled OFF via LayerToggleBar THEN the system SHALL CONTINUE TO hide all heatmap cells without affecting other layers

3.7 WHEN the heatmap layer is toggled ON THEN the system SHALL CONTINUE TO show the filtered or unfiltered cells based on current target area state

**4. Other Target Area Selection Methods**

3.8 WHEN a planner uses drawn_polygon mode instead of kecamatan mode THEN the system SHALL CONTINUE TO support polygon drawing and should apply the same spatial filtering logic

3.9 WHEN a target area is reset via the Reset button THEN the system SHALL CONTINUE TO clear the selection and return to showing all region cells

**5. Candidates and Other Layers**

3.10 WHEN heatmap filtering is applied THEN BTS candidate markers SHALL CONTINUE TO display independently (no filtering)

3.11 WHEN heatmap filtering is applied THEN other map layers (land cover, contours, villages) SHALL CONTINUE TO function normally

**6. Data Completeness Guarantees**

3.12 WHEN the backend pipeline processes coverage data THEN it SHALL ensure grid cells are generated for all kecamatan in all three provinces (NTT, NTB, Central Kalimantan)

3.13 WHEN new administrative boundaries are added THEN the system SHALL CONTINUE TO require corresponding grid cell data to maintain complete coverage

3.14 WHEN data generation is incomplete THEN the system SHALL CONTINUE TO log warnings and provide visibility into which areas lack data

---

## Bug Condition and Property Derivation

### Bug Condition Function

Identifies grid cells that should be hidden when a target area is active:

```pascal
FUNCTION isBugCondition(cell, targetArea)
  INPUT: cell of type GridCell
  INPUT: targetArea of type TargetArea | null
  OUTPUT: boolean
  
  // Bug occurs when a target area is selected BUT the cell is outside its boundary
  IF targetArea IS NULL THEN
    RETURN false  // No bug: no filtering expected
  END IF
  
  boundary ← targetArea.boundary_geojson
  point ← (cell.lon, cell.lat)
  
  // Bug condition: cell is NOT inside boundary but is still displayed
  RETURN NOT pointInPolygon(point, boundary)
END FUNCTION
```

### Fix Property: Correct Visibility

For all grid cells when a target area is selected, only cells within the boundary should be visible:

```pascal
// Property: Fix Checking - Spatial Filtering
FOR ALL cell IN grid_cells WHERE isBugCondition(cell, targetArea) DO
  visibleCells ← getVisibleHeatmapCells'(targetArea)
  ASSERT cell NOT IN visibleCells
END FOR

// Correct behavior: Only inside cells are visible
FOR ALL cell IN grid_cells WHERE targetArea ≠ NULL DO
  visibleCells ← getVisibleHeatmapCells'(targetArea)
  insideBoundary ← pointInPolygon((cell.lon, cell.lat), targetArea.boundary_geojson)
  ASSERT (cell IN visibleCells) = insideBoundary
END FOR
```

### Preservation Property: Region-Wide Display

When no target area is selected, all cells should remain visible:

```pascal
// Property: Preservation Checking
FOR ALL cell IN grid_cells WHERE targetArea IS NULL DO
  visibleCells ← getVisibleHeatmapCells'(NULL)
  // Original behavior: all region cells visible
  ASSERT cell IN visibleCells IF cell.region_id = activeRegion
END FOR
```

**Key Definitions:**
- **F**: Original implementation - `getGridCells()` filters by `region_id` only
- **F'**: Fixed implementation - `getGridCells()` applies spatial filtering when `target_area_id` is provided
- **Counterexample**: Select "Alor Selatan" kecamatan → All 50 NTT grid cells remain visible instead of filtering to ~5-10 cells within Alor Selatan boundary

---

## Data Context

**Existing Data (from investigation)**:
- `admin_boundaries` table has 45 kecamatan across all 3 regions (21 NTT, 10 NTB, 14 Central Kalimantan)
- `grid_cells` table has 50 cells, ALL for region 'ntt'
- NTB and Central Kalimantan have 0 grid cells (valid for testing empty results)
- Each admin boundary has valid GeoJSON polygon geometry
- Each grid cell has valid lat/lon coordinates

**Expected Test Scenarios**:
1. Select NTT kecamatan with cells inside → Show filtered subset
2. Select NTT kecamatan with NO cells inside → Show empty heatmap with warning message
3. Select NTB kecamatan → Show heatmap data (must exist per hardening requirement)
4. Select Central Kalimantan kecamatan → Show heatmap data (must exist per hardening requirement)
5. Reset to no target area → Show all cells for active region
6. Toggle heatmap OFF while filtered → Hide cells correctly
7. Toggle heatmap ON while filtered → Show only filtered cells
8. Switch between provinces → Validate data exists for each province before displaying selector
9. Load application → Display data coverage status for all provinces in UI
10. Select kecamatan with missing data → Show informative error message with actionable guidance

**Data Hardening Requirements**:
- ALL three provinces (NTT, NTB, Central Kalimantan) MUST have complete heatmap data coverage
- EVERY kecamatan within each province MUST have associated grid cells for visualization
- Missing data is a blocker for deployment - the bug fix includes ensuring data completeness
- UI MUST validate and display data coverage status before allowing province/kecamatan selection

