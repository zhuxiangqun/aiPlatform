/**
 * 服务管理 API
 */

import apiClient from './apiClient';

export interface Service {
  id: string;
  name: string;
  namespace: string;
  type: 'LLM' | 'Embed' | 'Vector' | 'Cache' | 'DB';
  image: string;
  imageTag: string;
  replicas: number;
  readyReplicas: number;
  gpuCount: number;
  gpuType: string;
  status: 'Running' | 'Pending' | 'Failed' | 'Unknown';
  createdAt?: string;
  updatedAt?: string;
  config?: ServiceConfig;
  pods?: Pod[];
}

export interface ServiceConfig {
  maxTokens?: number;
  temperature?: number;
  maxConcurrent?: number;
  timeout?: number;
  model?: string;
}

export interface Pod {
  name: string;
  node: string;
  gpuUsage: number;
  memoryUsage: number;
  cpuUsage: number;
  restarts: number;
  status: string;
  createdAt?: string;
}

export interface Image {
  id: string;
  name: string;
  tag: string;
  size: number;
  type: string;
  createdAt: string;
  updatedAt: string;
  vulnerabilityScan: 'passed' | 'failed' | 'pending';
}

export interface ServiceListResponse {
  services: Service[];
  total: number;
}

export interface DeployServiceRequest {
  name: string;
  image: string;
  replicas?: number;
  gpuCount?: number;
  gpuType?: string;
  namespace?: string;
  config?: ServiceConfig;
}

export const serviceApi = {
  list: async (namespace?: string): Promise<ServiceListResponse> => {
    const params = namespace ? `?namespace=${namespace}` : '';
    return apiClient.get<ServiceListResponse>(`/infra/services${params}`);
  },

  get: async (serviceName: string): Promise<Service> => {
    return apiClient.get<Service>(`/infra/services/${serviceName}`);
  },

  deploy: async (data: DeployServiceRequest): Promise<Service> => {
    return apiClient.post<Service>('/infra/services', data);
  },

  scale: async (serviceName: string, replicas: number): Promise<void> => {
    return apiClient.post(`/infra/services/${serviceName}/scale`, { replicas });
  },

  restart: async (serviceName: string): Promise<void> => {
    return apiClient.post(`/infra/services/${serviceName}/restart`);
  },

  stop: async (serviceName: string): Promise<void> => {
    return apiClient.post(`/infra/services/${serviceName}/stop`);
  },

  delete: async (serviceName: string): Promise<void> => {
    return apiClient.delete(`/infra/services/${serviceName}`);
  },

  getLogs: async (serviceName: string, lines?: number): Promise<string[]> => {
    const params = lines ? `?lines=${lines}` : '';
    return apiClient.get<string[]>(`/infra/services/${serviceName}/logs${params}`);
  },

  getEvents: async (serviceName: string): Promise<unknown[]> => {
    return apiClient.get<unknown[]>(`/infra/services/${serviceName}/events`);
  },

  listImages: async (): Promise<Image[]> => {
    return apiClient.get<Image[]>('/infra/images');
  },
};

export default serviceApi;