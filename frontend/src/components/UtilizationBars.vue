<template>
  <section class="tool-panel">
    <div class="panel-heading compact">
      <div>
        <span class="eyebrow">资源占用</span>
        <h2>实时利用率</h2>
      </div>
    </div>
    <div class="resource-bars">
      <div v-for="item in rows" :key="item.key" class="resource-row">
        <div>
          <span>{{ item.label }}</span>
          <strong>{{ item.value.toFixed(1) }}%</strong>
        </div>
        <progress :value="item.value" max="100"></progress>
      </div>
    </div>
  </section>
</template>

<script lang="ts">
import { defineComponent } from 'vue';
import type { PropType } from 'vue';

export interface UtilizationRow {
  key: string;
  label: string;
  value: number;
}

export default defineComponent({
  name: 'UtilizationBars',

  props: {
    rows: {
      type: Array as PropType<UtilizationRow[]>,
      required: true,
    },
  },
});
</script>
