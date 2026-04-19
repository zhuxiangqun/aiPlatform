/**
 * Core API 客户端 - Agent, Skill, Memory, Knowledge, Harness
 */

import { apiClient } from './apiClient';

// ==================== Agent API ====================

export interface Agent {
  id: string;
  name: string;
  agent_type: string;
  status: string;
  skills?: string[];
  tools?: string[];
  metadata: Record<string, unknown>;
}

export interface AgentListResponse {
  agents: Agent[];
  total: number;
  limit: number;
  offset: number;
}

export const agentApi = {
  list: async (params?: { agent_type?: string; status?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.agent_type) query.set('agent_type', params.agent_type);
    if (params?.status) query.set('status', params.status);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    const qs = query.toString();
    return apiClient.get<AgentListResponse>(`/core/agents${qs ? '?' + qs : ''}`);
  },

  get: async (agentId: string) => {
    return apiClient.get<Agent>(`/core/agents/${agentId}`);
  },

  create: async (data: { name: string; agent_type: string; config?: Record<string, unknown>; skills?: string[]; tools?: string[] }) => {
    return apiClient.post<{ id: string; status: string; name: string }>('/core/agents', data);
  },

  update: async (agentId: string, data: { config?: Record<string, unknown>; metadata?: Record<string, unknown> }) => {
    return apiClient.put<{ status: string; id: string }>(`/core/agents/${agentId}`, data);
  },

  delete: async (agentId: string) => {
    return apiClient.delete<{ status: string; id: string }>(`/core/agents/${agentId}`);
  },

  start: async (agentId: string) => {
    return apiClient.post<{ status: string; id: string }>(`/core/agents/${agentId}/start`);
  },

  stop: async (agentId: string) => {
    return apiClient.post<{ status: string; id: string }>(`/core/agents/${agentId}/stop`);
  },

  execute: async (agentId: string, data: { messages?: unknown[]; input?: unknown; context?: Record<string, unknown>; options?: { toolset?: string } }) => {
    return apiClient.post<{ execution_id: string; status: string; output?: unknown; error?: string }>(`/core/agents/${agentId}/execute`, data);
  },

  getHistory: async (agentId: string) => {
    return apiClient.get<{ history: unknown[]; total: number }>(`/core/agents/${agentId}/history`);
  },

  getSkills: async (agentId: string) => {
    return apiClient.get<{ skills: { skill_id: string; skill_name: string; skill_type: string; call_count: number; success_rate: number }[]; skill_ids: string[]; total: number }>(`/core/agents/${agentId}/skills`);
  },

  bindSkills: async (agentId: string, skillIds: string[]) => {
    return apiClient.post<{ status: string; skill_ids: string[] }>(`/core/agents/${agentId}/skills`, { skill_ids: skillIds });
  },

  unbindSkill: async (agentId: string, skillId: string) => {
    return apiClient.delete<{ status: string }>(`/core/agents/${agentId}/skills/${skillId}`);
  },

  getTools: async (agentId: string) => {
    return apiClient.get<{ tools: { tool_id: string; tool_name: string; tool_type: string; call_count: number; success_rate: number }[]; tool_ids: string[]; total: number }>(`/core/agents/${agentId}/tools`);
  },

  bindTools: async (agentId: string, toolIds: string[]) => {
    return apiClient.post<{ status: string; tool_ids: string[] }>(`/core/agents/${agentId}/tools`, { tool_ids: toolIds });
  },

  unbindTool: async (agentId: string, toolId: string) => {
    return apiClient.delete<{ status: string }>(`/core/agents/${agentId}/tools/${toolId}`);
  },
};

export const workspaceAgentApi = {
  list: async (params?: { agent_type?: string; status?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.agent_type) query.set('type', params.agent_type);
    if (params?.status) query.set('status', params.status);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    const qs = query.toString();
    return apiClient.get<AgentListResponse>(`/core/workspace/agents${qs ? '?' + qs : ''}`);
  },

  create: async (data: { name: string; agent_type: string; config?: Record<string, unknown>; skills?: string[]; tools?: string[]; memory_config?: Record<string, unknown>; metadata?: Record<string, unknown> }) => {
    return apiClient.post<{ id: string; status: string; name: string }>('/core/workspace/agents', data);
  },

  delete: async (agentId: string) => {
    return apiClient.delete<{ status: string; id: string }>(`/core/workspace/agents/${agentId}`);
  },

  start: async (agentId: string) => {
    return apiClient.post<{ status: string; id: string }>(`/core/workspace/agents/${agentId}/start`);
  },

  stop: async (agentId: string) => {
    return apiClient.post<{ status: string; id: string }>(`/core/workspace/agents/${agentId}/stop`);
  },

  get: async (agentId: string) => {
    return apiClient.get<Agent>(`/core/workspace/agents/${agentId}`);
  },

  update: async (agentId: string, data: { name?: string; config?: Record<string, unknown>; skills?: string[]; tools?: string[]; memory_config?: Record<string, unknown>; metadata?: Record<string, unknown> }) => {
    return apiClient.put<{ status: string; id: string }>(`/core/workspace/agents/${agentId}`, data);
  },

  getSop: async (agentId: string) => {
    return apiClient.get<{ agent_id: string; agent_md?: string; sop: string }>(`/core/workspace/agents/${agentId}/sop`);
  },

  updateSop: async (agentId: string, sop: string) => {
    return apiClient.put<{ status: string; id: string }>(`/core/workspace/agents/${agentId}/sop`, { sop });
  },

  getExecutionHelp: async (agentId: string) => {
    return apiClient.get<{ agent_id: string; help_markdown: string; examples: Array<{ title: string; content: string }>; input_schema?: Record<string, unknown> | null }>(
      `/core/workspace/agents/${agentId}/execution-help`
    );
  },

  execute: async (agentId: string, data: { messages?: unknown[]; input?: unknown; context?: Record<string, unknown>; options?: { toolset?: string } }) => {
    return apiClient.post<{ execution_id: string; status: string; output?: unknown; error?: string }>(`/core/workspace/agents/${agentId}/execute`, data);
  },

  getSkills: async (agentId: string) => {
    return apiClient.get<{ skills: { skill_id: string; skill_name: string; skill_type: string; call_count: number; success_rate: number }[]; skill_ids: string[]; total: number }>(`/core/workspace/agents/${agentId}/skills`);
  },

  bindSkills: async (agentId: string, skillIds: string[]) => {
    return apiClient.post<{ status: string; skill_ids: string[] }>(`/core/workspace/agents/${agentId}/skills`, { skill_ids: skillIds });
  },

  unbindSkill: async (agentId: string, skillId: string) => {
    return apiClient.delete<{ status: string }>(`/core/workspace/agents/${agentId}/skills/${skillId}`);
  },

  getTools: async (agentId: string) => {
    return apiClient.get<{ tools: { tool_id: string; tool_name: string; tool_type: string; call_count: number; success_rate: number }[]; tool_ids: string[]; total: number }>(`/core/workspace/agents/${agentId}/tools`);
  },

  bindTools: async (agentId: string, toolIds: string[]) => {
    return apiClient.post<{ status: string; tool_ids: string[] }>(`/core/workspace/agents/${agentId}/tools`, { tool_ids: toolIds });
  },

  unbindTool: async (agentId: string, toolId: string) => {
    return apiClient.delete<{ status: string }>(`/core/workspace/agents/${agentId}/tools/${toolId}`);
  },

  getHistory: async (agentId: string, params?: { limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    const qs = query.toString();
    return apiClient.get<{ history: any[]; total: number }>(`/core/workspace/agents/${agentId}/history${qs ? '?' + qs : ''}`);
  },

  getVersions: async (agentId: string) => {
    return apiClient.get<{ agent_id: string; versions: { version: string; status: string; created_at: string; changes: string }[] }>(`/core/workspace/agents/${agentId}/versions`);
  },

  createVersion: async (agentId: string, changes: string) => {
    return apiClient.post<{ version: string; status: string; created_at: string; changes: string }>(`/core/workspace/agents/${agentId}/versions`, { changes });
  },

  rollbackVersion: async (agentId: string, version: string) => {
    return apiClient.post<{ status: string; version: string }>(`/core/workspace/agents/${agentId}/versions/${version}/rollback`, {});
  },
};

// ==================== Learning / Releases / Approvals (Phase 6) ====================

export interface LearningArtifact {
  artifact_id: string;
  kind: string;
  target_type: string;
  target_id: string;
  version: string;
  status: string;
  trace_id?: string | null;
  run_id?: string | null;
  payload: Record<string, unknown>;
  metadata: Record<string, unknown>;
  created_at?: number | string;
}

export interface LearningArtifactListResponse {
  items: LearningArtifact[];
  total: number;
  limit: number;
  offset: number;
}

export const learningApi = {
  listArtifacts: async (params: {
    target_type?: string;
    target_id?: string;
    kind?: string;
    status?: string;
    trace_id?: string;
    run_id?: string;
    limit?: number;
    offset?: number;
  } = {}) => {
    const q = new URLSearchParams();
    if (params.target_type) q.set('target_type', params.target_type);
    if (params.target_id) q.set('target_id', params.target_id);
    if (params.kind) q.set('kind', params.kind);
    if (params.status) q.set('status', params.status);
    if (params.trace_id) q.set('trace_id', params.trace_id);
    if (params.run_id) q.set('run_id', params.run_id);
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiClient.get<LearningArtifactListResponse>(`/core/learning/artifacts${qs ? `?${qs}` : ''}`);
  },

  getArtifact: async (artifactId: string) => {
    return apiClient.get<LearningArtifact>(`/core/learning/artifacts/${artifactId}`);
  },

  setArtifactStatus: async (artifactId: string, status: string, metadata_update: Record<string, unknown> = {}) => {
    return apiClient.post<{ status: string; artifact_id: string; new_status: string }>(`/core/learning/artifacts/${artifactId}/status`, {
      status,
      metadata_update,
    });
  },

  publishCandidate: async (candidateId: string, payload: Record<string, unknown>) => {
    return apiClient.post<any>(`/core/learning/releases/${candidateId}/publish`, payload);
  },

  rollbackCandidate: async (candidateId: string, payload: Record<string, unknown>) => {
    return apiClient.post<any>(`/core/learning/releases/${candidateId}/rollback`, payload);
  },

  expireReleases: async (payload: Record<string, unknown> = {}) => {
    return apiClient.post<any>(`/core/learning/releases/expire`, payload);
  },

  autoRollbackRegression: async (payload: Record<string, unknown>) => {
    return apiClient.post<any>(`/core/learning/auto-rollback/regression`, payload);
  },

  cleanupRollbackApprovals: async (payload: Record<string, unknown> = {}) => {
    return apiClient.post<any>(`/core/learning/approvals/cleanup-rollback-approvals`, payload);
  },

  autocaptureToPromptRevision: async (payload: {
    artifact_id: string;
    patch?: { prepend?: string; append?: string };
    priority?: number;
    exclusive_group?: string;
    create_release_candidate?: boolean;
    summary?: string;
  }) => {
    return apiClient.post<any>(`/core/learning/autocapture/to_prompt_revision`, payload as any);
  },
};

export interface ApprovalRequestSummary {
  request_id: string;
  user_id: string;
  operation: string;
  status: string;
  rule_id?: string | null;
  rule_type?: string | null;
  created_at?: string;
  expires_at?: string | null;
  metadata?: Record<string, unknown>;
  related_counts?: Record<string, unknown>;
}

export const approvalsApi = {
  listPending: async (params: { user_id?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.user_id) q.set('user_id', params.user_id);
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    q.set('order_by', 'created_at');
    q.set('order_dir', 'asc');
    return apiClient.get<{ items: ApprovalRequestSummary[]; total: number }>(`/core/approvals/pending?${q.toString()}`);
  },

  get: async (requestId: string) => {
    return apiClient.get<any>(`/core/approvals/${requestId}`);
  },

  approve: async (requestId: string, approved_by: string, comments: string = '') => {
    return apiClient.post<any>(`/core/approvals/${requestId}/approve`, { approved_by, comments });
  },

  reject: async (requestId: string, rejected_by: string, comments: string = '') => {
    return apiClient.post<any>(`/core/approvals/${requestId}/reject`, { rejected_by, comments });
  },
};

// ==================== MCP API ====================

export interface McpServer {
  name: string;
  enabled: boolean;
  transport?: string;
  url?: string;
  command?: string;
  args?: string[];
  auth?: Record<string, unknown>;
  allowed_tools?: string[];
  metadata?: Record<string, unknown>;
}

export interface McpServerListResponse {
  servers: McpServer[];
}

export const mcpApi = {
  listServers: async () => {
    return apiClient.get<McpServerListResponse>('/core/mcp/servers');
  },

  enableServer: async (serverName: string) => {
    return apiClient.post<{ status: string }>(`/core/mcp/servers/${serverName}/enable`, {});
  },

  disableServer: async (serverName: string) => {
    return apiClient.post<{ status: string }>(`/core/mcp/servers/${serverName}/disable`, {});
  },
};

export const workspaceMcpApi = {
  listServers: async () => {
    return apiClient.get<McpServerListResponse>('/core/workspace/mcp/servers');
  },

  getServer: async (serverName: string) => {
    return apiClient.get<McpServer>(`/core/workspace/mcp/servers/${serverName}`);
  },

  discoverTools: async (serverName: string, params?: { timeout_seconds?: number }) => {
    const query = new URLSearchParams();
    if (params?.timeout_seconds) query.set('timeout_seconds', String(params.timeout_seconds));
    const qs = query.toString();
    return apiClient.get<{ tools: { name: string; description?: string; input_schema?: Record<string, unknown> }[]; total: number }>(
      `/core/workspace/mcp/servers/${serverName}/tools${qs ? '?' + qs : ''}`
    );
  },

  policyCheck: async (serverName: string) => {
    return apiClient.get<{ env: string; server_name: string; transport: string; ok: boolean; reason?: string; details?: any }>(
      `/core/workspace/mcp/servers/${serverName}/policy-check`
    );
  },

  upsertServer: async (payload: McpServer) => {
    return apiClient.post<{ status: string; server?: { name: string; enabled: boolean } }>('/core/workspace/mcp/servers', payload as any);
  },

  updateServer: async (serverName: string, payload: Partial<McpServer>) => {
    return apiClient.put<{ status: string; server?: { name: string; enabled: boolean } }>(`/core/workspace/mcp/servers/${serverName}`, payload as any);
  },

  enableServer: async (serverName: string) => {
    return apiClient.post<{ status: string }>(`/core/workspace/mcp/servers/${serverName}/enable`, {});
  },

  disableServer: async (serverName: string) => {
    return apiClient.post<{ status: string }>(`/core/workspace/mcp/servers/${serverName}/disable`, {});
  },
};

// ==================== Skill API ====================

export interface Skill {
  id: string;
  name: string;
  category: string;
  description?: string;
  enabled: boolean;
  config?: Record<string, unknown>;
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
  type?: string;
  status?: string;
  metadata?: Record<string, unknown>;
}

export interface SkillDetail {
  id: string;
  name: string;
  type?: string;
  category?: string;
  description?: string;
  enabled: boolean;
  status?: string;
  config?: Record<string, unknown>;
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

export interface SkillListResponse {
  skills: Skill[];
  total: number;
  limit: number;
  offset: number;
}

export const skillApi = {
  list: async (params?: { category?: string; status?: string; enabled_only?: boolean; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.category) query.set('category', params.category);
    if (params?.status) query.set('status', params.status);
    if (params?.enabled_only) query.set('enabled_only', 'true');
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    const qs = query.toString();
    return apiClient.get<SkillListResponse>(`/core/skills${qs ? '?' + qs : ''}`);
  },

  get: async (skillId: string) => {
    return apiClient.get<SkillDetail>(`/core/skills/${skillId}`);
  },

  create: async (data: { name: string; description: string; category?: string }) => {
    return apiClient.post<{ id: string; status: string }>('/core/skills', data);
  },

  update: async (skillId: string, data: Record<string, unknown>) => {
    return apiClient.put<{ status: string }>(`/core/skills/${skillId}`, data);
  },

  delete: async (skillId: string, params?: { delete_files?: boolean }) => {
    const qs = params?.delete_files ? '?delete_files=true' : '';
    return apiClient.delete<{ status: string }>(`/core/skills/${skillId}${qs}`);
  },

  enable: async (skillId: string) => {
    return apiClient.post<{ status: string }>(`/core/skills/${skillId}/enable`);
  },

  disable: async (skillId: string) => {
    return apiClient.post<{ status: string }>(`/core/skills/${skillId}/disable`);
  },

  restore: async (skillId: string) => {
    return apiClient.post<{ status: string }>(`/core/skills/${skillId}/restore`);
  },

  execute: async (skillId: string, data: { input?: Record<string, unknown>; context?: Record<string, unknown>; options?: { toolset?: string } }) => {
    return apiClient.post<{ execution_id: string; status: string; output?: unknown; error?: string; duration_ms?: number }>(`/core/skills/${skillId}/execute`, data);
  },
};

export const workspaceSkillApi = {
  list: async (params?: { category?: string; status?: string; enabled_only?: boolean; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.category) query.set('category', params.category);
    if (params?.status) query.set('status', params.status);
    if (params?.enabled_only) query.set('enabled_only', 'true');
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    const qs = query.toString();
    return apiClient.get<SkillListResponse>(`/core/workspace/skills${qs ? '?' + qs : ''}`);
  },

  create: async (data: { name: string; category: string; description: string; input_schema?: Record<string, unknown>; output_schema?: Record<string, unknown>; config?: Record<string, unknown>; template?: string; sop?: string }) => {
    return apiClient.post<{ id: string; status: string }>(`/core/workspace/skills`, data);
  },

  get: async (skillId: string) => {
    return apiClient.get<SkillDetail>(`/core/workspace/skills/${skillId}`);
  },

  update: async (skillId: string, data: Record<string, unknown>) => {
    return apiClient.put<{ status: string; id: string }>(`/core/workspace/skills/${skillId}`, data);
  },

  enable: async (skillId: string) => {
    return apiClient.post<{ status: string }>(`/core/workspace/skills/${skillId}/enable`);
  },

  disable: async (skillId: string) => {
    return apiClient.post<{ status: string }>(`/core/workspace/skills/${skillId}/disable`);
  },

  restore: async (skillId: string) => {
    return apiClient.post<{ status: string }>(`/core/workspace/skills/${skillId}/restore`);
  },

  delete: async (skillId: string, opts?: { delete_files?: boolean }) => {
    const query = new URLSearchParams();
    if (opts?.delete_files) query.set('delete_files', 'true');
    const qs = query.toString();
    return apiClient.delete<{ status: string }>(`/core/workspace/skills/${skillId}${qs ? '?' + qs : ''}`);
  },

  execute: async (skillId: string, data: { input?: Record<string, unknown>; context?: Record<string, unknown>; options?: { toolset?: string } }) => {
    return apiClient.post<{ execution_id: string; status: string; output?: unknown; error?: string; duration_ms?: number }>(`/core/workspace/skills/${skillId}/execute`, data);
  },

  getExecutionHelp: async (skillId: string) => {
    return apiClient.get<{ skill_id: string; help_markdown: string; examples: Array<{ title: string; content: string }>; input_schema?: Record<string, unknown> | null }>(
      `/core/workspace/skills/${skillId}/execution-help`
    );
  },

  getSkillMarkdown: async (skillId: string) => {
    return apiClient.get<{ skill_id: string; path: string; content: string }>(`/core/workspace/skills/${skillId}/skill-md`);
  },

  listExecutions: async (skillId: string, params?: { limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    const qs = query.toString();
    return apiClient.get<{ executions: any[]; total: number }>(`/core/workspace/skills/${skillId}/executions${qs ? '?' + qs : ''}`);
  },

  getVersions: async (skillId: string) => {
    return apiClient.get<{ versions: { version: string; is_active: boolean }[] }>(`/core/workspace/skills/${skillId}/versions`);
  },

  getActiveVersion: async (skillId: string) => {
    return apiClient.get<{ skill_id: string; active_version: string | null }>(`/core/workspace/skills/${skillId}/active-version`);
  },

  rollbackVersion: async (skillId: string, version: string) => {
    return apiClient.post<{ status: string; active_version: string | null }>(`/core/workspace/skills/${skillId}/versions/${version}/rollback`, {});
  },
};

// ==================== Jobs / Cron (Roadmap-3) ====================

export interface Job {
  id: string;
  name: string;
  enabled: boolean;
  cron: string;
  timezone?: string | null;
  kind: 'agent' | 'skill' | 'tool' | 'graph' | string;
  target_id: string;
  user_id?: string | null;
  session_id?: string | null;
  payload?: Record<string, unknown>;
  options?: Record<string, unknown>;
  delivery?: Record<string, unknown>;
  last_run_at?: number | null;
  next_run_at?: number | null;
  lock_until?: number | null;
  lock_owner?: string | null;
  created_at?: number | null;
  updated_at?: number | null;
}

export interface JobRun {
  id: string;
  job_id: string;
  scheduled_for?: number | null;
  started_at?: number | null;
  finished_at?: number | null;
  status: string;
  trace_id?: string | null;
  run_id?: string | null;
  error?: string | null;
  result?: any;
  created_at?: number | null;
}

export interface JobDeliveryDLQItem {
  id: string;
  job_id: string;
  run_id?: string | null;
  url?: string | null;
  delivery?: any;
  payload?: any;
  attempts: number;
  error?: string | null;
  status: 'pending' | 'resolved' | string;
  created_at?: number | null;
  resolved_at?: number | null;
}

export const jobApi = {
  list: async (params: { limit?: number; offset?: number; enabled?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    if (params.enabled != null) q.set('enabled', params.enabled ? 'true' : 'false');
    const qs = q.toString();
    return apiClient.get<{ items: Job[]; total: number; limit: number; offset: number }>(`/core/jobs${qs ? `?${qs}` : ''}`);
  },

  create: async (data: {
    name: string;
    kind: string;
    target_id: string;
    cron: string;
    enabled?: boolean;
    timezone?: string | null;
    user_id?: string | null;
    session_id?: string | null;
    payload?: Record<string, unknown>;
    options?: Record<string, unknown>;
    delivery?: Record<string, unknown>;
  }) => {
    return apiClient.post<Job>(`/core/jobs`, data);
  },

  get: async (jobId: string) => {
    return apiClient.get<Job>(`/core/jobs/${jobId}`);
  },

  update: async (jobId: string, data: Record<string, unknown>) => {
    return apiClient.put<Job>(`/core/jobs/${jobId}`, data);
  },

  delete: async (jobId: string) => {
    return apiClient.delete<{ status: string; job_id: string }>(`/core/jobs/${jobId}`);
  },

  enable: async (jobId: string) => {
    return apiClient.post<Job>(`/core/jobs/${jobId}/enable`, {});
  },

  disable: async (jobId: string) => {
    return apiClient.post<Job>(`/core/jobs/${jobId}/disable`, {});
  },

  runNow: async (jobId: string) => {
    return apiClient.post<any>(`/core/jobs/${jobId}/run`, {});
  },

  listRuns: async (jobId: string, params: { limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiClient.get<{ items: JobRun[]; total: number; limit: number; offset: number }>(`/core/jobs/${jobId}/runs${qs ? `?${qs}` : ''}`);
  },

  listDLQ: async (params: { status?: string; job_id?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    if (params.status) q.set('status', params.status);
    if (params.job_id) q.set('job_id', params.job_id);
    const qs = q.toString();
    return apiClient.get<{ items: JobDeliveryDLQItem[]; total: number; limit: number; offset: number }>(`/core/jobs/dlq${qs ? `?${qs}` : ''}`);
  },

  retryDLQ: async (dlqId: string) => {
    return apiClient.post<any>(`/core/jobs/dlq/${dlqId}/retry`, {});
  },

  deleteDLQ: async (dlqId: string) => {
    return apiClient.delete<{ status: string; dlq_id: string }>(`/core/jobs/dlq/${dlqId}`);
  },
};

// ==================== Gateway Admin API (pairings / tokens) ====================

export interface GatewayPairing {
  id: string;
  channel: string;
  channel_user_id: string;
  user_id: string;
  session_id?: string | null;
  tenant_id?: string | null;
  metadata?: any;
  created_at?: number | null;
  updated_at?: number | null;
}

export interface GatewayToken {
  id: string;
  name: string;
  tenant_id?: string | null;
  enabled: boolean | number;
  created_at?: number | null;
  metadata?: any;
}

export const gatewayAdminApi = {
  listPairings: async (params: { limit?: number; offset?: number; channel?: string; user_id?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    if (params.channel) q.set('channel', params.channel);
    if (params.user_id) q.set('user_id', params.user_id);
    const qs = q.toString();
    return apiClient.get<{ items: GatewayPairing[]; total: number; limit: number; offset: number }>(`/core/gateway/pairings${qs ? `?${qs}` : ''}`);
  },
  upsertPairing: async (data: { channel: string; channel_user_id: string; user_id: string; session_id?: string; tenant_id?: string; metadata?: any }) => {
    return apiClient.post<GatewayPairing>(`/core/gateway/pairings`, data);
  },
  deletePairing: async (params: { channel: string; channel_user_id: string }) => {
    const q = new URLSearchParams();
    q.set('channel', params.channel);
    q.set('channel_user_id', params.channel_user_id);
    return apiClient.delete<{ status: string }>(`/core/gateway/pairings?${q.toString()}`);
  },
  listTokens: async (params: { limit?: number; offset?: number; enabled?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    if (params.enabled != null) q.set('enabled', params.enabled ? 'true' : 'false');
    const qs = q.toString();
    return apiClient.get<{ items: GatewayToken[]; total: number; limit: number; offset: number }>(`/core/gateway/tokens${qs ? `?${qs}` : ''}`);
  },
  createToken: async (data: { name: string; token: string; tenant_id?: string; enabled?: boolean; metadata?: any }) => {
    return apiClient.post<GatewayToken>(`/core/gateway/tokens`, data);
  },
  deleteToken: async (tokenId: string) => {
    return apiClient.delete<{ status: string; token_id: string }>(`/core/gateway/tokens/${tokenId}`);
  },
};

// ==================== Quota / Usage (PR-12/14 ops) ====================

export interface TenantQuotaSnapshot {
  tenant_id: string;
  version: number;
  quota: any;
  updated_at?: number | null;
}

export interface TenantUsageItem {
  tenant_id: string;
  day: string;
  metric_key: string;
  value: number;
  updated_at?: number | null;
}

export const quotaApi = {
  getSnapshot: async (tenantId: string) => {
    const q = new URLSearchParams({ tenant_id: tenantId });
    return apiClient.get<TenantQuotaSnapshot>(`/core/quota/snapshot?${q.toString()}`);
  },
  getUsage: async (params: { tenant_id: string; day_start?: string; day_end?: string; metric_key?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    q.set('tenant_id', params.tenant_id);
    if (params.day_start) q.set('day_start', params.day_start);
    if (params.day_end) q.set('day_end', params.day_end);
    if (params.metric_key) q.set('metric_key', params.metric_key);
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    return apiClient.get<{ items: TenantUsageItem[]; total: number; limit: number; offset: number }>(`/core/quota/usage?${q.toString()}`);
  },
};

// ==================== Gateway Delivery DLQ (PR-12 connectors) ====================

export interface GatewayDeliveryDLQItem {
  id: string;
  connector: string;
  tenant_id?: string | null;
  run_id?: string | null;
  url?: string | null;
  payload?: any;
  attempts: number;
  error?: string | null;
  status: 'pending' | 'resolved' | string;
  created_at?: number | null;
  resolved_at?: number | null;
}

export const gatewayDlqApi = {
  list: async (params: { status?: string; connector?: string; tenant_id?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set('status', params.status);
    if (params.connector) q.set('connector', params.connector);
    if (params.tenant_id) q.set('tenant_id', params.tenant_id);
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiClient.get<{ items: GatewayDeliveryDLQItem[]; total: number; limit: number; offset: number }>(`/core/gateway/dlq${qs ? `?${qs}` : ''}`);
  },
  retry: async (dlqId: string) => {
    return apiClient.post<any>(`/core/gateway/dlq/${dlqId}/retry`, {});
  },
  delete: async (dlqId: string) => {
    return apiClient.delete<{ status: string; dlq_id: string }>(`/core/gateway/dlq/${dlqId}`);
  },
};

// ==================== Ops actions (PR-14) ====================

export const opsApi = {
  prune: async (body: { now_ts?: number } = {}) => {
    return apiClient.post<{ ok: boolean; deleted?: any }>(`/core/ops/prune`, body);
  },
};

// ==================== Memory API ====================

export interface MemorySession {
  session_id: string;
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface MemoryMessage {
  role: string;
  content: string;
  timestamp?: string | null;
}

export interface MemorySessionDetail {
  session_id: string;
  messages: MemoryMessage[];
  metadata: Record<string, unknown>;
  message_count: number;
}

export interface MemorySearchResult {
  session_id: string;
  role: string;
  content: string;
  score?: number;
}

export interface SessionListResponse {
  sessions: MemorySession[];
  total: number;
}

export const memoryApi = {
  listSessions: async (params?: { limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    const qs = query.toString();
    return apiClient.get<SessionListResponse>(`/core/memory/sessions${qs ? '?' + qs : ''}`);
  },

  createSession: async (data?: { session_id?: string; metadata?: Record<string, unknown> }) => {
    return apiClient.post<{ session_id: string; status: string }>('/core/memory/sessions', data || {});
  },

  getSession: async (sessionId: string) => {
    return apiClient.get<MemorySessionDetail>(`/core/memory/sessions/${sessionId}`);
  },

  deleteSession: async (sessionId: string) => {
    return apiClient.delete<{ status: string; session_id: string }>(`/core/memory/sessions/${sessionId}`);
  },

  addMessage: async (sessionId: string, data: { role: string; content: string }) => {
    return apiClient.post<{ status: string; message: MemoryMessage }>(`/core/memory/sessions/${sessionId}/messages`, data);
  },

  search: async (query: string, limit?: number) => {
    return apiClient.post<{ results: MemorySearchResult[]; total: number }>('/core/memory/search', { query, limit: limit || 10 });
  },

  // Roadmap-4: Long-term memory
  addLongTerm: async (data: { user_id?: string; key?: string; content: string; metadata?: Record<string, unknown> }) => {
    return apiClient.post<{ id: string; user_id: string; key?: string | null; content: string; metadata?: Record<string, unknown>; created_at?: number }>(
      '/core/memory/longterm',
      data,
    );
  },

  searchLongTerm: async (data: { user_id?: string; query: string; limit?: number }) => {
    return apiClient.post<{ items: LongTermMemoryItem[]; total: number }>('/core/memory/longterm/search', {
      user_id: data.user_id,
      query: data.query,
      limit: data.limit ?? 10,
    });
  },
};

// ==================== Skill Packs API (Roadmap-4) ====================

export interface SkillPack {
  id: string;
  name: string;
  description?: string | null;
  manifest: Record<string, unknown>;
  created_at?: number | null;
  updated_at?: number | null;
}

export interface SkillPackVersion {
  id: string;
  pack_id: string;
  version: string;
  manifest: Record<string, unknown>;
  created_at?: number | null;
}

export interface SkillPackInstall {
  id: string;
  pack_id: string;
  version?: string | null;
  scope: string;
  installed_at?: number | null;
  metadata?: Record<string, unknown>;
}

export interface LongTermMemoryItem {
  id: string;
  user_id: string;
  key?: string | null;
  content: string;
  metadata?: Record<string, unknown>;
  created_at?: number | null;
}

export const skillPackApi = {
  list: async (params: { limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiClient.get<{ items: SkillPack[]; total: number; limit: number; offset: number }>(`/core/skill-packs${qs ? `?${qs}` : ''}`);
  },

  create: async (data: { name: string; description?: string; manifest?: Record<string, unknown> }) => {
    return apiClient.post<SkillPack>('/core/skill-packs', data);
  },

  get: async (packId: string) => {
    return apiClient.get<SkillPack>(`/core/skill-packs/${packId}`);
  },

  update: async (packId: string, data: { name?: string; description?: string | null; manifest?: Record<string, unknown> }) => {
    return apiClient.put<SkillPack>(`/core/skill-packs/${packId}`, data);
  },

  delete: async (packId: string) => {
    return apiClient.delete<{ status: string; id: string }>(`/core/skill-packs/${packId}`);
  },

  publish: async (packId: string, version: string) => {
    return apiClient.post<SkillPackVersion>(`/core/skill-packs/${packId}/publish`, { version });
  },

  listVersions: async (packId: string, params: { limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiClient.get<{ items: SkillPackVersion[]; total: number; limit: number; offset: number }>(
      `/core/skill-packs/${packId}/versions${qs ? `?${qs}` : ''}`,
    );
  },

  install: async (packId: string, data: { version?: string; scope?: 'engine' | 'workspace'; metadata?: Record<string, unknown> }) => {
    return apiClient.post<{ install: SkillPackInstall; applied: { skill_id: string; status: string; reason?: string }[] }>(
      `/core/skill-packs/${packId}/install`,
      {
        version: data.version,
        scope: data.scope || 'workspace',
        metadata: data.metadata || {},
      },
    );
  },

  listInstalls: async (params: { scope?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.scope) q.set('scope', String(params.scope));
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiClient.get<{ items: SkillPackInstall[]; total: number; limit: number; offset: number }>(`/core/skill-packs/installs${qs ? `?${qs}` : ''}`);
  },
};

// ==================== Knowledge API ====================

export const knowledgeApi = {
  listCollections: async () => {
    return apiClient.get<{ collections: unknown[]; total: number }>('/core/knowledge/collections');
  },

  createCollection: async (data: { name: string; description?: string }) => {
    return apiClient.post<{ collection_id: string; status: string }>('/core/knowledge/collections', data);
  },

  deleteCollection: async (collectionId: string) => {
    return apiClient.delete<{ status: string; collection_id: string }>(`/core/knowledge/collections/${collectionId}`);
  },

  search: async (query: string, limit?: number) => {
    return apiClient.post<{ results: unknown[]; total: number }>('/core/knowledge/search', { query, limit: limit || 10 });
  },
};

// ==================== Tool API ====================

export interface ToolInfo {
  name: string;
  description?: string;
  category?: string;
  scope?: 'engine' | 'workspace';
  protected?: boolean;
  status?: string;
  enabled?: boolean;
  config?: Record<string, unknown>;
  parameters?: Record<string, unknown>;
  stats?: {
    call_count: number;
    success_count: number;
    error_count: number;
    total_latency: number;
    avg_latency: number;
  };
}

export interface ToolListResponse {
  tools: ToolInfo[];
  total: number;
}

export const toolApi = {
  list: async (params?: { category?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.category) query.set('category', params.category);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    const qs = query.toString();
    return apiClient.get<ToolListResponse>(`/core/tools${qs ? '?' + qs : ''}`);
  },

  get: async (toolName: string) => {
    return apiClient.get<ToolInfo>(`/core/tools/${toolName}`);
  },

  getStats: async () => {
    return apiClient.get<Record<string, ToolInfo['stats']>>('/core/tools/stats');
  },

  execute: async (
    toolName: string,
    params: Record<string, unknown>,
    opts?: { toolset?: string; context?: Record<string, unknown>; session_id?: string; user_id?: string }
  ) => {
    return apiClient.post<{ output?: unknown; error?: string; success: boolean; latency?: number }>(`/core/tools/${toolName}/execute`, {
      input: params,
      options: opts?.toolset ? { toolset: opts.toolset } : undefined,
      context: opts?.context,
      session_id: opts?.session_id,
      user_id: opts?.user_id,
    });
  },

  updateConfig: async (toolName: string, config: Record<string, unknown>) => {
    return apiClient.put<{ status: string }>(`/core/tools/${toolName}`, { config });
  },
};

// ==================== Harness API ====================

export const harnessApi = {
  getStatus: async () => {
    return apiClient.get<{ status: string; agents: number }>('/core/harness/status');
  },

  getConfig: async () => {
    return apiClient.get<{ config: Record<string, unknown> }>('/core/harness/config');
  },

  getMetrics: async () => {
    return apiClient.get<{ metrics: Record<string, unknown> }>('/core/harness/metrics');
  },
};

// ==================== Runs API (Platform execution contract) ====================

export interface RunSummary {
  ok?: boolean;
  run_id: string;
  kind?: string;
  target_type?: string;
  target_id?: string;
  trace_id?: string | null;
  status?: string;
  legacy_status?: string;
  output?: unknown;
  start_time?: number | null;
  end_time?: number | null;
  error_code?: string | null;
  error_message?: string | null;
  error?: { code?: string; message?: string; detail?: Record<string, unknown> | null } | null;
  user_id?: string | null;
  session_id?: string | null;
  tenant_id?: string | null;
}

export interface RunEvent {
  seq: number;
  type: string;
  created_at?: number;
  trace_id?: string | null;
  tenant_id?: string | null;
  payload?: Record<string, unknown>;
}

export const runApi = {
  get: async (runId: string) => {
    return apiClient.get<RunSummary>(`/core/runs/${encodeURIComponent(runId)}`);
  },
  listEvents: async (runId: string, params: { after_seq?: number; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.after_seq != null) q.set('after_seq', String(params.after_seq));
    if (params.limit != null) q.set('limit', String(params.limit));
    const qs = q.toString();
    return apiClient.get<{ items: RunEvent[]; after_seq: number; last_seq: number }>(
      `/core/runs/${encodeURIComponent(runId)}/events${qs ? `?${qs}` : ''}`
    );
  },
  wait: async (runId: string, params: { timeout_ms?: number; after_seq?: number } = {}) => {
    return apiClient.post<{ run: RunSummary; events: RunEvent[]; after_seq: number; last_seq: number; done: boolean }>(
      `/core/runs/${encodeURIComponent(runId)}/wait`,
      {
        timeout_ms: params.timeout_ms ?? 30000,
        after_seq: params.after_seq ?? 0,
      }
    );
  },
};

// ==================== Audit API (enterprise governance) ====================

export interface AuditLogEntry {
  id: number;
  tenant_id?: string | null;
  actor_id?: string | null;
  actor_role?: string | null;
  action: string;
  resource_type?: string | null;
  resource_id?: string | null;
  request_id?: string | null;
  run_id?: string | null;
  trace_id?: string | null;
  status?: string | null;
  detail?: Record<string, unknown>;
  created_at: number;
}

export const auditApi = {
  listLogs: async (params: {
    tenant_id?: string;
    actor_id?: string;
    action?: string;
    resource_type?: string;
    resource_id?: string;
    request_id?: string;
    run_id?: string;
    trace_id?: string;
    status?: string;
    created_after?: number;
    created_before?: number;
    limit?: number;
    offset?: number;
  } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v == null) return;
      q.set(k, String(v));
    });
    const qs = q.toString();
    return apiClient.get<{ items: AuditLogEntry[]; total: number; limit: number; offset: number }>(`/audit/logs${qs ? `?${qs}` : ''}`);
  },
};

// ==================== Tenant Policies API (policy-as-code) ====================

export interface TenantPolicy {
  tenant_id: string;
  version: number;
  policy: Record<string, unknown>;
  updated_at: number;
}

export const policyApi = {
  listTenants: async (params: { limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.limit != null) q.set('limit', String(params.limit));
    if (params.offset != null) q.set('offset', String(params.offset));
    const qs = q.toString();
    return apiClient.get<{ items: TenantPolicy[]; total: number; limit: number; offset: number }>(`/policies/tenants${qs ? `?${qs}` : ''}`);
  },
  getTenant: async (tenantId: string) => {
    return apiClient.get<TenantPolicy>(`/policies/tenants/${encodeURIComponent(tenantId)}`);
  },
  upsertTenant: async (tenantId: string, data: { policy: Record<string, unknown>; version?: number; actor_id?: string }) => {
    return apiClient.put<TenantPolicy>(`/policies/tenants/${encodeURIComponent(tenantId)}`, data);
  },
  evaluateTool: async (tenantId: string, toolName: string) => {
    const q = new URLSearchParams({ tool_name: toolName });
    return apiClient.get<{ tenant_id: string; tool_name: string; decision: string; policy_version?: number; matched_rule?: string | null }>(
      `/policies/tenants/${encodeURIComponent(tenantId)}/evaluate-tool?${q.toString()}`
    );
  },
};
