/**
 * Shared helpers for Task 27 Playwright E2E tests.
 *
 * LIVE vs HERMETIC tests
 * ──────────────────────
 * LIVE tests interact with the real Next.js app and require:
 *   - Supabase project with data (grid_cells, bts_candidates, etc.)
 *   - NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY set
 *
 * HERMETIC tests test component logic and API contracts using the real
 * app but with mocked API routes (via route interception) — they do not
 * require seeded Supabase data.
 *
 * All live tests call `skipIfNoData(test)` at the top. Hermetic tests
 * proceed regardless of Supabase availability.
 */

import type { Page, Route } from '@playwright/test'
import { test } from '@playwright/test'

// ---------------------------------------------------------------------------
// Environment check
// ---------------------------------------------------------------------------

export const SUPABASE_CONFIGURED =
  Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL) &&
  Boolean(process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY)

/**
 * Skip a live test when Supabase is not provisioned.
 * Usage: skipIfNoData(test) at the top of a live test.
 */
export function skipIfNoData(t: typeof test): void {
  t.skip(
    !SUPABASE_CONFIGURED,
    'BLOCKED: Supabase not provisioned — NEXT_PUBLIC_SUPABASE_URL and ' +
    'NEXT_PUBLIC_SUPABASE_ANON_KEY must be set for live E2E tests.',
  )
}
// ---------------------------------------------------------------------------
// Deterministic NTT seed fixture
// (used in hermetic tests that intercept API routes)
// ---------------------------------------------------------------------------

export const NTT_SEED = {
  cells: [
    {
      cell_id: 'e2e-c1', region_id: 'ntt', lat: -9.1, lon: 120.1,
      resolution_m: 100, coverage_score: 64.5, confidence_tag: 'Med',
      shap_top3: [
        { feature_name: 'Distance to nearest BTS tower', value: 0.22, direction: 'positive' },
        { feature_name: 'Distance to nearest facility', value: 0.20, direction: 'positive' },
        { feature_name: 'Population density', value: 0.18, direction: 'positive' },
      ],
      model_version: 'ahp-v2.0',
      scoring_run_id: 'run-e2e-001',
    },
  ],
  candidates: [
    {
      candidate_id: 'cand-e2e-01', region_id: 'ntt', target_area_id: 'ta-e2e',
      rank: 1, lat: -9.15, lon: 120.15, expected_improvement: 14.0,
      los_validated: true, confidence_tag: 'High',
      shap_values: {
        elevation_m: 0.10, slope_deg: -0.05, canopy_height_m: 0.08,
        land_cover_class: 0.03, distance_to_bts_m: 0.22,
        road_distance_m: 0.10, population_density_per_km2: 0.18,
        facility_proximity_m: 0.21,
      },
      model_version: 'ahp-v2.0',
      scoring_run_id: 'run-e2e-001',
      excluded_by_canopy: false,
    },
    {
      candidate_id: 'cand-e2e-02', region_id: 'ntt', target_area_id: 'ta-e2e',
      rank: 2, lat: -9.20, lon: 120.20, expected_improvement: 10.0,
      los_validated: true, confidence_tag: 'Low',
      shap_values: {
        elevation_m: 0.05, slope_deg: -0.03, canopy_height_m: 0.04,
        land_cover_class: 0.02, distance_to_bts_m: 0.12,
        road_distance_m: 0.06, population_density_per_km2: 0.09,
        facility_proximity_m: 0.11,
      },
      model_version: 'ahp-v2.0',
      scoring_run_id: 'run-e2e-001',
      excluded_by_canopy: false,
    },
  ],
  targetArea: {
    target_area_id: 'ta-e2e',
    region_id: 'ntt',
    selection_method: 'drawn_polygon',
    kecamatan_id: null,
    boundary_geojson: {
      type: 'Polygon',
      coordinates: [[[119.8, -9.3], [120.4, -9.3], [120.4, -8.8], [119.8, -8.8], [119.8, -9.3]]],
    },
    created_at: '2026-01-01T00:00:00Z',
  },
  simResult: {
    before_heatmap: { region_id: 'ntt', cells: [], snapshot_label: 'before' },
    after_heatmap:  { region_id: 'ntt', cells: [], snapshot_label: 'after' },
    pct_good_change: 12.5,
    villages_newly_covered: 3,
    new_coverage_score: 74.2,
    elapsed_ms: 450,
  },
}

// ---------------------------------------------------------------------------
// Route interception helpers
// ---------------------------------------------------------------------------

/** Intercept all Task 25 API routes and serve NTT seed data. */
export async function interceptWithSeedData(page: Page): Promise<void> {
  await page.route('**/api/grid-cells**', (route: Route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(NTT_SEED.cells),
    })
  })

  await page.route('**/api/recommendations', (route: Route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(NTT_SEED.candidates),
    })
  })

  await page.route('**/api/target-area', (route: Route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(NTT_SEED.targetArea),
    })
  })

  await page.route('**/api/simulate', (route: Route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(NTT_SEED.simResult),
    })
  })

  await page.route('**/api/drag-drop', (route: Route) => {
    // Default: service unavailable (Python bridge not wired)
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({
        error: { code: 'SERVICE_UNAVAILABLE', message: 'Python bridge not wired.' },
      }),
    })
  })
}

/** Navigate to the app and wait for the map container to be visible. */
export async function gotoAndWaitForMap(page: Page): Promise<void> {
  await page.goto('/')
  // Map container or WebGL fallback must appear — both are valid
  await page.waitForSelector(
    '[data-testid="map-view"], [data-testid="webgl-fallback"], [data-testid="map-loading"]',
    { timeout: 15_000 },
  )
}
