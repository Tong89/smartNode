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
import type { SystemData, Satellite, GroundStation, GeoRelay, TransmissionRequest, ResourceTimeline, ResourceUtilization, DecisionMetrics } from '../types/api';
import { apiClient } from '../api/client';
import {
  fetchHealth,
  fetchData,
  fetchSystemInfo,
  fetchResourceStatus,
  fetchResourceUtilization,
  fetchResourceTimeline,
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
import { usePlayback } from '../composables/use-playback';
import type { PlaybackSpeed } from '../composables/use-playback';

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
  const resourceUtilization = ref<ResourceUtilization | null>(null);

  /** Sliding window of throughput samples (last 20 polls) for sparkline */
  const throughputHistory = ref<number[]>([]);

  const resourceTimeline = ref<ResourceTimeline | null>(null);

  let pollingTimer: ReturnType<typeof window.setInterval> | null = null;

  // ── Playback composable ────────────────────────────────────────────────────
  /**
   * Playback state and controls wired to the simulation clock and timeline.
   * When the user drags the slider, playbackCursorTime diverges from systemTime
   * so that components can render the historical snapshot.
   */
  const playback = usePlayback(
    () => systemTime.value,
    () => {
      if (!resourceTimeline.value) return [0, Math.max(1, systemTime.value)] as [number, number];
      return resourceTimeline.value.time_range as [number, number];
    },
    (_seekTime: number) => {
      // Seek notification — currently used by watcher on playback.cursorTime
      // to trigger filtered rendering; no additional async call required here.
    },
  );

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

  /** Typed decision metrics from the last /api/resource_utilization fetch */
  const decisionMetrics = computed<DecisionMetrics>(() => {
    const dm = resourceUtilization.value?.decision_metrics;
    return {
      acceptance_rate: dm?.acceptance_rate ?? 0,
      completion_rate: dm?.completion_rate ?? 0,
      avg_scheduling_time: dm?.avg_scheduling_time ?? 0,
      avg_transmission_time: dm?.avg_transmission_time ?? 0,
      throughput_mbps: dm?.throughput_mbps ?? 0,
      total_scheduling_time: dm?.total_scheduling_time ?? 0,
      total_transmission_time: dm?.total_transmission_time ?? 0,
      scheduling_count: dm?.scheduling_count ?? 0,
      transmission_count: dm?.transmission_count ?? 0,
    };
  });

  /** Rejection distribution map keyed by reason code */
  const rejectionDistribution = computed<Record<string, number>>(
    () => resourceUtilization.value?.rejection_distribution ?? {},
  );

  const utilizationRows = computed(() => {
    const summary = (resourceStatus.value as { summary?: Record<string, unknown> }).summary || {};
    return [
      { key: 'satellites', label: '卫星资源', value: Number(summary.satellites_utilization || 0) },
      { key: 'ground', label: '地面站资源', value: Number(summary.ground_stations_utilization || 0) },
      { key: 'geo', label: '中继资源', value: Number(summary.geo_relays_utilization || 0) },
      { key: 'overall', label: '综合占用', value: Number(summary.overall_utilization || 0) },
    ];
  });

  // ── Playback getters ───────────────────────────────────────────────────────

  /**
   * The simulation time to use for rendering.
   * When in historical mode this follows the playback cursor; otherwise it
   * tracks the live systemTime.
   */
  const renderTime = computed<number>(() =>
    playback.isHistorical.value ? playback.cursorTime.value : systemTime.value,
  );

  /**
   * Events from the resource timeline that are active at renderTime.
   * Used by GanttTimeline and CesiumScene overlays for situational replay.
   */
  const activeEventsAtRenderTime = computed(() => {
    const tl = resourceTimeline.value;
    if (!tl) return [];
    const t = renderTime.value;
    const collect = (bucket: Record<string, { events: Array<{ start: number; end: number }> }>) =>
      Object.values(bucket).flatMap((res) =>
        res.events.filter((ev) => ev.start <= t && ev.end >= t),
      );
    return [
      ...collect(tl.satellites),
      ...collect(tl.ground_stations),
      ...collect(tl.geo_relays),
    ];
  });

  // Keep cursor in sync with live time when not in historical / playing mode.
  function tickPlaybackSync(): void {
    playback.syncLive();
  }

  // ── Actions ────────────────────────────────────────────────────────────────

  /** Fetch all backend data in parallel and update store state. */
  async function refreshAll(): Promise<void> {
    if (refreshing.value) return;
    refreshing.value = true;
    try {
      const [health, data, info, status, util, timeline] = await Promise.allSettled([
        fetchHealth(),
        fetchData(),
        fetchSystemInfo(),
        fetchResourceStatus(),
        fetchResourceUtilization(),
        fetchResourceTimeline(),
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

      if (util.status === 'fulfilled' && util.value) {
        resourceUtilization.value = util.value;
        // Maintain a sliding window of throughput samples for sparkline display
        const mbps = util.value.decision_metrics?.throughput_mbps ?? 0;
        throughputHistory.value = [...throughputHistory.value, mbps].slice(-20);
      }

      if (timeline.status === 'fulfilled') {
        resourceTimeline.value = timeline.value || null;
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
      // Sync the playback cursor to live time when not scrubbing.
      tickPlaybackSync();
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
    resourceUtilization,
    throughputHistory,
    resourceTimeline,
    // playback state (forwarded from composable)
    playback,
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
    decisionMetrics,
    rejectionDistribution,
    renderTime,
    activeEventsAtRenderTime,
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
