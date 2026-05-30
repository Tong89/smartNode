<template>
  <section class="tool-panel playback-panel" v-show="visible" aria-label="时间播放控制">
    <div class="panel-heading compact">
      <div>
        <span class="eyebrow">态势回放</span>
        <h2>时间播放控制</h2>
      </div>
      <button
        v-if="isHistorical"
        class="secondary-button live-btn"
        type="button"
        @click="$emit('return-to-live')"
        title="回到实时"
      >
        <i data-lucide="radio"></i>
        回到实时
      </button>
    </div>

    <div class="playback-body">
      <!-- Time cursor display -->
      <div class="playback-time-row">
        <span class="playback-time-label">
          <span
            class="playback-live-dot"
            :class="{ 'is-live': !isHistorical }"
            title="实时"
          ></span>
          {{ cursorLabel }}
        </span>
        <span class="playback-range-label">/ {{ endLabel }}</span>
      </div>

      <!-- Slider -->
      <div class="playback-slider-wrap">
        <input
          type="range"
          class="playback-slider"
          min="0"
          max="1000"
          :value="Math.round(sliderFraction * 1000)"
          :disabled="!hasData"
          @input="onSliderChange"
          :title="`拖动至 ${cursorLabel}`"
        />
      </div>

      <!-- Controls row: play/pause + speed selector -->
      <div class="playback-controls">
        <button
          class="playback-play-btn"
          :class="{ 'is-playing': playing }"
          type="button"
          :disabled="!hasData"
          @click="$emit('toggle-play')"
          :title="playing ? '暂停' : '播放'"
          :aria-pressed="playing"
        >
          <i :data-lucide="playing ? 'pause' : 'play'"></i>
          {{ playing ? '暂停' : '播放' }}
        </button>

        <div class="playback-speed-group" role="group" aria-label="播放倍速">
          <button
            v-for="s in SPEED_OPTIONS"
            :key="s"
            class="speed-btn"
            :class="{ 'is-active': speed === s }"
            type="button"
            @click="$emit('set-speed', s)"
            :title="`${s}× 速`"
          >
            {{ s }}×
          </button>
        </div>
      </div>

      <!-- Historical mode notice -->
      <div v-if="isHistorical" class="playback-notice">
        <i data-lucide="history"></i>
        正在回放历史态势，拖动滑块或点击"回到实时"恢复跟踪
      </div>
    </div>
  </section>
</template>

<script lang="ts">
import { defineComponent, computed, watch, nextTick } from 'vue';
import type { PropType } from 'vue';
import { SPEED_OPTIONS } from '../composables/use-playback';
import type { PlaybackSpeed } from '../composables/use-playback';

export default defineComponent({
  name: 'TimePlayback',

  props: {
    /** Whether this panel is currently shown. */
    visible: {
      type: Boolean,
      required: true,
    },
    /** Whether the backend has delivered valid timeline data. */
    hasData: {
      type: Boolean,
      default: false,
    },
    /** Whether the playback ticker is currently running. */
    playing: {
      type: Boolean,
      default: false,
    },
    /** Whether the cursor has been detached from the live edge. */
    isHistorical: {
      type: Boolean,
      default: false,
    },
    /** Normalised cursor position [0, 1]. */
    sliderFraction: {
      type: Number,
      default: 1,
    },
    /** Human-readable cursor time label (HH:MM:SS). */
    cursorLabel: {
      type: String,
      default: '00:00:00',
    },
    /** Human-readable end-of-window time label (HH:MM:SS). */
    endLabel: {
      type: String,
      default: '00:00:00',
    },
    /** Active playback speed multiplier. */
    speed: {
      type: Number as PropType<PlaybackSpeed>,
      default: 1,
    },
  },

  emits: ['toggle-play', 'seek', 'set-speed', 'return-to-live'],

  setup(props, { emit }) {
    /**
     * Convert the slider's integer value [0, 1000] to a fraction [0, 1]
     * and emit 'seek'.
     */
    function onSliderChange(event: Event): void {
      const raw = (event.target as HTMLInputElement).valueAsNumber;
      emit('seek', raw / 1000);
    }

    // Re-render lucide icons whenever the playing state changes (icon swaps).
    watch(
      () => props.playing,
      () => {
        nextTick(() => {
          const w = window as unknown as { lucide?: { createIcons: () => void } };
          if (w.lucide) w.lucide.createIcons();
        });
      },
    );

    return {
      SPEED_OPTIONS,
      onSliderChange,
    };
  },
});
</script>
