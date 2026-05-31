import React, { useEffect, useState, useCallback, useRef } from 'react';
import { Brain, Code, Network, RefreshCw, Download, GitBranch, BookOpen, Layers, Maximize2, Minimize2, Compass } from 'lucide-react';
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
  const [diffResult, setDiffResult] = useState<{ file: string; affected: string[]; count: number } | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const chartRef = useRef<any>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [globalResults, setGlobalResults] = useState<any>(null);
  const [globalOpen, setGlobalOpen] = useState(false);
  const [globalQuery, setGlobalQuery] = useState('');
  const lastCenter = useRef('');
  const [tourMode, setTourMode] = useState(false);
  const [tourSteps, setTourSteps] = useState<{ file: string; layer: string; in_degree: number; out_degree: number; symbols: string[] }[]>([]);
  const [tourIdx, setTourIdx] = useState(0);

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

  const inferLayer = (path: string): string => {
    if (!path) return 'unknown';
    if (path.includes('infra') || path.includes('model')) return 'infra';
    if (path.includes('harness') || path.includes('syscall') || path.includes('engine')) return 'core';
    if (path.includes('api/rest') || path.includes('platform')) return 'platform';
    if (path.includes('frontend') || path.includes('App.') || path.includes('page')) return 'app';
    return 'core';
  };

  // ── Guided Tour ──
  const startTour = useCallback(async () => {
    setTourMode(true);
    setTourIdx(0);
    try {
      const res = await fetch('/api/core/diagnostics/code-intel/scan?depth=2&limit=200');
      const data = await res.json();
      const nodes = data?.nodes || data?.graph?.nodes || {};
      const nodeList = Array.isArray(nodes) ? nodes : Object.values(nodes);
      const sorted = nodeList
        .filter((n: any) => n.in_degree !== undefined || n.out_degree !== undefined)
        .sort((a: any, b: any) => (a.in_degree || 0) - (b.in_degree || 0))
        .slice(0, 30)
        .map((n: any) => ({
          file: n.path || n.id || n.file || '',
          layer: n.layer || inferLayer(n.path || n.file || ''),
          in_degree: n.in_degree || 0,
          out_degree: n.out_degree || 0,
          symbols: ((n.symbols || []) as any[]).map((s: any) => {
            if (Array.isArray(s)) return s[0];
            if (typeof s === 'object' && s !== null) return s.name || '';
            return String(s || '');
          }).filter(Boolean).slice(0, 8),
        }));
      setTourSteps(sorted);
    } catch {
      setTourMode(false);
    }
  }, []);

  const nextTour = () => { if (tourIdx < tourSteps.length - 1) setTourIdx(tourIdx + 1); };
  const prevTour = () => { if (tourIdx > 0) setTourIdx(tourIdx - 1); };
  const closeTour = () => { setTourMode(false); setTourSteps([]); };

  // ── Export Graph as committable JSON ──
  const exportGraph = async () => {
    try {
      const res = await fetch('/api/core/diagnostics/code-intel/export');
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'code_graph.json';
      a.click();
      URL.revokeObjectURL(url);
    } catch {}
  };

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
          {/* Tour button */}
          {tab === 'code' && (
            <button
              onClick={() => tourMode ? closeTour() : startTour()}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                tourMode ? 'bg-amber-500/20 text-amber-400' : 'text-gray-400 hover:text-gray-300'
              }`}
            >
              <Compass className="w-3 h-3" />
              {tourMode ? `导览中 (${tourIdx + 1}/${tourSteps.length})` : '导览'}
            </button>
          )}
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
          <button
            onClick={exportGraph}
            className="p-1.5 rounded text-gray-400 hover:text-gray-200 transition-colors" title="导出JSON（可提交到仓库）"
          >
            <GitBranch className="w-3 h-3" />
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
            onKeyDown={async e => {
              if (e.key === 'Enter') {
                const file = diffInput.trim();
                if (!file) return;
                setDiffLoading(true);
                try {
                  // Call blast radius API
                  const res = await fetch(`/api/core/diagnostics/code-intel/blast?file=${encodeURIComponent(file)}`);
                  const data = await res.json();
                  const affected: string[] = data.affected || [];
                  const matchSet = new Set<string>([file, ...affected]);
                  setDiffNodes(matchSet);
                  setDiffResult({ file, affected, count: affected.length });
                } catch {
                  // Fallback: simple name matching
                  const files = diffInput.split(/[\n,]/).map(f => f.trim()).filter(Boolean);
                  const matchSet = new Set<string>();
                  (graphData?.nodes || []).forEach((n: any) => {
                    if (files.some(f => (n.id || n.fullName || '').includes(f))) matchSet.add(n.id);
                  });
                  setDiffNodes(matchSet);
                  setDiffResult(null);
                } finally {
                  setDiffLoading(false);
                }
              }
            }}
            placeholder="输入改动文件路径（逗号或换行分隔），按 Enter 高亮影响..."
            className="flex-1 bg-dark-bg border border-dark-border rounded px-2 py-1 text-[10px] text-gray-300 outline-none focus:border-primary/50"
          />
          <span className="text-[10px] text-gray-600">
            {diffLoading ? '分析中...' : diffResult ? `⚠ ${diffResult.affected.length} 个受影响文件` : diffNodes.size > 0 ? `${diffNodes.size} 节点高亮` : '输入文件路径，按 Enter 分析影响面'}
          </span>
          {diffNodes.size > 0 && (
            <button onClick={() => { setDiffNodes(new Set()); setDiffInput(''); setDiffResult(null); }} className="text-[10px] text-gray-500 hover:text-gray-300">
              清除
            </button>
          )}
          {diffResult && diffResult.affected.length > 0 && (
            <button
              onClick={() => {
                const list = `目标文件: ${diffResult.file}\n\n受影响文件 (${diffResult.affected.length}):\n${diffResult.affected.map(f => '  - ' + f).join('\n')}`;
                navigator.clipboard.writeText(list);
              }}
              className="text-[10px] text-gray-500 hover:text-gray-300"
              title="复制影响面清单"
            >
              复制清单
            </button>
          )}
          <button onClick={() => setDiffInput('')} className="text-gray-500 text-[10px]">×</button>
        </div>

      {/* Guided Tour Panel */}
      {tourMode && tourSteps.length > 0 && (
        <div style={{
          position: 'absolute', bottom: 12, left: 12, zIndex: 30,
          width: 320, maxHeight: 360, overflowY: 'auto',
          background: '#1f2937', border: '1px solid #374151', borderRadius: 10,
          padding: 12, boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: '#f59e0b' }}>
              🧭 架构导览
            </span>
            <div style={{ display: 'flex', gap: 4 }}>
              <button onClick={prevTour} disabled={tourIdx === 0}
                style={{ fontSize: 10, background: '#374151', border: 'none', borderRadius: 4,
                  color: tourIdx === 0 ? '#4b5563' : '#e5e7eb', cursor: tourIdx === 0 ? 'default' : 'pointer', padding: '2px 8px' }}>
                ◀ 上一个
              </button>
              <button onClick={nextTour} disabled={tourIdx >= tourSteps.length - 1}
                style={{ fontSize: 10, background: '#374151', border: 'none', borderRadius: 4,
                  color: tourIdx >= tourSteps.length - 1 ? '#4b5563' : '#e5e7eb', cursor: tourIdx >= tourSteps.length - 1 ? 'default' : 'pointer', padding: '2px 8px' }}>
                下一个 ▶
              </button>
              <button onClick={closeTour}
                style={{ fontSize: 10, background: '#374151', border: 'none', borderRadius: 4,
                  color: '#9ca3af', cursor: 'pointer', padding: '2px 6px' }}>
                ✕
              </button>
            </div>
          </div>
          <div style={{ fontSize: 10, color: '#6b7280', marginBottom: 8 }}>
            按依赖深度排序 — 从基础层向上探索 {tourIdx + 1} / {tourSteps.length}
          </div>
          {/* Current step */}
          {(() => {
            const step = tourSteps[tourIdx];
            const colors: Record<string, string> = { infra: '#10b981', core: '#3b82f6', platform: '#8b5cf6', app: '#f59e0b', unknown: '#6b7280' };
            const labels: Record<string, string> = { infra: 'Infra', core: 'Core', platform: 'Platform', app: 'App', unknown: 'Unknown' };
            if (!step) return null;
            return (
              <div>
                <div style={{
                  background: '#111827', borderRadius: 6, padding: '8px 10px', marginBottom: 6,
                  borderLeft: `3px solid ${colors[step.layer] || '#6b7280'}`,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <span style={{
                      fontSize: 9, padding: '1px 5px', borderRadius: 3,
                      background: `${colors[step.layer]}20`, color: colors[step.layer],
                    }}>
                      {labels[step.layer] || step.layer}
                    </span>
                    <span style={{ fontSize: 9, color: '#6b7280' }}>
                      ⬇{step.in_degree} ⬆{step.out_degree}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, fontFamily: 'monospace', color: '#e5e7eb', wordBreak: 'break-all' }}>
                    {step.file ? step.file.replace(/^.*\/aiPlat-(core|platform|app|infra|management)\//, '$1/').replace(/^core\//, '') : '(unknown)'}
                  </div>
                  {step.symbols.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 4 }}>
                      {step.symbols.map((s, i) => (
                        <span key={i} style={{ fontSize: 9, color: '#9ca3af', background: '#374151', borderRadius: 3, padding: '0 4px' }}>
                          {s}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                {/* Progress dots */}
                <div style={{ display: 'flex', gap: 2, justifyContent: 'center' }}>
                  {tourSteps.slice(Math.max(0, tourIdx - 2), Math.min(tourSteps.length, tourIdx + 5)).map((_, i) => {
                    const actualIdx = Math.max(0, tourIdx - 2) + i;
                    return (
                      <div key={i} style={{
                        width: 6, height: 6, borderRadius: '50%',
                        background: actualIdx === tourIdx ? '#f59e0b' : actualIdx < tourIdx ? '#22c55e' : '#374151',
                        cursor: 'pointer',
                      }} onClick={() => setTourIdx(actualIdx)} />
                    );
                  })}
                </div>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
};

export default SystemGraph;
