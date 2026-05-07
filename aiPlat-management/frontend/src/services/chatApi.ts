import { apiClient } from './apiClient';

export interface ChatMessage {
  role: string;
  content: string;
}

export const chatApi = {
  createSession: async (agentId: string, systemPrompt: string, initialContext?: Record<string, unknown>) => {
    return apiClient.post<{ session_id: string }>('/platform/chat/sessions', {
      agent_id: agentId,
      system_prompt: systemPrompt,
      initial_context: initialContext || {},
    });
  },

  sendMessage: async (sessionId: string, message: string) => {
    return apiClient.post<{ reply: string; session_id: string; messages: ChatMessage[] }>(
      `/platform/chat/sessions/${sessionId}/chat`,
      { message }
    );
  },
};
