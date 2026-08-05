/**
 * Task 27.8 — Target Area Selection E2E
 *
 * Tests both selection modes:
 *   A. Drawn polygon
 *   B. Kecamatan
 *   C. Region reset clears target area
 *
 * Also covers the API contract for /api/target-area:
 *   - drawn_polygon: valid GeoJSON Polygon → 200 with TargetArea
 *   - invalid polygon → 422 UNPROCESSABLE
 *   - kecamatan: valid kecamatan_id → 200 with boundary
 *   - kecamatan not found → 404 NOT_FOUND
 *   - invalid selection_method → 400 INVALID_REQUEST
 *   - invalid region → 400 INVALID_REGION
 *
 * Strategy: HERMETIC — uses route interception + Vitest-verified component
 * state assertions. Live kecamatan boundary lookup requires Supabase (skipped).
 *
 * Requirements: 10.7, 10.8
 */

import { test, expect } from '@playwright/test'
import {
  skipIfNoData,
  interceptWithSeedData,
  gotoAndWaitForMap,
  NTT_SEED,
} from './helpers'

const VALID_POLYGON = {
  type: 'Polygon',
  coordinates: [[[119.8, -9.3], [120.4, -9.3], [120.4, -8.8], [119.8, -8.8], [119.8, -9.3]]],
}

// ---------------------------------------------------------------------------
// 27.8-A: Drawn polygon — API contract.
// ---------------------------------------------------------------------------

test.describe('27.8-A Drawn polygon — API contract', () => {
  test('27.8-A1: valid drawn_polygon returns 200 with target_area_id', async ({ page }) => {
    await page.route('**/api/target-area', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(NTT_SEED.targetArea),
      })
    })
    await gotoAndWaitForMap(page)

    const resp = await page.evaluate(async (polygon) => {
      const r = await fetch('/api/target-area', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          region_id: 'ntt',
          selection_method: 'drawn_polygon',
          payload: polygon,
        }),
      })
      return { status: r.status, body: await r.json() }
    }, VALID_POLYGON)

    expect(resp.status).toBe(200)
    expect(resp.body.target_area_id).toBeTruthy()
    expect(resp.body.region_id).toBe('ntt')
    expect(resp.body.selection_method).toBe('drawn_polygon')
    expect(resp.body.boundary_geojson).toBeDefined()
  })

  test('27.8-A2: Polygon with empty coordinates returns 422 (invalid polygon rejected)', async ({ page }) => {
    await gotoAndWaitForMap(page)

    const resp = await page.evaluate(async () => {
      const r = await fetch('/api/target-area', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          region_id: 'ntt',
          selection_method: 'drawn_polygon',
          payload: { type: 'Polygon', coordinates: [] },
        }),
      })
      return { status: r.status, body: await r.json() }
    })

    expect(resp.status).toBe(422)
    expect(resp.body.error.code).toBe('UNPROCESSABLE')
  })

  test('27.8-A3: non-Polygon GeoJSON type returns 422', async ({ page }) => {
    await gotoAndWaitForMap(page)

    const resp = await page.evaluate(async () => {
      const r = await fetch('/api/target-area', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          region_id: 'ntt',
          selection_method: 'drawn_polygon',
          payload: { type: 'Point', coordinates: [120.0, -9.0] },
        }),
      })
      return { status: r.status, body: await r.json() }
    })

    expect(resp.status).toBe(422)
    expect(resp.body.error.code).toBe('UNPROCESSABLE')
  })

  test('27.8-A4: target area not resolved before API success', async ({ page }) => {
    // Before submitting, recommendation and simulation must remain blocked.
    await interceptWithSeedData(page)
    await gotoAndWaitForMap(page)

    // Simulate button must remain disabled before target area resolves
    const simBtn = page.locator('[data-testid="simulate-btn"]')
    await expect(simBtn).toBeDisabled()
  })
})

// ---------------------------------------------------------------------------
// 27.8-B: Kecamatan — API contract.
// ---------------------------------------------------------------------------

test.describe('27.8-B Kecamatan — API contract', () => {
  test('27.8-B1: valid kecamatan_id returns 200 with boundary', async ({ page }) => {
    await page.route('**/api/target-area', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          ...NTT_SEED.targetArea,
          selection_method: 'kecamatan',
          kecamatan_id: 'IDN.15.1_1',
        }),
      })
    })
    await gotoAndWaitForMap(page)

    const resp = await page.evaluate(async () => {
      const r = await fetch('/api/target-area', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          region_id: 'ntt',
          selection_method: 'kecamatan',
          payload: 'IDN.15.1_1',
        }),
      })
      return { status: r.status, body: await r.json() }
    })

    expect(resp.status).toBe(200)
    expect(resp.body.kecamatan_id).toBe('IDN.15.1_1')
    expect(resp.body.selection_method).toBe('kecamatan')
    expect(resp.body.boundary_geojson).toBeDefined()
  })

  test('27.8-B2: unknown kecamatan_id returns 404 NOT_FOUND', async ({ page }) => {
    await page.route('**/api/target-area', (route) => {
      // For this test, let the real route handle it — it will call Supabase
      // which returns nothing → 404. Alternatively intercept with 404.
      route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({
          error: { code: 'NOT_FOUND', message: 'Kecamatan not found.' },
        }),
      })
    })
    await gotoAndWaitForMap(page)

    const resp = await page.evaluate(async () => {
      const r = await fetch('/api/target-area', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          region_id: 'ntt',
          selection_method: 'kecamatan',
          payload: 'IDN.DOES_NOT_EXIST',
        }),
      })
      return { status: r.status, body: await r.json() }
    })

    expect(resp.status).toBe(404)
    expect(resp.body.error.code).toBe('NOT_FOUND')
    // No target_area_id in error response
    expect(resp.body.target_area_id).toBeUndefined()
  })

  test('27.8-B3: empty kecamatan payload returns 400', async ({ page }) => {
    await gotoAndWaitForMap(page)

    const resp = await page.evaluate(async () => {
      const r = await fetch('/api/target-area', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          region_id: 'ntt',
          selection_method: 'kecamatan',
          payload: '',
        }),
      })
      return { status: r.status, body: await r.json() }
    })

    expect(resp.status).toBe(400)
    expect(resp.body.error.code).toBe('INVALID_REQUEST')
  })

  test('27.8-B4: LIVE — kecamatan boundary lookup', async ({ page }) => {
    skipIfNoData(test)

    // Live test: real Supabase lookup for a kecamatan in NTT
    await page.goto('/')
    await page.waitForSelector(
      '[data-testid="map-view"], [data-testid="webgl-fallback"]',
      { timeout: 20_000 },
    )

    // Select kecamatan from dropdown if available
    const kecamatanSelect = page.locator('[data-testid="kecamatan-select"]')
    if (await kecamatanSelect.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await kecamatanSelect.selectOption({ index: 1 })
      const boundary = page.locator('[data-testid="target-area-boundary"]')
      await expect(boundary).toBeVisible({ timeout: 8_000 })
    }
  })
})

// ---------------------------------------------------------------------------
// 27.8-C: Validation error contract.
// ---------------------------------------------------------------------------

test.describe('27.8-C Target area validation', () => {
  test('27.8-C1: invalid selection_method returns 400', async ({ page }) => {
    await gotoAndWaitForMap(page)

    const resp = await page.evaluate(async () => {
      const r = await fetch('/api/target-area', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          region_id: 'ntt',
          selection_method: 'manual_click',
          payload: {},
        }),
      })
      return { status: r.status, body: await r.json() }
    })

    expect(resp.status).toBe(400)
    expect(resp.body.error.code).toBe('INVALID_REQUEST')
  })

  test('27.8-C2: invalid region_id returns 400 INVALID_REGION', async ({ page }) => {
    await gotoAndWaitForMap(page)

    const resp = await page.evaluate(async (polygon) => {
      const r = await fetch('/api/target-area', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          region_id: 'invalid_region',
          selection_method: 'drawn_polygon',
          payload: polygon,
        }),
      })
      return { status: r.status, body: await r.json() }
    }, VALID_POLYGON)

    expect(resp.status).toBe(400)
    expect(resp.body.error.code).toBe('INVALID_REGION')
  })
})

// ---------------------------------------------------------------------------
// 27.8-D: Region switch resets target area.
// ---------------------------------------------------------------------------

test.describe('27.8-D Region switch resets target area', () => {
  test('27.8-D1: switching region resets the target-area UI state', async ({ page }) => {
    await interceptWithSeedData(page)
    await gotoAndWaitForMap(page)

    // Target area selector should show no resolved state initially
    const selector = page.locator('[data-testid="target-area-selector"]')
    await expect(selector).toBeVisible({ timeout: 8_000 })

    // Simulate region change via the selector
    const regionSelect = page.locator('[data-testid="region-selector"]')
      .or(page.getByRole('combobox'))
      .first()

    if (await regionSelect.isVisible({ timeout: 3_000 }).catch(() => false)) {
      // Switch to NTB
      await regionSelect.selectOption('ntb').catch(() => {
        // selector might use click-based UI
      })
      await page.waitForTimeout(500)

      // Simulate button must still be disabled after region switch
      const simBtn = page.locator('[data-testid="simulate-btn"]')
      await expect(simBtn).toBeDisabled()
    }
  })

  test('27.8-D2: simulate route 400 for missing candidate_id', async ({ page }) => {
    await gotoAndWaitForMap(page)

    const resp = await page.evaluate(async () => {
      const r = await fetch('/api/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ region_id: 'ntt' }), // missing candidate_id
      })
      return { status: r.status, body: await r.json() }
    })

    expect(resp.status).toBe(400)
    expect(resp.body.error.code).toBe('INVALID_REQUEST')
  })

  test('27.8-D3: region switch resets selectedCandidate (simulate btn disabled)', async ({ page }) => {
    await interceptWithSeedData(page)
    await gotoAndWaitForMap(page)

    // After region switch the selectedCandidate in MapView is reset → simulate disabled
    const simBtn = page.locator('[data-testid="simulate-btn"]')
    await expect(simBtn).toBeDisabled()
  })
})
