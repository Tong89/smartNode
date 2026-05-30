<template>
  <header class="topbar">
    <div class="brand">
      <span class="brand-mark">CD</span>
      <div>
        <strong>天基智枢 SmartNode 仿真平台</strong>
        <small>Space-Based Intelligent Relay Simulation Platform</small>
      </div>
    </div>

    <div class="status-strip">
      <span :class="['service-dot', backendOnline ? 'is-online' : 'is-offline']"></span>
      <span>{{ backendOnline ? '后端在线' : '等待后端' }}</span>
      <span class="splitter"></span>
      <span>仿真时钟 {{ formattedTime }}</span>
    </div>

    <div class="api-control">
      <i data-lucide="server"></i>
      <input
        :value="apiBaseDraft"
        @input="$emit('update:apiBaseDraft', ($event.target as HTMLInputElement).value)"
        @keyup.enter="$emit('save-api-base')"
        placeholder="API Base"
      >
      <button class="icon-button" type="button" @click="$emit('save-api-base')" title="保存 API 地址">
        <i data-lucide="check"></i>
      </button>
    </div>
  </header>
</template>

<script lang="ts">
import { defineComponent } from 'vue';

export default defineComponent({
  name: 'TopBar',

  props: {
    backendOnline: {
      type: Boolean,
      required: true,
    },
    formattedTime: {
      type: String,
      required: true,
    },
    apiBaseDraft: {
      type: String,
      required: true,
    },
  },

  emits: ['update:apiBaseDraft', 'save-api-base'],
});
</script>
