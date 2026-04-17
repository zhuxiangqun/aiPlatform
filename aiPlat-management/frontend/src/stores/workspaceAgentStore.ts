import { create } from 'zustand';
import { workspaceAgentApi } from '../services/coreApi';
import type { Agent } from '../services';

interface WorkspaceAgentState {
  agents: Agent[];
  loading: boolean;
  fetchAgents: (params?: { agent_type?: string; status?: string }) => Promise<void>;
  startAgent: (id: string) => Promise<void>;
  stopAgent: (id: string) => Promise<void>;
  deleteAgent: (id: string) => Promise<void>;
  createAgent: (data: { name: string; agent_type: string; config?: Record<string, unknown>; skills?: string[]; tools?: string[] }) => Promise<void>;
}

export const useWorkspaceAgentStore = create<WorkspaceAgentState>((set, get) => ({
  agents: [],
  loading: false,

  fetchAgents: async (params) => {
    set({ loading: true });
    try {
      const res = await workspaceAgentApi.list({ agent_type: params?.agent_type, status: params?.status });
      set({ agents: res.agents || [] });
    } catch {
      set({ agents: [] });
    } finally {
      set({ loading: false });
    }
  },

  startAgent: async (id) => {
    await workspaceAgentApi.start(id);
    await get().fetchAgents();
  },

  stopAgent: async (id) => {
    await workspaceAgentApi.stop(id);
    await get().fetchAgents();
  },

  deleteAgent: async (id) => {
    await workspaceAgentApi.delete(id);
    await get().fetchAgents();
  },

  createAgent: async (data) => {
    await workspaceAgentApi.create(data);
    await get().fetchAgents();
  },
}));

