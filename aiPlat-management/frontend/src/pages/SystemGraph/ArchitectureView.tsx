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

const ArchitectureView: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [selectedLayer, setSelectedLayer] = useState<string>('core');
  const [fullscreenTop, setFullscreenTop] = useState(false);
  const [fullscreenBottom, setFullscreenBottom] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setFullscreenTop(false); setFullscreenBottom(false); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    fetch('/api/core/knowledge-graph/architecture')
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  const graphOption = useMemo(() => {
    if (!data?.sankey) return {};
    const layers = data.sankey.nodes;
    const flows = data.sankey.links || [];

    const maxVal = Math.max(1, ...flows.map((f: any) => f.value));

    const gNodes = layers.map((n: any) => ({
      id: n.name,
      name: n.name,
      symbolSize: 50,
      itemStyle: { color: LAYER_COLORS[n.name] || '#9ca3af' },
      label: { show: true, fontSize: 12, color: '#c9d1d9' },
    }));

    // Use allLinks with reverse edges to avoid overlap
    const seen: Record<string, boolean> = {};
    const allLinks = [];
    for (const f of flows) {
      const pairKey = [f.source, f.target].sort().join('↔');
      if (seen[pairKey]) {
        allLinks.push({ ...f, source: f.source, target: f.target, label: { show: true, formatter: f.value.toLocaleString(), fontSize: 9, color: '#8b949e' },
          lineStyle: { color: LAYER_COLORS[f.source] || '#9ca3af', opacity: 0.3 + (f.value/maxVal)*0.5, width: 0.5 + (f.value/maxVal)*4, curveness: -0.3 } });
      } else {
        seen[pairKey] = true;
        allLinks.push({ ...f, source: f.source, target: f.target, label: { show: true, formatter: f.value.toLocaleString(), fontSize: 9, color: '#8b949e' },
          lineStyle: { color: LAYER_COLORS[f.source] || '#9ca3af', opacity: 0.3 + (f.value/maxVal)*0.5, width: 0.5 + (f.value/maxVal)*4, curveness: 0.3 } });
      }
    }

    return {
      tooltip: {
        backgroundColor: '#161B22', borderColor: '#30363D',
        textStyle: { color: '#c9d1d9', fontSize: 11 },
        formatter: (p: any) => {
          return `${p.data.source || ''} → ${p.data.target || ''}<br/>${p.data.label?.formatter || p.data.value} interactions`;
        },
      },
      series: [{
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        force: { repulsion: 500, gravity: 0.1, edgeLength: [200, 400] },
        data: gNodes,
        links: allLinks,
        emphasis: { focus: 'adjacency' },
      }],
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
      series: [{
        type: 'treemap',
        name: selectedLayer,
        data: layer.children,
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
      }],
      visualMap: {
        show: false,
        min: 0,
        max: layer.children.reduce((m: number, c: any) => Math.max(m, c.value || (c.children ? c.children.length : 5)), 5) || 100,
        inRange: { color: [LAYER_COLORS[selectedLayer] + '20', LAYER_COLORS[selectedLayer]] },
      },
    };
  }, [data, selectedLayer]);

  if (!data) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500 text-sm">
        加载架构数据...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full gap-3 p-3 overflow-auto relative">
      {/* Top: Cross-layer dependency graph */}
      {!fullscreenBottom && (
      <Card key={`top-${fullscreenTop}-${fullscreenBottom}`} className={`bg-dark-card border-dark-border ${fullscreenTop ? 'fixed inset-0 z-50 m-0 rounded-none' : 'shrink-0'}`}>
        <CardContent className={`${fullscreenTop ? 'h-full p-4' : 'p-3'} flex flex-col`}>
          <div className="flex items-center gap-2 text-xs text-gray-400 mb-2 shrink-0">
             <TrendingUp className="w-3 h-3 text-blue-400" />
             层间依赖流
             <span className="text-gray-600">· import edges only · 真实架构依赖</span>
             <button
               onClick={() => setFullscreenTop(!fullscreenTop)}
               className="ml-auto p-1 rounded text-gray-500 hover:text-gray-300 transition-colors"
               title={fullscreenTop ? '退出全屏 (ESC)' : '全屏'}
             >
               {fullscreenTop ? <Minimize2 className="w-3 h-3" /> : <Maximize2 className="w-3 h-3" />}
             </button>
           </div>
           {(data.sankey?.links || []).length === 0 ? (
             <div className="flex-1 flex items-center justify-center">
               <div className="text-center">
                 <span className="text-2xl">✅</span>
                 <p className="text-sm text-green-400 mt-2 font-medium">无跨层导入违规</p>
                 <p className="text-xs text-gray-500 mt-1">app → platform → core → infra 单向依赖链</p>
                 <p className="text-xs text-gray-600 mt-1">跨层通信通过 HTTP API，符合架构设计规范</p>
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


      {/* Bottom: Treemap */}
      {!fullscreenTop && (
      <Card key={`bottom-${fullscreenBottom}-${fullscreenTop}`} className={`bg-dark-card border-dark-border ${fullscreenBottom ? 'fixed inset-0 z-50 m-0 rounded-none' : 'flex-1'}`}>
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
                    selectedLayer === l.name
                      ? 'bg-primary/20 text-primary'
                      : 'text-gray-500 hover:text-gray-300'
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
          <div className="flex-1">
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
