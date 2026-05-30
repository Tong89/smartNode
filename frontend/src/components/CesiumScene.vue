<template>
  <section class="map-area" aria-label="空间态势">
    <div id="cesiumContainer" class="map-canvas"></div>
    <div v-if="!cesiumReady" class="map-fallback">
      <strong>三维地球加载中</strong>
      <span>如果 CDN 不可用，数据面板仍可继续使用。</span>
    </div>

    <MetricsRibbon
      :satellite-count="satelliteCount"
      :ground-station-count="groundStationCount"
      :geo-relay-count="geoRelayCount"
      :total-requests="totalRequests"
    />

    <div class="map-legend">
      <span><b class="legend-dot sat"></b> LEO/MEO</span>
      <span><b class="legend-dot gs"></b> 地面站</span>
      <span><b class="legend-dot geo"></b> GEO 中继</span>
      <span><b class="legend-line"></b> 活动链路</span>
    </div>
  </section>
</template>

<script lang="ts">
import { defineComponent, onMounted, onBeforeUnmount, watch } from 'vue';
import type { PropType } from 'vue';
import MetricsRibbon from './MetricsRibbon.vue';
import { useCesiumScene } from '../composables/use-cesium-scene';
import type { Satellite, GroundStation, GeoRelay, TransmissionRequest } from '../types/api';

export default defineComponent({
  name: 'CesiumScene',

  components: { MetricsRibbon },

  props: {
    satellites: {
      type: Array as PropType<Satellite[]>,
      required: true,
    },
    groundStations: {
      type: Array as PropType<GroundStation[]>,
      required: true,
    },
    geoRelays: {
      type: Array as PropType<GeoRelay[]>,
      required: true,
    },
    activeRequests: {
      type: Array as PropType<TransmissionRequest[]>,
      required: true,
    },
    satelliteCount: {
      type: Number,
      required: true,
    },
    groundStationCount: {
      type: Number,
      required: true,
    },
    geoRelayCount: {
      type: Number,
      required: true,
    },
    totalRequests: {
      type: Number,
      required: true,
    },
  },

  setup(props) {
    const { cesiumReady, initCesium, updateScene, resizeViewer, destroyViewer } = useCesiumScene();

    onMounted(() => {
      initCesium('cesiumContainer');
      window.addEventListener('resize', resizeViewer);
    });

    onBeforeUnmount(() => {
      window.removeEventListener('resize', resizeViewer);
      destroyViewer();
    });

    // Re-render whenever scene data changes
    watch(
      () => [props.satellites, props.groundStations, props.geoRelays, props.activeRequests],
      () => {
        updateScene({
          satellites: props.satellites,
          groundStations: props.groundStations,
          geoRelays: props.geoRelays,
          activeRequests: props.activeRequests,
        });
      },
      { deep: true },
    );

    return { cesiumReady, resizeViewer };
  },
});
</script>
