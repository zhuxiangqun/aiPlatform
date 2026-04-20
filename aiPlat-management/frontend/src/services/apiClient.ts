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
    // PR-01: tenant/actor propagation (best-effort; platformization MVP)
    try {
      const tenantId = localStorage.getItem('active_tenant_id') || '';
      const actorId = localStorage.getItem('active_actor_id') || '';
      const actorRole = localStorage.getItem('active_actor_role') || '';
      if (tenantId.trim()) (defaultHeaders as any)['X-AIPLAT-TENANT-ID'] = tenantId.trim();
      if (actorId.trim()) (defaultHeaders as any)['X-AIPLAT-ACTOR-ID'] = actorId.trim();
      if (actorRole.trim()) (defaultHeaders as any)['X-AIPLAT-ACTOR-ROLE'] = actorRole.trim();
    } catch {
      // ignore (SSR / privacy mode)
    }

    const config: RequestInit = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    };

    const response = await fetch(url, config);

    if (!response.ok) {
      // Try parse structured error envelope from core (FastAPI style).
      const payload: any = await response.json().catch(() => null);
      const d = payload?.detail;
      const msg =
        (typeof d === 'string' ? d : null) ||
        (d && typeof d === 'object' ? (d.message || d.code) : null) ||
        payload?.message ||
        `HTTP error! status: ${response.status}`;
      const err: any = new Error(String(msg));
      // attach raw info for UI handlers
      err.status = response.status;
      err.payload = payload;
      err.detail = d;
      throw err;
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

  getContextConfig: async () => {
    return apiClient.get<any>('/diagnostics/context/config');
  },

  promptAssemble: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/diagnostics/prompt/assemble', body);
  },

  getContextMetricsRecent: async (params: { limit?: number; offset?: number; tenant_id?: string; session_id?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    if (params.tenant_id) q.set('tenant_id', String(params.tenant_id));
    if (params.session_id) q.set('session_id', String(params.session_id));
    const qs = q.toString();
    return apiClient.get<any>(`/diagnostics/context/metrics/recent${qs ? '?' + qs : ''}`);
  },

  getContextMetricsSummary: async (params: { window_hours?: number; top_n?: number; tenant_id?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.window_hours != null) q.set('window_hours', String(params.window_hours));
    if (params.top_n != null) q.set('top_n', String(params.top_n));
    if (params.tenant_id) q.set('tenant_id', String(params.tenant_id));
    const qs = q.toString();
    return apiClient.get<any>(`/diagnostics/context/metrics/summary${qs ? '?' + qs : ''}`);
  },

  getExecBackends: async () => {
    return apiClient.get<any>('/diagnostics/exec/backends');
  },

  recordRepoChangeset: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/diagnostics/repo/changeset/record', body);
  },

  repoGitBranch: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/diagnostics/repo/git/branch', body);
  },

  repoGitCommit: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/diagnostics/repo/git/commit', body);
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

  // Change Control (derived from changeset syscalls)
  listChangeControls: async (params: { limit?: number; offset?: number; tenant_id?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    if (params.tenant_id) q.set('tenant_id', params.tenant_id);
    const qs = q.toString();
    return apiClient.get<any>(`/diagnostics/change-control/core${qs ? `?${qs}` : ''}`);
  },
  getChangeControl: async (changeId: string, params: { limit?: number; offset?: number; tenant_id?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    if (params.tenant_id) q.set('tenant_id', params.tenant_id);
    const qs = q.toString();
    return apiClient.get<any>(`/diagnostics/change-control/core/${encodeURIComponent(changeId)}${qs ? `?${qs}` : ''}`);
  },
  autosmokeChangeControl: async (changeId: string) => {
    return apiClient.post<any>(`/diagnostics/change-control/core/${encodeURIComponent(changeId)}/autosmoke`, {});
  },
  exportChangeControlEvidence: async (changeId: string, params: { format?: 'zip' | 'json'; limit?: number } = {}) => {
    const q = new URLSearchParams();
    q.set('format', params.format || 'zip');
    if (params.limit != null) q.set('limit', String(params.limit));
    const qs = q.toString();
    // Return raw Response so caller can download zip
    const url = `${(import.meta as any).env?.VITE_API_URL || '/api'}/diagnostics/change-control/core/${encodeURIComponent(changeId)}/evidence${qs ? `?${qs}` : ''}`;
    // best-effort identity headers (align apiClient.request)
    const headers: any = {};
    try {
      const tenantId = localStorage.getItem('active_tenant_id') || '';
      const actorId = localStorage.getItem('active_actor_id') || '';
      const actorRole = localStorage.getItem('active_actor_role') || '';
      if (tenantId.trim()) headers['X-AIPLAT-TENANT-ID'] = tenantId.trim();
      if (actorId.trim()) headers['X-AIPLAT-ACTOR-ID'] = actorId.trim();
      if (actorRole.trim()) headers['X-AIPLAT-ACTOR-ROLE'] = actorRole.trim();
    } catch {
      // ignore
    }
    return fetch(url, { method: 'GET', headers });
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
  createEvidence: async (body: Record<string, unknown>) => {
    return apiClient.post<any>('/onboarding/evidence/runs', body);
  },
  listEvidence: async (params: { step_key?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.step_key) q.set('step_key', params.step_key);
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiClient.get<any>(`/onboarding/evidence/runs${qs ? `?${qs}` : ''}`);
  },
  getEvidence: async (evidenceId: string) => {
    return apiClient.get<any>(`/onboarding/evidence/runs/${encodeURIComponent(evidenceId)}`);
  },
  autosmokeRuns: async (params: { resource_type: string; resource_id: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    q.set('resource_type', params.resource_type);
    q.set('resource_id', params.resource_id);
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    return apiClient.get<any>(`/autosmoke/runs?${q.toString()}`);
  },
  autosmokeStatus: async (params: { resource_type: string; resource_id: string }) => {
    const q = new URLSearchParams();
    q.set('resource_type', params.resource_type);
    q.set('resource_id', params.resource_id);
    return apiClient.get<any>(`/autosmoke/status?${q.toString()}`);
  },
  autosmokeRun: async (body: { resource_type: string; resource_id: string; tenant_id?: string; actor_id?: string; detail?: any }) => {
    return apiClient.post<any>(`/autosmoke/run`, body);
  },
};

// Monitoring API (legacy - for layer metrics)
export const monitoringApi = {
  getMetrics: async (layer: string) => {
    return apiClient.get(`/monitoring/metrics/${layer}`);
  },
};

export default apiClient;
