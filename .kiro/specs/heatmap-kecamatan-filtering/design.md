# Heatmap Kecamatan Filtering Bugfix Design

## Overview

The coverage heatmap currently displays all grid cells for the selected region, regardless of which kecamatan (district) is selected in the TargetAreaSelector. This design document specifies a spatial filtering fix that will display only grid cells falling within the selected kecamatan's boundary polygon.

**Fix Approach**: Implement client-side spatial filtering using Turf.js point-in-polygon checks. When a target area is resolved, MapView will filter the grid cells array before passing it to CoverageHeatmap. This minimizes backend changes while providing immediate filtering capability.

**Rationale**: Client-side filtering is chosen because:
- Grid cells are already loaded for the entire region (maximum ~50 cells per region based on existing data)
- Point-in-polygon checks with Turf.js are computationally inexpensive for this scale
- No backend API changes required - filtering logic lives in MapView component
- Faster iteration and testing compared to backend PostGIS queries
- Preserves existing API contracts and data flow

**Data Generation**: The fix includes a data validation and generation phase to ensure all three provinces (NTT, NTB, Central Kalimantan) have complete heatmap coverage for all kecamatan. Currently only NTT has grid cells; NTB and Central Kalimantan require data generation via the backend pipeline.

---

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when a target area (kecamatan) is selected but grid cells outside its boundary remain visible
- **Property (P)**: The desired behavior - only grid cells whose centroids fall within the selected kecamatan's boundary polygon should be displayed
- **Preservation**: Region-wide display behavior (no target area selected) must remain unchanged - all cells for the active region should be visible
- **TargetAreaSelector**: Component in `frontend/components/TargetAreaSelector.tsx` that allows planners to select a kecamatan or draw a polygon
- **MapView**: Parent component in `frontend/components/MapView.tsx` that orchestrates data fetching and passes filtered cells to CoverageHeatmap
- **CoverageHeatmap**: Rendering component in `frontend/components/CoverageHeatmap.tsx` that displays grid cells as colored polygons on the map
- **GridCell**: Data structure with `cell_id`, `lat`, `lon`, `coverage_score`, `confidence_tag`, and `region_id`
- **TargetArea**: Resolved area with `target_area_id`, `boundary_geojson` (Polygon geometry), `kecamatan_id`, and `region_id`
- **Point-in-Polygon**: Spatial operation that tests whether a point (cell centroid) falls inside a polygon boundary

---

## Bug Details

### Bug Condition

The bug manifests when a planner selects a kecamatan from the TargetAreaSelector dropdown, but the heatmap layer continues to display all grid cells for the entire region instead of filtering to only those within the selected kecamatan's boundary.

The filtering logic is missing at the data flow layer. MapView receives a resolved target area with boundary geometry from TargetAreaSelector but does not filter the grid cells array before passing it to CoverageHeatmap. The component receives all cells and renders them regardless of spatial relationship to the target area boundary.

**Formal Specification:**
```
FUNCTION isBugCondition(cell, targetArea)
  INPUT: cell of type GridCell with properties { lat, lon, region_id, ... }
  INPUT: targetArea of type TargetArea | null with properties { boundary_geojson, ... }
  OUTPUT: boolean
  
  // Bug occurs when a target area is selected AND the cell is outside its boundary
  IF targetArea IS NULL THEN
    RETURN false  // No bug: no filtering expected
  END IF
  
  boundary ← targetArea.boundary_geojson (Polygon geometry)
  point ← [cell.lon, cell.lat]  // GeoJSON uses [longitude, latitude] order
  
  // Bug condition: cell is NOT inside boundary but is still displayed
  RETURN NOT pointInPolygon(point, boundary)
END FUNCTION
```

### Examples

**Example 1: Alor Selatan (NTT) - Cells Inside**
- Input: Select kecamatan "Alor Selatan" (GID: IDN.20.1.1_1)
- Boundary: Polygon covering southern portion of Alor island
- Expected: Show ~5-10 grid cells with centroids inside boundary
- Actual (before fix): All 50 NTT grid cells remain visible

**Example 2: Kupang Tengah (NTT) - Cells Outside**
- Input: Select kecamatan "Kupang Tengah" (GID: IDN.20.10.5_1)
- Boundary: Polygon covering central Kupang mainland district
- Expected: Show only cells within Kupang Tengah boundary (~8-12 cells)
- Actual (before fix): All 50 NTT grid cells remain visible, including cells in Alor, Flores, and other islands

**Example 3: Sumbawa Besar (NTB) - Empty Results**
- Input: Select kecamatan "Sumbawa Besar" from NTB dropdown
- Boundary: Polygon for Sumbawa Besar district
- Expected: Show heatmap cells within boundary + warning message if no cells exist yet
- Actual (before fix): Cannot test - NTB has 0 grid cells in database (data generation required)

**Example 4: Reset to Region View**
- Input: Click "Reset" button after filtering by kecamatan
- Expected: Return to showing all cells for the active region (e.g., all 50 NTT cells)
- Actual (before fix): Works correctly (no bug in reset path - preservation requirement)

---

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Region-wide display when no target area is selected must continue working exactly as before (all cells for selected region visible)
- Region switching (NTT → NTB → Central Kalimantan) without kecamatan selection must continue showing all cells for the new region
- Heatmap color coding (Green ≥70, Yellow 40-69, Red <40) must remain unchanged
- Confidence-based opacity (High 0.85, Med 0.55, Low 0.30) must remain unchanged
- Cell click behavior (open SidePanel with details) must remain unchanged
- Layer toggle behavior (heatmap ON/OFF) must remain unchanged
- Other layers (candidates, BTS markers, land cover) must remain unaffected by heatmap filtering
- Drawn polygon mode (if implemented in TargetAreaSelector) should apply the same spatial filtering logic

**Scope:**
All display and interaction behaviors that do NOT involve target area selection should be completely unaffected by this fix. The only change is the introduction of spatial filtering when a target area is active.

---

## Hypothesized Root Cause

Based on the bugfix requirements and code investigation, the root causes are:

1. **Missing Filtering Logic in MapView**: 
   - `MapView.tsx` receives `targetArea` state from `handleTargetAreaResolved` callback
   - `MapView.tsx` fetches grid cells via `RegionSelector` → `handleRegionChange` which loads all cells for the region
   - No spatial filtering step exists between fetching cells and passing them to `<CoverageHeatmap cells={coverageCells} />`
   - The `coverageCells` prop always contains the full unfiltered array

2. **No Spatial Utility Integration**:
   - Turf.js is not installed in `frontend/package.json`
   - No `pointInPolygon` or equivalent spatial utility function exists in the codebase
   - MapView has no mechanism to perform spatial filtering even if target area boundary is available

3. **Disconnected Data Flow**:
   - TargetAreaSelector correctly highlights the boundary and calls `onResolved(targetArea)`
   - MapView stores the resolved target area in state but never uses it to filter cells
   - CoverageHeatmap is a pure rendering component - it displays whatever cells are passed to it
   - No reactive effect connects target area changes to cell re-filtering

4. **Missing Data for NTB and Central Kalimantan**:
   - Database has 50 grid cells, all for region 'ntt'
   - NTB and Central Kalimantan regions have 0 grid cells
   - Backend pipeline has not been run for these regions
   - No validation exists to warn users about missing data coverage

---

## Correctness Properties

Property 1: Bug Condition - Spatial Filtering After Kecamatan Selection

_For any_ grid cell where a target area is selected and the cell's centroid (lat, lon) does NOT fall within the target area's boundary polygon (isBugCondition returns true), the fixed MapView component SHALL exclude that cell from the cells array passed to CoverageHeatmap, causing it to not be rendered on the map.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**

Property 2: Preservation - Region-Wide Display Without Target Area

_For any_ grid cell where no target area is selected (targetArea is null), the fixed MapView component SHALL include that cell in the cells array passed to CoverageHeatmap exactly as the original implementation does, preserving the region-wide display behavior where all cells for the active region remain visible.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11**

---

## Fix Implementation

### Architecture Decision: Client-Side Filtering

**Selected Approach**: Client-side spatial filtering in MapView using Turf.js

**Alternatives Considered**:
1. **PostGIS Backend Filtering**: Modify `getGridCells()` API to accept `target_area_id` parameter and perform `ST_Within` spatial query in Supabase
   - Rejected: Requires schema migration to add `target_area_id` foreign key to `grid_cells` table
   - Rejected: More complex implementation and testing surface
   - Rejected: Overkill for current scale (50 cells per region maximum)

2. **Hybrid Approach**: Backend filtering with frontend fallback
   - Rejected: Added complexity with minimal benefit at current scale
   - Could be revisited if grid cell counts exceed 500+ per region

**Why Client-Side Filtering Wins**:
- Grid cells are already loaded in memory (~50 cells per region)
- Turf.js `booleanPointInPolygon` is highly optimized and runs in <1ms for this dataset
- No backend changes required - faster iteration and deployment
- Simpler testing surface - unit tests can mock spatial checks easily
- Frontend already has boundary geometry from TargetAreaSelector

---

### Changes Required

**File**: `frontend/components/MapView.tsx`

**Function**: Component body, specifically data flow between `cells` state and `<CoverageHeatmap>` prop

**Specific Changes**:

1. **Install Turf.js Dependency**:
   - Add `@turf/boolean-point-in-polygon` to `frontend/package.json`
   - Version: Use latest stable (6.5.0 or higher)

2. **Import Turf.js Utility**:
   ```typescript
   import booleanPointInPolygon from '@turf/boolean-point-in-polygon'
   import { point, polygon } from '@turf/helpers'
   ```

3. **Create Filtering Function**:
   Add a pure function that filters grid cells by target area boundary:
   ```typescript
   function filterCellsByTargetArea(
     cells: GridCell[],
     targetArea: TargetArea | null
   ): GridCell[] {
     if (!targetArea || !targetArea.boundary_geojson) {
       return cells // No filtering - return all cells
     }
     
     const boundaryPolygon = polygon(targetArea.boundary_geojson.coordinates)
     
     return cells.filter((cell) => {
       const cellPoint = point([cell.lon, cell.lat])
       return booleanPointInPolygon(cellPoint, boundaryPolygon)
     })
   }
   ```

4. **Apply Filtering Before Passing to CoverageHeatmap**:
   Replace the current direct mapping:
   ```typescript
   // BEFORE (buggy):
   const coverageCells: CoverageCell[] = cells.map((c) => ({ ... }))
   ```
   
   With filtered mapping:
   ```typescript
   // AFTER (fixed):
   const filteredCells = filterCellsByTargetArea(cells, targetArea)
   const coverageCells: CoverageCell[] = filteredCells.map((c) => ({
     cell_id: c.cell_id,
     coverage_score: c.coverage_score,
     confidence_tag: c.confidence_tag,
     lat: c.lat,
     lon: c.lon,
   }))
   ```

5. **Add Reactive Effect for Target Area Changes**:
   The filtering will automatically occur whenever `cells` or `targetArea` state changes because the filtering function is called in the render path. No additional useEffect needed.

6. **Add Empty Results Messaging**:
   Add conditional UI in MapView overlay to display warning when filtered cells array is empty:
   ```typescript
   {targetArea && coverageCells.length === 0 && (
     <div style={{ /* warning banner styles */ }} data-testid="no-cells-warning">
       No heatmap data available for selected area. Data may not be processed yet.
     </div>
   )}
   ```

---

**File**: `frontend/package.json`

**Changes**: Add Turf.js dependencies
```json
"dependencies": {
  "@turf/boolean-point-in-polygon": "^6.5.0",
  "@turf/helpers": "^6.5.0",
  // ... existing dependencies
}
```

---

**File**: `backend/geosignal/pipeline.py` (Data Generation)

**Purpose**: Generate missing grid cells for NTB and Central Kalimantan regions

**Changes**:
1. Run the existing scoring pipeline for regions 'ntb' and 'central_kalimantan'
2. Ensure `grid_cells` table is populated with complete coverage for all kecamatan in both regions
3. Validate that every admin boundary in `admin_boundaries` table has corresponding grid cells within its boundary

**Validation Script** (add to `backend/geosignal/validation.py`):
```python
def validate_grid_cell_coverage(region_id: str) -> dict:
    """
    Validate that all kecamatan in a region have at least one grid cell.
    Returns dict with coverage statistics.
    """
    # Query admin_boundaries for region
    # Query grid_cells for region
    # For each boundary, check if at least one cell falls within its polygon
    # Return { total_kecamatan, covered_kecamatan, missing_kecamatan_ids }
```

---

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code (exploratory phase), then verify the fix works correctly and preserves existing behavior (fix and preservation checking).

The fix is primarily testable via:
- Unit tests for the filtering function
- Integration tests for MapView component behavior
- Manual testing with real map interactions

---

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm the root cause analysis. If we refute the hypothesis, we will need to re-hypothesize.

**Test Plan**: Write tests that select a kecamatan via TargetAreaSelector, observe the cells rendered by CoverageHeatmap, and assert that cells outside the boundary are incorrectly displayed. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:

1. **NTT Kecamatan Selection Test**: Select "Alor Selatan" kecamatan in NTT region
   - Expected counterexample: CoverageHeatmap renders all 50 NTT cells instead of filtering to ~5-10 cells within Alor Selatan boundary
   - Will fail on unfixed code: `expect(renderedCells.length).toBeLessThan(50)` assertion fails

2. **Boundary Crossing Test**: Select "Kupang Tengah" (mainland) when cells exist on Alor island
   - Expected counterexample: Cells on Alor island (>100km away) are displayed despite being outside Kupang Tengah boundary
   - Will fail on unfixed code: Cell with coordinates on Alor island passes to CoverageHeatmap

3. **Region Switch Test**: Switch from NTT to NTB and select any kecamatan
   - Expected counterexample: No cells exist for NTB, but no warning message is displayed (empty array silently rendered)
   - Will fail on unfixed code: Empty result with no user feedback

4. **Reset After Filtering Test**: Select kecamatan, observe filtering, click Reset button
   - Expected counterexample: After reset, if bug exists in reset path, cells remain filtered instead of showing all region cells
   - May pass on unfixed code (reset behavior is likely correct - preservation check)

**Expected Counterexamples**:
- MapView passes unfiltered cells array to CoverageHeatmap component
- No spatial filtering function is called between fetching cells and rendering
- Possible root cause confirmation: Missing filtering logic in MapView, no Turf.js integration

---

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds (target area selected, cell outside boundary), the fixed function produces the expected behavior (cell is excluded from rendered array).

**Pseudocode:**
```
FOR ALL cell IN grid_cells WHERE isBugCondition(cell, targetArea) DO
  filteredCells := filterCellsByTargetArea(grid_cells, targetArea)
  ASSERT cell NOT IN filteredCells
END FOR

// Positive check: cells inside boundary ARE included
FOR ALL cell IN grid_cells WHERE targetArea ≠ NULL AND pointInPolygon(cell, targetArea.boundary) DO
  filteredCells := filterCellsByTargetArea(grid_cells, targetArea)
  ASSERT cell IN filteredCells
END FOR
```

**Test Implementation**: Use property-based testing (PBT) to generate random cell coordinates and boundary polygons, then verify filtering correctness.

---

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold (no target area selected), the fixed function produces the same result as the original function (all region cells visible).

**Pseudocode:**
```
FOR ALL cell IN grid_cells WHERE targetArea IS NULL DO
  filteredCells_original := grid_cells  // Original behavior: no filtering
  filteredCells_fixed := filterCellsByTargetArea(grid_cells, NULL)
  ASSERT filteredCells_original = filteredCells_fixed
  ASSERT cell IN filteredCells_fixed
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain (various cell configurations, null target areas)
- It catches edge cases that manual unit tests might miss (empty cell arrays, boundary edge cases)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs (no regressions)

**Test Plan**: 
1. Observe behavior on UNFIXED code first: Verify that when targetArea is null, all cells are passed through unchanged
2. Write property-based tests capturing that behavior using Hypothesis (Python) or fast-check (TypeScript)
3. Run tests on FIXED code to verify preservation

**Test Cases**:

1. **No Target Area Selected**: targetArea state is null after initial load
   - Property: `filterCellsByTargetArea(cells, null)` returns `cells` unchanged
   - Verify: All region cells are rendered (length matches cells.length)

2. **Region Switch Resets Target Area**: Switch from NTT to NTB, no kecamatan selected yet
   - Property: After region switch, targetArea is reset to null, all NTB cells are visible
   - Verify: MapView renders all cells for new region (preservation of region-wide display)

3. **Heatmap Layer Toggle**: Toggle heatmap OFF then ON while target area is null
   - Property: Layer visibility changes but cell array remains unfiltered
   - Verify: CoverageHeatmap receives full cell array both times

4. **Cell Click Behavior**: Click a cell when no target area is selected
   - Property: SidePanel opens with cell details (existing behavior preserved)
   - Verify: onClick handler receives correct cell data from unfiltered array

---

### Unit Tests

**Test Suite**: `frontend/__tests__/MapView.spatial-filtering.test.tsx`

1. **filterCellsByTargetArea Function Tests**:
   - Test null target area returns all cells
   - Test valid target area filters cells correctly
   - Test empty boundary returns empty array (edge case)
   - Test cell on boundary edge (use Turf.js precision)
   - Test cells with invalid coordinates (graceful handling)

2. **MapView Component Integration Tests**:
   - Test initial render with no target area shows all cells
   - Test target area selection triggers filtering
   - Test target area reset restores all cells
   - Test region switch resets target area and cells
   - Test empty filtered result displays warning message

3. **CoverageHeatmap Rendering Tests**:
   - Verify CoverageHeatmap receives filtered cell array
   - Verify CoverageHeatmap renders only filtered cells on map
   - Verify cell count matches filtered array length

---

### Property-Based Tests

**Test Suite**: `frontend/__tests__/MapView.pbt.test.tsx`

Use `fast-check` (TypeScript) or `Hypothesis` (Python) to generate random test cases:

1. **Spatial Filtering Property**:
   - Generate: Random grid cells with lat/lon coordinates within Indonesia bounds
   - Generate: Random polygon boundary (valid GeoJSON Polygon)
   - Property: All cells in filtered array satisfy `booleanPointInPolygon(cell, boundary) === true`
   - Property: All cells NOT in filtered array satisfy `booleanPointInPolygon(cell, boundary) === false`

2. **Preservation Property**:
   - Generate: Random grid cell arrays (0-100 cells)
   - Property: When targetArea is null, `filterCellsByTargetArea(cells, null) === cells`
   - Property: Filtered array length equals original array length when targetArea is null

3. **Idempotence Property**:
   - Generate: Random cells and target area
   - Property: `filter(filter(cells, ta), ta) === filter(cells, ta)` (filtering twice produces same result)

4. **Boundary Edge Cases**:
   - Generate: Cells with coordinates exactly on boundary edges
   - Property: Turf.js handles edge cases consistently (no crashes, deterministic inclusion/exclusion)

---

### Integration Tests

**Test Suite**: `frontend/__tests__/MapView.integration.test.tsx`

1. **Full Kecamatan Selection Flow**:
   - Render MapView with NTT region and admin boundaries
   - Select "Alor Selatan" kecamatan from TargetAreaSelector dropdown
   - Verify boundary is highlighted on map
   - Verify CoverageHeatmap displays only cells within Alor Selatan boundary
   - Verify cell count decreases from 50 to expected subset

2. **Region Switch Resets Filtering**:
   - Start with NTT region and "Alor Selatan" selected (cells filtered)
   - Switch to NTB region via RegionSelector
   - Verify target area is reset (boundary highlight removed)
   - Verify heatmap shows all NTB cells (no filtering)

3. **Empty Results Handling**:
   - Select a kecamatan that has no grid cells within its boundary
   - Verify warning message is displayed: "No heatmap data available for selected area"
   - Verify boundary remains highlighted despite empty results
   - Verify no crashes or rendering errors

4. **Layer Toggle During Filtering**:
   - Select kecamatan (filtering active)
   - Toggle heatmap layer OFF
   - Verify cells disappear from map
   - Toggle heatmap layer ON
   - Verify only filtered cells reappear (filtering is preserved during toggle)

5. **Data Coverage Validation** (requires NTB/Central Kalimantan data):
   - Load MapView with NTB region
   - Verify RegionSelector displays data coverage status
   - Select any NTB kecamatan
   - Verify heatmap cells are displayed (data generation successful)
   - Repeat for Central Kalimantan

---

### Manual Testing Checklist

**Tester**: QA Engineer or Developer

1. **NTT Region Testing**:
   - [ ] Load app, verify NTT selected by default, all ~50 cells visible
   - [ ] Select "Alor Selatan" kecamatan, verify cells filter to Alor area only
   - [ ] Select "Kupang Tengah" kecamatan, verify cells filter to Kupang area only
   - [ ] Select "Rote Ndao" kecamatan, verify cells filter to Rote island only
   - [ ] Click Reset, verify all 50 cells reappear

2. **NTB Region Testing** (after data generation):
   - [ ] Switch to NTB region, verify cells appear
   - [ ] Select any kecamatan, verify filtering works
   - [ ] Verify no cells from NTT are displayed in NTB region

3. **Central Kalimantan Testing** (after data generation):
   - [ ] Switch to Central Kalimantan region, verify cells appear
   - [ ] Select any kecamatan, verify filtering works
   - [ ] Verify distinct cells from other regions

4. **Empty Results Testing**:
   - [ ] If any kecamatan has no cells, verify warning message displays
   - [ ] Verify boundary remains highlighted
   - [ ] Verify no console errors

5. **Preservation Testing**:
   - [ ] Toggle heatmap layer OFF/ON without target area selected - all cells visible
   - [ ] Toggle heatmap layer OFF/ON with target area selected - filtered cells visible
   - [ ] Click cell to open SidePanel - works with and without filtering
   - [ ] Verify color coding unchanged (Green/Yellow/Red)
   - [ ] Verify opacity unchanged (High 0.85, Med 0.55, Low 0.30)

6. **Drawn Polygon Mode** (if implemented):
   - [ ] Switch to drawn polygon mode
   - [ ] Draw a custom polygon
   - [ ] Verify same spatial filtering logic applies
   - [ ] Verify only cells within drawn polygon are displayed

---

## Data Generation Requirements

### Backend Pipeline Execution

**Objective**: Ensure all three provinces (NTT, NTB, Central Kalimantan) and ALL kecamatan within them have complete heatmap data coverage.

**Current State**:
- `grid_cells` table: 50 cells, all for region 'ntt'
- `admin_boundaries` table: 45 kecamatan (21 NTT, 10 NTB, 14 Central Kalimantan)
- Missing: Grid cells for NTB and Central Kalimantan regions

**Required Actions**:

1. **Run Scoring Pipeline for NTB**:
   ```bash
   python backend/geosignal/pipeline.py --region ntb --resolution 1000
   ```
   - Expected output: ~30-40 grid cells covering all NTB kecamatan
   - Validation: Run `validate_grid_cell_coverage('ntb')` → 100% coverage

2. **Run Scoring Pipeline for Central Kalimantan**:
   ```bash
   python backend/geosignal/pipeline.py --region central_kalimantan --resolution 1000
   ```
   - Expected output: ~50-60 grid cells covering all Central Kalimantan kecamatan
   - Validation: Run `validate_grid_cell_coverage('central_kalimantan')` → 100% coverage

3. **Verify Data Completeness**:
   ```sql
   -- Check coverage by region
   SELECT 
     ab.region_id,
     COUNT(DISTINCT ab.kecamatan_id) as total_kecamatan,
     COUNT(DISTINCT gc.cell_id) as total_cells,
     COUNT(DISTINCT CASE 
       WHEN ST_Within(
         ST_SetSRID(ST_MakePoint(gc.lon, gc.lat), 4326),
         ST_GeomFromGeoJSON(ab.boundary_geojson)
       ) THEN ab.kecamatan_id 
     END) as covered_kecamatan
   FROM admin_boundaries ab
   LEFT JOIN grid_cells gc ON ab.region_id = gc.region_id
   GROUP BY ab.region_id;
   ```
   - Expected result: All three regions show covered_kecamatan = total_kecamatan

4. **Update Frontend Validation**:
   - Add data coverage check on app load
   - Display status indicator in RegionSelector if data is incomplete
   - Show actionable error messages when selecting regions/kecamatan with missing data

---

## Error Handling and Edge Cases

### Empty Filtered Results

**Scenario**: Target area is selected but no grid cells fall within its boundary.

**UI Response**:
- Display warning banner in MapView overlay: "No heatmap data available for selected area. Data may not be processed yet for this kecamatan."
- Keep boundary highlight visible
- Keep TargetAreaSelector in "resolved" state (allow user to Reset and try another area)
- Log warning to console: `[MapView] No grid cells found within target area ${targetArea.target_area_id}`

### Invalid Boundary Geometry

**Scenario**: TargetArea has malformed boundary_geojson (e.g., invalid Polygon coordinates).

**Handling**:
- Catch Turf.js exceptions in `filterCellsByTargetArea` function
- Log error: `[MapView] Invalid boundary geometry for target area ${targetArea.target_area_id}`
- Fall back to showing all region cells (no filtering)
- Display error banner: "Unable to filter cells - invalid boundary data"

### Missing Target Area Data

**Scenario**: User selects kecamatan but API returns error or null.

**Handling**:
- TargetAreaSelector already handles this with error state
- MapView receives null targetArea → shows all region cells (preservation behavior)
- No additional handling needed in filtering logic

### Zero Grid Cells for Region

**Scenario**: User switches to region with no grid cells in database.

**Handling**:
- RegionSelector loads empty cells array
- MapView passes empty array to CoverageHeatmap
- Display prominent warning: "No heatmap data available for this region. Please run data generation pipeline."
- Disable TargetAreaSelector or show "Data not available" message
- Provide link/guidance to run backend pipeline

---

## Performance Considerations

### Turf.js Performance

- `booleanPointInPolygon` has O(n) complexity where n = number of polygon vertices
- Typical kecamatan boundary: ~100-500 vertices
- Filtering 50 cells × 500 vertices = 25,000 operations
- Estimated time: <1ms on modern browsers
- No performance concerns at current scale

### Optimization Opportunities (Future)

If grid cell counts grow beyond 500 per region:
1. **Spatial Indexing**: Pre-compute which cells belong to which kecamatan during pipeline execution
2. **Backend Filtering**: Move to PostGIS `ST_Within` queries in `getGridCells()` API
3. **Caching**: Cache filtered results per target_area_id to avoid redundant calculations
4. **Web Workers**: Offload filtering to Web Worker thread to avoid UI blocking

Current implementation prioritizes simplicity and maintainability over premature optimization.

---

## Deployment Strategy

### Phase 1: Fix Implementation (No Data)
1. Merge filtering logic to MapView component
2. Install Turf.js dependencies
3. Deploy to staging environment
4. Test with NTT data (only region with existing cells)
5. Verify empty results handling for NTB and Central Kalimantan

### Phase 2: Data Generation
1. Run backend scoring pipeline for NTB region
2. Run backend scoring pipeline for Central Kalimantan region
3. Validate data completeness for all regions
4. Verify data in staging Supabase instance

### Phase 3: Production Deployment
1. Deploy filtering logic to production
2. Verify data exists for all three regions in production Supabase
3. Run integration tests in production environment
4. Monitor for errors and performance issues

### Rollback Plan
- If filtering causes performance issues: Add feature flag to disable filtering
- If data generation fails: Display clear error messages, allow region selection but show warnings
- If critical bugs found: Revert MapView component to pre-filtering version
