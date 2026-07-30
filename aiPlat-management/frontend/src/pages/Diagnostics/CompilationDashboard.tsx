/**
 * CompilationDashboard — 知识编译仪表盘 (Karpathy LLM Wiki 对齐)
 *
 * 三层可视化:
 *   1. 总量层 — 文档数/Wiki页数/实体数/关系数
 *   2. 效率层 — RAG vs Wiki Token 对比折线图
 *   3. ROI 层 — 累积节省 Token + 折合成本
 */
import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { BookOpen, TrendingUp, Zap, DollarSign, Database, FileText, RefreshCw } from 'lucide-react';

const API_BASE = '/api/platform/apps/fde';

interface ROISummary {
  total_queries: number;
  total_rag_tokens: number;
  total_wiki_tokens: number;
  total_saved_tokens: number;
  avg_saved_percent: number;
  estimated_cost_saved: number;
  by_domain: Record<string, { queries: number; saved_tokens: number; avg_saved_pct: number }>;
  trend: Array<{ day: string; queries: number; saved_tokens: number }>;
}

const CompilationDashboard: React.FC = () => {
  const [roi, setRoi] = useState<ROISummary | null>(null);
  const [okfResult, setOkfResult] = useState<any>(null);
  const [domain, setDomain] = useState('ai-knowledge');
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(false);

  const loadRoi = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API_BASE}/knowledge/roi?domain_id=${domain}&days=${days}`);
      setRoi(await r.json());
    } catch {}
    setLoading(false);
  };

  const exportOkf = async () => {
    try {
      const r = await fetch(`${API_BASE}/knowledge/export-okf`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain_id: domain, incremental: false }),
      });
      setOkfResult(await r.json());
    } catch {}
  };

  useEffect(() => { loadRoi(); }, [domain, days]);

  const formatTokens = (n: number) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">知识编译</h2>
          <p className="text-xs text-gray-500">Karpathy LLM Wiki — 编译效率·Token节省·ROI</p>
        </div>
        <div className="flex items-center gap-2">
          <input className="bg-gray-800 border border-gray-700 text-gray-300 text-xs rounded px-2 py-1 w-32"
            value={domain} onChange={e => setDomain(e.target.value)} placeholder="domain" />
          <select value={days} onChange={e => setDays(Number(e.target.value))}
            className="bg-gray-800 border border-gray-700 text-gray-300 text-xs rounded px-2 py-1">
            <option value={7}>7天</option><option value={30}>30天</option><option value={90}>90天</option>
          </select>
          <Button variant="ghost" size="sm" onClick={loadRoi}><RefreshCw className="w-3 h-3" /></Button>
          <Button variant="default" size="sm" onClick={exportOkf}>导出 OKF</Button>
        </div>
      </div>

      {/* Layer 1: 编译总量 */}
      {roi && (
        <div className="grid grid-cols-4 gap-3">
          <Card className="border-gray-700/50"><CardContent className="p-3 text-center">
            <div className="text-xl font-bold text-blue-400">{roi.total_queries}</div>
            <div className="text-[10px] text-gray-500">总查询数</div>
          </CardContent></Card>
          <Card className="border-gray-700/50"><CardContent className="p-3 text-center">
            <div className="text-xl font-bold text-orange-400">{formatTokens(roi.total_rag_tokens)}</div>
            <div className="text-[10px] text-gray-500">RAG 模式 Token</div>
          </CardContent></Card>
          <Card className="border-gray-700/50"><CardContent className="p-3 text-center">
            <div className="text-xl font-bold text-green-400">{formatTokens(roi.total_wiki_tokens)}</div>
            <div className="text-[10px] text-gray-500">Wiki 模式 Token</div>
          </CardContent></Card>
          <Card className="border-gray-700/50"><CardContent className="p-3 text-center">
            <div className="text-xl font-bold text-purple-400">{roi.avg_saved_percent}%</div>
            <div className="text-[10px] text-gray-500">平均节省</div>
          </CardContent></Card>
        </div>
      )}

      {/* Layer 2: 效率对比 */}
      {roi && roi.total_queries > 0 && (
        <Card className="border-gray-700/50">
          <CardHeader><span className="text-sm font-medium text-gray-200">Token 效率对比</span></CardHeader>
          <CardContent>
            <div className="flex items-center gap-4 mb-3">
              <div className="flex-1">
                <div className="text-xs text-gray-500 mb-1">RAG 模式</div>
                <div className="h-3 bg-gray-800 rounded overflow-hidden">
                  <div className="h-full bg-orange-500 rounded" style={{ width: '100%' }} />
                </div>
                <div className="text-[10px] text-orange-400 mt-0.5">{formatTokens(roi.total_rag_tokens)} tokens</div>
              </div>
              <span className="text-gray-600 text-xs">→</span>
              <div className="flex-1">
                <div className="text-xs text-gray-500 mb-1">Wiki 模式</div>
                <div className="h-3 bg-gray-800 rounded overflow-hidden">
                  <div className="h-full bg-green-500 rounded" style={{ width: `${Math.max(5, (roi.total_wiki_tokens / Math.max(roi.total_rag_tokens, 1)) * 100)}%` }} />
                </div>
                <div className="text-[10px] text-green-400 mt-0.5">{formatTokens(roi.total_wiki_tokens)} tokens</div>
              </div>
            </div>
            <div className="text-center text-sm">
              <span className="text-gray-400">节省 </span>
              <span className="text-green-400 font-bold">{formatTokens(roi.total_saved_tokens)} tokens</span>
              <span className="text-gray-500 ml-2">({roi.avg_saved_percent}%)</span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Layer 3: ROI 累积 */}
      {roi && roi.total_saved_tokens > 0 && (
        <Card className="border-green-500/20">
          <CardHeader>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-200">知识复利 ROI</span>
              <span className="text-xs text-gray-500">{days} 天累积</span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-4 text-center mb-4">
              <div>
                <div className="text-2xl font-bold text-green-400">{formatTokens(roi.total_saved_tokens)}</div>
                <div className="text-[10px] text-gray-500">累积节省 Token</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-purple-400">{roi.avg_saved_percent}%</div>
                <div className="text-[10px] text-gray-500">平均节省率</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-yellow-400">¥{roi.estimated_cost_saved.toFixed(2)}</div>
                <div className="text-[10px] text-gray-500">折合成本节省</div>
              </div>
            </div>

            {/* 趋势图 */}
            {roi.trend.length > 0 && (
              <div>
                <div className="text-xs text-gray-500 mb-2">每日节省趋势</div>
                <div className="flex items-end gap-1 h-24">
                  {roi.trend.map((t, i) => {
                    const maxSaved = Math.max(...roi!.trend.map(x => x.saved_tokens), 1);
                    const height = (t.saved_tokens / maxSaved) * 100;
                    return (
                      <div key={i} className="flex-1 flex flex-col items-center" title={`${t.day}: ${formatTokens(t.saved_tokens)} tokens`}>
                        <div className="w-full bg-green-500/30 rounded-t" style={{ height: `${Math.max(height, 2)}%` }} />
                        <div className="text-[8px] text-gray-600 mt-0.5">{t.day.slice(5)}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 按域分解 */}
            {Object.keys(roi.by_domain).length > 0 && (
              <div className="mt-4 pt-3 border-t border-gray-700/50">
                <div className="text-xs text-gray-500 mb-2">按域分解</div>
                {Object.entries(roi.by_domain).map(([d, v]) => (
                  <div key={d} className="flex items-center justify-between text-xs py-1">
                    <span className="text-gray-300">{d}</span>
                    <div className="flex gap-3">
                      <span className="text-gray-500">{v.queries} 查询</span>
                      <span className="text-green-400">{formatTokens(v.saved_tokens)} 节省</span>
                      <span className="text-blue-400">{v.avg_saved_pct}%</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* OKF Export Result */}
      {okfResult && (
        <Card className="border-blue-500/20">
          <CardContent className="p-3">
            <div className="text-xs text-blue-400">
              导出完成: {okfResult.exported} 文件 → {okfResult.dir}
              {okfResult.skipped > 0 && <span className="text-gray-500 ml-2">(跳过 {okfResult.skipped})</span>}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Empty state */}
      {!loading && (!roi || roi.total_queries === 0) && (
        <Card className="border-dashed border-gray-700">
          <CardContent className="p-8 text-center">
            <div className="text-gray-600 mb-2"><BookOpen className="w-8 h-8 mx-auto" /></div>
            <div className="text-sm text-gray-500">暂无编译数据</div>
            <div className="text-xs text-gray-600 mt-1">运行知识查询后，ROI 数据将自动累积</div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default CompilationDashboard;
