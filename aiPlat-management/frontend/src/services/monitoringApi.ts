/**
 * 监控告警 API
 */

import apiClient from './apiClient';

export interface GPUMetrics {
  nodeId: string;
  gpuIndex: number;
  utilization: number;
  memoryUsed: number;
  memoryTotal: number;
  temperature: number;
  powerDraw: number;
  powerLimit: number;
  status: 'healthy' | 'warning' | 'critical';
}

export interface NodeMetrics {
  nodeId: string;
  cpuUsage: number;
  memoryUsage: number;
  diskUsage: number;
  networkIn: number;
  networkOut: number;
  gpus: GPUMetrics[];
}

export interface AlertRule {
  id: string;
  name: string;
  type: 'system' | 'gpu' | 'service' | 'network';
  condition: string;
  severity: 'info' | 'warning' | 'critical';
  status: 'enabled' | 'disabled';
  threshold: number;
  duration: number;
  createdAt?: string;
  updatedAt?: string;
}

export interface Alert {
  id: string;
  ruleId: string;
  ruleName: string;
  severity: 'info' | 'warning' | 'critical';
  status: 'firing' | 'resolved';
  message: string;
  labels: Record<string, string>;
  startsAt: string;
  endsAt?: string;
}

export interface AuditLog {
  id: string;
  user: string;
  action: string;
  resource: string;
  resourceType: string;
  status: 'success' | 'failure';
  timestamp: string;
  details: string;
  ip: string;
}

export interface ClusterMetrics {
  totalNodes: number;
  healthyNodes: number;
  totalGPUs: number;
  usedGPUs: number;
  cpuUsage: number;
  memoryUsage: number;
  gpuUsage: number;
}

export const monitoringApi = {
  // Metrics
  getClusterMetrics: async (): Promise<ClusterMetrics> => {
    return apiClient.get<ClusterMetrics>('/infra/monitoring/metrics/cluster');
  },

  getNodeMetrics: async (nodeId?: string): Promise<NodeMetrics[]> => {
    const params = nodeId ? `?node=${nodeId}` : '';
    return apiClient.get<NodeMetrics[]>(`/infra/monitoring/metrics/nodes${params}`);
  },

  getGPUMetrics: async (nodeId?: string): Promise<GPUMetrics[]> => {
    const params = nodeId ? `?node=${nodeId}` : '';
    return apiClient.get<GPUMetrics[]>(`/infra/monitoring/metrics/gpus${params}`);
  },

  // Alert Rules
  listAlertRules: async (): Promise<AlertRule[]> => {
    return apiClient.get<AlertRule[]>('/infra/monitoring/alerts/rules');
  },

  createAlertRule: async (data: Partial<AlertRule>): Promise<AlertRule> => {
    return apiClient.post<AlertRule>('/infra/monitoring/alerts/rules', data);
  },

  updateAlertRule: async (ruleId: string, data: Partial<AlertRule>): Promise<void> => {
    return apiClient.put(`/infra/monitoring/alerts/rules/${ruleId}`, data);
  },

  deleteAlertRule: async (ruleId: string): Promise<void> => {
    return apiClient.delete(`/infra/monitoring/alerts/rules/${ruleId}`);
  },

  enableAlertRule: async (ruleId: string): Promise<void> => {
    return apiClient.post(`/infra/monitoring/alerts/rules/${ruleId}/enable`);
  },

  disableAlertRule: async (ruleId: string): Promise<void> => {
    return apiClient.post(`/infra/monitoring/alerts/rules/${ruleId}/disable`);
  },

  // Alerts
  listAlerts: async (status?: 'firing' | 'resolved'): Promise<Alert[]> => {
    const params = status ? `?status=${status}` : '';
    return apiClient.get<Alert[]>(`/infra/monitoring/alerts${params}`);
  },

  acknowledgeAlert: async (alertId: string): Promise<void> => {
    return apiClient.post(`/infra/monitoring/alerts/${alertId}/acknowledge`);
  },

  // Audit Logs
  listAuditLogs: async (params?: {
    user?: string;
    action?: string;
    startTime?: string;
    endTime?: string;
  }): Promise<AuditLog[]> => {
    const query = new URLSearchParams();
    if (params?.user) query.set('user', params.user);
    if (params?.action) query.set('action', params.action);
    if (params?.startTime) query.set('start', params.startTime);
    if (params?.endTime) query.set('end', params.endTime);
    const queryString = query.toString();
    return apiClient.get<AuditLog[]>(`/infra/monitoring/audit?${queryString}`);
  },
};

export default monitoringApi;