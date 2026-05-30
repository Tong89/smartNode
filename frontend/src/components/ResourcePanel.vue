<template>
  <section class="tool-panel" v-show="visible">
    <div class="panel-heading">
      <div>
        <span class="eyebrow">资源控制</span>
        <h2>调整仿真规模</h2>
      </div>
      <button class="icon-button" type="button" @click="$emit('refresh')" title="刷新">
        <i data-lucide="refresh-cw"></i>
      </button>
    </div>

    <div class="control-stack">
      <label>
        <span>地面站数量</span>
        <input
          :value="modelValue.ground_station_count"
          @input="update('ground_station_count', Number(($event.target as HTMLInputElement).value))"
          type="number"
          min="1"
          step="1"
        >
      </label>
      <button class="secondary-button" type="button" @click="$emit('update-ground-stations')">
        <i data-lucide="radio-tower"></i>
        <span>应用地面站</span>
      </button>
      <label>
        <span>LEO 卫星数量</span>
        <input
          :value="modelValue.leo_satellite_count"
          @input="update('leo_satellite_count', Number(($event.target as HTMLInputElement).value))"
          type="number"
          min="1"
          step="1"
        >
      </label>
      <button class="secondary-button" type="button" @click="$emit('update-leo-satellites')">
        <i data-lucide="orbit"></i>
        <span>应用卫星</span>
      </button>
    </div>
  </section>
</template>

<script lang="ts">
import { defineComponent } from 'vue';
import type { PropType } from 'vue';

export interface ResourceFormData {
  ground_station_count: number;
  leo_satellite_count: number;
}

export default defineComponent({
  name: 'ResourcePanel',

  props: {
    visible: {
      type: Boolean,
      required: true,
    },
    modelValue: {
      type: Object as PropType<ResourceFormData>,
      required: true,
    },
  },

  emits: ['update:modelValue', 'refresh', 'update-ground-stations', 'update-leo-satellites'],

  setup(props, { emit }) {
    function update<K extends keyof ResourceFormData>(key: K, value: ResourceFormData[K]) {
      emit('update:modelValue', { ...props.modelValue, [key]: value });
    }
    return { update };
  },
});
</script>
