<template>
  <header class="topbar">
    <div class="brand">
      <span class="brand-mark">CD</span>
      <div>
        <strong>{{ t('app.title') }}</strong>
        <small>{{ t('app.subtitle') }}</small>
      </div>
    </div>

    <div class="status-strip">
      <span :class="['service-dot', backendOnline ? 'is-online' : 'is-offline']"></span>
      <span>{{ backendOnline ? t('topbar.backendOnline') : t('topbar.backendOffline') }}</span>
      <span class="splitter"></span>
      <span>{{ t('topbar.simClock') }} {{ formattedTime }}</span>
    </div>

    <div class="api-control">
      <i data-lucide="server"></i>
      <input
        :value="apiBaseDraft"
        @input="$emit('update:apiBaseDraft', ($event.target as HTMLInputElement).value)"
        @keyup.enter="$emit('save-api-base')"
        :placeholder="t('topbar.apiBasePlaceholder')"
      >
      <button class="icon-button" type="button" @click="$emit('save-api-base')" :title="t('topbar.saveApiBase')">
        <i data-lucide="check"></i>
      </button>

      <!-- Language toggle -->
      <button
        class="icon-button"
        type="button"
        @click="toggleLocale()"
        :title="t('topbar.langToggle')"
        aria-label="toggle language"
      >
        <i data-lucide="languages"></i>
      </button>

      <!-- Theme toggle -->
      <button
        class="icon-button"
        type="button"
        @click="toggleTheme()"
        :title="t('topbar.themeToggle')"
        aria-label="toggle theme"
      >
        <i :data-lucide="isDark ? 'sun' : 'moon'"></i>
      </button>
    </div>
  </header>
</template>

<script lang="ts">
import { defineComponent } from 'vue';
import { useTheme } from '../composables/use-theme';
import { useI18n } from '../i18n';

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

  setup() {
    const { isDark, toggleTheme } = useTheme();
    const { t, toggleLocale } = useI18n();
    return { isDark, toggleTheme, t, toggleLocale };
  },
});
</script>
