<template>
  <section class="tool-panel gantt-panel" v-show="visible">
    <div class="panel-heading">
      <div>
        <span class="eyebrow">资源时间轴</span>
        <h2>占用甘特图</h2>
      </div>
      <button class="icon-button" type="button" @click="$emit('refresh')" title="刷新">
        <i data-lucide="refresh-cw"></i>
      </button>
    </div>

    <div v-if="!timeline" class="empty-state">暂无数据，等待后端响应…</div>

    <template v-else>
      <!-- 时间轴图例 -->
      <div class="gantt-legend">
        <span
          v-for="(label, key) in statusLabels"
          :key="key"
          class="legend-item"
        >
          <span class="legend-dot" :class="'dot-' + key"></span>{{ label }}
        </span>
      </div>

      <!-- 时间刻度 -->
      <div class="gantt-scale" :style="{ paddingLeft: LABEL_WIDTH + 'px' }">
        <div
          v-for="tick in timeTicks"
          :key="tick.t"
          class="gantt-tick"
          :style="{ left: tick.pct + '%' }"
        >
          {{ tick.label }}
        </div>
      </div>

      <!-- 各资源分组 -->
      <div class="gantt-body">
        <template v-for="group in groups" :key="group.id">
          <!-- 分组标头 -->
          <div class="gantt-group-header">{{ group.label }}</div>

          <!-- 每一行资源 -->
          <div
            v-for="row in group.rows"
            :key="row.id"
            class="gantt-row"
          >
            <div class="gantt-label" :style="{ width: LABEL_WIDTH + 'px' }" :title="row.name">
              {{ row.name }}
            </div>
            <div class="gantt-track">
              <div
                v-for="(evt, i) in row.events"
                :key="i"
                class="gantt-bar"
                :class="barClass(evt)"
                :style="barStyle(evt)"
                :title="barTooltip(evt)"
                @mouseenter="hoveredEvent = evt"
                @mouseleave="hoveredEvent = null"
              ></div>
            </div>
          </div>
        </template>

        <div v-if="groups.length === 0" class="empty-state">时间窗口内无占用事件</div>
      </div>

      <!-- 悬浮详情气泡 -->
      <div class="gantt-tooltip" v-if="hoveredEvent">
        <div class="tooltip-row">
          <span class="tooltip-key">请求 ID</span>
          <span class="tooltip-val">{{ hoveredEvent.request_id }}</span>
        </div>
        <div class="tooltip-row">
          <span class="tooltip-key">状态</span>
          <span class="tooltip-val">{{ statusLabels[hoveredEvent.status] || hoveredEvent.status }}</span>
        </div>
        <div class="tooltip-row">
          <span class="tooltip-key">数据类型</span>
          <span class="tooltip-val">{{ dataTypeLabels[hoveredEvent.data_type] || hoveredEvent.data_type }}</span>
        </div>
        <div class="tooltip-row">
          <span class="tooltip-key">数据量</span>
          <span class="tooltip-val">{{ hoveredEvent.data_size }} MB</span>
        </div>
        <div class="tooltip-row">
          <span class="tooltip-key">优先级</span>
          <span class="tooltip-val">P{{ hoveredEvent.priority }}</span>
        </div>
        <div class="tooltip-row">
          <span class="tooltip-key">进度</span>
          <span class="tooltip-val">{{ (hoveredEvent.progress * 100).toFixed(0) }}%</span>
        </div>
        <div class="tooltip-row">
          <span class="tooltip-key">时长</span>
          <span class="tooltip-val">{{ fmtDuration(hoveredEvent.end - hoveredEvent.start) }}</span>
        </div>
      </div>
    </template>
  </section>
</template>

<script lang="ts">
import { defineComponent, computed, ref } from 'vue';
import type { PropType } from 'vue';
import type { ResourceTimeline, TimelineEvent } from '../types/api';

const STATUS_LABELS: Record<string, string> = {
  transmitting: '传输中',
  completed: '已完成',
};

const DATA_TYPE_LABELS: Record<string, string> = {
  TASK_CMD: '任务指令',
  INTEL: '情报信息',
  DATA_SLICE: '数据切片',
  RAW_IMAGE: '原始影像',
};

const LABEL_WIDTH = 90; // px — resource name column width

export default defineComponent({
  name: 'GanttTimeline',

  props: {
    visible: {
      type: Boolean,
      required: true,
    },
    timeline: {
      type: Object as PropType<ResourceTimeline | null>,
      default: null,
    },
  },

  emits: ['refresh'],

  setup(props) {
    const hoveredEvent = ref<TimelineEvent | null>(null);

    const timeRange = computed<[number, number]>(() => {
      if (!props.timeline) return [0, 1];
      const [s, e] = props.timeline.time_range;
      // Avoid zero-length range to prevent division by zero
      return e > s ? [s, e] : [s, s + 1];
    });

    const rangeSpan = computed(() => timeRange.value[1] - timeRange.value[0]);

    /** Convert a simulation-time value to a percentage within the visible range */
    function toPct(t: number): number {
      const [start] = timeRange.value;
      return Math.max(0, Math.min(100, ((t - start) / rangeSpan.value) * 100));
    }

    /** 5 evenly-spaced tick marks along the time axis */
    const timeTicks = computed(() => {
      const [start] = timeRange.value;
      const span = rangeSpan.value;
      const count = 5;
      return Array.from({ length: count + 1 }, (_, i) => {
        const t = start + (span * i) / count;
        const pct = (i / count) * 100;
        const label = fmtTime(t);
        return { t, pct, label };
      });
    });

    interface GanttRow {
      id: string;
      name: string;
      events: TimelineEvent[];
    }

    interface GanttGroup {
      id: string;
      label: string;
      rows: GanttRow[];
    }

    /** Build display groups from the timeline data, skipping resources with no events */
    const groups = computed<GanttGroup[]>(() => {
      if (!props.timeline) return [];

      const result: GanttGroup[] = [];

      const satRows: GanttRow[] = Object.entries(props.timeline.satellites)
        .filter(([, res]) => res.events.length > 0)
        .map(([id, res]) => ({ id, name: res.name, events: res.events }));
      if (satRows.length > 0) result.push({ id: 'sat', label: '卫星 LEO', rows: satRows });

      const gsRows: GanttRow[] = Object.entries(props.timeline.ground_stations)
        .filter(([, res]) => res.events.length > 0)
        .map(([id, res]) => ({ id, name: res.name, events: res.events }));
      if (gsRows.length > 0) result.push({ id: 'gs', label: '地面站', rows: gsRows });

      const geoRows: GanttRow[] = Object.entries(props.timeline.geo_relays)
        .filter(([, res]) => res.events.length > 0)
        .map(([id, res]) => ({ id, name: res.name, events: res.events }));
      if (geoRows.length > 0) result.push({ id: 'geo', label: '中继 GEO', rows: geoRows });

      return result;
    });

    function barStyle(evt: TimelineEvent): Record<string, string> {
      const leftPct = toPct(evt.start);
      const rightPct = toPct(evt.end);
      const widthPct = Math.max(0.4, rightPct - leftPct); // minimum 0.4% width for visibility
      return {
        left: leftPct + '%',
        width: widthPct + '%',
      };
    }

    function barClass(evt: TimelineEvent): string {
      return `bar-${evt.status} bar-dt-${(evt.data_type || 'unknown').toLowerCase()}`;
    }

    function barTooltip(evt: TimelineEvent): string {
      const dtLabel = DATA_TYPE_LABELS[evt.data_type] || evt.data_type;
      const stLabel = STATUS_LABELS[evt.status] || evt.status;
      return `${evt.request_id} · ${dtLabel} · ${stLabel} · ${evt.data_size}MB`;
    }

    function fmtTime(seconds: number): string {
      const total = Math.max(0, Math.floor(seconds));
      const h = Math.floor(total / 3600);
      const m = Math.floor((total % 3600) / 60);
      const s = total % 60;
      return [h, m, s].map((v) => String(v).padStart(2, '0')).join(':');
    }

    function fmtDuration(seconds: number): string {
      const total = Math.max(0, Math.floor(seconds));
      if (total < 60) return `${total}s`;
      if (total < 3600) return `${Math.floor(total / 60)}m ${total % 60}s`;
      return `${Math.floor(total / 3600)}h ${Math.floor((total % 3600) / 60)}m`;
    }

    return {
      LABEL_WIDTH,
      hoveredEvent,
      timeTicks,
      groups,
      barStyle,
      barClass,
      barTooltip,
      fmtDuration,
      statusLabels: STATUS_LABELS,
      dataTypeLabels: DATA_TYPE_LABELS,
    };
  },
});
</script>
