/**
 * simulation.ts — Pinia store for simulation state management.
 *
 * Centralises systemData, systemInfo, resourceStatus, utilization, and
 * backendOnline status previously scattered across App.vue component data.
 * Provides configurable polling via startPolling / stopPolling.
 */
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { SystemData, Satellite, GroundStation, GeoRelay, TransmissionRequest } from '../types/api';

/** Default polling interval in milliseconds */
const DEFAULT_POLL_INTERVAL = 2000;

const DATA_TYPE_LABELS: Record<string, string> = {
  TASK_CMD: '任务指令',
  INTEL: '情报信息',
  DATA_SLICE: '数据切片',
  RAW_IMAGE: '原始影像',
};

function resolveApiBase(): string {
  const params = new URLSearchParams(window.location.search);
  const configured = params.get('api') || localStorage.getItem('space_api_base');
  if (configured) {
    return configured.replace(/\/$/, '');
  }
  if (
    window.location.protocol === 'file:' ||
    (window.location.port && window.location.port !== '5000')
  ) {
    return 'http://127.0.0.1:5000';
  }
  return '';
}

export const useSimulationStore = defineStore('simulation', () => {
  // ── State ──────────────────────────────────────────────────────────────────
  const apiBase = ref(resolveApiBase());
  const backendOnline = ref(false);
  const refreshing = ref(false);
  const pollInterval = ref(DEFAULT_POLL_INTERVAL);

  const systemData = ref<SystemData>({
    time: 0,
    satellites: [],
    ground_stations: [],
    geo_relays: [],
    requests: [],
    stats: {},
  });

  const systemInfo = ref<Record<string, unknown>>({});
  const resourceStatus = ref<Record<string, unknown>>({});
  const utilization = ref<Record<string, unknown>>({});

  let pollingTimer: ReturnType<typeof window.setInterval> | null = null;

  // ── Getters ────────────────────────────────────────────────────────────────
  const systemTime = computed(() => Number(systemData.value.time || 0));

  const formattedTime = computed(() => {
    const total = Math.max(0, Math.floor(systemTime.value));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    return [hours, minutes, secs].map((p) => String(p).padStart(2, '0')).join(':');
  });

  const stats = computed(() => systemData.value.stats || {});

  const satellites = computed<Satellite[]>(() =>
    Array.isArray(systemData.value.satellites) ? systemData.value.satellites : [],
  );

  const leoSatellites = computed<Satellite[]>(() =>
    satellites.value.filter((sat) => sat.type === 'LEO'),
  );

  const groundStations = computed<GroundStation[]>(() =>
    Array.isArray(systemData.value.ground_stations) ? systemData.value.ground_stations : [],
  );

  const geoRelays = computed<GeoRelay[]>(() =>
    Array.isArray(systemData.value.geo_relays) ? systemData.value.geo_relays : [],
  );

  const requests = computed<(TransmissionRequest & Record<string, unknown>)[]>(() => {
    const rows = Array.isArray(systemData.value.requests)
      ? (systemData.value.requests as (TransmissionRequest & Record<string, unknown>)[])
      : [];
    return rows
      .filter((req) => req.source !== 'background')
      .slice()
      .sort((a, b) => String(b.id || '').localeCompare(String(a.id || '')));
  });

  const recentRequests = computed(() => requests.value.slice(0, 8));

  const satelliteCount = computed(() => satellites.value.length);
  const groundStationCount = computed(() => groundStations.value.length);
  const geoRelayCount = computed(() => geoRelays.value.length);

  const dataTypeOptions = computed(() => {
    const apiTypes = (systemInfo.value.data_types as Record<string, { name?: string }>) || {};
    const keys = Object.keys(apiTypes);
    const sourceKeys = keys.length ? keys : Object.keys(DATA_TYPE_LABELS);
    return sourceKeys.map((key) => ({
      value: key,
      label: DATA_TYPE_LABELS[key] || apiTypes[key]?.name || key,
    }));
  });

  const utilizationRows = computed(() => {
    const summary = (resourceStatus.value as { summary?: Record<string, unknown> }).summary || {};
    return [
      { key: 'satellites', label: '卫星资源', value: Number(summary.satellites_utilization || 0) },
      { key: 'ground', label: '地面站资源', value: Number(summary.ground_stations_utilization || 0) },
      { key: 'geo', label: '中继资源', value: Number(summary.geo_relays_utilization || 0) },
      { key: 'overall', label: '综合占用', value: Number(summary.overall_utilization || 0) },
    ];
  });

  // ── Helpers ────────────────────────────────────────────────────────────────
  function apiUrl(path: string): string {
    return `${apiBase.value}${path}`;
  }

  async function fetchJson<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    };
    const token = localStorage.getItem('smartnode_token');
    if (token && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    const response = await fetch(apiUrl(path), { ...options, headers });
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json')
      ? await response.json()
      : await response.text();
    if (!response.ok) {
      const message =
        typeof payload === 'string'
          ? payload
          : (payload.message || payload.reject_reason || payload.error || '请求失败');
      throw new Error(message);
    }
    if (payload && typeof payload === 'object' && payload.code === 0 && 'data' in payload) {
      return payload.data as T;
    }
    return payload as T;
  }

  // ── Actions ��───────────────────────────────────────────────────────────────

  /** Fetch all backend data in parallel and update store state. */
  async function refreshAll(): Promise<void> {
    if (refreshing.value) return;
    refreshing.value = true;
    try {
      const [health, data, info, status] = await Promise.allSettled([
        fetchJson('/api/health'),
        fetchJson<SystemData>('/api/data'),
        fetchJson<Record<string, unknown>>('/api/system_info'),
        fetchJson<Record<string, unknown>>('/api/resource_status'),
        fetchJson('/api/resource_utilization'),
      ]);

      backendOnline.value = health.status === 'fulfilled';

      if (data.status === 'fulfilled') {
        systemData.value = data.value || {
          time: 0,
          satellites: [],
          ground_stations: [],
          geo_relays: [],
          requests: [],
          stats: {},
        };
      }

      if (info.status === 'fulfilled') {
        systemInfo.value = info.value || {};
      }

      if (status.status === 'fulfilled') {
        resourceStatus.value = status.value || {};
      }
    } catch {
      backendOnline.value = false;
    } finally {
      refreshing.value = false;
    }
  }

  /**
   * Start background polling. Safe to call multiple times — creates at most
   * one timer. Performs an immediate refresh before starting the interval.
   */
  function startPolling(interval?: number): void {
    if (pollingTimer !== null) return; // already polling
    if (interval !== undefined) {
      pollInterval.value = interval;
    }
    void refreshAll();
    pollingTimer = window.setInterval(() => {
      void refreshAll();
    }, pollInterval.value);
  }

  /** Stop background polling and clear the timer. */
  function stopPolling(): void {
    if (pollingTimer !== null) {
      window.clearInterval(pollingTimer);
      pollingTimer = null;
    }
  }

  /** Update the API base URL and immediately refresh all data. */
  function setApiBase(value: string): void {
    const normalized = (value || '').trim().replace(/\/$/, '');
    apiBase.value = normalized === window.location.origin ? '' : normalized;
    if (apiBase.value) {
      localStorage.setItem('space_api_base', apiBase.value);
    } else {
      localStorage.removeItem('space_api_base');
    }
    void refreshAll();
  }

  return {
    // state
    apiBase,
    backendOnline,
    refreshing,
    pollInterval,
    systemData,
    systemInfo,
    resourceStatus,
    utilization,
    // getters
    systemTime,
    formattedTime,
    stats,
    satellites,
    leoSatellites,
    groundStations,
    geoRelays,
    requests,
    recentRequests,
    satelliteCount,
    groundStationCount,
    geoRelayCount,
    dataTypeOptions,
    utilizationRows,
    // actions
    fetchJson,
    refreshAll,
    startPolling,
    stopPolling,
    setApiBase,
  };
});
