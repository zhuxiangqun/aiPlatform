import { create } from 'zustand';
import { workspaceSkillApi } from '../services/coreApi';
import type { Skill } from '../services';

interface WorkspaceSkillState {
  skills: Skill[];
  loading: boolean;
  fetchSkills: (params?: { category?: string; status?: string; enabled_only?: boolean }) => Promise<void>;
  toggleSkill: (id: string, enable: boolean) => Promise<any>;
  deleteSkill: (id: string, opts?: { delete_files?: boolean }) => Promise<void>;
  restoreSkill: (id: string) => Promise<void>;
  createSkill: (data: { name: string; description: string; category?: string }) => Promise<void>;
}

export const useWorkspaceSkillStore = create<WorkspaceSkillState>((set, get) => ({
  skills: [],
  loading: false,

  fetchSkills: async (params) => {
    set({ loading: true });
    try {
      const res = await workspaceSkillApi.list({
        category: params?.category,
        status: params?.status,
        enabled_only: params?.enabled_only,
        include_lint: true,
      });
      set({ skills: res.skills || [] });
    } catch {
      set({ skills: [] });
    } finally {
      set({ loading: false });
    }
  },

  toggleSkill: async (id, enable) => {
    let res: any = null;
    if (enable) res = await workspaceSkillApi.enable(id);
    else res = await workspaceSkillApi.disable(id);
    await get().fetchSkills();
    return res;
  },

  deleteSkill: async (id, opts) => {
    await workspaceSkillApi.delete(id, opts);
    await get().fetchSkills();
  },

  restoreSkill: async (id) => {
    await workspaceSkillApi.restore(id);
    await get().fetchSkills();
  },

  createSkill: async (data) => {
    await workspaceSkillApi.create({ name: data.name, description: data.description, category: data.category || 'general' });
    await get().fetchSkills();
  },
}));
