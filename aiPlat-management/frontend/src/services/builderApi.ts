import { apiClient } from './apiClient';

export interface BuilderSession {
  session_id: string;
  phase: 'dialogue' | 'executing' | 'done' | 'failed';
  requirement: string;
  prd?: {
    title: string;
    overview: string;
    user_stories: { id: string; description: string; acceptance_criteria: string[]; priority: string }[];
    constraints: string[];
    scope: string;
  } | null;
  architecture?: {
    components: { name: string; responsibility: string; dependencies: string[] }[];
    data_model: Record<string, Record<string, string>>;
    api_contracts: Record<string, unknown>[];
    tech_stack: Record<string, unknown>;
  } | null;
  code?: {
    files: { path: string; content: string }[];
    skills_created: string[];
    agents_created: string[];
    tools_created: string[];
  } | null;
  test_report?: {
    test_cases: { id: string; description: string; acceptance_criteria_id: string; script: string; expected: string }[];
    results: { test_case_id: string; passed: boolean; actual: string; error: string }[];
    pass_rate: number;
    issues: string[];
    recommendation: string;
    score_functionality: number;
    score_product_depth: number;
    score_design_ux: number;
    score_code_architecture: number;
  } | null;
  messages: { role: string; content: string }[];
  iteration: number;
  error: string;
}

export interface BuilderChatResponse {
  reply: string;
  session_state: BuilderSession;
  prd_ready: boolean;
}

export const builderApi = {
  createSession: async (requirement: string) => {
    return apiClient.post<{ session_id: string }>('/platform/builder/sessions', { requirement });
  },
  chat: async (sessionId: string, message: string) => {
    return apiClient.post<BuilderChatResponse>(`/platform/builder/sessions/${sessionId}/chat`, { message });
  },
  confirm: async (sessionId: string) => {
    return apiClient.post<BuilderSession>(`/platform/builder/sessions/${sessionId}/confirm`);
  },
  startPipeline: async (sessionId: string) => {
    return apiClient.post<BuilderSession>(`/platform/builder/sessions/${sessionId}/start`);
  },
  getState: async (sessionId: string) => {
    return apiClient.get<BuilderSession>(`/platform/builder/sessions/${sessionId}`);
  },
};
