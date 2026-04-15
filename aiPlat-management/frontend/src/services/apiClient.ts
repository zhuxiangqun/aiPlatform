/**
 * API 客户端
 * 
 * 统一的 API 请求客户端，支持所有后端接口
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    
    const defaultHeaders: HeadersInit = {
      'Content-Type': 'application/json',
    };

    const config: RequestInit = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    };

    const response = await fetch(url, config);

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Unknown error' }));
      throw new Error(error.message || `HTTP error! status: ${response.status}`);
    }

    return response.json();
  }

  async get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' });
  }

  async post<T>(endpoint: string, data?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async put<T>(endpoint: string, data?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  async delete<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' });
  }
}

export const apiClient = new ApiClient(API_BASE_URL);

// Dashboard API
export const dashboardApi = {
  getStatus: async () => {
    return apiClient.get('/dashboard/status');
  },

  getHealth: async () => {
    return apiClient.get('/dashboard/health');
  },

  getMetrics: async () => {
    return apiClient.get('/dashboard/metrics');
  },
};

// Alerting API
export const alertingApi = {
  getAlerts: async () => {
    return apiClient.get('/alerting/alerts');
  },

  getRules: async () => {
    return apiClient.get('/alerting/rules');
  },
};

// Diagnostics API
export const diagnosticsApi = {
  getHealth: async (layer: string) => {
    return apiClient.get(`/diagnostics/health/${layer}`);
  },
};

// Monitoring API (legacy - for layer metrics)
export const monitoringApi = {
  getMetrics: async (layer: string) => {
    return apiClient.get(`/monitoring/metrics/${layer}`);
  },
};

export default apiClient;