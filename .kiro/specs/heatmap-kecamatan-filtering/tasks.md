# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Cells Outside Boundary Remain Visible
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Generate random kecamatan selections and verify cells outside boundary are incorrectly displayed
  - Test implementation: For any selected kecamatan, check if cells outside the boundary polygon are still visible in CoverageHeatmap
  - The test should select "Alor Selatan" (NTT) and verify that cells NOT within its boundary are displayed (bug condition)
  - Use Turf.js booleanPointInPolygon to identify which cells should be filtered
  - Assert that MapView passes unfiltered cells to CoverageHeatmap (50 NTT cells instead of ~5-10 within boundary)
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples: specific cells outside boundary that are incorrectly displayed
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.7_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Region-Wide Display Without Target Area
  - **IMPORTANT**: Follow observation-first methodology
  - Observe behavior on UNFIXED code for non-buggy inputs (no target area selected)
  - Write property-based test: When targetArea is null, all region cells remain visible
  - Test that region switching without kecamatan selection shows all cells for new region
  - Test that heatmap layer toggle preserves cell visibility when no target area is active
  - Test that cell click behavior works correctly without filtering
  - Test that color coding (Green ≥70, Yellow 40-69, Red <40) remains unchanged
  - Test that confidence-based opacity (High 0.85, Med 0.55, Low 0.30) remains unchanged
  - Property-based testing generates many test cases for stronger guarantees
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11_

- [ ] 3. Implement spatial filtering fix

  - [x] 3.1 Add Turf.js dependencies
    - Install `@turf/boolean-point-in-polygon` version ^6.5.0 in frontend
    - Install `@turf/helpers` version ^6.5.0 in frontend
    - Run `npm install` in frontend directory
    - Verify dependencies are added to `frontend/package.json`
    - _Requirements: 2.6_

  - [x] 3.2 Implement filterCellsByTargetArea function in MapView
    - Open `frontend/components/MapView.tsx`
    - Import Turf.js utilities: `import booleanPointInPolygon from '@turf/boolean-point-in-polygon'`
    - Import helpers: `import { point, polygon } from '@turf/helpers'`
    - Create pure function `filterCellsByTargetArea(cells: GridCell[], targetArea: TargetArea | null): GridCell[]`
    - Handle null target area case: return all cells unchanged (preservation)
    - Extract boundary polygon from `targetArea.boundary_geojson.coordinates`
    - Filter cells using `booleanPointInPolygon(point([cell.lon, cell.lat]), boundaryPolygon)`
    - Return filtered cells array
    - _Bug_Condition: isBugCondition(cell, targetArea) where cell is NOT in pointInPolygon(cell, boundary)_
    - _Expected_Behavior: Only cells where pointInPolygon(cell, boundary) === true are included in filtered array_
    - _Preservation: When targetArea is null, return cells unchanged_
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 3.1_

  - [x] 3.3 Connect filtering to MapView render path
    - Locate where `coverageCells` is mapped from `cells` state
    - Replace direct mapping with: `const filteredCells = filterCellsByTargetArea(cells, targetArea)`
    - Update mapping: `const coverageCells: CoverageCell[] = filteredCells.map((c) => ({ ... }))`
    - Ensure filtering occurs reactively when `cells` or `targetArea` state changes
    - Verify `targetArea` state is available from `handleTargetAreaResolved` callback
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [x] 3.4 Add empty results messaging
    - Add conditional UI in MapView overlay section
    - Check if `targetArea && coverageCells.length === 0`
    - Display warning banner: "No heatmap data available for selected area. Data may not be processed yet for this kecamatan."
    - Add `data-testid="no-cells-warning"` for testing
    - Style banner with appropriate warning colors and positioning
    - Ensure boundary highlight remains visible even with empty results
    - _Requirements: 2.7, 2.8, 2.12, 2.13_

  - [x] 3.5 Add error handling for invalid boundary geometry
    - Wrap Turf.js calls in try-catch block within `filterCellsByTargetArea`
    - Catch exceptions and log error: `console.error('[MapView] Invalid boundary geometry for target area', targetArea.target_area_id, error)`
    - Fall back to showing all region cells (no filtering) on error
    - Display error banner: "Unable to filter cells - invalid boundary data"
    - Prevent crashes from malformed GeoJSON
    - _Requirements: 2.6_

  - [x] 3.6 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Only Cells Inside Boundary Are Visible
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (spatial filtering)
    - Run test: Select "Alor Selatan" kecamatan, verify only cells within boundary are displayed
    - Assert that cells outside boundary are NOT in the rendered array
    - Assert that filtered cell count is less than total region cells (50 → ~5-10)
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6_

  - [x] 3.7 Verify preservation tests still pass
    - **Property 2: Preservation** - Region-Wide Display Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - Verify region-wide display works (no target area selected → all cells visible)
    - Verify region switching preserves behavior
    - Verify heatmap layer toggle works correctly
    - Verify cell click behavior unchanged
    - Verify color coding and opacity unchanged
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11_

- [ ] 4. Data generation for NTB region

  - [x] 4.1 Run backend scoring pipeline for NTB
    - Navigate to backend directory
    - Run command: `python backend/geosignal/pipeline.py --region ntb --resolution 1000`
    - Monitor pipeline execution for errors
    - Verify pipeline completes successfully
    - _Requirements: 2.9, 2.10, 3.12_

  - [x] 4.2 Validate NTB data coverage
    - Query Supabase: `SELECT COUNT(*) FROM grid_cells WHERE region_id = 'ntb'`
    - Expected: ~30-40 grid cells for NTB region
    - Verify all 10 NTB kecamatan have at least one cell within their boundaries
    - Run SQL query to check coverage by kecamatan:
      ```sql
      SELECT 
        ab.kecamatan_name,
        COUNT(gc.cell_id) as cell_count
      FROM admin_boundaries ab
      LEFT JOIN grid_cells gc ON ab.region_id = gc.region_id
        AND ST_Within(
          ST_SetSRID(ST_MakePoint(gc.lon, gc.lat), 4326),
          ST_GeomFromGeoJSON(ab.boundary_geojson)
        )
      WHERE ab.region_id = 'ntb'
      GROUP BY ab.kecamatan_name
      ORDER BY cell_count;
      ```
    - Document any kecamatan with 0 cells
    - _Requirements: 2.9, 2.10, 3.12_

  - [ ] 4.3 Test NTB kecamatan selection in UI
    - Load MapView in browser
    - Switch to NTB region
    - Verify heatmap cells are displayed for NTB
    - Select any NTB kecamatan from dropdown
    - Verify spatial filtering works (cells filter to selected boundary)
    - Verify no cells from NTT or Central Kalimantan are displayed
    - Test multiple NTB kecamatan selections
    - _Requirements: 2.1, 2.2, 2.3, 2.9, 2.10_

- [ ] 5. Data generation for Central Kalimantan region

  - [x] 5.1 Run backend scoring pipeline for Central Kalimantan
    - Navigate to backend directory
    - Run command: `python backend/geosignal/pipeline.py --region central_kalimantan --resolution 1000`
    - Monitor pipeline execution for errors
    - Verify pipeline completes successfully
    - _Requirements: 2.9, 2.10, 3.12_

  - [x] 5.2 Validate Central Kalimantan data coverage
    - Query Supabase: `SELECT COUNT(*) FROM grid_cells WHERE region_id = 'central_kalimantan'`
    - Expected: ~50-60 grid cells for Central Kalimantan region
    - Verify all 14 Central Kalimantan kecamatan have at least one cell within their boundaries
    - Run SQL query to check coverage by kecamatan (same query as 4.2, change region to 'central_kalimantan')
    - Document any kecamatan with 0 cells
    - _Requirements: 2.9, 2.10, 3.12_

  - [ ] 5.3 Test Central Kalimantan kecamatan selection in UI
    - Load MapView in browser
    - Switch to Central Kalimantan region
    - Verify heatmap cells are displayed for Central Kalimantan
    - Select any Central Kalimantan kecamatan from dropdown
    - Verify spatial filtering works (cells filter to selected boundary)
    - Verify no cells from NTT or NTB are displayed
    - Test multiple Central Kalimantan kecamatan selections
    - _Requirements: 2.1, 2.2, 2.3, 2.9, 2.10_

- [ ] 6. Add data coverage validation to frontend

  - [x] 6.1 Create data coverage validation utility
    - Create `frontend/lib/validation/data-coverage.ts`
    - Implement `validateRegionDataCoverage(regionId: string): Promise<DataCoverageStatus>`
    - Query grid_cells and admin_boundaries to check if all kecamatan have cells
    - Return status object: `{ hasData: boolean, totalKecamatan: number, coveredKecamatan: number, missingKecamatan: string[] }`
    - _Requirements: 2.9, 2.10, 2.11, 3.12, 3.13, 3.14_

  - [x] 6.2 Display data coverage status in RegionSelector
    - Modify `frontend/components/RegionSelector.tsx`
    - Call `validateRegionDataCoverage` on component mount
    - Display badge/indicator next to region name showing data status
    - Green checkmark for complete coverage (100% kecamatan have cells)
    - Yellow warning for incomplete coverage (<100% kecamatan have cells)
    - Red error for no data (0 cells)
    - Add tooltip showing coverage details on hover
    - _Requirements: 2.11, 3.14_

  - [ ] 6.3 Enhance empty results messaging with coverage info
    - Update empty results banner from task 3.4
    - Include specific coverage information: "X of Y kecamatan have heatmap data"
    - List missing kecamatan names if data is incomplete
    - Provide actionable guidance: "Contact administrator to process missing data"
    - Add link to data generation documentation if available
    - _Requirements: 2.7, 2.8, 2.12, 2.13, 3.14_

- [ ] 7. Integration testing

  - [ ] 7.1 Test full kecamatan selection flow
    - Test suite: `frontend/__tests__/MapView.integration.test.tsx`
    - Test: Render MapView with NTT region and admin boundaries
    - Test: Select "Alor Selatan" kecamatan from TargetAreaSelector
    - Test: Verify boundary is highlighted on map
    - Test: Verify CoverageHeatmap displays only cells within Alor Selatan boundary
    - Test: Verify cell count decreases from 50 to expected subset (~5-10)
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ] 7.2 Test region switch resets filtering
    - Test: Start with NTT region and "Alor Selatan" selected (cells filtered)
    - Test: Switch to NTB region via RegionSelector
    - Test: Verify target area is reset (boundary highlight removed)
    - Test: Verify heatmap shows all NTB cells (no filtering)
    - Test: Verify cell count matches NTB total (~30-40)
    - _Requirements: 3.1, 3.2, 3.9_

  - [ ] 7.3 Test empty results handling
    - Test: Select a kecamatan that has no grid cells within its boundary
    - Test: Verify warning message is displayed with correct text
    - Test: Verify boundary remains highlighted despite empty results
    - Test: Verify no crashes or rendering errors
    - Test: Verify data-testid="no-cells-warning" element is present
    - _Requirements: 2.7, 2.8_

  - [ ] 7.4 Test layer toggle during filtering
    - Test: Select kecamatan (filtering active, e.g., "Kupang Tengah")
    - Test: Toggle heatmap layer OFF via LayerToggleBar
    - Test: Verify cells disappear from map
    - Test: Toggle heatmap layer ON
    - Test: Verify only filtered cells reappear (not all region cells)
    - Test: Verify filtering state is preserved during toggle
    - _Requirements: 3.6, 3.7_

  - [ ] 7.5 Test data coverage validation
    - Test: Load MapView with each region (NTT, NTB, Central Kalimantan)
    - Test: Verify RegionSelector displays data coverage status
    - Test: Verify all three regions show 100% coverage (green checkmark)
    - Test: Select any kecamatan from each region
    - Test: Verify heatmap cells are displayed (data exists)
    - Test: Verify no "missing data" warnings appear
    - _Requirements: 2.9, 2.10, 2.11_

- [ ] 8. Unit testing

  - [ ] 8.1 Test filterCellsByTargetArea function
    - Test suite: `frontend/__tests__/MapView.spatial-filtering.test.tsx`
    - Test: Null target area returns all cells unchanged
    - Test: Valid target area filters cells correctly (mock Turf.js)
    - Test: Empty boundary returns empty array (edge case)
    - Test: Cell on boundary edge uses Turf.js precision rules
    - Test: Invalid cell coordinates handled gracefully (no crash)
    - Test: Malformed boundary geometry caught by try-catch
    - _Requirements: 2.1, 2.4, 2.6, 3.1_

  - [ ] 8.2 Test MapView component behavior
    - Test: Initial render with no target area shows all cells
    - Test: Target area selection triggers filtering (mock handleTargetAreaResolved)
    - Test: Target area reset restores all cells
    - Test: Region switch resets target area and cells
    - Test: Empty filtered result displays warning message
    - Test: Invalid boundary geometry displays error message
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.7, 2.8, 3.1, 3.9_

  - [ ] 8.3 Test CoverageHeatmap receives filtered cells
    - Test: Verify CoverageHeatmap receives filtered cell array as prop
    - Test: Verify CoverageHeatmap renders only filtered cells on map
    - Test: Verify cell count matches filtered array length
    - Test: Verify color coding and opacity unchanged
    - _Requirements: 2.1, 3.3, 3.4_

- [ ] 9. Manual testing checklist

  - [ ] 9.1 NTT region testing
    - Load app, verify NTT selected by default, all ~50 cells visible
    - Select "Alor Selatan" kecamatan, verify cells filter to Alor area only
    - Select "Kupang Tengah" kecamatan, verify cells filter to Kupang area only
    - Select "Rote Ndao" kecamatan, verify cells filter to Rote island only
    - Click Reset button, verify all 50 cells reappear
    - Test multiple kecamatan selections in sequence
    - _Requirements: 2.1, 2.2, 2.3, 3.9_

  - [ ] 9.2 NTB region testing
    - Switch to NTB region, verify cells appear (~30-40 expected)
    - Select any NTB kecamatan, verify filtering works
    - Verify no cells from NTT are displayed in NTB region
    - Test empty results if any kecamatan lacks cells
    - Verify data coverage indicator shows 100% coverage
    - _Requirements: 2.1, 2.2, 2.3, 2.9, 2.10, 2.11_

  - [ ] 9.3 Central Kalimantan region testing
    - Switch to Central Kalimantan region, verify cells appear (~50-60 expected)
    - Select any Central Kalimantan kecamatan, verify filtering works
    - Verify distinct cells from other regions (no overlap)
    - Test empty results if any kecamatan lacks cells
    - Verify data coverage indicator shows 100% coverage
    - _Requirements: 2.1, 2.2, 2.3, 2.9, 2.10, 2.11_

  - [ ] 9.4 Preservation testing
    - Toggle heatmap layer OFF/ON without target area selected - all cells visible
    - Toggle heatmap layer OFF/ON with target area selected - filtered cells visible
    - Click cell to open SidePanel - works with and without filtering
    - Verify color coding unchanged (Green ≥70, Yellow 40-69, Red <40)
    - Verify opacity unchanged (High 0.85, Med 0.55, Low 0.30)
    - Verify BTS candidate markers display independently (no filtering)
    - Verify other map layers (land cover, contours, villages) function normally
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 3.7, 3.10, 3.11_

  - [ ] 9.5 Error handling testing
    - Test empty results scenario (select kecamatan with no cells)
    - Verify warning message displays correctly
    - Verify boundary remains highlighted with empty results
    - Verify no console errors during normal operation
    - Test invalid boundary geometry handling (if possible to trigger)
    - Verify app recovers gracefully from errors
    - _Requirements: 2.7, 2.8, 2.12, 2.13_

- [ ] 10. Checkpoint - Ensure all tests pass
  - Run all unit tests: `npm test` in frontend directory
  - Run all integration tests
  - Execute manual testing checklist
  - Verify all three regions have complete data coverage
  - Verify no console errors or warnings
  - Verify spatial filtering works correctly for all regions
  - Verify preservation requirements are met (no regressions)
  - Ask the user if questions arise or if any tests fail
