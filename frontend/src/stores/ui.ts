/**
 * ui.ts — Pinia store for transient UI state.
 *
 * Manages active view selection, notice/toast messages, form-ready flags, and
 * the submitting flag so that App.vue and child components can share UI state
 * without prop drilling.
 */
import { defineStore } from 'pinia';
import { ref } from 'vue';

export type ActiveView = 'requests' | 'resources';
export type NoticeType = 'success' | 'error';

export const useUiStore = defineStore('ui', () => {
  // ── State ──────────────────────────────────────────────────────────────────
  const activeView = ref<ActiveView>('requests');
  const notice = ref('');
  const noticeType = ref<NoticeType>('success');
  const submitting = ref(false);
  const resourceFormReady = ref(false);

  let noticeTimer: ReturnType<typeof window.setTimeout> | null = null;

  // ── Actions ────────────────────────────────────────────────────────────────

  /** Switch the active panel view. */
  function setView(view: ActiveView): void {
    activeView.value = view;
  }

  /**
   * Show a toast-style notice message that auto-clears after 4.2 seconds.
   * Calling this again before the timer fires resets the timer.
   */
  function setNotice(message: string, type: NoticeType = 'success'): void {
    notice.value = message;
    noticeType.value = type;
    if (noticeTimer !== null) window.clearTimeout(noticeTimer);
    noticeTimer = window.setTimeout(() => {
      notice.value = '';
    }, 4200);
  }

  /** Mark the resource form as needing re-population from backend data. */
  function invalidateResourceForm(): void {
    resourceFormReady.value = false;
  }

  /** Mark the resource form as populated (no re-sync needed until next reset). */
  function markResourceFormReady(): void {
    resourceFormReady.value = true;
  }

  return {
    // state
    activeView,
    notice,
    noticeType,
    submitting,
    resourceFormReady,
    // actions
    setView,
    setNotice,
    invalidateResourceForm,
    markResourceFormReady,
  };
});
