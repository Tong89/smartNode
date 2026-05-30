/**
 * endpoints.ts — Typed endpoint methods for every smartNode backend route.
 *
 * Each function delegates to the shared `apiClient` singleton and returns a
 * strongly-typed promise that matches the backend response schema defined in
 * `types/api.ts`.
 */

import { apiClient } from './client';
import type {
  SystemData,
  ResourceUtilization,
  ScenarioData,
  ScenarioRestoreResult,
} from '../types/api';

// ── Payload types for write endpoints ───────────────────────────────────────

export interface TransmissionRequestPayload {
  data_type: string;
  data_size: number;
  priority: number;
  max_delay: number;
  selected_ground_stations: string[];
  satellite_id?: string;
}

export interface UpdateGroundStationsPayload {
  count: number;
}

export interface UpdateLeoSatellitesPayload {
  count: number;
}

// ── Response types ───────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  time?: number;
  [key: string]: unknown;
}

export interface TransmissionRequestResult {
  id: string;
  status: 'accepted' | 'rejected' | 'pending' | 'transmitting' | 'completed';
  reject_reason?: string;
  [key: string]: unknown;
}

export interface UpdateResourceResult {
  success: boolean;
  message?: string;
  [key: string]: unknown;
}

// ── Endpoint functions ───────────────────────────────────────────────────────

/**
 * GET /api/health — Liveness check.
 * Returns basic status and server time.
 */
export function fetchHealth(): Promise<HealthResponse> {
  return apiClient.get<HealthResponse>('/api/health');
}

/**
 * GET /api/data — Full simulation snapshot.
 * Returns all satellites, ground stations, geo relays, requests, and stats.
 */
export function fetchData(): Promise<SystemData> {
  return apiClient.get<SystemData>('/api/data');
}

/**
 * GET /api/system_info — Static system configuration.
 * Returns available data types, node counts, and other metadata.
 */
export function fetchSystemInfo(): Promise<Record<string, unknown>> {
  return apiClient.get<Record<string, unknown>>('/api/system_info');
}

/**
 * GET /api/resource_status — Per-resource occupancy summary.
 * Returns a `summary` sub-object with utilization percentages.
 */
export function fetchResourceStatus(): Promise<Record<string, unknown>> {
  return apiClient.get<Record<string, unknown>>('/api/resource_status');
}

/**
 * GET /api/resource_utilization — Aggregate utilization metrics.
 * Returns totals for accepted, rejected, and in-flight requests.
 */
export function fetchResourceUtilization(): Promise<ResourceUtilization> {
  return apiClient.get<ResourceUtilization>('/api/resource_utilization');
}

/**
 * POST /api/request — Submit a new transmission request.
 * Returns the created request object including its assigned `id` and `status`.
 */
export function submitRequest(payload: TransmissionRequestPayload): Promise<TransmissionRequestResult> {
  return apiClient.post<TransmissionRequestResult>('/api/request', payload);
}

/**
 * POST /api/update_ground_stations — Resize the ground-station pool.
 */
export function updateGroundStations(payload: UpdateGroundStationsPayload): Promise<UpdateResourceResult> {
  return apiClient.post<UpdateResourceResult>('/api/update_ground_stations', payload);
}

/**
 * POST /api/update_leo_satellites — Resize the LEO satellite constellation.
 */
export function updateLeoSatellites(payload: UpdateLeoSatellitesPayload): Promise<UpdateResourceResult> {
  return apiClient.post<UpdateResourceResult>('/api/update_leo_satellites', payload);
}

// ── Scenario API ─────────────────────────────────────────────────────────────

/**
 * GET /api/scenario/current — Retrieve the last saved in-memory scenario.
 * Returns null when nothing has been saved yet.
 */
export function fetchCurrentScenario(): Promise<ScenarioData | null> {
  return apiClient.get<ScenarioData | null>('/api/scenario/current');
}

/**
 * POST /api/scenario/save — Snapshot current engine resource config as a scenario.
 */
export function saveScenario(name?: string): Promise<ScenarioData> {
  return apiClient.post<ScenarioData>('/api/scenario/save', { name: name ?? '' });
}

/**
 * POST /api/scenario/load — Restore the last saved scenario to the engine.
 */
export function loadScenario(): Promise<ScenarioRestoreResult> {
  return apiClient.post<ScenarioRestoreResult>('/api/scenario/load', {});
}

/**
 * GET /api/scenario/export — Download the current scenario as a file.
 * Returns the raw Blob so the caller can trigger a browser download.
 */
export async function exportScenario(format: 'json' | 'yaml' = 'json'): Promise<Blob> {
  const url = apiClient.url(`/api/scenario/export?format=${format}`);
  const token = localStorage.getItem('smartnode_token');
  const headers: HeadersInit = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const response = await fetch(url, { method: 'GET', headers });
  if (!response.ok) throw new Error(`导出失败 (${response.status})`);
  return response.blob();
}

/**
 * POST /api/scenario/import — Upload a JSON or YAML scenario file and restore it.
 */
export async function importScenario(file: File): Promise<ScenarioRestoreResult> {
  const url = apiClient.url('/api/scenario/import');
  const token = localStorage.getItem('smartnode_token');
  const headers: HeadersInit = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(url, { method: 'POST', headers, body: form });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error((payload as Record<string, unknown>).message as string || '导入失败');
  }
  const payload = await response.json();
  // Unwrap envelope if present
  if (payload && payload.code === 0 && 'data' in payload) return payload.data;
  return payload;
}
