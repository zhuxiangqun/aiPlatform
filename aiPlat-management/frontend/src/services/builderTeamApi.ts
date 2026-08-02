import { apiClient } from './apiClient';

export interface AgentCatalogItem {
  agent_id: string;
  display_name: string;
  description: string;
  agent_type: string;
  category: string;
  tags: string[];
  phase: string;
  output_artifact?: string;
  hitl_phase?: string;
  protected: boolean;
  scope: string;
}

export interface AgentCatalogResponse {
  categories: Record<string, AgentCatalogItem[]>;
  total: number;
}

export interface PipelineStageConfig {
  id: string;
  agent_id: string;
  agent_name: string;
  description?: string;
  category: string;
  tags: string[];
  phase: string;
  order: number;
  hitl: boolean;
  hitl_phase: string;
  hitl_after_execute?: boolean;
  hitl_after_phase?: string;
  retry_target_id: string;
  generate_test_plan?: boolean;
  phase_description?: string;
  input_artifacts: string[];
  output_artifact: string;
  routing_rules?: { condition: string; next: string }[];
}

export interface TeamConfig {
  team_id: string;
  name: string;
  description: string;
  stages: PipelineStageConfig[];
  max_iterations: number;
  max_tokens_per_run: number;
  max_stagnation: number;
}

export interface BuilderSession {
  session_id: string;
  phase: string;
  iteration?: number;
  stepCount?: number;
  tokens_used?: number;
  tokens_budget?: number;
  error?: string;
  [key: string]: any;  // artifact keys are config-driven
}

export const builderTeamApi = {
  /** Simple list of all workspace agents (for catalog browsing) */
  listAgents: async (category?: string) => {
    const params = new URLSearchParams();
    if (category) params.set('category', category);
    const qs = params.toString();
    return apiClient.get<{ agents: AgentCatalogItem[] }>(
      `/platform/workspace/agents${qs ? '?' + qs : ''}`
    );
  },

  /** Assemble a team */
  createTeam: async (data: {
    name: string;
    description: string;
    stages: PipelineStageConfig[];
    max_tokens_per_run?: number;
  }) => {
    return apiClient.post<TeamConfig>('/platform/builder/teams', data);
  },

  /** List saved teams */
  listTeams: async () => {
    return apiClient.get<{ teams: TeamConfig[] }>('/platform/builder/teams');
  },

  /** Delete a saved team */
  deleteTeam: async (teamId: string) => {
    return apiClient.delete<{ ok: boolean }>(`/platform/builder/teams/${teamId}`);
  },

  /** Update a saved team */
  updateTeam: async (teamId: string, data: {
    name: string;
    description: string;
    stages: PipelineStageConfig[];
    max_tokens_per_run?: number;
  }) => {
    return apiClient.put<TeamConfig>(`/platform/builder/teams/${teamId}`, data);
  },

  /** Run a team */
  runTeam: async (teamId: string, description: string) => {
    return apiClient.post<{ team_id: string; phase: string }>(
      `/platform/builder/teams/${teamId}/run`,
      { description }
    );
  },

  /** Manually rollback a stage */
  rollback: async (teamId: string, stageId: string) => {
    return apiClient.post<{ team_id: string; phase: string }>(`/platform/builder/projects/${teamId}/rollback/${stageId}`);
  },

  /** Get pipeline state */
  getState: async (teamId: string) => {
    return apiClient.get<{ team_id: string; phase: string; state: Record<string, unknown> }>(
      `/platform/builder/teams/${teamId}/state`
    );
  },
};

// ━━━ Project API ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export interface ProjectRun {
  run_id: string;
  project_id: string;
  phase: string;
  pass_rate: number;
  tokens_used: number;
  iteration: number;
  error: string;
  started_at: string;
  finished_at: string;
}

export interface ProjectItem {
  project_id: string;
  name: string;
  description: string;
  team_id: string;
  team_name: string;
  team_stages: PipelineStageConfig[];
  runs: ProjectRun[];
  created_at: string;
  updated_at: string;
}

export const projectApi = {
  list: async () => {
    return apiClient.get<{ projects: ProjectItem[]; total: number }>('/platform/builder/projects');
  },
  create: async (data: { name: string; description: string; team_id?: string }) => {
    return apiClient.post<ProjectItem>('/platform/builder/projects', data);
  },
  get: async (projectId: string) => {
    return apiClient.get<ProjectItem>(`/platform/builder/projects/${projectId}`);
  },
  delete: async (projectId: string) => {
    return apiClient.delete(`/platform/builder/projects/${projectId}`);
  },
  batchDelete: async (data: { project_ids?: string[]; pass_rate_below?: number }) => {
    return apiClient.post<{ deleted: number }>('/platform/builder/projects/batch-delete', data);
  },
  chat: async (projectId: string, message: string) => {
    return apiClient.post<{ reply: string; prd_ready: boolean; trace_id: string }>(
      `/platform/builder/projects/${projectId}/chat`, { message }
    );
  },
  getMessages: async (projectId: string) => {
    return apiClient.get<{ messages: Array<{ role: string; content: string }> }>(
      `/platform/builder/projects/${projectId}/messages`
    );
  },
  confirm: async (projectId: string, prd?: Record<string, unknown>) => {
    return apiClient.post<{ phase: string }>(`/platform/builder/projects/${projectId}/confirm`, prd ? { prd } : {});
  },
  start: async (projectId: string) => {
    return apiClient.post<{ project_id: string; phase: string; run_id: string; state: Record<string, unknown> }>(
      `/platform/builder/projects/${projectId}/start`
    );
  },
  recommendTeam: async (projectId: string) => {
    return apiClient.post<{
      project_id: string;
      recommendation: { team_name?: string; reasoning?: string; stages: Array<Record<string, unknown>>; parse_error?: boolean; raw_reply?: string };
      trace_id: string;
    }>(`/platform/builder/projects/${projectId}/recommend-team`);
  },
  approve: async (projectId: string) => {
    return apiClient.post<{ project_id: string; phase: string }>(`/platform/builder/projects/${projectId}/approve`);
  },
  reject: async (projectId: string, feedback: string) => {
    return apiClient.post<{ project_id: string; phase: string }>(`/platform/builder/projects/${projectId}/reject`, { feedback });
  },
  getState: async (projectId: string) => {
    return apiClient.get<{ project_id: string; phase: string; state: Record<string, unknown>; runs: ProjectRun[] }>(
      `/platform/builder/projects/${projectId}/state`
    );
  },

  /** Rollback to a specific pipeline stage or PRD */
  rollback: async (projectId: string, stageId: string) => {
    return apiClient.post<{ project_id: string; phase: string }>(
      `/platform/builder/projects/${projectId}/rollback/${stageId}`
    );
  },

  startFix: async (projectId: string) => {
    return apiClient.post<{ project_id: string; phase: string }>(
      `/platform/builder/projects/${projectId}/fix`
    );
  },

  /** Regenerate a specific stage with human feedback. */
  regenerateStage: async (projectId: string, stageId: string, feedback: string) => {
    return apiClient.post<{ project_id: string; phase: string; state: Record<string, unknown> }>(
      `/platform/builder/projects/${projectId}/regenerate`,
      { stage_id: stageId, feedback }
    );
  },

  /** Run tests (E2E smoke + repo tests) on a completed project. */
  test: async (projectId: string) => {
    return apiClient.post<{ project_id: string; all_passed: boolean; e2e_smoke: Record<string, unknown>; repo_tests: Record<string, unknown> }>(
      `/platform/builder/projects/${projectId}/test`
    );
  },

  /** Deploy the project to aiPlat-app. */
  deployToApp: async (projectId: string) => {
    return apiClient.post<{ ok: boolean; project_id: string; deploy_dir: string; app_url: string }>(
      `/platform/builder/projects/${projectId}/deploy-to-app`
    );
  },

  /** Directly update PRD without PM chat re-engagement. */
  updatePrd: async (projectId: string, prd: Record<string, unknown>) => {
    return apiClient.post<{ status: string; detail: string }>(
      `/platform/builder/projects/${projectId}/update-prd`, { prd }
    );
  },

  /** Re-run pipeline with existing PRD (e.g., after editing PRD). */
  rebuild: async (projectId: string) => {
    return apiClient.post<{ status: string; detail: string }>(
      `/platform/builder/projects/${projectId}/rebuild`
    );
  },

  /** Get pipeline health report with per-stage dimensional scores. */
  getHealthReport: async (projectId: string) => {
    return apiClient.get<{
      project_id: string; overall_score: number;
      dimensions: Array<{ name: string; display_name: string; score: number; max_score: number; weight: number }>;
      stages: Array<{ stage_id: string; agent_id: string; overall_score: number; verdict: string; dimensions: Array<any> }>;
      trend: Array<{ run_id: string; score: number; timestamp: string }>;
    }>(`/platform/builder/projects/${projectId}/health-report`);
  },

  /** Upload a file for an App Factory project. Returns file reference. */
  uploadFile: async (projectId: string, formData: FormData) => {
    const resp = await fetch(`/api/platform/builder/projects/${projectId}/files/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!resp.ok) {
      const txt = await resp.text().catch(() => '');
      throw new Error(txt || `HTTP ${resp.status}`);
    }
    return resp.json();
  },
};

// ━━━ Agent Insights API ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export interface AgentInsight {
  agent_id: string;
  agent_name?: string;
  total_runs: number;
  rejection_rate: number;
  qa_rollback_rate: number;
  first_pass_rate: number;
  output_completeness: number;
  recent_runs?: { project?: string; phase?: string; pass_rate?: number; error?: string }[];
}

export const insightApi = {
  get: async (agentId: string) => {
    return apiClient.get<AgentInsight>(`/platform/builder/agent-insight/${agentId}`);
  },
  all: async () => {
    return apiClient.get<Record<string, AgentInsight>>('/platform/builder/agent-insights');
  },
  refresh: async () => {
    return apiClient.post<{ agents: number; ok: boolean }>('/platform/builder/agent-insights/refresh');
  },
};
