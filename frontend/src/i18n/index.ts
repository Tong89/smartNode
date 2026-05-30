/**
 * i18n/index.ts — Lightweight i18n helper (no external dependencies).
 *
 * Supports zh (Simplified Chinese) and en (English).  The active locale is
 * stored in `localStorage` under the key `sn-locale` so it persists across
 * page loads.  The module exports a singleton reactive `locale` ref and a
 * `t()` helper that resolves dot-separated keys against the active messages.
 *
 * Example:
 *   import { t, locale, setLocale } from '@/i18n';
 *   t('topbar.backendOnline')  // → '后端在线' | 'Backend Online'
 */
import { ref, computed } from 'vue';
import zh from './zh';
import en from './en';

export type Locale = 'zh' | 'en';

const STORAGE_KEY = 'sn-locale';

/** All message bundles keyed by locale. */
const messages: Record<Locale, typeof zh> = { zh, en };

/** Singleton reactive locale ref shared across the whole app. */
const locale = ref<Locale>(
  (() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY) as Locale | null;
      return stored === 'en' ? 'en' : 'zh';
    } catch {
      return 'zh';
    }
  })()
);

/** Persist locale on change. */
function persistLocale(l: Locale): void {
  try {
    localStorage.setItem(STORAGE_KEY, l);
  } catch {
    // Ignore storage errors in restricted environments.
  }
}

/**
 * Switch the active locale.
 */
function setLocale(l: Locale): void {
  locale.value = l;
  persistLocale(l);
}

/**
 * Toggle between zh and en.
 */
function toggleLocale(): void {
  setLocale(locale.value === 'zh' ? 'en' : 'zh');
}

/**
 * Resolve a dot-separated key path against the active locale's messages.
 * Falls back to `zh` if the key is missing in the current locale.
 * Returns the key string itself if unresolved in both bundles.
 *
 * @example  t('app.loading')  // → '加载中…' | 'Loading…'
 */
function t(key: string): string {
  const parts = key.split('.');
  // Try active locale first, then fall back to zh.
  for (const bundle of [messages[locale.value] as Record<string, unknown>, messages.zh as Record<string, unknown>]) {
    let node: unknown = bundle;
    for (const part of parts) {
      if (typeof node !== 'object' || node === null) { node = undefined; break; }
      node = (node as Record<string, unknown>)[part];
    }
    if (typeof node === 'string') return node;
  }
  return key;
}

/** Reactive derived helper for template usage via `computed`. */
function useI18n() {
  const currentMessages = computed(() => messages[locale.value]);
  return {
    locale,
    t,
    setLocale,
    toggleLocale,
    currentMessages,
  };
}

export { locale, t, setLocale, toggleLocale, useI18n };
