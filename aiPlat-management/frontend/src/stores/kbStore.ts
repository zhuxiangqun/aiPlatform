import { create } from 'zustand';
import { kbApi } from '../services';
import type { KBDocument, KBCategory, KBConversation } from '../services';

interface ChatMessage {
  role: string;
  content: string;
  citations?: any[];
}

interface KBState {
  documents: KBDocument[];
  totalDocuments: number;
  selectedDocIds: Set<string>;
  kindCategories: KBCategory[];
  contentCategories: KBCategory[];
  activeCategory: string;

  conversation: KBConversation | null;
  messages: ChatMessage[];
  chatLoading: boolean;

  loading: boolean;
  uploadModalOpen: boolean;
  uploadProgress: { pct: number; message: string } | null;

  fetchDocuments: (collectionId?: string, category?: string) => Promise<void>;
  fetchCategories: (collectionId?: string) => Promise<void>;
  toggleDocumentSelection: (docId: string) => void;
  selectDocuments: (docIds: string[]) => void;
  clearSelection: () => void;

  createConversation: (docIds: string[], title?: string) => Promise<void>;
  sendMessage: (text: string) => Promise<void>;
  appendMessage: (msg: ChatMessage) => void;
  loadConversation: (sessionId: string) => Promise<void>;

  setUploadModalOpen: (open: boolean) => void;
  uploadDocument: (file: File, kind: 'pdf' | 'video' | 'word' | 'ppt' | 'markdown', collectionId: string) => Promise<any>;
}

export const useKBStore = create<KBState>((set, get) => ({
  documents: [],
  totalDocuments: 0,
  selectedDocIds: new Set(),
  kindCategories: [],
  contentCategories: [],
  activeCategory: 'all',

  conversation: null,
  messages: [],
  chatLoading: false,

  loading: false,
  uploadModalOpen: false,
  uploadProgress: null,

  fetchDocuments: async (collectionId?: string, category?: string) => {
    set({ loading: true });
    try {
      const res = await kbApi.listManagedDocuments(collectionId, 200, 0);
      let items = res.items || [];
      if (category && category !== 'all') {
        items = items.filter((d) => {
          const cls = d.meta?.classification || {};
          const contentCat = cls.content_category || 'general';
          const kindCat = cls.kind_category || d.kind;
          return contentCat === category || kindCat === category || d.kind === category;
        });
      }
      set({ documents: items, totalDocuments: res.total || items.length });
    } catch {
      set({ documents: [], totalDocuments: 0 });
    } finally {
      set({ loading: false });
    }
  },

  fetchCategories: async (collectionId?: string) => {
    try {
      const res = await kbApi.fetchCategories(collectionId);
      set({
        kindCategories: res.kind_categories || [],
        contentCategories: res.content_categories || [],
      });
    } catch {
      // silently ignore
    }
  },

  toggleDocumentSelection: (docId: string) => {
    const next = new Set(get().selectedDocIds);
    if (next.has(docId)) {
      next.delete(docId);
    } else {
      next.add(docId);
    }
    set({ selectedDocIds: next });
  },

  selectDocuments: (docIds: string[]) => {
    set({ selectedDocIds: new Set(docIds) });
  },

  clearSelection: () => {
    set({ selectedDocIds: new Set() });
  },

  createConversation: async (docIds: string[], title?: string) => {
    set({ chatLoading: true });
    try {
      const conv = await kbApi.createConversation({
        title: title || '资料对话',
        scope: { collection_id: 'default', doc_ids: docIds },
      });
      set({ conversation: conv, messages: conv.messages || [] });
    } catch {
      // ignore
    } finally {
      set({ chatLoading: false });
    }
  },

  sendMessage: async (text: string) => {
    const { conversation } = get();
    if (!conversation?.session_id) return;
    set({ chatLoading: true });
    try {
      await kbApi.queryConversation(conversation.session_id, {
        message: text,
        options: { citation_required: true, max_citations: 5, top_k: 8, language: 'zh-CN' },
      });
      const updated = await kbApi.getConversation(conversation.session_id);
      set({ conversation: updated, messages: updated.messages || [] });
    } catch {
      // ignore
    } finally {
      set({ chatLoading: false });
    }
  },

  appendMessage: (msg: ChatMessage) => {
    set((state) => ({ messages: [...state.messages, msg] }));
  },

  loadConversation: async (sessionId: string) => {
    set({ chatLoading: true });
    try {
      const conv = await kbApi.getConversation(sessionId);
      set({ conversation: conv, messages: conv.messages || [] });
    } catch {
      // ignore
    } finally {
      set({ chatLoading: false });
    }
  },

  setUploadModalOpen: (open: boolean) => {
    set({ uploadModalOpen: open, uploadProgress: open ? null : get().uploadProgress });
  },

  uploadDocument: async (file: File, kind: 'pdf' | 'video' | 'word' | 'ppt' | 'markdown', collectionId: string) => {
    set({ uploadProgress: { pct: 0, message: '上传中...' } });
    try {
      const res = await kbApi.uploadDocument(collectionId, file, kind);
      const jobId = res?.job?.job_id || res?.core?.job_id;
      if (jobId) {
        set({ uploadProgress: { pct: 50, message: '正在解析...' } });
        let polled = 0;
        while (polled < 120) {
          await new Promise((r) => setTimeout(r, 2000));
          try {
            const job = await kbApi.getJob(jobId);
            const status = job?.status || 'running';
            const pct = Math.min(90, (job?.progress || 0) * 100);
            set({ uploadProgress: { pct, message: job?.message || status } });
            if (status === 'completed') {
              set({ uploadProgress: { pct: 100, message: '完成' } });
              await get().fetchDocuments();
              await get().fetchCategories();
              break;
            }
            if (status === 'failed') {
              set({ uploadProgress: null });
              break;
            }
          } catch {
            break;
          }
          polled++;
        }
      }
      return res;
    } catch {
      set({ uploadProgress: null });
      throw new Error('上传失败');
    }
  },
}));
