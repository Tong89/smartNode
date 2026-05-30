<template>
  <div class="shell" v-cloak>
    <TopBar
      :backend-online="simStore.backendOnline"
      :formatted-time="simStore.formattedTime"
      v-model:api-base-draft="apiBaseDraft"
      @save-api-base="saveApiBase"
    />

    <main class="workspace">
      <SideRail :active-view="uiStore.activeView" @set-view="uiStore.setView" />

      <CesiumScene
        :satellites="simStore.satellites"
        :ground-stations="simStore.groundStations"
        :geo-relays="simStore.geoRelays"
        :active-requests="simStore.requests"
        :satellite-count="simStore.satelliteCount"
        :ground-station-count="simStore.groundStationCount"
        :geo-relay-count="simStore.geoRelayCount"
        :total-requests="Number(simStore.stats.total_requests) || 0"
      />

      <aside class="inspector">
        <RequestForm
          :visible="uiStore.activeView !== 'resources'"
          v-model="requestForm"
          :leo-satellites="simStore.leoSatellites"
          :ground-stations="simStore.groundStations"
          :data-type-options="simStore.dataTypeOptions"
          :submitting="uiStore.submitting"
          :notice="uiStore.notice"
          :notice-type="uiStore.noticeType"
          @submit="submitRequest"
        />

        <ResourcePanel
          :visible="uiStore.activeView === 'resources'"
          v-model="resourceForm"
          @refresh="simStore.refreshAll"
          @update-ground-stations="updateGroundStations"
          @update-leo-satellites="updateLeoSatellites"
        />

        <UtilizationBars :rows="simStore.utilizationRows" />

        <RequestList :requests="simStore.recentRequests" />
      </aside>
    </main>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted, onBeforeUnmount, watch } from 'vue';
import { useSimulationStore } from './stores/simulation';
import { useUiStore } from './stores/ui';
import TopBar from './components/TopBar.vue';
import SideRail from './components/SideRail.vue';
import CesiumScene from './components/CesiumScene.vue';
import RequestForm from './components/RequestForm.vue';
import type { RequestFormData } from './components/RequestForm.vue';
import ResourcePanel from './components/ResourcePanel.vue';
import type { ResourceFormData } from './components/ResourcePanel.vue';
import UtilizationBars from './components/UtilizationBars.vue';
import RequestList from './components/RequestList.vue';

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
    const simStore = useSimulationStore();
    const uiStore = useUiStore();

    // ── Local UI state (form data, not shared globally) ───────────────────────
    const apiBaseDraft = ref(simStore.apiBase || window.location.origin);

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

    // ── Sync resource form when system info is first available ────────────────
    function syncResourceForm() {
      if (uiStore.resourceFormReady) return;
      resourceForm.value.ground_station_count = Number(
        (simStore.systemInfo.ground_station_count as number) ||
          simStore.groundStationCount ||
          0,
      );
      resourceForm.value.leo_satellite_count = Number(
        (simStore.systemInfo.leo_satellite_count as number) ||
          simStore.leoSatellites.length ||
          0,
      );
      uiStore.markResourceFormReady();
    }

    watch(
      () => simStore.systemInfo,
      () => {
        syncResourceForm();
      },
      { deep: true },
    );

    // ── Actions ───────────────────────────────────────────────────────────────
    function saveApiBase() {
      const value = (apiBaseDraft.value || '').trim().replace(/\/$/, '');
      simStore.setApiBase(value);
      uiStore.setNotice('API 地址已更新');
    }

    async function submitRequest() {
      uiStore.submitting = true;
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

        const result = await simStore.fetchJson<Record<string, unknown>>('/api/request', {
          method: 'POST',
          body: JSON.stringify(payload),
        });

        if (result && result.status === 'rejected') {
          uiStore.setNotice(
            `请求被拒绝：${(result.reject_reason as string) || '资源暂不可用'}`,
            'error',
          );
        } else {
          uiStore.setNotice(`请求已提交：${(result.id as string) || '已进入队列'}`);
        }

        await simStore.refreshAll();
      } catch (error) {
        uiStore.setNotice((error as Error).message || '提交失败', 'error');
      } finally {
        uiStore.submitting = false;
      }
    }

    async function updateGroundStations() {
      try {
        await simStore.fetchJson('/api/update_ground_stations', {
          method: 'POST',
          body: JSON.stringify({ count: Number(resourceForm.value.ground_station_count) }),
        });
        uiStore.setNotice('地面站数量已更新');
        uiStore.invalidateResourceForm();
        await simStore.refreshAll();
      } catch (error) {
        uiStore.setNotice((error as Error).message || '资源更新失败', 'error');
      }
    }

    async function updateLeoSatellites() {
      try {
        await simStore.fetchJson('/api/update_leo_satellites', {
          method: 'POST',
          body: JSON.stringify({ count: Number(resourceForm.value.leo_satellite_count) }),
        });
        uiStore.setNotice('卫星数量已更新');
        uiStore.invalidateResourceForm();
        await simStore.refreshAll();
      } catch (error) {
        uiStore.setNotice((error as Error).message || '资源更新失败', 'error');
      }
    }

    // ── Lifecycle ─────────────────────────────────────────────────────────────
    onMounted(() => {
      if ((window as unknown as { lucide?: { createIcons: () => void } }).lucide) {
        (window as unknown as { lucide: { createIcons: () => void } }).lucide.createIcons();
      }
      // startPolling guards against duplicate timers, so this is safe to call once
      simStore.startPolling(2000);
    });

    onBeforeUnmount(() => {
      simStore.stopPolling();
    });

    return {
      simStore,
      uiStore,
      apiBaseDraft,
      requestForm,
      resourceForm,
      saveApiBase,
      submitRequest,
      updateGroundStations,
      updateLeoSatellites,
    };
  },
});
</script>
