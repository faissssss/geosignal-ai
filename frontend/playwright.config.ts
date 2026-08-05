/**
 * Playwright configuration — Task 27 E2E tests.
 *
 * Test environment strategy:
 *   - Live tests: require NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY
 *     in the environment. If absent, tests are skipped at runtime via
 *     `test.skip(condition, reason)` inside each test file.
 *   - Hermetic tests (ConfidenceGate, SimulationPanel contract checks) do not
 *     require Supabase and run against the Next.js dev server.
 *
 * Playwright artifacts (playwright-report/, test-results/) are excluded from
 * git via .gitignore. Browser binaries are never committed.
 */

import { defineConfig, devices } from '@playwright/test'

/** True when Supabase credentials are available in the environment. */
export const SUPABASE_AVAILABLE =
  Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL) &&
  Boolean(process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY)

export default defineConfig({
  testDir: './e2e',

  /* Fail fast on first failure in CI */
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,

  workers: 1,

  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],

  use: {
    /* Base URL — Next.js dev server is started by webServer below */
    baseURL: 'http://localhost:3000',

    /* Capture trace on failure only */
    trace: 'on-first-retry',

    /* No video or screenshots on success (large artifacts) */
    screenshot: 'only-on-failure',
    video: 'off',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  /* Start Next.js dev server before running tests.
     `reuseExistingServer: true` prevents double-start if already running. */
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
})
