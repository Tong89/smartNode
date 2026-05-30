<template>
  <section class="tool-panel" v-show="visible">
    <div class="panel-heading">
      <div>
        <span class="eyebrow">任务编排</span>
        <h2>提交回传请求</h2>
      </div>
      <button class="icon-button" type="button" @click="$emit('submit')" :disabled="submitting" title="提交">
        <i data-lucide="send-horizontal"></i>
      </button>
    </div>

    <form class="request-form" @submit.prevent="$emit('submit')">
      <label>
        <span>数据类型</span>
        <select :value="modelValue.data_type" @change="update('data_type', ($event.target as HTMLSelectElement).value)">
          <option v-for="item in dataTypeOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
      </label>
      <div class="form-grid">
        <label>
          <span>数据量</span>
          <input
            :value="modelValue.data_size"
            @input="update('data_size', Number(($event.target as HTMLInputElement).value))"
            type="number"
            min="1"
            step="1"
          >
        </label>
        <label>
          <span>优先级</span>
          <input
            :value="modelValue.priority"
            @input="update('priority', Number(($event.target as HTMLInputElement).value))"
            type="number"
            min="1"
            max="10"
            step="1"
          >
        </label>
      </div>
      <label>
        <span>最大等待秒数</span>
        <input
          :value="modelValue.max_delay"
          @input="update('max_delay', Number(($event.target as HTMLInputElement).value))"
          type="number"
          min="60"
          step="60"
        >
      </label>
      <label>
        <span>指定卫星</span>
        <select :value="modelValue.satellite_id" @change="update('satellite_id', ($event.target as HTMLSelectElement).value)">
          <option value="">自动选择</option>
          <option v-for="sat in leoSatellites" :key="sat.id" :value="sat.id">{{ sat.id }} · {{ sat.name }}</option>
        </select>
      </label>
      <label>
        <span>优先地面站</span>
        <select :value="modelValue.ground_station_id" @change="update('ground_station_id', ($event.target as HTMLSelectElement).value)">
          <option value="">自动选择</option>
          <option v-for="station in groundStations" :key="station.id" :value="station.id">{{ station.id }} · {{ station.name }}</option>
        </select>
      </label>
      <button class="primary-button" type="submit" :disabled="submitting">
        <i data-lucide="play"></i>
        <span>{{ submitting ? '提交中' : '启动任务' }}</span>
      </button>
    </form>

    <p v-if="notice" :class="['notice', noticeType]">{{ notice }}</p>
  </section>
</template>

<script lang="ts">
import { defineComponent } from 'vue';
import type { PropType } from 'vue';
import type { Satellite, GroundStation } from '../types/api';

export interface RequestFormData {
  data_type: string;
  data_size: number;
  priority: number;
  max_delay: number;
  satellite_id: string;
  ground_station_id: string;
}

export interface DataTypeOption {
  value: string;
  label: string;
}

export default defineComponent({
  name: 'RequestForm',

  props: {
    visible: {
      type: Boolean,
      required: true,
    },
    modelValue: {
      type: Object as PropType<RequestFormData>,
      required: true,
    },
    leoSatellites: {
      type: Array as PropType<Satellite[]>,
      required: true,
    },
    groundStations: {
      type: Array as PropType<GroundStation[]>,
      required: true,
    },
    dataTypeOptions: {
      type: Array as PropType<DataTypeOption[]>,
      required: true,
    },
    submitting: {
      type: Boolean,
      required: true,
    },
    notice: {
      type: String,
      default: '',
    },
    noticeType: {
      type: String,
      default: 'success',
    },
  },

  emits: ['update:modelValue', 'submit'],

  setup(props, { emit }) {
    function update<K extends keyof RequestFormData>(key: K, value: RequestFormData[K]) {
      emit('update:modelValue', { ...props.modelValue, [key]: value });
    }
    return { update };
  },
});
</script>
