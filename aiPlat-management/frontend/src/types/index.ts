export interface ComponentMetrics {
  connections?: number;
  max_connections?: number;
  idle_connections?: number;
  active_queries?: number;
  hit_rate?: number;
  memory_usage_bytes?: number;
  max_memory_bytes?: number;
  keys?: number;
  connected_clients?: number;
  collections?: number;
  total_vectors?: number;
  index_size_bytes?: number;
  queries_per_second?: number;
  requests_total?: number;
  tokens_total?: number;
  average_latency_seconds?: number;
  queue_size?: number;
  max_concurrent?: number;
  queues?: number;
  messages_pending?: number;
  consumers?: number;
  producers?: number;
  throughput_per_second?: number;
  total_space_bytes?: number;
  used_space_bytes?: number;
  available_space_bytes?: number;
  file_count?: number;
  connections_active?: number;
  bytes_sent?: number;
  bytes_received?: number;
  latency_ms?: number;
  total_bytes?: number;
  used_bytes?: number;
  available_bytes?: number;
  usage_percent?: number;
}

export interface ComponentDetails {
  type?: string;
  host?: string;
  port?: number;
  database?: string;
  version?: string;
  path?: string;
  endpoint?: string;
  models?: string[];
  api_endpoint?: string;
  collections?: string[];
  queues?: string[];
  permissions?: string;
  swap_total_bytes?: number;
  swap_used_bytes?: number;
  buffers_bytes?: number;
  cached_bytes?: number;
}

export interface ComponentStatus {
  status: 'healthy' | 'degraded' | 'unhealthy';
  message: string;
  metrics: ComponentMetrics;
  details: ComponentDetails;
  last_check?: string;
}

export interface LayerStatus {
  layer: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  uptime: number;
  components: Record<string, ComponentStatus>;
}

export interface DashboardStatus {
  timestamp: string;
  layers: {
    infra: LayerStatus;
    core: LayerStatus;
    platform: LayerStatus;
    app: LayerStatus;
  };
  overall_status: 'healthy' | 'degraded' | 'unhealthy';
  summary: {
    total_layers: number;
    healthy_layers: number;
    degraded_layers: number;
    unhealthy_layers: number;
  };
}

export type ComponentType = 
  | 'database' 
  | 'cache' 
  | 'llm' 
  | 'vector' 
  | 'messaging' 
  | 'storage' 
  | 'network' 
  | 'memory'
  | 'compute';

export interface ComponentConfig {
  type: string;
  [key: string]: unknown;
}