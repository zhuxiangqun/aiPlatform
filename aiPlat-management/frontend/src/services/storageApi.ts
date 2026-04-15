/**
 * 存储管理 API
 */

import apiClient from './apiClient';

export interface VectorCollection {
  id: string;
  name: string;
  vectors: number;
  dimension: number;
  size: string;
  status: 'green' | 'yellow' | 'red';
  createdAt?: string;
}

export interface ModelStorage {
  id: string;
  name: string;
  type: 'LLM' | 'Embed' | 'Rerank';
  size: string;
  path: string;
  checksum: string;
  createdAt: string;
}

export interface PVC {
  id: string;
  name: string;
  namespace: string;
  size: string;
  used: string;
  storageClass: string;
  status: 'Bound' | 'Pending' | 'Lost';
  accessMode: 'ReadWriteOnce' | 'ReadWriteMany' | 'ReadOnlyMany';
  createdAt?: string;
}

export const storageApi = {
  // Vector Collections
  listCollections: async (): Promise<VectorCollection[]> => {
    return apiClient.get<VectorCollection[]>('/infra/storage/collections');
  },

  getCollection: async (name: string): Promise<VectorCollection> => {
    return apiClient.get<VectorCollection>(`/infra/storage/collections/${name}`);
  },

  createCollection: async (data: Partial<VectorCollection>): Promise<VectorCollection> => {
    return apiClient.post<VectorCollection>('/infra/storage/collections', data);
  },

  deleteCollection: async (name: string): Promise<void> => {
    return apiClient.delete(`/infra/storage/collections/${name}`);
  },

  // Model Storage
  listModels: async (): Promise<ModelStorage[]> => {
    return apiClient.get<ModelStorage[]>('/infra/storage/models');
  },

  uploadModel: async (data: FormData): Promise<ModelStorage> => {
    return apiClient.post<ModelStorage>('/infra/storage/models', data);
  },

  deleteModel: async (modelId: string): Promise<void> => {
    return apiClient.delete(`/infra/storage/models/${modelId}`);
  },

  // PVCs
  listPVCs: async (namespace?: string): Promise<PVC[]> => {
    const params = namespace ? `?namespace=${namespace}` : '';
    return apiClient.get<PVC[]>(`/infra/storage/pvcs${params}`);
  },

  createPVC: async (data: Partial<PVC>): Promise<PVC> => {
    return apiClient.post<PVC>('/infra/storage/pvcs', data);
  },

  expandPVC: async (pvcName: string, size: string): Promise<void> => {
    return apiClient.post(`/infra/storage/pvcs/${pvcName}/expand`, { size });
  },

  deletePVC: async (pvcName: string): Promise<void> => {
    return apiClient.delete(`/infra/storage/pvcs/${pvcName}`);
  },
};

export default storageApi;