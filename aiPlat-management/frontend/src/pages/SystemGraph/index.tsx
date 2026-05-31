import React, { useEffect, useState, useCallback, useRef } from 'react';
import { Brain, Code, Network, RefreshCw, Download, GitBranch, BookOpen, Layers, Maximize2, Minimize2 } from 'lucide-react';
import GraphCanvas from './GraphCanvas';
import NodeDetailPanel from './NodeDetailPanel';
import SearchBar from './SearchBar';
import LayerLegend from './LayerLegend';
import ArchitectureView from './ArchitectureView';

const SystemGraph: React.FC = () => {
  const [tab, setTab] = useState<'code' | 'capability' | 'wiki' | 'architecture'>('code');
  const [graphData, setGraphData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeLayers, setActiveLayers] = useState<Set<string>>(new Set(['infra', 'core', 'platform', 'app']));
  const [diffInput, setDiffInput] = useState('');
  const [diffNodes, setDiffNodes] = useState<Set<string>>(new Set());
  const chartRef = useRef<any>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [globalResults, setGlobalResults] = useState<any>(null);
  const [globalOpen, setGlobalOpen] = useState(false);
  const [globalQuery, setGlobalQuery] = useState('');
  const lastCenter = useRef('');

  const debounceTimer = useRef<ReturnType<typeof setTimeout>>();

  // Global search — auto-detect NL vs keyword
  const doGlobalSearch = useCallback(async (val: string) => {
    if (val.length < 2) { setGlobalResults(null); setGlobalOpen(false); return; }
    // NL detection: Chinese/Japanese chars, questions, or long queries
    const isNL = /[\u4e00-\u9fff\u3040-\u30ff]/.test(val) || val.length > 12 || val.endsWith('?') || val.endsWith('？');
    try {
      const url = isNL
        ? '/api/core/knowledge-graph/ask'
        : `/api/core/knowledge-graph/global-search?q=${encodeURIComponent(val)}`;
      const r = await fetch(url, isNL ? {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: val }),
      } : undefined);
      const d = await r.json();
      if (isNL) {
        setGlobalResults({ type: 'nl', data: d });
        setGlobalOpen(true);
      } else {
        setGlobalResults(d);
        setGlobalOpen(d.total > 0);
      }
    } catch { setGlobalResults(null); }
  }, []);

  // ESC to exit fullscreen
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setFullscreen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const fetchGraph = useCallback(async (c?: string, d?: number) => {
    if (tab === 'architecture') return;
    if (tab === 'code' && !c) { setGraphData(null); setLoading(false); return; }
    setLoading(true);
    try {
      let url = tab === 'code'
        ? '/api/core/knowledge-graph/code'
        : tab === 'capability'
          ? '/api/core/knowledge-graph/capability'
          : '/api/core/knowledge-graph/wiki';
      if (tab === 'code' && c) {
        lastCenter.current = c;
        url += `?center=${encodeURIComponent(c)}&depth=${d || 2}`;
      }
      const r = await fetch(url);
      setGraphData(await r.json());
    } catch { }
    finally { setLoading(false); }
  }, [tab]);

  useEffect(() => { setGraphData(null); if (tab !== 'code') fetchGraph(); }, [fetchGraph, tab]);

  return (
    <div className={`flex flex-col bg-dark-bg ${fullscreen ? 'fixed inset-0 z-50' : 'h-screen'}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-dark-border shrink-0">
        <div className="flex items-center gap-3">
          <Brain className="w-5 h-5 text-primary" />
          <h1 className="text-lg font-semibold text-gray-100">系统图谱</h1>
          {/* Tab switcher */}
          <div className="flex gap-0.5 bg-dark-bg rounded-lg p-0.5 border border-dark-border">
            <button
              onClick={() => { setTab('code'); setActiveLayers(new Set()); setGraphData(null); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                tab === 'code' ? 'bg-primary/20 text-primary' : 'text-gray-400 hover:text-gray-300'
              }`}
            >
              <Code className="w-3 h-3" />代码图谱
            </button>
            <button
              onClick={() => { setTab('capability'); setActiveLayers(new Set(['agent', 'skill', 'tool', 'mcp_server', 'workflow', 'entry_point'])); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                tab === 'capability' ? 'bg-primary/20 text-primary' : 'text-gray-400 hover:text-gray-300'
              }`}
            >
              <Network className="w-3 h-3" />能力图谱
            </button>
            <button
              onClick={() => { setTab('wiki'); setActiveLayers(new Set(['entities', 'topics', 'contradictions'])); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                tab === 'wiki' ? 'bg-primary/20 text-primary' : 'text-gray-400 hover:text-gray-300'
              }`}
            >
              <BookOpen className="w-3 h-3" />知识图谱
            </button>
            <button
              onClick={() => { setTab('architecture'); setActiveLayers(new Set()); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                tab === 'architecture' ? 'bg-primary/20 text-primary' : 'text-gray-400 hover:text-gray-300'
              }`}
            >
              <Layers className="w-3 h-3" />架构全景
            </button>
          </div>
          {/* Code tab: subgraph info bar */}
          {tab === 'code' && graphData && (
            <div className="flex items-center gap-2 text-[10px] text-gray-500">
              <span>中心: {lastCenter.current}</span>
              <span className="text-gray-600">· {graphData.nodes?.length || 0} 节点 · {graphData.links?.length || 0} 边</span>
              <button onClick={() => { setGraphData(null); lastCenter.current = ''; }}
                className="text-gray-500 hover:text-gray-300">✕ 清除</button>
              <button onClick={() => fetchGraph(lastCenter.current, 3)}
                className="text-gray-500 hover:text-gray-300">+ 展开</button>
            </div>
          )}
          {tab === 'wiki' && (
            <div className="flex gap-1">
              {[{ key: 'entities', label: '实体', cls: 'bg-blue-900/20 text-blue-300 border-blue-500/30' },
                { key: 'topics', label: '主题', cls: 'bg-purple-900/20 text-purple-300 border-purple-500/30' },
                { key: 'contradictions', label: '矛盾', cls: 'bg-red-900/20 text-red-300 border-red-500/30' }].map(cat => (
                <button
                  key={cat.key}
                  onClick={() => {
                    const next = new Set(activeLayers);
                    next.has(cat.key) ? next.delete(cat.key) : next.add(cat.key);
                    if (next.size > 0) setActiveLayers(next);
                  }}
                  className={`px-1.5 py-0.5 rounded text-[10px] border transition-colors ${
                    activeLayers.has(cat.key) ? cat.cls : 'text-gray-600 border-dark-border'
                  }`}
                >
                  {cat.label}
                </button>
              ))}
            </div>
          )}
          {graphData?.stats && (
            <span className="text-[10px] text-gray-600">
              {graphData.stats.total_nodes} 节点 · {graphData.stats.total_edges} 边
              {graphData.stats.health_score != null && (
                <span className={
                  graphData.stats.health_score >= 75 ? 'text-green-400 ml-1' :
                    graphData.stats.health_score >= 50 ? 'text-yellow-400 ml-1' : 'text-red-400 ml-1'
                }>
                  {graphData.stats.health_score}/{graphData.stats.health_grade}
                </span>
              )}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 relative">
          {/* Global search */}
          <div className="relative">
            <input
              type="text"
              value={globalQuery}
              onChange={e => { setGlobalQuery(e.target.value); clearTimeout(debounceTimer.current); debounceTimer.current = setTimeout(() => doGlobalSearch(e.target.value), 300); }}
              onFocus={() => globalResults && globalResults.total > 0 && setGlobalOpen(true)}
              onBlur={() => setTimeout(() => setGlobalOpen(false), 200)}
              placeholder="全局搜索..."
              className="w-44 bg-dark-bg border border-dark-border rounded px-2.5 py-1.5 text-xs text-gray-200 outline-none focus:border-primary/50 placeholder-gray-600"
            />
            {globalOpen && globalResults && (
              <div className="absolute top-full left-0 mt-1 w-80 max-h-64 overflow-y-auto bg-dark-card border border-dark-border rounded-lg shadow-lg z-20">
                {/* NL Answer */}
                {globalResults.type === 'nl' && (
                  <div className="p-3">
                    <div className="text-xs text-blue-300 mb-2">{globalResults.data.answer}</div>
                    {globalResults.data.results?.output && (
                      <pre className="text-[10px] text-gray-400 max-h-32 overflow-auto bg-dark-bg rounded p-2">{globalResults.data.results.output}</pre>
                    )}
                  </div>
                )}
                {globalResults.results?.code?.length > 0 && (
                  <div className="px-2 py-1.5 text-[10px] text-gray-500 font-medium">代码文件</div>
                )}
                {globalResults.results?.code.map((f: any) => (
                  <div key={f.path}
                    className="px-3 py-1 text-xs text-gray-300 hover:bg-dark-bg cursor-pointer flex justify-between"
                    onClick={() => { setTab('code'); fetchGraph(f.short.replace(/\.[^.]+$/, ''), 2); setGlobalOpen(false); }}>
                    <span className="truncate flex-1">{f.short}</span>
                    <span className="text-gray-600 ml-2 shrink-0">in:{f.in}</span>
                  </div>
                ))}
                {globalResults.results?.capability.length > 0 && (
                  <div className="px-2 py-1.5 text-[10px] text-gray-500 font-medium border-t border-dark-border">能力组件</div>
                )}
                {globalResults.results?.capability.map((c: any) => (
                  <div key={c.id}
                    className="px-3 py-1 text-xs text-gray-300 hover:bg-dark-bg cursor-pointer flex justify-between"
                    onClick={() => { setTab(c.type === 'skill' ? 'capability' : 'capability'); setGlobalOpen(false); }}>
                    <span className="truncate flex-1">{c.label}</span>
                    <span className="text-gray-600 ml-2 shrink-0">{c.type}</span>
                  </div>
                ))}
                {globalResults.results?.wiki.length > 0 && (
                  <div className="px-2 py-1.5 text-[10px] text-gray-500 font-medium border-t border-dark-border">Wiki 知识</div>
                )}
                {globalResults.results?.wiki.map((w: any, i: number) => (
                  <div key={i}
                    className="px-3 py-1 text-xs text-gray-300 hover:bg-dark-bg cursor-pointer"
                    onClick={() => { setTab('wiki'); setGlobalOpen(false); }}>
                    <span className="truncate">{w.title}</span>
                    {w.summary && <span className="text-gray-600 block text-[10px] truncate">{w.summary}</span>}
                  </div>
                ))}
              </div>
            )}
          </div>
          <button
            onClick={() => setFullscreen(!fullscreen)}
            className={`flex items-center gap-1 px-2.5 py-1.5 rounded text-xs font-medium transition-colors ${
              fullscreen ? 'bg-primary/20 text-primary' : 'text-gray-400 hover:text-gray-300'
            }`}
            title={fullscreen ? '退出全屏 (ESC)' : '全屏'}
          >
            {fullscreen ? <><Minimize2 className="w-3 h-3" />退出</> : <><Maximize2 className="w-3 h-3" />全屏</>}
          </button>
          <button onClick={fetchGraph} className="p-1.5 rounded text-gray-400 hover:text-gray-200 transition-colors" title="刷新">
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={async () => {
              const instance = chartRef.current?.getEchartsInstance?.();
              if (instance) {
                const url = instance.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#0f172a' });
                const a = document.createElement('a'); a.href = url; a.download = 'system-graph.png'; a.click();
              }
            }}
            className="p-1.5 rounded text-gray-400 hover:text-gray-200 transition-colors" title="导出PNG"
          >
            <Download className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Main content: graph + detail panel */}
       <div className="flex-1 flex overflow-hidden">
         {tab === 'architecture' ? (
           <ArchitectureView />
         ) : (
          <div className="flex-1 relative">
            {loading ? (
             <div className="flex items-center justify-center h-full text-gray-500">
               <RefreshCw className="w-6 h-6 animate-spin" />
             </div>
            ) : tab === 'code' && !graphData ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center text-gray-500">
                  <p className="text-sm mb-2">依赖子图浏览器</p>
                  <p className="text-xs text-gray-600">← 使用顶部全局搜索框搜索代码文件</p>
                </div>
              </div>
           ) : graphData ? (
            <GraphCanvas
              ref={chartRef}
              data={graphData}
              selectedNode={selectedNode}
              onNodeSelect={setSelectedNode}
              searchQuery={searchQuery}
              tab={tab}
              activeLayers={activeLayers}
              diffNodes={diffNodes}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-gray-500 text-sm">
              加载中...
            </div>
          )}
          {graphData?.categories && <LayerLegend tab={tab} categories={graphData.categories} />}
        </div>
        )}

        {/* Detail panel */}
        {selectedNode ? (
          <NodeDetailPanel
            nodeId={selectedNode}
            tab={tab}
            onClose={() => setSelectedNode(null)}
            graphData={graphData}
          />
        ) : (
          tab !== 'architecture' && (
          <div className="w-64 shrink-0 border-l border-dark-border bg-dark-card/50 flex items-center justify-center">
            <div className="text-center text-gray-600">
              <div className="text-2xl mb-2">←</div>
              <p className="text-xs">点击图中节点</p>
              <p className="text-xs text-gray-700">查看文件详情</p>
            </div>
          </div>
          )
        )}
      </div>

      {/* Diff impact bar */}
      <div className="h-10 shrink-0 border-t border-dark-border bg-dark-card flex items-center px-3 gap-2">
          <GitBranch className="w-3 h-3 text-gray-500" />
          <input
            type="text"
            value={diffInput}
            onChange={e => setDiffInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') {
                const files = diffInput.split(/[\n,]/).map(f => f.trim()).filter(Boolean);
                const matchSet = new Set<string>();
                (graphData?.nodes || []).forEach((n: any) => {
                  if (files.some(f => (n.id || n.fullName || '').includes(f))) matchSet.add(n.id);
                });
                setDiffNodes(matchSet);
              }
            }}
            placeholder="输入改动文件路径（逗号或换行分隔），按 Enter 高亮影响..."
            className="flex-1 bg-dark-bg border border-dark-border rounded px-2 py-1 text-[10px] text-gray-300 outline-none focus:border-primary/50"
          />
          <span className="text-[10px] text-gray-600">
            {diffNodes.size > 0 ? `${diffNodes.size} 节点已高亮` : '输入文件后按 Enter'}
          </span>
          {diffNodes.size > 0 && (
            <button onClick={() => { setDiffNodes(new Set()); setDiffInput(''); }} className="text-[10px] text-gray-500 hover:text-gray-300">
              清除
            </button>
          )}
          <button onClick={() => setDiffInput('')} className="text-gray-500 text-[10px]">×</button>
        </div>
    </div>
  );
};

export default SystemGraph;
