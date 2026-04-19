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
    return apiClient.get<any>(`/diagnostics/health/${layer}`);
  },

  runE2ESmoke: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/diagnostics/e2e/smoke', body);
  },

  getDoctor: async () => {
    return apiClient.get<any>('/diagnostics/doctor');
  },

  recordRepoChangeset: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/diagnostics/repo/changeset/record', body);
  },

  getRepoChangesetPatch: async () => {
    return apiClient.get<any>('/diagnostics/repo/changeset/patch');
  },

  getRepoStagedPreview: async () => {
    return apiClient.get<any>('/diagnostics/repo/staged/preview');
  },

  getPromptTemplateDiff: async (templateId: string, params: { from_version?: string; to_version?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.from_version) q.set('from_version', params.from_version);
    if (params.to_version) q.set('to_version', params.to_version);
    const qs = q.toString();
    return apiClient.get<any>(`/diagnostics/prompts/${encodeURIComponent(templateId)}/diff${qs ? `?${qs}` : ''}`);
  },

  runRepoTests: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/diagnostics/repo/tests/run', body);
  },

  // ===== Observability (core only for now) =====

  listTraces: async (params: { limit?: number; offset?: number; status?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    if (params.status) q.set('status', params.status);
    const qs = q.toString();
    return apiClient.get<any>(`/diagnostics/trace/core${qs ? `?${qs}` : ''}`);
  },

  getTrace: async (traceId: string, params: { limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams({ trace_id: traceId });
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    return apiClient.get<any>(`/diagnostics/trace/core?${q.toString()}`);
  },

  getTraceByExecution: async (executionId: string) => {
    const q = new URLSearchParams({ execution_id: executionId });
    return apiClient.get<any>(`/diagnostics/trace/core?${q.toString()}`);
  },

  listGraphRuns: async (params: { limit?: number; offset?: number; graph_name?: string; status?: string; trace_id?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    if (params.graph_name) q.set('graph_name', params.graph_name);
    if (params.status) q.set('status', params.status);
    if (params.trace_id) q.set('trace_id', params.trace_id);
    const qs = q.toString();
    return apiClient.get<any>(`/diagnostics/graphs/core${qs ? `?${qs}` : ''}`);
  },

  getGraphRun: async (runId: string, includeCheckpoints: boolean = true) => {
    const q = new URLSearchParams();
    q.set('include_checkpoints', includeCheckpoints ? 'true' : 'false');
    return apiClient.get<any>(`/diagnostics/graphs/core/${runId}?${q.toString()}`);
  },

  resumeGraphRun: async (runId: string, payload: Record<string, unknown>) => {
    return apiClient.post<any>(`/diagnostics/graphs/core/${runId}/resume`, payload);
  },

  resumeExecuteGraphRun: async (runId: string, payload: Record<string, unknown>) => {
    return apiClient.post<any>(`/diagnostics/graphs/core/${runId}/resume/execute`, payload);
  },

  linksUi: async (params: { trace_id?: string; execution_id?: string; graph_run_id?: string; include_spans?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (params.trace_id) q.set('trace_id', params.trace_id);
    if (params.execution_id) q.set('execution_id', params.execution_id);
    if (params.graph_run_id) q.set('graph_run_id', params.graph_run_id);
    if (params.include_spans) q.set('include_spans', 'true');
    const qs = q.toString();
    return apiClient.get<any>(`/diagnostics/links/core/ui${qs ? `?${qs}` : ''}`);
  },

  listSyscalls: async (params: {
    limit?: number;
    offset?: number;
    trace_id?: string;
    run_id?: string;
    kind?: string;
    name?: string;
    status?: string;
    error_contains?: string;
    target_type?: string;
    target_id?: string;
    approval_request_id?: string;
    span_id?: string;
  } = {}) => {
    const q = new URLSearchParams();
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    if (params.trace_id) q.set('trace_id', params.trace_id);
    if (params.run_id) q.set('run_id', params.run_id);
    if (params.kind) q.set('kind', params.kind);
    if (params.name) q.set('name', params.name);
    if (params.status) q.set('status', params.status);
    if (params.error_contains) q.set('error_contains', params.error_contains);
    if (params.target_type) q.set('target_type', params.target_type);
    if (params.target_id) q.set('target_id', params.target_id);
    if (params.approval_request_id) q.set('approval_request_id', params.approval_request_id);
    if (params.span_id) q.set('span_id', params.span_id);
    const qs = q.toString();
    return apiClient.get<any>(`/diagnostics/syscalls/core${qs ? `?${qs}` : ''}`);
  },

  getSyscallStats: async (params: { window_hours?: number; top_n?: number; kind?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.window_hours != null) q.set('window_hours', String(params.window_hours));
    if (params.top_n != null) q.set('top_n', String(params.top_n));
    if (params.kind) q.set('kind', params.kind);
    const qs = q.toString();
    return apiClient.get<any>(`/diagnostics/syscalls/core/stats${qs ? `?${qs}` : ''}`);
  },
};

// Onboarding API
export const onboardingApi = {
  getState: async () => {
    return apiClient.get<any>('/onboarding/state');
  },
  configureLLMAdapter: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/onboarding/llm-adapter', body);
  },
  setDefaultLLM: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/onboarding/default-llm', body);
  },
  initTenant: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/onboarding/init-tenant', body);
  },
  rotateAdapterKey: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/onboarding/rotate-adapter-key', body);
  },
  setAutosmoke: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/onboarding/autosmoke', body);
  },
  getSecretsStatus: async () => {
    return apiClient.get<any>('/onboarding/secrets/status');
  },
  migrateSecrets: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/onboarding/secrets/migrate', body);
  },
  setStrongGate: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/onboarding/strong-gate', body);
  },
  setExecBackend: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/onboarding/exec-backend', body);
  },
  setTrustedSkillKeys: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/onboarding/trusted-skill-keys', body);
  },
};

// Monitoring API (legacy - for layer metrics)
export const monitoringApi = {
  getMetrics: async (layer: string) => {
    return apiClient.get(`/monitoring/metrics/${layer}`);
  },
};

export default apiClient;
