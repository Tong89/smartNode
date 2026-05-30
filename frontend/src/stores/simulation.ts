/**
 * simulation.ts — Pinia store for simulation state management.
 *
 * Centralises systemData, systemInfo, resourceStatus, utilization, and
 * backendOnline status previously scattered across App.vue component data.
 * Provides configurable polling via startPolling / stopPolling.
 *
 * All network calls are routed through the typed API client in `../api`.
 */
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { SystemData, Satellite, GroundStation, GeoRelay, TransmissionRequest } from '../types/api';
import { apiClient } from '../api/client';
import {
  fetchHealth,
  fetchData,
  fetchSystemInfo,
  fetchResourceStatus,
  fetchResourceUtilization,
  submitRequest as apiSubmitRequest,
  updateGroundStations as apiUpdateGroundStations,
  updateLeoSatellites as apiUpdateLeoSatellites,
} from '../api/endpoints';
import type {
  TransmissionRequestPayload,
  UpdateGroundStationsPayload,
  UpdateLeoSatellitesPayload,
  TransmissionRequestResult,
  UpdateResourceResult,
} from '../api/endpoints';

/** Default polling interval in milliseconds */
const DEFAULT_POLL_INTERVAL = 2000;

const DATA_TYPE_LABELS: Record<string, string> = {
  TASK_CMD: '任务指令',
  INTEL: '情报信息',
  DATA_SLICE: '数据切片',
  RAW_IMAGE: '原始影像',
};

export const useSimulationStore = defineStore('simulation', () => {
  // ── State ──────────────────────────────────────────────────────────────────
  const apiBase = ref(apiClient.baseUrl);
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

  // ── Actions ────────────────────────────────────────────────────────────────

  /** Fetch all backend data in parallel and update store state. */
  async function refreshAll(): Promise<void> {
    if (refreshing.value) return;
    refreshing.value = true;
    try {
      const [health, data, info, status] = await Promise.allSettled([
        fetchHealth(),
        fetchData(),
        fetchSystemInfo(),
        fetchResourceStatus(),
        fetchResourceUtilization(),
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
    apiClient.setBaseUrl(value);
    apiBase.value = apiClient.baseUrl;
    void refreshAll();
  }

  /**
   * Submit a new transmission request via the typed API client.
   * Returns the result object from the backend.
   */
  function sendRequest(payload: TransmissionRequestPayload): Promise<TransmissionRequestResult> {
    return apiSubmitRequest(payload);
  }

  /**
   * Update the ground-station pool size.
   */
  function sendUpdateGroundStations(payload: UpdateGroundStationsPayload): Promise<UpdateResourceResult> {
    return apiUpdateGroundStations(payload);
  }

  /**
   * Update the LEO satellite constellation size.
   */
  function sendUpdateLeoSatellites(payload: UpdateLeoSatellitesPayload): Promise<UpdateResourceResult> {
    return apiUpdateLeoSatellites(payload);
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
    refreshAll,
    startPolling,
    stopPolling,
    setApiBase,
    sendRequest,
    sendUpdateGroundStations,
    sendUpdateLeoSatellites,
  };
});
