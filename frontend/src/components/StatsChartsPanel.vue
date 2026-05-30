<template>
  <section class="tool-panel stats-charts-panel" v-show="visible">
    <div class="panel-heading">
      <div>
        <span class="eyebrow">统计分析</span>
        <h2>决策指标图表</h2>
      </div>
      <button class="icon-button" type="button" @click="$emit('refresh')" title="刷新">
        <i data-lucide="refresh-cw"></i>
      </button>
    </div>

    <!-- Zero-state: no requests yet -->
    <div v-if="totalRequests === 0" class="empty-state charts-empty">
      <i data-lucide="bar-chart-2"></i>
      <p>暂无请求数据，图表将在首次请求后显示</p>
    </div>

    <div v-else class="charts-body">

      <!-- ── 接受率 / 拒绝率 环形图 ─────────────────────────────────────── -->
      <div class="chart-card">
        <div class="chart-card-title">接受率 / 拒绝率</div>
        <div class="donut-row">
          <svg class="donut-svg" viewBox="0 0 100 100" aria-label="接受率环形图">
            <!-- background ring -->
            <circle cx="50" cy="50" r="38" fill="none" stroke="var(--line)" stroke-width="14" />
            <!-- accepted arc -->
            <circle
              cx="50" cy="50" r="38"
              fill="none"
              stroke="var(--accent)"
              stroke-width="14"
              stroke-linecap="butt"
              :stroke-dasharray="acceptedArc"
              stroke-dashoffset="0"
              transform="rotate(-90 50 50)"
            />
            <!-- center label -->
            <text x="50" y="46" text-anchor="middle" class="donut-pct">{{ acceptancePct }}%</text>
            <text x="50" y="59" text-anchor="middle" class="donut-label">接受率</text>
          </svg>

          <div class="donut-legend">
            <div class="donut-legend-row">
              <span class="legend-swatch" style="background: var(--accent)"></span>
              <span>接受</span>
              <strong>{{ acceptedRequests }}</strong>
            </div>
            <div class="donut-legend-row">
              <span class="legend-swatch" style="background: var(--red)"></span>
              <span>拒绝</span>
              <strong>{{ rejectedRequests }}</strong>
            </div>
            <div class="donut-legend-row">
              <span class="legend-swatch" style="background: var(--muted); opacity: 0.4"></span>
              <span>合计</span>
              <strong>{{ totalRequests }}</strong>
            </div>
          </div>
        </div>
      </div>

      <!-- ── 吞吐量 sparkline ─────────────────────────────────────────────── -->
      <div class="chart-card">
        <div class="chart-card-title">
          吞吐量
          <span class="chart-unit">Mbps</span>
        </div>
        <div class="sparkline-row">
          <svg class="sparkline-svg" viewBox="0 0 200 56" preserveAspectRatio="none" aria-label="吞吐量折线图">
            <!-- grid lines -->
            <line x1="0" y1="14" x2="200" y2="14" stroke="var(--line)" stroke-width="0.8" />
            <line x1="0" y1="28" x2="200" y2="28" stroke="var(--line)" stroke-width="0.8" />
            <line x1="0" y1="42" x2="200" y2="42" stroke="var(--line)" stroke-width="0.8" />
            <!-- sparkline path -->
            <polyline
              v-if="sparklinePoints"
              :points="sparklinePoints"
              fill="none"
              stroke="var(--accent)"
              stroke-width="2"
              stroke-linejoin="round"
              stroke-linecap="round"
            />
            <!-- area fill -->
            <polygon
              v-if="sparklineAreaPoints"
              :points="sparklineAreaPoints"
              fill="var(--accent)"
              opacity="0.12"
            />
            <!-- current value dot -->
            <circle
              v-if="sparklineDotX !== null"
              :cx="sparklineDotX"
              :cy="sparklineDotY"
              r="3"
              fill="var(--accent)"
            />
          </svg>
          <div class="sparkline-stat">
            <strong>{{ currentThroughput.toFixed(2) }}</strong>
            <span>当前 Mbps</span>
          </div>
        </div>
      </div>

      <!-- ── 拒因分布 横向条形图 ────────────────────────────────────────── -->
      <div class="chart-card">
        <div class="chart-card-title">拒绝原因分布</div>
        <div v-if="rejectionEntries.length === 0" class="empty-state charts-empty-small">
          <span>暂无拒绝记录</span>
        </div>
        <div v-else class="bar-chart">
          <div
            v-for="entry in rejectionEntries"
            :key="entry.reason"
            class="bar-row"
          >
            <div class="bar-label" :title="entry.reason">{{ entry.label }}</div>
            <div class="bar-track">
              <div
                class="bar-fill"
                :style="{ width: entry.pct + '%' }"
                :title="`${entry.count} 次 (${entry.pct.toFixed(1)}%)`"
              ></div>
            </div>
            <div class="bar-count">{{ entry.count }}</div>
          </div>
        </div>
      </div>

    </div>
  </section>
</template>

<script lang="ts">
import { defineComponent, computed } from 'vue';
import type { PropType } from 'vue';
import type { DecisionMetrics } from '../types/api';

/** Human-readable labels for known rejection reason codes */
const REJECTION_LABELS: Record<string, string> = {
  no_satellite: '无可用卫星',
  no_ground_station: '无可用地面站',
  no_geo_relay: '无可用中继',
  bandwidth_exceeded: '带宽超限',
  link_unavailable: '链路不可用',
  resource_busy: '资源繁忙',
  low_priority: '优先级过低',
  timeout: '请求超时',
};

export default defineComponent({
  name: 'StatsChartsPanel',

  props: {
    visible: {
      type: Boolean,
      required: true,
    },
    /** Accepted request count */
    acceptedRequests: {
      type: Number,
      required: true,
    },
    /** Rejected request count */
    rejectedRequests: {
      type: Number,
      required: true,
    },
    /** Total request count */
    totalRequests: {
      type: Number,
      required: true,
    },
    /** Decision metrics from /api/resource_utilization */
    decisionMetrics: {
      type: Object as PropType<DecisionMetrics>,
      required: true,
    },
    /** Rejection distribution (reason code → count) */
    rejectionDistribution: {
      type: Object as PropType<Record<string, number>>,
      required: true,
    },
    /** Sliding window of throughput samples for sparkline */
    throughputHistory: {
      type: Array as PropType<number[]>,
      required: true,
    },
  },

  emits: ['refresh'],

  setup(props) {
    // ── Donut chart ──────────────────────────────────────────────────────────

    const CIRCUMFERENCE = 2 * Math.PI * 38; // ≈ 238.76

    const acceptancePct = computed(() => {
      if (!props.totalRequests) return 0;
      return Math.round((props.acceptedRequests / props.totalRequests) * 100);
    });

    /** stroke-dasharray value for the accepted arc */
    const acceptedArc = computed(() => {
      const filled = (acceptancePct.value / 100) * CIRCUMFERENCE;
      return `${filled.toFixed(2)} ${(CIRCUMFERENCE - filled).toFixed(2)}`;
    });

    // ── Sparkline ───────────────────────��────────────────────────────────────

    const currentThroughput = computed(() => props.decisionMetrics.throughput_mbps);

    const sparklinePoints = computed<string | null>(() => {
      const samples = props.throughputHistory;
      if (samples.length < 2) return null;
      const maxVal = Math.max(...samples, 0.001);
      const W = 200;
      const H = 56;
      const pad = 4;
      return samples
        .map((v, i) => {
          const x = pad + (i / (samples.length - 1)) * (W - pad * 2);
          const y = H - pad - (v / maxVal) * (H - pad * 2);
          return `${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join(' ');
    });

    const sparklineAreaPoints = computed<string | null>(() => {
      const samples = props.throughputHistory;
      if (samples.length < 2) return null;
      const maxVal = Math.max(...samples, 0.001);
      const W = 200;
      const H = 56;
      const pad = 4;
      const pts = samples.map((v, i) => {
        const x = pad + (i / (samples.length - 1)) * (W - pad * 2);
        const y = H - pad - (v / maxVal) * (H - pad * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      });
      const firstX = pad.toFixed(1);
      const lastX = (W - pad).toFixed(1);
      const bottom = H.toFixed(1);
      return `${firstX},${bottom} ${pts.join(' ')} ${lastX},${bottom}`;
    });

    const sparklineDotX = computed<number | null>(() => {
      const samples = props.throughputHistory;
      if (samples.length < 2) return null;
      return 200 - 4; // rightmost x
    });

    const sparklineDotY = computed<number | null>(() => {
      const samples = props.throughputHistory;
      if (samples.length < 2) return null;
      const maxVal = Math.max(...samples, 0.001);
      const last = samples[samples.length - 1];
      return 56 - 4 - (last / maxVal) * (56 - 8);
    });

    // ── Bar chart ────────────────────────────────────────────────────────────

    interface BarEntry {
      reason: string;
      label: string;
      count: number;
      pct: number;
    }

    const rejectionEntries = computed<BarEntry[]>(() => {
      const dist = props.rejectionDistribution;
      const total = Object.values(dist).reduce((s, v) => s + v, 0);
      if (!total) return [];
      const maxCount = Math.max(...Object.values(dist));
      return Object.entries(dist)
        .sort((a, b) => b[1] - a[1])
        .map(([reason, count]) => ({
          reason,
          label: REJECTION_LABELS[reason] || reason,
          count,
          pct: (count / maxCount) * 100,
        }));
    });

    return {
      acceptancePct,
      acceptedArc,
      currentThroughput,
      sparklinePoints,
      sparklineAreaPoints,
      sparklineDotX,
      sparklineDotY,
      rejectionEntries,
    };
  },
});
</script>
