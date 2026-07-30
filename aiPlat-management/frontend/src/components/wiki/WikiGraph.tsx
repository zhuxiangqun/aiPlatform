import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { Search, X, Maximize2, Minimize2 } from 'lucide-react';

import { Input } from '../ui';

const LazyECharts: any = React.lazy(() => import('echarts-for-react'));

const CAT_COLORS: Record<string, string> = {
  entities: '#3b82f6',
  topics: '#a855f7',
  contradictions: '#ef4444',
};

const CAT_GLOW: Record<string, string> = {
  entities: 'rgba(59,130,246,0.4)',
  topics: 'rgba(168,85,247,0.4)',
  contradictions: 'rgba(239,68,68,0.4)',
};

interface GraphNode {
  id: string;
  name: string;
  category: string;
  symbolSize: number;
  tags: string[];
  summary: string;
  linkCount: number;
  hasIssues: boolean;
  itemStyle?: { color: string };
}

interface GraphEdge {
  source: string;
  target: string;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats?: { totalNodes: number; totalEdges: number; categories: Record<string, number>; avgLinksPerPage: number };
}

interface WikiGraphProps {
  onSelectPage: (title: string) => void;
  exploreTitles?: Set<string> | null;
  onExitExplore?: () => void;
  collection?: string;
}

const WikiGraph: React.FC<WikiGraphProps> = ({ onSelectPage, exploreTitles, onExitExplore, collection }) => {
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [error, setError] = useState('');
  const [fullscreen, setFullscreen] = useState(false);

  const fetchGraph = useCallback(async (kw: string) => {
    setLoading(true);
    setError('');
    try {
      let url = `/api/core/wiki/graph?max_nodes=400&collection=${collection || 'system_docs'}`;
      if (kw.trim()) url += `&keyword=${encodeURIComponent(kw.trim())}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      setData(d);
    } catch (e: any) {
      setError(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchGraph(''); }, [fetchGraph]);

  const handleSearch = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') fetchGraph(keyword);
  };

  const option = useMemo(() => {
    if (!data || !data.nodes.length) return null;

    const nodes = data.nodes;
    const edges = data.edges;
    const nodeCount = nodes.length;
    const edgeCount = edges.length;

    const showLabels = nodeCount <= 60;
    const edgeOpacity = edgeCount > 800 ? 0.10 : edgeCount > 400 ? 0.18 : 0.35;
    const repulsion = Math.max(200, nodeCount < 30 ? 500 : nodeCount < 80 ? 350 : 240);

    const categories = Object.keys(data.stats?.categories || {}).map((cat) => ({
      name: cat,
      itemStyle: {
        color: CAT_COLORS[cat] || '#3b82f6',
        borderColor: CAT_COLORS[cat] || '#3b82f6',
        borderWidth: 1.5,
        shadowBlur: 10,
        shadowColor: CAT_GLOW[cat] || 'rgba(59,130,246,0.3)',
      },
    }));
    if (!categories.length) categories.push({ name: 'entities' } as any);

    const qLower = keyword.trim().toLowerCase();
    const matchedIds = qLower
      ? new Set(nodes.filter(n =>
          n.id.toLowerCase().includes(qLower) ||
          n.name.toLowerCase().includes(qLower) ||
          (n.tags || []).some((t: string) => t.toLowerCase().includes(qLower))
        ).map(n => n.id))
      : new Set<string>();

    return {
      backgroundColor: exploreTitles ? '#06070a' : '#0a0b0f',
      darkMode: true,
      animationDurationUpdate: 600,
      animationEasingUpdate: 'cubicInOut',
      graphic: [
        // Subtle radial gradient mask at edges
        {
          type: 'rect',
          left: 0, top: 0, right: 0, bottom: 0,
          style: { fill: 'transparent' },
          z: -1,
        },
      ],
      tooltip: {
        trigger: 'item',
        confine: true,
        borderColor: '#333',
        borderWidth: 1,
        backgroundColor: 'rgba(15, 15, 20, 0.95)',
        textStyle: { color: '#d4d4d8' },
        formatter: (p: any) => {
          if (p?.dataType === 'node') {
            const d = p.data;
            const color = CAT_COLORS[d.category] || '#3b82f6';
            return `
              <div style="max-width:420px;overflow:hidden;white-space:normal;word-wrap:break-word;overflow-wrap:break-word;">
                <div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:4px;">
                  <div style="width:10px;height:10px;border-radius:50%;background:${color};box-shadow:0 0 8px ${color}66;flex-shrink:0;margin-top:4px;"></div>
                  <div style="font-weight:600;font-size:13px;color:#e4e4e7;line-height:1.4;max-width:380px;">${d.name}</div>
                </div>
                ${d.summary && d.summary.length > 20 ? `<div style="color:${color}99;font-size:11px;line-height:1.6;padding-left:18px;max-width:390px;word-break:break-all;">${d.summary.slice(0, 180)}</div>` : ''}
              </div>`;
          }
          return `<span style="color:#71717a;font-size:11px">${p?.data?.source} → ${p?.data?.target}</span>`;
        },
      },
      legend: nodeCount > 0 ? [{
        data: categories.map((c: any) => c.name),
        left: 12, top: 12,
        textStyle: { color: '#71717a', fontSize: 10 },
        itemWidth: 10, itemHeight: 10,
        itemStyle: { borderWidth: 0 },
        selectedMode: false,
      }] : undefined,
      series: [
        {
          type: 'graph',
          layout: 'force',
          roam: true,
          draggable: true,
          data: nodes.map((n: any) => {
            const isMatched = matchedIds.has(n.id);
            const inExplore = !exploreTitles || exploreTitles.has(n.id);
            const color = CAT_COLORS[n.category] || '#3b82f6';
            return {
              ...n,
              symbolSize: isMatched ? n.symbolSize * 1.4 : n.symbolSize,
              itemStyle: {
                ...n.itemStyle,
                color: n.itemStyle?.color || color,
                borderColor: n.itemStyle?.borderColor || color,
                borderWidth: isMatched ? 2.5 : 1.5,
                shadowBlur: isMatched ? 20 : 8,
                shadowColor: isMatched
                  ? `${color}aa`
                  : (CAT_GLOW[n.category] || 'rgba(59,130,246,0.3)'),
                opacity: inExplore ? (isMatched ? 1 : 0.85) : 0.06,
              },
            };
          }),
          links: exploreTitles
            ? edges.map((e: any) => ({
                ...e,
                lineStyle: { opacity: exploreTitles.has(e.source) && exploreTitles.has(e.target) ? 0.18 : 0.01, width: 0.3 },
              }))
            : edges,
          categories: categories,
          force: {
            repulsion,
            edgeLength: nodeCount < 30 ? [100, 300] : [50, 180],
            gravity: 0.06,
            layoutAnimation: true,
            friction: 0.1,
          },
          label: {
            show: showLabels,
            position: 'right',
            fontSize: 10,
            color: '#a1a1aa',
            fontWeight: 500,
            formatter: (p: any) => {
              const name = String(p?.data?.name || '');
              return name.length > 18 ? name.slice(0, 17) + '…' : name;
            },
          },
          labelLayout: { hideOverlap: true },
          lineStyle: {
            color: `rgba(255,255,255,${edgeOpacity})`,
            width: 0.8,
            curveness: 0.2,
          },
          emphasis: {
            focus: 'adjacency',
            scale: 1.3,
            label: { show: true, fontSize: 11 },
            itemStyle: {
              borderWidth: 2.5,
              shadowBlur: 24,
              shadowColor: 'rgba(255,255,255,0.3)',
            },
            lineStyle: { width: 2.5, opacity: 1, color: 'rgba(255,255,255,0.5)' },
          },
          blur: {
            itemStyle: { opacity: 0.08 },
            lineStyle: { opacity: 0.02 },
          },
          itemStyle: {},
        },
      ],
    };
  }, [data, keyword]);

  const onChartClick = useCallback(
    (params: any) => {
      if (params?.dataType === 'node' && params?.data?.id) {
        onSelectPage(String(params.data.id));
      }
    },
    [onSelectPage]
  );

  return (
    <div className="flex flex-col" style={{ height: '100%' }}>
      {/* Toolbar */}
      <div className="flex items-center gap-2 mb-2 px-1 shrink-0">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-500" />
          <Input
            placeholder="搜索节点…"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={handleSearch}
            className="pl-7 h-7 text-xs"
          />
          {keyword && (
            <button onClick={() => { setKeyword(''); fetchGraph(''); }} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300">
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
        <span className="text-[10px] text-gray-500">
          {data?.stats?.totalNodes != null ? `${data.stats.totalNodes} 节点 · ${data.stats.totalEdges} 边` : ''}
        </span>
        <div className="flex-1" />
        {exploreTitles && (
          <button onClick={() => { onExitExplore?.(); }} className="text-[10px] px-2 py-0.5 rounded bg-primary/20 text-primary hover:bg-primary/30">
            退出探索 · {exploreTitles.size} 个节点
          </button>
        )}
        <button
          onClick={() => setFullscreen(!fullscreen)}
          className="text-gray-500 hover:text-gray-300 transition-colors"
          title={fullscreen ? '退出全屏' : '全屏'}
        >
          {fullscreen ? <Minimize2 className="w-3 h-3" /> : <Maximize2 className="w-3 h-3" />}
        </button>
      </div>

      {/* Graph canvas */}
      <div className="flex-1 min-h-0 rounded-lg border border-dark-border overflow-hidden"
        style={fullscreen ? { position: 'fixed', inset: 0, zIndex: 50, borderRadius: 0, background: '#06070a' } : {}}>
        {fullscreen && (
          <button onClick={() => setFullscreen(false)}
            className="absolute top-3 right-3 z-10 px-3 py-1.5 rounded bg-dark-card border border-dark-border text-xs text-gray-400 hover:text-white shadow-lg">
            退出全屏
          </button>
        )}
        {loading && (
          <div className="flex items-center justify-center h-full bg-[#0a0b0f]">
            <div className="flex flex-col items-center gap-2">
              <div className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
              <span className="text-xs text-gray-500">加载知识图谱…</span>
            </div>
          </div>
        )}
        {error && (
          <div className="flex items-center justify-center h-full bg-[#0a0b0f]">
            <span className="text-xs text-red-400">{error}</span>
          </div>
        )}
        {!loading && !error && data && !data.nodes.length && (
          <div className="flex flex-col items-center justify-center h-full bg-[#0a0b0f] gap-1">
            <span className="text-xs text-gray-500">暂无图谱数据</span>
            <span className="text-[10px] text-gray-600">导入文档或新建 Wiki 页面后出现</span>
          </div>
        )}
        {!loading && !error && data && data.nodes.length > 0 && option && (
          <React.Suspense fallback={<div className="flex items-center justify-center h-full bg-[#0a0b0f]"><span className="text-xs text-gray-500">加载图表…</span></div>}>
            <LazyECharts
              option={option}
              style={{ height: '100%', width: '100%' }}
              onEvents={{ click: onChartClick }}
              opts={{ renderer: 'canvas' }}
            />
          </React.Suspense>
        )}
      </div>

      {/* Footer stats */}
      {data?.stats && (
        <div className="flex items-center gap-3 mt-1.5 px-1 text-[10px] text-gray-600">
          {Object.entries(data.stats.categories || {}).map(([cat, count]) => (
            <span key={cat} className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full" style={{ background: CAT_COLORS[cat] || '#3b82f6', boxShadow: `0 0 4px ${CAT_COLORS[cat] || '#3b82f6'}66` }} />
              {cat}: {count}
            </span>
          ))}
          <span className="ml-auto">平均 {data.stats.avgLinksPerPage} 链接/页</span>
        </div>
      )}
    </div>
  );
};

export default WikiGraph;
