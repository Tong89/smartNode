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
          :visible="uiStore.activeView === 'requests'"
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

        <ScenarioPanel
          :visible="uiStore.activeView === 'scenario'"
          @scenario-changed="simStore.refreshAll"
        />

        <GanttTimeline
          :visible="uiStore.activeView === 'timeline'"
          :timeline="simStore.resourceTimeline"
          @refresh="simStore.refreshAll"
        />

        <StatsChartsPanel
          :visible="uiStore.activeView === 'stats'"
          :accepted-requests="Number(simStore.stats.accepted_requests) || 0"
          :rejected-requests="Number(simStore.stats.rejected_requests) || 0"
          :total-requests="Number(simStore.stats.total_requests) || 0"
          :decision-metrics="simStore.decisionMetrics"
          :rejection-distribution="simStore.rejectionDistribution"
          :throughput-history="simStore.throughputHistory"
          @refresh="simStore.refreshAll"
        />

        <TimePlayback
          :visible="uiStore.activeView === 'playback'"
          :has-data="!!simStore.resourceTimeline"
          :playing="simStore.playback.playing.value"
          :is-historical="simStore.playback.isHistorical.value"
          :slider-fraction="simStore.playback.sliderFraction.value"
          :cursor-label="simStore.playback.cursorLabel.value"
          :end-label="playbackEndLabel"
          :speed="simStore.playback.speed.value"
          @toggle-play="simStore.playback.togglePlay"
          @seek="simStore.playback.onSliderInput"
          @set-speed="(s) => simStore.playback.setSpeed(s)"
          @return-to-live="simStore.playback.returnToLive"
        />

        <UtilizationBars :rows="simStore.utilizationRows" />

        <RequestList :requests="simStore.recentRequests" />
      </aside>
    </main>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, onMounted, onBeforeUnmount, watch } from 'vue';
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
import ScenarioPanel from './components/ScenarioPanel.vue';
import GanttTimeline from './components/GanttTimeline.vue';
import StatsChartsPanel from './components/StatsChartsPanel.vue';
import TimePlayback from './components/TimePlayback.vue';

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
    ScenarioPanel,
    GanttTimeline,
    StatsChartsPanel,
    TimePlayback,
  },

  setup() {
    const simStore = useSimulationStore();
    const uiStore = useUiStore();

    // ── Playback end-of-window label ──────────────────────────────────────────
    const playbackEndLabel = computed<string>(() => {
      const tl = simStore.resourceTimeline;
      if (!tl) return simStore.formattedTime;
      const total = Math.max(0, Math.floor(tl.time_range[1]));
      const h = Math.floor(total / 3600);
      const m = Math.floor((total % 3600) / 60);
      const s = total % 60;
      return [h, m, s].map((p) => String(p).padStart(2, '0')).join(':');
    });

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

        const result = await simStore.sendRequest({
          data_type: requestForm.value.data_type,
          data_size: Number(requestForm.value.data_size),
          priority: Number(requestForm.value.priority),
          max_delay: Number(requestForm.value.max_delay),
          selected_ground_stations: selectedGroundStations,
          satellite_id: requestForm.value.satellite_id || undefined,
        });

        if (result && result.status === 'rejected') {
          uiStore.setNotice(
            `请求被拒绝：${result.reject_reason || '资源暂不可用'}`,
            'error',
          );
        } else {
          uiStore.setNotice(`请求已提交：${result.id || '已进入队列'}`);
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
        await simStore.sendUpdateGroundStations({
          count: Number(resourceForm.value.ground_station_count),
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
        await simStore.sendUpdateLeoSatellites({
          count: Number(resourceForm.value.leo_satellite_count),
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
      playbackEndLabel,
      saveApiBase,
      submitRequest,
      updateGroundStations,
      updateLeoSatellites,
    };
  },
});
</script>
