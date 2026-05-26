import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { Search, X } from 'lucide-react';

import { Input } from '../ui';

const LazyECharts: any = React.lazy(() => import('echarts-for-react'));

const CAT_COLORS: Record<string, string> = {
  entities: '#4d9fff',
  topics: '#a855f7',
  contradictions: '#ef4444',
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
}

const WikiGraph: React.FC<WikiGraphProps> = ({ onSelectPage }) => {
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [error, setError] = useState('');

  const fetchGraph = useCallback(async (kw: string) => {
    setLoading(true);
    setError('');
    try {
      let url = '/api/core/wiki/graph?max_nodes=400&source=kb';
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

    const showLabels = nodeCount <= 80;
    const edgeOpacity = edgeCount > 800 ? 0.05 : edgeCount > 400 ? 0.10 : 0.16;
    const repulsion = Math.max(120, nodeCount < 60 ? 300 : nodeCount < 150 ? 220 : 160);

    const categories = Object.keys(data.stats?.categories || {}).map((cat) => ({
      name: cat,
      itemStyle: { color: CAT_COLORS[cat] || '#4d9fff' },
    }));
    if (!categories.length) categories.push({ name: 'entities' });

    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        confine: true,
        formatter: (p: any) => {
          if (p?.dataType === 'node') {
            const d = p.data;
            const tagsStr = (d.tags || []).slice(0, 5).map((t: string) =>
              `<span style="background:rgba(255,255,255,0.08);padding:1px 5px;border-radius:3px;margin-right:3px;font-size:10px">${t}</span>`
            ).join('');
            return `
              <div style="max-width:360px;white-space:normal;">
                <div style="font-weight:600;font-size:13px;margin-bottom:4px">${d.name}</div>
                ${d.summary ? `<div style="opacity:0.7;font-size:11px;margin-bottom:4px;line-height:1.4">${d.summary.slice(0, 120)}</div>` : ''}
                <div style="font-size:10px;opacity:0.6">链接数: ${d.linkCount} | 分类: ${d.category}</div>
                ${tagsStr ? `<div style="margin-top:4px">${tagsStr}</div>` : ''}
                <div style="opacity:0.5;margin-top:6px;font-size:10px">点击查看详情</div>
              </div>`;
          }
          return `${p?.data?.source} → ${p?.data?.target}`;
        },
      },
      legend: nodeCount > 0 ? [{ data: categories.map((c: any) => c.name), left: 8, top: 8, textStyle: { color: 'rgba(255,255,255,0.6)', fontSize: 10 } }] : undefined,
      series: [
        {
          type: 'graph',
          layout: 'force',
          roam: true,
          draggable: true,
          data: nodes,
          links: edges,
          categories: categories,
          force: {
            repulsion,
            edgeLength: nodeCount < 60 ? [80, 250] : [40, 160],
            gravity: 0.08,
            layoutAnimation: true,
          },
          label: {
            show: showLabels,
            position: 'right',
            fontSize: 10,
            color: 'rgba(255,255,255,0.7)',
            formatter: (p: any) => {
              const name = String(p?.data?.name || '');
              return name.length > 15 ? name.slice(0, 14) + '…' : name;
            },
          },
          labelLayout: { hideOverlap: true },
          lineStyle: {
            color: `rgba(255,255,255,${edgeOpacity})`,
            width: 0.8,
            curveness: 0.18,
          },
          emphasis: {
            focus: 'adjacency',
            label: { show: true },
            lineStyle: { width: 2, opacity: 0.8 },
          },
          blur: {
            itemStyle: { opacity: 0.15 },
            lineStyle: { opacity: 0.04 },
          },
          itemStyle: {},
        },
      ],
    };
  }, [data]);

  const onChartClick = useCallback(
    (params: any) => {
      if (params?.dataType === 'node' && params?.data?.id) {
        onSelectPage(String(params.data.id));
      }
    },
    [onSelectPage]
  );

  return (
    <div className="flex flex-col h-full">
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
        <span className="text-[10px] text-gray-500 ml-auto">
          {data?.stats?.totalNodes != null ? `${data.stats.totalNodes} 节点 · ${data.stats.totalEdges} 边` : ''}
        </span>
      </div>

      {/* Graph canvas */}
      <div className="flex-1 min-h-0 bg-dark-card rounded-lg border border-dark-border overflow-hidden">
        {loading && (
          <div className="flex items-center justify-center h-full">
            <span className="text-xs text-gray-500">加载中…</span>
          </div>
        )}
        {error && (
          <div className="flex items-center justify-center h-full">
            <span className="text-xs text-red-400">{error}</span>
          </div>
        )}
        {!loading && !error && data && !data.nodes.length && (
          <div className="flex items-center justify-center h-full">
            <span className="text-xs text-gray-500">暂无图谱数据</span>
          </div>
        )}
        {!loading && !error && data && data.nodes.length > 0 && option && (
          <React.Suspense fallback={<div className="flex items-center justify-center h-full"><span className="text-xs text-gray-500">加载图表…</span></div>}>
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
              <span className="w-2 h-2 rounded-full" style={{ background: CAT_COLORS[cat] || '#4d9fff' }} />
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
