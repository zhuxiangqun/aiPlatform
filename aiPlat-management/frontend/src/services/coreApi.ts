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

  execute: async (agentId: string, data: { messages?: unknown[]; input?: unknown; context?: Record<string, unknown> }) => {
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
}

export interface SkillListResponse {
  skills: Skill[];
  total: number;
  limit: number;
  offset: number;
}

export const skillApi = {
  list: async (params?: { category?: string; enabled_only?: boolean; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.category) query.set('category', params.category);
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

  delete: async (skillId: string) => {
    return apiClient.delete<{ status: string }>(`/core/skills/${skillId}`);
  },

  enable: async (skillId: string) => {
    return apiClient.post<{ status: string }>(`/core/skills/${skillId}/enable`);
  },

  disable: async (skillId: string) => {
    return apiClient.post<{ status: string }>(`/core/skills/${skillId}/disable`);
  },

  execute: async (skillId: string, data: { input?: Record<string, unknown>; context?: Record<string, unknown> }) => {
    return apiClient.post<{ execution_id: string; status: string; output?: unknown; error?: string; duration_ms?: number }>(`/core/skills/${skillId}/execute`, data);
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

  execute: async (toolName: string, params: Record<string, unknown>) => {
    return apiClient.post<{ output?: unknown; error?: string; success: boolean; latency?: number }>(`/core/tools/${toolName}/execute`, { input: params });
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