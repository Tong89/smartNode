/**
 * use-playback.ts — Composable managing time playback state for situational replay.
 *
 * Provides play/pause control, a draggable time cursor, playback speed selection,
 * and a "return to live" action.  When the cursor is dragged away from the live
 * edge the simulation stops following the real-time clock and displays historical
 * state calculated via the resource_timeline time-window.
 */

import { ref, computed, onBeforeUnmount } from 'vue';

/** Supported playback speed multipliers (×1, ×2, ×5, ×10). */
export const SPEED_OPTIONS = [1, 2, 5, 10] as const;
export type PlaybackSpeed = (typeof SPEED_OPTIONS)[number];

/** Tick interval for the internal playback clock (ms). */
const TICK_MS = 200;

export function usePlayback(
  /** Reactive getter returning the current live simulation time (seconds). */
  getLiveTime: () => number,
  /** Reactive getter returning the timeline time_range [start, end] (seconds). */
  getTimeRange: () => [number, number],
  /** Callback invoked whenever the playback cursor moves to a new time. */
  onSeek: (time: number) => void,
) {
  // ── State ──────────────────────────────────────────────────────────────────
  /** Whether playback is actively advancing the cursor. */
  const playing = ref(false);

  /** Whether the cursor has been detached from the live edge. */
  const isHistorical = ref(false);

  /** The current cursor position in simulation seconds. */
  const cursorTime = ref(getLiveTime());

  /** Active playback speed multiplier. */
  const speed = ref<PlaybackSpeed>(1);

  let ticker: ReturnType<typeof window.setInterval> | null = null;

  // ── Computed ───────────────────────────────────────────────────────────────

  /** Normalised slider value [0, 1] derived from cursorTime within the time range. */
  const sliderFraction = computed<number>(() => {
    const [start, end] = getTimeRange();
    const span = end - start;
    if (span <= 0) return 1;
    return Math.max(0, Math.min(1, (cursorTime.value - start) / span));
  });

  /** Human-readable HH:MM:SS label for the current cursor position. */
  const cursorLabel = computed<string>(() => fmtTime(cursorTime.value));

  // ── Private helpers ────────────────────────────────────────────────────────

  function fmtTime(seconds: number): string {
    const total = Math.max(0, Math.floor(seconds));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    return [h, m, s].map((v) => String(v).padStart(2, '0')).join(':');
  }

  function stopTicker(): void {
    if (ticker !== null) {
      window.clearInterval(ticker);
      ticker = null;
    }
  }

  function startTicker(): void {
    stopTicker();
    ticker = window.setInterval(() => {
      const [start, end] = getTimeRange();
      const next = cursorTime.value + (TICK_MS / 1000) * speed.value;
      if (next >= end) {
        // Reached the live edge — snap and exit historical mode.
        cursorTime.value = end;
        isHistorical.value = false;
        playing.value = false;
        stopTicker();
        onSeek(end);
      } else {
        cursorTime.value = Math.max(start, next);
        onSeek(cursorTime.value);
      }
    }, TICK_MS);
  }

  // ── Public actions ─────────────────────────────────────────────────────────

  /** Toggle play / pause. */
  function togglePlay(): void {
    if (playing.value) {
      playing.value = false;
      stopTicker();
    } else {
      // If already at the live edge, reset to start of window for replay.
      const [start, end] = getTimeRange();
      if (cursorTime.value >= end) {
        cursorTime.value = start;
        isHistorical.value = true;
        onSeek(start);
      }
      playing.value = true;
      startTicker();
    }
  }

  /**
   * Called when the user drags the range slider.
   * @param fraction — value in [0, 1] representing position in the time range.
   */
  function onSliderInput(fraction: number): void {
    const [start, end] = getTimeRange();
    const span = end - start;
    const newTime = start + fraction * span;
    cursorTime.value = newTime;
    isHistorical.value = newTime < end - 1; // treat within 1s of live as "live"
    onSeek(newTime);
    // Pause playback while scrubbing so the ticker does not interfere.
    if (playing.value) {
      playing.value = false;
      stopTicker();
    }
  }

  /** Snap back to the live edge and resume real-time following. */
  function returnToLive(): void {
    playing.value = false;
    stopTicker();
    const liveNow = getLiveTime();
    cursorTime.value = liveNow;
    isHistorical.value = false;
    onSeek(liveNow);
  }

  /** Select a new playback speed multiplier. */
  function setSpeed(s: PlaybackSpeed): void {
    speed.value = s;
    // Restart the ticker at the new rate if already playing.
    if (playing.value) startTicker();
  }

  // Sync cursor to live time whenever we are not in historical / playing mode.
  function syncLive(): void {
    if (!isHistorical.value && !playing.value) {
      cursorTime.value = getLiveTime();
    }
  }

  // ── Cleanup ────────────────────────────────────────────────────────────────
  onBeforeUnmount(() => {
    stopTicker();
  });

  return {
    playing,
    isHistorical,
    cursorTime,
    speed,
    sliderFraction,
    cursorLabel,
    SPEED_OPTIONS,
    togglePlay,
    onSliderInput,
    returnToLive,
    setSpeed,
    syncLive,
    fmtTime,
  };
}
