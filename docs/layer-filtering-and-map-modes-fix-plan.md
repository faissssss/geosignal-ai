# Layer Filtering, Visualization, and Map Modes Fix Plan

Date: 2026-08-11

## Goal

Fix the frontend map so layer controls behave like a real planning/GIS dashboard:

- Keep the existing checkbox strip for quick overlay visibility.
- Add a separate non-overlapping `Layers` feature button for map modes and visualization modes.
- Make Heatmap, Land Cover, Contours, Villages, BTS Towers, and Candidates visually distinct.
- Make target-area/kecamatan filtering affect every relevant overlay, not only the heatmap.
- Handle known console issues clearly:
  - `nighteye` hydration warning from browser extension.
  - ESA WorldCover tile fetch failures from an unreliable/expired tile service.

This plan intentionally does not replace the current checkbox strip.

## Source references

- `.kiro/specs/nextjs-filtering-features-fix/LAYER_GUIDE.md`
- `.kiro/specs/data-production/plan.md`
- `.kiro/specs/data-production/expected-outcomes.md`
- Current frontend files:
  - `frontend/components/MapView.tsx`
  - `frontend/components/CoverageHeatmap.tsx`
  - `frontend/components/RegionSelector.tsx`
  - `frontend/components/TargetAreaSelector.tsx`
  - `frontend/lib/server/geosignal-service.ts`
  - `frontend/app/api/*`

## Current symptoms

1. Heatmap checkbox appears to make little or no visual difference.
2. BTS Towers, Contours, Villages, and Candidates do not visually behave as expected from `LAYER_GUIDE.md`.
3. Target-area/kecamatan selection does not obviously filter every active layer.
4. Land Cover logs:

   ```text
   ESA WorldCover tile service error: TypeError: Failed to fetch
   ERR_HTTP2_PROTOCOL_ERROR
   ```

5. Dev console logs:

   ```text
   Warning: Extra attributes from the server: nighteye
   ```

6. The app lacks a Google-Maps-style `Layers` button for base map and map display modes.

## Important current-data correction

`LAYER_GUIDE.md` is stale in places. It says some layers have no data, but production validation now reports source-backed layer data:

- Heatmap: 45/45 kecamatan, 125,136 real grid cells.
- Contours: 45/45 kecamatan, 38,226 contour features.
- Villages: 45/45 kecamatan have villages, 14,374 total village features.
- BTS Towers: 3,741 real towers across the three regions.
- Candidates: 23/23 target areas have derived candidates, 230 total candidates.
- Land Cover: 3/3 regions have tile-set records, but browser tile delivery may fail.

The fix should update implementation behavior to match the current production dataset, not the stale “placeholder/no data” statements in the guide.

## Root-cause hypotheses to verify

### 1. Heatmap visibility is technically toggled but visually weak

Likely causes:

- Heatmap fill opacity/color ramp is too subtle against the OSM basemap.
- Cells are too small at current zoom or hidden behind other layers.
- Layer order may put heatmap below stronger boundary/base features.
- The selected kecamatan boundary is visually dominant, making heatmap changes hard to see.
- No legend or mode label tells the user what changed.

### 2. Overlay toggles do not fully match the intended layer semantics

The checkbox strip likely only calls `setLayoutProperty(..., visibility)`.

That is not enough for richer behavior such as:

- BTS tower range rings.
- Candidate rank labels.
- Contour elevation labels.
- Village hover/click state.
- Layer-specific legends.
- Different heatmap modes: thermal, gap, confidence, source/provenance.

### 3. Target-area filtering is incomplete

Current behavior likely filters heatmap cells by `targetArea`, but other layers are only partly filtered:

- Contours and villages use `kecamatan_id` when selected, but only if the selected target area has a `kecamatan_id`.
- BTS towers appear region-scoped, not point-in-selected-boundary.
- Candidates may remain region-wide or target-area dependent depending on the route used.
- Drawn polygon target areas likely do not filter contours/villages/BTS/candidates consistently.

### 4. Land Cover tile source is not frontend-reliable

The database can contain a land-cover tile-set record while the actual browser tile fetch fails.

Likely causes:

- GEE/ESA tile URL expired.
- Tile URL requires auth or session context unavailable to the browser.
- Tile provider returns HTTP/2 protocol failures.
- MapLibre repeatedly retries failed raster tiles.

### 5. `nighteye` warning is external extension mutation

The `nighteye` hydration warning is caused by a browser extension injecting attributes into the HTML before React hydrates.

This is not pipeline or map-layer logic. It can be:

- documented as harmless,
- hidden with `suppressHydrationWarning`,
- or avoided by disabling extensions/incognito testing.

## Product/UX decision

Keep two levels of controls:

### A. Existing checkbox strip: quick overlay on/off

Keep this as-is conceptually:

```text
Heatmap | Land Cover | Contours | Villages | BTS Towers | Candidates
```

Purpose:

- Fast overlay visibility.
- No mode switching.
- No replacement by the new Layers button.

### B. New `Layers` feature button: advanced map modes

Add a compact button that opens a non-overlapping panel.

Purpose:

- Base map selection.
- Visualization mode selection.
- Opacity/legend/display options.
- Optional advanced overlays such as BTS range rings.

## Proposed `Layers` button behavior

### Placement

Do not overlap the existing checkbox strip or the right-side simulation panels.

Preferred layout:

- Keep current top-left control stack:
  - Region selector
  - Checkbox strip
  - Target Area selector
- Place `Layers` button below the Target Area section inside the same left control stack.
- The panel opens downward within the left control area.
- Use max width and max height with scroll.

Fallback responsive behavior:

- On narrow screens, the `Layers` panel stays under the button and scrolls internally.
- Never open the panel over the right-side Simulation / Drag-and-Drop / Power panels.
- Keep `z-index` below modal dialogs, above map layers.

### Panel content

```text
Layers

Base map
  ○ Default
  ○ Satellite
  ○ Terrain

Coverage visualization
  ○ Coverage thermal
  ○ Coverage gaps
  ○ Confidence
  ○ Source/provenance

Advanced overlays
  □ BTS range rings
  □ Candidate rank labels
  □ Contour elevation labels
  □ Village labels
  □ Selected-area mask

Display
  Heatmap opacity slider
  Land-cover opacity slider
  Show legend
```

## Proposed state model

Keep existing `LayerVisibility`:

```ts
interface LayerVisibility {
  heatmap: boolean
  landcover: boolean
  contours: boolean
  villages: boolean
  btsMarkers: boolean
  candidates: boolean
}
```

Add new display state:

```ts
type BaseMapMode = 'default' | 'satellite' | 'terrain'

type CoverageVisualizationMode =
  | 'thermal'
  | 'gap'
  | 'confidence'
  | 'source'

interface AdvancedLayerOptions {
  btsRangeRings: boolean
  candidateRankLabels: boolean
  contourElevationLabels: boolean
  villageLabels: boolean
  selectedAreaMask: boolean
  showLegend: boolean
  heatmapOpacity: number
  landCoverOpacity: number
}
```

## Implementation phases

### Phase 1 — Audit actual layer behavior

Files to inspect:

- `frontend/components/MapView.tsx`
- `frontend/components/CoverageHeatmap.tsx`
- `frontend/lib/heatmap.ts`
- `frontend/lib/validation/filterCellsByTargetArea.ts`
- `frontend/lib/server/geosignal-service.ts`
- API routes under `frontend/app/api/`

Audit checklist:

- Confirm each MapLibre source/layer ID.
- Confirm each checkbox maps to the correct source/layer IDs.
- Confirm layer order matches `LAYER_GUIDE.md`:
  1. Base map
  2. Heatmap
  3. Land Cover
  4. Contours
  5. Villages
  6. BTS Towers
  7. Candidates
- Confirm toggling changes visible map output, not only React state.
- Confirm target-area selection updates every layer’s dataset or client-side filter.
- Confirm source data arrays contain expected row counts after API fetch.

Deliverable:

- Short audit note added to this plan or a follow-up implementation note.

### Phase 2 — Fix Heatmap visual difference

Required behavior:

- Heatmap ON/OFF must be visually obvious.
- Thermal mode should use clear red/yellow/green cells.
- Gaps mode should emphasize only poor coverage cells.
- Confidence mode should encode High/Med/Low.
- Source mode should distinguish real/derived/demo/unavailable if exposed.

Implementation tasks:

- Review `CoverageHeatmap.tsx` layer paint properties.
- Increase default opacity or add opacity slider.
- Ensure heatmap layer is above base map and below markers.
- Add a small legend when heatmap is visible.
- If selected kecamatan exists, either:
  - show only filtered cells, or
  - dim outside-area cells and highlight selected boundary.

Acceptance:

- Toggling Heatmap off removes colored cells.
- Toggling Heatmap on restores colored cells.
- Switching thermal/gap/confidence visibly changes style.

### Phase 3 — Fix layer-specific rendering

#### Contours

Desired style:

- Brown/orange contour lines.
- More visible than current lines.
- Optional elevation labels in advanced mode.
- Hover/click can show elevation metadata.

Tasks:

- Strengthen line color/width.
- Keep below markers but above land-cover.
- Add optional label layer using `symbol` if feasible.

#### Villages

Desired style:

- Yellow/orange polygons.
- Visible but not overpowering.
- Optional labels.
- Hover/click metadata later.

Tasks:

- Increase fill opacity slightly when toggled on.
- Add clear orange outline.
- Ensure village layer sits above contours or as specified by final design.

#### BTS Towers

Desired style:

- Blue/purple circles with white stroke.
- Cluster mode or density mode for high-count regions.
- Optional range rings in `Layers` advanced panel.

Tasks:

- Make BTS markers larger/clearer.
- Add `bts-range-source` and `bts-range-layer` for approximate rings.
- Decide initial range assumption, e.g. 2 km / 5 km / 10 km, clearly labeled as approximate.
- Do not imply exact RF propagation unless backed by data.

#### Candidates

Desired style:

- Orange markers, larger than BTS towers.
- Optional rank labels.
- Click opens side panel.

Tasks:

- Add rank label layer.
- Ensure candidates are above BTS towers.
- Ensure candidate marker click still works after style/layer changes.

### Phase 4 — Fix target-area filtering across all overlays

Filtering rules from production spec:

- Heatmap: cell centroid within selected boundary.
- BTS towers: point within selected boundary.
- Candidates: point within selected boundary or matching target area.
- Contours: geometry intersects selected boundary.
- Villages: geometry intersects selected boundary.
- Land Cover: region tile set remains region-scoped unless stable per-boundary tiles exist; visually mask/dim outside selected area if needed.

Implementation options:

#### Option A — Server-side filtering where possible

Best for large layers:

- Add or use `kecamatan_id` query param for contours/villages.
- Add `kecamatan_id` or boundary-based filtering for BTS/candidates.
- For drawn polygon, add API support for boundary geometry filtering if needed.

#### Option B — Client-side filtering for currently loaded region data

Acceptable for smaller layers:

- BTS towers: point-in-polygon in browser.
- Candidates: point-in-polygon in browser.
- Heatmap already does this.

Concern:

- Avoid heavy geometry filtering for 38k contours in browser.

Recommended:

- Server-side for contours/villages when `kecamatan_id` exists.
- Client-side for BTS/candidates initially.
- Drawn polygon filtering for contours/villages can be later server-side enhancement.

Acceptance:

- Selecting Alor changes visible heatmap cells.
- Selecting Alor changes BTS/candidate visibility.
- Contours/villages are scoped to Alor when kecamatan selection is used.
- Region switching resets target area and clears stale layers.

### Phase 5 — Add `LayersButton` component

New file:

- `frontend/components/LayersButton.tsx`

Props:

```ts
interface LayersButtonProps {
  baseMapMode: BaseMapMode
  onBaseMapModeChange: (mode: BaseMapMode) => void
  coverageMode: CoverageVisualizationMode
  onCoverageModeChange: (mode: CoverageVisualizationMode) => void
  options: AdvancedLayerOptions
  onOptionsChange: (options: AdvancedLayerOptions) => void
}
```

Placement:

- Render under `TargetAreaSelector` in `MapView.tsx`.
- Do not remove `LayerToggleBar`.

Accessibility:

- Button has `aria-expanded`.
- Panel has `role="dialog"` or `role="region"` with label.
- Escape closes panel.
- Click outside closes panel if simple to implement.

Acceptance:

- `Layers` button opens/closes panel.
- Panel does not overlap right-side planning panels.
- Existing checkbox strip remains usable.

### Phase 6 — Add base map switching

Base map modes:

1. Default
   - Current OSM raster tiles.
2. Satellite
   - Needs a valid provider decision.
   - Avoid hardcoding commercial providers without key/license.
3. Terrain
   - Can use OSM terrain-style tiles if license permits, or a configurable env URL.

Implementation recommendation:

- Define base map source configs in one module:

  ```ts
  frontend/lib/map/baseMaps.ts
  ```

- Support env-configurable tile URLs:

  ```text
  NEXT_PUBLIC_BASEMAP_DEFAULT_URL
  NEXT_PUBLIC_BASEMAP_SATELLITE_URL
  NEXT_PUBLIC_BASEMAP_TERRAIN_URL
  ```

- If satellite/terrain URL is missing, show disabled option with tooltip:

  ```text
  Satellite unavailable: configure tile URL
  ```

Acceptance:

- Switching base map visibly changes tiles when URLs are configured.
- Missing providers do not break the app.

### Phase 7 — Land Cover reliability fix

Short-term:

- Keep Land Cover checkbox.
- Detect raster tile errors.
- Show warning state in UI.
- Stop pretending the layer is usable when tile fetch fails.
- Add clear message:

  ```text
  Land Cover tile service unavailable. Other layers still work.
  ```

Medium-term:

- Replace volatile ESA/GEE browser tile URL with stable hosted tiles:
  - Supabase Storage XYZ tiles,
  - Cloudflare R2,
  - static MBTiles converted to XYZ,
  - or a backend tile proxy that refreshes GEE map IDs.

Implementation tasks:

- Listen to MapLibre `error` events for `LC_SOURCE`.
- Set `landCoverError` only for land-cover source failures.
- Optionally disable/hide Land Cover layer after repeated failures.
- Add retry/refresh action in `Layers` panel if feasible.

Acceptance:

- Failed Land Cover tile requests do not spam console indefinitely.
- User sees clear unavailable state.
- Other overlays continue to work.

### Phase 8 — Console warning policy

#### `nighteye`

Cause:

- Browser extension mutates HTML attributes.

Plan:

- Add `suppressHydrationWarning` to `<html>` or `<body>` if warning remains annoying.
- Document that extension should be disabled for clean debugging.

Acceptance:

- App behavior unaffected.
- Warning does not distract from real layer errors.

#### Chrome-extension `M_ID` error

Cause:

- External extension script expecting `M_ID`.

Plan:

- Keep or refine the narrow error guard if needed.
- Do not suppress app-origin `M_ID` errors.
- Ensure source filter is limited to `chrome-extension://`.

Acceptance:

- Extension-origin `M_ID` does not crash Next dev overlay.
- App-origin errors still surface.

## Test plan

### Unit/component tests

Add tests for:

- `LayersButton` open/close.
- Base map mode state.
- Visualization mode state.
- Heatmap opacity option.
- Existing checkbox strip still renders and works.
- No overlap layout class/positioning snapshot or style assertion.

### Map behavior tests

Add or update tests for:

- Heatmap OFF means heatmap layers are hidden.
- Heatmap ON means heatmap layers are visible.
- Coverage mode changes paint properties.
- BTS Towers toggle changes BTS layer visibility.
- Candidates toggle changes candidate layer visibility.
- BTS range rings only visible when advanced option is on.
- Target area filters BTS/candidates.

### API/data tests

Verify:

- `/api/grid-cells?region_id=ntt&resolution_m=100`
- `/api/contours?region_id=ntt&kecamatan_id=...`
- `/api/villages?region_id=ntt&kecamatan_id=...`
- `/api/bts-locations?region_id=ntt`
- `POST /api/recommendations`

### Browser/E2E tests

Scenarios:

1. Load app with default controls.
2. Open `Layers` button; verify panel does not cover right-side panel.
3. Toggle Heatmap off/on; verify visible map style changes.
4. Switch coverage mode thermal/gap/confidence; verify style changes.
5. Toggle BTS Towers; verify marker layer visibility.
6. Enable BTS range rings; verify ring layer appears.
7. Toggle Contours and Villages; verify visible style changes.
8. Select kecamatan; verify active overlays update/filter.
9. Switch region; verify target area resets and no stale layer data remains.
10. Confirm no app-origin runtime errors.

## Acceptance criteria

The fix is complete when:

- Existing checkbox strip remains present and usable.
- New `Layers` button exists and does not overlap current UI panels.
- Heatmap toggling creates a clear visual difference.
- Thermal/gap/confidence modes are visually distinct.
- BTS towers, contours, villages, and candidates have clear visual styles.
- BTS range mode exists as an advanced visualization option.
- Selected kecamatan filters all relevant overlays.
- Land Cover failure is communicated as unavailable, not silently broken.
- `nighteye` warning is either suppressed or documented as extension-only.
- Production build passes.
- Frontend unit tests pass.
- Playwright browser tests pass.

## Open decisions before implementation

1. Satellite/terrain tile providers:
   - Which tile provider is approved?
   - Are API keys available?
   - Should URLs be env-configured?

2. BTS range ring assumptions:
   - What default radius should be shown?
   - Should rings be fixed-radius visual aids or data-backed LOS/coverage estimates?

3. Drawn polygon filtering:
   - Is client-side filtering acceptable for BTS/candidates only?
   - Should contours/villages support drawn-polygon server-side intersection in this iteration?

4. Land Cover stable hosting:
   - Should we proxy/refresh GEE tiles?
   - Or generate static hosted tiles during data production?

## Recommended first implementation slice

Start with the smallest user-visible improvement:

1. Add `LayersButton` below the existing target-area controls.
2. Add heatmap opacity + thermal/gap/confidence mode.
3. Strengthen heatmap, BTS, contour, village, and candidate styling.
4. Add BTS range rings as optional advanced overlay.
5. Make BTS/candidate filtering respect selected kecamatan boundary.
6. Improve Land Cover unavailable handling.

This gives immediate visual improvement without replacing the current checkbox strip.
