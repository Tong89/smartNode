<template>
  <nav class="rail" aria-label="视图切换">
    <button
      :class="{ active: activeView === 'requests' }"
      type="button"
      @click="$emit('set-view', 'requests')"
      title="任务"
    >
      <i data-lucide="send"></i>
      <span>任务</span>
    </button>
    <button
      :class="{ active: activeView === 'resources' }"
      type="button"
      @click="$emit('set-view', 'resources')"
      title="资源"
    >
      <i data-lucide="sliders-horizontal"></i>
      <span>资源</span>
    </button>
  </nav>
</template>

<script lang="ts">
import { defineComponent } from 'vue';

export default defineComponent({
  name: 'SideRail',

  props: {
    activeView: {
      type: String,
      required: true,
    },
  },

  emits: ['set-view'],
});
</script>
