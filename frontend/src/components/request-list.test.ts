/**
 * request-list.test.ts — Component tests for RequestList.
 *
 * Covers:
 *  - Empty state: shows 暂无任务请求 when requests array is empty
 *  - Row rendering: correct data for each request row
 *  - Status pill: correct CSS class and label per status value
 *  - Data type labels: all known keys map to Chinese labels
 *  - Link mode labels: direct / relay / multi_relay / unknown
 *  - Progress formatting: percentage display with clamping
 */

import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import RequestList from './RequestList.vue';
import type { TransmissionRequest } from '../types/api';

// ── Helpers ───────────────────────────────────────────────────────────────────

type RequestWithExtras = TransmissionRequest & { transmission_method?: string };

function makeRequest(overrides: Partial<RequestWithExtras> = {}): RequestWithExtras {
  return {
    id: 'REQ-001',
    data_type: 'INTEL',
    status: 'pending',
    priority: 5,
    progress: 0,
    source: 'user',
    ...overrides,
  };
}

function makeWrapper(requests: RequestWithExtras[]) {
  return mount(RequestList, {
    props: { requests },
  });
}

// ── Empty state ───────────────────────────────────────────────────────────────

describe('RequestList empty state', () => {
  it('shows empty-state text when requests is empty', () => {
    const wrapper = makeWrapper([]);
    const empty = wrapper.find('.empty-state');
    expect(empty.exists()).toBe(true);
    expect(empty.text()).toBe('暂无任务请求');
  });

  it('does not render any data rows when requests is empty', () => {
    const wrapper = makeWrapper([]);
    // Only header row plus empty state — no request-row items with data
    const rows = wrapper.findAll('.request-row:not(.head)');
    // Empty state div is not a .request-row, only the v-for rows are
    expect(rows.filter((r) => !r.classes('head')).length).toBe(0);
  });

  it('renders the section with correct structure', () => {
    const wrapper = makeWrapper([]);
    expect(wrapper.find('section.request-list').exists()).toBe(true);
    expect(wrapper.find('.request-table').exists()).toBe(true);
    expect(wrapper.find('.request-row.head').exists()).toBe(true);
  });

  it('renders column headers', () => {
    const wrapper = makeWrapper([]);
    const head = wrapper.find('.request-row.head');
    const headers = head.findAll('span');
    expect(headers.map((h) => h.text())).toEqual(['编号', '类型', '状态', '链路', '进度']);
  });
});

// ── Row rendering ─────────────────────────────────────────────────────────────

describe('RequestList row rendering', () => {
  it('renders one row per request', () => {
    const requests = [
      makeRequest({ id: 'REQ-001' }),
      makeRequest({ id: 'REQ-002' }),
      makeRequest({ id: 'REQ-003' }),
    ];
    const wrapper = makeWrapper(requests);
    const rows = wrapper.findAll('.request-row:not(.head)');
    expect(rows.length).toBe(3);
  });

  it('displays request id in first column', () => {
    const wrapper = makeWrapper([makeRequest({ id: 'REQ-042' })]);
    const row = wrapper.find('.request-row:not(.head)');
    const cells = row.findAll('span');
    expect(cells.at(0)?.text()).toBe('REQ-042');
  });

  it('displays data type label in second column', () => {
    const wrapper = makeWrapper([makeRequest({ data_type: 'INTEL' })]);
    const row = wrapper.find('.request-row:not(.head)');
    const cells = row.findAll('span');
    expect(cells.at(1)?.text()).toBe('情报信息');
  });

  it('does not show empty-state when requests is non-empty', () => {
    const wrapper = makeWrapper([makeRequest()]);
    expect(wrapper.find('.empty-state').exists()).toBe(false);
  });
});

// ── Status pill rendering ─────────────────────────────────────────────────────

describe('RequestList status pill', () => {
  const statusCases: Array<[TransmissionRequest['status'], string]> = [
    ['pending', '排队'],
    ['accepted', '等待'],
    ['transmitting', '传输'],
    ['completed', '完成'],
    ['rejected', '拒绝'],
  ];

  it.each(statusCases)('status %s renders label %s', (status, label) => {
    const wrapper = makeWrapper([makeRequest({ status })]);
    const pill = wrapper.find('.status-pill');
    expect(pill.text()).toBe(label);
  });

  it.each(statusCases)('status %s gets CSS class %s on pill', (status) => {
    const wrapper = makeWrapper([makeRequest({ status })]);
    const pill = wrapper.find('.status-pill');
    expect(pill.classes()).toContain(status);
  });

  it('unknown status shows raw value', () => {
    const req = makeRequest({ status: 'expired' as TransmissionRequest['status'] });
    const wrapper = makeWrapper([req]);
    const pill = wrapper.find('.status-pill');
    expect(pill.text()).toBe('expired');
  });
});

// ── Data type labels ──────────────────────────────────────────────────────────

describe('RequestList data type labels', () => {
  const typeCases: Array<[string, string]> = [
    ['TASK_CMD', '任务指令'],
    ['INTEL', '情报信息'],
    ['DATA_SLICE', '数据切片'],
    ['RAW_IMAGE', '原始影像'],
  ];

  it.each(typeCases)('data_type %s renders as %s', (dataType, label) => {
    const wrapper = makeWrapper([makeRequest({ data_type: dataType })]);
    const row = wrapper.find('.request-row:not(.head)');
    const cells = row.findAll('span');
    expect(cells.at(1)?.text()).toBe(label);
  });

  it('unknown data_type shows raw key', () => {
    const wrapper = makeWrapper([makeRequest({ data_type: 'CUSTOM_TYPE' })]);
    const row = wrapper.find('.request-row:not(.head)');
    const cells = row.findAll('span');
    expect(cells.at(1)?.text()).toBe('CUSTOM_TYPE');
  });
});

// ── Link mode labels ──────────────────────────────────────────────────────────

describe('RequestList link mode labels', () => {
  const linkCases: Array<[string | undefined, string]> = [
    ['direct', '直连'],
    ['relay', '中继'],
    ['multi_relay', '多跳'],
    [undefined, '-'],
    ['quantum', '-'],
    ['', '-'],
  ];

  it.each(linkCases)('transmission_method %s renders as %s', (method, label) => {
    const req = makeRequest({ transmission_method: method });
    const wrapper = makeWrapper([req]);
    const row = wrapper.find('.request-row:not(.head)');
    const cells = row.findAll('span');
    expect(cells.at(3)?.text()).toBe(label);
  });
});

// ── Progress formatting ───────────────────────────────────────────────────────

describe('RequestList progress formatting', () => {
  it('formats 0 as 0%', () => {
    const wrapper = makeWrapper([makeRequest({ progress: 0 })]);
    const row = wrapper.find('.request-row:not(.head)');
    const cells = row.findAll('span');
    expect(cells.at(4)?.text()).toBe('0%');
  });

  it('formats 100 as 100%', () => {
    const wrapper = makeWrapper([makeRequest({ progress: 100 })]);
    const row = wrapper.find('.request-row:not(.head)');
    const cells = row.findAll('span');
    expect(cells.at(4)?.text()).toBe('100%');
  });

  it('formats 57.4 as 57%', () => {
    const wrapper = makeWrapper([makeRequest({ progress: 57.4 })]);
    const row = wrapper.find('.request-row:not(.head)');
    const cells = row.findAll('span');
    expect(cells.at(4)?.text()).toBe('57%');
  });

  it('clamps negative progress to 0%', () => {
    const wrapper = makeWrapper([makeRequest({ progress: -10 })]);
    const row = wrapper.find('.request-row:not(.head)');
    const cells = row.findAll('span');
    expect(cells.at(4)?.text()).toBe('0%');
  });

  it('clamps progress above 100 to 100%', () => {
    const wrapper = makeWrapper([makeRequest({ progress: 150 })]);
    const row = wrapper.find('.request-row:not(.head)');
    const cells = row.findAll('span');
    expect(cells.at(4)?.text()).toBe('100%');
  });

  it('handles undefined progress as 0%', () => {
    const req = makeRequest();
    delete (req as Partial<RequestWithExtras>).progress;
    const wrapper = makeWrapper([req]);
    const row = wrapper.find('.request-row:not(.head)');
    const cells = row.findAll('span');
    expect(cells.at(4)?.text()).toBe('0%');
  });
});

// ── Multiple requests ordering ────────────────────────────────────────────────

describe('RequestList multiple requests', () => {
  it('renders all requests in provided order', () => {
    const requests = [
      makeRequest({ id: 'REQ-001', status: 'completed' }),
      makeRequest({ id: 'REQ-002', status: 'transmitting' }),
      makeRequest({ id: 'REQ-003', status: 'pending' }),
    ];
    const wrapper = makeWrapper(requests);
    const rows = wrapper.findAll('.request-row:not(.head)');
    expect(rows.length).toBe(3);
    expect(rows.at(0)?.find('span').text()).toBe('REQ-001');
    expect(rows.at(1)?.find('span').text()).toBe('REQ-002');
    expect(rows.at(2)?.find('span').text()).toBe('REQ-003');
  });

  it('renders correct status pill for each row', () => {
    const requests = [
      makeRequest({ id: 'REQ-001', status: 'completed' }),
      makeRequest({ id: 'REQ-002', status: 'rejected' }),
    ];
    const wrapper = makeWrapper(requests);
    const pills = wrapper.findAll('.status-pill');
    expect(pills.at(0)?.text()).toBe('完成');
    expect(pills.at(1)?.text()).toBe('拒绝');
  });
});
