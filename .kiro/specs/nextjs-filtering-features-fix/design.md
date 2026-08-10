# Next.js Filtering Features Fix — Bugfix Design

## Overview

The GeoSignal AI Next.js application experiences multiple runtime failures that prevent map filtering controls from functioning. The root cause is a non-existent property access (`M_ID`) in GADM administrative boundary data, which cascades into component initialization failures across all eight filtering UI components. This design addresses the property mapping error, restores component functionality, implements graceful degradation for the ESA WorldCover tile service, and ensures proper initialization order.

### Design Goals

- Map GADM Level 2 boundary properties correctly to the `AdminBoundary` interface, eliminating the `M_ID` error
- Restore full functionality to all eight broken filtering features (Region selector, Land Cover, Heatmap, Target Area, BTS Towers, Candidates, Contours, Villages)
- Implement graceful degradation for ESA WorldCover tile service errors with user-visible warnings
- Ensure components initialize in the correct dependency order to prevent race conditions
- Preserve all existing functionality including heatmap rendering, candidate selection, target area workflows, and confidence tagging

### Out of Scope (MVP)

- Migrating from ESA WorldCover to an alternative land cover data provider
- Implementing offline caching for GADM boundaries
- Rewriting the MapLibre layer stack architecture
- Adding new filtering features beyond the existing eight

---

## Glossary

- **GADM**: Database of Global Administrative Areas — provides administrative boundary geometries at multiple levels (Level 2 = kabupaten/kecamatan for Indonesia)
- **GID_2**: GADM's unique identifier for Level 2 administrative units (e.g., `IDN.15.1_1`)
- **NAME_2**: GADM's name field for Level 2 units (e.g., `Alor`)
- **M_ID**: A non-existent property that the code incorrectly attempts to access, causing TypeErrors
- **AdminBoundary**: TypeScript interface in `frontend/lib/types.ts` that requires `boundary_id`, `kecamatan_id`, `kecamatan_name`, `region_id`, `boundary_geojson`
- **ESA WorldCover**: European Space Agency's 10m land cover classification tile service at `services.terrascope.be`
- **ERR_HTTP2_PROTOCOL_ERROR**: Browser error when the ESA WorldCover tile service returns HTTP/2 protocol violations
- **MapLibre GL**: WebGL-based map rendering library used by the frontend
- **TargetAreaSelector**: Component (Task 23.5) enabling draw polygon or kecamatan selection for analysis boundaries
- **RegionSelector**: Component (Task 23.3) for switching between NTT, NTB, and Central Kalimantan provinces
- **CoverageHeatmap**: Component (Task 23.1) rendering green/yellow/red coverage quality visualization

---

## Bug Details

### Bug Condition

The bug manifests when the application initializes map layers or when the user interacts with any filtering controls. The system attempts to read a property `M_ID` from GADM boundary feature data, but GADM Level 2 GeoJSON features do not contain this property.

**Formal Specification:**
```
FUNCTION isBugCondition(event)
  INPUT: event of type (ApplicationLoad | UserFilteringInteraction)
  OUTPUT: boolean
  
  RETURN (event.type == ApplicationLoad OR event.type == UserFilteringInteraction)
         AND gadmFeatureAccessAttempted(event)
         AND propertyAccessed(event) == 'M_ID'
         AND NOT propertyExists('M_ID', gadmFeatureProperties)
         AND componentInitializationBlocked(event)
END FUNCTION
```

**GADM Property Structure** (from `data/gadm_cache/gadm41_IDN_2.json`):
```json
{
  "type": "Feature",
  "properties": {
    "GID_2": "IDN.15.1_1",
    "GID_0": "IDN",
    "COUNTRY": "Indonesia",
    "GID_1": "IDN.15_1",
    "NAME_1": "Nusa Tenggara Timur",
    "NAME_2": "Alor",
    "TYPE_2": "Kabupaten",
    "HASC_2": "ID.NT.AL"
  },
  "geometry": { ... }
}
```

**Observable Property**: `M_ID` does NOT exist in the properties object.

### Examples

1. **Application Load Example**:
   - User navigates to the application URL
   - MapView component mounts and initializes MapLibre
   - MapView attempts to add GADM boundary layers
   - Code accesses `feature.properties.M_ID` (undefined)
   - TypeError: "Cannot read properties of undefined (reading 'M_ID')" thrown
   - All eight filtering controls fail to render: Region selector, Land Cover checkbox, Heatmap toggle, Target Area controls, BTS Towers toggle, Candidates toggle, Contours toggle, Villages toggle
   - User sees blank or broken UI with console errors

2. **Region Selector Interaction Example**:
   - User clicks Region dropdown (if it rendered)
   - RegionSelector calls `/api/grid-cells?region_id=ntt&resolution_m=100`
   - TargetAreaSelector attempts to load admin boundaries for NTT
   - Code accesses `boundary.M_ID` during kecamatan dropdown population
   - TypeError thrown
   - Kecamatan dropdown shows "No kecamatan data available for this region" despite boundaries existing in database

3. **Target Area Kecamatan Mode Example**:
   - User selects "Kecamatan" tab in TargetAreaSelector
   - Component fetches admin boundaries via `adminBoundaries` prop
   - Code maps boundaries to dropdown options using `boundary.M_ID` as key
   - TypeError thrown
   - Dropdown displays empty or shows error message
   - Boundary highlighting fails to render on map

4. **ESA WorldCover Tile Load Example**:
   - MapView adds Land Cover layer with ESA WorldCover WMTS URL
   - Browser requests tile from `services.terrascope.be/wmts/v2`
   - Service returns ERR_HTTP2_PROTOCOL_ERROR
   - Land Cover layer fails silently, checkbox appears functional but layer never displays
   - No user-visible warning or fallback message
   - Other layers continue functioning but user has no indication of Land Cover failure

## Expected Behavior

### Correct GADM Property Mapping

When administrative boundary data (kecamatan boundaries from GADM Level 2) is accessed for the Target Area Selector, the system SHALL correctly map GADM properties to the `AdminBoundary` TypeScript interface:

```typescript
// Correct mapping (design fix):
{
  boundary_id:       feature.properties.GID_2,      // "IDN.15.1_1"
  kecamatan_id:      feature.properties.GID_2,      // or HASC_2 as alternative
  kecamatan_name:    feature.properties.NAME_2,     // "Alor"
  region_id:         derivedFromGID_1(feature.properties.GID_1), // "ntt"
  boundary_geojson:  feature.geometry
}
```

**Region ID Derivation Logic**:
```typescript
// GID_1 → region_id mapping (reverse of REGION_PROVINCE_FILTERS):
function deriveRegionId(gid1: string, name1: string): RegionId {
  const normalized = name1.toLowerCase().replace(/\s/g, '')
  
  if (normalized.includes('nusatenggaratimur')) return 'ntt'
  if (normalized.includes('nusatenggarabarat')) return 'ntb'
  if (normalized.includes('kalimantantengah')) return 'central_kalimantan'
  
  // Fallback: use GID_1 prefix (IDN.15_1 → province 15 → NTT)
  throw new Error(`Unknown province: ${name1} (${gid1})`)
}
```

### Preservation Requirements

**Unchanged Behaviors:**
- Coverage Gap Heatmap rendering with green (≥70), yellow (40-69), red (<40) thresholds must continue to work (Requirements 3.1-3.5)
- BTS candidate click-to-select interaction opening SidePanel with Coverage Score, Confidence Tag, SHAP explanations must continue to work (Requirement 10.4)
- RegionSelector's AbortController race-condition handling and stale-request prevention logic must continue to function (Task 23.3)
- TargetAreaSelector's two-mode workflow (drawn_polygon vs kecamatan) and boundary highlighting behavior must continue to operate (Requirements 10.7, 10.8)
- Grid cell data and BTS candidate data fetching via API routes (`/api/grid-cells`, `/api/recommendations`, `/api/target-area`) must continue to return correctly formatted responses matching TypeScript interfaces
- WebGLFallback component display with browser recommendations for unsupported environments must continue to function (Requirement 10.6)
- GeoAI watermark "GeoAI-assisted estimate — decision support only" display at bottom center of map must continue to be visible (Requirement 9.3)
- SimulationPanel, DragDropMarker, PowerOverlay, ConfidenceGate components must continue to function (Task 24)

## Hypothesized Root Cause

Based on the bug description and code analysis, the most likely issues are:

1. **Incorrect Property Access in AdminBoundary Mapping**: Code in `frontend/app/api/target-area/route.ts`, `frontend/lib/server/geosignal-service.ts`, or `frontend/components/TargetAreaSelector.tsx` attempts to access `boundary.properties.M_ID` or `boundary.M_ID` when constructing `AdminBoundary` objects from GADM features, but GADM Level 2 data uses `GID_2` as the unique identifier

2. **Missing Property Validation**: The `parse_gadm_features` function in `backend/geosignal/admin_boundaries.py` correctly maps `GID_2 → kecamatan_id` and `NAME_2 → kecamatan_name`, but the frontend may be bypassing this mapping and accessing raw GADM features directly

3. **Inconsistent Boundary Data Flow**: Three possible data flow paths exist:
   - **Backend Python → Supabase → Frontend API route** (correct path, uses parsed data)
   - **GADM cache JSON → Frontend direct read** (incorrect path, bypasses Python parser)
   - **API response → Frontend component prop** (correct if backend-sourced, incorrect if cache-sourced)

4. **ESA WorldCover Service Unreliability**: The `services.terrascope.be/wmts/v2` endpoint returns HTTP/2 protocol errors intermittently or permanently for certain tile coordinates, but MapLibre's raster layer does not surface these errors to the UI layer

5. **Component Initialization Race Condition**: MapView initializes layers synchronously in `useEffect`, but if admin boundaries are fetched asynchronously after layer initialization, the TargetAreaSelector may receive empty `adminBoundaries` prop before the M_ID error is encountered

## Correctness Properties

Property 1: Bug Condition - GADM Property Mapping Correctness

_For any_ administrative boundary feature loaded from GADM Level 2 GeoJSON where the bug condition holds (application attempts to access `M_ID` property), the fixed code SHALL correctly map GADM properties `GID_2`, `NAME_2`, `GID_1`, `NAME_1` to the `AdminBoundary` interface fields (`boundary_id`, `kecamatan_id`, `kecamatan_name`, `region_id`, `boundary_geojson`), eliminating all `M_ID` property access attempts and allowing all eight filtering components to initialize successfully.

**Validates: Requirements 2.2, 2.3, 2.4**

Property 2: Preservation - Non-Boundary Functionality

_For any_ user interaction or data operation that does NOT involve administrative boundary property access (Coverage Heatmap rendering, BTS candidate selection, RegionSelector race-condition handling, API route responses), the fixed code SHALL produce exactly the same behavior as the original code, preserving all existing functionality for map layer rendering, side panel display, simulation controls, and WebGL fallback.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

---

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct, the fix involves the following specific changes:

**File 1**: `frontend/lib/server/geosignal-service.ts` (or wherever admin boundaries are fetched)

**Function**: `fetchAdminBoundaries(regionId: RegionId): Promise<AdminBoundary[]>`

**Specific Changes**:

1. **Add Region ID Derivation Helper**:
   ```typescript
   function deriveRegionIdFromGADM(gid1: string, name1: string): RegionId {
     const normalized = name1.toLowerCase().replace(/\s/g, '')
     
     // Map GADM NAME_1 to project region_id (reverse of REGION_PROVINCE_FILTERS)
     if (normalized.includes('nusatenggaratimur')) return 'ntt'
     if (normalized.includes('nusatenggarabarat')) return 'ntb'
     if (normalized.includes('kalimantantengah')) return 'central_kalimantan'
     
     // Log error but don't crash — return a fallback
     console.error(`Unknown GADM province: ${name1} (${gid1})`)
     return 'ntt' // fallback to MVP region
   }
   ```

2. **Fix AdminBoundary Mapping in Supabase Query Response**:
   ```typescript
   // OLD (incorrect — assumes M_ID exists):
   const adminBoundaries: AdminBoundary[] = data.map(row => ({
     boundary_id: row.M_ID,        // ❌ M_ID does not exist
     kecamatan_id: row.M_ID,       // ❌ M_ID does not exist
     kecamatan_name: row.NAME,     // ❌ Wrong property name
     region_id: row.REGION,        // ❌ Wrong property name
     boundary_geojson: row.geometry
   }))

   // NEW (correct — uses actual GADM properties):
   const adminBoundaries: AdminBoundary[] = data.map(row => ({
     boundary_id: row.kecamatan_id,      // ✅ Already mapped by Python backend
     kecamatan_id: row.kecamatan_id,     // ✅ GID_2 from Python parse
     kecamatan_name: row.kecamatan_name, // ✅ NAME_2 from Python parse
     region_id: row.region_id,           // ✅ Region ID from Python parse
     boundary_geojson: row.boundary_geojson // ✅ Geometry from Python parse
   }))
   ```

   **Critical Assumption**: The Supabase `admin_boundaries` table already contains correctly parsed data from `backend/geosignal/admin_boundaries.py::parse_gadm_features`. If the table is empty or contains raw GADM fields, the fix must include running `populate_database.py` Task 5.

**File 2**: `frontend/app/api/target-area/route.ts`

**Function**: `POST /api/target-area` handler for kecamatan mode

**Specific Changes**:

3. **Fix Kecamatan Boundary Lookup**:
   ```typescript
   // OLD (incorrect):
   const boundary = await supabase
     .from('admin_boundaries')
     .select('*')
     .eq('M_ID', payload.payload) // ❌ M_ID column does not exist
     .single()

   // NEW (correct):
   const boundary = await supabase
     .from('admin_boundaries')
     .select('*')
     .eq('kecamatan_id', payload.payload) // ✅ Correct column name
     .eq('region_id', payload.region_id)  // ✅ Additional filter for safety
     .single()
   ```

4. **Validate Returned Boundary Structure**:
   ```typescript
   if (boundary.error || !boundary.data) {
     return NextResponse.json(
       { error: `Kecamatan not found: ${payload.payload}` },
       { status: 404 }
     )
   }

   // Ensure boundary_geojson exists before returning
   if (!boundary.data.boundary_geojson) {
     return NextResponse.json(
       { error: `Invalid boundary data for kecamatan ${payload.payload}` },
       { status: 500 }
     )
   }
   ```

**File 3**: `frontend/components/TargetAreaSelector.tsx`

**Function**: `handleKecamatanChange` callback

**Specific Changes**:

5. **Fix Kecamatan Dropdown Key and Preview**:
   ```typescript
   // OLD (incorrect):
   <select ...>
     {adminBoundaries.map((b) => (
       <option key={b.M_ID} value={b.M_ID}>  {/* ❌ M_ID does not exist */}
         {b.NAME}                              {/* ❌ Wrong property name */}
       </option>
     ))}
   </select>

   // NEW (correct):
   <select ...>
     {adminBoundaries.map((b) => (
       <option key={b.kecamatan_id} value={b.kecamatan_id}>  {/* ✅ Correct */}
         {b.kecamatan_name}                                    {/* ✅ Correct */}
       </option>
     ))}
   </select>
   ```

6. **Fix Boundary Preview Lookup**:
   ```typescript
   const handleKecamatanChange = useCallback((kecamatanId: string) => {
     setSelectedKecamatan(kecamatanId)
     // ... existing state resets ...

     // Preview boundary from local adminBoundaries data
     if (!kecamatanId || !map || !map.isStyleLoaded()) return
     
     // OLD (incorrect):
     const boundary = adminBoundaries.find((b) => b.M_ID === kecamatanId) // ❌

     // NEW (correct):
     const boundary = adminBoundaries.find((b) => b.kecamatan_id === kecamatanId) // ✅

     if (boundary?.boundary_geojson) {
       addOrUpdateBoundary(map, boundary.boundary_geojson as Geometry)
       setBoundaryHighlighted(true)
     }
   }, [map, adminBoundaries])
   ```

**File 4**: `frontend/components/MapView.tsx`

**Function**: Land Cover layer initialization in `useEffect`

**Specific Changes**:

7. **Add ESA WorldCover Error Handling**:
   ```typescript
   // Add state for Land Cover layer error
   const [landCoverError, setLandCoverError] = useState<string | null>(null)

   // Wrap layer addition in try-catch
   useEffect(() => {
     const map = mapRef.current
     if (!map || !mapReady) return

     try {
       // Existing Land Cover layer addition code...
       if (!map.getSource(LC_SOURCE)) {
         map.addSource(LC_SOURCE, {
           type: 'raster',
           tiles: [
             'https://services.terrascope.be/wmts/v2?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=WORLDCOVER_2021_MAP&STYLE=default&TILEMATRIXSET=EPSG:3857&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/png',
           ],
           tileSize: 256,
           attribution: 'ESA WorldCover 2021',
         })
       }

       if (!map.getLayer(LC_LAYER)) {
         map.addLayer({
           id: LC_LAYER,
           type: 'raster',
           source: LC_SOURCE,
           layout: { visibility: visibility.landcover ? 'visible' : 'none' },
           paint: { 'raster-opacity': 0.55 },
         })
       }

       // Monitor tile loading errors
       map.on('error', (e) => {
         if (e.error?.message?.includes('terrascope') || 
             e.error?.message?.includes('WorldCover') ||
             e.sourceId === LC_SOURCE) {
           setLandCoverError('Land Cover tiles unavailable (ESA service error)')
           console.warn('ESA WorldCover tile service error:', e.error)
           // Do NOT remove layer — just show warning
         }
       })
     } catch (err) {
       console.error('Failed to initialize Land Cover layer:', err)
       setLandCoverError('Land Cover layer initialization failed')
     }
   }, [mapReady, visibility.landcover])
   ```

8. **Add User-Visible Warning for Land Cover Failure**:
   ```typescript
   // In LayerToggleBar component return:
   <div data-testid="layer-toggle-bar" style={{ ... }}>
     {layers.map(({ key, label }) => (
       <label ... >
         <input ... />
         {label}
         {key === 'landcover' && landCoverError && (
           <span 
             style={{ 
               marginLeft: 4, 
               fontSize: '0.7rem', 
               color: '#dc2626',
               fontWeight: 400 
             }}
             title={landCoverError}
             data-testid="landcover-error-indicator"
           >
             ⚠
           </span>
         )}
       </label>
     ))}
   </div>
   ```

9. **Ensure Proper Component Initialization Order**:
   ```typescript
   // In MapView component — defer TargetAreaSelector until boundaries loaded
   const [boundariesReady, setBoundariesReady] = useState(false)

   useEffect(() => {
     // Fetch admin boundaries on region change
     async function loadBoundaries() {
       setBoundariesReady(false)
       try {
         const boundaries = await fetchAdminBoundaries(activeRegion)
         setAdminBoundaries(boundaries)
         setBoundariesReady(true)
       } catch (err) {
         console.error('Failed to load admin boundaries:', err)
         setAdminBoundaries([])
         setBoundariesReady(true) // Allow component to render with empty state
       }
     }
     loadBoundaries()
   }, [activeRegion])

   // Only render TargetAreaSelector after boundaries are ready
   <TargetAreaSelector
     map={mapRef.current}
     regionId={activeRegion}
     adminBoundaries={boundariesReady ? adminBoundaries : []}
     onResolved={handleTargetAreaResolved}
     onReset={handleTargetAreaReset}
   />
   ```

**File 5**: `backend/geosignal/admin_boundaries.py` (validation only — no changes needed)

**Verification**: Confirm that `parse_gadm_features` already produces correct `AdminBoundary` schema:

```python
# Existing code (already correct):
rows.append({
    "kecamatan_id": str(gid2),           # ✅ Maps GID_2 correctly
    "kecamatan_name": str(name2),        # ✅ Maps NAME_2 correctly
    "region_id": region_id,              # ✅ Uses project region_id
    "boundary_geojson": geometry,        # ✅ Passes geometry through
})
```

**No changes required** — backend is already correct. The bug is exclusively in the frontend.

---

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug BEFORE implementing the fix, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that attempt to access `M_ID` property on GADM features and assert that the property does NOT exist (will pass on unfixed code, demonstrating the bug). Write tests that simulate user interactions with TargetAreaSelector in kecamatan mode and assert that the component renders without TypeErrors (will fail on unfixed code).

**Test Cases**:

1. **GADM Property Structure Test**: Load the cached GADM JSON file (`data/gadm_cache/gadm41_IDN_2.json`), extract a sample feature, assert that `feature.properties.M_ID === undefined`, assert that `feature.properties.GID_2` exists (will pass on unfixed code — demonstrates property mismatch)

2. **AdminBoundary Mapping Test**: Call the frontend function that maps GADM features to `AdminBoundary` objects, pass a real GADM feature, assert that the function throws TypeError when accessing `M_ID` (will pass on unfixed code — demonstrates mapping bug)

3. **TargetAreaSelector Kecamatan Dropdown Test**: Render `<TargetAreaSelector adminBoundaries={mockGADMData} />`, select "Kecamatan" tab, assert that dropdown shows "No kecamatan data available" despite `mockGADMData` being non-empty (will pass on unfixed code — demonstrates UI failure)

4. **ESA WorldCover Tile Error Test**: Initialize MapView, mock MapLibre's `map.on('error')` handler, simulate an ERR_HTTP2_PROTOCOL_ERROR event from the Land Cover layer, assert that no user-visible warning is displayed (will pass on unfixed code — demonstrates silent failure)

**Expected Counterexamples**:
- `M_ID` property access throws TypeError: "Cannot read properties of undefined (reading 'M_ID')"
- Possible causes: frontend bypassing backend's `parse_gadm_features`, frontend accessing raw GADM data, frontend using incorrect property names in UI components

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL gadmFeature WHERE isBugCondition(gadmFeature) DO
  mappedBoundary := mapGADMFeatureToAdminBoundary_fixed(gadmFeature)
  ASSERT mappedBoundary.boundary_id == gadmFeature.properties.GID_2
  ASSERT mappedBoundary.kecamatan_id == gadmFeature.properties.GID_2
  ASSERT mappedBoundary.kecamatan_name == gadmFeature.properties.NAME_2
  ASSERT mappedBoundary.region_id IN ['ntt', 'ntb', 'central_kalimantan']
  ASSERT mappedBoundary.boundary_geojson == gadmFeature.geometry
  ASSERT NO TypeError thrown
END FOR
```

**Test Cases**:

1. **Fixed GADM Mapping Test**: Load real GADM feature for NTT Province kecamatan, call fixed mapping function, assert `AdminBoundary` fields are correctly populated from `GID_2`, `NAME_2`, `GID_1`, `NAME_1` without accessing `M_ID`

2. **Fixed Kecamatan Dropdown Test**: Render `<TargetAreaSelector>` with correctly mapped `adminBoundaries`, select "Kecamatan" tab, assert dropdown displays kecamatan names, select a kecamatan, assert boundary preview renders on map

3. **Fixed Land Cover Error Display Test**: Initialize MapView, simulate ESA WorldCover tile error, assert that Land Cover checkbox displays warning indicator (⚠), assert other layers continue functioning

4. **Fixed Component Initialization Order Test**: Mount MapView, simulate slow admin boundaries fetch, assert TargetAreaSelector does not throw errors while boundaries are loading, assert TargetAreaSelector updates dropdown once boundaries arrive

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL userInteraction WHERE NOT isBugCondition(userInteraction) DO
  ASSERT fixedMapView(userInteraction) = originalMapView(userInteraction)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for non-boundary interactions (heatmap rendering, BTS candidate clicks, region switching, layer toggles), then write property-based tests capturing that behavior and verify it continues after the fix.

**Test Cases**:

1. **Heatmap Rendering Preservation**: Generate random grid cell data with varying coverage scores, render CoverageHeatmap on fixed code, assert cells with score ≥70 display green, 40-69 display yellow, <40 display red (same as unfixed code)

2. **BTS Candidate Selection Preservation**: Render MapView with candidate data on fixed code, simulate candidate marker click, assert SidePanel opens with correct Coverage Score, Confidence Tag, SHAP values (same as unfixed code)

3. **Region Selector Race Condition Preservation**: Simulate rapid region switching on fixed code, assert AbortController cancels stale requests, assert only the latest request's data is applied (same as unfixed code)

4. **WebGL Fallback Preservation**: Render MapView with WebGL disabled on fixed code, assert WebGLFallback component displays with browser recommendations (same as unfixed code)

5. **API Route Response Preservation**: Call `/api/grid-cells`, `/api/recommendations`, `/api/target-area` on fixed code, assert responses match TypeScript interfaces (same as unfixed code)

### Unit Tests

- Test `deriveRegionIdFromGADM` function with all three province names and GID_1 values
- Test AdminBoundary mapping for each of the three MVP regions (NTT, NTB, Central Kalimantan)
- Test TargetAreaSelector kecamatan dropdown key generation and selection handling
- Test MapView Land Cover error handler with simulated tile load failures
- Test component initialization order with mocked async boundary fetch

### Property-Based Tests

- Generate random GADM features (varying GID_2, NAME_2, NAME_1 values) and verify mapping function produces valid AdminBoundary objects
- Generate random user interaction sequences (region changes, layer toggles, target area selections) and verify no TypeErrors occur
- Generate random boundary geometries and verify preview rendering works correctly

### Integration Tests

- Test full user flow: Load application → Select region → Open TargetAreaSelector → Select kecamatan → Confirm target area → Verify boundary highlighted on map
- Test Land Cover error flow: Load application → ESA service fails → Verify warning indicator displays → Verify other layers continue working
- Test component initialization timing: Load application with slow network → Verify components render progressively → Verify no race conditions cause errors
