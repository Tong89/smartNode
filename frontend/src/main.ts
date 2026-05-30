/**
 * SFC 应用入口 — 将 App.vue 根组件挂载到 #app，替换原 app.js 的 Vue.createApp 调用。
 * lucide 图标在每次 updated 钩子后通过 App.vue 触发，Cesium 生命周期由 CesiumScene.vue 管理。
 * Pinia store 在应用创建后立即注册，供所有组件共享仿真态势与 UI 状态。
 *
 * Theme & i18n are initialised here via their respective composable/module so
 * the correct `data-theme` attribute and localStorage-persisted locale are
 * applied before the first paint.
 */
import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
// Import CSS variable tokens — applied globally via [data-theme] selectors.
import './styles/themes.css';
// Importing the i18n index module has the side-effect of reading the stored
// locale from localStorage; importing use-theme applies the stored theme to
// <html data-theme="…"> before the first render.
import './i18n/index';
import { useTheme } from './composables/use-theme';

// Ensure theme is applied immediately (the composable singleton handles it on
// first import, but calling useTheme() here makes the dependency explicit).
useTheme();

// Trigger lucide icon rendering after every DOM update
// (vendor.js exposes window.lucide; we hook into the app's afterEach update cycle)
const app = createApp(App);
const pinia = createPinia();
app.use(pinia);

app.config.globalProperties.$renderIcons = function () {
  const w = window as unknown as { lucide?: { createIcons: () => void } };
  if (w.lucide) {
    w.lucide.createIcons();
  }
};

// Re-render icons on every component update so dynamically inserted
// <i data-lucide="..."> elements are always processed
app.mixin({
  updated() {
    const w = window as unknown as { lucide?: { createIcons: () => void } };
    if (w.lucide) {
      w.lucide.createIcons();
    }
  },
});

app.mount('#app');
