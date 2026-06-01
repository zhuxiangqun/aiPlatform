import React, { useMemo } from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { TooltipComponent, GridComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { Card, CardContent } from '../../components/ui';
import { TrendingUp } from 'lucide-react';

echarts.use([LineChart, TooltipComponent, GridComponent, LegendComponent, CanvasRenderer]);

interface HistoryEntry {
  run_id: string;
  started_at: string;
  overall_score: number;
  overall_grade: string;
  duration_ms: number;
  pass: number;
  warn: number;
  fail: number;
}

interface Props {
  history: HistoryEntry[];
}

const DiagnosticTrendChart: React.FC<Props> = ({ history }) => {
  const option = useMemo(() => {
    if (!history || history.length < 2) return null;

    const data = history.map((h: HistoryEntry) => [
      new Date(h.started_at).getTime(),
      h.overall_score,
    ]);

    const passData = history.map((h: HistoryEntry) => {
      const total = (h.pass || 0) + (h.warn || 0) + (h.fail || 0) || 1;
      return [new Date(h.started_at).getTime(), Math.round(h.pass / total * 100)];
    });
    const warnData = history.map((h: HistoryEntry) => {
      const total = (h.pass || 0) + (h.warn || 0) + (h.fail || 0) || 1;
      return [new Date(h.started_at).getTime(), Math.round(h.warn / total * 100)];
    });
    const failData = history.map((h: HistoryEntry) => {
      const total = (h.pass || 0) + (h.warn || 0) + (h.fail || 0) || 1;
      return [new Date(h.started_at).getTime(), Math.round(h.fail / total * 100)];
    });

    return {
      tooltip: {
        trigger: 'axis' as const,
        backgroundColor: '#161B22',
        borderColor: '#30363D',
        textStyle: { color: '#c9d1d9', fontSize: 11 },
        formatter: (params: any) => {
          const h = history[params[0].dataIndex];
          const grade = h?.overall_grade || '?';
          let html = `<div style="font-size:12px;font-weight:600">评分: ${h?.overall_score ?? '?'} (${grade})</div>`;
          for (const p of params) {
            const v = Array.isArray(p.value) ? p.value[1] : p.value;
            let val = String(v);
            if (p.seriesName === '通过%' || p.seriesName === '警告%' || p.seriesName === '失败%') {
              const count = p.seriesName === '通过%' ? h?.pass : p.seriesName === '警告%' ? h?.warn : h?.fail;
              val = `${v}% (${count}项)`;
            }
            html += `<div style="font-size:10px">${p.marker} ${p.seriesName}: ${val}</div>`;
          }
          return html;
        },
      },
      legend: {
        top: 0,
        textStyle: { color: '#8b949e', fontSize: 10 },
        data: ['综合评分', '通过%', '警告%', '失败%'],
      },
      grid: { top: 30, right: 16, bottom: 24, left: 40 },
      xAxis: {
        type: 'time' as const,
        axisLine: { lineStyle: { color: '#30363d' } },
        axisLabel: { color: '#8b949e', fontSize: 9, formatter: (v: number) => {
          const d = new Date(v);
          return `${d.getMonth()+1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2,'0')}`;
        }},
      },
      yAxis: {
        type: 'value' as const,
        min: 0,
        max: 100,
        axisLine: { lineStyle: { color: '#30363d' } },
        axisLabel: { color: '#8b949e', fontSize: 9 },
        splitLine: { lineStyle: { color: '#21262d' } },
      },
      series: [
        {
          name: '综合评分',
          type: 'line',
          data,
          smooth: true,
          lineStyle: { color: '#58a6ff', width: 2 },
          itemStyle: { color: '#58a6ff' },
          symbol: 'circle',
          symbolSize: 4,
        },
        {
          name: '通过%',
          type: 'line',
          data: passData,
          lineStyle: { color: '#3fb950', width: 1, type: 'dashed' as const },
          itemStyle: { color: '#3fb950' },
          symbol: 'none',
        },
        {
          name: '警告%',
          type: 'line',
          data: warnData,
          lineStyle: { color: '#d29922', width: 1, type: 'dashed' as const },
          itemStyle: { color: '#d29922' },
          symbol: 'none',
        },
        {
          name: '失败%',
          type: 'line',
          data: failData,
          lineStyle: { color: '#f85149', width: 1, type: 'dashed' as const },
          itemStyle: { color: '#f85149' },
          symbol: 'none',
        },
      ],
    };
  }, [history]);

  if (!option) return null;

  return (
    <Card className="bg-dark-card border-dark-border">
      <CardContent className="p-3">
        <div className="flex items-center gap-2 text-xs text-gray-400 mb-2">
          <TrendingUp className="w-3 h-3 text-emerald-400" />
          诊断趋势 <span className="text-gray-600">· 最近 {history.length} 次</span>
        </div>
        <ReactEChartsCore
          echarts={echarts}
          option={option}
          style={{ width: '100%', height: '180px' }}
          opts={{ renderer: 'canvas' }}
          notMerge={true}
          lazyUpdate={true}
        />
      </CardContent>
    </Card>
  );
};

export default DiagnosticTrendChart;
