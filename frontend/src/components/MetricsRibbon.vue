<template>
  <div class="metrics-ribbon">
    <div class="metric">
      <span>在轨卫星</span>
      <strong>{{ satelliteCount }}</strong>
    </div>
    <div class="metric">
      <span>地面站</span>
      <strong>{{ groundStationCount }}</strong>
    </div>
    <div class="metric">
      <span>中继星</span>
      <strong>{{ geoRelayCount }}</strong>
    </div>
    <div class="metric">
      <span>请求总量</span>
      <strong>{{ totalRequests }}</strong>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue';

export default defineComponent({
  name: 'MetricsRibbon',

  props: {
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
});
</script>
