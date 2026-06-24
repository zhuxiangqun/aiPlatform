import { apiClient } from './apiClient';

export interface StudioSession {
  session_id: string;
  phase: string;
  requirement?: string;
  messages?: Array<{ role: string; content: string }>;
  prd?: Record<string, unknown>;
  pipeline_status?: string;
  pipeline_id?: string;
  project_id?: string;
}

export interface StudioProject {
  project_id: string;
  name: string;
  description?: string;
  team_id?: string;
  phase?: string;
  created_at?: string;
  updated_at?: string;
}

export interface PipelineState {
  project_id: string;
  phase: string;
  state: Record<string, unknown>;
  stages?: Array<{
    stage_id: string;
    agent_id: string;
    status: 'pending' | 'running' | 'completed' | 'failed' | 'paused' | 'skipped';
    started_at?: string;
    completed_at?: string;
    error?: string;
    pause_reason?: string;
  }>;
}

export interface DeployResult {
  ok: boolean;
  project_id: string;
  deploy_dir: string;
  app_url: string;
}

export const studioApi = {
  createSession: async (requirement: string) => {
    return apiClient.post<StudioSession>('/studio/sessions', { requirement });
  },

  chatSession: async (sessionId: string, message: string) => {
    return apiClient.post<StudioSession>('/studio/sessions/' + sessionId + '/chat', { message });
  },

  confirmSession: async (sessionId: string) => {
    return apiClient.post<{ session_id: string; phase: string }>('/studio/sessions/' + sessionId + '/confirm');
  },

  startPipeline: async (sessionId: string) => {
    return apiClient.post<StudioSession>('/studio/sessions/' + sessionId + '/start');
  },

  getSession: async (sessionId: string) => {
    return apiClient.get<StudioSession>('/studio/sessions/' + sessionId);
  },

  listProjects: async () => {
    return apiClient.get<{ projects: StudioProject[]; total: number }>('/studio/projects');
  },

  getProjectState: async (projectId: string) => {
    return apiClient.get<PipelineState>('/studio/projects/' + projectId + '/state');
  },

  approveProject: async (projectId: string) => {
    return apiClient.post<{ project_id: string; phase: string }>('/studio/projects/' + projectId + '/approve');
  },

  rejectProject: async (projectId: string, feedback: string) => {
    return apiClient.post<{ project_id: string; phase: string }>('/studio/projects/' + projectId + '/reject', { feedback });
  },

  testProject: async (projectId: string) => {
    return apiClient.post<{ project_id: string; all_passed: boolean }>('/studio/projects/' + projectId + '/test');
  },

  deployToApp: async (projectId: string) => {
    return apiClient.post<DeployResult>('/studio/projects/' + projectId + '/deploy-to-app');
  },
};
