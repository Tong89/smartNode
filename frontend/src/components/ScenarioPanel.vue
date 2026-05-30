<template>
  <section v-if="visible" class="scenario-panel" aria-label="场景管理">
    <h3 class="panel-title">场景管理</h3>

    <!-- 当前场景摘要 -->
    <div v-if="currentScenario" class="scenario-summary">
      <p class="summary-name">
        <strong>{{ currentScenario.name || '(未命名)' }}</strong>
      </p>
      <p class="summary-meta">
        保存时间: {{ formatDate(currentScenario.saved_at) }}
      </p>
      <p class="summary-counts">
        地面站 {{ currentScenario.ground_station_count }} &nbsp;·&nbsp;
        LEO {{ currentScenario.leo_satellite_count }} &nbsp;·&nbsp;
        GEO {{ currentScenario.geo_relay_count }}
      </p>
    </div>
    <p v-else class="no-scenario">尚未保存任何场景。</p>

    <!-- 场景名称输入 -->
    <div class="field-row">
      <label for="scenario-name">场景名称</label>
      <input
        id="scenario-name"
        v-model="scenarioName"
        type="text"
        maxlength="128"
        placeholder="可选，留空使用默认名称"
        class="text-input"
      />
    </div>

    <!-- 操作按钮组 -->
    <div class="btn-group">
      <button class="btn btn-primary" :disabled="busy" type="button" @click="handleSave">
        {{ busy === 'save' ? '保存中…' : '保存当前场景' }}
      </button>

      <button
        class="btn btn-secondary"
        :disabled="busy || !currentScenario"
        type="button"
        @click="handleLoad"
      >
        {{ busy === 'load' ? '恢复中…' : '恢复已保存场景' }}
      </button>
    </div>

    <!-- 导入导出组 -->
    <div class="io-group">
      <p class="group-label">导入 / 导出</p>

      <div class="export-row">
        <button
          class="btn btn-outline"
          :disabled="busy || !currentScenario"
          type="button"
          @click="handleExport('json')"
        >
          导出 JSON
        </button>
        <button
          class="btn btn-outline"
          :disabled="busy || !currentScenario"
          type="button"
          @click="handleExport('yaml')"
        >
          导出 YAML
        </button>
      </div>

      <div class="import-row">
        <label class="btn btn-outline import-label" :class="{ disabled: busy }">
          导入文件（JSON/YAML）
          <input
            ref="fileInputRef"
            type="file"
            accept=".json,.yaml,.yml"
            class="hidden-file-input"
            :disabled="!!busy"
            @change="handleImport"
          />
        </label>
      </div>
    </div>

    <!-- 操作结果通知 -->
    <transition name="fade">
      <p v-if="notice" :class="['panel-notice', noticeType]">{{ notice }}</p>
    </transition>

    <!-- 最近还原详情 -->
    <div v-if="lastRestoreResult" class="restore-details">
      <p class="restore-title">上次还原详情</p>
      <ul v-if="lastRestoreResult.changes.length">
        <li v-for="(c, i) in lastRestoreResult.changes" :key="i">{{ c }}</li>
      </ul>
      <p v-else class="no-changes">配置未变化，无需调整。</p>
    </div>
  </section>
</template>

<script lang="ts">
import { defineComponent, ref, onMounted } from 'vue';
import {
  fetchCurrentScenario,
  saveScenario,
  loadScenario,
  exportScenario,
  importScenario,
} from '../api/endpoints';
import type { ScenarioData, ScenarioRestoreResult } from '../types/api';

export default defineComponent({
  name: 'ScenarioPanel',

  props: {
    visible: {
      type: Boolean,
      default: true,
    },
  },

  emits: ['scenario-changed'],

  setup(_props, { emit }) {
    const scenarioName = ref('');
    const currentScenario = ref<ScenarioData | null>(null);
    const lastRestoreResult = ref<ScenarioRestoreResult | null>(null);
    const busy = ref<'save' | 'load' | 'export' | 'import' | false>(false);
    const notice = ref('');
    const noticeType = ref<'success' | 'error'>('success');
    const fileInputRef = ref<HTMLInputElement | null>(null);

    let noticeTimer: ReturnType<typeof setTimeout> | null = null;

    function showNotice(msg: string, type: 'success' | 'error' = 'success') {
      notice.value = msg;
      noticeType.value = type;
      if (noticeTimer) clearTimeout(noticeTimer);
      noticeTimer = setTimeout(() => { notice.value = ''; }, 4500);
    }

    function formatDate(iso: string): string {
      if (!iso) return '';
      try {
        return new Date(iso).toLocaleString('zh-CN', {
          year: 'numeric', month: '2-digit', day: '2-digit',
          hour: '2-digit', minute: '2-digit', second: '2-digit',
        });
      } catch {
        return iso;
      }
    }

    async function refreshCurrentScenario() {
      try {
        currentScenario.value = await fetchCurrentScenario();
      } catch {
        // 非致命——保持旧值
      }
    }

    async function handleSave() {
      busy.value = 'save';
      try {
        const result = await saveScenario(scenarioName.value.trim() || undefined);
        currentScenario.value = result;
        showNotice(`场景"${result.name}"已保存。`);
        emit('scenario-changed', result);
      } catch (err: unknown) {
        showNotice((err as Error).message || '保存失败', 'error');
      } finally {
        busy.value = false;
      }
    }

    async function handleLoad() {
      if (!currentScenario.value) return;
      busy.value = 'load';
      try {
        const result = await loadScenario();
        lastRestoreResult.value = result;
        showNotice(`场景"${result.scenario_name}"已恢复。`);
        emit('scenario-changed', currentScenario.value);
      } catch (err: unknown) {
        showNotice((err as Error).message || '恢复失败', 'error');
      } finally {
        busy.value = false;
      }
    }

    async function handleExport(format: 'json' | 'yaml') {
      if (!currentScenario.value) return;
      busy.value = 'export';
      try {
        const blob = await exportScenario(format);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `scenario.${format}`;
        a.click();
        URL.revokeObjectURL(url);
        showNotice(`场景已导出为 ${format.toUpperCase()} 文件。`);
      } catch (err: unknown) {
        showNotice((err as Error).message || '导出失败', 'error');
      } finally {
        busy.value = false;
      }
    }

    async function handleImport(event: Event) {
      const input = event.target as HTMLInputElement;
      const file = input.files?.[0];
      if (!file) return;
      // Reset so the same file can be re-selected
      input.value = '';

      busy.value = 'import';
      try {
        const result = await importScenario(file);
        lastRestoreResult.value = result;
        await refreshCurrentScenario();
        showNotice(`场景"${result.scenario_name}"导入并恢复成功。`);
        emit('scenario-changed', currentScenario.value);
      } catch (err: unknown) {
        showNotice((err as Error).message || '导��失败', 'error');
      } finally {
        busy.value = false;
      }
    }

    onMounted(() => {
      refreshCurrentScenario();
    });

    return {
      scenarioName,
      currentScenario,
      lastRestoreResult,
      busy,
      notice,
      noticeType,
      fileInputRef,
      formatDate,
      handleSave,
      handleLoad,
      handleExport,
      handleImport,
    };
  },
});
</script>

<style scoped>
.scenario-panel {
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.panel-title {
  font-size: 0.875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-muted, #888);
  margin: 0;
}

.scenario-summary {
  background: var(--color-surface-2, rgba(255,255,255,0.04));
  border: 1px solid var(--color-border, rgba(255,255,255,0.1));
  border-radius: 6px;
  padding: 0.6rem 0.8rem;
  font-size: 0.82rem;
  line-height: 1.6;
}
.scenario-summary p { margin: 0; }
.summary-name { font-size: 0.9rem; }
.summary-meta, .summary-counts { color: var(--color-muted, #888); }

.no-scenario {
  font-size: 0.82rem;
  color: var(--color-muted, #888);
  margin: 0;
}

.field-row {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.field-row label {
  font-size: 0.78rem;
  color: var(--color-muted, #888);
}
.text-input {
  background: var(--color-surface-2, rgba(255,255,255,0.06));
  border: 1px solid var(--color-border, rgba(255,255,255,0.15));
  border-radius: 4px;
  color: inherit;
  font-size: 0.85rem;
  padding: 0.35rem 0.6rem;
  width: 100%;
  box-sizing: border-box;
}

.btn-group, .io-group {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.group-label {
  font-size: 0.78rem;
  color: var(--color-muted, #888);
  margin: 0;
}

.export-row, .import-row {
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
}

.btn {
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.82rem;
  padding: 0.4rem 0.85rem;
  transition: opacity 0.15s;
}
.btn:disabled, .btn.disabled { opacity: 0.45; cursor: not-allowed; }

.btn-primary {
  background: var(--color-accent, #3b82f6);
  color: #fff;
}
.btn-secondary {
  background: var(--color-surface-3, rgba(255,255,255,0.1));
  color: inherit;
}
.btn-outline {
  background: transparent;
  border: 1px solid var(--color-border, rgba(255,255,255,0.2));
  color: inherit;
}

.import-label {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
}
.hidden-file-input {
  display: none;
}

.panel-notice {
  font-size: 0.82rem;
  border-radius: 4px;
  padding: 0.4rem 0.7rem;
  margin: 0;
}
.panel-notice.success {
  background: rgba(34, 197, 94, 0.15);
  color: #4ade80;
}
.panel-notice.error {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.restore-details {
  font-size: 0.8rem;
  border-top: 1px solid var(--color-border, rgba(255,255,255,0.1));
  padding-top: 0.5rem;
}
.restore-title {
  font-weight: 600;
  margin: 0 0 0.3rem;
  color: var(--color-muted, #888);
}
.restore-details ul {
  margin: 0;
  padding-left: 1.1rem;
}
.no-changes {
  color: var(--color-muted, #888);
  margin: 0;
}
</style>
