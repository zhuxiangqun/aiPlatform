import React, { useEffect, useState, useMemo } from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { GraphChart, TreemapChart } from 'echarts/charts';
import { TooltipComponent, GridComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { Card, CardContent } from '../../components/ui';
import { Layers, TrendingUp, Maximize2, Minimize2 } from 'lucide-react';

echarts.use([GraphChart, TreemapChart, TooltipComponent, GridComponent, LegendComponent, CanvasRenderer]);

const LAYER_COLORS: Record<string, string> = {
  infra: '#06b6d4',
  core: '#8b5cf6',
  platform: '#10b981',
  app: '#f97316',
  management: '#6366f1',
};

const FETCH_TIMEOUT_MS = 45000;

const ArchitectureView: React.FC = () => {
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedLayer, setSelectedLayer] = useState<string>('core');
  const [fullscreenTop, setFullscreenTop] = useState(false);
  const [fullscreenBottom, setFullscreenBottom] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setFullscreenTop(false);
        setFullscreenBottom(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const load = React.useCallback(() => {
    const ac = new AbortController();
    const timer = window.setTimeout(() => ac.abort(), FETCH_TIMEOUT_MS);
    setLoading(true);
    setError(null);
    fetch('/api/core/knowledge-graph/architecture', { signal: ac.signal })
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.text().catch(() => '');
          throw new Error(`HTTP ${r.status}${body ? `: ${body.slice(0, 160)}` : ''}`);
        }
        return r.json();
      })
      .then((d) => {
        setData(d);
        const layers = (d?.treemap || []).map((l: any) => String(l?.name || '')).filter(Boolean);
        setSelectedLayer((cur) => (layers.length && !layers.includes(cur) ? layers[0] : cur));
      })
      .catch((e: any) => {
        if (e?.name === 'AbortError') {
          setError('加载超时（后端全量图谱过慢时会卡住；请重试或检查 core:8002）');
        } else {
          setError(e?.message || '加载失败');
        }
        setData(null);
      })
      .finally(() => {
        window.clearTimeout(timer);
        setLoading(false);
      });
    return () => {
      window.clearTimeout(timer);
      ac.abort();
    };
  }, []);

  useEffect(() => load(), [load]);

  const graphOption = useMemo(() => {
    if (!data?.sankey) return {};
    const layers = data.sankey.nodes || [];
    const flows = data.sankey.links || [];

    const maxVal = Math.max(1, ...flows.map((f: any) => Number(f.value || 0)));

    const gNodes = layers.map((n: any) => ({
      id: n.name,
      name: n.name,
      symbolSize: 50,
      itemStyle: { color: LAYER_COLORS[n.name] || '#9ca3af' },
      label: { show: true, fontSize: 12, color: '#c9d1d9' },
    }));

    const seen: Record<string, boolean> = {};
    const allLinks: any[] = [];
    for (const f of flows) {
      const pairKey = [f.source, f.target].sort().join('↔');
      const curved = seen[pairKey] ? -0.3 : 0.3;
      seen[pairKey] = true;
      const count = Number(f.value || 0);
      allLinks.push({
        source: f.source,
        target: f.target,
        // Keep names/count outside ECharts index rewrite of source/target.
        sourceName: String(f.source),
        targetName: String(f.target),
        count,
        value: count,
        label: {
          show: true,
          formatter: String(count),
          fontSize: 9,
          color: '#8b949e',
        },
        lineStyle: {
          color: LAYER_COLORS[f.source] || '#9ca3af',
          opacity: 0.3 + (count / maxVal) * 0.5,
          width: 0.5 + (count / maxVal) * 4,
          curveness: curved,
        },
      });
    }

    // Few layers: circular keeps every node on-canvas (force often flings platform off-screen).
    const useCircular = gNodes.length > 0 && gNodes.length <= 8;

    return {
      tooltip: {
        backgroundColor: '#161B22',
        borderColor: '#30363D',
        textStyle: { color: '#c9d1d9', fontSize: 11 },
        formatter: (p: any) => {
          const d = p?.data || {};
          const nameOf = (ref: unknown) => {
            if (typeof ref === 'string') return ref;
            if (typeof ref === 'number' && gNodes[ref]) return String(gNodes[ref].name || '');
            return '';
          };
          if (p?.dataType === 'edge') {
            const src = d.sourceName || nameOf(d.source);
            const tgt = d.targetName || nameOf(d.target);
            const n = d.count ?? d.value ?? p.value;
            return `${src || '?'} → ${tgt || '?'}<br/>${n != null && n !== '' ? n : '—'} interactions`;
          }
          if (p?.dataType === 'node') {
            return `<b>${d.name || p.name || ''}</b>`;
          }
          return '';
        },
      },
      series: [
        {
          type: 'graph',
          layout: useCircular ? 'circular' : 'force',
          circular: useCircular ? { rotateLabel: false } : undefined,
          roam: true,
          draggable: true,
          force: useCircular ? undefined : { repulsion: 500, gravity: 0.1, edgeLength: [200, 400] },
          data: gNodes,
          links: allLinks,
          emphasis: { focus: 'adjacency' },
        },
      ],
    };
  }, [data]);

  const treemapOption = useMemo(() => {
    if (!data?.treemap) return {};
    const layer = data.treemap.find((l: any) => l.name === selectedLayer);
    if (!layer) return {};
    return {
      tooltip: {
        backgroundColor: '#161B22',
        borderColor: '#30363D',
        textStyle: { color: '#c9d1d9', fontSize: 11 },
        formatter: (p: any) => {
          if (p.value) return `${p.name}: ${p.value} files`;
          return p.name;
        },
      },
      series: [
        {
          type: 'treemap',
          name: selectedLayer,
          data: layer.children || [],
          top: 0,
          left: 0,
          bottom: 0,
          right: 0,
          label: { show: true, fontSize: 10, color: '#c9d1d9' },
          upperLabel: { show: true, height: 24, color: '#c9d1d9', fontSize: 12 },
          itemStyle: { borderColor: '#161b22', borderWidth: 1, gapWidth: 2 },
          levels: [
            { itemStyle: { borderColor: '#555' }, upperLabel: { show: true } },
            { colorSaturation: [0.3, 0.5], itemStyle: { borderColorSaturation: 0.7 } },
            { colorSaturation: [0.3, 0.5] },
          ],
        },
      ],
      visualMap: {
        show: false,
        min: 0,
        max:
          (layer.children || []).reduce(
            (m: number, c: any) => Math.max(m, c.value || (c.children ? c.children.length : 5)),
            5,
          ) || 100,
        inRange: { color: [LAYER_COLORS[selectedLayer] + '20', LAYER_COLORS[selectedLayer]] },
      },
    };
  }, [data, selectedLayer]);

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500 text-sm">
        加载架构数据…
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="flex items-center justify-center h-full px-6">
        <div className="text-center space-y-3 max-w-md">
          <p className="text-sm text-amber-200">架构数据加载失败</p>
          <p className="text-xs text-gray-500 break-words">{error}</p>
          <button
            type="button"
            onClick={() => load()}
            className="text-xs px-3 py-1.5 rounded border border-dark-border text-sky-300 hover:border-sky-500/50"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500 text-sm">
        暂无架构数据
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full gap-3 p-3 overflow-auto relative">
      {!fullscreenBottom && (
        <Card
          key={`top-${fullscreenTop}-${fullscreenBottom}`}
          className={`bg-dark-card border-dark-border ${fullscreenTop ? 'fixed inset-0 z-50 m-0 rounded-none' : 'shrink-0'}`}
        >
          <CardContent className={`${fullscreenTop ? 'h-full p-4' : 'p-3'} flex flex-col`}>
            <div className="flex items-center gap-2 text-xs text-gray-400 mb-2 shrink-0">
              <TrendingUp className="w-3 h-3 text-blue-400" />
              层间依赖流
              <span className="text-gray-600">· 浅层 import 聚合 · 非全量符号图</span>
              <button
                onClick={() => setFullscreenTop(!fullscreenTop)}
                className="ml-auto p-1 rounded text-gray-500 hover:text-gray-300 transition-colors"
                title={fullscreenTop ? '退出全屏 (ESC)' : '全屏'}
              >
                {fullscreenTop ? <Minimize2 className="w-3 h-3" /> : <Maximize2 className="w-3 h-3" />}
              </button>
            </div>
            {(data.sankey?.links || []).length === 0 ? (
              <div className="flex-1 flex items-center justify-center min-h-[180px]">
                <div className="text-center">
                  <p className="text-sm text-green-400 mt-2 font-medium">未检出跨层包导入边</p>
                  <p className="text-xs text-gray-500 mt-1">app → platform → core → infra 单向依赖链</p>
                </div>
              </div>
            ) : (
              <ReactEChartsCore
                key={`graph-${data.sankey?.nodes?.length || 0}-${fullscreenTop}`}
                echarts={echarts}
                option={graphOption}
                style={{ width: '100%', height: fullscreenTop ? 'calc(100% - 30px)' : '250px' }}
                opts={{ renderer: 'canvas' }}
                notMerge={true}
              />
            )}
          </CardContent>
        </Card>
      )}

      {!fullscreenTop && (
        <Card
          key={`bottom-${fullscreenBottom}-${fullscreenTop}`}
          className={`bg-dark-card border-dark-border ${fullscreenBottom ? 'fixed inset-0 z-50 m-0 rounded-none' : 'flex-1'}`}
        >
          <CardContent className={`${fullscreenBottom ? 'h-full p-4' : 'p-3'} h-full flex flex-col`}>
            <div className="flex items-center gap-2 text-xs text-gray-400 mb-2 shrink-0">
              <Layers className="w-3 h-3 text-purple-400" />
              层内模块结构 (Treemap)
              <span className="text-gray-600">· 面积=文件数量</span>
              <div className="flex gap-0.5 ml-auto bg-dark-bg rounded p-0.5 border border-dark-border">
                {(data.treemap || []).map((l: any) => (
                  <button
                    key={l.name}
                    onClick={() => setSelectedLayer(l.name)}
                    className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                      selectedLayer === l.name ? 'bg-primary/20 text-primary' : 'text-gray-500 hover:text-gray-300'
                    }`}
                  >
                    {l.name} ({l.file_count})
                  </button>
                ))}
              </div>
              <button
                onClick={() => setFullscreenBottom(!fullscreenBottom)}
                className="p-1 rounded text-gray-500 hover:text-gray-300 transition-colors"
                title={fullscreenBottom ? '退出全屏 (ESC)' : '全屏'}
              >
                {fullscreenBottom ? <Minimize2 className="w-3 h-3" /> : <Maximize2 className="w-3 h-3" />}
              </button>
            </div>
            <div className="flex-1 min-h-[240px]">
              <ReactEChartsCore
                echarts={echarts}
                option={treemapOption}
                style={{ width: '100%', height: '100%' }}
                opts={{ renderer: 'canvas' }}
                notMerge={true}
              />
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default ArchitectureView;
