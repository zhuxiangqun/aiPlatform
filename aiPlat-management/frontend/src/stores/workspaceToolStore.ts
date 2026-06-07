import { create } from 'zustand';
import { workspaceToolApi, toolApi } from '../services';
import type { ToolInfo } from '../services';

interface WorkspaceToolState {
  tools: ToolInfo[];
  loading: boolean;
  fetchTools: (params?: { category?: string; limit?: number; offset?: number }) => Promise<void>;
  deleteTool: (name: string) => Promise<void>;
  createTool: (data: { name: string; description?: string; code: string }) => Promise<void>;
  signTool: (name: string, privateKey: string) => Promise<void>;
  updateTool: (name: string, data: { description?: string; category?: string }) => Promise<void>;
  reloadTool: (name: string) => Promise<void>;
  saveSource: (name: string, source: string) => Promise<void>;
}

export const useWorkspaceToolStore = create<WorkspaceToolState>((set, get) => ({
  tools: [],
  loading: false,

  fetchTools: async (params) => {
    set({ loading: true });
    try {
      // Prefer dedicated workspace/tools endpoint; fallback to /tools with client-side filter
      const res = await workspaceToolApi.list({ limit: params?.limit, offset: params?.offset });
      const wsTools = (res.tools || []).filter((t: any) => t.scope === 'workspace');
      set({ tools: wsTools.length > 0 ? wsTools : [] });
      if (wsTools.length === 0) {
        // Fallback to toolApi if workspace/tools is empty
        const fallback = await toolApi.list({ limit: params?.limit, offset: params?.offset });
        const ws = (fallback.tools || []).filter((t: any) => {
          if (t.protected === true || t.scope === 'engine') return false;
          if (t.provenance?.scope === 'workspace') return true;
          return false;
        });
        set({ tools: ws });
      }
    } catch {
      try {
        const fallback = await toolApi.list({ limit: params?.limit, offset: params?.offset });
        const ws = (fallback.tools || []).filter((t: any) => {
          if (t.protected === true || t.scope === 'engine') return false;
          if (t.provenance?.scope === 'workspace') return true;
          return false;
        });
        set({ tools: ws });
      } catch {
        set({ tools: [] });
      }
    } finally {
      set({ loading: false });
    }
  },

  deleteTool: async (name) => {
    await toolApi.deleteTool(name);
    await get().fetchTools();
  },

  createTool: async (data) => {
    await toolApi.create(data);
    await get().fetchTools();
  },

  signTool: async (name, privateKey) => {
    await toolApi.sign(name, { private_key: privateKey });
    await get().fetchTools();
  },

  updateTool: async (name, data) => {
    await workspaceToolApi.update(name, data);
    await get().fetchTools();
  },

  reloadTool: async (name) => {
    await workspaceToolApi.reload(name);
    await get().fetchTools();
  },

  saveSource: async (name, source) => {
    await workspaceToolApi.updateSource(name, { source });
    await get().fetchTools();
  },
}));
