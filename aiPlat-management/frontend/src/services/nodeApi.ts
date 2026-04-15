/**
 * 节点管理 API
 */

import apiClient from './apiClient';

export interface Node {
  name: string;
  ip: string;
  gpu_model: string;
  gpu_count: number;
  driver_version: string;
  status: 'Ready' | 'NotReady' | 'Unknown';
  gpus: GPU[];
  labels: Record<string, string>;
  createdAt?: string;
}

export interface GPU {
  id: string;
  utilization: number;
  temperature: number;
  memory_shared?: boolean;
}

export interface NodeListResponse {
  nodes: Node[];
  total: number;
  healthy: number;
}

export interface AddNodeRequest {
  provider?: string;
  instanceType?: string;
  count?: number;
  labels?: Record<string, string>;
}

export const nodeApi = {
  list: async (): Promise<NodeListResponse> => {
    return apiClient.get<NodeListResponse>('/infra/nodes');
  },

  get: async (nodeName: string): Promise<Node> => {
    return apiClient.get<Node>(`/infra/nodes/${nodeName}`);
  },

  add: async (data: AddNodeRequest): Promise<Node> => {
    return apiClient.post<Node>('/infra/nodes', data);
  },

  remove: async (nodeName: string): Promise<void> => {
    return apiClient.delete(`/infra/nodes/${nodeName}`);
  },

  drain: async (nodeName: string): Promise<void> => {
    return apiClient.post(`/infra/nodes/${nodeName}/drain`);
  },

  restart: async (nodeName: string): Promise<void> => {
    return apiClient.post(`/infra/nodes/${nodeName}/restart`);
  },

  getGpuStatus: async (nodeName: string): Promise<GPU[]> => {
    return apiClient.get<GPU[]>(`/infra/nodes/${nodeName}/gpus`);
  },

  upgradeDriver: async (nodeName: string, version: string): Promise<void> => {
    return apiClient.post(`/infra/nodes/${nodeName}/driver/upgrade`, { version });
  },
};

export default nodeApi;