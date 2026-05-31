import React, { useEffect, useRef, useMemo } from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { GraphChart } from 'echarts/charts';
import { TooltipComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([GraphChart, TooltipComponent, LegendComponent, CanvasRenderer]);

interface Props {
  data: any;
  selectedNode: string | null;
  onNodeSelect: (id: string) => void;
  searchQuery: string;
  tab: 'code' | 'capability' | 'wiki' | 'architecture';
  activeLayers?: Set<string>;
  diffNodes?: Set<string>;
}

const GraphCanvas = React.forwardRef<any, Props>(({ data, selectedNode, onNodeSelect, searchQuery, tab, activeLayers, diffNodes }, ref) => {
  const option = useMemo(() => {
    if (!data?.nodes) return {};

    const nodes = data.nodes
      .filter((n: any) => !activeLayers || activeLayers.size === 0 || activeLayers.has(n.category))
      .map((n: any) => ({
      id: n.id,
      name: n.name,
      category: data.categories?.findIndex((c: any) => c.name === n.category) ?? 0,
      symbolSize: n.symbolSize || 15,
      itemStyle: {
        color: n.itemStyle?.color || (data.categories?.[0]?.itemStyle?.color || '#8b5cf6'),
        borderColor: selectedNode === n.id ? '#fff' : 'transparent',
        borderWidth: selectedNode === n.id ? 2 : 0,
      },
      label: {
        show: true,
        fontSize: 9,
        formatter: n.name,
        overflow: 'truncate',
        width: 60,
      },
      ...n,
    }));

    const filteredNodeIds = new Set(nodes.map((n: any) => n.id));
    const links = (data.links || [])
      .filter((l: any) => filteredNodeIds.has(l.source) && filteredNodeIds.has(l.target))
      .map((l: any) => ({
      source: l.source,
      target: l.target,
      lineStyle: { color: '#374151', opacity: 0.4, curveness: 0.1 },
      label: l.label ? { show: false, formatter: l.label } : undefined,
    }));

    const searchSet = new Set<string>();
    if (searchQuery && searchQuery.length >= 2) {
      nodes.forEach((n: any) => {
        if (n.fullName?.toLowerCase().includes(searchQuery.toLowerCase()) ||
            n.name?.toLowerCase().includes(searchQuery.toLowerCase())) {
          searchSet.add(n.id);
        }
      });
    }

    return {
      tooltip: {
        formatter: (params: any) => {
          if (params.dataType === 'node') {
            return `<div style="max-width:300px;font-size:11px">
              <b>${params.data.fullName || params.name}</b><br/>
              类型: ${params.data.category}<br/>
              入度: ${params.data.inDegree ?? '—'} / 出度: ${params.data.outDegree ?? '—'}
              ${params.data.issueCount ? `<br/>⚠️ ${params.data.issueCount} issues` : ''}
            </div>`;
          }
          return '';
        },
      },
      series: [{
        type: 'graph',
        layout: 'force',
        force: {
          repulsion: tab === 'code' ? 150 : tab === 'capability' ? 300 : 200,
          gravity: 0.08,
          edgeLength: tab === 'code' ? [80, 250] : tab === 'capability' ? [100, 200] : [120, 200],
          layoutAnimation: true,
        },
        roam: true,
        draggable: true,
        data: nodes.map((n: any) => ({
          ...n,
          itemStyle: {
            ...n.itemStyle,
            opacity: searchSet.size > 0 && !searchSet.has(n.id) ? 0.15 : 1,
            borderColor: diffNodes?.has(n.id) ? '#f59e0b' : (selectedNode === n.id ? '#fff' : (n.itemStyle?.borderColor || 'transparent')),
            borderWidth: diffNodes?.has(n.id) ? 2 : (selectedNode === n.id ? 2 : (n.itemStyle?.borderWidth || 0)),
          },
        })),
        links,
        categories: data.categories || [],
        emphasis: {
          focus: 'adjacency',
          itemStyle: { borderWidth: 2, borderColor: '#fff' },
        },
        lineStyle: { color: '#4b5563', opacity: 0.3, curveness: 0.1 },
        label: { show: tab === 'code' || tab === 'wiki', fontSize: 9, color: '#9ca3af' },
      }],
    };
  }, [data, selectedNode, searchQuery, tab, activeLayers, diffNodes]);

  const onEvents = useMemo(() => ({
    click: (params: any) => {
      if (params.dataType === 'node' && params.data?.id) {
        onNodeSelect(params.data.id);
      }
    },
  }), [onNodeSelect]);

  return (
    <ReactEChartsCore
      ref={ref}
      echarts={echarts}
      option={option}
      style={{ width: '100%', height: '100%' }}
      opts={{ renderer: 'canvas' }}
      onEvents={onEvents}
      notMerge={true}
      lazyUpdate={true}
    />
  );
});

export default GraphCanvas;
