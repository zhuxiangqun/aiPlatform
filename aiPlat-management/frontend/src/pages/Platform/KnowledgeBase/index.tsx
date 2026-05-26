import React, { useEffect, useState } from 'react';
import { Button, Card, CardContent, CardHeader, Input, Textarea, toast } from '../../../components/ui';
import { BookOpen, Plus, AlertTriangle, RefreshCw, Database } from 'lucide-react';
import { useKBStore } from '../../../stores';
import { kbApi } from '../../../services';
import { DocumentGrid } from './DocumentGrid';
import { UploadModal } from './UploadModal';
import { ChatPanel } from './ChatPanel';

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
  const [showChat, setShowChat] = useState(false);

  // Wiki states
  const [wikiPages, setWikiPages] = useState<any[]>([]);
  const [wikiQuery, setWikiQuery] = useState('');
  const [wikiCategory, setWikiCategory] = useState('');
  const [wikiLoading, setWikiLoading] = useState(false);
  const [selectedPage, setSelectedPage] = useState<any>(null);
  const [wikiNewTitle, setWikiNewTitle] = useState('');
  const [wikiNewBody, setWikiNewBody] = useState('');
  const [wikiNewTags, setWikiNewTags] = useState('');
  const [wikiNewCategory, setWikiNewCategory] = useState('entities');
  const [convertResult, setConvertResult] = useState<any>(null);
  const [converting, setConverting] = useState(false);
  const [lintResult, setLintResult] = useState<any>(null);
  const [lintLoading, setLintLoading] = useState(false);

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
  }, [activeCategory]);

  const handleUploadComplete = async () => {
    setUploadModalOpen(false);
    await fetchDocuments(undefined, activeCategory);
    await fetchCategories();
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
    else if (activeTab === 'wiki') fetchWikiPages();
    else if (activeTab === 'health') runLint();
  }, [activeTab]);

  // ── Wiki functions ──
  const fetchWikiPages = async () => {
    setWikiLoading(true);
    try {
      let url = `${WIKI_API}/pages?limit=100`;
      if (wikiQuery) url += `&query=${encodeURIComponent(wikiQuery)}`;
      if (wikiCategory) url += `&category=${encodeURIComponent(wikiCategory)}`;
      const res = await fetch(url); setWikiPages((await res.json()).items || []);
    } catch {} finally { setWikiLoading(false); }
  };
  const readWikiPage = async (title: string) => {
    try { const res = await fetch(`${WIKI_API}/pages/${encodeURIComponent(title)}`); setSelectedPage(await res.json()); } catch {}
  };
  const handleWikiCreate = async () => {
    if (!wikiNewTitle.trim() || !wikiNewBody.trim()) return;
    try {
      await fetch(`${WIKI_API}/pages`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: wikiNewTitle, body: wikiNewBody, category: wikiNewCategory, tags: wikiNewTags.split(',').map((s: string) => s.trim()).filter(Boolean), summary: wikiNewBody.slice(0, 200) }) });
      toast.success('页面已创建'); setWikiNewTitle(''); setWikiNewBody(''); setWikiNewTags(''); fetchWikiPages();
    } catch { toast.error('创建失败'); }
  };
  const handleConvertKb = async () => {
    setConverting(true);
    try { const res = await fetch(`${WIKI_API}/convert-from-kb`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tenant_id: 'default', limit: 50 }) });
      const data = await res.json(); setConvertResult(data); toast.success(`${data.created} 文档 → Wiki 页面`); fetchWikiPages(); } catch {} finally { setConverting(false); }
  };
  const runLint = async () => {
    setLintLoading(true);
    try { const res = await fetch(`${WIKI_API}/lint`); setLintResult(await res.json()); } catch {} finally { setLintLoading(false); }
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
            {(['documents', '编缉知识', '健康', '评估'] as const).map((label) => {
              const k = label === '评估' ? 'eval' : label === '编缉知识' ? 'wiki' : label === '健康' ? 'health' : 'documents';
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
          <Button variant="primary" size="sm" onClick={() => setUploadModalOpen(true)}>上传资料</Button>
        </div>
      </div>

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

          <div className="flex gap-3">
            <div className="flex-1 min-w-0">
              <DocumentGrid documents={documents} loading={loading} total={totalDocuments} selectedDocIds={selectedDocIds} />
            </div>

            {showChat && (
              <div className="w-[420px] flex-shrink-0 bg-dark-card rounded-lg border border-dark-border overflow-hidden" style={{ height: 'calc(100vh - 160px)', position: 'sticky', top: '1rem' }}>
                <ChatPanel onClose={() => setShowChat(false)} />
              </div>
            )}
          </div>

          {!showChat && selectedDocIds.size > 0 && (
            <div className="fixed bottom-4 right-4 z-40">
              <button onClick={() => setShowChat(true)}
                className="flex items-center gap-1.5 px-3 py-2 bg-primary text-white rounded-full shadow-lg text-sm hover:bg-primary/90 transition-colors">
                <span>💬</span> AI 资料助手
              </button>
            </div>
          )}
          {showChat && (
            <button onClick={() => setShowChat(false)}
              className="fixed bottom-4 right-4 z-40 w-8 h-8 bg-dark-card border border-dark-border rounded-full text-sm text-gray-400 hover:text-gray-200 flex items-center justify-center shadow-lg">&times;</button>
          )}
        </>
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
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="md:col-span-1 space-y-3">
            <Card>
              <CardHeader><div className="text-sm font-medium">Wiki 编缉知识</div></CardHeader>
              <CardContent className="space-y-2">
                <Input placeholder="搜索标题..." value={wikiQuery} onChange={e => setWikiQuery(e.target.value)} />
                <select value={wikiCategory} onChange={e => setWikiCategory(e.target.value)}
                  className="w-full h-8 px-2 bg-dark-card border border-dark-border rounded text-xs text-gray-300">
                  <option value="">全部分类</option>
                  <option value="entities">实体</option>
                  <option value="topics">主题</option>
                </select>
                <Button variant="secondary" size="sm" onClick={fetchWikiPages} loading={wikiLoading} className="w-full"><RefreshCw className="w-3 h-3 mr-1" />刷新</Button>
                <Button variant="primary" size="sm" onClick={handleConvertKb} loading={converting} className="w-full"><Database className="w-3 h-3 mr-1" />从文档导入</Button>
                {convertResult && <div className="text-xs text-gray-400">{convertResult.message}</div>}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><div className="text-sm font-medium"><Plus className="w-3 h-3 inline mr-1" />新建页面</div></CardHeader>
              <CardContent className="space-y-2">
                <Input placeholder="标题" value={wikiNewTitle} onChange={e => setWikiNewTitle(e.target.value)} />
                <select value={wikiNewCategory} onChange={e => setWikiNewCategory(e.target.value)} className="w-full h-8 px-2 bg-dark-card border border-dark-border rounded text-xs text-gray-300">
                  <option value="entities">实体</option><option value="topics">主题</option>
                </select>
                <Input placeholder="标签 (逗号分隔)" value={wikiNewTags} onChange={e => setWikiNewTags(e.target.value)} />
                <Textarea rows={4} placeholder="Markdown 正文" value={wikiNewBody} onChange={e => setWikiNewBody(e.target.value)} />
                <Button variant="primary" size="sm" onClick={handleWikiCreate} className="w-full">创建页面</Button>
              </CardContent>
            </Card>
          </div>
          <div className="md:col-span-3">
            <div className="text-xs text-gray-500 mb-2">{wikiPages.length} 个页面</div>
            <div className="space-y-2">
              {wikiPages.map((p: any) => (
                <div key={p.title} onClick={() => readWikiPage(p.title)} className="p-3 rounded-lg border border-dark-border bg-dark-card cursor-pointer hover:border-gray-600">
                  <div className="flex items-center gap-2 mb-1">
                    <BookOpen className="w-3 h-3 text-gray-400" />
                    <span className="text-sm font-medium text-gray-200">{p.title}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${sourceBadge(p.category)}`}>{p.category}</span>
                  </div>
                  {p.summary && <div className="text-xs text-gray-500 line-clamp-1">{p.summary}</div>}
                  <div className="flex gap-2 mt-1">{(p.tags || []).slice(0,3).map((t:string) => <span key={t} className="text-[10px] text-gray-600 bg-dark-bg px-1 rounded">{t}</span>)}
                    {p.contradictions?.length > 0 && <span className="text-[10px] text-red-400"><AlertTriangle className="w-2 h-2 inline mr-0.5" />{p.contradictions.length}</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'health' && (
        <Card>
          <CardHeader><div className="text-sm font-medium flex items-center justify-between">
            <span><AlertTriangle className="w-3 h-3 inline mr-1" />知识库健康检查</span>
            {lintResult && <span className={`text-xs px-2 py-0.5 rounded ${lintResult.health_score >= 80 ? 'bg-green-900/50 text-green-300' : 'bg-yellow-900/50 text-yellow-300'}`}>得分: {lintResult.health_score}</span>}
          </div></CardHeader>
          <CardContent className="space-y-2">
            <Button variant="primary" size="sm" onClick={runLint} loading={lintLoading}>执行健康检查</Button>
            {lintResult && lintResult.issues && (
              <div className="space-y-1 mt-3">
                {lintResult.issues.map((issue: any, idx: number) => (
                  <div key={idx} className="flex items-start gap-2 text-xs p-2 bg-dark-bg rounded">
                    <AlertTriangle className="w-3 h-3 text-yellow-400 shrink-0 mt-0.5" />
                    <div><span className="text-gray-300">[{issue.type}] {issue.page_a}</span>
                      {issue.page_b && <span className="text-gray-500"> ↔ {issue.page_b}</span>}
                      {issue.suggestion && <div className="text-blue-400">建议: {issue.suggestion}</div>}
                      {issue.description && <div className="text-gray-500">{issue.description}</div>}
                    </div>
                  </div>
                ))}
                {lintResult.issues.length === 0 && <div className="text-xs text-green-400">✅ 知识库健康，无问题</div>}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {selectedPage && activeTab === 'wiki' && (
        <Card>
          <CardHeader><div className="text-sm font-medium flex items-center justify-between"><span>{selectedPage.title}</span><button onClick={() => setSelectedPage(null)} className="text-gray-500 hover:text-gray-300 text-xs">关闭</button></div></CardHeader>
          <CardContent><pre className="text-xs text-gray-300 whitespace-pre-wrap bg-dark-bg p-3 rounded max-h-96 overflow-auto">{selectedPage.body || '(无正文)'}</pre></CardContent>
        </Card>
      )}

      <UploadModal open={uploadModalOpen} onClose={() => setUploadModalOpen(false)} onComplete={handleUploadComplete} />
    </div>
  );
};

export default KnowledgeBasePage;
