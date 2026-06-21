import React, { useEffect, useState } from 'react';

interface RouteStats {
  quality: Record<string, number>;
  latency: Record<string, { p95_s: number; congestion: number }>;
  routes: {
    total_calls: number;
    fallback_rate: number;
    avg_attempts: number;
    local_calls: number;
    external_calls: number;
    external_ratio: number;
    complexity: Record<string, number>;
    recent_logs: Array<{
      time: string; purpose: string; model: string; success: boolean;
      quality_delta?: number; latency_ms?: number; fallback?: boolean; source?: string;
    }>;
  };
  generated_at: number;
}

const API = '/api/core/models/v3-stats';

function colorCard(value: number, thresholds: [number, number][], invert: boolean = false) {
  for (const [th, color] of thresholds) {
    if (invert ? value <= th : value >= th) return color;
  }
  return '#ef4444';
}

export const LlmRouteMonitor: React.FC = () => {
  const [stats, setStats] = useState<RouteStats | null>(null);
  const [filterModel, setFilterModel] = useState('all');

  useEffect(() => {
    const fetchStats = () => {
      fetch(API).then(r => r.json()).then(setStats).catch(() => {});
    };
    fetchStats();
    const interval = setInterval(fetchStats, 10000);
    return () => clearInterval(interval);
  }, []);

  if (!stats) {
    return <div className="p-6 text-gray-500">加载中...</div>;
  }

  const r = stats.routes;
  const qualityEntry = Object.entries(stats.quality)[0]?.[1] || 0;
  const latencyVals = Object.values(stats.latency).map(l => l.p95_s);
  const avgP95 = latencyVals.length > 0 ? latencyVals.reduce((a, b) => a + b, 0) / latencyVals.length : 0;

  const filters = [
    { label: '质量 EWMA', value: qualityEntry.toFixed(3),
      color: colorCard(qualityEntry, [[0.1, '#22c55e'], [0, '#eab308']], false) },
    { label: 'P99 延迟', value: avgP95.toFixed(1) + 's',
      color: colorCard(avgP95, [[5, '#22c55e'], [10, '#eab308']], true) },
    { label: 'Fallback 率', value: (r.fallback_rate * 100).toFixed(1) + '%',
      color: colorCard(r.fallback_rate, [[0.05, '#22c55e'], [0.15, '#eab308']], true) },
    { label: 'API 占比', value: (r.external_ratio * 100).toFixed(1) + '%',
      color: colorCard(r.external_ratio, [[0.2, '#22c55e'], [0.4, '#eab308']], true) },
  ];

  const compEntries = Object.entries(r.complexity || {});
  const compTotal = compEntries.reduce((s, [, v]) => s + (v as number), 0) || 1;

  const filteredLogs = filterModel === 'all'
    ? r.recent_logs
    : r.recent_logs.filter(l => l.model === filterModel);
  const uniqueModels = [...new Set(r.recent_logs.map(l => l.model))];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-100">LLM 路由监控 v3.0</h1>
          <p className="text-sm text-gray-500 mt-1">质量反馈、延迟退让、成本效率</p>
        </div>
        <span className="text-xs text-gray-600">
          自动刷新 (10s) · 调用 {r.total_calls} 次
        </span>
      </div>

      {/* 4 Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        {filters.map(f => (
          <div key={f.label} className="bg-dark-card rounded-lg border border-dark-border p-4 text-center">
            <div className="text-xs text-gray-500 mb-1">{f.label}</div>
            <div className="text-2xl font-bold" style={{ color: f.color }}>{f.value}</div>
          </div>
        ))}
      </div>

      {/* Complexity Distribution */}
      <div className="bg-dark-card rounded-lg border border-dark-border p-4">
        <div className="text-sm text-gray-300 mb-3">复杂度分布</div>
        <div className="flex h-6 rounded overflow-hidden">
          {compEntries.map(([k, v]) => {
            const pct = ((v as number) / compTotal * 100).toFixed(0);
            const colors: Record<string, string> = { simple: '#22c55e', medium: '#eab308', complex: '#ef4444' };
            return (
              <div key={k} title={`${k}: ${v} (${pct}%)`}
                className="flex items-center justify-center text-[10px] text-white"
                style={{ width: `${pct}%`, backgroundColor: colors[k] || '#6b7280', minWidth: '30px' }}>
                {k} {pct}%
              </div>
            );
          })}
        </div>
      </div>

      {/* Recent Logs */}
      <div className="bg-dark-card rounded-lg border border-dark-border p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm text-gray-300">最近路由日志</div>
          <select value={filterModel} onChange={e => setFilterModel(e.target.value)}
            className="h-7 px-2 bg-dark-bg border border-dark-border rounded text-xs text-gray-300">
            <option value="all">全部模型</option>
            {uniqueModels.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        <div className="space-y-1 max-h-48 overflow-auto">
          {filteredLogs.map((log, i) => (
            <div key={i} className="flex items-center gap-3 text-xs p-1.5 rounded bg-dark-bg">
              <span className="text-gray-500 w-14">{log.time}</span>
              <span className="text-gray-300 w-20 truncate" title={log.model}>{log.model}</span>
              <span className={log.fallback ? 'text-yellow-400' : 'text-green-400'}>
                {log.fallback ? '✗ →' : '✓'}
              </span>
              {log.quality_delta !== undefined && (
                <span className={`w-12 text-right ${log.quality_delta >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  {log.quality_delta > 0 ? '+' : ''}{log.quality_delta.toFixed(2)}
                </span>
              )}
              {log.latency_ms !== undefined && (
                <span className="text-gray-500 w-16 text-right">{(log.latency_ms / 1000).toFixed(1)}s</span>
              )}
              <span className="text-gray-600 w-8">{log.source === 'local' ? '本地' : 'API'}</span>
              <span className="text-gray-500 w-12 truncate">{log.purpose}</span>
            </div>
          ))}
          {filteredLogs.length === 0 && (
            <div className="text-xs text-gray-600 py-4 text-center">暂无日志，等待 LLM 调用...</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default LlmRouteMonitor;
