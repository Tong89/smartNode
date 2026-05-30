/**
 * format.test.ts — Unit tests for pure formatting utilities.
 *
 * Covers: formatTime, formatProgress, labelDataType, labelStatus, labelLinkMode.
 * No DOM, no network — pure function tests only.
 */

import { describe, it, expect } from 'vitest';
import {
  formatTime,
  formatProgress,
  labelDataType,
  labelStatus,
  labelLinkMode,
  DATA_TYPE_LABELS,
  STATUS_LABELS,
  LINK_MODE_LABELS,
} from './format';

// ── formatTime ────────────────────────────────────────────────────────────────

describe('formatTime', () => {
  it('formats zero as 00:00:00', () => {
    expect(formatTime(0)).toBe('00:00:00');
  });

  it('formats 3661 seconds as 01:01:01', () => {
    expect(formatTime(3661)).toBe('01:01:01');
  });

  it('pads single-digit hours, minutes, and seconds', () => {
    expect(formatTime(3600 + 60 + 5)).toBe('01:01:05');
  });

  it('truncates fractional seconds', () => {
    expect(formatTime(59.9)).toBe('00:00:59');
  });

  it('clamps negative values to 00:00:00', () => {
    expect(formatTime(-10)).toBe('00:00:00');
  });

  it('handles NaN as 00:00:00', () => {
    expect(formatTime(NaN)).toBe('00:00:00');
  });

  it('handles Infinity as 00:00:00', () => {
    expect(formatTime(Infinity)).toBe('00:00:00');
  });

  it('formats 86399 seconds as 23:59:59', () => {
    expect(formatTime(86399)).toBe('23:59:59');
  });

  it('handles hours beyond 24 correctly', () => {
    expect(formatTime(86400)).toBe('24:00:00');
  });
});

// ── formatProgress ────────────────────────────────────────────────────────────

describe('formatProgress', () => {
  it('formats 0 as 0%', () => {
    expect(formatProgress(0)).toBe('0%');
  });

  it('formats 100 as 100%', () => {
    expect(formatProgress(100)).toBe('100%');
  });

  it('formats 50 as 50%', () => {
    expect(formatProgress(50)).toBe('50%');
  });

  it('formats 75.6 as 76% (rounds half-up)', () => {
    expect(formatProgress(75.6)).toBe('76%');
  });

  it('clamps values below 0 to 0%', () => {
    expect(formatProgress(-5)).toBe('0%');
  });

  it('clamps values above 100 to 100%', () => {
    expect(formatProgress(150)).toBe('100%');
  });

  it('handles undefined as 0%', () => {
    expect(formatProgress(undefined)).toBe('0%');
  });

  it('handles null as 0%', () => {
    expect(formatProgress(null)).toBe('0%');
  });

  it('handles NaN as 0%', () => {
    expect(formatProgress(NaN)).toBe('0%');
  });
});

// ── labelDataType ─────────────────────────────────────────────────────────────

describe('labelDataType', () => {
  it.each(Object.entries(DATA_TYPE_LABELS))('maps %s → %s', (key, label) => {
    expect(labelDataType(key)).toBe(label);
  });

  it('returns the raw key for unknown types', () => {
    expect(labelDataType('UNKNOWN_TYPE')).toBe('UNKNOWN_TYPE');
  });

  it('returns 未知 for empty string', () => {
    expect(labelDataType('')).toBe('未知');
  });

  it('returns 未知 for undefined', () => {
    expect(labelDataType(undefined)).toBe('未知');
  });

  it('returns 未知 for null', () => {
    expect(labelDataType(null)).toBe('未知');
  });
});

// ── labelStatus ───────────────────────────────────────────────────────────────

describe('labelStatus', () => {
  it.each(Object.entries(STATUS_LABELS))('maps %s → %s', (key, label) => {
    expect(labelStatus(key)).toBe(label);
  });

  it('returns the raw status for unknown values', () => {
    expect(labelStatus('expired')).toBe('expired');
  });

  it('returns 未知 for empty string', () => {
    expect(labelStatus('')).toBe('未知');
  });

  it('returns 未知 for undefined', () => {
    expect(labelStatus(undefined)).toBe('未知');
  });

  it('returns 未知 for null', () => {
    expect(labelStatus(null)).toBe('未知');
  });
});

// ── labelLinkMode ─────────────────────────────────────────────────────────────

describe('labelLinkMode', () => {
  it.each(Object.entries(LINK_MODE_LABELS))('maps %s → %s', (key, label) => {
    expect(labelLinkMode(key)).toBe(label);
  });

  it('returns - for unknown transmission method', () => {
    expect(labelLinkMode('quantum')).toBe('-');
  });

  it('returns - for empty string', () => {
    expect(labelLinkMode('')).toBe('-');
  });

  it('returns - for undefined', () => {
    expect(labelLinkMode(undefined)).toBe('-');
  });

  it('returns - for null', () => {
    expect(labelLinkMode(null)).toBe('-');
  });
});
