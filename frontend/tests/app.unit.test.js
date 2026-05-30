/**
 * app.unit.test.js — Vitest unit tests for pure-logic helpers extracted from app.js.
 *
 * Tests cover:
 *   - formatProgress   : progress value → "N%" string (clamping, rounding)
 *   - formatTime       : seconds → "HH:MM:SS" string (edge cases, truncation)
 *   - utilizationRows  : resource status summary → label/value row array
 *   - requestsSort     : request list sorting & background-task filtering
 *   - DATA_TYPE_LABELS : data-type key → Chinese label
 *   - STATUS_LABELS    : status key → Chinese label
 *
 * All helpers are extracted from app.js as standalone pure functions so that
 * they can be tested without a browser, Vue instance, or running server.
 *
 * Run:  npx vitest run tests/app.unit.test.js
 */

import { describe, it, expect } from 'vitest';

// ── Pure helpers replicated from app.js for testability ──────────────────────
// These mirror the inline methods/constants in app.js exactly.

const DATA_TYPE_LABELS = {
  TASK_CMD: '任务指令',
  INTEL: '情报信息',
  DATA_SLICE: '数据切片',
  RAW_IMAGE: '原始影像',
};

const STATUS_LABELS = {
  pending: '排队',
  accepted: '等待',
  transmitting: '传输',
  completed: '完成',
  rejected: '拒绝',
};

/**
 * Format transmission progress (0–100) to a percentage string.
 * Mirrors app.js `methods.formatProgress`.
 */
function formatProgress(progress) {
  const value = Number(progress || 0);
  return `${Math.max(0, Math.min(100, value)).toFixed(0)}%`;
}

/**
 * Format simulation seconds to "HH:MM:SS".
 * Mirrors app.js `methods.formatTime`.
 */
function formatTime(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds || 0)));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return [hours, minutes, secs].map((part) => String(part).padStart(2, '0')).join(':');
}

/**
 * Build utilization row array from resource_status.summary.
 * Mirrors app.js `computed.utilizationRows`.
 */
function utilizationRows(resourceStatus) {
  const summary = (resourceStatus || {}).summary || {};
  return [
    { key: 'satellites', label: '卫星资源', value: Number(summary.satellites_utilization || 0) },
    { key: 'ground', label: '地面站资源', value: Number(summary.ground_stations_utilization || 0) },
    { key: 'geo', label: '中继资源', value: Number(summary.geo_relays_utilization || 0) },
    { key: 'overall', label: '综合占用', value: Number(summary.overall_utilization || 0) },
  ];
}

/**
 * Filter and sort requests: exclude background tasks, sort descending by id.
 * Mirrors app.js `computed.requests`.
 */
function processRequests(rawRequests) {
  const rows = Array.isArray(rawRequests) ? rawRequests : [];
  return rows
    .filter((req) => req.source !== 'background')
    .slice()
    .sort((a, b) => String(b.id || '').localeCompare(String(a.id || '')));
}

/**
 * Transmission method → display string.
 * Mirrors the inline ternary in the request-list template (app.js).
 */
function formatLinkMode(req) {
  if (!req || !req.transmission_method) return '-';
  if (req.transmission_method === 'direct') return '直连';
  if (req.transmission_method === 'relay') return '中继';
  if (req.transmission_method === 'multi_relay') return '多跳';
  return '-';
}

// ── DATA_TYPE_LABELS ──────────────────────────────────────────────────────────

describe('DATA_TYPE_LABELS', () => {
  it('maps TASK_CMD to 任务指令', () => {
    expect(DATA_TYPE_LABELS['TASK_CMD']).toBe('任务指令');
  });

  it('maps INTEL to 情报信息', () => {
    expect(DATA_TYPE_LABELS['INTEL']).toBe('情报信息');
  });

  it('maps DATA_SLICE to 数据切片', () => {
    expect(DATA_TYPE_LABELS['DATA_SLICE']).toBe('数据切片');
  });

  it('maps RAW_IMAGE to 原始影像', () => {
    expect(DATA_TYPE_LABELS['RAW_IMAGE']).toBe('原始影像');
  });

  it('returns undefined for unknown keys', () => {
    expect(DATA_TYPE_LABELS['UNKNOWN']).toBeUndefined();
  });
});

// ── STATUS_LABELS ─────────────────────────────────────────────��───────────────

describe('STATUS_LABELS', () => {
  it('maps pending to 排队', () => {
    expect(STATUS_LABELS['pending']).toBe('排队');
  });

  it('maps accepted to 等待', () => {
    expect(STATUS_LABELS['accepted']).toBe('等待');
  });

  it('maps transmitting to 传输', () => {
    expect(STATUS_LABELS['transmitting']).toBe('传输');
  });

  it('maps completed to 完成', () => {
    expect(STATUS_LABELS['completed']).toBe('完成');
  });

  it('maps rejected to 拒绝', () => {
    expect(STATUS_LABELS['rejected']).toBe('拒绝');
  });
});

// ── formatProgress ────────────────────────────────────────────────────────────

describe('formatProgress', () => {
  it('returns "0%" for 0', () => {
    expect(formatProgress(0)).toBe('0%');
  });

  it('returns "100%" for 100', () => {
    expect(formatProgress(100)).toBe('100%');
  });

  it('returns "50%" for 50', () => {
    expect(formatProgress(50)).toBe('50%');
  });

  it('clamps values above 100 to 100%', () => {
    expect(formatProgress(150)).toBe('100%');
  });

  it('clamps negative values to 0%', () => {
    expect(formatProgress(-10)).toBe('0%');
  });

  it('rounds fractional values', () => {
    expect(formatProgress(75.6)).toBe('76%');
    expect(formatProgress(75.4)).toBe('75%');
  });

  it('handles undefined/null/falsy as 0%', () => {
    expect(formatProgress(undefined)).toBe('0%');
    expect(formatProgress(null)).toBe('0%');
    expect(formatProgress('')).toBe('0%');
  });

  it('handles string numbers', () => {
    expect(formatProgress('42')).toBe('42%');
  });
});

// ── formatTime ────────────────────────────────────────────────────────────────

describe('formatTime', () => {
  it('returns "00:00:00" for 0', () => {
    expect(formatTime(0)).toBe('00:00:00');
  });

  it('formats 3661 seconds as 01:01:01', () => {
    expect(formatTime(3661)).toBe('01:01:01');
  });

  it('pads single-digit components', () => {
    expect(formatTime(3600 + 60 + 5)).toBe('01:01:05');
  });

  it('truncates fractional seconds', () => {
    expect(formatTime(59.9)).toBe('00:00:59');
  });

  it('clamps negative values to 00:00:00', () => {
    expect(formatTime(-5)).toBe('00:00:00');
  });

  it('handles null/undefined as 00:00:00', () => {
    expect(formatTime(null)).toBe('00:00:00');
    expect(formatTime(undefined)).toBe('00:00:00');
  });

  it('formats exactly one hour as 01:00:00', () => {
    expect(formatTime(3600)).toBe('01:00:00');
  });

  it('formats 86399 seconds as 23:59:59', () => {
    expect(formatTime(86399)).toBe('23:59:59');
  });

  it('correctly derives hours from large second counts', () => {
    // 12345.67 seconds = 3h 25m 45s (truncated)
    expect(formatTime(12345.67)).toBe('03:25:45');
  });
});

// ── utilizationRows ───────────────────────────────────────────────────────────

describe('utilizationRows', () => {
  const mockStatus = {
    summary: {
      satellites_utilization: 42,
      ground_stations_utilization: 35,
      geo_relays_utilization: 18,
      overall_utilization: 32,
    },
  };

  it('returns exactly 4 rows', () => {
    expect(utilizationRows(mockStatus)).toHaveLength(4);
  });

  it('maps satellites_utilization correctly', () => {
    const rows = utilizationRows(mockStatus);
    const satRow = rows.find((r) => r.key === 'satellites');
    expect(satRow).toBeDefined();
    expect(satRow.label).toBe('卫星资源');
    expect(satRow.value).toBe(42);
  });

  it('maps ground_stations_utilization correctly', () => {
    const rows = utilizationRows(mockStatus);
    const gsRow = rows.find((r) => r.key === 'ground');
    expect(gsRow).toBeDefined();
    expect(gsRow.label).toBe('地面站资源');
    expect(gsRow.value).toBe(35);
  });

  it('maps geo_relays_utilization correctly', () => {
    const rows = utilizationRows(mockStatus);
    const geoRow = rows.find((r) => r.key === 'geo');
    expect(geoRow).toBeDefined();
    expect(geoRow.label).toBe('中继资源');
    expect(geoRow.value).toBe(18);
  });

  it('maps overall_utilization correctly', () => {
    const rows = utilizationRows(mockStatus);
    const overallRow = rows.find((r) => r.key === 'overall');
    expect(overallRow).toBeDefined();
    expect(overallRow.label).toBe('综合占用');
    expect(overallRow.value).toBe(32);
  });

  it('defaults to 0 for missing summary fields', () => {
    const rows = utilizationRows({ summary: {} });
    rows.forEach((r) => expect(r.value).toBe(0));
  });

  it('handles null/undefined resourceStatus gracefully', () => {
    expect(() => utilizationRows(null)).not.toThrow();
    expect(() => utilizationRows(undefined)).not.toThrow();
    const rows = utilizationRows(null);
    rows.forEach((r) => expect(r.value).toBe(0));
  });
});

// ── processRequests ───────────────────────────────────────────────────────────

describe('processRequests (filtering & sorting)', () => {
  const requests = [
    { id: 'req-003', source: 'user', status: 'pending' },
    { id: 'req-001', source: 'background', status: 'completed' },
    { id: 'req-002', source: 'user', status: 'transmitting' },
    { id: 'req-005', source: 'user', status: 'accepted' },
  ];

  it('filters out background-source requests', () => {
    const result = processRequests(requests);
    expect(result.every((r) => r.source !== 'background')).toBe(true);
  });

  it('includes all non-background requests', () => {
    const result = processRequests(requests);
    expect(result).toHaveLength(3);
  });

  it('sorts by id descending (lexicographic)', () => {
    const result = processRequests(requests);
    const ids = result.map((r) => r.id);
    expect(ids).toEqual(['req-005', 'req-003', 'req-002']);
  });

  it('handles empty array', () => {
    expect(processRequests([])).toEqual([]);
  });

  it('handles non-array input gracefully', () => {
    expect(processRequests(null)).toEqual([]);
    expect(processRequests(undefined)).toEqual([]);
  });

  it('does not mutate the original array', () => {
    const original = [
      { id: 'req-002', source: 'user' },
      { id: 'req-001', source: 'user' },
    ];
    const copy = [...original];
    processRequests(original);
    expect(original).toEqual(copy);
  });
});

// ── formatLinkMode ────────────────────────────────────────────────────────────

describe('formatLinkMode', () => {
  it('returns 直连 for direct', () => {
    expect(formatLinkMode({ transmission_method: 'direct' })).toBe('直连');
  });

  it('returns 中继 for relay', () => {
    expect(formatLinkMode({ transmission_method: 'relay' })).toBe('中继');
  });

  it('returns 多跳 for multi_relay', () => {
    expect(formatLinkMode({ transmission_method: 'multi_relay' })).toBe('多跳');
  });

  it('returns - for unknown method', () => {
    expect(formatLinkMode({ transmission_method: 'quantum' })).toBe('-');
  });

  it('returns - when transmission_method is absent', () => {
    expect(formatLinkMode({})).toBe('-');
    expect(formatLinkMode(null)).toBe('-');
    expect(formatLinkMode(undefined)).toBe('-');
  });
});
