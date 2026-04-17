import { create } from 'zustand';
import { mcpApi } from '../services/coreApi';
import type { McpServer } from '../services/coreApi';

interface McpState {
  servers: McpServer[];
  loading: boolean;
  fetchServers: () => Promise<void>;
  setServerEnabled: (name: string, enabled: boolean) => Promise<void>;
}

export const useMcpStore = create<McpState>((set, get) => ({
  servers: [],
  loading: false,

  fetchServers: async () => {
    set({ loading: true });
    try {
      const res = await mcpApi.listServers();
      set({ servers: res.servers || [], loading: false });
    } catch {
      set({ loading: false });
    }
  },

  setServerEnabled: async (name: string, enabled: boolean) => {
    if (enabled) {
      await mcpApi.enableServer(name);
    } else {
      await mcpApi.disableServer(name);
    }
    await get().fetchServers();
  },
}));

