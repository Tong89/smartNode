/**
 * use-theme.ts — Composable for toggling light/dark theme.
 *
 * The active theme is stored as a `data-theme` attribute on `<html>` and
 * persisted to `localStorage` under the key `sn-theme` so it survives page
 * reloads.  Defaults to `light` unless the stored preference says `dark`.
 *
 * Usage:
 *   const { theme, toggleTheme, setTheme, isDark } = useTheme();
 */
import { ref, computed } from 'vue';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'sn-theme';

/** Singleton reactive theme ref shared across all component instances. */
const theme = ref<Theme>(
  (() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
      return stored === 'dark' ? 'dark' : 'light';
    } catch {
      return 'light';
    }
  })()
);

/** Apply the current theme to <html> on first module load. */
function applyTheme(t: Theme): void {
  document.documentElement.setAttribute('data-theme', t);
  try {
    localStorage.setItem(STORAGE_KEY, t);
  } catch {
    // Storage might be blocked (private browsing), ignore.
  }
}

// Initialise on module load.
applyTheme(theme.value);

/**
 * useTheme — returns reactive helpers for theme management.
 */
export function useTheme() {
  const isDark = computed(() => theme.value === 'dark');

  /**
   * Switch to the given theme.
   */
  function setTheme(t: Theme): void {
    theme.value = t;
    applyTheme(t);
  }

  /**
   * Toggle between light and dark.
   */
  function toggleTheme(): void {
    setTheme(theme.value === 'light' ? 'dark' : 'light');
  }

  return {
    /** Currently active theme name ('light' | 'dark'). */
    theme,
    /** True when the dark theme is active. */
    isDark,
    /** Set a specific theme. */
    setTheme,
    /** Toggle between light and dark. */
    toggleTheme,
  };
}
