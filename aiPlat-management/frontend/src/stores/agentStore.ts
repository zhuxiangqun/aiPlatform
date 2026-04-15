import { create } from 'zustand';
import { agentApi, type Agent } from '../services';

interface AgentState {
  agents: Agent[];
  loading: boolean;
  typeFilter: string | undefined;
  statusFilter: string | undefined;
  setTypeFilter: (filter: string | undefined) => void;
  setStatusFilter: (filter: string | undefined) => void;
  fetchAgents: () => Promise<void>;
  startAgent: (id: string) => Promise<void>;
  stopAgent: (id: string) => Promise<void>;
  deleteAgent: (id: string) => Promise<void>;
  createAgent: (data: { name: string; agent_type: string; config?: Record<string, unknown>; skills?: string[]; tools?: string[] }) => Promise<void>;
}

export const useAgentStore = create<AgentState>((set, get) => ({
  agents: [],
  loading: false,
  typeFilter: undefined,
  statusFilter: undefined,

  setTypeFilter: (filter) => {
    set({ typeFilter: filter });
    get().fetchAgents();
  },

  setStatusFilter: (filter) => {
    set({ statusFilter: filter });
    get().fetchAgents();
  },

  fetchAgents: async () => {
    set({ loading: true });
    try {
      const { typeFilter, statusFilter } = get();
      const res = await agentApi.list({ agent_type: typeFilter, status: statusFilter });
      set({ agents: res.agents || [] });
    } catch {
      set({ agents: [] });
    } finally {
      set({ loading: false });
    }
  },

  startAgent: async (id) => {
    await agentApi.start(id);
    await get().fetchAgents();
  },

  stopAgent: async (id) => {
    await agentApi.stop(id);
    await get().fetchAgents();
  },

  deleteAgent: async (id) => {
    await agentApi.delete(id);
    await get().fetchAgents();
  },

  createAgent: async (data) => {
    await agentApi.create(data);
    await get().fetchAgents();
  },
}));