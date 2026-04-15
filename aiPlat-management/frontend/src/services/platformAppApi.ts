import { apiClient } from './apiClient';

export interface GatewayRoute {
  id: string;
  name: string;
  path: string;
  backend: string;
  methods: string[];
  enabled: boolean;
  rate_limit: number;
  timeout: number;
  created_at: string;
  updated_at: string;
}

export interface GatewayRouteListResponse {
  routes: GatewayRoute[];
  total: number;
}

export const gatewayApi = {
  list: async (params?: { enabled?: boolean }) => {
    const query = new URLSearchParams();
    if (params?.enabled !== undefined) query.set('enabled', String(params.enabled));
    const qs = query.toString();
    return apiClient.get<GatewayRouteListResponse>(`/platform/gateway/routes${qs ? '?' + qs : ''}`);
  },
  get: async (id: string) => {
    return apiClient.get<GatewayRoute>(`/platform/gateway/routes/${id}`);
  },
  create: async (data: Partial<GatewayRoute>) => {
    return apiClient.post<GatewayRoute>('/platform/gateway/routes', data);
  },
  update: async (id: string, data: Partial<GatewayRoute>) => {
    return apiClient.put<GatewayRoute>(`/platform/gateway/routes/${id}`, data);
  },
  delete: async (id: string) => {
    return apiClient.delete<{ status: string }>(`/platform/gateway/routes/${id}`);
  },
  getMetrics: async () => {
    return apiClient.get<{ total_requests: number; success_rate: number; avg_latency_ms: number; active_routes: number }>('/platform/gateway/metrics');
  },
};

export interface AuthUser {
  id: string;
  username: string;
  email: string;
  role: string;
  status: 'active' | 'inactive' | 'locked';
  last_login: string | null;
  created_at: string;
}

export interface AuthUserListResponse {
  users: AuthUser[];
  total: number;
}

export const authApi = {
  list: async (params?: { role?: string; status?: string }) => {
    const query = new URLSearchParams();
    if (params?.role) query.set('role', params.role);
    if (params?.status) query.set('status', params.status);
    const qs = query.toString();
    return apiClient.get<AuthUserListResponse>(`/platform/auth/users${qs ? '?' + qs : ''}`);
  },
  create: async (data: { username: string; email: string; role: string; password: string }) => {
    return apiClient.post<AuthUser>('/platform/auth/users', data);
  },
  update: async (id: string, data: Partial<AuthUser>) => {
    return apiClient.put<AuthUser>(`/platform/auth/users/${id}`, data);
  },
  delete: async (id: string) => {
    return apiClient.delete<{ status: string }>(`/platform/auth/users/${id}`);
  },
};

export interface TenantInfo {
  id: string;
  name: string;
  description: string;
  quota: { gpu_limit: number; storage_limit_gb: number; max_agents: number };
  status: 'active' | 'suspended' | 'pending';
  user_count: number;
  created_at: string;
}

export interface TenantListResponse {
  tenants: TenantInfo[];
  total: number;
}

export const tenantApi = {
  list: async (params?: { status?: string }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    const qs = query.toString();
    return apiClient.get<TenantListResponse>(`/platform/tenants${qs ? '?' + qs : ''}`);
  },
  create: async (data: { name: string; description: string; quota: Partial<TenantInfo['quota']> }) => {
    return apiClient.post<TenantInfo>('/platform/tenants', data);
  },
  update: async (id: string, data: Partial<TenantInfo>) => {
    return apiClient.put<TenantInfo>(`/platform/tenants/${id}`, data);
  },
  delete: async (id: string) => {
    return apiClient.delete<{ status: string }>(`/platform/tenants/${id}`);
  },
  suspend: async (id: string) => {
    return apiClient.post<{ status: string }>(`/platform/tenants/${id}/suspend`);
  },
  resume: async (id: string) => {
    return apiClient.post<{ status: string }>(`/platform/tenants/${id}/resume`);
  },
};

export interface Channel {
  id: string;
  name: string;
  type: 'telegram' | 'slack' | 'webchat' | 'api' | 'wechat';
  status: 'connected' | 'disconnected' | 'error';
  config: Record<string, unknown>;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
}

export interface ChannelListResponse {
  channels: Channel[];
  total: number;
}

export const channelApi = {
  list: async (params?: { type?: string; status?: string }) => {
    const query = new URLSearchParams();
    if (params?.type) query.set('type', params.type);
    if (params?.status) query.set('status', params.status);
    const qs = query.toString();
    return apiClient.get<ChannelListResponse>(`/app/channels${qs ? '?' + qs : ''}`);
  },
  create: async (data: { name: string; type: string; config: Record<string, unknown> }) => {
    return apiClient.post<Channel>('/app/channels', data);
  },
  update: async (id: string, data: Partial<Channel>) => {
    return apiClient.put<Channel>(`/app/channels/${id}`, data);
  },
  delete: async (id: string) => {
    return apiClient.delete<{ status: string }>(`/app/channels/${id}`);
  },
  test: async (id: string) => {
    return apiClient.post<{ success: boolean; message: string }>(`/app/channels/${id}/test`);
  },
};

export interface AppSession {
  id: string;
  channel: string;
  channel_type: string;
  user_id: string;
  agent_id: string;
  status: 'active' | 'ended' | 'timeout';
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface AppSessionListResponse {
  sessions: AppSession[];
  total: number;
}

export const appSessionApi = {
  list: async (params?: { status?: string; channel?: string }) => {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.channel) query.set('channel', params.channel);
    const qs = query.toString();
    return apiClient.get<AppSessionListResponse>(`/app/sessions${qs ? '?' + qs : ''}`);
  },
  get: async (id: string) => {
    return apiClient.get<AppSession>(`/app/sessions/${id}`);
  },
  end: async (id: string) => {
    return apiClient.post<{ status: string }>(`/app/sessions/${id}/end`);
  },
};