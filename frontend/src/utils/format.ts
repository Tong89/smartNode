/**
 * format.ts — Pure utility functions for formatting display values.
 *
 * All functions are side-effect free and suitable for unit testing without
 * any DOM or browser dependencies.
 */

/** Data-type label map (mirrors the backend's known types). */
export const DATA_TYPE_LABELS: Record<string, string> = {
  TASK_CMD: '任务指令',
  INTEL: '情报信息',
  DATA_SLICE: '数据切片',
  RAW_IMAGE: '原始影像',
};

/** Transmission-status label map. */
export const STATUS_LABELS: Record<string, string> = {
  pending: '排队',
  accepted: '等待',
  transmitting: '传输',
  completed: '完成',
  rejected: '拒绝',
};

/** Transmission-method (link mode) label map. */
export const LINK_MODE_LABELS: Record<string, string> = {
  direct: '直连',
  relay: '中继',
  multi_relay: '多跳',
};

/**
 * Format a simulation time value (in seconds) as "HH:MM:SS".
 *
 * Negative values are clamped to 0.  Non-finite/NaN inputs return "00:00:00".
 *
 * @param totalSeconds - Elapsed time in seconds (may be fractional; truncated).
 */
export function formatTime(totalSeconds: number): string {
  const total = Math.max(0, Math.floor(isFinite(totalSeconds) ? totalSeconds : 0));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return [hours, minutes, secs].map((p) => String(p).padStart(2, '0')).join(':');
}

/**
 * Format a transmission progress value (0–100) as a percentage string like "42%".
 *
 * Values below 0 are clamped to 0; values above 100 are clamped to 100.
 *
 * @param progress - Progress value, typically 0–100.
 */
export function formatProgress(progress: number | undefined | null): string {
  const value = Number(progress ?? 0);
  const clamped = Math.max(0, Math.min(100, isFinite(value) ? value : 0));
  return `${clamped.toFixed(0)}%`;
}

/**
 * Return the human-readable label for a data type key.
 *
 * Falls back to the raw key string if unknown, or '未知' if the key is empty.
 *
 * @param type - Backend data-type key (e.g. "DATA_SLICE").
 */
export function labelDataType(type: string | undefined | null): string {
  if (!type) return '未知';
  return DATA_TYPE_LABELS[type] || type;
}

/**
 * Return the human-readable label for a transmission status.
 *
 * Falls back to the raw status string if unknown, or '未知' if empty.
 *
 * @param status - Backend status value (e.g. "transmitting").
 */
export function labelStatus(status: string | undefined | null): string {
  if (!status) return '未知';
  return STATUS_LABELS[status] || status;
}

/**
 * Return the human-readable label for a transmission-method / link mode.
 *
 * Returns '-' for requests without a known transmission_method.
 *
 * @param method - Backend transmission_method value (e.g. "direct").
 */
export function labelLinkMode(method: string | undefined | null): string {
  if (!method) return '-';
  return LINK_MODE_LABELS[method] || '-';
}
