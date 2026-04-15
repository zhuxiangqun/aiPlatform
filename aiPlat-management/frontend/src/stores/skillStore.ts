import { create } from 'zustand';
import { skillApi, type Skill } from '../services';

interface SkillState {
  skills: Skill[];
  loading: boolean;
  categoryFilter: string | undefined;
  enabledOnly: boolean;
  setCategoryFilter: (filter: string | undefined) => void;
  setEnabledOnly: (enabled: boolean) => void;
  fetchSkills: () => Promise<void>;
  toggleSkill: (id: string, enable: boolean) => Promise<void>;
  deleteSkill: (id: string) => Promise<void>;
  createSkill: (data: { name: string; description: string; category?: string }) => Promise<void>;
}

export const useSkillStore = create<SkillState>((set, get) => ({
  skills: [],
  loading: false,
  categoryFilter: undefined,
  enabledOnly: false,

  setCategoryFilter: (filter) => {
    set({ categoryFilter: filter });
    get().fetchSkills();
  },

  setEnabledOnly: (enabled) => {
    set({ enabledOnly: enabled });
    get().fetchSkills();
  },

  fetchSkills: async () => {
    set({ loading: true });
    try {
      const { categoryFilter, enabledOnly } = get();
      const res = await skillApi.list({ category: categoryFilter, enabled_only: enabledOnly });
      set({ skills: res.skills || [] });
    } catch {
      set({ skills: [] });
    } finally {
      set({ loading: false });
    }
  },

  toggleSkill: async (id, enable) => {
    if (enable) {
      await skillApi.enable(id);
    } else {
      await skillApi.disable(id);
    }
    await get().fetchSkills();
  },

  deleteSkill: async (id) => {
    await skillApi.delete(id);
    await get().fetchSkills();
  },

  createSkill: async (data) => {
    await skillApi.create(data);
    await get().fetchSkills();
  },
}));