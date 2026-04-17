import { create } from 'zustand';
import { workspaceMcpApi } from '../services/coreApi';
import type { McpServer } from '../services/coreApi';

interface WorkspaceMcpState {
  servers: McpServer[];
  loading: boolean;
  fetchServers: () => Promise<void>;
  setServerEnabled: (name: string, enabled: boolean) => Promise<void>;
}

export const useWorkspaceMcpStore = create<WorkspaceMcpState>((set, get) => ({
  servers: [],
  loading: false,

  fetchServers: async () => {
    set({ loading: true });
    try {
      const res = await workspaceMcpApi.listServers();
      set({ servers: res.servers || [], loading: false });
    } catch {
      set({ loading: false });
    }
  },

  setServerEnabled: async (name: string, enabled: boolean) => {
    if (enabled) {
      await workspaceMcpApi.enableServer(name);
    } else {
      await workspaceMcpApi.disableServer(name);
    }
    await get().fetchServers();
  },
}));

