import { apiClient } from './apiClient';

export type KBCollection = {
  collection_id: string;
  name?: string | null;
  created_at?: number;
  doc_count?: number;
};

export type KBCategory = {
  key: string;
  label: string;
  count: number;
};

export type KBDocument = {
  doc_id: string;
  collection_id: string;
  source_uri: string;
  kind: string;
  status: string;
  created_at?: number;
  meta?: Record<string, any>;
  element_count?: number;
  embedding_count?: number;
  source_count?: number;
};

export type KBDocumentSource = {
  source_id: string;
  doc_id: string;
  source_type: string;
  source_uri: string;
  url?: string | null;
  local_path?: string | null;
  kind?: string | null;
  content_type?: string | null;
  content_hash?: string | null;
  created_at?: number;
  meta?: Record<string, any>;
};

export type KBAnalysisRun = {
  run_id: string;
  doc_id?: string | null;
  collection_id?: string | null;
  run_type: string;
  mode?: string;
  retrieval_mode?: string;
  generation_mode?: string;
  created_at?: number;
  input?: Record<string, any>;
  output?: Record<string, any>;
};

export type KBAnalysisBatch = {
  batch_id: string;
  collection_id?: string | null;
  batch_type: string;
  title?: string | null;
  created_at?: number;
  input?: Record<string, any>;
  output?: Record<string, any>;
};

export type KBConversationScope = {
  collection_id: string;
  doc_ids: string[];
  version?: number;
  scope_hash?: string | null;
};

export type KBConversationMessage = {
  id?: string;
  role: string;
  content: string;
  metadata?: Record<string, any>;
  run_id?: string | null;
  created_at?: number;
};

export type KBConversation = {
  session_id: string;
  title: string;
  scope: KBConversationScope;
  profile?: Record<string, any>;
  messages: KBConversationMessage[];
  created_at?: number;
  updated_at?: number;
};

export const kbApi = {
  listCollections: async () => {
    return apiClient.get<{ collections: KBCollection[]; total: number }>('/platform/kb/collections');
  },

  getStats: async () => {
    return apiClient.get<{ documents: number; elements: number; embeddings: number; collections: number; jobs_pending: number; tenant_id: string }>('/platform/kb/stats');
  },

  reindex: async () => {
    return apiClient.post<{ status: string; count: number }>('/platform/kb/reindex', {});
  },

  createCollection: async (collection_id: string, name: string) => {
    return apiClient.post<{ status: string; collection_id: string }>('/platform/kb/collections', { collection_id, name });
  },

  listDocuments: async (collection_id: string) => {
    return apiClient.get<{ documents: KBDocument[]; total: number }>(
      `/platform/kb/collections/${encodeURIComponent(collection_id)}/documents`
    );
  },

  deleteDocument: async (doc_id: string) => {
    return apiClient.delete<{ status: string; doc_id: string }>(`/platform/kb/documents/${encodeURIComponent(doc_id)}`);
  },

  reingestDocument: async (doc_id: string) => {
    return apiClient.post<any>(`/platform/documents/${encodeURIComponent(doc_id)}/refresh`, { force: false });
  },

  refreshDocument: async (doc_id: string, force: boolean = false) => {
    return apiClient.post<any>(`/platform/documents/${encodeURIComponent(doc_id)}/refresh`, { force });
  },

  listManagedDocuments: async (collection_id?: string, limit: number = 100, offset: number = 0) => {
    const q = new URLSearchParams();
    if (collection_id) q.set('collection_id', collection_id);
    q.set('limit', String(limit));
    q.set('offset', String(offset));
    return apiClient.get<{ items: KBDocument[]; total: number }>(`/platform/documents?${q.toString()}`);
  },

  fetchCategories: async (collection_id?: string) => {
    const q = collection_id ? `?collection_id=${encodeURIComponent(collection_id)}` : '';
    return apiClient.get<{ kind_categories: KBCategory[]; content_categories: KBCategory[] }>(
      `/platform/documents/categories${q}`
    );
  },

  getDocument: async (doc_id: string) => {
    return apiClient.get<KBDocument>(`/platform/documents/${encodeURIComponent(doc_id)}`);
  },

  listDocumentSources: async (doc_id: string, limit: number = 100, offset: number = 0) => {
    return apiClient.get<{ items: KBDocumentSource[]; total: number }>(
      `/platform/documents/${encodeURIComponent(doc_id)}/sources?limit=${encodeURIComponent(String(limit))}&offset=${encodeURIComponent(
        String(offset)
      )}`
    );
  },

  listDocumentElements: async (doc_id: string, type?: string, limit: number = 200, offset: number = 0) => {
    const q = new URLSearchParams();
    if (type) q.set('type', type);
    q.set('limit', String(limit));
    q.set('offset', String(offset));
    return apiClient.get<{ items: any[]; total: number }>(`/platform/documents/${encodeURIComponent(doc_id)}/elements?${q.toString()}`);
  },

  exportDocument: async (doc_id: string, format: 'json' | 'markdown' = 'json', include_embeddings: boolean = false) => {
    const q = new URLSearchParams();
    q.set('format', format);
    if (include_embeddings) q.set('include_embeddings', 'true');
    return apiClient.get<any>(`/platform/documents/${encodeURIComponent(doc_id)}/export?${q.toString()}`);
  },

  documentQuery: async (doc_id: string, question: string, top_k: number = 5) => {
    return apiClient.post<any>('/platform/documents/query', { doc_id, collection_id: 'default', question, top_k });
  },

  collectionQuery: async (collection_id: string, question: string, top_k: number = 8) => {
    return apiClient.post<any>('/platform/collections/query', { collection_id, question, top_k });
  },

  rewriteCollectionAnswer: async (collection_id: string, question: string, current_answer: string, items: any[]) => {
    return apiClient.post<any>('/platform/collections/rewrite-answer', {
      collection_id,
      question,
      current_answer,
      items: Array.isArray(items) ? items : [],
    });
  },

  documentSummarize: async (doc_id: string, profile: string = 'key_points', max_points: number = 5) => {
    return apiClient.post<any>('/platform/documents/summarize', { doc_id, profile, max_points });
  },

  listDocumentAnalysisRuns: async (doc_id: string, run_type?: string, limit: number = 50, offset: number = 0, keyword?: string) => {
    const qs = new URLSearchParams();
    if (run_type) qs.set('run_type', run_type);
    qs.set('limit', String(limit));
    qs.set('offset', String(offset));
    if (keyword) qs.set('q', keyword);
    return apiClient.get<{ items: KBAnalysisRun[]; total: number }>(
      `/platform/documents/${encodeURIComponent(doc_id)}/analysis-runs?${qs.toString()}`
    );
  },

  deleteDocumentAnalysisRun: async (doc_id: string, run_id: string) => {
    return apiClient.delete<{ status: string; doc_id: string; run_id: string }>(
      `/platform/documents/${encodeURIComponent(doc_id)}/analysis-runs/${encodeURIComponent(run_id)}`
    );
  },

  createAnalysisBatch: async (payload: {
    collection_id: string;
    batch_type: string;
    title?: string;
    input?: Record<string, any>;
    output?: Record<string, any>;
  }) => {
    return apiClient.post<{ status: string; batch_id: string }>('/platform/analysis-batches', payload);
  },

  listAnalysisBatches: async (collection_id?: string, batch_type?: string, limit: number = 50, offset: number = 0, keyword?: string) => {
    const qs = new URLSearchParams();
    if (collection_id) qs.set('collection_id', collection_id);
    if (batch_type) qs.set('batch_type', batch_type);
    qs.set('limit', String(limit));
    qs.set('offset', String(offset));
    if (keyword) qs.set('q', keyword);
    return apiClient.get<{ items: KBAnalysisBatch[]; total: number }>(`/platform/analysis-batches?${qs.toString()}`);
  },

  deleteAnalysisBatch: async (batch_id: string) => {
    return apiClient.delete<{ status: string; batch_id: string }>(`/platform/analysis-batches/${encodeURIComponent(batch_id)}`);
  },

  uploadDocument: async (collection_id: string, file: File, kind: 'pdf' | 'video' | 'word' | 'ppt' | 'markdown' = 'pdf') => {
    // Use ingest endpoint which properly handles all file types (video, audio, pdf, etc.)
    // via async pipeline: ffmpeg extraction → whisper transcription → keyframe OCR → embed
    const baseUrl = (import.meta as any).env?.VITE_API_URL || '/api';
    const url = `${baseUrl}/platform/documents/ingest`;
    const form = new FormData();
    form.append('file', file, file.name);
    form.append('kind', kind);
    form.append('collection_id', collection_id);

    const headers: Record<string, string> = {};
    try {
      const tenantId = localStorage.getItem('active_tenant_id') || '';
      const actorId = localStorage.getItem('active_actor_id') || 'admin';
      const actorRole = localStorage.getItem('active_actor_role') || 'admin';
      const scopes = localStorage.getItem('active_scopes') || 'kb:read,kb:write';
      const releaseChannel = localStorage.getItem('active_release_channel') || '';
      const apiKey = localStorage.getItem('active_api_key') || '';
      if (tenantId.trim()) headers['X-AIPLAT-TENANT-ID'] = tenantId.trim();
      if (actorId.trim()) headers['X-AIPLAT-ACTOR-ID'] = actorId.trim();
      if (actorRole.trim()) headers['X-AIPLAT-ACTOR-ROLE'] = actorRole.trim();
      if (scopes.trim()) headers['X-AIPLAT-SCOPES'] = scopes.trim();
      if (releaseChannel.trim()) headers['X-AIPLAT-RELEASE-CHANNEL'] = releaseChannel.trim();
      if (apiKey.trim()) headers['X-AIPLAT-API-KEY'] = apiKey.trim();
    } catch {
      // ignore
    }

    const resp = await fetch(url, { method: 'POST', body: form, headers });
    if (!resp.ok) {
      const payload: any = await resp.json().catch(() => null);
      const msg = payload?.detail || payload?.message || `HTTP error! status: ${resp.status}`;
      const err: any = new Error(String(msg));
      err.status = resp.status;
      err.payload = payload;
      throw err;
    }
    return resp.json();
  },

  previewDocument: async (file: File, kind: string, collection_id: string) => {
    const baseUrl = (import.meta as any).env?.VITE_API_URL || '/api';
    const url = `${baseUrl}/platform/documents/preview`;
    const form = new FormData();
    form.append('file', file, file.name);
    form.append('kind', kind);
    form.append('collection_id', collection_id);
    const headers: Record<string, string> = {};
    try {
      const tenantId = localStorage.getItem('active_tenant_id') || '';
      const actorId = localStorage.getItem('active_actor_id') || 'admin';
      const actorRole = localStorage.getItem('active_actor_role') || 'admin';
      const scopes = localStorage.getItem('active_scopes') || 'kb:read,kb:write';
      const apiKey = localStorage.getItem('active_api_key') || '';
      if (tenantId.trim()) headers['X-AIPLAT-TENANT-ID'] = tenantId.trim();
      if (actorId.trim()) headers['X-AIPLAT-ACTOR-ID'] = actorId.trim();
      if (actorRole.trim()) headers['X-AIPLAT-ACTOR-ROLE'] = actorRole.trim();
      if (scopes.trim()) headers['X-AIPLAT-SCOPES'] = scopes.trim();
      if (apiKey.trim()) headers['X-AIPLAT-API-KEY'] = apiKey.trim();
    } catch { /* ignore */ }
    const resp = await fetch(url, { method: 'POST', body: form, headers });
    if (!resp.ok) {
      const payload: any = await resp.json().catch(() => null);
      const msg = payload?.detail || payload?.message || `HTTP error! status: ${resp.status}`;
      const err: any = new Error(String(msg));
      err.status = resp.status;
      throw err;
    }
    return resp.json();
  },

  previewDocumentByUrl: async (url: string, collection_id: string) => {
    return apiClient.post<any>('/platform/documents/preview', {
      url,
      collection_id,
    });
  },

  ingestDocumentByFilePath: async (file_path: string, collection_id: string, kind: string) => {
    return apiClient.post<any>('/platform/documents/ingest', {
      collection_id,
      file_path,
      kind,
    });
  },

  ingestDocumentByUrl: async (
    collection_id: string,
    url: string,
    kind: string = 'pdf',
    ocr_lang: string = 'zh',
    max_pages: number = 60
  ) => {
    return apiClient.post<any>('/platform/documents/ingest', {
      collection_id,
      url,
      kind,
      ocr_lang,
      max_pages,
    });
  },

  getJob: async (job_id: string) => {
    return apiClient.get<any>(`/platform/kb/jobs/${encodeURIComponent(job_id)}`);
  },

  listJobEvents: async (job_id: string, limit: number = 200, offset: number = 0) => {
    return apiClient.get<any>(
      `/platform/kb/jobs/${encodeURIComponent(job_id)}/events?limit=${encodeURIComponent(String(limit))}&offset=${encodeURIComponent(
        String(offset)
      )}`
    );
  },

  createConversation: async (payload: { title?: string; scope?: KBConversationScope; profile?: Record<string, any> }) => {
    return apiClient.post<KBConversation>('/platform/conversations', payload);
  },

  listConversations: async (limit: number = 100, offset: number = 0) => {
    return apiClient.get<{ items: KBConversation[]; total: number }>(
      `/platform/conversations?limit=${encodeURIComponent(String(limit))}&offset=${encodeURIComponent(String(offset))}`
    );
  },

  getConversation: async (sessionId: string) => {
    return apiClient.get<KBConversation>(`/platform/conversations/${encodeURIComponent(sessionId)}`);
  },

  updateConversationScope: async (sessionId: string, scope: KBConversationScope) => {
    return apiClient.put<{ ok: boolean; scope: KBConversationScope }>(`/platform/conversations/${encodeURIComponent(sessionId)}/scope`, scope);
  },

  queryConversation: async (
    sessionId: string,
    payload: { message: string; scope_override?: KBConversationScope | null; options?: Record<string, any> }
  ) => {
    return apiClient.post<any>(`/platform/conversations/${encodeURIComponent(sessionId)}/query`, payload);
  },

  // ── Eval ──
  listEvalSamples: async (limit = 50, offset = 0) => {
    return apiClient.get<any>(`/core/kb-eval/samples?limit=${limit}&offset=${offset}`);
  },
  createEvalSample: async (data: { question: string; ground_truth: string; doc_ids: string[]; tags: string[] }) => {
    return apiClient.post<any>('/core/kb-eval/samples', data);
  },
  deleteEvalSample: async (id: string) => {
    return apiClient.delete<any>(`/core/kb-eval/samples/${id}`);
  },
  runEval: async (body: { tag?: string; sample_ids?: string[] }) => {
    return apiClient.post<any>('/core/kb-eval/run', body);
  },
  listEvalReports: async (limit = 50, offset = 0) => {
    return apiClient.get<any>(`/core/kb-eval/reports?limit=${limit}&offset=${offset}`);
  },

  // ── Tools ──
  createWithAi: async (title: string, prompt: string, collection_id = 'default') => {
    return apiClient.post<any>('/platform/kb/documents/create-with-ai', { title, prompt, collection_id });
  },
  cleanupStorage: async () => {
    return apiClient.post<any>('/platform/kb/storage/cleanup', {});
  },
  getStorageStats: async () => {
    return apiClient.get<any>('/platform/kb/storage/stats');
  },
  updateDocMeta: async (docId: string, meta: any) => {
    return apiClient.put<any>(`/platform/kb/documents/${docId}/meta`, meta);
  },
  updateDocContent: async (docId: string, content: string) => {
    return apiClient.put<any>(`/platform/kb/documents/${docId}/content`, { content });
  },
  getDocVersions: async (docId: string) => {
    return apiClient.get<any>(`/platform/kb/documents/${docId}/versions`);
  },
};
