/**
 * 网络管理 API
 */

import apiClient from './apiClient';

export interface ServiceEndpoint {
  id: string;
  name: string;
  namespace: string;
  type: 'ClusterIP' | 'NodePort' | 'LoadBalancer' | 'ExternalName';
  clusterIP: string;
  ports: ServicePort[];
  selector: Record<string, string>;
  status: 'Active' | 'Inactive';
  createdAt?: string;
}

export interface ServicePort {
  name: string;
  port: number;
  targetPort: number;
  protocol: 'TCP' | 'UDP';
}

export interface Ingress {
  id: string;
  name: string;
  namespace: string;
  host: string;
  path: string;
  backend: string;
  tls: boolean;
  tlsSecret?: string;
  annotations: Record<string, string>;
  status: 'Active' | 'Inactive';
  createdAt?: string;
}

export interface NetworkPolicy {
  id: string;
  name: string;
  namespace: string;
  type: 'Ingress' | 'Egress';
  podSelector: Record<string, string>;
  rules: NetworkRule[];
  status: 'Enabled' | 'Disabled';
}

export interface NetworkRule {
  from?: string[];
  to?: string[];
  ports: number[];
}

export const networkApi = {
  // Services
  listServices: async (namespace?: string): Promise<ServiceEndpoint[]> => {
    const params = namespace ? `?namespace=${namespace}` : '';
    return apiClient.get<ServiceEndpoint[]>(`/infra/network/services${params}`);
  },

  getService: async (serviceName: string): Promise<ServiceEndpoint> => {
    return apiClient.get<ServiceEndpoint>(`/infra/network/services/${serviceName}`);
  },

  createService: async (data: Partial<ServiceEndpoint>): Promise<ServiceEndpoint> => {
    return apiClient.post<ServiceEndpoint>('/infra/network/services', data);
  },

  updateService: async (serviceName: string, data: Partial<ServiceEndpoint>): Promise<void> => {
    return apiClient.put(`/infra/network/services/${serviceName}`, data);
  },

  deleteService: async (serviceName: string): Promise<void> => {
    return apiClient.delete(`/infra/network/services/${serviceName}`);
  },

  // Ingresses
  listIngresses: async (namespace?: string): Promise<Ingress[]> => {
    const params = namespace ? `?namespace=${namespace}` : '';
    return apiClient.get<Ingress[]>(`/infra/network/ingresses${params}`);
  },

  createIngress: async (data: Partial<Ingress>): Promise<Ingress> => {
    return apiClient.post<Ingress>('/infra/network/ingresses', data);
  },

  updateIngress: async (ingressName: string, data: Partial<Ingress>): Promise<void> => {
    return apiClient.put(`/infra/network/ingresses/${ingressName}`, data);
  },

  deleteIngress: async (ingressName: string): Promise<void> => {
    return apiClient.delete(`/infra/network/ingresses/${ingressName}`);
  },

  // Network Policies
  listNetworkPolicies: async (namespace?: string): Promise<NetworkPolicy[]> => {
    const params = namespace ? `?namespace=${namespace}` : '';
    return apiClient.get<NetworkPolicy[]>(`/infra/network/policies${params}`);
  },

  createNetworkPolicy: async (data: Partial<NetworkPolicy>): Promise<NetworkPolicy> => {
    return apiClient.post<NetworkPolicy>('/infra/network/policies', data);
  },

  deleteNetworkPolicy: async (policyName: string): Promise<void> => {
    return apiClient.delete(`/infra/network/policies/${policyName}`);
  },
};

export default networkApi;