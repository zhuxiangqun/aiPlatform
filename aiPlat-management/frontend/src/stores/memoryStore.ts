import { create } from 'zustand';
import { memoryApi, type MemorySession, type MemorySessionDetail, type MemorySearchResult } from '../services';

interface MemoryState {
  sessions: MemorySession[];
  loading: boolean;
  selectedSession: MemorySessionDetail | null;
  searchResults: MemorySearchResult[];
  fetchSessions: () => Promise<void>;
  getDetail: (sessionId: string) => Promise<void>;
  createSession: (data?: { session_id?: string; metadata?: Record<string, unknown> }) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  addMessage: (sessionId: string, data: { role: string; content: string }) => Promise<void>;
  search: (query: string) => Promise<void>;
  clearSelectedSession: () => void;
  clearSearchResults: () => void;
}

export const useMemoryStore = create<MemoryState>((set, get) => ({
  sessions: [],
  loading: false,
  selectedSession: null,
  searchResults: [],

  fetchSessions: async () => {
    set({ loading: true });
    try {
      const res = await memoryApi.listSessions();
      set({ sessions: res.sessions || [] });
    } catch {
      set({ sessions: [] });
    } finally {
      set({ loading: false });
    }
  },

  getDetail: async (sessionId) => {
    try {
      const detail = await memoryApi.getSession(sessionId);
      set({ selectedSession: detail });
    } catch {
      set({ selectedSession: null });
    }
  },

  createSession: async (data) => {
    await memoryApi.createSession(data);
    await get().fetchSessions();
  },

  deleteSession: async (sessionId) => {
    await memoryApi.deleteSession(sessionId);
    await get().fetchSessions();
  },

  addMessage: async (sessionId, data) => {
    await memoryApi.addMessage(sessionId, data);
    await get().getDetail(sessionId);
  },

  search: async (query) => {
    try {
      const res = await memoryApi.search(query);
      set({ searchResults: res.results || [] });
    } catch {
      set({ searchResults: [] });
    }
  },

  clearSelectedSession: () => set({ selectedSession: null }),
  clearSearchResults: () => set({ searchResults: [], }),
}));