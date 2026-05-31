import { apiClient } from './apiClient';

export interface ChatMessage {
  role: string;
  content: string;
}

export const chatApi = {
  createSession: async (opts: {
    agentId?: string;
    systemPrompt?: string;
    templateId?: string;
    variables?: Record<string, string>;
    initialContext?: Record<string, unknown>;
  }) => {
    return apiClient.post<{ session_id: string }>('/platform/chat/sessions', {
      agent_id: opts.agentId || '',
      system_prompt: opts.systemPrompt || '',
      template_id: opts.templateId || '',
      variables: opts.variables || {},
      initial_context: opts.initialContext || {},
    });
  },

  sendMessage: async (sessionId: string, message: string) => {
    return apiClient.post<{ reply: string; session_id: string; messages: ChatMessage[] }>(
      `/platform/chat/sessions/${sessionId}/chat`,
      { message }
    );
  },
};

export const promptsApi = {
  run: async (opts: {
    templateId?: string;
    instanceId?: string;
    variables: Record<string, string>;
    model?: string;
  }) => {
    return apiClient.post<{ output: string; model: string }>('/platform/prompts/run', {
      template_id: opts.templateId || '',
      instance_id: opts.instanceId || '',
      variables: opts.variables,
      model: opts.model || 'deepseek-chat',
    });
  },
};
