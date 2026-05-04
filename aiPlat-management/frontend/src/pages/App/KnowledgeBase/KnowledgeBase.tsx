import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Card, CardContent, CardHeader, Input, Modal, Progress, Table, toast } from '../../../components/ui';

const _copyText = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
    toast.success('已复制到剪贴板');
  } catch {
    try {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      toast.success('已复制到剪贴板');
    } catch (e) {
      toast.error('复制失败');
    }
  }
};

const _tsSlug = () => {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
};

const _downloadText = (filename: string, text: string, mime: string = 'text/plain;charset=utf-8') => {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
};

const _cleanSnippet = (text: any) =>
  String(text || '')
    .replace(/\r/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

const _snippetPreview = (text: any, limit: number = 220) => {
  const s = _cleanSnippet(text).replace(/\n/g, ' ');
  return s.length > limit ? `${s.slice(0, limit)}...` : s;
};

const _snippetTitle = (text: any) => {
  const s = _cleanSnippet(text);
  const m = s.match(/【([^】]{1,80})】/);
  if (m?.[1]) return m[1];
  const first = s.split('\n').find((x) => String(x || '').trim());
  return String(first || '命中片段').slice(0, 60);
};

const _meaningfulLines = (text: any) =>
  _cleanSnippet(text)
    .split('\n')
    .map((x) => String(x || '').trim())
    .map((x) => x.replace(/^[。·•\-●■□◇◆○◎◉◌〇圆]+/, '').trim())
    .map((x) => x.replace(/[「」【】]/g, ''))
    .map((x) => x.replace(/[J】〕]/g, ''))
    .map((x) => x.replace(/\s+/g, ' '))
    .filter(Boolean)
    .filter((x) => !/排版建议|字号|加粗|背景|留白|居中|浅灰|深蓝|边框|pt|布局|表格占页面|三栏|四宫格|目录|封面|项目符号|主题:|副标题:|定制部门:|日期:|投资周期/.test(x))
    .filter((x) => !/^\d+\.\s*$/.test(x))
    .filter((x) => !/^[Pp]\d+/.test(x))
    .filter((x) => !/^[一二三四五六七八九十]、?$/.test(x))
    .filter((x) => x.length >= 6);

const _dedupe = (arr: string[]) => {
  const seen = new Set<string>();
  const out: string[] = [];
  arr.forEach((x) => {
    const k = x.replace(/\s+/g, ' ').trim();
    if (!k || seen.has(k)) return;
    seen.add(k);
    out.push(x);
  });
  return out;
};

const _prettyLine = (text: any) =>
  String(text || '')
    .replace(/^[。·•\-●■□◇◆○◎◉◌〇圆]+/, '')
    .replace(/\s+/g, ' ')
    .trim();

const _questionKeywords = (question: any) => {
  const normalized = String(question || '')
    .replace(/[？?，。,.\s]/g, '')
    .replace(/是什么|有哪些|有什么|多少|如何|怎么|有关|关于|请问|一下|一下子|吗|呢|的/g, ' ')
    .trim();
  const tokens = (normalized.match(/[A-Za-z0-9\u4e00-\u9fa5]+/g) || [])
    .map((x) => x.trim())
    .filter(Boolean);
  return _dedupe(tokens).sort((a, b) => b.length - a.length);
};

const _questionFocusScore = (text: any, question: any) => {
  const body = _cleanSnippet(text);
  const q = String(question || '').trim();
  const kws = _questionKeywords(q);
  let score = 0;
  if (q && body.includes(q.replace(/[？?]/g, ''))) score += 3;
  kws.forEach((kw) => {
    if (kw && body.includes(kw)) score += Math.min(2, 0.4 + kw.length * 0.15);
  });
  if (/目标/.test(q) && /营业额|净利润|目标/.test(body)) score += 1.2;
  if (/2026|2027|2028|3年/.test(q) && /2026|2027|2028|3年/.test(body)) score += 1;
  return score;
};

const _isPreciseQuestion = (question: any) => {
  const q = String(question || '').trim();
  const kws = _questionKeywords(q);
  return q.length <= 16 || kws.length <= 3 || /是什么|多少|谁|哪年|何时|目标|预算|利润|营收/.test(q);
};

const _fmtMs = (ms: any) => {
  const n = Number(ms);
  if (!Number.isFinite(n) || n < 0) return '-';
  const total = Math.floor(n / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (x: number) => String(x).padStart(2, '0');
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
};

const _citationLabel = (c: any) => {
  if (c?.asset_kind === 'frame_image') {
    const start = c?.start_ms ?? c?.time_ms;
    const end = c?.end_ms;
    return end !== undefined && end !== null ? `${_fmtMs(start)} - ${_fmtMs(end)}` : `${_fmtMs(start)}`;
  }
  return `p${String(c?.page_idx ?? '-')}`;
};

const _itemTimeLabel = (it: any) => {
  const m = it?.meta || {};
  const start = m?.start_ms ?? m?.time_ms ?? it?.time_ms;
  const end = m?.end_ms;
  if (start === undefined || start === null) return `p${String(it?.page_idx ?? '-')}`;
  return end !== undefined && end !== null ? `${_fmtMs(start)} - ${_fmtMs(end)}` : `${_fmtMs(start)}`;
};

const _isVideoItem = (it: any) => String(it?.doc_kind || '').toLowerCase() === 'video' || String(it?.meta?.source || '').startsWith('video_');

const _kbFriendlyError = (err: any) => {
  const msg = String(err?.message || err || '');
  if (msg.includes('whisper_not_installed')) return '当前环境尚未安装 Whisper 转写依赖，暂时无法解析视频语音。';
  if (msg.includes('ffmpeg_not_found')) return '当前环境缺少 ffmpeg，无法处理视频音频抽取。';
  if (msg.includes('ffprobe_not_found')) return '当前环境缺少 ffprobe，无法读取视频元数据。';
  if (msg.includes('video_page_requires_ytdlp')) return '视频平台页面链接需要服务端安装 yt-dlp；当前更建议先使用可直接下载的视频直链。';
  if (msg.includes('video_download_failed')) return '视频下载失败，请检查链接是否可访问，或改用视频直链。';
  if (msg.includes('no_video_content_extracted')) return '视频未能提取出任何可检索内容。可能没有可识别语音，也没有可读字幕/画面文字。';
  if (msg.includes('ingest_job_not_created')) return '导入请求没有成功创建任务，请检查服务是否已重启到最新代码。';
  if (msg.includes('file_too_large')) return '文件过大，当前上传限制已超出。';
  if (msg.includes('file_path_not_accessible')) return '服务端无法访问该文件路径。';
  return msg;
};

const _citationKey = (docId: string, pageIdx: any) => `${String(docId || '')}__${String(pageIdx ?? '')}`;
const _citationAssetUrl = (citation: any) => {
  const raw = String(citation?.asset_url || '').trim();
  if (!raw) return '';
  return raw.startsWith('/platform/') ? `/api${raw}` : raw;
};
import { kbApi, KBAnalysisBatch, KBAnalysisRun, KBCollection, KBDocument, KBDocumentSource } from '../../../services/kbApi';

type TabKey = 'collections' | 'documents' | 'query' | 'settings';

const KnowledgeBase: React.FC = () => {
  const navigate = useNavigate();
  const [tab, setTab] = useState<TabKey>('collections');

  // Settings
  const [apiKey, setApiKey] = useState(localStorage.getItem('active_api_key') || '');
  const [tenantId, setTenantId] = useState(localStorage.getItem('active_tenant_id') || 'default');

  // Collections
  const [collections, setCollections] = useState<KBCollection[]>([]);
  const [selectedCollection, setSelectedCollection] = useState<string>('default');
  const [loadingCollections, setLoadingCollections] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [newCollectionId, setNewCollectionId] = useState('');
  const [newCollectionName, setNewCollectionName] = useState('');

  // Documents
  const [documents, setDocuments] = useState<KBDocument[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [urlIngesting, setUrlIngesting] = useState(false);
  const [urlInput, setUrlInput] = useState('');
  const [uploadKind, setUploadKind] = useState<'pdf' | 'video'>('pdf');
  const [urlKind, setUrlKind] = useState<'pdf' | 'video'>('pdf');
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [batchActing, setBatchActing] = useState(false);
  const [batchMoreOpen, setBatchMoreOpen] = useState(false);
  const [batchRecordsOpen, setBatchRecordsOpen] = useState(false);
  const [batchRecordsLoading, setBatchRecordsLoading] = useState(false);
  const [batchRecords, setBatchRecords] = useState<KBAnalysisBatch[]>([]);
  const [batchRecordFilter, setBatchRecordFilter] = useState<'all' | 'query' | 'summarize'>('all');
  const [batchRecordKeyword, setBatchRecordKeyword] = useState('');
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [activeJobId, setActiveJobId] = useState<string>('');
  const [activeJob, setActiveJob] = useState<any>(null);
  const [jobPolling, setJobPolling] = useState(false);
  const [jobEventsOpen, setJobEventsOpen] = useState(false);
  const [jobEvents, setJobEvents] = useState<any[]>([]);
  const [jobEventsLoading, setJobEventsLoading] = useState(false);
  const [autoOpenedFailDiag, setAutoOpenedFailDiag] = useState<string>('');
  const [docDetailOpen, setDocDetailOpen] = useState(false);
  const [docDetailLoading, setDocDetailLoading] = useState(false);
  const [docDetailOrigin, setDocDetailOrigin] = useState<'documents' | 'query' | 'other'>('documents');
  const [selectedDoc, setSelectedDoc] = useState<KBDocument | null>(null);
  const [selectedDocSources, setSelectedDocSources] = useState<KBDocumentSource[]>([]);
  const [selectedDocElements, setSelectedDocElements] = useState<any[]>([]);
  const [selectedDocAnalysisRuns, setSelectedDocAnalysisRuns] = useState<KBAnalysisRun[]>([]);
  const [analysisRunFilter, setAnalysisRunFilter] = useState<'all' | 'query' | 'summarize'>('all');
  const [analysisRunKeyword, setAnalysisRunKeyword] = useState('');
  const [docQuestion, setDocQuestion] = useState('这份文档讲了什么？');
  const [docQueryScope, setDocQueryScope] = useState<'document' | 'collection'>('document');
  const [docQueryLoading, setDocQueryLoading] = useState(false);
  const [docQueryResp, setDocQueryResp] = useState<any>(null);
  const [docSummarizeLoading, setDocSummarizeLoading] = useState(false);
  const [docSummarizeResp, setDocSummarizeResp] = useState<any>(null);
  const [citationImageUrls, setCitationImageUrls] = useState<Record<string, string>>({});
  const [citationImageFailures, setCitationImageFailures] = useState<Record<string, boolean>>({});
  const [focusedPageIdx, setFocusedPageIdx] = useState<number | null>(null);

  // Query
  const [question, setQuestion] = useState('这个集合里有哪些关键信息？');
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryResp, setQueryResp] = useState<any>(null);
  const [queryRewriteLoading, setQueryRewriteLoading] = useState(false);
  const [rewrittenAnswer, setRewrittenAnswer] = useState('');
  const [rewrittenAnswerMode, setRewrittenAnswerMode] = useState<'llm' | 'local'>('llm');
  const [queryViewMode, setQueryViewMode] = useState<'auto' | 'precise' | 'analysis'>(
    () => (localStorage.getItem('kb_query_view_mode') as 'auto' | 'precise' | 'analysis') || 'auto'
  );
  const [queryScope, setQueryScope] = useState<'collection' | 'document'>('collection');
  const [queryDocId, setQueryDocId] = useState<string>('');
  const [queryPreviewItem, setQueryPreviewItem] = useState<any>(null);
  const [queryHighScoreOnly, setQueryHighScoreOnly] = useState(false);
  const [queryShowAllEvidence, setQueryShowAllEvidence] = useState(false);
  const [queryExpandedView, setQueryExpandedView] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

  const collectionOptions = useMemo(() => {
    const ids = new Set<string>(['default']);
    collections.forEach((c) => ids.add(c.collection_id));
    return Array.from(ids);
  }, [collections]);
  const queryDocOptions = useMemo(
    () =>
      documents.map((d) => ({
        value: d.doc_id,
        label: [
          String(d?.meta?.title || '').trim() || String(d.source_uri || '').split('/').filter(Boolean).pop() || d.doc_id,
          d.kind ? String(d.kind).toUpperCase() : '',
          String(d.source_uri || '').startsWith('http') ? 'URL' : '本地',
        ]
          .filter(Boolean)
          .join(' · '),
      })),
    [documents]
  );

  const refreshCollections = async () => {
    setLoadingCollections(true);
    try {
      const res = await kbApi.listCollections();
      setCollections(res.collections || []);
      if (res.collections?.length && !collectionOptions.includes(selectedCollection)) {
        setSelectedCollection(res.collections[0].collection_id);
      }
    } catch (e: any) {
      toast.error(`加载集合失败：${e?.message || e}`);
    } finally {
      setLoadingCollections(false);
    }
  };

  const refreshDocuments = async () => {
    setLoadingDocs(true);
    try {
      const res = await kbApi.listManagedDocuments(selectedCollection, 100, 0);
      setDocuments(res.items || []);
    } catch (e: any) {
      toast.error(`加载文档失败：${e?.message || e}`);
    } finally {
      setLoadingDocs(false);
    }
  };

  useEffect(() => {
    if (queryScope !== 'document') return;
    if (queryDocId && documents.some((d) => d.doc_id === queryDocId)) return;
    if (documents.length > 0) {
      setQueryDocId(documents[0].doc_id);
    } else {
      setQueryScope('collection');
      setQueryDocId('');
    }
  }, [documents, queryDocId, queryScope]);

  useEffect(() => {
    refreshCollections();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (tab === 'documents' || tab === 'query') {
      refreshDocuments();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCollection, tab]);

  useEffect(() => {
    localStorage.setItem('kb_query_view_mode', queryViewMode);
  }, [queryViewMode]);

  useEffect(() => {
    const visible = new Set(documents.map((d) => String(d.doc_id)));
    setSelectedDocIds((prev) => prev.filter((id) => visible.has(id)));
  }, [documents]);

  const saveSettings = () => {
    localStorage.setItem('active_api_key', apiKey.trim());
    localStorage.setItem('active_tenant_id', tenantId.trim() || 'default');
    localStorage.setItem('active_actor_id', localStorage.getItem('active_actor_id') || 'admin');
    localStorage.setItem('active_actor_role', localStorage.getItem('active_actor_role') || 'admin');
    localStorage.setItem('active_scopes', localStorage.getItem('active_scopes') || 'kb:read,kb:write');
    toast.success('已保存认证配置（将用于平台 API 调用）');
  };

  const onCreateCollection = async () => {
    if (!newCollectionId.trim()) {
      toast.error('请输入 collection_id');
      return;
    }
    try {
      await kbApi.createCollection(newCollectionId.trim(), newCollectionName.trim());
      toast.success('集合创建成功');
      setCreateOpen(false);
      setNewCollectionId('');
      setNewCollectionName('');
      await refreshCollections();
    } catch (e: any) {
      toast.error(`创建集合失败：${e?.message || e}`);
    }
  };

  const onUpload = async (file: File) => {
    setUploading(true);
    try {
      const res = await kbApi.uploadDocument(selectedCollection, file, uploadKind);
      const jobId =
        res?.job?.job_id ||
        res?.job_id ||
        res?.core?.output?.output?.job_id ||
        res?.core?.output?.job_id ||
        '';
      if (jobId) {
        setActiveJobId(String(jobId));
        toast.success(`已创建入库任务：${jobId}`);
      } else {
        toast.success('上传成功（未返回 job_id，可能为旧接口响应）');
      }
      // refresh docs right away so queued/ingesting doc is visible
      await refreshDocuments();
      setQueryResp(res);
      setTab('documents');
    } catch (e: any) {
      toast.error(`上传失败：${_kbFriendlyError(e)}`);
    } finally {
      setUploading(false);
    }
  };

  const onUrlIngest = async () => {
    const raw = String(urlInput || '').trim();
    if (!raw) {
      toast.error('请输入文档 URL');
      return;
    }
    if (!/^https?:\/\//i.test(raw)) {
      toast.error('URL 必须以 http:// 或 https:// 开头');
      return;
    }
    setUrlIngesting(true);
    try {
      const res = await kbApi.ingestDocumentByUrl(selectedCollection, raw, urlKind, 'zh', 60);
      const jobId = String(res?.job?.job_id || res?.job_id || res?.core?.output?.output?.job_id || res?.core?.output?.job_id || '');
      if (!jobId) {
        throw new Error('ingest_job_not_created');
      }
      setActiveJobId(jobId);
      setJobPolling(true);
      toast.success('URL 导入任务已提交');
      setUrlInput('');
      await refreshDocuments();
    } catch (e: any) {
      toast.error(`URL 导入失败：${_kbFriendlyError(e)}`);
    } finally {
      setUrlIngesting(false);
    }
  };

  // Poll active job (ingest) status
  useEffect(() => {
    if (!activeJobId) return;
    let stopped = false;
    setJobPolling(true);

    const tick = async () => {
      try {
        const j = await kbApi.getJob(activeJobId);
        if (stopped) return;
        setActiveJob(j);
        const st = String(j?.status || '');
        if (st === 'completed' || st === 'failed' || st === 'canceled') {
          setJobPolling(false);
          // refresh docs when job finishes
          await refreshDocuments();
          if (st === 'completed') toast.success(`入库完成：${activeJobId}`);
          if (st === 'failed') {
            toast.error(`入库失败：${_kbFriendlyError(j?.message || activeJobId)}`);
            // Auto open diagnostic panel once per job
            if (autoOpenedFailDiag !== activeJobId) {
              setAutoOpenedFailDiag(activeJobId);
              await loadJobEvents(activeJobId);
              setJobEventsOpen(true);
            }
          }
          return true;
        }
      } catch (e: any) {
        // do not spam toast; keep polling
      }
      return false;
    };

    const timer = window.setInterval(async () => {
      const done = await tick();
      if (done) window.clearInterval(timer);
    }, 2000);

    // fire immediately
    tick();

    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeJobId, autoOpenedFailDiag]);

  const loadJobEvents = async (jobId?: string) => {
    const jid = String(jobId || activeJobId || '');
    if (!jid) return;
    setJobEventsLoading(true);
    try {
      const res = await kbApi.listJobEvents(jid, 200, 0);
      setJobEvents(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      toast.error(`加载任务日志失败：${e?.message || e}`);
    } finally {
      setJobEventsLoading(false);
    }
  };

  const onDeleteDoc = async (docId: string) => {
    if (!confirm(`确认删除文档 ${docId}？`)) return;
    try {
      await kbApi.deleteDocument(docId);
      toast.success('已删除');
      await refreshDocuments();
    } catch (e: any) {
      toast.error(`删除失败：${e?.message || e}`);
    }
  };

  const toggleDocSelection = (docId: string, checked: boolean) => {
    setSelectedDocIds((prev) => {
      const set = new Set(prev);
      if (checked) set.add(docId);
      else set.delete(docId);
      return Array.from(set);
    });
  };

  const toggleSelectAllVisibleDocs = (checked: boolean) => {
    if (checked) {
      setSelectedDocIds(documents.map((d) => String(d.doc_id)));
    } else {
      setSelectedDocIds([]);
    }
  };

  const batchRefreshDocs = async (force: boolean = false) => {
    if (selectedDocIds.length === 0) return;
    setBatchActing(true);
    try {
      for (const docId of selectedDocIds) {
        await kbApi.refreshDocument(docId, force);
      }
      toast.success(force ? `已批量强制刷新 ${selectedDocIds.length} 个文档` : `已批量刷新 ${selectedDocIds.length} 个文档`);
      await refreshDocuments();
    } catch (e: any) {
      toast.error(`批量刷新失败：${e?.message || e}`);
    } finally {
      setBatchActing(false);
    }
  };

  const batchDeleteDocs = async () => {
    if (selectedDocIds.length === 0) return;
    if (!confirm(`确认批量删除 ${selectedDocIds.length} 个文档？`)) return;
    setBatchActing(true);
    try {
      for (const docId of selectedDocIds) {
        await kbApi.deleteDocument(docId);
      }
      setSelectedDocIds([]);
      toast.success(`已批量删除 ${selectedDocIds.length} 个文档`);
      await refreshDocuments();
    } catch (e: any) {
      toast.error(`批量删除失败：${e?.message || e}`);
    } finally {
      setBatchActing(false);
    }
  };

  const batchCopyDocIds = async () => {
    if (selectedDocIds.length === 0) return;
    await _copyText(selectedDocIds.join('\n'));
  };

  const loadBatchRecords = async () => {
    setBatchRecordsLoading(true);
    try {
      const res = await kbApi.listAnalysisBatches(
        selectedCollection,
        batchRecordFilter === 'all' ? undefined : batchRecordFilter,
        50,
        0,
        batchRecordKeyword.trim() || undefined
      );
      setBatchRecords(res.items || []);
    } catch (e: any) {
      toast.error(`加载批次记录失败：${e?.message || e}`);
    } finally {
      setBatchRecordsLoading(false);
    }
  };

  useEffect(() => {
    if (!batchRecordsOpen) return;
    loadBatchRecords();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchRecordsOpen, batchRecordFilter, batchRecordKeyword, selectedCollection]);

  const deleteBatchRecord = async (batchId: string) => {
    if (!confirm('确认删除这条批次记录？')) return;
    try {
      await kbApi.deleteAnalysisBatch(batchId);
      await loadBatchRecords();
      toast.success('批次记录已删除');
    } catch (e: any) {
      toast.error(`删除批次记录失败：${e?.message || e}`);
    }
  };

  const replayBatchRecord = async (batch: KBAnalysisBatch) => {
    const input = (batch.input || {}) as any;
    const docIds = Array.isArray(input?.doc_ids) ? input.doc_ids.map((x: any) => String(x)) : [];
    if (batch.collection_id) {
      setSelectedCollection(String(batch.collection_id));
    }
    if (docIds.length > 0) {
      setSelectedDocIds(docIds);
    }
    if (String(batch.batch_type || '') === 'query' && input?.question) {
      setQuestion(String(input.question));
    }
    setTab('documents');
    toast.success('已回放批次记录');
  };

  const batchExportDocs = async (format: 'json' | 'markdown') => {
    if (selectedDocIds.length === 0) return;
    setBatchActing(true);
    try {
      const outputs: any[] = [];
      for (const docId of selectedDocIds) {
        const res = await kbApi.exportDocument(docId, format, false);
        outputs.push({ doc_id: docId, data: res });
      }
      if (format === 'json') {
        const jsonText = JSON.stringify(outputs, null, 2);
        _downloadText(`kb_batch_export_${selectedCollection || 'default'}_${_tsSlug()}.json`, jsonText, 'application/json;charset=utf-8');
        await _copyText(jsonText);
      } else {
        const text = outputs
          .map((x) => {
            const content = String(x?.data?.content || '').trim();
            return [`<!-- doc_id: ${x.doc_id} -->`, content].join('\n');
          })
          .join('\n\n---\n\n');
        _downloadText(`kb_batch_export_${selectedCollection || 'default'}_${_tsSlug()}.md`, text, 'text/markdown;charset=utf-8');
        await _copyText(text);
      }
      toast.success(`已批量导出 ${selectedDocIds.length} 个文档的 ${format} 并下载文件`);
    } catch (e: any) {
      toast.error(`批量导出失败：${e?.message || e}`);
    } finally {
      setBatchActing(false);
    }
  };

  const batchSummarizeDocs = async () => {
    if (selectedDocIds.length === 0) return;
    setBatchActing(true);
    try {
      const pickedDocs = documents.filter((d) => selectedDocIds.includes(String(d.doc_id)));
      const sections: string[] = [];
      for (const doc of pickedDocs) {
        const res = await kbApi.documentSummarize(String(doc.doc_id), 'key_points', 5);
        const out = (res?.output || res || {}) as any;
        const summary = String(out?.summary || '').trim();
        const points = Array.isArray(out?.points) ? out.points : [];
        const lines = [
          `## ${String(doc.doc_id)}`,
          ``,
          `- collection_id: ${String(doc.collection_id || '')}`,
          `- kind: ${String(doc.kind || '')}`,
          `- mode: ${String(out?.mode || '')}`,
          `- source_uri: ${String(doc.source_uri || '')}`,
          ``,
          `### summary`,
          summary || '(empty)',
          ``,
          `### points`,
          ...(points.length > 0
            ? points.map((p: any, idx: number) => `${idx + 1}. p${String(p?.page_idx ?? '-')} ${String(p?.text || '')}`)
            : ['(none)']),
        ];
        sections.push(lines.join('\n'));
      }
      const report = ['# 批量文档总结', '', ...sections].join('\n\n---\n\n');
      _downloadText(`kb_batch_summarize_${selectedCollection || 'default'}_${_tsSlug()}.md`, report, 'text/markdown;charset=utf-8');
      await _copyText(report);
      await kbApi.createAnalysisBatch({
        collection_id: selectedCollection || 'default',
        batch_type: 'summarize',
        title: `批量总结 ${new Date().toLocaleString()}`,
        input: { doc_ids: pickedDocs.map((d) => d.doc_id), profile: 'key_points', max_points: 5 },
        output: { report, count: pickedDocs.length },
      });
      toast.success(`已批量总结 ${selectedDocIds.length} 个文档，并下载/复制结果`);
    } catch (e: any) {
      toast.error(`批量总结失败：${e?.message || e}`);
    } finally {
      setBatchActing(false);
    }
  };

  const batchQueryDocs = async () => {
    if (selectedDocIds.length === 0) return;
    const ask = window.prompt('输入要批量提问的问题', question || docQuestion || '这份文档的核心内容是什么？');
    if (!ask || !ask.trim()) return;
    setBatchActing(true);
    try {
      const pickedDocs = documents.filter((d) => selectedDocIds.includes(String(d.doc_id)));
      const sections: string[] = [];
      for (const doc of pickedDocs) {
        const res = await kbApi.documentQuery(String(doc.doc_id), ask.trim(), 5);
        const out = (res?.output || res || {}) as any;
        const answer = String(out?.answer || '').trim();
        const items = Array.isArray(out?.items) ? out.items : [];
        const lines = [
          `## ${String(doc.doc_id)}`,
          ``,
          `- question: ${ask.trim()}`,
          `- collection_id: ${String(doc.collection_id || '')}`,
          `- kind: ${String(doc.kind || '')}`,
          `- mode: ${String(out?.mode || '')}`,
          `- source_uri: ${String(doc.source_uri || '')}`,
          ``,
          `### answer`,
          answer || '(empty)',
          ``,
          `### items`,
          ...(items.length > 0
            ? items.map((it: any, idx: number) => `${idx + 1}. p${String(it?.page_idx ?? '-')} ${String(it?.snippet || '')}`)
            : ['(none)']),
        ];
        sections.push(lines.join('\n'));
      }
      const report = ['# 批量文档问答', '', ...sections].join('\n\n---\n\n');
      _downloadText(`kb_batch_query_${selectedCollection || 'default'}_${_tsSlug()}.md`, report, 'text/markdown;charset=utf-8');
      await _copyText(report);
      await kbApi.createAnalysisBatch({
        collection_id: selectedCollection || 'default',
        batch_type: 'query',
        title: `批量问答 ${new Date().toLocaleString()}`,
        input: { doc_ids: pickedDocs.map((d) => d.doc_id), question: ask.trim() },
        output: { report, count: pickedDocs.length },
      });
      toast.success(`已批量问答 ${selectedDocIds.length} 个文档，并下载/复制结果`);
    } catch (e: any) {
      toast.error(`批量问答失败：${e?.message || e}`);
    } finally {
      setBatchActing(false);
    }
  };

  const startMaterialsConversation = async () => {
    if (selectedDocIds.length === 0) return;
    setBatchActing(true);
    try {
      const res = await kbApi.createConversation({
        title: `资料对话 ${new Date().toLocaleString()}`,
        scope: {
          collection_id: selectedCollection || 'default',
          doc_ids: selectedDocIds,
        },
        profile: {
          citation_required: true,
          answer_style: 'concise',
          language: 'zh-CN',
        },
      });
      const sid = String((res as any)?.session_id || '');
      if (!sid) throw new Error('conversation_create_failed');
      toast.success(`已创建资料对话，会话：${sid}`);
      navigate(`/app/kb/chat/${encodeURIComponent(sid)}`);
    } catch (e: any) {
      toast.error(`开始对话失败：${e?.message || e}`);
    } finally {
      setBatchActing(false);
    }
  };

  const onReingestDoc = async (docId: string) => {
    try {
      const res = await kbApi.reingestDocument(docId);
      const jobId = res?.job?.job_id || res?.job_id || res?.core?.output?.output?.job_id || '';
      if (jobId) {
        setActiveJobId(String(jobId));
        toast.success(`已触发重试入库：${jobId}`);
      } else {
        toast.success('已触发重试入库');
      }
      await refreshDocuments();
    } catch (e: any) {
      toast.error(`重试入库失败：${e?.message || e}`);
    }
  };

  const loadDocumentDetail = async (docId: string) => {
    setDocDetailLoading(true);
    try {
      setDocDetailOrigin(tab === 'query' ? 'query' : tab === 'documents' ? 'documents' : 'other');
      const [doc, src, els, ars] = await Promise.all([
        kbApi.getDocument(docId),
        kbApi.listDocumentSources(docId, 100, 0),
        kbApi.listDocumentElements(docId, undefined, 50, 0),
        kbApi.listDocumentAnalysisRuns(docId, undefined, 20, 0),
      ]);
      setSelectedDoc(doc as KBDocument);
      setSelectedDocSources(src.items || []);
      setSelectedDocElements(els.items || []);
      setSelectedDocAnalysisRuns(ars.items || []);
      setDocQueryResp(null);
      setDocSummarizeResp(null);
      setFocusedPageIdx(null);
      setQueryDocId(docId);
      setDocDetailOpen(true);
    } catch (e: any) {
      toast.error(`加载文档详情失败：${e?.message || e}`);
    } finally {
      setDocDetailLoading(false);
    }
  };

  const onRefreshDoc = async (docId: string, force: boolean = false) => {
    try {
      const res = await kbApi.refreshDocument(docId, force);
      const jobId = res?.job?.job_id || res?.job_id || res?.core?.output?.output?.job_id || res?.core?.output?.job_id || '';
      if (jobId) {
        setActiveJobId(String(jobId));
        toast.success(force ? `已强制刷新：${jobId}` : `已触发刷新：${jobId}`);
      } else {
        toast.success(force ? '已强制刷新' : '已触发刷新');
      }
      await refreshDocuments();
      if (selectedDoc?.doc_id === docId) {
        await loadDocumentDetail(docId);
      }
    } catch (e: any) {
      toast.error(`刷新失败：${e?.message || e}`);
    }
  };

  const onDocQuery = async () => {
    if (!selectedDoc?.doc_id) return;
    setDocQueryLoading(true);
    try {
      if (docQueryScope === 'document') {
        setQueryScope('document');
        setQueryDocId(selectedDoc.doc_id);
      } else {
        setQueryScope('collection');
      }
      const res =
        docQueryScope === 'collection'
          ? await kbApi.collectionQuery(selectedDoc.collection_id || selectedCollection || 'default', docQuestion, 8)
          : await kbApi.documentQuery(selectedDoc.doc_id, docQuestion, 5);
      setDocQueryResp(res?.output || res);
      const ars = await kbApi.listDocumentAnalysisRuns(selectedDoc.doc_id, undefined, 20, 0);
      setSelectedDocAnalysisRuns(ars.items || []);
      toast.success(docQueryScope === 'collection' ? '集合问答完成' : '文档问答完成');
    } catch (e: any) {
      toast.error(`${docQueryScope === 'collection' ? '集合问答' : '文档问答'}失败：${e?.message || e}`);
    } finally {
      setDocQueryLoading(false);
    }
  };

  const onDocSummarize = async () => {
    if (!selectedDoc?.doc_id) return;
    setDocSummarizeLoading(true);
    try {
      const res = await kbApi.documentSummarize(selectedDoc.doc_id, 'key_points', 5);
      setDocSummarizeResp(res?.output || res);
      const ars = await kbApi.listDocumentAnalysisRuns(selectedDoc.doc_id, undefined, 20, 0);
      setSelectedDocAnalysisRuns(ars.items || []);
      toast.success('文档总结完成');
    } catch (e: any) {
      toast.error(`文档总结失败：${e?.message || e}`);
    } finally {
      setDocSummarizeLoading(false);
    }
  };

  const onExportDoc = async (format: 'json' | 'markdown') => {
    if (!selectedDoc?.doc_id) return;
    try {
      const res = await kbApi.exportDocument(selectedDoc.doc_id, format, false);
      if (format === 'json') {
        await _copyText(JSON.stringify(res, null, 2));
      } else {
        await _copyText(String(res?.content || ''));
      }
      toast.success(`已复制 ${format} 导出内容`);
    } catch (e: any) {
      toast.error(`导出失败：${e?.message || e}`);
    }
  };

  const replayAnalysisRun = (run: KBAnalysisRun) => {
    const input = run.input || {};
    const output = (run.output || {}) as any;
    if (run.run_type === 'query') {
      setDocQuestion(String(input?.question || ''));
      setDocQueryScope(input?.doc_id ? 'document' : 'collection');
      setDocQueryResp(output);
      toast.success('已回放历史问答结果');
      return;
    }
    if (run.run_type === 'summarize') {
      setDocSummarizeResp(output);
      toast.success('已回放历史总结结果');
      return;
    }
  };

  const deleteAnalysisRun = async (run: KBAnalysisRun) => {
    if (!selectedDoc?.doc_id || !run?.run_id) return;
    if (!confirm(`确认删除这条${run.run_type === 'summarize' ? '总结' : '问答'}历史记录？`)) return;
    try {
      await kbApi.deleteDocumentAnalysisRun(selectedDoc.doc_id, run.run_id);
      const ars = await kbApi.listDocumentAnalysisRuns(selectedDoc.doc_id, undefined, 20, 0);
      setSelectedDocAnalysisRuns(ars.items || []);
      if ((docQueryResp as any)?.analysis_run_id === run.run_id) setDocQueryResp(null);
      if ((docSummarizeResp as any)?.analysis_run_id === run.run_id) setDocSummarizeResp(null);
      toast.success('历史分析记录已删除');
    } catch (e: any) {
      toast.error(`删除历史分析失败：${e?.message || e}`);
    }
  };

  const openCitationInDetail = async (citation: any) => {
    const docId = String(citation?.doc_id || '');
    const pageIdxRaw = citation?.page_idx;
    if (!docId) return;
    try {
      await loadDocumentDetail(docId);
      const pageIdx = pageIdxRaw === undefined || pageIdxRaw === null ? null : Number(pageIdxRaw);
      setFocusedPageIdx(Number.isFinite(pageIdx as number) ? (pageIdx as number) : null);
      setTab('documents');
      toast.success('已打开引用对应文档');
    } catch {
      // loadDocumentDetail already reports error
    }
  };

  const onQuery = async () => {
    if (queryScope === 'document' && !queryDocId) {
      toast.error('请先选择要提问的文档');
      return;
    }
    setQueryLoading(true);
    setRewrittenAnswer('');
    setRewrittenAnswerMode('llm');
    setQueryExpandedView(false);
    setQueryShowAllEvidence(false);
    try {
      const res =
        queryScope === 'document'
          ? await kbApi.documentQuery(queryDocId, question, 5)
          : await kbApi.collectionQuery(selectedCollection, question, 8);
      setQueryResp(res?.output || res);
      toast.success(queryScope === 'document' ? '单文档查询完成' : '集合查询完成');
    } catch (e: any) {
      toast.error(`查询失败：${e?.message || e}`);
    } finally {
      setQueryLoading(false);
    }
  };

  const onRewriteAnswer = async () => {
    if (!qout?.answer) return;
    setQueryRewriteLoading(true);
    try {
      const res = await kbApi.rewriteCollectionAnswer(
        selectedCollection,
        question,
        String(qout.answer || ''),
        Array.isArray(items) ? items.slice(0, 8) : []
      );
      const text = String(res?.rewritten_answer || '').trim();
      if (!text) throw new Error('重写结果为空');
      setRewrittenAnswerMode('llm');
      setRewrittenAnswer(text);
      toast.success('答案重写完成');
    } catch (e: any) {
      const msg = String(e?.message || e || '');
      if (msg.includes('llm_not_enabled')) {
        const fallback = localRewrittenAnswer || String(qout?.answer || '').trim();
        if (!fallback) {
          toast.error('当前环境未启用 LLM，且暂无可用于本地重写的内容');
        } else {
          setRewrittenAnswerMode('local');
          setRewrittenAnswer(fallback);
          toast.success('当前环境未启用 LLM，已自动切换为本地重写');
        }
      } else {
        toast.error(`答案重写失败：${msg}`);
      }
    } finally {
      setQueryRewriteLoading(false);
    }
  };

  const qout = queryResp || {};
  const items: any[] = Array.isArray(qout.items) ? qout.items : [];
  const isVideoQuery = items.some((it: any) => _isVideoItem(it));
  const shownItems = queryHighScoreOnly ? items.filter((it: any) => Number(it?.score || 0) >= 0.08) : items;
  const filteredOutCount = Math.max(0, items.length - shownItems.length);
  const groupedItems = useMemo(() => {
    const groups = new Map<string, any>();
    shownItems.forEach((it: any, idx: number) => {
      const docId = String(it?.doc_id || '-');
      const pageIdx = String(it?.page_idx ?? '-');
      const key = `${docId}__${pageIdx}`;
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          doc_id: docId,
          page_idx: pageIdx,
          maxScore: Number(it?.score || 0),
          items: [],
        });
      }
      const g = groups.get(key);
      g.items.push({ ...it, _idx: idx });
      g.maxScore = Math.max(g.maxScore, Number(it?.score || 0));
    });
    return Array.from(groups.values())
      .map((g: any) => {
        const firstText = _cleanSnippet(g.items?.[0]?.snippet || '');
        const title = _snippetTitle(firstText);
        const bonus =
          /核心业务|战略|目标|合作|市场|风险|预算|营收|利润|路线图|业务概要|阶段性营收规划/.test(firstText + title) ? 0.08 : 0;
        const penalty = /封面|目录/.test(firstText + title) ? 0.08 : 0;
        const focusScore = _questionFocusScore(`${title}\n${firstText}`, question);
        return { ...g, rankScore: Number(g.maxScore || 0) + bonus - penalty, focusScore };
      })
      .sort((a, b) => Number(b.rankScore || 0) - Number(a.rankScore || 0));
  }, [shownItems, question]);
  const focusedGroups = useMemo(() => {
    const ranked = [...groupedItems].sort((a: any, b: any) => {
      const fd = Number(b.focusScore || 0) - Number(a.focusScore || 0);
      if (fd !== 0) return fd;
      return Number(b.rankScore || 0) - Number(a.rankScore || 0);
    });
    const positive = ranked.filter((g: any) => Number(g.focusScore || 0) > 0);
    return (positive.length > 0 ? positive : ranked).slice(0, 2);
  }, [groupedItems]);
  const preciseQuestionMode = useMemo(() => {
    if (queryViewMode === 'precise') return true;
    if (queryViewMode === 'analysis') return false;
    return _isPreciseQuestion(question);
  }, [question, queryViewMode]);
  const primaryEvidenceGroups = preciseQuestionMode ? focusedGroups.slice(0, 1) : focusedGroups;
  const evidenceGroups = queryShowAllEvidence ? groupedItems : primaryEvidenceGroups;
  const summaryGroups = focusedGroups.length > 0 ? focusedGroups : groupedItems;
  const structuredAnswer = useMemo(() => {
    const lines = _dedupe(
      summaryGroups.flatMap((g: any) => (g.items || []).flatMap((it: any) => _meaningfulLines(it?.snippet || '')))
    );
    const highValue = lines.filter((x) => /核心业务|目标|合作|市场|优势|需求|风险|预算|营收|利润|子公司|解决方案|呼叫中心|智慧消防|离岸外包/.test(x));
    const numeric = lines
      .filter((x) => /\d/.test(x))
      .filter((x) => /营业额|净利润|投资|预算|合同额|2026|2027|2028|POC|目标|万元|亿元/.test(x))
      .slice(0, 4);
    const core = (highValue.length > 0 ? highValue : lines.filter((x) => !/\d/.test(x))).slice(0, 4);
    const pages = summaryGroups
      .slice(0, 4)
      .map((g: any) => (_isVideoItem(g.items?.[0]) ? _itemTimeLabel(g.items?.[0]) : `P${String(Number(g.page_idx) + 1)}`))
      .filter(Boolean);
    return {
      core: core.length > 0 ? core : lines.slice(0, 4),
      numeric,
      pages,
    };
  }, [summaryGroups]);
  const structuredAnswerMarkdown = useMemo(() => {
    const lines: string[] = [];
    lines.push(`# 知识库问答摘要`);
    lines.push('');
    lines.push(`- collection: ${selectedCollection}`);
    lines.push(`- question: ${question}`);
    lines.push(`- mode: ${String(qout?.mode || '')}`);
    lines.push('');
    lines.push(`## 系统回答`);
    lines.push(String(qout?.answer || '').trim() || '(empty)');
    lines.push('');
    lines.push(`## 结构化总结`);
    if (structuredAnswer.core.length === 0) {
      lines.push('- (none)');
    } else {
      structuredAnswer.core.forEach((x, idx) => lines.push(`${idx + 1}. ${x}`));
    }
    lines.push('');
    lines.push(`## 关键数字`);
    if (structuredAnswer.numeric.length === 0) {
      lines.push('- (none)');
    } else {
      structuredAnswer.numeric.forEach((x) => lines.push(`- ${x}`));
    }
    lines.push('');
    lines.push(`## 主要依据${isVideoQuery ? '时间片段' : '页'}`);
    if (structuredAnswer.pages.length === 0) {
      lines.push('- (none)');
    } else {
      structuredAnswer.pages.forEach((x) => lines.push(`- ${x}`));
    }
    return lines.join('\n');
  }, [selectedCollection, question, qout?.mode, qout?.answer, structuredAnswer, isVideoQuery]);
  const localRewrittenAnswer = useMemo(() => {
    const parts: string[] = [];
    const core = structuredAnswer.core.map((x) => _prettyLine(x)).filter(Boolean);
    const numeric = structuredAnswer.numeric.map((x) => _prettyLine(x)).filter(Boolean);
    const pages = structuredAnswer.pages.filter(Boolean);

    if (core.length > 0) {
      parts.push(`结合当前检索结果，这份资料的关键信息主要集中在以下几个方面：${core.join('；')}。`);
    } else if (qout?.answer) {
      parts.push(String(qout.answer).trim());
    }

    if (numeric.length > 0) {
      parts.push(`其中较关键的数字信息包括：${numeric.join('；')}。`);
    }

    if (pages.length > 0) {
      parts.push(`相关依据主要分布在 ${pages.join('、')}。`);
    }

    if (parts.length === 0 && qout?.answer) {
      parts.push(String(qout.answer).trim());
    }

    return parts.join('\n\n').trim();
  }, [structuredAnswer, qout?.answer]);
  const citations: any[] = Array.isArray(qout.citations) ? qout.citations : [];
  const evidenceGroupKeys = useMemo(() => new Set(evidenceGroups.map((g: any) => `${String(g.doc_id)}__${String(g.page_idx)}`)), [evidenceGroups]);
  const displayedCitations = useMemo(() => {
    const filtered = citations.filter((c: any) => evidenceGroupKeys.has(_citationKey(c?.doc_id, c?.page_idx)));
    return filtered.length > 0 ? filtered : citations;
  }, [citations, evidenceGroupKeys]);
  const citationGroups = useMemo(() => {
    const m = new Map<string, any>();
    displayedCitations.forEach((c: any) => {
      const docId = String(c?.doc_id || '-');
      if (!m.has(docId)) {
        m.set(docId, { doc_id: docId, pages: [] as any[] });
      }
      m.get(docId).pages.push(c);
    });
    return Array.from(m.values()).map((g: any) => ({
      ...g,
      pages: (g.pages || []).sort((a: any, b: any) => Number(a?.page_idx ?? 0) - Number(b?.page_idx ?? 0)),
      hasPreview: (g.pages || []).some((c: any) => !!citationImageUrls[_citationKey(c?.doc_id, c?.page_idx)]),
    }));
  }, [displayedCitations, citationImageUrls]);
  const allCitationsWithoutPreview = displayedCitations.length > 0 && displayedCitations.every((c: any) => c?.asset_available === false);
  const detailCitations: any[] = [
    ...(Array.isArray(docQueryResp?.citations) ? docQueryResp.citations : []),
    ...(Array.isArray(docSummarizeResp?.citations) ? docSummarizeResp.citations : []),
  ];
  const focusedDocPreviewUrl =
    selectedDoc?.doc_id && focusedPageIdx !== null
      ? citationImageUrls[_citationKey(selectedDoc.doc_id, focusedPageIdx)]
      : '';
  const focusedElements =
    focusedPageIdx === null
      ? selectedDocElements
      : selectedDocElements.filter((e: any) => Number(e?.page_idx ?? -1) === Number(focusedPageIdx));
  const filteredAnalysisRuns =
    selectedDocAnalysisRuns.filter((r) => {
      if (analysisRunFilter !== 'all' && String(r.run_type || '') !== analysisRunFilter) return false;
      const kw = analysisRunKeyword.trim().toLowerCase();
      if (!kw) return true;
      const hay = [
        String(r.run_type || ''),
        String(r.mode || ''),
        String(r.input?.question || ''),
        String(r.input?.profile || ''),
        String((r.output as any)?.answer || ''),
        String((r.output as any)?.summary || ''),
      ]
        .join('\n')
        .toLowerCase();
      return hay.includes(kw);
    });

  useEffect(() => {
    const all = [...citations.slice(0, 6), ...detailCitations.slice(0, 6)];
    const unique = new Map<string, any>();
    all.forEach((c: any) => {
      const docId = String(c?.doc_id || '');
      const pageIdx = c?.page_idx;
      if (!docId || pageIdx === undefined || pageIdx === null) return;
      const key = _citationKey(docId, pageIdx);
      if (!unique.has(key)) unique.set(key, c);
    });
    if (unique.size === 0) return;
    let stopped = false;
    const createdUrls: string[] = [];
    (async () => {
      for (const [key, c] of unique.entries()) {
        if (stopped || citationImageUrls[key] || citationImageFailures[key]) continue;
        try {
          const assetUrl = _citationAssetUrl(c);
          if (!assetUrl) {
            if (!stopped) {
              setCitationImageFailures((prev) => ({ ...prev, [key]: true }));
            }
            continue;
          }
          const resp = await fetch(assetUrl, {
            headers: {
              'X-AIPLAT-API-KEY': apiKey,
              'X-AIPLAT-TENANT-ID': tenantId || 'default',
            },
          });
          if (!resp.ok) {
            if (!stopped) {
              setCitationImageFailures((prev) => ({ ...prev, [key]: true }));
            }
            continue;
          }
          const blob = await resp.blob();
          const obj = URL.createObjectURL(blob);
          createdUrls.push(obj);
          if (!stopped) {
            setCitationImageUrls((prev) => ({ ...prev, [key]: obj }));
          }
        } catch {
          if (!stopped) {
            setCitationImageFailures((prev) => ({ ...prev, [key]: true }));
          }
        }
      }
    })();
    return () => {
      stopped = true;
      createdUrls.forEach((u) => URL.revokeObjectURL(u));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiKey, tenantId, JSON.stringify(citations.slice(0, 6)), JSON.stringify(detailCitations.slice(0, 6)), JSON.stringify(citationImageFailures)]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-100">知识库（多模态）</h1>
          <div className="text-xs text-gray-400 mt-1">
            tenant: <span className="text-gray-300">{tenantId || 'default'}</span> · active_collection:{' '}
            <span className="text-gray-300">{selectedCollection}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="bg-dark-card border border-dark-border text-gray-200 rounded-lg px-3 h-9 text-sm"
            value={selectedCollection}
            onChange={(e) => setSelectedCollection(e.target.value)}
          >
            {collectionOptions.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
          <Button variant="secondary" onClick={() => setTab('settings')}>
            认证配置
          </Button>
        </div>
      </div>

      <div className="flex gap-2 border-b border-dark-border pb-2">
        {([
          ['collections', '集合'],
          ['documents', '文档'],
          ['query', '问答'],
          ['settings', '设置'],
        ] as Array<[TabKey, string]>).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
              tab === k ? 'bg-dark-hover text-primary' : 'text-gray-400 hover:text-gray-200 hover:bg-dark-hover'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'collections' && (
        <Card>
          <CardHeader>
            <div>
              <div className="font-semibold text-gray-100">集合管理</div>
              <div className="text-xs text-gray-400 mt-0.5">创建/查看集合（MVP：集合也可由入库隐式创建）</div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 mb-3">
              <Button variant="primary" onClick={() => setCreateOpen(true)}>
                新建集合
              </Button>
              <Button variant="secondary" loading={loadingCollections} onClick={refreshCollections}>
                刷新
              </Button>
            </div>
            <Table
              columns={[
                { key: 'collection_id', title: 'collection_id', dataIndex: 'collection_id' },
                { key: 'name', title: 'name', dataIndex: 'name' },
                { key: 'doc_count', title: 'docs', dataIndex: 'doc_count' },
              ]}
              data={collections.map((c) => ({ ...c, doc_count: c.doc_count ?? 0 }))}
              rowKey="collection_id"
            />
          </CardContent>

          <Modal
            open={createOpen}
            onClose={() => setCreateOpen(false)}
            title="新建集合"
            footer={
              <>
                <Button variant="secondary" onClick={() => setCreateOpen(false)}>
                  取消
                </Button>
                <Button variant="primary" onClick={onCreateCollection}>
                  创建
                </Button>
              </>
            }
          >
            <div className="space-y-3">
              <Input label="collection_id" value={newCollectionId} onChange={(e) => setNewCollectionId(e.target.value)} placeholder="例如 jp_strategy_2026" />
              <Input label="name（可选）" value={newCollectionName} onChange={(e) => setNewCollectionName(e.target.value)} placeholder="展示名" />
            </div>
          </Modal>
        </Card>
      )}

      {tab === 'documents' && (
        <Card>
          <CardHeader>
            <div>
              <div className="font-semibold text-gray-100">文档管理</div>
              <div className="text-xs text-gray-400 mt-0.5">支持本地文档/视频上传，也支持通过 URL 导入网络文档或视频；查看文档状态；删除文档</div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 mb-3 flex-wrap">
              <div className="flex items-center gap-2 mr-2">
                <Button variant={uploadKind === 'pdf' ? 'primary' : 'secondary'} size="sm" onClick={() => setUploadKind('pdf')}>
                  本地文档
                </Button>
                <Button variant={uploadKind === 'video' ? 'primary' : 'secondary'} size="sm" onClick={() => setUploadKind('video')}>
                  本地视频
                </Button>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept={uploadKind === 'video' ? '.mp4,.mov,.mkv,.avi,.webm,.m4v,video/*' : '.pdf'}
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) {
                    onUpload(f);
                  }
                  // reset so selecting same file again still triggers change
                  e.currentTarget.value = '';
                }}
              />
              <Button
                variant="primary"
                loading={uploading}
                onClick={() => {
                  if (!selectedCollection) {
                    toast.error('请先选择 collection');
                    return;
                  }
                  fileInputRef.current?.click();
                }}
              >
                {uploadKind === 'video' ? '上传视频并入库' : '上传文档并入库'}
              </Button>
              <Button variant="secondary" loading={loadingDocs} onClick={refreshDocuments}>
                刷新
              </Button>
            </div>

            <div className="mb-3 rounded-xl border border-dark-border bg-dark-card p-3">
              <div className="flex items-center justify-between gap-3 flex-wrap mb-2">
                <div className="text-sm font-medium text-gray-200">URL 导入</div>
                <div className="flex items-center gap-2">
                  <Button variant={urlKind === 'pdf' ? 'primary' : 'secondary'} size="sm" onClick={() => setUrlKind('pdf')}>
                    网络文档
                  </Button>
                  <Button variant={urlKind === 'video' ? 'primary' : 'secondary'} size="sm" onClick={() => setUrlKind('video')}>
                    网络视频
                  </Button>
                </div>
              </div>
              <div className="text-xs text-gray-400 mb-3">
                {urlKind === 'video'
                  ? '优先支持可直接下载的视频直链；若是视频平台页面，需要服务端具备 yt-dlp 才能成功解析。'
                  : '适合导入网络上的 PDF / 文档链接。当前会导入到选中的 collection。'}
              </div>
              <div className="flex gap-2 flex-wrap items-end">
                <div className="min-w-[320px] flex-1">
                  <Input
                    label={urlKind === 'video' ? '视频 URL' : '文档 URL'}
                    value={urlInput}
                    onChange={(e) => setUrlInput(e.target.value)}
                    placeholder={urlKind === 'video' ? 'https://example.com/video.mp4' : 'https://example.com/file.pdf'}
                  />
                </div>
                <Button variant="primary" loading={urlIngesting} onClick={onUrlIngest}>
                  {urlKind === 'video' ? '导入视频' : '导入文档'}
                </Button>
              </div>
            </div>

            <div className="mb-3 rounded-xl border border-dark-border bg-dark-card p-3 space-y-3">
              <div className="text-xs text-gray-400">
                使用建议：先勾选文档，再优先使用 `批量问答`、`批量总结`。导出、刷新、复制 ID 等低频功能放在 `更多操作` 里。
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <label className="flex items-center gap-2 text-sm text-gray-300">
                  <input
                    type="checkbox"
                    checked={documents.length > 0 && selectedDocIds.length === documents.length}
                    onChange={(e) => toggleSelectAllVisibleDocs(e.target.checked)}
                  />
                  <span>全选当前列表</span>
                </label>
                <span className="text-xs text-gray-400">已选 {selectedDocIds.length} 项</span>
                <Button variant="primary" size="sm" disabled={selectedDocIds.length === 0 || batchActing} onClick={startMaterialsConversation}>
                  开始对话
                </Button>
                <Button variant="primary" size="sm" disabled={selectedDocIds.length === 0 || batchActing} onClick={batchQueryDocs}>
                  批量问答
                </Button>
                <Button variant="secondary" size="sm" disabled={selectedDocIds.length === 0 || batchActing} onClick={batchSummarizeDocs}>
                  批量总结
                </Button>
                <Button variant="danger" size="sm" disabled={selectedDocIds.length === 0 || batchActing} onClick={batchDeleteDocs}>
                  批量删除
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setBatchMoreOpen((v) => !v)}>
                  {batchMoreOpen ? '收起更多操作' : '更多操作'}
                </Button>
              </div>
              {batchMoreOpen && (
                <div className="flex items-center gap-2 flex-wrap rounded-lg border border-dark-border bg-dark-bg px-3 py-3">
                  <Button variant="secondary" size="sm" disabled={selectedDocIds.length === 0 || batchActing} onClick={batchCopyDocIds}>
                    复制 doc_id
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={async () => {
                      await loadBatchRecords();
                      setBatchRecordsOpen(true);
                    }}
                  >
                    批次记录
                  </Button>
                  <Button variant="secondary" size="sm" disabled={selectedDocIds.length === 0 || batchActing} onClick={() => batchExportDocs('json')}>
                    导出 JSON
                  </Button>
                  <Button variant="secondary" size="sm" disabled={selectedDocIds.length === 0 || batchActing} onClick={() => batchExportDocs('markdown')}>
                    导出 Markdown
                  </Button>
                  <Button variant="secondary" size="sm" disabled={selectedDocIds.length === 0 || batchActing} onClick={() => batchRefreshDocs(false)}>
                    刷新
                  </Button>
                  <Button variant="secondary" size="sm" disabled={selectedDocIds.length === 0 || batchActing} onClick={() => batchRefreshDocs(true)}>
                    强制刷新
                  </Button>
                </div>
              )}
            </div>

            <Modal
              open={batchRecordsOpen}
              onClose={() => setBatchRecordsOpen(false)}
              title="批次记录"
              footer={
                <>
                  <Button variant="secondary" onClick={() => setBatchRecordsOpen(false)}>
                    关闭
                  </Button>
                  <Button variant="secondary" loading={batchRecordsLoading} onClick={() => loadBatchRecords()}>
                    刷新
                  </Button>
                </>
              }
            >
              <div className="space-y-2 max-h-[60vh] overflow-auto">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex gap-2">
                    <Button variant={batchRecordFilter === 'all' ? 'primary' : 'secondary'} size="sm" onClick={() => setBatchRecordFilter('all')}>
                      全部
                    </Button>
                    <Button variant={batchRecordFilter === 'query' ? 'primary' : 'secondary'} size="sm" onClick={() => setBatchRecordFilter('query')}>
                      问答
                    </Button>
                    <Button variant={batchRecordFilter === 'summarize' ? 'primary' : 'secondary'} size="sm" onClick={() => setBatchRecordFilter('summarize')}>
                      总结
                    </Button>
                  </div>
                </div>
                <Input
                  label="搜索批次记录"
                  value={batchRecordKeyword}
                  onChange={(e) => setBatchRecordKeyword(e.target.value)}
                  placeholder="按标题、问题、输出内容搜索"
                />
                {batchRecords.length === 0 ? (
                  <div className="text-sm text-gray-400">{batchRecordsLoading ? '加载中...' : '暂无批次记录'}</div>
                ) : (
                  batchRecords.map((b) => (
                    <div key={b.batch_id} className="border border-dark-border rounded-lg p-3 text-xs text-gray-300">
                      <div className="flex items-center justify-between gap-2">
                        <button type="button" onClick={() => replayBatchRecord(b)} className="text-left hover:text-white transition-colors">
                          {String(b.batch_type)} · {String(b.title || '')}
                        </button>
                        <div className="text-gray-500">{String(b.created_at || '')}</div>
                      </div>
                      <button
                        type="button"
                        onClick={() => replayBatchRecord(b)}
                        className="mt-2 whitespace-pre-wrap break-words text-gray-400 text-left w-full hover:text-gray-200 transition-colors"
                      >
                        {String((b.output as any)?.report || '').slice(0, 1200) || '(empty)'}
                      </button>
                      <div className="mt-2 flex gap-2 justify-end">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() =>
                            _downloadText(
                              `kb_batch_${String(b.batch_type || 'result')}_${String(b.batch_id || _tsSlug())}.md`,
                              String((b.output as any)?.report || ''),
                              'text/markdown;charset=utf-8'
                            )
                          }
                        >
                          下载
                        </Button>
                        <Button variant="secondary" size="sm" onClick={() => _copyText(String((b.output as any)?.report || ''))}>
                          复制
                        </Button>
                        <Button variant="danger" size="sm" onClick={() => deleteBatchRecord(b.batch_id)}>
                          删除
                        </Button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </Modal>

            {activeJobId && (
              <div className="mb-3 p-3 rounded-xl border border-dark-border bg-dark-card">
                <div className="text-sm text-gray-200">
                  当前任务：<span className="text-gray-100">{activeJobId}</span>{' '}
                  <span className="text-xs text-gray-400">{jobPolling ? '（轮询中）' : ''}</span>
                </div>
                <div className="text-xs text-gray-400 mt-1">
                  status: <span className="text-gray-300">{String(activeJob?.status || '-')}</span> · progress:{' '}
                  <span className="text-gray-300">{activeJob?.progress ?? '-'}</span> · message:{' '}
                  <span className="text-gray-300">{String(activeJob?.message || '')}</span>
                </div>
                {typeof activeJob?.progress === 'number' && (
                  <div className="mt-2">
                    <Progress value={Math.max(0, Math.min(1, Number(activeJob.progress))) * 100} />
                  </div>
                )}
                <div className="mt-2 flex gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={jobEventsLoading}
                    onClick={async () => {
                      await loadJobEvents();
                      setJobEventsOpen(true);
                    }}
                  >
                    查看任务日志
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setActiveJobId('');
                      setActiveJob(null);
                      setJobPolling(false);
                      toast.success('已清除当前任务显示');
                    }}
                  >
                    清除
                  </Button>
                </div>
              </div>
            )}

            <Modal
              open={jobEventsOpen}
              onClose={() => setJobEventsOpen(false)}
              title={`任务日志：${activeJobId || ''}`}
              footer={
                <>
                  <Button variant="secondary" onClick={() => setJobEventsOpen(false)}>
                    关闭
                  </Button>
                  <Button variant="secondary" loading={jobEventsLoading} onClick={() => loadJobEvents()}>
                    刷新日志
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      const last = jobEvents.slice(-20);
                      _copyText(
                        [
                          `job_id=${activeJobId}`,
                          `status=${String(activeJob?.status || '')}`,
                          `progress=${String(activeJob?.progress ?? '')}`,
                          `message=${String(activeJob?.message || '')}`,
                          `events(last20)=${JSON.stringify(last, null, 2)}`,
                        ].join('\n')
                      );
                    }}
                  >
                    复制诊断（含日志）
                  </Button>
                </>
              }
            >
              <div className="text-xs text-gray-300 space-y-2 max-h-[60vh] overflow-auto">
                {jobEvents.length === 0 ? (
                  <div className="text-gray-400">暂无日志</div>
                ) : (
                  jobEvents.slice(-200).map((ev, idx) => (
                    <div key={idx} className="border border-dark-border rounded-lg p-2 bg-dark-card">
                      <div className="flex items-center justify-between">
                        <div className="text-gray-200">
                          [{String(ev.level || 'info')}] {String(ev.message || '')}
                        </div>
                        <div className="text-gray-500">{ev.ts}</div>
                      </div>
                      {ev.extra && <pre className="text-gray-400 whitespace-pre-wrap mt-1">{JSON.stringify(ev.extra, null, 2)}</pre>}
                    </div>
                  ))
                )}
              </div>
            </Modal>

            <Table
              columns={[
                {
                  key: 'select',
                  title: 'select',
                  width: 56,
                  render: (_: any, row: any) => (
                    <input
                      type="checkbox"
                      checked={selectedDocIds.includes(String(row.doc_id))}
                      onChange={(e) => toggleDocSelection(String(row.doc_id), e.target.checked)}
                      onClick={(e) => e.stopPropagation()}
                    />
                  ),
                },
                {
                  key: 'document',
                  title: '文档',
                  width: '32%',
                  render: (_: any, row: any) => (
                    <div className="min-w-0">
                      <div
                        className="truncate text-sm text-gray-100"
                        title={String(row?.meta?.title || '').trim() || String(row?.source_uri || '').split('/').filter(Boolean).pop() || String(row?.doc_id || '')}
                      >
                        {String(row?.meta?.title || '').trim() || String(row?.source_uri || '').split('/').filter(Boolean).pop() || String(row?.doc_id || '')}
                      </div>
                      <div className="truncate text-xs text-gray-500 mt-0.5" title={String(row?.doc_id || '')}>
                        {String(row?.doc_id || '')}
                      </div>
                      <div className="truncate text-xs text-gray-400 mt-1" title={String(row?.source_uri || '')}>
                        {String(row?.source_uri || '')}
                      </div>
                    </div>
                  ),
                },
                {
                  key: 'status',
                  title: '状态',
                  width: '24%',
                  render: (_: any, row: any) => (
                    <div className="min-w-0">
                      <div className="text-sm text-gray-200">
                        {String(row?.status || '-')} · {String(row?.kind || '').toUpperCase()}
                      </div>
                      {!!row?.meta?.last_job_id && (
                        <div className="truncate text-xs text-gray-500 mt-1" title={String(row?.meta?.last_job_id || '')}>
                          job: {String(row?.meta?.last_job_id || '')}
                        </div>
                      )}
                      {!!row?.meta?.error && (
                        <div className="truncate text-xs text-red-300 mt-1" title={String(row?.meta?.error || '')}>
                          {String(row?.meta?.error || '')}
                        </div>
                      )}
                    </div>
                  ),
                },
                {
                  key: 'stats',
                  title: '内容',
                  width: '20%',
                  render: (_: any, row: any) => (
                    <div className="text-xs text-gray-300 space-y-1">
                      <div>elements: {Number(row?.element_count || 0)}</div>
                      <div>emb: {Number(row?.embedding_count || 0)}</div>
                      <div>sources: {Number(row?.source_count || 0)}</div>
                    </div>
                  ),
                },
                {
                  key: 'actions',
                  title: '操作',
                  width: '24%',
                  render: (_: any, row: any) => (
                    <div className="flex items-center gap-2 flex-wrap">
                      <Button variant="secondary" size="sm" loading={docDetailLoading && selectedDoc?.doc_id === row.doc_id} onClick={() => loadDocumentDetail(row.doc_id)}>
                        详情
                      </Button>
                      {row?.meta?.last_job_id && (
                        <Button
                          variant="secondary"
                          size="sm"
                          loading={jobEventsLoading}
                          onClick={async () => {
                            setActiveJobId(String(row.meta.last_job_id));
                            await loadJobEvents();
                            setJobEventsOpen(true);
                          }}
                        >
                          查看日志
                        </Button>
                      )}
                      {String(row.status) === 'failed' && (
                        <Button variant="secondary" size="sm" onClick={() => onReingestDoc(row.doc_id)}>
                          重试入库
                        </Button>
                      )}
                      <Button variant="secondary" size="sm" onClick={() => onRefreshDoc(row.doc_id, false)}>
                        刷新
                      </Button>
                      <Button variant="danger" size="sm" onClick={() => onDeleteDoc(row.doc_id)}>
                        删除
                      </Button>
                    </div>
                  ),
                },
              ]}
              data={documents}
              rowKey="doc_id"
            />

            <Modal
              open={docDetailOpen}
              onClose={() => setDocDetailOpen(false)}
              title={`文档详情：${selectedDoc?.doc_id || ''}`}
              footer={
                <>
                  <Button variant="secondary" onClick={() => setDocDetailOpen(false)}>
                    {docDetailOrigin === 'query' ? '返回主问答' : '关闭'}
                  </Button>
                  <Button variant="secondary" onClick={() => onExportDoc('json')}>
                    导出 JSON
                  </Button>
                  <Button variant="secondary" onClick={() => onExportDoc('markdown')}>
                    导出 Markdown
                  </Button>
                </>
              }
            >
              <div className="space-y-4 max-h-[70vh] overflow-auto">
                {docDetailOrigin === 'query' && (
                  <div className="text-xs text-sky-300 border border-sky-500/20 bg-sky-500/5 rounded-lg p-3">
                    当前详情是从主问答页打开的，关闭后会回到你刚才的提问上下文。
                  </div>
                )}
                <div className="text-xs text-gray-300 whitespace-pre-wrap">
                  {selectedDoc
                    ? [
                        `doc_id=${selectedDoc.doc_id}`,
                        `collection_id=${selectedDoc.collection_id}`,
                        `status=${selectedDoc.status}`,
                        `kind=${selectedDoc.kind}`,
                        `source_uri=${selectedDoc.source_uri}`,
                        `elements=${selectedDoc.element_count || 0}`,
                        `embeddings=${selectedDoc.embedding_count || 0}`,
                        `sources=${selectedDoc.source_count || 0}`,
                      ].join('\n')
                    : '暂无详情'}
                </div>

                <div className="space-y-2">
                  <div className="text-sm font-medium text-gray-200">文档问答 / 总结</div>
                  <div className="flex gap-2">
                    <Button variant={docQueryScope === 'document' ? 'primary' : 'secondary'} size="sm" onClick={() => setDocQueryScope('document')}>
                      当前文档
                    </Button>
                    <Button variant={docQueryScope === 'collection' ? 'primary' : 'secondary'} size="sm" onClick={() => setDocQueryScope('collection')}>
                      整个集合
                    </Button>
                  </div>
                  <textarea
                    className="w-full min-h-[88px] bg-dark-card border border-dark-border text-gray-200 rounded-lg px-3 py-2 text-sm"
                    value={docQuestion}
                    onChange={(e) => setDocQuestion(e.target.value)}
                    placeholder={docQueryScope === 'collection' ? '输入一个关于整个集合的问题' : '输入一个关于该文档的问题'}
                  />
                  <div className="flex gap-2">
                    <Button variant="primary" loading={docQueryLoading} onClick={onDocQuery}>
                      {docQueryScope === 'collection' ? '集合问答' : '文档问答'}
                    </Button>
                    <Button variant="secondary" loading={docSummarizeLoading} onClick={onDocSummarize}>
                      文档总结
                    </Button>
                  </div>
                  {docQueryResp?.answer && (
                    <div className="text-sm text-gray-200 border border-dark-border rounded-lg p-3">
                      <div className="text-xs text-gray-400 mb-1">
                        {docQueryScope === 'collection' ? 'collection-query' : 'document-query'} · {String(docQueryResp?.mode || '')}
                      </div>
                      <div>{String(docQueryResp.answer)}</div>
                      {Array.isArray(docQueryResp?.citations) && docQueryResp.citations.length > 0 && (
                        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                          {docQueryResp.citations.slice(0, 4).map((c: any, idx: number) => {
                            const key = _citationKey(c?.doc_id, c?.page_idx);
                            const imgUrl = citationImageUrls[key];
                            return (
                              <button
                                key={idx}
                                type="button"
                                onClick={() => openCitationInDetail(c)}
                                className="border border-dark-border rounded-lg p-2 text-xs text-gray-300 text-left hover:bg-dark-hover transition-colors"
                              >
                                <div className="mb-1">
                                  doc={String(c?.doc_id || '')} · {c?.asset_kind === 'frame_image' ? `time=${_citationLabel(c)}` : `page=${String(c?.page_idx ?? '')}`}
                                </div>
                                {imgUrl ? (
                                  <img src={imgUrl} className="w-full rounded-lg border border-dark-border" />
                                ) : c?.asset_available === false ? (
                                  <div className="text-gray-400 border border-dashed border-dark-border rounded-lg p-3 mt-2">
                                    该引用页尚未生成页面预览图，仅展示引用元数据。
                                  </div>
                                ) : (
                                  <div className="text-gray-500 border border-dashed border-dark-border rounded-lg p-3 mt-2">页面预览加载中</div>
                                )}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                  {docSummarizeResp?.summary && (
                    <div className="text-sm text-gray-200 border border-dark-border rounded-lg p-3">
                      <div className="text-xs text-gray-400 mb-1">summarize · {String(docSummarizeResp?.mode || '')}</div>
                      <div>{String(docSummarizeResp.summary)}</div>
                      {Array.isArray(docSummarizeResp.points) && docSummarizeResp.points.length > 0 && (
                        <div className="mt-2 space-y-1">
                          {docSummarizeResp.points.map((p: any, idx: number) => (
                            <div key={idx} className="text-xs text-gray-300">
                              {idx + 1}. {p?.time_ms !== undefined ? _fmtMs(p?.time_ms) : `p${String(p?.page_idx ?? '-')}`} · {String(p?.text || '')}
                            </div>
                          ))}
                        </div>
                      )}
                      {Array.isArray(docSummarizeResp?.citations) && docSummarizeResp.citations.length > 0 && (
                        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                          {docSummarizeResp.citations.slice(0, 4).map((c: any, idx: number) => {
                            const key = _citationKey(c?.doc_id, c?.page_idx);
                            const imgUrl = citationImageUrls[key];
                            return (
                              <button
                                key={idx}
                                type="button"
                                onClick={() => openCitationInDetail(c)}
                                className="border border-dark-border rounded-lg p-2 text-xs text-gray-300 text-left hover:bg-dark-hover transition-colors"
                              >
                                <div className="mb-1">
                                  doc={String(c?.doc_id || '')} · {c?.asset_kind === 'frame_image' ? `time=${_citationLabel(c)}` : `page=${String(c?.page_idx ?? '')}`}
                                </div>
                                {imgUrl ? (
                                  <img src={imgUrl} className="w-full rounded-lg border border-dark-border" />
                                ) : c?.asset_available === false ? (
                                  <div className="text-gray-400 border border-dashed border-dark-border rounded-lg p-3 mt-2">
                                    该引用页尚未生成页面预览图，仅展示引用元数据。
                                  </div>
                                ) : (
                                  <div className="text-gray-500 border border-dashed border-dark-border rounded-lg p-3 mt-2">页面预览加载中</div>
                                )}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div>
                  <div className="text-sm font-medium text-gray-200 mb-2">来源（{selectedDocSources.length}）</div>
                  <div className="space-y-2">
                    {selectedDocSources.length === 0 ? (
                      <div className="text-xs text-gray-400">暂无 sources</div>
                    ) : (
                      selectedDocSources.map((s) => (
                        <div key={s.source_id} className="border border-dark-border rounded-lg p-2 text-xs text-gray-300">
                          <div>type={s.source_type} kind={s.kind || ''}</div>
                          <div className="break-all">source_uri={s.source_uri}</div>
                          {s.url && <div className="break-all">url={s.url}</div>}
                          {s.content_hash && <div>hash={s.content_hash}</div>}
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between gap-3 mb-2">
                    <div className="text-sm font-medium text-gray-200">历史分析（{filteredAnalysisRuns.length}）</div>
                    <div className="flex gap-2">
                      <Button variant={analysisRunFilter === 'all' ? 'primary' : 'secondary'} size="sm" onClick={() => setAnalysisRunFilter('all')}>
                        全部
                      </Button>
                      <Button variant={analysisRunFilter === 'query' ? 'primary' : 'secondary'} size="sm" onClick={() => setAnalysisRunFilter('query')}>
                        问答
                      </Button>
                      <Button
                        variant={analysisRunFilter === 'summarize' ? 'primary' : 'secondary'}
                        size="sm"
                        onClick={() => setAnalysisRunFilter('summarize')}
                      >
                        总结
                      </Button>
                    </div>
                  </div>
                  <div className="mb-2">
                    <Input
                      label="搜索历史分析"
                      value={analysisRunKeyword}
                      onChange={(e) => setAnalysisRunKeyword(e.target.value)}
                      placeholder="按问题、profile、answer、summary 搜索"
                    />
                  </div>
                  <div className="space-y-2">
                    {filteredAnalysisRuns.length === 0 ? (
                      <div className="text-xs text-gray-400">暂无历史分析记录</div>
                    ) : (
                      filteredAnalysisRuns.map((r) => (
                        <div key={r.run_id} className="w-full border border-dark-border rounded-lg p-2 text-xs text-gray-300 text-left">
                          <div className="flex items-center justify-between gap-2">
                            <button type="button" onClick={() => replayAnalysisRun(r)} className="text-left hover:text-white transition-colors">
                              {String(r.run_type)} · {String(r.mode || '')}
                            </button>
                            <div className="text-gray-500">{String(r.created_at || '')}</div>
                          </div>
                          {r.run_type === 'query' && (
                            <button type="button" onClick={() => replayAnalysisRun(r)} className="mt-1 whitespace-pre-wrap text-left w-full hover:text-white transition-colors">
                              Q: {String(r.input?.question || '')}
                              {'\n'}A: {String((r.output as any)?.answer || '')}
                            </button>
                          )}
                          {r.run_type === 'summarize' && (
                            <button type="button" onClick={() => replayAnalysisRun(r)} className="mt-1 whitespace-pre-wrap text-left w-full hover:text-white transition-colors">
                              profile={String(r.input?.profile || '')}
                              {'\n'}summary: {String((r.output as any)?.summary || '')}
                            </button>
                          )}
                          <div className="mt-2 flex justify-end">
                            <Button variant="danger" size="sm" onClick={() => deleteAnalysisRun(r)}>
                              删除
                            </Button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-sm font-medium text-gray-200">元素（前 {focusedElements.length} 条）</div>
                    {focusedPageIdx !== null && (
                      <Button variant="secondary" size="sm" onClick={() => setFocusedPageIdx(null)}>
                        清除页聚焦
                      </Button>
                    )}
                  </div>
                  {focusedPageIdx !== null && (
                    <div className="mb-3 border border-dark-border rounded-lg p-3 text-xs text-gray-300">
                      <div className="mb-2">{selectedDoc?.kind === 'video' ? `当前聚焦时间片段：${_fmtMs(focusedPageIdx)}` : `当前聚焦页：p${String(focusedPageIdx)}`}</div>
                      {focusedDocPreviewUrl ? (
                        <img src={focusedDocPreviewUrl} className="w-full rounded-lg border border-dark-border" />
                      ) : (
                        <div className="text-gray-500">当前页预览加载中或不可用</div>
                      )}
                    </div>
                  )}
                  <div className="space-y-2">
                    {focusedElements.length === 0 ? (
                      <div className="text-xs text-gray-400">暂无 elements</div>
                    ) : (
                      focusedElements.map((e: any) => (
                        <div
                          key={e.element_id}
                          className={`border rounded-lg p-2 text-xs text-gray-300 ${
                            focusedPageIdx !== null && Number(e?.page_idx ?? -1) === Number(focusedPageIdx)
                              ? 'border-primary bg-dark-hover'
                              : 'border-dark-border'
                          }`}
                        >
                          <div>
                            {selectedDoc?.kind === 'video'
                              ? `segment=${String(e.page_idx ?? '-')} · ${_fmtMs(e?.meta?.start_ms)} - ${_fmtMs(e?.meta?.end_ms)}`
                              : `page=${String(e.page_idx ?? '-')} · type=${String(e.type || '')}`}
                          </div>
                          <div className="whitespace-pre-wrap break-words">{String(e.text || '').slice(0, 300)}</div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </Modal>
          </CardContent>
        </Card>
      )}

      {tab !== 'documents' && (
        <Modal
          open={docDetailOpen}
          onClose={() => setDocDetailOpen(false)}
          title={`文档详情：${selectedDoc?.doc_id || ''}`}
          footer={
            <>
              <Button variant="secondary" onClick={() => setDocDetailOpen(false)}>
                {docDetailOrigin === 'query' ? '返回主问答' : '关闭'}
              </Button>
              <Button variant="secondary" onClick={() => onExportDoc('json')}>
                导出 JSON
              </Button>
              <Button variant="secondary" onClick={() => onExportDoc('markdown')}>
                导出 Markdown
              </Button>
            </>
          }
        >
          <div className="space-y-4 max-h-[70vh] overflow-auto">
            {docDetailOrigin === 'query' && (
              <div className="text-xs text-sky-300 border border-sky-500/20 bg-sky-500/5 rounded-lg p-3">
                当前详情是从主问答页打开的，关闭后会回到你刚才的提问上下文。
              </div>
            )}
            <div className="text-xs text-gray-300 whitespace-pre-wrap">
              {selectedDoc
                ? [
                    `doc_id=${selectedDoc.doc_id}`,
                    `collection_id=${selectedDoc.collection_id}`,
                    `status=${selectedDoc.status}`,
                    `kind=${selectedDoc.kind}`,
                    `source_uri=${selectedDoc.source_uri}`,
                    `elements=${selectedDoc.element_count || 0}`,
                    `embeddings=${selectedDoc.embedding_count || 0}`,
                    `sources=${selectedDoc.source_count || 0}`,
                  ].join('\n')
                : '暂无详情'}
            </div>

            <div className="space-y-2">
              <div className="text-sm font-medium text-gray-200">文档问答 / 总结</div>
              <div className="flex gap-2">
                <Button variant={docQueryScope === 'document' ? 'primary' : 'secondary'} size="sm" onClick={() => setDocQueryScope('document')}>
                  当前文档
                </Button>
                <Button variant={docQueryScope === 'collection' ? 'primary' : 'secondary'} size="sm" onClick={() => setDocQueryScope('collection')}>
                  整个集合
                </Button>
              </div>
              <textarea
                className="w-full min-h-[88px] bg-dark-card border border-dark-border text-gray-200 rounded-lg px-3 py-2 text-sm"
                value={docQuestion}
                onChange={(e) => setDocQuestion(e.target.value)}
                placeholder={docQueryScope === 'collection' ? '输入一个关于整个集合的问题' : '输入一个关于该文档的问题'}
              />
              <div className="flex gap-2">
                <Button variant="primary" loading={docQueryLoading} onClick={onDocQuery}>
                  {docQueryScope === 'collection' ? '集合问答' : '文档问答'}
                </Button>
                <Button variant="secondary" loading={docSummarizeLoading} onClick={onDocSummarize}>
                  文档总结
                </Button>
              </div>
              {docQueryResp?.answer && (
                <div className="text-sm text-gray-200 border border-dark-border rounded-lg p-3">
                  <div className="text-xs text-gray-400 mb-1">
                    {docQueryScope === 'collection' ? 'collection-query' : 'document-query'} · {String(docQueryResp?.mode || '')}
                  </div>
                  <div>{String(docQueryResp.answer)}</div>
                  {Array.isArray(docQueryResp?.citations) && docQueryResp.citations.length > 0 && (
                    <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                      {docQueryResp.citations.slice(0, 4).map((c: any, idx: number) => {
                        const key = _citationKey(c?.doc_id, c?.page_idx);
                        const imgUrl = citationImageUrls[key];
                        return (
                          <button
                            key={idx}
                            type="button"
                            onClick={() => openCitationInDetail(c)}
                            className="border border-dark-border rounded-lg p-2 text-xs text-gray-300 text-left hover:bg-dark-hover transition-colors"
                          >
                            <div className="mb-1">
                              doc={String(c?.doc_id || '')} · {c?.asset_kind === 'frame_image' ? `time=${_citationLabel(c)}` : `page=${String(c?.page_idx ?? '')}`}
                            </div>
                            {imgUrl ? (
                              <img src={imgUrl} className="w-full rounded-lg border border-dark-border" />
                            ) : c?.asset_available === false ? (
                              <div className="text-gray-400 border border-dashed border-dark-border rounded-lg p-3 mt-2">
                                该引用页尚未生成页面预览图，仅展示引用元数据。
                              </div>
                            ) : (
                              <div className="text-gray-500 border border-dashed border-dark-border rounded-lg p-3 mt-2">页面预览加载中</div>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
              {docSummarizeResp?.summary && (
                <div className="text-sm text-gray-200 border border-dark-border rounded-lg p-3">
                  <div className="text-xs text-gray-400 mb-1">summarize · {String(docSummarizeResp?.mode || '')}</div>
                  <div>{String(docSummarizeResp.summary)}</div>
                  {Array.isArray(docSummarizeResp.points) && docSummarizeResp.points.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {docSummarizeResp.points.map((p: any, idx: number) => (
                        <div key={idx} className="text-xs text-gray-300">
                          {idx + 1}. {p?.time_ms !== undefined ? _fmtMs(p?.time_ms) : `p${String(p?.page_idx ?? '-')}`} · {String(p?.text || '')}
                        </div>
                      ))}
                    </div>
                  )}
                  {Array.isArray(docSummarizeResp?.citations) && docSummarizeResp.citations.length > 0 && (
                    <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                      {docSummarizeResp.citations.slice(0, 4).map((c: any, idx: number) => {
                        const key = _citationKey(c?.doc_id, c?.page_idx);
                        const imgUrl = citationImageUrls[key];
                        return (
                          <button
                            key={idx}
                            type="button"
                            onClick={() => openCitationInDetail(c)}
                            className="border border-dark-border rounded-lg p-2 text-xs text-gray-300 text-left hover:bg-dark-hover transition-colors"
                          >
                            <div className="mb-1">
                              doc={String(c?.doc_id || '')} · {c?.asset_kind === 'frame_image' ? `time=${_citationLabel(c)}` : `page=${String(c?.page_idx ?? '')}`}
                            </div>
                            {imgUrl ? (
                              <img src={imgUrl} className="w-full rounded-lg border border-dark-border" />
                            ) : c?.asset_available === false ? (
                              <div className="text-gray-400 border border-dashed border-dark-border rounded-lg p-3 mt-2">
                                该引用页尚未生成页面预览图，仅展示引用元数据。
                              </div>
                            ) : (
                              <div className="text-gray-500 border border-dashed border-dark-border rounded-lg p-3 mt-2">页面预览加载中</div>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div>
              <div className="text-sm font-medium text-gray-200 mb-2">来源（{selectedDocSources.length}）</div>
              <div className="space-y-2">
                {selectedDocSources.length === 0 ? (
                  <div className="text-xs text-gray-400">暂无 sources</div>
                ) : (
                  selectedDocSources.map((s) => (
                    <div key={s.source_id} className="border border-dark-border rounded-lg p-2 text-xs text-gray-300">
                      <div>type={s.source_type} kind={s.kind || ''}</div>
                      <div className="break-all">source_uri={s.source_uri}</div>
                      {s.url && <div className="break-all">url={s.url}</div>}
                      {s.content_hash && <div>hash={s.content_hash}</div>}
                    </div>
                  ))
                )}
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between gap-3 mb-2">
                <div className="text-sm font-medium text-gray-200">历史分析（{filteredAnalysisRuns.length}）</div>
                <div className="flex gap-2">
                  <Button variant={analysisRunFilter === 'all' ? 'primary' : 'secondary'} size="sm" onClick={() => setAnalysisRunFilter('all')}>
                    全部
                  </Button>
                  <Button variant={analysisRunFilter === 'query' ? 'primary' : 'secondary'} size="sm" onClick={() => setAnalysisRunFilter('query')}>
                    问答
                  </Button>
                  <Button variant={analysisRunFilter === 'summarize' ? 'primary' : 'secondary'} size="sm" onClick={() => setAnalysisRunFilter('summarize')}>
                    总结
                  </Button>
                </div>
              </div>
              <div className="mb-2">
                <Input
                  label="搜索历史分析"
                  value={analysisRunKeyword}
                  onChange={(e) => setAnalysisRunKeyword(e.target.value)}
                  placeholder="按问题、profile、answer、summary 搜索"
                />
              </div>
              <div className="space-y-2">
                {filteredAnalysisRuns.length === 0 ? (
                  <div className="text-xs text-gray-400">暂无历史分析记录</div>
                ) : (
                  filteredAnalysisRuns.map((r) => (
                    <div key={r.run_id} className="w-full border border-dark-border rounded-lg p-2 text-xs text-gray-300 text-left">
                      <div className="flex items-center justify-between gap-2">
                        <button type="button" onClick={() => replayAnalysisRun(r)} className="text-left hover:text-white transition-colors">
                          {String(r.run_type)} · {String(r.mode || '')}
                        </button>
                        <div className="text-gray-500">{String(r.created_at || '')}</div>
                      </div>
                      {r.run_type === 'query' && (
                        <button type="button" onClick={() => replayAnalysisRun(r)} className="mt-1 whitespace-pre-wrap text-left w-full hover:text-white transition-colors">
                          Q: {String(r.input?.question || '')}
                          {'\n'}A: {String((r.output as any)?.answer || '')}
                        </button>
                      )}
                      {r.run_type === 'summarize' && (
                        <button type="button" onClick={() => replayAnalysisRun(r)} className="mt-1 whitespace-pre-wrap text-left w-full hover:text-white transition-colors">
                          profile={String(r.input?.profile || '')}
                          {'\n'}summary: {String((r.output as any)?.summary || '')}
                        </button>
                      )}
                      <div className="mt-2 flex justify-end">
                        <Button variant="danger" size="sm" onClick={() => deleteAnalysisRun(r)}>
                          删除
                        </Button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="text-sm font-medium text-gray-200">元素（前 {focusedElements.length} 条）</div>
                {focusedPageIdx !== null && (
                  <Button variant="secondary" size="sm" onClick={() => setFocusedPageIdx(null)}>
                    清除页聚焦
                  </Button>
                )}
              </div>
              {focusedPageIdx !== null && (
                <div className="mb-3 border border-dark-border rounded-lg p-3 text-xs text-gray-300">
                  <div className="mb-2">{selectedDoc?.kind === 'video' ? `当前聚焦时间片段：${_fmtMs(focusedPageIdx)}` : `当前聚焦页：p${String(focusedPageIdx)}`}</div>
                  {focusedDocPreviewUrl ? (
                    <img src={focusedDocPreviewUrl} className="w-full rounded-lg border border-dark-border" />
                  ) : (
                    <div className="text-gray-500">当前页预览加载中或不可用</div>
                  )}
                </div>
              )}
              <div className="space-y-2">
                {focusedElements.length === 0 ? (
                  <div className="text-xs text-gray-400">暂无 elements</div>
                ) : (
                  focusedElements.map((e: any) => (
                    <div
                      key={e.element_id}
                      className={`border rounded-lg p-2 text-xs text-gray-300 ${
                        focusedPageIdx !== null && Number(e?.page_idx ?? -1) === Number(focusedPageIdx) ? 'border-primary bg-dark-hover' : 'border-dark-border'
                      }`}
                    >
                      <div>
                        {selectedDoc?.kind === 'video'
                          ? `segment=${String(e.page_idx ?? '-')} · ${_fmtMs(e?.meta?.start_ms)} - ${_fmtMs(e?.meta?.end_ms)}`
                          : `page=${String(e.page_idx ?? '-')} · type=${String(e.type || '')}`}
                      </div>
                      <div className="whitespace-pre-wrap break-words">{String(e.text || '').slice(0, 300)}</div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </Modal>
      )}

      {tab === 'query' && (
        <div className="grid grid-cols-1 gap-4">
          <Card>
            <CardHeader>
              <div>
                <div className="font-semibold text-gray-100">问答</div>
                <div className="text-xs text-gray-400 mt-0.5">
                  {queryScope === 'document'
                    ? '当前使用单文档问答：只在指定文档内检索与回答'
                    : '当前使用集合问答：在当前 collection 的全部文档中检索与回答'}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <Input label="问题" value={question} onChange={(e) => setQuestion(e.target.value)} />
                <div className="flex items-center gap-2 flex-wrap text-xs text-gray-400">
                  <span>提问范围</span>
                  <Button variant={queryScope === 'collection' ? 'primary' : 'secondary'} size="sm" onClick={() => setQueryScope('collection')}>
                    整个集合
                  </Button>
                  <Button
                    variant={queryScope === 'document' ? 'primary' : 'secondary'}
                    size="sm"
                    onClick={() => {
                      setQueryScope('document');
                      if (!queryDocId && queryDocOptions.length > 0) setQueryDocId(queryDocOptions[0].value);
                    }}
                  >
                    指定文档
                  </Button>
                </div>
                {queryScope === 'document' && (
                  <div>
                    <div className="text-xs text-gray-400 mb-1">选择文档</div>
                    <div className="flex gap-2 items-center">
                      <select
                        className="flex-1 bg-dark-card border border-dark-border text-gray-200 rounded-lg px-3 py-2 text-sm"
                        value={queryDocId}
                        onChange={(e) => setQueryDocId(e.target.value)}
                      >
                        {queryDocOptions.length === 0 ? (
                          <option value="">当前集合暂无文档</option>
                        ) : (
                          queryDocOptions.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))
                        )}
                      </select>
                      <Button variant="secondary" size="sm" disabled={!queryDocId} onClick={() => queryDocId && loadDocumentDetail(queryDocId)}>
                        查看详情
                      </Button>
                    </div>
                  </div>
                )}
                <div className="flex items-center gap-2 flex-wrap text-xs text-gray-400">
                  <span>视图模式</span>
                  <Button variant={queryViewMode === 'auto' ? 'primary' : 'secondary'} size="sm" onClick={() => setQueryViewMode('auto')}>
                    自动
                  </Button>
                  <Button variant={queryViewMode === 'precise' ? 'primary' : 'secondary'} size="sm" onClick={() => setQueryViewMode('precise')}>
                    精确问答
                  </Button>
                  <Button variant={queryViewMode === 'analysis' ? 'primary' : 'secondary'} size="sm" onClick={() => setQueryViewMode('analysis')}>
                    浏览分析
                  </Button>
                </div>
                <div className="flex gap-2">
                  <Button variant="primary" loading={queryLoading} onClick={onQuery}>
                    查询
                  </Button>
                  <Button
                    variant="secondary"
                    loading={queryRewriteLoading}
                    disabled={!qout?.answer}
                    onClick={onRewriteAnswer}
                  >
                    答案重写
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setQueryResp(null);
                      setRewrittenAnswer('');
                      setRewrittenAnswerMode('llm');
                      setQueryExpandedView(false);
                      setQueryShowAllEvidence(false);
                    }}
                  >
                    清空
                  </Button>
                </div>
              </div>

              {qout?.answer && (
                <div className="mt-4 text-sm text-gray-200 border border-dark-border rounded-xl p-4 bg-dark-card">
                  <div className="flex items-center justify-between gap-3 flex-wrap mb-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <div className="text-sm font-medium text-gray-100">系统回答</div>
                      <span
                        className={`px-2 py-1 rounded text-xs ${
                          preciseQuestionMode
                            ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20'
                            : 'bg-sky-500/10 text-sky-300 border border-sky-500/20'
                        }`}
                      >
                        {preciseQuestionMode ? '精确问答模式' : '浏览分析模式'}
                        {queryViewMode !== 'auto' ? '（手动）' : '（自动）'}
                      </span>
                    </div>
                    <div className="text-xs text-gray-400">mode: {String(qout?.mode || '')}</div>
                  </div>
                  <div className="text-xs text-gray-400 mb-2">
                    {preciseQuestionMode
                      ? '当前默认只展示最直接支撑答案的精简证据，适合“是什么 / 多少 / 哪一年”这类短问题。'
                      : '当前会展示更多结构化总结与相关依据，适合浏览文档全貌或做主题分析。'}
                  </div>
                  <div className="flex items-center gap-2 flex-wrap text-xs text-gray-400 mb-2">
                    <span>
                      {queryScope === 'document'
                        ? `当前提问范围：单文档${queryDocId ? ` · ${queryDocOptions.find((x) => x.value === queryDocId)?.label || queryDocId}` : ''}`
                        : `当前提问范围：整个集合 · ${selectedCollection}`}
                    </span>
                    {queryScope === 'document' && queryDocId && (
                      <Button variant="secondary" size="sm" onClick={() => loadDocumentDetail(queryDocId)}>
                        跳到文档详情
                      </Button>
                    )}
                  </div>
                  <div className="whitespace-pre-wrap break-words leading-7">{String(qout.answer)}</div>
                  {String(qout?.mode || '').includes('fallback') && (
                    <div className="mt-3 text-xs text-amber-300 border border-amber-500/20 bg-amber-500/5 rounded-lg p-3">
                      当前结果更偏“检索命中展示”，不是经过 LLM 整理后的正式摘要。请结合下方命中依据判断答案是否准确。
                    </div>
                  )}
                </div>
              )}

              {rewrittenAnswer && (
                <div className="mt-4 text-sm text-gray-200 border border-primary/30 rounded-xl p-4 bg-dark-card">
                  <div className="flex items-center justify-between gap-3 flex-wrap mb-2">
                    <div className="text-sm font-medium text-primary">
                      重写后答案（{rewrittenAnswerMode === 'llm' ? 'LLM' : '本地降级'}）
                    </div>
                    <Button variant="secondary" size="sm" onClick={() => _copyText(rewrittenAnswer)}>
                      复制
                    </Button>
                  </div>
                  <div className="whitespace-pre-wrap break-words leading-7">{rewrittenAnswer}</div>
                </div>
              )}

              {(structuredAnswer.core.length > 0 || structuredAnswer.numeric.length > 0) && (!preciseQuestionMode || queryExpandedView) && (
                <div className="mt-4 grid grid-cols-1 xl:grid-cols-3 gap-4">
                  <div className="xl:col-span-2 border border-dark-border rounded-xl p-4 bg-dark-card">
                    <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
                      <div className="text-sm font-medium text-gray-100">结构化总结</div>
                      <div className="flex gap-2">
                        <Button variant="secondary" size="sm" onClick={() => _copyText(structuredAnswerMarkdown)}>
                          复制摘要
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => _downloadText(`kb_structured_answer_${selectedCollection || 'default'}_${_tsSlug()}.md`, structuredAnswerMarkdown, 'text/markdown;charset=utf-8')}
                        >
                          导出 Markdown
                        </Button>
                      </div>
                    </div>
                    <div className="space-y-2">
                      {structuredAnswer.core.length === 0 ? (
                        <div className="text-sm text-gray-400">暂无可提炼的核心结论</div>
                      ) : (
                        structuredAnswer.core.map((line, idx) => (
                          <div key={idx} className="text-sm text-gray-200 leading-7 border border-dark-border rounded-lg px-3 py-2 bg-dark-hover">
                            {idx + 1}. {_prettyLine(line)}
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                  <div className="space-y-4">
                    <div className="border border-dark-border rounded-xl p-4 bg-dark-card">
                      <div className="text-sm font-medium text-gray-100 mb-3">关键数字</div>
                      <div className="space-y-2">
                        {structuredAnswer.numeric.length === 0 ? (
                          <div className="text-sm text-gray-400">暂无明显数字信息</div>
                        ) : (
                          structuredAnswer.numeric.map((line, idx) => (
                            <div key={idx} className="text-sm text-gray-200 leading-7 border border-dark-border rounded-lg px-3 py-2 bg-dark-hover">
                              {_prettyLine(line)}
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                    <div className="border border-dark-border rounded-xl p-4 bg-dark-card">
                      <div className="text-sm font-medium text-gray-100 mb-3">主要依据{isVideoQuery ? '时间片段' : '页'}</div>
                      <div className="flex gap-2 flex-wrap">
                        {structuredAnswer.pages.length === 0 ? (
                          <div className="text-sm text-gray-400">暂无</div>
                        ) : (
                          structuredAnswer.pages.map((p, idx) => (
                            <span key={idx} className="px-2 py-1 rounded bg-dark-hover text-xs text-gray-200">
                              {p}
                            </span>
                          ))
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <div className="mt-4">
                <div className="flex items-center justify-between gap-3 mb-1 flex-wrap">
                  <div className="text-sm font-medium text-gray-200">
                    {preciseQuestionMode ? '精确证据' : `直接证据${isVideoQuery ? '片段' : '页'}`}（{evidenceGroups.length}/{groupedItems.length} {isVideoQuery ? '段' : '页'}，原始 {items.length} 条）
                  </div>
                  <div className="flex items-center gap-3 flex-wrap">
                    <label className="flex items-center gap-2 text-xs text-gray-400">
                      <input type="checkbox" checked={queryHighScoreOnly} onChange={(e) => setQueryHighScoreOnly(e.target.checked)} />
                      <span>仅看高相关（score ≥ 0.08）</span>
                    </label>
                    {preciseQuestionMode && (
                      <Button variant="secondary" size="sm" onClick={() => setQueryExpandedView((v) => !v)}>
                        {queryExpandedView ? '收起更多' : '展开更多'}
                      </Button>
                    )}
                    <Button variant="secondary" size="sm" onClick={() => setQueryShowAllEvidence((v) => !v)}>
                      {queryShowAllEvidence ? '只看直接证据' : '显示全部相关页'}
                    </Button>
                  </div>
                </div>
                <div className="text-xs text-gray-400 mb-3">
                  {preciseQuestionMode
                    ? '当前是精确问答模式：默认只展示最直接支撑答案的 1 条证据，避免把整篇文档背景全部摊开。'
                    : `默认优先展示最直接支撑当前问题的 1 到 2 ${isVideoQuery ? '段' : '页'}依据，避免把整篇文档背景全部摊开。需要时可切换为全部相关${isVideoQuery ? '片段' : '页'}。`}
                </div>
                {queryHighScoreOnly && filteredOutCount > 0 && (
                  <div className="text-xs text-amber-300 border border-amber-500/20 bg-amber-500/5 rounded-lg p-2 mb-3">
                    已按高相关过滤掉 {filteredOutCount} 条命中。若想看全量结果，请关闭“仅看高相关”。
                  </div>
                )}
                <div className="space-y-3">
                  {evidenceGroups.length === 0 ? (
                    <div className="text-sm text-gray-400">
                      {items.length > 0 && queryHighScoreOnly ? '当前无命中页（可能被高相关过滤隐藏）' : '暂无命中条目'}
                    </div>
                  ) : (
                    evidenceGroups.map((group: any) => (
                      <div
                        key={group.key}
                        className="border border-dark-border rounded-xl p-4 bg-dark-card"
                      >
                        <div className="flex items-start justify-between gap-3 mb-2 flex-wrap">
                          <div className="min-w-0 flex-1">
                            <div className="text-sm font-medium text-gray-100 break-words">
                              {_snippetTitle(group.items?.[0]?.snippet)}
                            </div>
                            <div className="flex items-center gap-2 flex-wrap text-xs mt-2">
                              <span className="px-2 py-1 rounded bg-dark-hover text-gray-200">doc: {String(group.doc_id || '-')}</span>
                              <span className="px-2 py-1 rounded bg-dark-hover text-gray-200">
                                {_isVideoItem(group.items?.[0]) ? `time: ${_itemTimeLabel(group.items?.[0])}` : `page: ${String(group.page_idx ?? '-')}`}
                              </span>
                              <span className="px-2 py-1 rounded bg-dark-hover text-gray-200">最高 score: {Number(group.maxScore || 0).toFixed(4)}</span>
                              <span className="px-2 py-1 rounded bg-dark-hover text-gray-200">命中数: {Number(group.items?.length || 0)}</span>
                            </div>
                          </div>
                          <div className="flex gap-2">
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => setCollapsedGroups((prev) => ({ ...prev, [group.key]: !prev[group.key] }))}
                            >
                              {collapsedGroups[group.key] === false ? '折叠' : '展开'}
                            </Button>
                            <Button variant="secondary" size="sm" onClick={() => setQueryPreviewItem(group.items?.[0])}>
                              查看首条全文
                            </Button>
                          </div>
                        </div>
                        <div className="text-sm text-gray-300 leading-7 bg-dark-hover border border-dark-border rounded-lg p-3">
                          {_snippetPreview(group.items?.[0]?.snippet, 220) || '(empty)'}
                        </div>
                        {collapsedGroups[group.key] === false && (
                          <div className="mt-3 space-y-2">
                            {(group.items || []).map((it: any, subIdx: number) => (
                              <div key={`${group.key}_${subIdx}`} className="border border-dark-border rounded-lg p-3">
                                <div className="flex items-center justify-between gap-2 flex-wrap mb-2">
                                  <div className="text-xs text-gray-400">片段 {subIdx + 1} · score {Number(it.score || 0).toFixed(4)}</div>
                                  <Button variant="secondary" size="sm" onClick={() => setQueryPreviewItem(it)}>
                                    查看全文
                                  </Button>
                                </div>
                                <div className="text-sm text-gray-300 leading-7">{_snippetPreview(it.snippet, 320) || '(empty)'}</div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div>
                <div className="font-semibold text-gray-100">引用与高亮</div>
                <div className="text-xs text-gray-400 mt-0.5">这里展示答案引用来源。若没有可用预览图，会显示文档ID与页码/时间片段定位信息。</div>
              </div>
            </CardHeader>
            <CardContent>
              {displayedCitations.length === 0 ? (
                <div className="text-sm text-gray-400">暂无 citations</div>
              ) : allCitationsWithoutPreview ? (
                <div className="space-y-4">
                  <div className="text-sm text-gray-300 border border-dashed border-dark-border rounded-xl p-4 bg-dark-card">
                    当前还没有可显示的预览图，所以这里先展示引用位置。你可以点击条目，跳到对应文档页或视频时间片段继续查看。
                  </div>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {citationGroups.map((group: any) => (
                      <div key={group.doc_id} className="border border-dark-border rounded-xl p-4 bg-dark-card">
                        <div className="text-sm font-medium text-gray-100 break-all">{group.doc_id}</div>
                        <div className="text-xs text-gray-400 mt-1">暂无预览图 · 共 {Number(group.pages?.length || 0)} 条引用</div>
                        <div className="flex gap-2 flex-wrap mt-3">
                          {(group.pages || []).map((c: any, idx: number) => (
                            <button
                              key={`${group.doc_id}_${idx}`}
                              type="button"
                              onClick={() => openCitationInDetail(c)}
                              className="px-2 py-1 rounded-lg bg-dark-hover text-xs text-gray-200 hover:text-white"
                            >
                              {_citationLabel(c)}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {displayedCitations.slice(0, 10).map((c, idx) => (
                    (() => {
                      const key = _citationKey(c?.doc_id, c?.page_idx);
                      const imgUrl = citationImageUrls[key];
                      return (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => openCitationInDetail(c)}
                          className="border border-dark-border rounded-xl p-3 text-xs text-gray-300 text-left hover:bg-dark-hover transition-colors"
                        >
                          <div className="flex items-center gap-2 flex-wrap mb-2">
                            <span className="px-2 py-1 rounded bg-dark-hover">doc={String(c.doc_id || '')}</span>
                            <span className="px-2 py-1 rounded bg-dark-hover">
                              {_isVideoItem(c) ? `time=${_citationLabel(c)}` : `page=${String(c.page_idx ?? '')}`}
                            </span>
                          </div>
                          {imgUrl ? (
                            <img src={imgUrl} className="w-full rounded-lg border border-dark-border" />
                          ) : c?.asset_available === false ? (
                            <div className="text-gray-400 border border-dashed border-dark-border rounded-lg p-3 mt-2">
                              {_isVideoItem(c) ? '该引用时间片段尚未生成可用预览，因此这里只展示时间与引用元数据。' : '该引用页尚未生成页面预览图，因此这里只能展示页码与引用元数据。'}
                            </div>
                          ) : (
                            <div className="text-gray-500 border border-dashed border-dark-border rounded-lg p-3 mt-2">页面预览加载中</div>
                          )}
                        </button>
                      );
                    })()
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Modal
            open={!!queryPreviewItem}
            onClose={() => setQueryPreviewItem(null)}
            title="命中片段全文"
            footer={
              <Button variant="secondary" onClick={() => setQueryPreviewItem(null)}>
                关闭
              </Button>
            }
          >
            <div className="space-y-3">
              <div className="flex gap-2 flex-wrap text-xs text-gray-300">
                <span className="px-2 py-1 rounded bg-dark-hover">doc: {String(queryPreviewItem?.doc_id || '-')}</span>
                <span className="px-2 py-1 rounded bg-dark-hover">
                  {_isVideoItem(queryPreviewItem) ? `time: ${_itemTimeLabel(queryPreviewItem)}` : `page: ${String(queryPreviewItem?.page_idx ?? '-')}`}
                </span>
                <span className="px-2 py-1 rounded bg-dark-hover">score: {Number(queryPreviewItem?.score || 0).toFixed(4)}</span>
              </div>
              <div className="text-xs text-gray-400">
                这里优先展示命中片段的完整文本；列表里的短句只是预览。
              </div>
              <pre className="text-sm text-gray-200 whitespace-pre-wrap break-words leading-6 bg-dark-hover border border-dark-border rounded-lg p-4 max-h-[60vh] overflow-auto">
                {String(queryPreviewItem?.full_text || queryPreviewItem?.snippet || '').trim() || '(empty)'}
              </pre>
            </div>
          </Modal>
        </div>
      )}

      {tab === 'settings' && (
        <Card>
          <CardHeader>
            <div>
              <div className="font-semibold text-gray-100">认证配置</div>
              <div className="text-xs text-gray-400 mt-0.5">写入 localStorage：active_api_key / active_tenant_id</div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 max-w-xl">
              <Input label="Tenant ID" value={tenantId} onChange={(e) => setTenantId(e.target.value)} placeholder="default" />
              <Input label="API Key" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="X-AIPLAT-API-KEY" />
              <div className="flex gap-2">
                <Button variant="primary" onClick={saveSettings}>
                  保存
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default KnowledgeBase;
