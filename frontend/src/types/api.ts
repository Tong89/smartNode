// 后端 API 响应类型定义（供前端 TS 模块共享）。

export interface Envelope<T> {
  code: number;
  data: T;
  request_id?: string;
}

export interface ApiError {
  status: 'error';
  code: string;
  message: string;
  request_id?: string;
  reject_reason?: string;
}

export interface Satellite {
  id: string;
  name: string;
  type: 'LEO' | 'MEO' | 'GEO';
  lat: number;
  lon: number;
  alt: number;
  orbit_period?: number;
  /** Minimum elevation angle (degrees) for visibility — used to compute coverage radius */
  min_elevation?: number;
}

export interface GroundStation {
  id: string;
  name: string;
  lat: number;
  lon: number;
  antenna_type: string;
  max_links?: number;
}

export interface GeoRelay {
  id: string;
  name: string;
  lon: number;
  lat?: number;
  alt?: number;
  bandwidth?: number;
  /** Field-of-view half-angle (degrees) for GEO relay coverage ring */
  coverage_fov?: number;
  /** Minimum elevation angle (degrees) for GEO relay visibility ring */
  coverage_min_elevation?: number;
}

export interface TransmissionRequest {
  id: string;
  data_type: string;
  status: 'pending' | 'accepted' | 'transmitting' | 'completed' | 'rejected';
  priority: number;
  progress: number;
  source: 'user' | 'background';
  reject_reason?: string | null;
  transmission_rate?: number;
}

export interface SystemData {
  time: number;
  satellites: Satellite[];
  ground_stations: GroundStation[];
  geo_relays: GeoRelay[];
  requests: TransmissionRequest[];
  stats: Record<string, unknown>;
}

export interface ResourceUtilization {
  resource_utilization: { satellites: number; ground_stations: number; geo_relays: number };
  total_requests: number;
  accepted_requests: number;
  rejected_requests: number;
}

/** 场景对象 (Scenario Schema v1) */
export interface ScenarioData {
  version: string;
  name: string;
  saved_at: string;
  ground_station_count: number;
  leo_satellite_count: number;
  geo_relay_count: number;
  data_types: string[];
}

/** /api/scenario/load 和 /api/scenario/import 的还原结果 */
export interface ScenarioRestoreResult {
  restored: boolean;
  scenario_name: string;
  saved_at: string;
  changes: string[];
  ground_station_count: number;
  leo_satellite_count: number;
}

/** 单条资源占用事件（来自 /api/resource_timeline） */
export interface TimelineEvent {
  request_id: string;
  start: number;
  end: number;
  status: 'transmitting' | 'completed';
  data_type: string;
  data_size: number;
  priority: number;
  source: string;
  progress: number;
}

/** 单个资源的时间轴信息 */
export interface TimelineResource {
  name: string;
  type: string;
  antenna?: string;
  events: TimelineEvent[];
}

/** /api/resource_timeline 的完整响应结构 */
export interface ResourceTimeline {
  current_time: number;
  time_range: [number, number];
  satellites: Record<string, TimelineResource>;
  ground_stations: Record<string, TimelineResource>;
  geo_relays: Record<string, TimelineResource>;
}
