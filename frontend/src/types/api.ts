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
  bandwidth?: number;
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
