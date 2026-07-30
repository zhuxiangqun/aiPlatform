/**
 * EvoXPanel — 蜂群执行面板 (EvoMap EvoX 对齐)
 *
 * 一键执行 EvoX 蜂群流水线: 拆分 → 并行执行 → 汇合 → 损耗检测
 */
import React, { useState } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import { Play, CheckCircle, XCircle, Target, TrendingUp, AlertTriangle, Zap } from 'lucide-react';

const API_BASE = '/api/platform/apps/fde';

const EvoXPanel: React.FC = () => {
  const [task, setTask] = useState('');
  const [maxAtoms, setMaxAtoms] = useState(30);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const run = async () => {
    if (!task.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const r = await fetch(`${API_BASE}/evo/execute`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task, max_atoms: maxAtoms, parallel_limit: 10 }),
      });
      setResult(await r.json());
    } catch (e: any) { toast?.error?.(e?.message || '执行失败'); }
    setLoading(false);
  };

  const lossRateColor = (rate: number) => {
    if (rate <= 5) return 'text-green-400';
    if (rate <= 20) return 'text-yellow-400';
    return 'text-red-400';
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">蜂群推演</h2>
          <p className="text-xs text-gray-500">拆分 → 并行执行 → 结构化汇合 → 损耗检测</p>
        </div>
      </div>

      <Card className="border-gray-700/50">
        <CardContent className="p-3 space-y-3">
          <textarea className="w-full h-24 bg-gray-800 border border-gray-700 rounded p-2 text-sm text-gray-200 resize-y"
            value={task} onChange={e => setTask(e.target.value)}
            placeholder="描述复杂任务，如: 分析563道题目（100逻辑+250数学+63竞赛数学+150物理），计算每题的正确答案" />
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">最大原子数:</span>
            <input type="number" className="w-16 bg-gray-800 border border-gray-700 text-gray-300 text-xs rounded px-1 py-0.5"
              value={maxAtoms} onChange={e => setMaxAtoms(parseInt(e.target.value) || 30)} />
            <Button variant="default" size="sm" onClick={run} loading={loading}>
              <Zap className="w-3 h-3 mr-1" />执行蜂群
            </Button>
          </div>
        </CardContent>
      </Card>

      {result && (
        <>
          <div className="grid grid-cols-4 gap-3">
            <Card className="border-gray-700/50"><CardContent className="p-3 text-center">
              <div className="text-xl font-bold text-blue-400">{result.atom_count}</div>
              <div className="text-[10px] text-gray-500">原子任务</div>
            </CardContent></Card>
            <Card className="border-gray-700/50"><CardContent className="p-3 text-center">
              <div className="text-xl font-bold text-green-400">{result.collected_count}</div>
              <div className="text-[10px] text-gray-500">成功收集</div>
            </CardContent></Card>
            <Card className="border-gray-700/50"><CardContent className="p-3 text-center">
              <div className={`text-xl font-bold ${lossRateColor(result.loss_analysis?.loss_rate || 0)}`}>
                {result.loss_analysis?.loss_rate || 0}%
              </div>
              <div className="text-[10px] text-gray-500">损耗率</div>
            </CardContent></Card>
            <Card className="border-gray-700/50"><CardContent className="p-3 text-center">
              <div className="text-xl font-bold text-gray-200">{(result.total_time_ms / 1000).toFixed(1)}s</div>
              <div className="text-[10px] text-gray-500">总耗时</div>
            </CardContent></Card>
          </div>

          {result.loss_analysis?.loss_count > 0 && (
            <Card className="border-red-500/20">
              <CardHeader><span className="text-sm font-medium text-red-400">损耗分析</span></CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 gap-4 text-center mb-3">
                  <div><div className="text-green-400 text-lg font-bold">{result.loss_analysis.total_correct_in_atoms}</div><div className="text-[10px] text-gray-500">原子阶段正确</div></div>
                  <div><ArrowRight className="w-5 h-5 text-gray-600 mx-auto" /></div>
                  <div><div className="text-red-400 text-lg font-bold">{result.loss_analysis.total_correct_in_final}</div><div className="text-[10px] text-gray-500">汇总后剩余</div></div>
                </div>
                <div className="text-center text-sm mb-2">
                  保留率: <span className="font-bold text-yellow-400">{result.loss_analysis.retention_rate}%</span>
                  <span className="text-gray-500 ml-2">| 丢失: <span className="text-red-400">{result.loss_analysis.loss_count} 个正确答案</span></span>
                </div>
                {result.loss_analysis.root_causes?.length > 0 && (
                  <div className="space-y-1 mt-2 pt-2 border-t border-gray-700/50">
                    <div className="text-xs text-gray-400">根因:</div>
                    {result.loss_analysis.root_causes.map((c: string, i: number) => (
                      <div key={i} className="text-[10px] text-orange-400 flex items-center gap-1">
                        <AlertTriangle className="w-3 h-3" />{c}
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          <div className="text-xs text-gray-400">{result.summary}</div>
        </>
      )}
    </div>
  );
};

export default EvoXPanel;

// ArrowRight icon for loss analysis
const ArrowRight: React.FC<{ className?: string; size?: number }> = ({ className, size = 16 }) => (
  <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
  </svg>
);
