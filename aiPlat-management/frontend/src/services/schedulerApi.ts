/**
 * 算力调度 API
 */

import apiClient from './apiClient';

export interface Quota {
  id: string;
  name: string;
  gpuQuota: number;
  gpuUsed: number;
  team: string;
  status: 'active' | 'exhausted' | 'inactive';
  createdAt?: string;
  updatedAt?: string;
}

export interface Policy {
  id: string;
  name: string;
  type: 'default' | 'high-priority' | 'batch';
  priority: number;
  nodeSelector: Record<string, string>;
  status: 'enabled' | 'disabled';
}

export interface Task {
  id: string;
  name: string;
  gpuCount: number;
  gpuType: string;
  queue: string;
  priority: number;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  position: number;
  estimatedWaitTime: number;
  submitter: string;
  submittedAt?: string;
}

export interface AutoscalingPolicy {
  id: string;
  service: string;
  type: 'HPA' | 'manual';
  minReplicas: number;
  maxReplicas: number;
  currentReplicas: number;
  targetReplicas: number;
  metrics: ScalingMetric[];
  status: 'running' | 'paused' | 'scaling';
}

export interface ScalingMetric {
  type: 'cpu' | 'gpu' | 'qps' | 'memory';
  target: number;
  operator: '>' | '<';
}

export const schedulerApi = {
  // Quotas
  listQuotas: async (): Promise<Quota[]> => {
    return apiClient.get<Quota[]>('/infra/scheduler/quotas');
  },

  createQuota: async (data: Partial<Quota>): Promise<Quota> => {
    return apiClient.post<Quota>('/infra/scheduler/quotas', data);
  },

  updateQuota: async (quotaId: string, data: Partial<Quota>): Promise<void> => {
    return apiClient.put(`/infra/scheduler/quotas/${quotaId}`, data);
  },

  deleteQuota: async (quotaId: string): Promise<void> => {
    return apiClient.delete(`/infra/scheduler/quotas/${quotaId}`);
  },

  // Policies
  listPolicies: async (): Promise<Policy[]> => {
    return apiClient.get<Policy[]>('/infra/scheduler/policies');
  },

  createPolicy: async (data: Partial<Policy>): Promise<Policy> => {
    return apiClient.post<Policy>('/infra/scheduler/policies', data);
  },

  updatePolicy: async (policyId: string, data: Partial<Policy>): Promise<void> => {
    return apiClient.put(`/infra/scheduler/policies/${policyId}`, data);
  },

  deletePolicy: async (policyId: string): Promise<void> => {
    return apiClient.delete(`/infra/scheduler/policies/${policyId}`);
  },

  // Tasks
  listTasks: async (queue?: string): Promise<Task[]> => {
    const params = queue ? `?queue=${queue}` : '';
    return apiClient.get<Task[]>(`/infra/scheduler/tasks${params}`);
  },

  submitTask: async (data: Partial<Task>): Promise<Task> => {
    return apiClient.post<Task>('/infra/scheduler/tasks', data);
  },

  cancelTask: async (taskId: string): Promise<void> => {
    return apiClient.post(`/infra/scheduler/tasks/${taskId}/cancel`);
  },

  // Autoscaling
  listAutoscalingPolicies: async (): Promise<AutoscalingPolicy[]> => {
    return apiClient.get<AutoscalingPolicy[]>('/infra/scheduler/autoscaling');
  },

  createAutoscalingPolicy: async (data: Partial<AutoscalingPolicy>): Promise<AutoscalingPolicy> => {
    return apiClient.post<AutoscalingPolicy>('/infra/scheduler/autoscaling', data);
  },

  pauseAutoscaling: async (policyId: string): Promise<void> => {
    return apiClient.post(`/infra/scheduler/autoscaling/${policyId}/pause`);
  },

  resumeAutoscaling: async (policyId: string): Promise<void> => {
    return apiClient.post(`/infra/scheduler/autoscaling/${policyId}/resume`);
  },
};

export default schedulerApi;