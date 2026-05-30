/**
 * playwright.config.ts — Playwright E2E test configuration for smartNode frontend.
 *
 * Covers smoke tests for the critical user journeys:
 *   - Initial page load & backend status display
 *   - Submitting a transmission request and queue appearance
 *   - Switching to the resource view and applying counts
 *   - Offline/Cesium CDN unavailable fallback
 *
 * Run locally:  npx playwright test
 * Run in CI:    npx playwright test --ci
 */

import { defineConfig, devices } from '@playwright/test';

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:5173';

export default defineConfig({
  // Test directory
  testDir: './e2e',

  // Run all tests in parallel
  fullyParallel: true,

  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,

  // Retry on CI only
  retries: process.env.CI ? 2 : 0,

  // Number of workers: 1 on CI to avoid flakiness, auto on local
  workers: process.env.CI ? 1 : undefined,

  // Reporter
  reporter: process.env.CI
    ? [['github'], ['html', { outputFolder: 'playwright-report', open: 'never' }]]
    : [['list'], ['html', { outputFolder: 'playwright-report', open: 'on-failure' }]],

  use: {
    // Base URL for page.goto('/')
    baseURL: BASE_URL,

    // Collect trace on first retry
    trace: 'on-first-retry',

    // Screenshot on failure
    screenshot: 'only-on-failure',

    // Reasonable action timeout
    actionTimeout: 10_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // Run Firefox in CI for broader coverage
    ...(process.env.CI
      ? [
          {
            name: 'firefox',
            use: { ...devices['Desktop Firefox'] },
          },
        ]
      : []),
  ],

  // Launch the dev server if not running in CI (CI should start its own server)
  webServer: process.env.CI
    ? undefined
    : {
        command: 'npm run dev',
        url: BASE_URL,
        reuseExistingServer: !process.env.CI,
        timeout: 30_000,
      },
});
