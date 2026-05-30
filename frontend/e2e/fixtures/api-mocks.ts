/**
 * api-mocks.ts — Playwright route intercept fixtures for smartNode backend APIs.
 *
 * Each exported mock function registers a `page.route()` handler that intercepts
 * requests to a backend API path and returns a deterministic, schema-compatible
 * JSON response without hitting a real server.
 *
 * Usage:
 *   import { mockAll, mockHealthOffline } from './fixtures/api-mocks';
 *   test('...', async ({ page }) => {
 *     await mockAll(page);
 *     await page.goto('/');
 *   });
 */

import type { Page, Route } from '@playwright/test';

// ── Response fixtures ────────────────────────────────────────────────────────

export const HEALTH_ONLINE = {
  status: 'ok',
  time: 12345.67,
};

export const SYSTEM_DATA = {
  time: 12345.67,
  satellites: [
    { id: 'LEO-001', name: 'LEO-001', type: 'LEO', lat: 45.1, lon: 120.3, alt: 550 },
    { id: 'LEO-002', name: 'LEO-002', type: 'LEO', lat: -10.2, lon: 80.5, alt: 560 },
  ],
  ground_stations: [
    {
      id: 'GS-001',
      name: '北京站',
      lat: 39.9,
      lon: 116.4,
      antenna_type: 'parabolic',
      max_links: 4,
    },
    {
      id: 'GS-002',
      name: '上海站',
      lat: 31.2,
      lon: 121.5,
      antenna_type: 'parabolic',
      max_links: 4,
    },
  ],
  geo_relays: [
    { id: 'GEO-001', name: 'GEO-东方', lon: 105.0, bandwidth: 1000 },
  ],
  requests: [
    {
      id: 'req-001',
      data_type: 'DATA_SLICE',
      status: 'accepted',
      priority: 5,
      progress: 50,
      source: 'user',
    },
  ],
  stats: {
    total_requests: 1,
    accepted_requests: 1,
    rejected_requests: 0,
  },
};

export const SYSTEM_INFO = {
  ground_station_count: 2,
  leo_satellite_count: 2,
  data_types: {
    TASK_CMD: { name: '任务指令' },
    INTEL: { name: '情报信息' },
    DATA_SLICE: { name: '数据切片' },
    RAW_IMAGE: { name: '原始影像' },
  },
};

export const RESOURCE_STATUS = {
  summary: {
    satellites_utilization: 42,
    ground_stations_utilization: 35,
    geo_relays_utilization: 18,
    overall_utilization: 32,
  },
};

export const RESOURCE_UTILIZATION = {
  resource_utilization: {
    satellites: 42,
    ground_stations: 35,
    geo_relays: 18,
  },
  total_requests: 1,
  accepted_requests: 1,
  rejected_requests: 0,
};

export const REQUEST_ACCEPTED = {
  id: 'req-new-001',
  status: 'accepted',
  data_type: 'DATA_SLICE',
  priority: 5,
};

export const REQUEST_REJECTED = {
  id: 'req-rej-001',
  status: 'rejected',
  reject_reason: '资源暂不可用',
};

export const UPDATE_GROUND_STATIONS_OK = {
  success: true,
  message: 'Ground stations updated',
};

export const UPDATE_LEO_SATELLITES_OK = {
  success: true,
  message: 'LEO satellites updated',
};

// ── Route registration helpers ───────────────────────────────────────────────

/** Registers all standard mock routes that simulate a healthy backend. */
export async function mockAll(page: Page): Promise<void> {
  await page.route('**/api/health', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(HEALTH_ONLINE) }),
  );
  await page.route('**/api/data', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(SYSTEM_DATA) }),
  );
  await page.route('**/api/system_info', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(SYSTEM_INFO) }),
  );
  await page.route('**/api/resource_status', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RESOURCE_STATUS) }),
  );
  await page.route('**/api/resource_utilization', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RESOURCE_UTILIZATION) }),
  );
  await page.route('**/api/request', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(REQUEST_ACCEPTED) }),
  );
  await page.route('**/api/update_ground_stations', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(UPDATE_GROUND_STATIONS_OK) }),
  );
  await page.route('**/api/update_leo_satellites', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(UPDATE_LEO_SATELLITES_OK) }),
  );
}

/**
 * Registers health endpoint as offline (connection refused) and data endpoints
 * that return empty/fallback payloads — simulates backend unreachable.
 */
export async function mockHealthOffline(page: Page): Promise<void> {
  await page.route('**/api/health', (route: Route) => route.abort('failed'));
  await page.route('**/api/data', (route: Route) => route.abort('failed'));
  await page.route('**/api/system_info', (route: Route) => route.abort('failed'));
  await page.route('**/api/resource_status', (route: Route) => route.abort('failed'));
  await page.route('**/api/resource_utilization', (route: Route) => route.abort('failed'));
}

/**
 * Simulates Cesium JS CDN being unreachable while the backend remains online.
 * Blocks requests to the cesium CDN domains.
 */
export async function mockCesiumUnavailable(page: Page): Promise<void> {
  // First set up all normal backend mocks
  await mockAll(page);
  // Block Cesium CDN resources
  await page.route(/cesium\.com|cesiumjs\.org/, (route: Route) => route.abort('failed'));
}

/**
 * Registers the POST /api/request route to return a rejected response.
 * Use after mockAll() to override just the request endpoint.
 */
export async function mockRequestRejected(page: Page): Promise<void> {
  await page.route('**/api/request', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(REQUEST_REJECTED) }),
  );
}
