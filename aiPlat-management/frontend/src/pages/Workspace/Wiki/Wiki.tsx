import React, { useEffect, useState } from 'react';
import { Button, Card, CardContent, CardHeader, Input, Textarea, toast } from '../../../components/ui';
import { Search, BookOpen, Plus, AlertTriangle, RefreshCw, Database } from 'lucide-react';

type TabKey = 'browse' | 'ingest' | 'query' | 'lint';
type WikiPage = { title: string; category: string; tags: string[]; summary: string; related: string[]; contradictions: string[]; last_updated: string; path: string };

const API = '/api/core/wiki';

const WikiPage: React.FC = () => {
  const [tab, setTab] = useState<TabKey>('browse');
  const [pages, setPages] = useState<WikiPage[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');
  const [selectedPage, setSelectedPage] = useState<any>(null);

  // Ingest state
  const [ingestText, setIngestText] = useState('');
  const [ingestTitle, setIngestTitle] = useState('');
  const [ingesting, setIngesting] = useState(false);

  // Query state
  const [wikiQuestion, setWikiQuestion] = useState('');
  const [wikiAnswer, setWikiAnswer] = useState('');
  const [querying, setQuerying] = useState(false);

  // Lint state
  const [lintResult, setLintResult] = useState<any>(null);

  // KB → Wiki conversion
  const [converting, setConverting] = useState(false);
  const [convertResult, setConvertResult] = useState<any>(null);

  // Create page state
  const [newTitle, setNewTitle] = useState('');
  const [newBody, setNewBody] = useState('');
  const [newTags, setNewTags] = useState('');
  const [newCategory, setNewCategory] = useState('entities');

  const fetchPages = async () => {
    setLoading(true);
    try {
      let url = `${API}/pages?limit=100`;
      if (query) url += `&query=${encodeURIComponent(query)}`;
      if (category) url += `&category=${encodeURIComponent(category)}`;
      const res = await fetch(url);
      const data = await res.json();
      setPages(data.items || []);
    } catch {}
    finally { setLoading(false); }
  };

  const readPage = async (title: string) => {
    try {
      const res = await fetch(`${API}/pages/${encodeURIComponent(title)}`);
      const data = await res.json();
      setSelectedPage(data);
    } catch { toast.error('读取页面失败'); }
  };

  const handleIngest = async () => {
    if (!ingestText.trim()) return;
    setIngesting(true);
    try {
      const res = await fetch(`${API}/ingest`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_text: ingestText, source_title: ingestTitle }),
      });
      const data = await res.json();
      toast.success(`文本已摄入 (${data.source_id})。请执行 wiki_curator Agent 更新 Wiki 页面。`);
      setIngestText(''); setIngestTitle('');
    } catch { toast.error('摄入失败'); }
    finally { setIngesting(false); }
  };

  const handleQuery = async () => {
    if (!wikiQuestion.trim()) return;
    setQuerying(true); setWikiAnswer('');
    try {
      const res = await fetch(`${API}/pages?query=${encodeURIComponent(wikiQuestion)}&limit=5`);
      const data = await res.json();
      const items = data.items || [];
      if (items.length === 0) { setWikiAnswer('Wiki 中未找到相关内容。'); return; }

      // Traverse links from top results
      const allPages: string[] = [];
      for (const item of items.slice(0, 3)) {
        allPages.push(`### ${item.title} [${item.category}]\n${item.summary || ''}\nTags: ${(item.tags || []).join(', ')}\nRelated: ${(item.related || []).join(', ')}`);
      }
      setWikiAnswer(allPages.join('\n\n'));
      // Also return the first page for detail view
      if (items[0]) readPage(items[0].title);
    } catch { toast.error('查询失败'); }
    finally { setQuerying(false); }
  };

  const handleLint = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/lint`);
      const data = await res.json();
      setLintResult(data);
      toast.success(`发现 ${data.total} 个问题`);
    } catch { toast.error('Lint 失败'); }
    finally { setLoading(false); }
  };

  const handleCreate = async () => {
    if (!newTitle.trim() || !newBody.trim()) return;
    try {
      await fetch(`${API}/pages`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: newTitle, body: newBody,
          category: newCategory,
          tags: newTags.split(',').map((s: string) => s.trim()).filter(Boolean),
          summary: newBody.slice(0, 200),
        }),
      });
      toast.success('页面已创建');
      setNewTitle(''); setNewBody(''); setNewTags('');
      fetchPages();
    } catch { toast.error('创建失败'); }
  };

  const handleConvertKb = async () => {
    setConverting(true); setConvertResult(null);
    try {
      const res = await fetch(`${API}/convert-from-kb`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tenant_id: 'default', limit: 50 }) });
      const data = await res.json();
      setConvertResult(data);
      toast.success(`已转换 ${data.created} 个文档 → Wiki 页面`);
      fetchPages();
    } catch { toast.error('转换失败'); }
    finally { setConverting(false); }
  };

  useEffect(() => { if (tab === 'browse') fetchPages(); }, [tab, query, category]);

  const sourceBadge = (cat: string) => {
    const colors: Record<string, string> = { entities: 'bg-blue-50 text-blue-300', topics: 'bg-purple-50 text-purple-300', contradictions: 'bg-red-50 text-red-300' };
    return colors[cat] || 'bg-dark-hover text-gray-300';
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-100">📖 Wiki 知识库</h1>
          <p className="text-xs text-gray-500 mt-1">持久化 LLM 编缉知识库 — ~/.aiplat/wiki/</p>
        </div>
        <div className="flex gap-1">
          {(['browse', 'ingest', 'query', 'lint'] as TabKey[]).map(k => (
            <button key={k} onClick={() => setTab(k)}
              className={`px-3 py-1 rounded text-xs ${tab === k ? 'bg-primary/20 text-primary' : 'text-gray-400 hover:text-gray-200'}`}>
              {{browse:'浏览', ingest:'摄入', query:'问答', lint:'健康'}[k]}
            </button>
          ))}
        </div>
      </div>

      {/* Browse Tab */}
      {tab === 'browse' && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-1 space-y-3">
            <Card>
              <CardHeader><div className="text-sm font-medium">搜索与筛选</div></CardHeader>
              <CardContent className="space-y-2">
                <Input placeholder="搜索标题..." value={query} onChange={e => setQuery(e.target.value)} />
                <select value={category} onChange={e => setCategory(e.target.value)}
                  className="w-full h-8 px-2 bg-dark-card border border-dark-border rounded text-xs text-gray-300">
                  <option value="">全部分类</option>
                  <option value="entities">实体</option>
                  <option value="topics">主题</option>
                  <option value="contradictions">矛盾</option>
                </select>
                <Button variant="secondary" size="sm" onClick={fetchPages} loading={loading} className="w-full">
                  <RefreshCw className="w-3 h-3 mr-1" />刷新
                </Button>
                <Button variant="primary" size="sm" onClick={handleConvertKb} loading={converting} className="w-full">
                  <Database className="w-3 h-3 mr-1" />从知识库导入
                </Button>
                {convertResult && (
                  <div className="text-xs text-gray-400 mt-1">
                    {convertResult.message || `${convertResult.created} 已创建, ${convertResult.skipped} 跳过`}
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><div className="text-sm font-medium"><Plus className="w-3 h-3 inline mr-1" />新建页面</div></CardHeader>
              <CardContent className="space-y-2">
                <Input placeholder="标题" value={newTitle} onChange={e => setNewTitle(e.target.value)} />
                <select value={newCategory} onChange={e => setNewCategory(e.target.value)}
                  className="w-full h-8 px-2 bg-dark-card border border-dark-border rounded text-xs text-gray-300">
                  <option value="entities">实体</option>
                  <option value="topics">主题</option>
                </select>
                <Input placeholder="标签 (逗号分隔)" value={newTags} onChange={e => setNewTags(e.target.value)} />
                <Textarea rows={4} placeholder="Markdown 正文" value={newBody} onChange={e => setNewBody(e.target.value)} />
                <Button variant="primary" size="sm" onClick={handleCreate} className="w-full">创建页面</Button>
              </CardContent>
            </Card>
          </div>
          <div className="md:col-span-2">
            <div className="text-xs text-gray-500 mb-2">{pages.length} 个页面</div>
            <div className="space-y-2">
              {pages.map((p) => (
                <div key={p.title} onClick={() => readPage(p.title)}
                  className="p-3 rounded-lg border border-dark-border bg-dark-card cursor-pointer hover:border-gray-600 transition-colors">
                  <div className="flex items-center gap-2 mb-1">
                    <BookOpen className="w-3 h-3 text-gray-400" />
                    <span className="text-sm font-medium text-gray-200">{p.title}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${sourceBadge(p.category)}`}>{p.category}</span>
                  </div>
                  {p.summary && <div className="text-xs text-gray-500 line-clamp-1">{p.summary}</div>}
                  <div className="flex gap-2 mt-1">
                    {(p.tags || []).slice(0, 3).map(t => (
                      <span key={t} className="text-[10px] text-gray-600 bg-dark-bg px-1 rounded">{t}</span>
                    ))}
                    {p.contradictions?.length > 0 && (
                      <span className="text-[10px] text-red-400"><AlertTriangle className="w-2 h-2 inline mr-0.5" />{p.contradictions.length} 矛盾</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Ingest Tab */}
      {tab === 'ingest' && (
        <Card>
          <CardHeader><div className="text-sm font-medium">摄入新文本</div></CardHeader>
          <CardContent className="space-y-3">
            <Input placeholder="文档/文章标题" value={ingestTitle} onChange={e => setIngestTitle(e.target.value)} />
            <Textarea rows={12} placeholder="粘贴全文..." value={ingestText} onChange={e => setIngestText(e.target.value)} />
            <Button variant="primary" onClick={handleIngest} loading={ingesting}>
              摄入到 Wiki
            </Button>
            <div className="text-xs text-gray-500">
              摄入后存储到 _sources 目录。需执行 <b>wiki_curator</b> Agent 来分析和更新 Wiki 页面。
            </div>
          </CardContent>
        </Card>
      )}

      {/* Query Tab */}
      {tab === 'query' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card>
            <CardHeader><div className="text-sm font-medium"><Search className="w-3 h-3 inline mr-1" />Wiki 问答</div></CardHeader>
            <CardContent className="space-y-3">
              <Input placeholder="输入你的问题..." value={wikiQuestion} onChange={e => setWikiQuestion(e.target.value)} />
              <Button variant="primary" onClick={handleQuery} loading={querying}>搜索 Wiki</Button>
              {wikiAnswer && (
                <pre className="text-xs text-gray-300 whitespace-pre-wrap bg-dark-bg p-3 rounded max-h-96 overflow-auto">{wikiAnswer}</pre>
              )}
            </CardContent>
          </Card>
          {selectedPage && (
            <Card>
              <CardHeader>
                <div className="text-sm font-medium flex items-center justify-between">
                  <span>{selectedPage.title}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${sourceBadge(selectedPage.category)}`}>{selectedPage.category}</span>
                </div>
              </CardHeader>
              <CardContent>
                {selectedPage.summary && <div className="text-xs text-gray-400 mb-2">{selectedPage.summary}</div>}
                <div className="flex flex-wrap gap-1 mb-2">
                  {(selectedPage.tags || []).map((t: string) => <span key={t} className="text-[10px] text-gray-600 bg-dark-bg px-1 rounded">{t}</span>)}
                </div>
                {(selectedPage.related || []).length > 0 && (
                  <div className="text-xs text-gray-500 mb-2">链接: {(selectedPage.related || []).join(', ')}</div>
                )}
                {selectedPage.contradictions?.length > 0 && (
                  <div className="text-xs text-red-400 mb-2">⚠ 矛盾: {(selectedPage.contradictions || []).join(', ')}</div>
                )}
                <pre className="text-xs text-gray-300 whitespace-pre-wrap bg-dark-bg p-3 rounded max-h-80 overflow-auto">{selectedPage.body || '(无正文)'}</pre>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Lint Tab */}
      {tab === 'lint' && (
        <div className="space-y-3">
          <Card>
            <CardHeader><div className="text-sm font-medium flex items-center justify-between">
              <span><AlertTriangle className="w-3 h-3 inline mr-1" />Wiki 健康检查</span>
              {lintResult && (
                <span className={`text-xs px-2 py-0.5 rounded ${lintResult.health_score >= 80 ? 'bg-green-900/50 text-green-300' : 'bg-yellow-900/50 text-yellow-300'}`}>
                  得分: {lintResult.health_score}
                </span>
              )}
            </div></CardHeader>
            <CardContent className="space-y-2">
              <Button variant="primary" size="sm" onClick={handleLint} loading={loading}>执行健康检查</Button>
              {lintResult && lintResult.issues && (
                <div className="space-y-1 mt-3">
                  {lintResult.issues.map((issue: any, idx: number) => (
                    <div key={idx} className="flex items-start gap-2 text-xs p-2 bg-dark-bg rounded">
                      <AlertTriangle className="w-3 h-3 text-yellow-400 shrink-0 mt-0.5" />
                      <div>
                        <span className="text-gray-300">[{issue.type}] {issue.page_a}</span>
                        {issue.page_b && <span className="text-gray-500"> ↔ {issue.page_b}</span>}
                        {issue.description && <div className="text-gray-500">{issue.description}</div>}
                        {issue.suggestion && <div className="text-blue-400">建议: {issue.suggestion}</div>}
                      </div>
                    </div>
                  ))}
                  {lintResult.issues.length === 0 && <div className="text-xs text-green-400">✅ Wiki 健康，无问题</div>}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Page Detail Modal */}
      {selectedPage && tab !== 'query' && (
        <Card>
          <CardHeader>
            <div className="text-sm font-medium flex items-center justify-between">
              <span>{selectedPage.title}</span>
              <button onClick={() => setSelectedPage(null)} className="text-gray-500 hover:text-gray-300 text-xs">关闭</button>
            </div>
          </CardHeader>
          <CardContent>
            <pre className="text-xs text-gray-300 whitespace-pre-wrap bg-dark-bg p-3 rounded max-h-96 overflow-auto">{selectedPage.body || '(无正文)'}</pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default WikiPage;
