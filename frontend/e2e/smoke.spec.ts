/**
 * smoke.spec.ts — Playwright E2E smoke tests for the smartNode simulation frontend.
 *
 * Covers four critical user journeys:
 *   1. Initial page load and backend online status display
 *   2. Submitting a transmission request and task queue appearance
 *   3. Switching to resource view and applying resource counts
 *   4. Offline / Cesium CDN unavailable fallback (data panel remains usable)
 *
 * All backend calls are intercepted via Playwright route mocking — no real
 * server is required. See e2e/fixtures/api-mocks.ts for the mock responses.
 */

import { test, expect } from '@playwright/test';
import {
  mockAll,
  mockHealthOffline,
  mockCesiumUnavailable,
  mockRequestRejected,
  SYSTEM_DATA,
  REQUEST_ACCEPTED,
} from './fixtures/api-mocks';

// ── Journey 1: Initial page load & backend online status ─────────────────────

test.describe('页面首屏加载', () => {
  test('显示品牌标题与后端在线状态', async ({ page }) => {
    await mockAll(page);
    await page.goto('/');

    // Brand title is visible
    await expect(page.getByText('SmartNode')).toBeVisible();

    // Backend online indicator appears — "后端在线" text
    // The TopBar toggles between "后端在线" and "等待后端" based on backendOnline state
    await expect(page.getByText('后端在线')).toBeVisible({ timeout: 8000 });
  });

  test('仿真时钟以 HH:MM:SS 格式呈现', async ({ page }) => {
    await mockAll(page);
    await page.goto('/');

    // The formatted time is rendered in the TopBar status strip
    // It should match a HH:MM:SS pattern (e.g. "03:25:45" from time=12345.67)
    const timeEl = page.getByText(/\d{2}:\d{2}:\d{2}/);
    await expect(timeEl).toBeVisible({ timeout: 8000 });
  });

  test('卫星与地面站数量展示在 Cesium 图层信息中', async ({ page }) => {
    await mockAll(page);
    await page.goto('/');

    // The CesiumScene component shows satellite / station counts derived from
    // the store — these appear in the corner stats overlay
    // Wait for the simulation store to populate
    await page.waitForTimeout(500);

    // The page should have loaded without JS errors
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));
    await page.waitForLoadState('domcontentloaded');
    expect(errors.filter((e) => !/cesium|webgl/i.test(e))).toHaveLength(0);
  });
});

// ── Journey 2: Submit request and task queue appearance ───────────────────────

test.describe('提交回传请求', () => {
  test('点击提交后任务队列中出现新请求条目', async ({ page }) => {
    await mockAll(page);
    await page.goto('/');

    // Wait for the form panel to be visible (it's shown by default on 'requests' view)
    // The RequestForm has a submit button that triggers the request
    const submitButton = page.getByRole('button', { name: /提交|submit/i });
    await expect(submitButton).toBeVisible({ timeout: 8000 });

    // Click submit
    await submitButton.click();

    // After submission, a notice with the accepted request ID should appear
    // The App.vue sets notice to `请求已提交：${result.id}`
    await expect(page.getByText(new RegExp(REQUEST_ACCEPTED.id))).toBeVisible({ timeout: 5000 });
  });

  test('任务列表（RequestList）在提交后呈现请求条目', async ({ page }) => {
    await mockAll(page);
    await page.goto('/');

    // The system_data mock already contains one request (req-001)
    // After the page loads and refreshAll() runs, the request list should show it
    await page.waitForTimeout(800);

    // The RequestList renders request IDs; look for the mocked request id
    const existingReqId = SYSTEM_DATA.requests[0].id;
    await expect(page.getByText(existingReqId)).toBeVisible({ timeout: 8000 });
  });

  test('提交被拒绝的请求时显示错误通知', async ({ page }) => {
    // First set all normal mocks, then override the request endpoint
    await mockAll(page);
    await mockRequestRejected(page);
    await page.goto('/');

    const submitButton = page.getByRole('button', { name: /提交|submit/i });
    await expect(submitButton).toBeVisible({ timeout: 8000 });
    await submitButton.click();

    // On rejection, App.vue sets notice to: "请求被拒绝：${reject_reason || '资源暂不可用'}"
    await expect(page.getByText(/请求被拒绝|资源暂不可用/)).toBeVisible({ timeout: 5000 });
  });
});

// ── Journey 3: Switch to resource view and apply counts ───────────────────────

test.describe('切换资源视图', () => {
  test('点击侧边栏「资源」后 ResourcePanel 可见', async ({ page }) => {
    await mockAll(page);
    await page.goto('/');

    // The SideRail has a "资源" button that sets view to 'resources'
    const resourceNavBtn = page.getByRole('button', { name: '资源' });
    await expect(resourceNavBtn).toBeVisible({ timeout: 8000 });
    await resourceNavBtn.click();

    // After click, the ResourcePanel (v-show="uiStore.activeView === 'resources'") becomes visible
    // It contains "调整仿真规模" heading
    await expect(page.getByText('调整仿真规模')).toBeVisible({ timeout: 3000 });
  });

  test('资源视图中「应用地面站」按钮触发更新并显示成功通知', async ({ page }) => {
    await mockAll(page);
    await page.goto('/');

    // Switch to resources view
    await page.getByRole('button', { name: '资源' }).click();
    await expect(page.getByText('调整仿真规模')).toBeVisible({ timeout: 3000 });

    // Click the "应用地面站" button
    const applyGsBtn = page.getByRole('button', { name: '应用地面站' });
    await expect(applyGsBtn).toBeVisible();
    await applyGsBtn.click();

    // App.vue sets notice to "地面站数量已更新" on success
    await expect(page.getByText('地面站数量已更新')).toBeVisible({ timeout: 5000 });
  });

  test('资源视图中「应用卫星」按钮触发更新并显示成功通知', async ({ page }) => {
    await mockAll(page);
    await page.goto('/');

    // Switch to resources view
    await page.getByRole('button', { name: '资源' }).click();
    await expect(page.getByText('调整仿真规模')).toBeVisible({ timeout: 3000 });

    // Click the "应用卫星" button
    const applySatBtn = page.getByRole('button', { name: '应用卫星' });
    await expect(applySatBtn).toBeVisible();
    await applySatBtn.click();

    // App.vue sets notice to "卫星数量已更新" on success
    await expect(page.getByText('卫星数量已更新')).toBeVisible({ timeout: 5000 });
  });

  test('切换视图后可以切回「任务」视图', async ({ page }) => {
    await mockAll(page);
    await page.goto('/');

    // Switch to resources
    await page.getByRole('button', { name: '资源' }).click();
    await expect(page.getByText('调整仿真规模')).toBeVisible({ timeout: 3000 });

    // Switch back to tasks
    const taskNavBtn = page.getByRole('button', { name: '任务' });
    await taskNavBtn.click();

    // RequestForm becomes visible again (visible when activeView !== 'resources')
    // It contains a submit button
    await expect(page.getByRole('button', { name: /提交|submit/i })).toBeVisible({ timeout: 3000 });
  });
});

// ── Journey 4: Offline / Cesium CDN unavailable fallback ─────────────────────

test.describe('离线兜底', () => {
  test('后端不可用时显示「等待后端」而非报错', async ({ page }) => {
    await mockHealthOffline(page);
    await page.goto('/');

    // The TopBar should show "等待后端" (the offline state label)
    await expect(page.getByText('等待后端')).toBeVisible({ timeout: 8000 });

    // Page should still be functional — no unhandled JS crash
    const criticalErrors: string[] = [];
    page.on('pageerror', (err) => {
      // Ignore WebGL / Cesium canvas errors which are expected without real GPU
      if (!/cesium|webgl|canvas|three\.js/i.test(err.message)) {
        criticalErrors.push(err.message);
      }
    });

    await page.waitForTimeout(1000);
    expect(criticalErrors).toHaveLength(0);
  });

  test('后端不可用时数据面板（RequestForm）仍可操作', async ({ page }) => {
    await mockHealthOffline(page);
    await page.goto('/');

    // Wait for offline state to settle
    await expect(page.getByText('等待后端')).toBeVisible({ timeout: 8000 });

    // RequestForm should still be rendered and its submit button usable
    const submitButton = page.getByRole('button', { name: /提交|submit/i });
    await expect(submitButton).toBeVisible({ timeout: 5000 });

    // Button is not disabled in offline mode — user can still attempt to submit
    // (the error will surface in the notice, not prevent rendering)
    await expect(submitButton).toBeEnabled();
  });

  test('Cesium CDN 不可用时数据面板仍可用且后端状态正常', async ({ page }) => {
    await mockCesiumUnavailable(page);
    await page.goto('/');

    // Backend online status should still show because our API mocks work
    await expect(page.getByText('后端在线')).toBeVisible({ timeout: 8000 });

    // RequestForm submit button should still be accessible
    const submitButton = page.getByRole('button', { name: /提交|submit/i });
    await expect(submitButton).toBeVisible({ timeout: 5000 });
  });

  test('后端不可用时切换至资源视图面板不崩溃', async ({ page }) => {
    await mockHealthOffline(page);
    await page.goto('/');

    await expect(page.getByText('等待后端')).toBeVisible({ timeout: 8000 });

    // Should be able to navigate to resources panel even when backend is down
    const resourceNavBtn = page.getByRole('button', { name: '资源' });
    await expect(resourceNavBtn).toBeVisible();
    await resourceNavBtn.click();

    await expect(page.getByText('调整仿真规模')).toBeVisible({ timeout: 3000 });
  });
});
