/**
 * 模型管理 API
 */

import apiClient from './apiClient';

export interface Model {
  id: string;
  name: string;
  displayName: string;
  type: 'chat' | 'embedding' | 'image' | 'audio';
  provider: string;
  source: 'config' | 'local' | 'external';
  enabled: boolean;
  status: 'available' | 'unavailable' | 'error' | 'not_configured';
  description: string;
  tags: string[];
  capabilities: string[];
  config: ModelConfig;
  stats?: ModelStats;
  createdAt: string;
  updatedAt: string;
}

export interface ModelConfig {
  temperature: number;
  maxTokens: number;
  topP: number;
  frequencyPenalty: number;
  presencePenalty: number;
  stop: string[];
  apiKeyEnv?: string;
  baseUrl?: string;
  headers?: Record<string, string>;
}

export interface ModelStats {
  requestsTotal: number;
  requestsSuccess: number;
  requestsFailed: number;
  tokensTotal: number;
  avgLatencyMs: number;
}

export interface Provider {
  id: string;
  name: string;
  type: 'local' | 'external';
  requiresApiKey: boolean;
  capabilities: string[];
}

export interface AddModelRequest {
  name: string;
  displayName?: string;
  type: string;
  provider: string;
  description?: string;
  tags?: string[];
  capabilities?: string[];
  config?: Partial<ModelConfig>;
}

export interface ModelListResponse {
  models: Model[];
  total: number;
}

export const modelApi = {
  list: async (params?: {
    source?: string;
    type?: string;
    enabled?: boolean;
    status?: string;
  }): Promise<ModelListResponse> => {
    const query = new URLSearchParams();
    if (params?.source) query.append('source', params.source);
    if (params?.type) query.append('type', params.type);
    if (params?.enabled !== undefined) query.append('enabled', String(params.enabled));
    if (params?.status) query.append('status', params.status);
    
    return apiClient.get<ModelListResponse>(`/infra/models?${query.toString()}`);
  },

  get: async (modelId: string): Promise<Model> => {
    return apiClient.get<Model>(`/infra/models/${modelId}`);
  },

  add: async (data: AddModelRequest): Promise<Model> => {
    return apiClient.post<Model>('/infra/models', data);
  },

  update: async (modelId: string, data: Partial<AddModelRequest>): Promise<{ id: string; status: string }> => {
    return apiClient.put<{ id: string; status: string }>(`/infra/models/${modelId}`, data);
  },

  delete: async (modelId: string): Promise<void> => {
    return apiClient.delete(`/infra/models/${modelId}`);
  },

  enable: async (modelId: string): Promise<{ id: string; enabled: boolean }> => {
    return apiClient.post<{ id: string; enabled: boolean }>(`/infra/models/${modelId}/enable`);
  },

  disable: async (modelId: string): Promise<{ id: string; enabled: boolean }> => {
    return apiClient.post<{ id: string; enabled: boolean }>(`/infra/models/${modelId}/disable`);
  },

  testConnectivity: async (modelId: string): Promise<{ success: boolean; error?: string }> => {
    return apiClient.post<{ success: boolean; error?: string }>(`/infra/models/${modelId}/test/connectivity`);
  },

  testResponse: async (modelId: string): Promise<{ success: boolean; latency?: number; error?: string }> => {
    return apiClient.post<{ success: boolean; latency?: number; error?: string }>(`/infra/models/${modelId}/test/response`);
  },

  scanLocal: async (endpoint?: string): Promise<{ models: Model[]; total: number }> => {
    const query = endpoint ? `?endpoint=${encodeURIComponent(endpoint)}` : '';
    return apiClient.get<{ models: Model[]; total: number }>(`/infra/models/local${query}`);
  },

  getProviders: async (): Promise<{ providers: Provider[] }> => {
    return apiClient.get<{ providers: Provider[] }>('/infra/models/providers');
  },
};

export default modelApi;