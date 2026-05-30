<template>
  <section class="tool-panel request-list">
    <div class="panel-heading compact">
      <div>
        <span class="eyebrow">任务队列</span>
        <h2>最近请求</h2>
      </div>
    </div>
    <div class="request-table">
      <div class="request-row head">
        <span>编号</span>
        <span>类型</span>
        <span>状态</span>
        <span>链路</span>
        <span>进度</span>
      </div>
      <div v-for="req in requests" :key="req.id" class="request-row">
        <span>{{ req.id }}</span>
        <span>{{ labelDataType(req.data_type) }}</span>
        <span :class="['status-pill', req.status]">{{ labelStatus(req.status) }}</span>
        <span>{{ labelLinkMode(req) }}</span>
        <span>{{ formatProgress(req.progress) }}</span>
      </div>
      <div v-if="requests.length === 0" class="empty-state">暂无任务请求</div>
    </div>
  </section>
</template>

<script lang="ts">
import { defineComponent } from 'vue';
import type { PropType } from 'vue';
import type { TransmissionRequest } from '../types/api';

const DATA_TYPE_LABELS: Record<string, string> = {
  TASK_CMD: '任务指令',
  INTEL: '情报信息',
  DATA_SLICE: '数据切片',
  RAW_IMAGE: '原始影像',
};

const STATUS_LABELS: Record<string, string> = {
  pending: '排队',
  accepted: '等待',
  transmitting: '传输',
  completed: '完成',
  rejected: '拒绝',
};

type RequestWithExtras = TransmissionRequest & {
  transmission_method?: string;
};

export default defineComponent({
  name: 'RequestList',

  props: {
    requests: {
      type: Array as PropType<RequestWithExtras[]>,
      required: true,
    },
  },

  setup() {
    function labelDataType(type: string): string {
      return DATA_TYPE_LABELS[type] || type || '未知';
    }

    function labelStatus(status: string): string {
      return STATUS_LABELS[status] || status || '未知';
    }

    function labelLinkMode(req: RequestWithExtras): string {
      if (req.transmission_method === 'direct') return '直连';
      if (req.transmission_method === 'relay') return '中继';
      if (req.transmission_method === 'multi_relay') return '多跳';
      return '-';
    }

    function formatProgress(progress: number | undefined): string {
      const value = Number(progress || 0);
      return `${Math.max(0, Math.min(100, value)).toFixed(0)}%`;
    }

    return { labelDataType, labelStatus, labelLinkMode, formatProgress };
  },
});
</script>
