import React, { useEffect, useState } from 'react';
import { Button, Card, CardContent, CardHeader, Input, Textarea, toast } from '../../../components/ui';
import { Plus, AlertTriangle, Database, Trash2 } from 'lucide-react';
import { useKBStore } from '../../../stores';
import { kbApi } from '../../../services';
import { DocumentGrid } from './DocumentGrid';
import { UploadModal } from './UploadModal';
import { ChatPanel } from './ChatPanel';
import WikiGraph from '../../../components/wiki/WikiGraph';
import WikiListView from '../../../components/wiki/WikiListView';
import WikiHealthDashboard from '../../../components/wiki/WikiHealthDashboard';
import VaultBrowser from './VaultBrowser';

const WIKI_API = '/api/core/wiki';

const METRIC_LABELS: Record<string, string> = {
  faithfulness: '忠实度',
  answer_relevancy: '答案相关性',
  context_precision: '上下文精确度',
  context_recall: '上下文召回率',
};

const KnowledgeBasePage: React.FC = () => {
  const {
    documents, loading, totalDocuments,
    selectedDocIds, activeCategory,
    contentCategories,
    uploadModalOpen, uploadProgress,
    fetchDocuments, fetchCategories,
    setUploadModalOpen, clearSelection,
  } = useKBStore();

  const [activeTab, setActiveTab] = useState<string>('documents');

  // Wiki states
  const [wikiPages, setWikiPages] = useState<any[]>([]);
  const [wikiQuery, setWikiQuery] = useState('');
  const [wikiViewMode, setWikiViewMode] = useState<'graph' | 'list'>('graph');
  const [wikiCategory, setWikiCategory] = useState('');
  const [wikiLoading] = useState(false);
  const [selectedPage, setSelectedPage] = useState<any>(null);
  const [wikiNewTitle, setWikiNewTitle] = useState('');
  const [wikiNewBody, setWikiNewBody] = useState('');
  const [wikiNewTags, setWikiNewTags] = useState('');
  const [wikiNewCategory, setWikiNewCategory] = useState('entities');
  const [convertResult, setConvertResult] = useState<any>(null);
  const [converting, setConverting] = useState(false);
  const [convertingSelected, setConvertingSelected] = useState(false);
  const [newPageOpen, setNewPageOpen] = useState(false);
  const [unprocessedCount, setUnprocessedCount] = useState(0);
  const [unprocessedDocs, setUnprocessedDocs] = useState<any[]>([]);
  const [wikiDocIds, setWikiDocIds] = useState<Set<string>>(new Set());
  const [lintResult, setLintResult] = useState<any>(null);
  const [healthTrend, setHealthTrend] = useState<any>(null);
  const [lintLoading, setLintLoading] = useState(false);
  const [proposals, setProposals] = useState<any[]>([]);
  const [proposalsLoading, setProposalsLoading] = useState(false);
  const [curating, setCurating] = useState(false);
  const [curateReport, setCurateReport] = useState<any>(null);
  const [graphRefreshKey, setGraphRefreshKey] = useState(0);
  const [wikiChatOpen, setWikiChatOpen] = useState(false);
  const [exploreTitles, setExploreTitles] = useState<Set<string> | null>(null);
  const [wikiCollection, setWikiCollection] = useState('default');
  const [wikiCollections, setWikiCollections] = useState<Array<{ collection_id: string; page_count: number }>>([]);
  const [schema, setSchema] = useState<any>(null);
  const [allSchemas, setAllSchemas] = useState<any[]>([]);
  const [hasExtension, setHasExtension] = useState(false);
  const [extensionLabel, setExtensionLabel] = useState('');
  const [ontoMetrics, setOntoMetrics] = useState<any>(null);
  const [ontoSuggestions, setOntoSuggestions] = useState<any[]>([]);
  const [ontoPanelOpen, setOntoPanelOpen] = useState(false);
  const [ontoGenerating, setOntoGenerating] = useState(false);
  const [metricsHistory, setMetricsHistory] = useState<any[]>([]);
  const [goldenResults, setGoldenResults] = useState<any>(null);
  const [patterns, setPatterns] = useState<any>(null);
  const [ontoClasses, setOntoClasses] = useState<any[]>([]);
  const [ontoTreeOpen, setOntoTreeOpen] = useState(false);
  const [modelLog, setModelLog] = useState<any[]>([]);
  const [latencyData, setLatencyData] = useState<any>(null);
  const [evolutionHistory, setEvolutionHistory] = useState<any[]>([]);
  const [evolving, setEvolving] = useState(false);
  const [evidenceChain, setEvidenceChain] = useState<any>(null);
  const [showEvidence, setShowEvidence] = useState(false);

  const [evalSamples, setEvalSamples] = useState<any[]>([]);
  const [evalResult, setEvalResult] = useState<any>(null);
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalForm, setEvalForm] = useState({ question: '', ground_truth: '', doc_ids: '', tags: '' });
  const [evalTag, setEvalTag] = useState('');
  const [timeSeries, setTimeSeries] = useState<any>(null);
  const [compareResult, setCompareResult] = useState<any>(null);
  const [drillSample, setDrillSample] = useState<any>(null);
  const [csvFile, setCsvFile] = useState<File | null>(null);

  const updateEvalForm = (field: string, value: string) => {
    setEvalForm(prev => ({ ...prev, [field]: value }));
  };

  useEffect(() => {
    fetchDocuments(undefined, activeCategory);
    fetchCategories();
    checkUnprocessed();
  }, [activeCategory]);

  const checkUnprocessed = async () => {
    try {
      const res = await fetch(`${WIKI_API}/unprocessed-docs`).then(r => r.json());
      const items = res.items || [];
      setUnprocessedDocs(items);
      setUnprocessedCount(items.length);
    } catch { setUnprocessedCount(0); setUnprocessedDocs([]); }
  };

  const handleUploadComplete = async () => {
    setUploadModalOpen(false);
    await fetchDocuments(undefined, activeCategory);
    await fetchCategories();
    // Poll until all documents are ready (not ingesting)
    pollDocumentReady();
  };

  const pollDocumentReady = () => {
    let attempts = 0;
    const maxAttempts = 30;
    const poll = async () => {
      try {
        const res = await fetch('/api/platform/documents?limit=100').then(r => r.json());
        const items = res.items || [];
        const ingesting = items.filter((d: any) => d.status === 'ingesting');
        if (ingesting.length === 0 && items.length > 0) {
          // All documents ready — final refresh
          await fetchDocuments(undefined, activeCategory);
          checkUnprocessed();
          return;
        }
        attempts++;
        if (attempts < maxAttempts) {
          if (attempts === 1) toast.info('文档处理中…');
          setTimeout(poll, 2000);
        } else {
          toast.info('处理超时，请刷新页面查看');
          await fetchDocuments(undefined, activeCategory);
        }
      } catch {
        setTimeout(poll, 2000);
      }
    };
    poll();
  };

  const refreshEvalSamples = async () => {
    try { const r = await kbApi.listEvalSamples(50, 0); setEvalSamples(r.items || []); } catch {}
  };
  const addEvalSample = async () => {
    if (!evalForm.question.trim() || !evalForm.ground_truth.trim()) { toast.error('问题和标准答案必填'); return; }
    try {
      await kbApi.createEvalSample({ question: evalForm.question, ground_truth: evalForm.ground_truth, doc_ids: evalForm.doc_ids.split(',').map(s=>s.trim()).filter(Boolean), tags: evalForm.tags.split(',').map(s=>s.trim()).filter(Boolean) });
      setEvalForm({ question: '', ground_truth: '', doc_ids: '', tags: '' });
      await refreshEvalSamples();
      toast.success('样本已添加');
    } catch (e: any) { toast.error(`添加失败：${e?.message || e}`); }
  };
  const deleteEvalSample = async (id: string) => {
    if (!window.confirm('确定删除此评估样本？')) return;
    try { await kbApi.deleteEvalSample(id); await refreshEvalSamples(); } catch {}
  };
  const runEval = async () => {
    setEvalLoading(true); setEvalResult(null);
    try {
      const r = await kbApi.runEval(evalTag ? { tag: evalTag } : {});
      setEvalResult(r);
      toast.success(`${r.reports || 0} 个报告完成`);
    } catch (e: any) { toast.error(`评估失败：${e?.message || e}`); }
    finally { setEvalLoading(false); }
  };

  useEffect(() => {
    if (activeTab === 'eval') { refreshEvalSamples(); loadTimeSeries(); }
    else if (activeTab === 'wiki') { fetchWikiPages(); fetchWikiCollections(); fetchWikiSchema(); }
    else if (activeTab === 'health') { runLint(); fetchProposals(); fetchHealthTrend(); }
    else if (activeTab === 'ontology') { fetchOntoMetrics(); fetchOntoSuggestions(); fetchMetricsHistory(); fetchGoldenRegression(); fetchPatterns(); fetchOntoClasses(); }
    else if (activeTab === 'observe') { fetchOntoMetrics(); fetchModelLog(); fetchEvolutionHistory(); }
  }, [activeTab]);

  // ── Wiki functions ──
  const fetchWikiPages = async () => {
    void (wikiLoading);
    try {
      let url = `${WIKI_API}/pages?limit=100&source=kb&collection=${wikiCollection}`;
      if (wikiQuery) url += `&query=${encodeURIComponent(wikiQuery)}`;
      if (wikiCategory) url += `&category=${encodeURIComponent(wikiCategory)}`;
      const res = await fetch(url); setWikiPages((await res.json()).items || []);
    } catch {} finally { void (wikiLoading); }
  };
  const readWikiPage = async (title: string) => {
    try {
      const res = await fetch(`${WIKI_API}/pages/${encodeURIComponent(title)}?collection=${wikiCollection}`);
      setSelectedPage(await res.json());
      // Also fetch evidence chain
      try {
        const evRes = await fetch(`${WIKI_API}/claim/${encodeURIComponent(title)}/evidence-chain?collection=${wikiCollection}`);
        setEvidenceChain(await evRes.json());
      } catch { setEvidenceChain(null); }
    } catch {}
  };
  const handleWikiCreate = async () => {
    if (!wikiNewTitle.trim() || !wikiNewBody.trim()) return;
    try {
      const res = await fetch(`${WIKI_API}/pages?collection=${wikiCollection}`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: wikiNewTitle, body: wikiNewBody, category: wikiNewCategory, tags: wikiNewTags.split(',').map((s: string) => s.trim()).filter(Boolean), summary: wikiNewBody.slice(0, 200) }) });
      const data = await res.json();
      const autoLinks = data?.auto_links || [];
      const msg = '页面已创建' + (autoLinks.length > 0 ? ` · 自动关联 ${autoLinks.length} 个页面` : '');
      toast.success(msg); setWikiNewTitle(''); setWikiNewBody(''); setWikiNewTags(''); setNewPageOpen(false); fetchWikiPages();
    } catch { toast.error('创建失败'); }
  };
  const handleWikiDelete = async (title: string) => {
    if (!confirm(`确定删除 "${title}"？`)) return;
    try {
      await fetch(`${WIKI_API}/pages/${encodeURIComponent(title)}?collection=${wikiCollection}`, { method: 'DELETE' });
      toast.success('已删除'); fetchWikiPages(); setSelectedPage(null); setGraphRefreshKey(k => k + 1);
    } catch { toast.error('删除失败'); }
  };
  const handleExplore = async (title: string) => {
    try {
      const res = await fetch(`${WIKI_API}/traverse/${encodeURIComponent(title)}?depth=2&collection=${wikiCollection}`);
      const data = await res.json();
      const titles = new Set<string>((data.items || []).map((p: any) => p.title));
      titles.add(title); setExploreTitles(titles);
    } catch { toast.error('展开失败'); }
  };
  const handleExitExplore = () => { setExploreTitles(null); setSelectedPage(null); };
  const handleConvertKb = async (docIds?: string[]) => {
    setConverting(true);
    try {
      const body: any = { tenant_id: 'default', limit: 50 };
      if (docIds && docIds.length > 0) body.doc_ids = docIds;
      const res = await fetch(`${WIKI_API}/convert-from-kb`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await res.json(); setConvertResult(data); toast.success(data.message || `转换 ${data.docs_converted || 0} 个文档`);
      fetchWikiPages(); setTimeout(checkUnprocessed, 500); setGraphRefreshKey(k => k + 1); } catch {} finally { setConverting(false); }
  };
  const handleConvertSelected = async () => {
    const unprocessedIds = new Set(unprocessedDocs.map((d: any) => d.doc_id));
    const selected = Array.from(selectedDocIds).filter(id => unprocessedIds.has(id));
    if (selected.length === 0) { toast.info('请先在文档列表中选中未转换的文档'); return; }
    setConvertingSelected(true);
    try {
      const body = { tenant_id: 'default', limit: 50, doc_ids: selected };
      const res = await fetch(`${WIKI_API}/convert-from-kb`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await res.json(); setConvertResult(data);
      toast.success(data.message || `转换 ${data.docs_converted || 0} 个文档`);
      fetchWikiPages(); setTimeout(checkUnprocessed, 500); setGraphRefreshKey(k => k + 1);
    } catch {} finally { setConvertingSelected(false); }
  };
  const handleCurate = async () => {
    setCurating(true); setCurateReport(null);
    try {
      const res = await fetch(`${WIKI_API}/curate?collection=${wikiCollection}`, { method: 'POST', headers: { 'Content-Type': 'application/json' } });
      const data = await res.json();
      setCurateReport(data);
      toast.success(`策展完成：${data.processed} 页，${data.links_added} 条新关联`);
      fetchWikiPages(); setGraphRefreshKey(k => k + 1);
    } catch (e: any) { toast.error('策展失败'); }
    finally { setCurating(false); }
  };
  const handleWikiClear = async () => {
    if (!confirm('确定清空所有 Wiki 页面？清空后可从文档重新导入。')) return;
    try {
      const res = await fetch(`${WIKI_API}/pages-all?collection=${wikiCollection}`, { method: 'DELETE' });
      const data = await res.json();
      toast.success(data.message || '已清空');
      fetchWikiPages(); checkUnprocessed(); setSelectedPage(null); setGraphRefreshKey(k => k + 1);
    } catch { toast.error('清空失败'); }
  };

  const fetchWikiCollections = async () => {
    try {
      const res = await fetch(`${WIKI_API}/collections`);
      const data = await res.json();
      setWikiCollections(data.collections || []);
    } catch {}
  };
  const handleCreateCollection = () => {
    const name = prompt('输入新集合名称（英文/数字/下划线）：');
    if (!name) return;
    if (!/^[a-zA-Z0-9_]+$/.test(name)) { toast.error('集合名只能包含英文、数字和下划线'); return; }
    fetch(`${WIKI_API}/collections`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ collection_id: name }) })
      .then(r => r.json()).then(() => { fetchWikiCollections(); setWikiCollection(name); fetchWikiPages(); })
      .catch(() => toast.error('创建集合失败'));
  };
  const handleDeleteCollection = (cid: string) => {
    if (cid === 'default') { toast.error('不能删除 default 集合'); return; }
    if (!confirm(`确定删除集合 "${cid}" 及其所有页面？`)) return;
    fetch(`${WIKI_API}/collections/${encodeURIComponent(cid)}`, { method: 'DELETE' })
      .then(r => r.json()).then(() => { fetchWikiCollections(); if (wikiCollection === cid) setWikiCollection('default'); fetchWikiPages(); })
      .catch(() => toast.error('删除集合失败'));
  };

  const fetchWikiSchema = async () => {
    try {
      const r = await fetch(`${WIKI_API}/schema?collection=${wikiCollection}`);
      const data = await r.json();
      setAllSchemas(data.schemas || []);
      setSchema(data.schemas?.find((s: any) => s.categories?.includes(wikiNewCategory)));
      setHasExtension(data.has_extension || false);
      setExtensionLabel(data.extension_label || '');
    } catch {}
  };

  const fetchOntoMetrics = async (refresh = false) => {
    try {
      const r = await fetch(`${WIKI_API}/ontology/metrics?collection=${wikiCollection}&refresh=${refresh}`);
      setOntoMetrics(await r.json());
    } catch {}
  };
  const fetchMetricsHistory = async () => {
    try {
      const r = await fetch(`${WIKI_API}/ontology/metrics/history?collection=${wikiCollection}`);
      const data = await r.json();
      setMetricsHistory(data.history || []);
    } catch {}
  };
  const fetchGoldenRegression = async () => {
    try {
      const r = await fetch(`${WIKI_API}/ontology/golden-regression?collection=${wikiCollection}`);
      setGoldenResults(await r.json());
    } catch {}
  };
  const fetchPatterns = async () => {
    try {
      const r = await fetch(`${WIKI_API}/ontology/patterns?collection=${wikiCollection}`);
      setPatterns(await r.json());
    } catch {}
  };
  const fetchOntoClasses = async () => {
    try {
      const r = await fetch(`${WIKI_API}/ontology/classes`);
      const data = await r.json();
      setOntoClasses(data.classes || []);
    } catch {}
  };
  const fetchModelLog = async () => {
    try {
      const r = await fetch('/api/core/maintain/model-log');
      setModelLog((await r.json()).entries || []);
    } catch {}
  };
  const fetchEvolutionHistory = async () => {
    try {
      const r = await fetch(`${WIKI_API}/evolution-history?collection=${wikiCollection}`);
      setEvolutionHistory((await r.json()).generations || []);
    } catch {}
  };
  const handleEvolve = async () => {
    if (!confirm('将使用本地 LLM 运行一代知识进化（零 API 成本）。继续？')) return;
    setEvolving(true);
    try {
      const r = await fetch(`${WIKI_API}/evolve?collection=${wikiCollection}&generations=1&max_mutations=3&force=true`, { method: 'POST' });
      const data = await r.json();
      const gen = data.generations?.[0];
      if (gen) toast.success(`进化: ${gen.verdict} (delta=${gen.delta})`);
      fetchEvolutionHistory();
      fetchOntoMetrics(true);
    } catch { toast.error('进化失败'); }
    finally { setEvolving(false); }
  };
  const fetchOntoSuggestions = async () => {
    try {
      const r = await fetch(`${WIKI_API}/ontology/suggestions?collection=${wikiCollection}`);
      const data = await r.json();
      setOntoSuggestions(data.suggestions || []);
    } catch {}
  };
  const generateOntoSuggestions = async () => {
    setOntoGenerating(true);
    try {
      await fetch(`${WIKI_API}/ontology/suggestions?collection=${wikiCollection}`, { method: 'POST' });
      await fetchOntoSuggestions();
      toast.success('本体建议已生成');
    } catch { toast.error('建议生成失败'); }
    finally { setOntoGenerating(false); }
  };
  const handleAcceptSuggestion = async (id: string) => {
    try {
      await fetch(`${WIKI_API}/ontology/suggestions/${id}/accept?collection=${wikiCollection}`, { method: 'POST' });
      toast.success('已接受建议，可生成代码');
      fetchOntoSuggestions();
    } catch { toast.error('操作失败'); }
  };
  const handleRejectSuggestion = async (id: string) => {
    const reason = prompt('拒绝理由（可选）：') || '';
    try {
      await fetch(`${WIKI_API}/ontology/suggestions/${id}/reject?collection=${wikiCollection}&reason=${encodeURIComponent(reason)}`, { method: 'POST' });
      fetchOntoSuggestions();
    } catch { toast.error('操作失败'); }
  };
    const [codeGenSugId, setCodeGenSugId] = useState<string | null>(null);
  const [codeGenResult, setCodeGenResult] = useState<any>(null);
  const handleGenerateCode = async (id: string) => {
    setCodeGenSugId(id);
    try {
      const r = await fetch(`${WIKI_API}/ontology/suggestions/${id}/generate-code?collection=${wikiCollection}`, { method: 'POST' });
      setCodeGenResult(await r.json());
    } catch { toast.error('代码生成失败'); }
  };
  const handleExportOwl = async (format = 'turtle') => {
    try {
      const r = await fetch(`${WIKI_API}/ontology/export?collection=${wikiCollection}&format=${format}`);
      const text = await r.text();
      const blob = new Blob([text], { type: 'text/turtle' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `ontology-${new Date().toISOString().slice(0,10)}.${format === 'ntriples' ? 'nt' : 'ttl'}`;
      a.click(); URL.revokeObjectURL(url);
      toast.success(`已导出 ${format.toUpperCase()} (${(text.length/1024).toFixed(1)}KB)`);
    } catch { toast.error('导出失败'); }
  };
  const [batchAtomizing, setBatchAtomizing] = useState(false);
  const handleBatchAtomize = async () => {
    setBatchAtomizing(true);
    try {
      const r = await fetch(`${WIKI_API}/batch-atomize?collection=${wikiCollection}&limit=5`, { method: 'POST' });
      const data = await r.json();
      toast.success(`原子化: ${data.atoms_created} 条`);
      fetchWikiPages();
    } catch { toast.error('批量原子化失败'); }
    finally { setBatchAtomizing(false); }
  };
  const [seeding, setSeeding] = useState(false);
  const handleSeedInstances = async () => {
    if (!confirm('将用LLM分析topic页面提取子概念和矛盾。继续？')) return;
    setSeeding(true);
    try {
      const r = await fetch(`${WIKI_API}/seed-instances?collection=${wikiCollection}`, { method: 'POST' });
      const data = await r.json();
      toast.success(`种子: ${data.atoms_created||0}原子 ${data.contradictions_created||0}矛盾`);
      fetchWikiPages();
    } catch { toast.error('种子创建失败'); }
    finally { setSeeding(false); }
  };

  const runLint = async () => {
    setLintLoading(true);
    try { const res = await fetch(`${WIKI_API}/lint?collection=${wikiCollection}`); setLintResult(await res.json()); } catch {} finally { setLintLoading(false); }
  };
  const fetchHealthTrend = async () => {
    try { const res = await fetch(`${WIKI_API}/health-trend`); setHealthTrend(await res.json()); } catch {}
  };
  const fetchProposals = async () => {
    setProposalsLoading(true);
    try { const res = await fetch(`${WIKI_API}/proposals?status=pending`); setProposals((await res.json()).items || []); } catch {} finally { setProposalsLoading(false); }
  };
  const handleApproveProposal = async (id: string) => {
    try {
      const res = await fetch(`${WIKI_API}/proposals/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'approved' }) });
      const data = await res.json();
      toast.success(data?.execution?.message || '已执行');
      fetchProposals(); fetchWikiPages(); setGraphRefreshKey(k => k + 1);
    } catch { toast.error('审批失败'); }
  };
  const handleRejectProposal = async (id: string) => {
    try { await fetch(`${WIKI_API}/proposals/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: 'rejected' }) }); fetchProposals(); } catch {}
  };
  const [atomizing, setAtomizing] = useState(false);
  const handleAtomize = async () => {
    const text = prompt('输入要原子化的文档文本：');
    if (!text?.trim()) return;
    const docId = `doc_${Date.now()}`;
    setAtomizing(true);
    try {
      const res = await fetch(`${WIKI_API}/atomize-document?collection=${wikiCollection}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_text: text, doc_id: docId, max_atoms: 20 }),
      });
      const data = await res.json();
      toast.success(`原子化完成：${data.atoms_written} 条断言，${data.contradictions_found} 处矛盾`);
      fetchWikiPages(); setGraphRefreshKey(k => k + 1);
    } catch { toast.error('原子化失败'); }
    finally { setAtomizing(false); }
  };
  const sourceBadge = (cat: string) => { const colors: Record<string, string> = { entities: 'bg-blue-50 text-blue-300', topics: 'bg-purple-50 text-purple-300' }; return colors[cat] || 'bg-dark-hover text-gray-300'; };

  const loadTimeSeries = async () => {
    try { const r = await kbApi.reportsTimeSeries(30); setTimeSeries(r); } catch {}
  };
  const loadCompare = async () => {
    try { const r = await kbApi.compareReports(); setCompareResult(r); } catch {}
  };
  const handleCsvImport = async () => {
    if (!csvFile) return;
    try {
      const r = await kbApi.importEvalSamples(csvFile);
      toast.success(`已导入 ${r.imported} 条样本`);
      setCsvFile(null);
      await refreshEvalSamples();
    } catch (e: any) { toast.error(`导入失败：${e?.message || e}`); }
  };

  const MiniChart: React.FC<{ data: number[]; color: string; height?: number }> = ({ data, color, height = 30 }) => {
    if (!data || data.length < 2) return <div className="text-[10px] text-gray-600" style={{ height }}>数据不足</div>;
    const min = Math.min(...data), max = Math.max(...data), range = max - min || 1;
    const w = 120, h = height, pad = 2;
    const points = data.map((v, i) => `${(i / (data.length - 1)) * (w - 4) + 2},${h - pad - ((v - min) / range) * (h - pad * 2)}`);
    return (
      <svg width={w} height={h} className="inline-block">
        <polyline points={points.join(' ')} fill="none" stroke={color} strokeWidth="1.5" />
        {data.map((v, i) => (
          <circle key={i} cx={(i / (data.length - 1)) * (w - 4) + 2} cy={h - pad - ((v - min) / range) * (h - pad * 2)} r="1.5" fill={color} />
        ))}
      </svg>
    );
  };

  const selCount = selectedDocIds.size;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-gray-100">知识库</h1>
          <div className="flex gap-1">
            {(['documents', '编缉知识', '本体', '观测', 'Vault', '健康', '评估'] as const).map((label) => {
              const k = label === '评估' ? 'eval' : label === '编缉知识' ? 'wiki' : label === '健康' ? 'health' : label === '本体' ? 'ontology' : label === '观测' ? 'observe' : label === 'Vault' ? 'vault' : 'documents';
              return (
                <button key={k} onClick={() => setActiveTab(k)}
                  className={`px-3 py-1 rounded text-sm transition-colors ${
                    activeTab === k ? 'bg-primary/20 text-primary' : 'text-gray-400 hover:text-gray-200'
                  }`}>
                  {label}
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {selCount > 0 && (
            <Button variant="ghost" size="sm" onClick={clearSelection}>取消选中 ({selCount})</Button>
          )}
          {activeTab === 'documents' && (
            <Button variant="primary" size="sm" onClick={() => setUploadModalOpen(true)}>上传资料</Button>
          )}
        </div>
      </div>

      {unprocessedCount > 0 && (
        <div className="flex items-center gap-3 p-3 rounded-lg bg-yellow-900/20 border border-yellow-900/40 text-sm">
          <AlertTriangle className="w-4 h-4 text-yellow-400 shrink-0" />
          <span className="text-yellow-300">{unprocessedCount} 个已有文档尚未关联 Wiki 页面</span>
          <div className="flex-1" />
          <Button variant="primary" size="sm"
            onClick={handleConvertSelected}
            loading={convertingSelected}>
            转换选中 ({(() => {
              const unprocessedIds = new Set(unprocessedDocs.map((d: any) => d.doc_id));
              return Array.from(selectedDocIds).filter(id => unprocessedIds.has(id)).length;
            })()})
          </Button>
          <Button variant="ghost" size="sm" onClick={() => handleConvertKb()} loading={converting}
            className="text-xs text-yellow-400">
            批量转换全部
          </Button>
          {convertResult && <span className="text-xs text-gray-400">{convertResult.message}</span>}
        </div>
      )}

      {activeTab === 'documents' && (
        <>
          {uploadProgress && (
            <div className="flex items-center gap-3 p-2.5 rounded-lg bg-dark-card border border-dark-border">
              <div className="flex-1 h-1.5 bg-dark-bg rounded-full overflow-hidden">
                <div className="h-full bg-primary rounded-full transition-all duration-500" style={{ width: `${Math.min(100, uploadProgress.pct)}%` }} />
              </div>
              <span className="text-xs text-gray-400">{uploadProgress.message}</span>
            </div>
          )}

          <div className="flex gap-1.5 flex-wrap">
            <button onClick={() => useKBStore.setState({ activeCategory: 'all' })}
              className={`px-2.5 py-1 rounded-full text-xs transition-colors ${
                activeCategory === 'all' ? 'bg-primary/20 text-primary font-medium' : 'text-gray-400 hover:text-gray-200 hover:bg-dark-hover'
              }`}>全部文档</button>
            {contentCategories.map((cat) => (
              <button key={cat.key} onClick={() => useKBStore.setState({ activeCategory: cat.key })}
                className={`px-2.5 py-1 rounded-full text-xs transition-colors ${
                  activeCategory === cat.key ? 'bg-primary/20 text-primary font-medium' : 'text-gray-400 hover:text-gray-200 hover:bg-dark-hover'
                }`}>
                {cat.label} {cat.count > 0 && <span className="ml-1 text-[10px] opacity-60">{cat.count}</span>}
              </button>
            ))}
          </div>

          <div className="flex-1 min-w-0">
              <DocumentGrid documents={documents} loading={loading} total={totalDocuments} selectedDocIds={selectedDocIds} wikiDocIds={new Set(documents.filter((d: any) => d.wiki_status === 'wikified').map((d: any) => d.doc_id))} />
            </div>
          </>
        )}

      {activeTab === 'vault' && (
        <VaultBrowser />
      )}

      {activeTab === 'eval' && (
        <div className="space-y-4">
          {/* Time-series chart */}
          {timeSeries && timeSeries.days && timeSeries.days.length > 1 && (
            <Card>
              <CardHeader><div className="font-semibold text-gray-100">评估趋势 (近 {timeSeries.days.length} 天)</div></CardHeader>
              <CardContent>
                <div className="grid grid-cols-4 gap-3">
                  {['faithfulness', 'answer_relevancy', 'context_precision', 'context_recall'].map(k => (
                    <div key={k} className="bg-dark-bg rounded-lg p-2">
                      <div className="text-[10px] text-gray-400 mb-1">{METRIC_LABELS[k]}</div>
                      <div className="flex items-center gap-2">
                        <span className={`text-sm font-bold ${(timeSeries[k]?.[timeSeries[k].length-1] || 0) >= 0.7 ? 'text-green-400' : 'text-yellow-400'}`}>
                          {timeSeries[k]?.[timeSeries[k].length-1]?.toFixed(2) || '-'}
                        </span>
                        <MiniChart data={timeSeries[k] || []} color={k === 'faithfulness' ? '#4ade80' : k === 'answer_relevancy' ? '#60a5fa' : k === 'context_precision' ? '#f59e0b' : '#a78bfa'} />
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Regression comparison */}
          <Card>
            <CardHeader>
              <div className="font-semibold text-gray-100 flex items-center justify-between">
                <span>回归对比</span>
                <Button variant="ghost" size="sm" onClick={loadCompare}>刷新对比</Button>
              </div>
            </CardHeader>
            {compareResult && compareResult.session_a && (
              <CardContent>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <div className="text-gray-400 mb-1">📅 {compareResult.session_a}</div>
                    {Object.entries(compareResult.metrics_a || {}).map(([k, v]) => (
                      <div key={k} className="flex justify-between py-0.5">
                        <span className="text-gray-500">{k}</span>
                        <span className="font-mono">{(v as number).toFixed(3)}</span>
                      </div>
                    ))}
                  </div>
                  <div>
                    <div className="text-gray-400 mb-1">📅 {compareResult.session_b}</div>
                    {Object.entries(compareResult.metrics_b || {}).map(([k, v]) => (
                      <div key={k} className="flex justify-between py-0.5">
                        <span className="text-gray-500">{k}</span>
                        <span className={`font-mono ${(v as number) < (compareResult.metrics_a?.[k] as number || 0) ? 'text-red-400' : 'text-green-400'}`}>
                          {(v as number).toFixed(3)}
                          {(compareResult.metrics_a?.[k] as number) != null && (
                            <span className="ml-1 text-[10px]">
                              ({((v as number) - (compareResult.metrics_a?.[k] as number || 0) >= 0 ? '+' : '') + ((v as number) - (compareResult.metrics_a?.[k] as number || 0)).toFixed(3)})
                            </span>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            )}
          </Card>

          {/* Sample CRUD + CSV import */}
          <Card>
            <CardHeader><div className="font-semibold text-gray-100">评估样本</div></CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-2 mb-3">
                <Input label="问题" value={evalForm.question} onChange={e => updateEvalForm('question', e.target.value)} placeholder="例如：深度学习是什么" />
                <Input label="标准答案" value={evalForm.ground_truth} onChange={e => updateEvalForm('ground_truth', e.target.value)} placeholder="正确的回答内容" />
                <Input label="关联文档ID (逗号分隔)" value={evalForm.doc_ids} onChange={e => updateEvalForm('doc_ids', e.target.value)} placeholder="留空则检索全部文档" />
                <Input label="标签 (逗号分隔)" value={evalForm.tags} onChange={e => updateEvalForm('tags', e.target.value)} placeholder="ai, basics" />
              </div>
              <div className="flex gap-2 flex-wrap">
                <Button variant="primary" onClick={addEvalSample}>添加样本</Button>
                <Button variant="secondary" onClick={refreshEvalSamples}>刷新</Button>
                <label className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-dark-hover border border-dark-border text-sm text-gray-300 cursor-pointer hover:bg-dark-border">
                  📂 CSV导入
                  <input type="file" accept=".csv" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) { setCsvFile(f); }}} />
                </label>
                {csvFile && (
                  <Button variant="primary" size="sm" onClick={handleCsvImport}>确认导入 {csvFile.name}</Button>
                )}
              </div>
              {evalSamples.length > 0 && (
                <div className="mt-3 space-y-1 max-h-40 overflow-auto">
                  {evalSamples.map((s: any) => (
                    <div key={s.id} className="flex items-center gap-2 text-xs py-1 px-2 bg-dark-bg rounded">
                      <span className="text-gray-400 flex-1 truncate">{s.question}</span>
                      <span className="text-gray-600">{s.tags?.join(',') || ''}</span>
                      <button onClick={() => deleteEvalSample(s.id)} className="text-red-400 hover:text-red-300">&times;</button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Run eval + results */}
          <Card>
            <CardHeader><div className="font-semibold text-gray-100">执行评估</div></CardHeader>
            <CardContent>
              <div className="flex gap-2 mb-3">
                <Input label="标签筛选" value={evalTag} onChange={e => setEvalTag(e.target.value)} placeholder="留空评估全部" className="w-40" />
                <Button variant="primary" loading={evalLoading} onClick={runEval}>执行评估</Button>
                <Button variant="secondary" size="sm" onClick={loadTimeSeries}>📊 刷新趋势</Button>
              </div>
              {evalResult && (
                <div className="grid grid-cols-4 gap-2 mb-3">
                  {Object.entries(evalResult.avg_metrics || {}).map(([k, v]) => (
                    <div key={k} className="bg-dark-bg rounded-lg p-3 text-center cursor-pointer hover:bg-dark-hover"
                      onClick={async () => { try { const r = await kbApi.listEvalReports(200); setDrillSample(r.items || []); } catch {} }}>
                      <div className="text-[10px] text-gray-400">{METRIC_LABELS[k] || k}</div>
                      <div className={`text-lg font-bold ${Number(v) >= 0.7 ? 'text-green-400' : Number(v) >= 0.4 ? 'text-yellow-400' : 'text-red-400'}`}>{Number(v).toFixed(3)}</div>
                    </div>
                  ))}
                </div>
              )}
              {evalResult?.failure_distribution && (
                <div className="text-xs text-gray-500">失败分布：{JSON.stringify(evalResult.failure_distribution)}</div>
              )}
            </CardContent>
          </Card>

          {/* Drill-down modal */}
          {drillSample && drillSample.length > 0 && (
            <Card>
              <CardHeader>
                <div className="font-semibold text-gray-100 flex items-center justify-between">
                  <span>评估明细 ({drillSample.length} 条)</span>
                  <button onClick={() => setDrillSample(null)} className="text-gray-500 hover:text-gray-300 text-xs" style={{background:'none',border:'none',cursor:'pointer'}}>关闭</button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 max-h-96 overflow-auto">
                  {drillSample.slice(0, 20).map((r: any, i: number) => (
                    <div key={i} className="bg-dark-bg rounded p-2 text-xs">
                      <div className="text-gray-300 mb-1">{r.question?.slice(0, 200)}</div>
                      <div className="text-gray-500 mb-1">回答: {r.answer?.slice(0, 150)}</div>
                      <div className="grid grid-cols-4 gap-1 text-[10px]">
                        {['faithfulness','answer_relevancy','context_precision','context_recall'].map(m => (
                          <span key={m} className={Number(r[m]) >= 0.7 ? 'text-green-400' : Number(r[m]) >= 0.4 ? 'text-yellow-400' : 'text-red-400'}>
                            {m.slice(0,4)}: {Number(r[m]).toFixed(2)}
                          </span>
                        ))}
                        {r.failure_type && r.failure_type !== 'ok' && <span className="text-red-400 col-span-4">失败: {r.failure_type}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {activeTab === 'wiki' && (
        <div className="flex flex-col" style={{ height: 'calc(100vh - 200px)' }}>
          {/* Toolbar */}
          <div className="flex items-center gap-2 mb-3">
            <div className="flex gap-1">
              <button onClick={() => setWikiViewMode('graph')}
                className={`px-2.5 py-1 rounded text-xs ${wikiViewMode === 'graph' ? 'bg-primary/20 text-primary' : 'text-gray-400 hover:text-gray-200'}`}>
                图谱
              </button>
              <button onClick={() => setWikiViewMode('list')}
                className={`px-2.5 py-1 rounded text-xs ${wikiViewMode === 'list' ? 'bg-primary/20 text-primary' : 'text-gray-400 hover:text-gray-200'}`}>
                列表
              </button>
            </div>
            {wikiViewMode === 'list' && (
              <>
                <Input placeholder="搜索..." value={wikiQuery} onChange={e => setWikiQuery(e.target.value)}
                  className="w-40 h-7 text-xs" />
                <select value={wikiCategory} onChange={e => setWikiCategory(e.target.value)}
                  className="h-7 px-2 bg-dark-card border border-dark-border rounded text-xs text-gray-300">
                  <option value="">全部分类</option>
                  <option value="entities">实体</option>
                  <option value="topics">主题</option>
                </select>
              </>
            )}
            <div className="flex-1" />
            <select value={wikiCollection} onChange={e => { setWikiCollection(e.target.value); fetchWikiPages(); }}
              className="h-7 px-2 bg-dark-card border border-dark-border rounded text-xs text-gray-300">
              {wikiCollections.map(c => (
                <option key={c.collection_id} value={c.collection_id}>{c.collection_id} ({c.page_count})</option>
              ))}
            </select>
            <Button variant="ghost" size="sm" onClick={handleCreateCollection} className="text-xs" title="新建集合">+集合</Button>
            <Button variant="ghost" size="sm" onClick={() => wikiCollection !== 'default' && handleDeleteCollection(wikiCollection)} className="text-xs text-red-400 hover:text-red-300" title="删除当前集合">-集合</Button>
            <Button variant="ghost" size="sm" onClick={() => setWikiChatOpen(!wikiChatOpen)} className="text-xs">
              💬 问答
            </Button>
            <Button variant="ghost" size="sm" onClick={handleCurate} loading={curating} className="text-xs">策展</Button>
            <Button variant="ghost" size="sm" onClick={() => setNewPageOpen(true)} className="text-xs"><Plus className="w-3 h-3 mr-1" />新建</Button>
            <Button variant="primary" size="sm" onClick={() => handleConvertKb()} loading={converting} className="text-xs"><Database className="w-3 h-3 mr-1" />导入</Button>
            <Button variant="ghost" size="sm" onClick={handleAtomize} loading={atomizing} className="text-xs" title="原子化：将文档拆解为知识原子">⚛️ 原子化</Button>
            <Button variant="ghost" size="sm" onClick={handleWikiClear} className="text-xs text-red-400 hover:text-red-300"><Trash2 className="w-3 h-3 mr-1" />清空</Button>
            {convertResult && <span className="text-[10px] text-gray-400">{convertResult.message}</span>}
            {curateReport && (
              <span className="text-[10px] text-gray-400">
                策展: {curateReport.processed}页 · {curateReport.links_added}关联
                {curateReport.errors?.length > 0 && <span className="text-yellow-400"> · {curateReport.errors.length}错误</span>}
              </span>
            )}
          </div>

          {/* Wiki content + optional chat panel */}
          <div className="flex-1 min-h-0 flex gap-3">
            <div className="flex-1 min-w-0">
              {wikiViewMode === 'graph' ? (
                <div className="flex-1 min-h-0 relative h-full">
              <WikiGraph key={graphRefreshKey} onSelectPage={(title: string) => readWikiPage(title)}
                exploreTitles={exploreTitles} onExitExplore={handleExitExplore} />
              {selectedPage && (
                <div className="absolute top-2 right-2 w-80 max-h-[60%] overflow-auto bg-dark-card border border-dark-border rounded-lg shadow-lg z-10">
                  <div className="flex items-center justify-between p-2 border-b border-dark-border">
                    <span className="text-sm font-medium text-gray-200 truncate">{selectedPage.title}</span>
                    <div className="flex items-center gap-1">
                      <button onClick={() => handleExplore(selectedPage.title)} className="text-gray-500 hover:text-blue-400 text-xs" title="探索关联">🔍</button>
                      <button onClick={() => handleWikiDelete(selectedPage.title)} className="text-gray-500 hover:text-red-400 text-xs" title="删除"><Trash2 className="w-3 h-3" /></button>
                      <button onClick={() => setSelectedPage(null)} className="text-gray-500 hover:text-gray-300 text-xs">✕</button>
                    </div>
                  </div>
                  <pre className="text-xs text-gray-300 whitespace-pre-wrap p-2 max-h-64 overflow-auto">{selectedPage.body || '(无正文)'}</pre>
                  {(selectedPage.source_articles?.length > 0) && (
                    <div className="px-2 pb-2 text-[10px] text-gray-500 border-t border-dark-border pt-1.5 mt-1">
                      📎 来源: {(selectedPage.source_articles || []).filter((s: string) => s.startsWith('kb:')).join(', ').replace(/kb:/g, '') || '未知'}
                    </div>
                  )}
                  {/* Evidence Chain */}
                  {evidenceChain && (
                    <div className="px-2 pb-2 border-t border-dark-border pt-1.5 mt-1">
                      <button onClick={() => setShowEvidence(!showEvidence)}
                        className="text-[10px] text-blue-400 hover:text-blue-300 flex items-center gap-1">
                        {showEvidence ? '▼' : '▶'} 证据链
                        {evidenceChain.has_controversy && <span className="text-amber-400">⚠️ 争议</span>}
                      </button>
                      {showEvidence && (
                        <div className="mt-1 space-y-1 text-[10px]">
                          {evidenceChain.evidence_text && (
                            <div className="bg-dark-bg rounded p-1">
                              <span className="text-gray-500">证据原文: </span>
                              <span className="text-gray-300">{evidenceChain.evidence_text.slice(0, 150)}</span>
                            </div>
                          )}
                          {evidenceChain.contradictions?.length > 0 && (
                            <div className="text-amber-400">
                              ⚠️ 矛盾: {evidenceChain.contradictions.slice(0, 3).join(', ')}
                            </div>
                          )}
                          {evidenceChain.onto_contradictions?.length > 0 && (
                            <div className="text-amber-400">
                              🔗 本体矛盾: {evidenceChain.onto_contradictions.slice(0, 3).join(', ')}
                            </div>
                          )}
                          {evidenceChain.related?.length > 0 && (
                            <div className="text-gray-500">
                              🔗 关联: {evidenceChain.related.slice(0, 3).join(', ')}
                            </div>
                          )}
                          {evidenceChain.stale_references?.length > 0 && (
                            <div className="text-red-400">
                              ⚠️ 失效引用: {evidenceChain.stale_references.join(', ')}
                            </div>
                          )}
                          <div className="text-gray-500">
                            分类: {evidenceChain.category} · 更新: {(evidenceChain.last_updated || '').slice(0, 10)}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <WikiListView
              pages={wikiPages}
              onSelect={(title: string) => readWikiPage(title)}
              onDelete={handleWikiDelete}
              sourceBadge={sourceBadge}
            />
          )}

          {/* New page modal */}
          {newPageOpen && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setNewPageOpen(false)}>
              <div className="bg-dark-card border border-dark-border rounded-lg p-4 w-full max-w-md" onClick={e => e.stopPropagation()}>
                <div className="text-sm font-medium text-gray-200 mb-3">
                  新建 Wiki 页面
                  {schema && <span className="ml-2 text-xs text-gray-500">[{schema.label}]</span>}
                </div>
                <div className="space-y-2">
                  <Input placeholder="标题" value={wikiNewTitle} onChange={e => setWikiNewTitle(e.target.value)} />
                  <select value={wikiNewCategory} onChange={e => { setWikiNewCategory(e.target.value); setSchema(allSchemas.find((s: any) => s.categories?.includes(e.target.value))); }}
                    className="w-full h-8 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-300">
                    <option value="entities">实体 (概念页)</option>
                    <option value="topics">主题 (专题页)</option>
                  </select>
                  {schema && (
                    <div className="text-[10px] space-y-0.5">
                      <span className="text-amber-400">*必填: </span>
                      {schema.required_fields?.map((f: string) => (
                        <span key={f} className="text-amber-400/70 mr-2">{f}</span>
                      ))}
                      {schema.optional_fields?.length > 0 && (
                        <><span className="text-gray-500 ml-1">可选: </span>
                        {schema.optional_fields?.slice(0, 5).map((f: string) => (
                          <span key={f} className="text-gray-500 mr-2">{f}</span>
                        ))}</>
                      )}
                    </div>
                  )}
                  <Input placeholder="标签 (逗号分隔)" value={wikiNewTags} onChange={e => setWikiNewTags(e.target.value)} />
                  <Textarea rows={5} placeholder="Markdown 正文" value={wikiNewBody} onChange={e => setWikiNewBody(e.target.value)} />
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={() => setNewPageOpen(false)} className="flex-1 text-xs">取消</Button>
                    <Button variant="primary" size="sm" onClick={handleWikiCreate} className="flex-1 text-xs">创建页面</Button>
                  </div>
                </div>
              </div>
            </div>
          )}
            </div>
            {/* Wiki chat sidebar */}
            {wikiChatOpen && (
              <div className="w-[380px] flex-shrink-0 bg-dark-card rounded-lg border border-dark-border overflow-hidden">
                <ChatPanel onClose={() => setWikiChatOpen(false)} wikiTitles={selectedPage ? [selectedPage.title] : []} label="Wiki 问答" />
              </div>
            )}
            {/* Ontology Health Panel */}
            <div className="mt-3 border-t border-dark-border pt-2">
              <button onClick={() => { setOntoPanelOpen(!ontoPanelOpen); if (!ontoMetrics) fetchOntoMetrics(); if (ontoSuggestions.length === 0) fetchOntoSuggestions(); }}
                className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200">
                <span>{ontoPanelOpen ? '▼' : '▶'}</span> 本体健康
                {ontoMetrics && <span className="ml-2 text-gray-500">
                  覆盖率 {ontoMetrics.coverage?.percentage}% · {ontoSuggestions.filter((s: any) => s.status === 'pending').length} 待处理
                </span>}
              </button>
              {ontoPanelOpen && (
                <div className="mt-2 space-y-2">
                  {/* Quick metrics */}
                  {ontoMetrics && (
                    <div className="grid grid-cols-4 gap-2 text-[10px]">
                      <div className="bg-dark-bg rounded p-1.5 text-center">
                        <div className="text-gray-400">覆盖率</div>
                        <div className="text-primary font-medium">{ontoMetrics.coverage?.percentage}%</div>
                      </div>
                      <div className="bg-dark-bg rounded p-1.5 text-center">
                        <div className="text-gray-400">一致性</div>
                        <div className="text-primary font-medium">{ontoMetrics.consistency?.score}分</div>
                      </div>
                      <div className="bg-dark-bg rounded p-1.5 text-center">
                        <div className="text-gray-400">推理增益</div>
                        <div className="text-primary font-medium">{ontoMetrics.inference_gain?.total_inferred || 0}</div>
                      </div>
                      <div className="bg-dark-bg rounded p-1.5 text-center">
                        <div className="text-gray-400">待处理</div>
                        <div className="text-amber-400 font-medium">{ontoMetrics.maintenance_cost?.pending_suggestions || 0}</div>
                      </div>
                    </div>
                  )}
                  {/* Action buttons */}
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={() => fetchOntoMetrics(true)} className="text-[10px]">刷新指标</Button>
                    <Button variant="ghost" size="sm" onClick={generateOntoSuggestions} loading={ontoGenerating} className="text-[10px]">生成建议</Button>
                    <Button variant="ghost" size="sm" onClick={() => handleExportOwl('turtle')} className="text-[10px]" title="导出 OWL/RDF (Turtle)">📥 导出OWL</Button>
                  </div>
                  {/* Suggestions list */}
                  {ontoSuggestions.filter((s: any) => s.status === 'pending').length > 0 && (
                    <div className="space-y-1 max-h-[200px] overflow-auto">
                      <div className="text-[10px] text-gray-400 mb-1">待处理建议</div>
                      {ontoSuggestions.filter((s: any) => s.status === 'pending').slice(0, 8).map((s: any) => (
                        <div key={s.id} className="flex items-center justify-between bg-dark-bg rounded px-2 py-1 text-[10px]">
                          <div className="flex-1 min-w-0">
                            <span className="text-gray-300 truncate block">{s.description?.slice(0, 50)}</span>
                            <span className="text-gray-500">[{s.type}] 置信度 {((s.confidence || 0) * 100).toFixed(0)}% · {s.risk}</span>
                          </div>
                          <div className="flex gap-1 ml-2 flex-shrink-0">
                            <button onClick={() => handleAcceptSuggestion(s.id)} className="text-green-400 hover:text-green-300 px-1">✓</button>
                            <button onClick={() => handleRejectSuggestion(s.id)} className="text-red-400 hover:text-red-300 px-1">✗</button>
                            <button onClick={() => handleGenerateCode(s.id)} className="text-blue-400 hover:text-blue-300 px-1" title="生成代码">{'</>'}</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  {/* Code generation result */}
                  {codeGenResult && (
                    <div className="bg-gray-900 rounded p-2 max-h-[200px] overflow-auto">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] text-gray-400">生成的代码 ({codeGenResult.affected_file})</span>
                        <button onClick={() => setCodeGenResult(null)} className="text-gray-500 hover:text-gray-300 text-[10px]">关闭</button>
                      </div>
                      <pre className="text-[10px] text-green-400 whitespace-pre-wrap">{codeGenResult.code_diff}</pre>
                      <div className="text-[9px] text-gray-500 mt-1">{codeGenResult.instructions}</div>
                    </div>
                  )}
                  {/* Class usage */}
                  {ontoMetrics?.class_usage && (
                    <div className="text-[9px] text-gray-500">
                      类使用: {ontoMetrics.class_usage.map((c: any) => `${c.class}(${c.pages})`).join(' · ')}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'observe' && (
        <div className="space-y-4">
          <h2 className="text-base font-medium text-gray-200">系统观测</h2>

          {/* Metrics Overview */}
          {ontoMetrics && (
            <div className="grid grid-cols-4 gap-3">
              <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                <div className="text-xs text-gray-400">检索 P99</div>
                <div className="text-2xl font-bold text-primary">
                  {ontoMetrics.maintenance_cost?.latency?.p99
                    ? `${(ontoMetrics.maintenance_cost.latency.p99 * 1000).toFixed(0)}ms`
                    : '--'}
                </div>
                <div className="text-[10px] text-gray-500">
                  样本 {ontoMetrics.maintenance_cost?.latency?.samples || 0}
                </div>
              </div>
              <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                <div className="text-xs text-gray-400">策展成功率</div>
                <div className="text-2xl font-bold text-primary">
                  {ontoMetrics.maintenance_cost?.curation
                    ? `${ontoMetrics.maintenance_cost.curation.successes}/${(ontoMetrics.maintenance_cost.curation.successes||0) + (ontoMetrics.maintenance_cost.curation.failures||0)}`
                    : '--'}
                </div>
                <div className="text-[10px] text-gray-500">
                  重试 {ontoMetrics.maintenance_cost?.curation?.retries_total || 0} 次
                </div>
              </div>
              <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                <div className="text-xs text-gray-400">Golden 回归</div>
                <div className="text-2xl font-bold text-green-400">
                  {ontoMetrics.golden_regression?.pass_rate || '--'}%
                </div>
                <div className="text-[10px] text-gray-500">
                  {ontoMetrics.golden_regression?.passed}/{ontoMetrics.golden_regression?.total}
                </div>
              </div>
              <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                <div className="text-xs text-gray-400">模型选择</div>
                <div className="text-2xl font-bold text-primary">{modelLog.length || 0}</div>
                <div className="text-[10px] text-gray-500">最近调用</div>
              </div>
            </div>
          )}

          {/* Ontology Dimensions (5 new cards) */}
          {ontoMetrics && (
            <div className="grid grid-cols-5 gap-3">
              <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                <div className="text-xs text-gray-400">A-Box 规模</div>
                <div className="text-2xl font-bold text-emerald-400">
                  {ontoMetrics.abox_size?.total_triples ?? '--'}
                </div>
                <div className="text-[10px] text-gray-500">
                  显式 {ontoMetrics.abox_size?.explicit ?? 0} · 推理 {ontoMetrics.abox_size?.inferred ?? 0}
                </div>
              </div>
              <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                <div className="text-xs text-gray-400">Schema 合规</div>
                <div className="text-2xl font-bold text-purple-400">
                  {ontoMetrics.schema_compliance?.rate ?? '--'}%
                </div>
                <div className="text-[10px] text-gray-500">
                  {ontoMetrics.schema_compliance?.valid}/{ontoMetrics.schema_compliance?.sampled} 通过
                </div>
              </div>
              <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                <div className="text-xs text-gray-400">推理增益</div>
                <div className="text-2xl font-bold text-blue-400">
                  {ontoMetrics.inference_gain?.total_inferred ?? '--'}
                </div>
                <div className="text-[10px] text-gray-500">
                  传递 {ontoMetrics.inference_gain?.transitive_edges ?? 0} · 源链 {ontoMetrics.inference_gain?.source_chains ?? 0}
                </div>
              </div>
              <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                <div className="text-xs text-gray-400">推理有效率</div>
                <div className="text-2xl font-bold text-cyan-400">
                  {ontoMetrics.inference_effectiveness?.ratio != null
                    ? `${(ontoMetrics.inference_effectiveness.ratio * 100).toFixed(0)}%`
                    : '--'}
                </div>
                <div className="text-[10px] text-gray-500">
                  推理 {ontoMetrics.inference_effectiveness?.inferred ?? 0} / 总 {((ontoMetrics.inference_effectiveness?.explicit_edges ?? 0) + (ontoMetrics.inference_effectiveness?.inferred ?? 0))}
                </div>
              </div>
              <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                <div className="text-xs text-gray-400">本体进化</div>
                <div className="text-2xl font-bold text-amber-400">
                  {ontoMetrics.onto_evolution?.total_generations ?? '--'}
                  <span className="text-sm font-normal text-gray-500 ml-1">代</span>
                </div>
                <div className="text-[10px] text-gray-500">
                  +{ontoMetrics.onto_evolution?.classes_added ?? 0} 类 · +{ontoMetrics.onto_evolution?.properties_added ?? 0} 属性
                </div>
              </div>
            </div>
          )}

          {/* Coverage Trend */}
          {ontoMetrics?.coverage_trend && (
            <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
              <div className="flex items-center gap-3 text-xs">
                <span className="text-gray-400">覆盖率趋势</span>
                <span className="text-gray-200 font-mono">{ontoMetrics.coverage?.percentage ?? '--'}%</span>
                <span className={`${(ontoMetrics.coverage_trend.direction === 'up' || ontoMetrics.coverage_trend.direction === 'same') ? 'text-green-400' : 'text-red-400'}`}>
                  {ontoMetrics.coverage_trend.delta > 0 ? '↑' : ontoMetrics.coverage_trend.delta < 0 ? '↓' : '→'}
                  {' '}{ontoMetrics.coverage_trend.delta > 0 ? '+' : ''}{ontoMetrics.coverage_trend.delta}%
                </span>
              </div>
            </div>
          )}

          {/* Retrieval Governance Metrics */}
          {ontoMetrics?.retrieval_governance && (
            <div className="space-y-2">
              <h3 className="text-xs font-medium text-gray-400">检索治理</h3>
              <div className="grid grid-cols-4 gap-3">
                <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                  <div className="text-xs text-gray-400">治理效率</div>
                  <div className="text-2xl font-bold text-indigo-400">
                    {ontoMetrics.retrieval_governance.avg_raw_chunks} → {ontoMetrics.retrieval_governance.avg_governed_chunks}
                  </div>
                  <div className="text-[10px] text-gray-500">原始 → 治理后 (均)</div>
                </div>
                <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                  <div className="text-xs text-gray-400">过滤分布</div>
                  <div className="text-lg font-bold text-gray-200">
                    <span className="text-amber-400">{ontoMetrics.retrieval_governance.avg_time_penalized}</span>
                    <span className="text-gray-600 mx-1">/</span>
                    <span className="text-purple-400">{ontoMetrics.retrieval_governance.avg_density_filtered}</span>
                    <span className="text-gray-600 mx-1">/</span>
                    <span className="text-cyan-400">{ontoMetrics.retrieval_governance.avg_dedup_merged}</span>
                  </div>
                  <div className="text-[10px] text-gray-500">时效 · 密度 · 去重</div>
                </div>
                <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                  <div className="text-xs text-gray-400">冲突检出率</div>
                  <div className="text-2xl font-bold text-red-400">
                    {ontoMetrics.retrieval_governance.avg_conflict_marked ?? 0}
                  </div>
                  <div className="text-[10px] text-gray-500">每次平均冲突标记数</div>
                </div>
                <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                  <div className="text-xs text-gray-400">综合得分</div>
                  <div className="text-2xl font-bold text-green-400">
                    {ontoMetrics.retrieval_governance.avg_composite_score != null
                      ? (ontoMetrics.retrieval_governance.avg_composite_score * 100).toFixed(0)
                      : '--'}
                  </div>
                  <div className="text-[10px] text-gray-500">
                    截断阈值 {(ontoMetrics.retrieval_governance.avg_cutoff_score || 0).toFixed(2)}
                  </div>
                </div>
              </div>
            </div>
          )}

          {!ontoMetrics && (
            <div className="text-xs text-gray-500 text-center py-4">
              暂无观测数据，点击下方「刷新指标」获取。
            </div>
          )}

          {/* Model Selection Log */}
          {modelLog.length > 0 && (
            <div className="bg-dark-card rounded-lg border border-dark-border overflow-hidden">
              <div className="px-3 py-2 border-b border-dark-border text-xs font-medium text-gray-300">
                模型选择记录 (最近 {modelLog.length} 次)
              </div>
              <div className="divide-y divide-dark-border max-h-[300px] overflow-auto">
                {modelLog.slice(-20).reverse().map((e: any, i: number) => (
                  <div key={i} className="flex items-center px-3 py-1.5 text-xs">
                    <span className="w-24 text-gray-500">
                      {new Date(e.ts * 1000).toLocaleTimeString()}
                    </span>
                    <span className="w-28 text-gray-400">{e.purpose}</span>
                    <span className="flex-1 text-gray-200 font-mono">{e.selected}</span>
                    {e.candidates?.length > 1 && (
                      <span className="text-gray-500 text-[10px]">
                        vs {e.candidates.slice(1).map((c: any) => c.name).join(', ')}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Evolution Runner */}
          <div className="bg-dark-card rounded-lg border border-dark-border p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-gray-300">
                知识进化 {evolutionHistory.length > 0 && `(第 ${evolutionHistory.length} 代)`}
              </span>
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={fetchEvolutionHistory} className="text-[10px]">刷新</Button>
                <Button variant="primary" size="sm" onClick={handleEvolve} loading={evolving} className="text-[10px]">运行一代</Button>
              </div>
            </div>
            {evolutionHistory.length > 0 ? (
              <div className="divide-y divide-dark-border max-h-[200px] overflow-auto">
                {evolutionHistory.slice(-5).reverse().map((g: any) => (
                  <div key={g.id} className="flex items-center px-2 py-1 text-[10px]">
                    <span className="w-8 text-gray-500">#{g.id}</span>
                    <span className="w-12 text-gray-400">{g.fitness_golden_before}→{g.fitness_golden_after}</span>
                    <span className={`w-16 ${g.delta > 0 ? 'text-green-400' : g.delta < 0 ? 'text-red-400' : 'text-gray-400'}`}>
                      {g.delta > 0 ? '+' : ''}{g.delta}%
                    </span>
                    <span className="flex-1 text-gray-500">
                      {g.verdict === 'ACCEPTED' ? '✅' : g.verdict === 'REVERTED' ? '↩️' : '⏭️'} {g.verdict}
                    </span>
                    <span className="text-gray-500">{g.mutations_count} 变异</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-[10px] text-gray-500">尚未运行。使用本地 qwen2.5:7b，零 API 成本。</div>
            )}
          </div>

          {/* Quick Actions */}
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => fetchOntoMetrics(true)} className="text-xs">刷新指标</Button>
            <Button variant="ghost" size="sm" onClick={fetchModelLog} className="text-xs">刷新模型日志</Button>
          </div>
        </div>
      )}

      {activeTab === 'ontology' && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-medium text-gray-200">本体健康</h2>
            <Button variant="ghost" size="sm" onClick={() => fetchOntoMetrics(true)} className="text-xs">刷新指标</Button>
            <Button variant="ghost" size="sm" onClick={generateOntoSuggestions} loading={ontoGenerating} className="text-xs">生成建议</Button>
            <Button variant="ghost" size="sm" onClick={handleBatchAtomize} loading={batchAtomizing} className="text-xs">批量原子化</Button>
            <Button variant="ghost" size="sm" onClick={handleSeedInstances} loading={seeding} className="text-xs">种子实例</Button>
            <Button variant="ghost" size="sm" onClick={async () => {
              const r = await fetch(`${WIKI_API}/maintain/fts-rebuild?collection=${wikiCollection}`, { method: 'POST' });
              const d = await r.json();
              toast.success(`FTS5 已重建: ${d.indexed} 页`);
            }} className="text-xs">FTS索引</Button>
            {ontoMetrics && <Button variant="ghost" size="sm" onClick={() => handleExportOwl('turtle')} className="text-xs">📥 导出OWL</Button>}
          </div>

          {/* Metrics Dashboard */}
          {ontoMetrics && (
            <div className="grid grid-cols-4 gap-3">
              <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                <div className="text-xs text-gray-400">覆盖率</div>
                <div className="text-2xl font-bold text-primary">{ontoMetrics.coverage?.percentage}%</div>
                <div className="text-[10px] text-gray-500">{ontoMetrics.coverage?.covered}/{ontoMetrics.coverage?.total} 页</div>
              </div>
              <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                <div className="text-xs text-gray-400">一致性</div>
                <div className="text-2xl font-bold text-primary">{ontoMetrics.consistency?.score}分</div>
                <div className="text-[10px] text-gray-500">错误 {ontoMetrics.consistency?.errors} · 警告 {ontoMetrics.consistency?.warnings}</div>
              </div>
              <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                <div className="text-xs text-gray-400">推理增益</div>
                <div className="text-2xl font-bold text-primary">{ontoMetrics.inference_gain?.total_inferred || 0}</div>
                <div className="text-[10px] text-gray-500">{ontoMetrics.inference_gain?.transitive_edges || 0}传递 · {ontoMetrics.inference_gain?.source_chains || 0}来源链</div>
              </div>
              <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                <div className="text-xs text-gray-400">待处理</div>
                <div className="text-2xl font-bold text-amber-400">{ontoMetrics.maintenance_cost?.pending_suggestions || 0}</div>
                <div className="text-[10px] text-gray-500">最后审查: {ontoMetrics.maintenance_cost?.last_review?.slice(0, 10) || '从未'}</div>
              </div>
              {ontoMetrics.maintenance_cost?.curation && (
                <div className="bg-dark-card rounded-lg p-3 border border-dark-border">
                  <div className="text-xs text-gray-400">策展成功率</div>
                  <div className="text-2xl font-bold text-primary">
                    {ontoMetrics.maintenance_cost.curation.successes}/
                    {(ontoMetrics.maintenance_cost.curation.successes || 0) + 
                     (ontoMetrics.maintenance_cost.curation.failures || 0)}
                  </div>
                  <div className="text-[10px] text-gray-500">
                    重试 {ontoMetrics.maintenance_cost.curation.retries_total || 0} 次
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Class Usage Table */}
          {ontoMetrics?.class_usage && (
            <div className="bg-dark-card rounded-lg border border-dark-border overflow-hidden">
              <div className="px-3 py-2 border-b border-dark-border text-xs font-medium text-gray-300">类使用分布</div>
              <div className="divide-y divide-dark-border">
                {ontoMetrics.class_usage.map((c: any) => (
                  <div key={c.class} className="flex items-center px-3 py-1.5 text-xs">
                    <span className="w-32 text-gray-300">{c.class}</span>
                    <span className="w-16 text-gray-500">{c.categories?.join(', ')}</span>
                    <div className="flex-1 mx-2 bg-dark-bg rounded h-3 overflow-hidden">
                      <div className="bg-primary h-full rounded" style={{ width: `${Math.min(100, c.pages * 5)}%` }} />
                    </div>
                    <span className="w-8 text-right text-gray-400">{c.pages}页</span>
                  </div>
                ))}
               </div>
            </div>
          )}

          {/* T-Box Structure Tree */}
          {ontoClasses.length > 0 && (
            <div className="bg-dark-card rounded-lg border border-dark-border overflow-hidden">
              <button onClick={() => setOntoTreeOpen(!ontoTreeOpen)}
                className="w-full px-3 py-2 flex items-center gap-2 text-xs text-gray-400 hover:text-gray-200 border-b border-dark-border">
                <span>{ontoTreeOpen ? '▼' : '▶'}</span>
                T-Box 结构 ({ontoClasses.length} 类)
                <span className="text-gray-600 ml-2">
                  {ontoClasses.filter((c: any) => c.children?.length > 0).length} 层级 · 
                  {ontoClasses.filter((c: any) => c.categories?.length > 0).length} 映射
                </span>
              </button>
              {ontoTreeOpen && (
                <div className="p-2 text-xs font-mono space-y-0.5 max-h-[500px] overflow-auto">
                  {ontoClasses
                    .filter((c: any) => !c.parent) // Roots first
                    .map((root: any) => (
                      <div key={root.uri} className="text-gray-300">
                        <span className="text-primary">{root.label}</span>
                        <span className="text-gray-600 ml-1">
                          {root.children?.length > 0 ? `(${root.children.length} 子类)` : ''}
                          {root.categories?.length > 0 ? ` [${root.categories.join(', ')}]` : ''}
                        </span>
                        {/* Render children recursively */}
                        {root.children?.length > 0 && (
                          <div className="ml-4 border-l border-dark-border pl-2">
                            {root.children.map((childName: string) => {
                              const child = ontoClasses.find((c: any) => c.label === childName);
                              if (!child) return null;
                              return (
                                <div key={child.uri} className="text-gray-400">
                                  <span className={child.categories?.length > 0 ? 'text-amber-300' : 'text-gray-400'}>
                                    {child.label}
                                  </span>
                                  {child.categories?.length > 0 && (
                                    <span className="text-gray-600 ml-1">[{child.categories.join(', ')}]</span>
                                  )}
                                  {child.required_fields?.length > 0 && (
                                    <span className="text-green-600 ml-1 text-[10px]">
                                      req: {child.required_fields.join(', ')}
                                    </span>
                                  )}
                                  {/* Grandchildren */}
                                  {child.children?.length > 0 && (
                                    <div className="ml-4 border-l border-dark-border pl-2">
                                      {child.children.map((gcName: string) => {
                                        const gc = ontoClasses.find((c: any) => c.label === gcName);
                                        if (!gc) return null;
                                        return (
                                          <div key={gc.uri} className="text-gray-500">
                                            <span className={gc.categories?.length > 0 ? 'text-amber-400' : 'text-gray-500'}>
                                              {gc.label}
                                            </span>
                                            {gc.categories?.length > 0 && (
                                              <span className="text-gray-600 ml-1">[{gc.categories.join(', ')}]</span>
                                            )}
                                            {gc.required_fields?.length > 0 && (
                                              <span className="text-green-700 ml-1 text-[9px]">
                                                req: {gc.required_fields.join(', ')}
                                              </span>
                                            )}
                                          </div>
                                        );
                                      })}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    ))}
                  {/* Axioms summary */}
                  <div className="mt-2 pt-2 border-t border-dark-border">
                    <span className="text-gray-500 text-[10px]">
                      对象属性: 15 · 数据属性: 18 · 公理: A1-A7 · 标准映射: SKOS/DC/PROV-O/CIDOC-CRM/FOAF
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* History Trend */}
          {metricsHistory.length >= 2 && (
            <div className="bg-dark-card rounded-lg border border-dark-border p-3">
              <div className="text-xs font-medium text-gray-300 mb-2">一致性趋势 (最近 {metricsHistory.length} 次)</div>
              <div className="flex items-end gap-1 h-16">
                {metricsHistory.map((h: any, i: number) => (
                  <div key={i} className="flex-1 flex flex-col items-center" title={`${new Date(h.ts*1000).toLocaleDateString()}: ${h.score}分`}>
                    <div className="w-full bg-primary/30 rounded-t" style={{ height: `${h.score}%` }}>
                      <div className="w-full bg-primary rounded-t" style={{ height: `${h.score}%` }} />
                    </div>
                    <span className="text-[8px] text-gray-500 mt-0.5">{h.score}</span>
                  </div>
                ))}
              </div>
              <div className="flex justify-between text-[8px] text-gray-500 mt-1">
                <span>{metricsHistory[0] ? new Date(metricsHistory[0].ts * 1000).toLocaleDateString() : ''}</span>
                <span>{metricsHistory[metricsHistory.length - 1] ? new Date(metricsHistory[metricsHistory.length - 1].ts * 1000).toLocaleDateString() : ''}</span>
              </div>
            </div>
           )}

          {/* Golden Query Regression */}
          {goldenResults && (
            <div className="bg-dark-card rounded-lg border border-dark-border p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-gray-300">
                  黄金问题回归: <span className={
                    (goldenResults.pass_rate || 0) < 75 ? 'text-red-400' :
                    (goldenResults.pass_rate || 0) < 90 ? 'text-amber-400' : 'text-green-400'
                  }>{goldenResults.passed}/{goldenResults.total} ({goldenResults.pass_rate}%)</span>
                  {ontoMetrics?.golden_regression?.alert && (
                    <span className="ml-2 text-[10px] text-red-400">⚠️ {ontoMetrics.golden_regression.alert}</span>
                  )}
                </span>
                <Button variant="ghost" size="sm" onClick={fetchGoldenRegression} className="text-[10px]">刷新</Button>
              </div>
              <div className="space-y-0.5 max-h-40 overflow-auto">
                {goldenResults.per_query?.map((q: any) => (
                  <div key={q.query} className="flex items-center gap-2 text-[10px]">
                    <span className={q.passed ? 'text-green-400' : 'text-red-400'}>
                      {q.passed ? '✓' : '✗'}
                    </span>
                    <span className="text-gray-400 w-36 truncate">{q.query}</span>
                    {q.missing?.length > 0 && (
                      <span className="text-amber-400 text-[9px]">缺: {q.missing.join(', ')}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
           )}

          {/* Cross-page Contradiction Candidates */}
          {patterns?.cross_page_contradictions?.length > 0 && (
            <div className="bg-dark-card rounded-lg border border-dark-border p-3">
              <div className="text-xs font-medium text-gray-300 mb-1">
                跨页面矛盾候选 ({patterns.cross_page_contradictions.length})
              </div>
              <div className="space-y-0.5 max-h-32 overflow-auto">
                {patterns.cross_page_contradictions.slice(0, 10).map((c: any, i: number) => (
                  <div key={i} className="text-[10px] text-amber-400/80 flex items-center gap-1">
                    <span className="truncate max-w-[120px]">{c.page_a?.slice(0, 25)}</span>
                    <span className="text-gray-500">↔</span>
                    <span className="truncate max-w-[120px]">{c.page_b?.slice(0, 25)}</span>
                    <span className="text-gray-500 ml-1 text-[9px]">[{c.shared_tags?.join(', ')}]</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Suggestions List */}
          {ontoSuggestions.filter((s: any) => s.status === 'pending').length > 0 && (
            <div className="bg-dark-card rounded-lg border border-dark-border overflow-hidden">
              <div className="px-3 py-2 border-b border-dark-border text-xs font-medium text-gray-300 flex items-center justify-between">
                <span>待处理建议 ({ontoSuggestions.filter((s: any) => s.status === 'pending').length})</span>
              </div>
              <div className="divide-y divide-dark-border max-h-[400px] overflow-auto">
                {ontoSuggestions.filter((s: any) => s.status === 'pending').slice(0, 20).map((s: any) => (
                  <div key={s.id} className="flex items-center justify-between px-3 py-2 text-xs">
                    <div className="flex-1 min-w-0">
                      <div className="text-gray-300 truncate">{s.description?.slice(0, 80)}</div>
                      <div className="text-gray-500">[{s.type}] 置信 {((s.confidence || 0) * 100).toFixed(0)}% · {s.risk}</div>
                    </div>
                    <div className="flex gap-1 ml-2 flex-shrink-0">
                      <button onClick={() => handleAcceptSuggestion(s.id)} className="text-green-400 hover:text-green-300 px-1.5 py-0.5 rounded hover:bg-green-900/20">接受</button>
                      <button onClick={() => handleRejectSuggestion(s.id)} className="text-red-400 hover:text-red-300 px-1.5 py-0.5 rounded hover:bg-red-900/20">拒绝</button>
                      <button onClick={() => handleGenerateCode(s.id)} className="text-blue-400 hover:text-blue-300 px-1.5 py-0.5 rounded hover:bg-blue-900/20">代码</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Code Gen Result */}
          {codeGenResult && (
            <div className="bg-gray-900 border border-dark-border rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-400">生成代码 · {codeGenResult.affected_file}</span>
                <button onClick={() => setCodeGenResult(null)} className="text-gray-500 hover:text-gray-300 text-xs">关闭</button>
              </div>
              <pre className="text-xs text-green-400 whitespace-pre-wrap max-h-[300px] overflow-auto bg-gray-950 p-2 rounded">{codeGenResult.code_diff}</pre>
              <div className="text-[10px] text-gray-500 mt-2 whitespace-pre-wrap">{codeGenResult.instructions}</div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'health' && (
        <>
          <WikiHealthDashboard />
          <Card className="mt-4">
          <CardHeader><div className="text-sm font-medium flex items-center justify-between">
            <span><AlertTriangle className="w-3 h-3 inline mr-1" />知识库健康检查</span>
            {lintResult && (
              <span className={`text-xs px-2 py-0.5 rounded font-semibold ${
                lintResult.health_score >= 90 ? 'bg-green-900/50 text-green-300' :
                lintResult.health_score >= 70 ? 'bg-yellow-900/50 text-yellow-300' :
                'bg-red-900/50 text-red-300'
              }`}>得分: {lintResult.health_score}</span>
            )}
          </div></CardHeader>
          <CardContent className="space-y-4">
            <Button variant="primary" size="sm" onClick={runLint} loading={lintLoading}>执行健康检查</Button>
            
            {lintResult && lintResult.checks && (
              <div className="space-y-3">
                {/* Check summary */}
                <div className="text-xs font-semibold text-gray-300 mb-1">检查项</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {lintResult.checks.map((chk: any, idx: number) => (
                    <div key={idx} className={`p-2 rounded border text-xs ${
                      chk.pass ? 'border-green-900/40 bg-green-900/10' : 'border-yellow-900/40 bg-yellow-900/10'
                    }`}>
                      <div className="flex items-center gap-1.5">
                        <span className={chk.pass ? 'text-green-400' : 'text-yellow-400'}>
                          {chk.pass ? '✓' : '!'}
                        </span>
                        <span className="text-gray-300">{chk.name}</span>
                      </div>
                      <div className={`ml-4 text-[10px] ${chk.pass ? 'text-green-500' : 'text-yellow-500'}`}>
                        {chk.pass ? '通过' : `${chk.count} 个问题`}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Stats summary */}
                {lintResult.stats && (
                  <>
                    <div className="text-xs font-semibold text-gray-300 mt-4 mb-1">统计摘要</div>
                    <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
                      <div className="p-2 rounded bg-dark-bg text-center">
                        <div className="text-lg font-semibold text-gray-200">{lintResult.total_pages}</div>
                        <div className="text-[10px] text-gray-500">总页面</div>
                      </div>
                      <div className="p-2 rounded bg-dark-bg text-center">
                        <div className="text-lg font-semibold text-gray-200">{lintResult.stats.pages_with_body}</div>
                        <div className="text-[10px] text-gray-500">有内容</div>
                      </div>
                      <div className="p-2 rounded bg-dark-bg text-center">
                        <div className="text-lg font-semibold text-gray-200">{lintResult.stats.total_links}</div>
                        <div className="text-[10px] text-gray-500">总链接</div>
                      </div>
                      <div className="p-2 rounded bg-dark-bg text-center">
                        <div className="text-lg font-semibold text-gray-200">{lintResult.stats.avg_links_per_page}</div>
                        <div className="text-[10px] text-gray-500">平均链接</div>
                      </div>
                      <div className="p-2 rounded bg-dark-bg text-center">
                        <div className="text-lg font-semibold text-gray-200">{lintResult.stats.orphan_pages}</div>
                        <div className="text-[10px] text-gray-500">孤立页面</div>
                      </div>
                      <div className="p-2 rounded bg-dark-bg text-center">
                        <div className="text-lg font-semibold text-gray-200">{lintResult.stats.dead_links}</div>
                        <div className="text-[10px] text-gray-500">死链</div>
                      </div>
                    </div>

                    {/* Categories */}
                    {lintResult.stats.categories && (
                      <div className="flex gap-2 flex-wrap">
                        {Object.entries(lintResult.stats.categories).map(([cat, count]: any) => (
                          <span key={cat} className="text-[10px] px-2 py-0.5 rounded-full bg-dark-hover text-gray-400">
                            {cat}: {count}
                          </span>
                        ))}
                      </div>
                    )}
                  </>
                )}

                {/* Issues detail */}
                {lintResult.issues && lintResult.issues.length > 0 && (
                  <>
                    <div className="text-xs font-semibold text-gray-300 mt-4 mb-1">
                      详细问题 ({lintResult.issues.length})
                    </div>
                    <div className="space-y-1 max-h-64 overflow-y-auto">
                      {lintResult.issues.map((issue: any, idx: number) => (
                        <div key={idx} className={`flex items-start gap-2 text-xs p-2 rounded ${
                          issue.severity === 'high' ? 'bg-red-900/10 border border-red-900/30' :
                          issue.severity === 'medium' ? 'bg-yellow-900/10 border border-yellow-900/30' :
                          'bg-dark-bg'
                        }`}>
                          <span className={`shrink-0 mt-0.5 ${
                            issue.severity === 'high' ? 'text-red-400' :
                            issue.severity === 'medium' ? 'text-yellow-400' :
                            'text-gray-500'
                          }`}>
                            [{issue.check_type}]
                          </span>
                          <div className="min-w-0">
                            <span className="text-gray-300">{issue.description}</span>
                            <div className="text-gray-500 truncate">
                              {issue.page_a}{issue.page_b ? ` ↔ ${issue.page_b}` : ''}
                            </div>
                            {issue.suggestion && <div className="text-blue-400 mt-0.5">建议: {issue.suggestion}</div>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </>
                )}

                {lintResult.issues && lintResult.issues.length === 0 && lintResult.total_pages > 0 && (
                  <div className="text-xs text-green-400 mt-2">✅ 知识库健康，无问题</div>
          )}
            </div>
          )}

            {/* Knowledge proposals */}
            <div className="border-t border-dark-border pt-3 mt-2">
              <div className="flex items-center justify-between mb-2">
                <div className="text-xs font-semibold text-gray-300">📋 待审批提案</div>
                <Button variant="ghost" size="sm" onClick={fetchProposals} loading={proposalsLoading} className="text-xs">刷新</Button>
              </div>
              {proposals.filter((p: any) => p.status === 'pending').length > 0 ? (
                <div className="space-y-2">
                  {proposals.filter((p: any) => p.status === 'pending').map((p: any) => (
                    <div key={p.id} className="flex items-start gap-2 text-xs p-2 rounded bg-dark-bg border border-dark-border">
                      <span className={`shrink-0 px-1 py-0.5 rounded text-[10px] ${
                        p.action === 'merge' ? 'bg-purple-900/50 text-purple-300' :
                        p.action === 'contradict' ? 'bg-red-900/50 text-red-300' :
                        'bg-blue-900/50 text-blue-300'
                      }`}>{p.action}</span>
                      <div className="flex-1 min-w-0">
                        <div className="text-gray-300">
                          {p.action === 'merge' && <span>合并 "{p.from_title?.slice(0,20)}..." → "{p.to_title?.slice(0,20)}..."</span>}
                          {p.action === 'contradict' && <span>标记矛盾 "{p.from_title?.slice(0,20)}..." ↔ "{p.to_title?.slice(0,20)}..."</span>}
                        </div>
                        {p.reason && <div className="text-gray-500 mt-0.5">{p.reason.slice(0, 80)}</div>}
                      </div>
                      <div className="flex gap-1 shrink-0">
                        <Button variant="primary" size="sm" onClick={() => handleApproveProposal(p.id)} className="text-xs">批准</Button>
                        <Button variant="ghost" size="sm" onClick={() => handleRejectProposal(p.id)} className="text-xs">拒绝</Button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-xs text-gray-500">暂无待审批提案</div>
              )}
            </div>

            {/* Health Trend */}
            {healthTrend?.history && healthTrend.history.length > 0 && (
              <div className="mt-4 p-3 rounded bg-dark-bg border border-dark-border">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-gray-300">
                    健康趋势 (最近 {healthTrend.history.length} 次)
                  </span>
                  {healthTrend.trend && (
                    <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                      healthTrend.trend.direction === '↑' ? 'bg-green-900/30 text-green-300' :
                      healthTrend.trend.direction === '↓' ? 'bg-red-900/30 text-red-300' :
                      'bg-dark-hover text-gray-400'
                    }`}>
                      {healthTrend.trend.direction} {healthTrend.trend.score_delta > 0 ? '+' : ''}{healthTrend.trend.score_delta}
                    </span>
                  )}
                </div>
                <div className="flex items-end gap-1 h-16">
                  {healthTrend.history.map((snap: any, i: number) => {
                    const h = Math.max(4, (snap.score / 100) * 60);
                    const color = snap.score >= 90 ? 'bg-green-500' : snap.score >= 70 ? 'bg-yellow-500' : 'bg-red-500';
                    return (
                      <div key={i} className="flex-1 flex flex-col items-center group relative" title={`${snap.score}分 · ${snap.grade} · ${new Date(snap.ts * 1000).toLocaleDateString()}`}>
                        <div className={`w-full rounded-t ${color}`} style={{ height: `${h}px` }} />
                        <span className="text-[8px] text-gray-600 mt-0.5">{snap.score}</span>
                      </div>
                    );
                  })}
                </div>
                {healthTrend.best && (
                  <div className="text-[10px] text-gray-500 mt-1">
                    历史最高: {healthTrend.best.score} 分 ({new Date(healthTrend.best.ts * 1000).toLocaleDateString()})
                  </div>
                )}
              </div>
            )}

            {!lintResult && <div className="text-xs text-gray-500">点击上方按钮运行健康检查</div>}
          </CardContent>
        </Card>
        </>
      )}

      <UploadModal open={uploadModalOpen} onClose={() => setUploadModalOpen(false)} onComplete={handleUploadComplete} />
    </div>
  );
};

export default KnowledgeBasePage;
