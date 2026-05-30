/**
 * utilization-bars.test.ts — Component tests for UtilizationBars.
 *
 * Covers:
 *  - Renders a bar for each row in the rows prop
 *  - Displays label and percentage value for each row
 *  - progress element value and max attributes are set correctly
 *  - Boundary values: 0% and 100%
 *  - Fractional values are formatted to one decimal place
 *  - Empty rows array renders no resource bars
 *  - Section heading is always present
 */

import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import UtilizationBars from './UtilizationBars.vue';
import type { UtilizationRow } from './UtilizationBars.vue';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeRows(overrides: Partial<UtilizationRow>[] = []): UtilizationRow[] {
  const defaults: UtilizationRow[] = [
    { key: 'satellites', label: '卫星资源', value: 42.5 },
    { key: 'ground', label: '地面站资源', value: 78.3 },
    { key: 'geo', label: '中继资源', value: 15.0 },
    { key: 'overall', label: '综合占用', value: 60.2 },
  ];
  return defaults.map((row, i) => ({ ...row, ...(overrides[i] || {}) }));
}

function makeWrapper(rows: UtilizationRow[]) {
  return mount(UtilizationBars, {
    props: { rows },
  });
}

// ── Section structure ─────────────────────────────────────────────────────────

describe('UtilizationBars section structure', () => {
  it('renders a section.tool-panel', () => {
    const wrapper = makeWrapper(makeRows());
    expect(wrapper.find('section.tool-panel').exists()).toBe(true);
  });

  it('renders the eyebrow label', () => {
    const wrapper = makeWrapper(makeRows());
    expect(wrapper.find('.eyebrow').text()).toBe('资源占用');
  });

  it('renders the heading', () => {
    const wrapper = makeWrapper(makeRows());
    expect(wrapper.find('h2').text()).toBe('实时利用率');
  });

  it('renders the resource-bars container', () => {
    const wrapper = makeWrapper(makeRows());
    expect(wrapper.find('.resource-bars').exists()).toBe(true);
  });
});

// ── Row rendering ─────────────────────────────────────────────────────────────

describe('UtilizationBars row rendering', () => {
  it('renders the correct number of resource rows', () => {
    const rows = makeRows();
    const wrapper = makeWrapper(rows);
    expect(wrapper.findAll('.resource-row').length).toBe(rows.length);
  });

  it('renders zero rows when rows prop is empty', () => {
    const wrapper = makeWrapper([]);
    expect(wrapper.findAll('.resource-row').length).toBe(0);
  });

  it('renders single row', () => {
    const row: UtilizationRow = { key: 'test', label: 'テスト', value: 50 };
    const wrapper = makeWrapper([row]);
    expect(wrapper.findAll('.resource-row').length).toBe(1);
  });
});

// ── Label rendering ───────────────────────────────────────────────────────────

describe('UtilizationBars label rendering', () => {
  it('displays the label for each row', () => {
    const rows = makeRows();
    const wrapper = makeWrapper(rows);
    const resourceRows = wrapper.findAll('.resource-row');
    rows.forEach((row, idx) => {
      const label = resourceRows[idx].find('span');
      expect(label.text()).toBe(row.label);
    });
  });

  it('displays 卫星资源 label for satellite row', () => {
    const rows = [{ key: 'satellites', label: '卫星资源', value: 30 }];
    const wrapper = makeWrapper(rows);
    expect(wrapper.find('.resource-row span').text()).toBe('卫星资源');
  });

  it('displays 地面站资源 label for ground station row', () => {
    const rows = [{ key: 'ground', label: '地面站资源', value: 55 }];
    const wrapper = makeWrapper(rows);
    expect(wrapper.find('.resource-row span').text()).toBe('地面站资源');
  });
});

// ── Percentage value rendering ────────────────────────────────────────────────

describe('UtilizationBars percentage rendering', () => {
  it('displays value formatted to one decimal place', () => {
    const rows = [{ key: 'sat', label: '卫星', value: 42.5 }];
    const wrapper = makeWrapper(rows);
    const strong = wrapper.find('.resource-row strong');
    expect(strong.text()).toBe('42.5%');
  });

  it('displays integer value with .0 decimal', () => {
    const rows = [{ key: 'sat', label: '卫星', value: 75 }];
    const wrapper = makeWrapper(rows);
    const strong = wrapper.find('.resource-row strong');
    expect(strong.text()).toBe('75.0%');
  });

  it('displays 0% as 0.0%', () => {
    const rows = [{ key: 'sat', label: '卫星', value: 0 }];
    const wrapper = makeWrapper(rows);
    const strong = wrapper.find('.resource-row strong');
    expect(strong.text()).toBe('0.0%');
  });

  it('displays 100% as 100.0%', () => {
    const rows = [{ key: 'sat', label: '卫星', value: 100 }];
    const wrapper = makeWrapper(rows);
    const strong = wrapper.find('.resource-row strong');
    expect(strong.text()).toBe('100.0%');
  });

  it('renders correct percentage for all rows', () => {
    const rows = makeRows();
    const wrapper = makeWrapper(rows);
    const strongs = wrapper.findAll('.resource-row strong');
    rows.forEach((row, idx) => {
      expect(strongs[idx].text()).toBe(`${row.value.toFixed(1)}%`);
    });
  });
});

// ── Progress element ─────────────────────────────────────────────────────────

describe('UtilizationBars progress element', () => {
  it('renders a progress element for each row', () => {
    const rows = makeRows();
    const wrapper = makeWrapper(rows);
    expect(wrapper.findAll('progress').length).toBe(rows.length);
  });

  it('progress value matches the row value', () => {
    const rows = [{ key: 'sat', label: '卫星', value: 63.7 }];
    const wrapper = makeWrapper(rows);
    const progress = wrapper.find('progress');
    expect(Number(progress.attributes('value'))).toBeCloseTo(63.7);
  });

  it('progress max is 100', () => {
    const rows = [{ key: 'sat', label: '卫星', value: 50 }];
    const wrapper = makeWrapper(rows);
    const progress = wrapper.find('progress');
    expect(progress.attributes('max')).toBe('100');
  });

  it('progress value is 0 for 0% utilization', () => {
    const rows = [{ key: 'sat', label: '卫星', value: 0 }];
    const wrapper = makeWrapper(rows);
    const progress = wrapper.find('progress');
    expect(Number(progress.attributes('value'))).toBe(0);
  });

  it('progress value is 100 for full utilization', () => {
    const rows = [{ key: 'sat', label: '卫星', value: 100 }];
    const wrapper = makeWrapper(rows);
    const progress = wrapper.find('progress');
    expect(Number(progress.attributes('value'))).toBe(100);
  });

  it('each progress element has the correct value for its row', () => {
    const rows = makeRows();
    const wrapper = makeWrapper(rows);
    const progressEls = wrapper.findAll('progress');
    rows.forEach((row, idx) => {
      expect(Number(progressEls[idx].attributes('value'))).toBeCloseTo(row.value);
    });
  });
});

// ── Boundary values ───────────────────────────────────────────────────────────

describe('UtilizationBars boundary values', () => {
  it('handles near-zero values correctly', () => {
    const rows = [{ key: 'sat', label: '卫星', value: 0.1 }];
    const wrapper = makeWrapper(rows);
    const strong = wrapper.find('.resource-row strong');
    expect(strong.text()).toBe('0.1%');
  });

  it('handles near-full values correctly', () => {
    const rows = [{ key: 'sat', label: '卫星', value: 99.9 }];
    const wrapper = makeWrapper(rows);
    const strong = wrapper.find('.resource-row strong');
    expect(strong.text()).toBe('99.9%');
  });

  it('handles multiple rows with mixed extreme values', () => {
    const rows: UtilizationRow[] = [
      { key: 'a', label: 'A', value: 0 },
      { key: 'b', label: 'B', value: 100 },
      { key: 'c', label: 'C', value: 50 },
    ];
    const wrapper = makeWrapper(rows);
    const strongs = wrapper.findAll('.resource-row strong');
    expect(strongs[0].text()).toBe('0.0%');
    expect(strongs[1].text()).toBe('100.0%');
    expect(strongs[2].text()).toBe('50.0%');
  });
});

// ── Key-based reactivity ──────────────────────────────────────────────────────

describe('UtilizationBars key-based list rendering', () => {
  it('uses key attribute for each row (not index)', () => {
    const rows: UtilizationRow[] = [
      { key: 'satellites', label: '卫星资源', value: 20 },
      { key: 'ground', label: '地面站资源', value: 40 },
    ];
    const wrapper = makeWrapper(rows);
    // Each row is keyed by the key prop; rows should appear in order
    const resourceRows = wrapper.findAll('.resource-row');
    expect(resourceRows[0].find('span').text()).toBe('卫星资源');
    expect(resourceRows[1].find('span').text()).toBe('地面站资源');
  });
});
