<template>
  <slot v-if="!caught" />

  <div v-else class="error-boundary">
    <div class="error-boundary__icon">
      <i data-lucide="alert-triangle"></i>
    </div>
    <h3 class="error-boundary__title">{{ t('error.boundary') }}</h3>
    <p class="error-boundary__detail">{{ t('error.boundaryDetail') }}</p>
    <pre v-if="errorMessage" class="error-boundary__message">{{ errorMessage }}</pre>
    <button class="error-boundary__retry btn-primary" type="button" @click="reset">
      <i data-lucide="refresh-cw"></i>
      {{ t('error.retry') }}
    </button>
  </div>
</template>

<script lang="ts">
/**
 * error-boundary.vue — Global Vue error boundary component.
 *
 * Wraps any subtree with `onErrorCaptured` to intercept thrown errors and
 * render a contained error UI instead of letting the white-screen propagate.
 * The slot is restored on `reset()` so the user can retry without a full
 * page reload.
 *
 * Usage:
 *   <ErrorBoundary>
 *     <SomeRiskyPanel />
 *   </ErrorBoundary>
 */
import { defineComponent, ref, onErrorCaptured, nextTick } from 'vue';
import { t } from '../i18n';

export default defineComponent({
  name: 'ErrorBoundary',

  setup() {
    const caught = ref(false);
    const errorMessage = ref('');

    onErrorCaptured((err: unknown, _instance, info) => {
      caught.value = true;
      const msg = err instanceof Error ? err.message : String(err);
      errorMessage.value = `${msg}\n\n(${info})`;
      // Return false to stop the error propagating further up the tree.
      return false;
    });

    async function reset() {
      caught.value = false;
      errorMessage.value = '';
      // Give Vue a tick to unmount the error UI before re-rendering the slot.
      await nextTick();
    }

    return { caught, errorMessage, t, reset };
  },
});
</script>

<style scoped>
.error-boundary {
  display:          flex;
  flex-direction:   column;
  align-items:      center;
  justify-content:  center;
  gap:              0.75rem;
  padding:          2rem 1.5rem;
  border-radius:    8px;
  border:           1px solid var(--color-error, #dc2626);
  background:       var(--bg-surface, #fff);
  color:            var(--text-primary, #1a1f2e);
  text-align:       center;
  min-height:       120px;
}

.error-boundary__icon {
  color: var(--color-error, #dc2626);
  font-size: 2rem;
  line-height: 1;
}

.error-boundary__title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-error, #dc2626);
}

.error-boundary__detail {
  margin: 0;
  font-size: 0.85rem;
  color: var(--text-secondary, #4a5568);
  max-width: 32rem;
}

.error-boundary__message {
  font-family: monospace;
  font-size:   0.78rem;
  white-space: pre-wrap;
  word-break:  break-all;
  background:  var(--bg-elevated, #e8ecf4);
  border:      1px solid var(--border-subtle, #d5dae6);
  border-radius: 4px;
  padding:     0.5rem 0.75rem;
  max-width:   32rem;
  max-height:  8rem;
  overflow:    auto;
  text-align:  left;
  color:       var(--text-secondary, #4a5568);
}

.error-boundary__retry {
  display:       inline-flex;
  align-items:   center;
  gap:           0.4rem;
  padding:       0.4rem 1rem;
  border:        none;
  border-radius: 4px;
  background:    var(--btn-primary-bg, #2563eb);
  color:         var(--btn-primary-text, #fff);
  font-size:     0.85rem;
  cursor:        pointer;
  transition:    background 0.15s;
}

.error-boundary__retry:hover {
  background: var(--accent-hover, #1d4ed8);
}
</style>
