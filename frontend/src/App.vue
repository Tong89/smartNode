<template>
  <div class="shell" v-cloak>
    <TopBar
      :backend-online="backendOnline"
      :formatted-time="formattedTime"
      v-model:api-base-draft="apiBaseDraft"
      @save-api-base="saveApiBase"
    />

    <main class="workspace">
      <SideRail :active-view="activeView" @set-view="setView" />

      <CesiumScene
        :satellites="satellites"
        :ground-stations="groundStations"
        :geo-relays="geoRelays"
        :active-requests="requests"
        :satellite-count="satelliteCount"
        :ground-station-count="groundStationCount"
        :geo-relay-count="geoRelayCount"
        :total-requests="Number(stats.total_requests) || 0"
      />

      <aside class="inspector">
        <RequestForm
          :visible="activeView !== 'resources'"
          v-model="requestForm"
          :leo-satellites="leoSatellites"
          :ground-stations="groundStations"
          :data-type-options="dataTypeOptions"
          :submitting="submitting"
          :notice="notice"
          :notice-type="noticeType"
          @submit="submitRequest"
        />

        <ResourcePanel
          :visible="activeView === 'resources'"
          v-model="resourceForm"
          @refresh="refreshAll"
          @update-ground-stations="updateGroundStations"
          @update-leo-satellites="updateLeoSatellites"
        />

        <UtilizationBars :rows="utilizationRows" />

        <RequestList :requests="recentRequests" />
      </aside>
    </main>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, onMounted, onBeforeUnmount } from 'vue';
import TopBar from './components/TopBar.vue';
import SideRail from './components/SideRail.vue';
import CesiumScene from './components/CesiumScene.vue';
import RequestForm from './components/RequestForm.vue';
import type { RequestFormData } from './components/RequestForm.vue';
import ResourcePanel from './components/ResourcePanel.vue';
import type { ResourceFormData } from './components/ResourcePanel.vue';
import UtilizationBars from './components/UtilizationBars.vue';
import RequestList from './components/RequestList.vue';
import type { SystemData, TransmissionRequest } from './types/api';

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

export default defineComponent({
  name: 'App',

  components: {
    TopBar,
    SideRail,
    CesiumScene,
    RequestForm,
    ResourcePanel,
    UtilizationBars,
    RequestList,
  },

  setup() {
    // ── State ─────────────────────────────────────────────────────────────────
    const apiBase = ref(resolveApiBase());
    const apiBaseDraft = ref(apiBase.value || window.location.origin);
    const activeView = ref<'requests' | 'resources'>('requests');
    const backendOnline = ref(false);
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
    const notice = ref('');
    const noticeType = ref<'success' | 'error'>('success');
    const submitting = ref(false);
    const refreshing = ref(false);
    const resourceFormReady = ref(false);
    let refreshTimer: ReturnType<typeof window.setInterval> | null = null;
    let noticeTimer: ReturnType<typeof window.setTimeout> | null = null;

    const requestForm = ref<RequestFormData>({
      data_type: 'DATA_SLICE',
      data_size: 120,
      priority: 5,
      max_delay: 600,
      satellite_id: '',
      ground_station_id: '',
    });

    const resourceForm = ref<ResourceFormData>({
      ground_station_count: 0,
      leo_satellite_count: 0,
    });

    // ── Computed ──────────────────────────────────────────────────────────────
    const systemTime = computed(() => Number(systemData.value.time || 0));

    const formattedTime = computed(() => {
      const total = Math.max(0, Math.floor(systemTime.value));
      const hours = Math.floor(total / 3600);
      const minutes = Math.floor((total % 3600) / 60);
      const secs = total % 60;
      return [hours, minutes, secs].map((p) => String(p).padStart(2, '0')).join(':');
    });

    const stats = computed(() => systemData.value.stats || {});

    const satellites = computed(() =>
      Array.isArray(systemData.value.satellites) ? systemData.value.satellites : [],
    );

    const leoSatellites = computed(() =>
      satellites.value.filter((sat) => sat.type === 'LEO'),
    );

    const groundStations = computed(() =>
      Array.isArray(systemData.value.ground_stations) ? systemData.value.ground_stations : [],
    );

    const geoRelays = computed(() =>
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

    // ── Helpers ───────────────────────────────────────────────────────────────
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

    function setNotice(message: string, type: 'success' | 'error' = 'success') {
      notice.value = message;
      noticeType.value = type;
      if (noticeTimer !== null) window.clearTimeout(noticeTimer);
      noticeTimer = window.setTimeout(() => {
        notice.value = '';
      }, 4200);
    }

    function syncResourceForm() {
      if (resourceFormReady.value) return;
      resourceForm.value.ground_station_count = Number(
        (systemInfo.value.ground_station_count as number) || groundStationCount.value || 0,
      );
      resourceForm.value.leo_satellite_count = Number(
        (systemInfo.value.leo_satellite_count as number) || leoSatellites.value.length || 0,
      );
      resourceFormReady.value = true;
    }

    // ── Actions ───────────────────────────────────────────────────────────────
    function setView(view: 'requests' | 'resources') {
      activeView.value = view;
    }

    function saveApiBase() {
      const value = (apiBaseDraft.value || '').trim().replace(/\/$/, '');
      apiBase.value = value === window.location.origin ? '' : value;
      if (apiBase.value) {
        localStorage.setItem('space_api_base', apiBase.value);
      } else {
        localStorage.removeItem('space_api_base');
      }
      setNotice('API 地址已更新');
      refreshAll();
    }

    async function refreshAll() {
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
          syncResourceForm();
        }

        if (status.status === 'fulfilled') {
          resourceStatus.value = status.value || {};
        }
      } catch (error) {
        backendOnline.value = false;
        setNotice((error as Error).message || '刷新失败', 'error');
      } finally {
        refreshing.value = false;
      }
    }

    async function submitRequest() {
      submitting.value = true;
      try {
        const selectedGroundStations = requestForm.value.ground_station_id
          ? [requestForm.value.ground_station_id]
          : [];

        const payload: Record<string, unknown> = {
          data_type: requestForm.value.data_type,
          data_size: Number(requestForm.value.data_size),
          priority: Number(requestForm.value.priority),
          max_delay: Number(requestForm.value.max_delay),
          selected_ground_stations: selectedGroundStations,
        };

        if (requestForm.value.satellite_id) {
          payload.satellite_id = requestForm.value.satellite_id;
        }

        const result = await fetchJson<Record<string, unknown>>('/api/request', {
          method: 'POST',
          body: JSON.stringify(payload),
        });

        if (result && result.status === 'rejected') {
          setNotice(`请求被拒绝：${(result.reject_reason as string) || '资源暂不可用'}`, 'error');
        } else {
          setNotice(`请求已提交：${(result.id as string) || '已进入队列'}`);
        }

        await refreshAll();
      } catch (error) {
        setNotice((error as Error).message || '提交失败', 'error');
      } finally {
        submitting.value = false;
      }
    }

    async function updateGroundStations() {
      try {
        await fetchJson('/api/update_ground_stations', {
          method: 'POST',
          body: JSON.stringify({ count: Number(resourceForm.value.ground_station_count) }),
        });
        setNotice('地面站数量已更新');
        resourceFormReady.value = false;
        await refreshAll();
      } catch (error) {
        setNotice((error as Error).message || '资源更新失败', 'error');
      }
    }

    async function updateLeoSatellites() {
      try {
        await fetchJson('/api/update_leo_satellites', {
          method: 'POST',
          body: JSON.stringify({ count: Number(resourceForm.value.leo_satellite_count) }),
        });
        setNotice('卫星数量已更新');
        resourceFormReady.value = false;
        await refreshAll();
      } catch (error) {
        setNotice((error as Error).message || '资源更新失败', 'error');
      }
    }

    // ── Lifecycle ─────────────────────────────────────────────────────────────
    onMounted(() => {
      // Render lucide icons after each DOM update
      if ((window as unknown as { lucide?: { createIcons: () => void } }).lucide) {
        (window as unknown as { lucide: { createIcons: () => void } }).lucide.createIcons();
      }
      refreshAll();
      refreshTimer = window.setInterval(refreshAll, 2000);
    });

    onBeforeUnmount(() => {
      if (refreshTimer !== null) window.clearInterval(refreshTimer);
      if (noticeTimer !== null) window.clearTimeout(noticeTimer);
    });

    return {
      apiBaseDraft,
      activeView,
      backendOnline,
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
      requestForm,
      resourceForm,
      submitting,
      notice,
      noticeType,
      setView,
      saveApiBase,
      refreshAll,
      submitRequest,
      updateGroundStations,
      updateLeoSatellites,
    };
  },
});
</script>
