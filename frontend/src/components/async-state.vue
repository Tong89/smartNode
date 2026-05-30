<template>
  <!-- Loading state: skeleton placeholder rows -->
  <div v-if="loading" class="async-state async-state--loading" :aria-label="t('error.loading')">
    <div
      v-for="n in skeletonRows"
      :key="n"
      class="skeleton async-state__skeleton-row"
      :style="{ width: rowWidth(n), height: rowHeight }"
    ></div>
  </div>

  <!-- Error state: message + optional retry -->
  <div v-else-if="error" class="async-state async-state--error" role="alert">
    <i data-lucide="alert-circle" class="async-state__icon async-state__icon--error"></i>
    <span class="async-state__message">{{ errorMessage || t('error.boundary') }}</span>
    <button
      v-if="showRetry"
      class="async-state__retry"
      type="button"
      @click="$emit('retry')"
    >
      <i data-lucide="refresh-cw"></i>
      {{ t('error.retry') }}
    </button>
  </div>

  <!-- Empty state: no data yet -->
  <div v-else-if="empty" class="async-state async-state--empty">
    <i data-lucide="inbox" class="async-state__icon async-state__icon--empty"></i>
    <span class="async-state__message">{{ emptyMessage || t('error.empty') }}</span>
    <span v-if="showEmptyHint" class="async-state__hint">{{ t('error.emptyHint') }}</span>
  </div>

  <!-- Happy path: render slotted content -->
  <slot v-else />
</template>

<script lang="ts">
/**
 * async-state.vue — Unified loading / empty / error state wrapper.
 *
 * Renders one of three non-happy-path states based on Boolean props, or
 * falls through to the default slot when none are active.
 *
 * Props:
 *   loading       — show skeleton rows
 *   error         — show error message
 *   errorMessage  — custom error text (falls back to i18n key)
 *   showRetry     — show a retry button when in error state
 *   empty         — show the empty-state UI
 *   emptyMessage  — custom empty text
 *   showEmptyHint — show a secondary hint line in empty state
 *   skeletonRows  — number of skeleton rows (default 3)
 *   rowHeight     — CSS height of each skeleton row (default '1rem')
 *
 * Emits:
 *   retry — when the user clicks the retry button
 */
import { defineComponent } from 'vue';
import { t } from '../i18n';

export default defineComponent({
  name: 'AsyncState',

  props: {
    /** Show the loading skeleton. */
    loading: {
      type: Boolean,
      default: false,
    },
    /** Show the error state. */
    error: {
      type: Boolean,
      default: false,
    },
    /** Custom error message text. */
    errorMessage: {
      type: String,
      default: '',
    },
    /** Show a retry button in the error state. */
    showRetry: {
      type: Boolean,
      default: true,
    },
    /** Show the empty state (no data). */
    empty: {
      type: Boolean,
      default: false,
    },
    /** Custom empty-state message text. */
    emptyMessage: {
      type: String,
      default: '',
    },
    /** Show the secondary hint line in empty state. */
    showEmptyHint: {
      type: Boolean,
      default: false,
    },
    /** Number of skeleton placeholder rows to render. */
    skeletonRows: {
      type: Number,
      default: 3,
    },
    /** CSS height value for each skeleton row. */
    rowHeight: {
      type: String,
      default: '1rem',
    },
  },

  emits: ['retry'],

  setup() {
    /**
     * Vary each skeleton row width slightly so the placeholder looks natural.
     * Rows cycle through 100 / 85 / 70 % widths.
     */
    function rowWidth(n: number): string {
      const widths = ['100%', '85%', '70%'];
      return widths[(n - 1) % widths.length];
    }

    return { t, rowWidth };
  },
});
</script>

<style scoped>
.async-state {
  display:         flex;
  flex-direction:  column;
  align-items:     center;
  justify-content: center;
  gap:             0.6rem;
  padding:         1.5rem 1rem;
  min-height:      80px;
  color:           var(--text-secondary, #4a5568);
  text-align:      center;
}

/* ── Loading ─────────────────────────────────────────────────────────── */
.async-state--loading {
  align-items: flex-start;
  gap:         0.5rem;
}

.async-state__skeleton-row {
  border-radius: 4px;
}

/* ── Error ───────────────────────────────────────────────────────────── */
.async-state--error {
  color: var(--color-error, #dc2626);
}

/* ── Empty ───────────────────────────────────────────────────────────── */
.async-state--empty {
  color: var(--text-muted, #8a97ab);
}

.async-state__icon {
  width:  1.75rem;
  height: 1.75rem;
  flex-shrink: 0;
}

.async-state__icon--error {
  color: var(--color-error, #dc2626);
}

.async-state__icon--empty {
  color: var(--text-muted, #8a97ab);
}

.async-state__message {
  font-size:   0.9rem;
  font-weight: 500;
}

.async-state__hint {
  font-size: 0.8rem;
  color:     var(--text-muted, #8a97ab);
}

.async-state__retry {
  display:       inline-flex;
  align-items:   center;
  gap:           0.35rem;
  margin-top:    0.25rem;
  padding:       0.3rem 0.8rem;
  border:        1px solid var(--color-error, #dc2626);
  border-radius: 4px;
  background:    transparent;
  color:         var(--color-error, #dc2626);
  font-size:     0.82rem;
  cursor:        pointer;
  transition:    background 0.15s, color 0.15s;
}

.async-state__retry:hover {
  background: var(--color-error, #dc2626);
  color:      var(--text-inverse, #fff);
}
</style>
