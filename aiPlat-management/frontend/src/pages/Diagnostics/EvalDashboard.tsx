import { useEffect, useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, BarChart3, Trophy, TrendingUp, Zap, Brain, Activity } from 'lucide-react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { LineChart, BarChart } from 'echarts/charts';
import { TooltipComponent, GridComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { Card, CardContent, CardHeader } from '../../components/ui';

echarts.use([LineChart, BarChart, TooltipComponent, GridComponent, LegendComponent, CanvasRenderer]);

interface EvalSummary {
  arena: { leaderboard: any[]; total_matches: number };
  regression: { history: any[] };
  ab_scores: { templates: number; items: any[] };
  evolution: { generations: number; latest_fitness: number; trend: any[] };
  observability: { token_efficiency_pct: number; llm_success_rate: number; avg_latency_ms: number; total_calls: number };
  diagnostic_trend: { current_score: number; current_grade: string; score_trend: any[] };
  stage_rewards: { total_stages: number; by_stage: Record<string, { recent: any[]; avg_reward: number }> };
}

const EvalDashboard: React.FC = () => {
  const [data, setData] = useState<EvalSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/core/diagnostics/eval/summary')
      .then(r => r.json())
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const scoreChart = useMemo(() => {
    if (!data?.diagnostic_trend?.score_trend?.length) return null;
    return {
      tooltip: { trigger: 'axis' as const },
      grid: { top: 10, right: 10, bottom: 20, left: 40 },
      xAxis: { type: 'category' as const, data: data.diagnostic_trend.score_trend.map((h: any) =>
        h.started_at ? new Date(h.started_at).toLocaleDateString() : '').slice(-15),
        axisLabel: { fontSize: 9, color: '#8b949e' } },
      yAxis: { type: 'value' as const, min: 0, max: 100, axisLabel: { fontSize: 9, color: '#8b949e' } },
      series: [{
        name: '评分', type: 'line', data: data.diagnostic_trend.score_trend.map((h: any) => h.overall_score || 0),
        smooth: true, lineStyle: { color: '#58a6ff', width: 2 }, itemStyle: { color: '#58a6ff' }, symbol: 'circle', symbolSize: 3,
      }],
    };
  }, [data]);

  const fitnessChart = useMemo(() => {
    if (!data?.evolution?.trend?.length) return null;
    return {
      tooltip: { trigger: 'axis' as const },
      grid: { top: 10, right: 10, bottom: 20, left: 40 },
      xAxis: { type: 'category' as const, data: data.evolution.trend.map((e: any) => `Gen ${e.id}`),
        axisLabel: { fontSize: 9, color: '#8b949e' } },
      yAxis: { type: 'value' as const, min: 0, max: 1, axisLabel: { fontSize: 9, color: '#8b949e' } },
      series: [{
        name: 'Fitness', type: 'line', data: data.evolution.trend.map((e: any) => e.fitness || 0),
        smooth: true, lineStyle: { color: '#3fb950', width: 2 }, areaStyle: { color: 'rgba(63,185,80,0.1)' },
        itemStyle: { color: '#3fb950' }, symbol: 'circle', symbolSize: 3,
      }],
    };
  }, [data]);

  if (loading) return <div className="p-6 text-gray-400">加载中...</div>;

  return (
    <div className="space-y-6 p-4">
      <div>
        <h1 className="text-2xl font-semibold text-gray-200">Eval Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">统一评估指标：Arena 排名 · AB 评分 · 进化适应度 · Token 效率</p>
      </div>

      <Link to="/diagnostics" className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 transition-colors">
        <ArrowLeft className="w-3 h-3" />返回诊断中心
      </Link>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Arena Leaderboard */}
        <Card className="bg-dark-card border-dark-border">
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
              <Trophy className="w-4 h-4 text-yellow-400" />
              Arena 排行榜 {data?.arena.total_matches ? `· ${data.arena.total_matches} 场` : ''}
            </div>
          </CardHeader>
          <CardContent>
            {(data?.arena?.leaderboard || []).length > 0 ? (
              <div className="space-y-2 text-xs">
                {(data.arena.leaderboard || []).slice(0, 5).map((p: any, i: number) => (
                  <div key={p.name} className="flex justify-between items-center">
                    <span className="text-gray-300">#{i + 1} {p.name}</span>
                    <span className="text-gray-400">{p.rating} Elo · {p.matches} 场</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-500">尚未运行 Arena。POST /diagnostics/arena/run 触发</p>
            )}
            {(data?.regression?.history || []).length > 0 && (
              <div className="mt-3 pt-3 border-t border-dark-border/50 text-xs text-gray-400">
                <div className="text-gray-500 mb-1">最近回归</div>
                {data.regression.history.map((r: any, i: number) => (
                  <div key={i} className={r.verdict === 'PASS' ? 'text-green-400' : r.verdict === 'REGRESSION' ? 'text-red-400' : 'text-yellow-400'}>
                    #{i + 1} {r.verdict} (pass_rate={r.pass_rate}%, {r.total_tasks} tasks)
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Token Efficiency */}
        <Card className="bg-dark-card border-dark-border">
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
              <Zap className="w-4 h-4 text-blue-400" />
              Token 效率 (24h)
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-gray-500">LLM 调用</span>
                <span className="text-gray-300">{data?.observability?.total_calls ?? '—'} 次</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">成功率</span>
                <span className={data?.observability?.llm_success_rate === 100 ? 'text-green-400' : 'text-yellow-400'}>
                  {data?.observability?.llm_success_rate ?? '—'}%
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">平均延迟</span>
                <span className="text-gray-300">{data?.observability?.avg_latency_ms?.toFixed(0) ?? '—'}ms</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Token 效率</span>
                <span className={(data?.observability?.token_efficiency_pct ?? 0) >= 30 ? 'text-green-400' : 'text-yellow-400'}>
                  {data?.observability?.token_efficiency_pct ?? '—'}%
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Evolution Fitness */}
        <Card className="bg-dark-card border-dark-border">
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
              <TrendingUp className="w-4 h-4 text-green-400" />
              进化适应度 {data?.evolution ? `· ${data.evolution.generations} 代` : ''}
            </div>
          </CardHeader>
          <CardContent>
            {fitnessChart ? (
              <ReactEChartsCore echarts={echarts} option={fitnessChart}
                style={{ width: '100%', height: '160px' }} notMerge lazyUpdate />
            ) : (
              <p className="text-xs text-gray-500">尚未运行进化</p>
            )}
            {data?.evolution?.latest_fitness ? (
              <div className="text-xs text-gray-400 mt-1">
                最新适应度: <span className="text-green-400">{data.evolution.latest_fitness.toFixed(2)}</span>
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* AB Scores */}
        <Card className="bg-dark-card border-dark-border">
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
              <Brain className="w-4 h-4 text-purple-400" />
              AB 评分 {data?.ab_scores ? `· ${data.ab_scores.templates} 模板` : ''}
            </div>
          </CardHeader>
          <CardContent>
            {(data?.ab_scores?.items || []).length > 0 ? (
              <div className="space-y-2 text-xs">
                {data.ab_scores.items.slice(0, 5).map((s: any) => (
                  <div key={s.template_id + s.version} className="flex justify-between">
                    <span className="text-gray-300">{s.template_id} v{s.version}</span>
                    <span className={s.avg_score >= 75 ? 'text-green-400' : s.avg_score >= 50 ? 'text-yellow-400' : 'text-red-400'}>
                      {s.avg_score} ({s.eval_count} 次)
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-500">暂无 AB 评分数据</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Stage Rewards */}
      {data?.stage_rewards && data.stage_rewards.total_stages > 0 && (
        <Card className="bg-dark-card border-dark-border">
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
              <Activity className="w-4 h-4 text-amber-400" />
              Stage 奖励明细 (细粒度归因)
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-500 border-b border-dark-border/50">
                    <th className="text-left py-1">Stage</th>
                    <th className="text-right py-1">Avg Reward</th>
                    <th className="text-right py-1">Quality</th>
                    <th className="text-right py-1">Token Eff</th>
                    <th className="text-right py-1">Latency</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(data.stage_rewards.by_stage).map(([stageId, info]: [string, any]) => (
                    <tr key={stageId} className="border-b border-dark-border/30">
                      <td className="py-1 text-gray-300">{stageId}</td>
                      <td className={`py-1 text-right font-medium ${info.avg_reward >= 80 ? 'text-green-400' : info.avg_reward >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>
                        {info.avg_reward}
                      </td>
                      <td className="py-1 text-right text-gray-400">
                        {info.recent?.[0]?.dimensions?.output_quality ?? '—'}%
                      </td>
                      <td className="py-1 text-right text-gray-400">
                        {info.recent?.[0]?.dimensions?.token_efficiency ?? '—'}%
                      </td>
                      <td className="py-1 text-right text-gray-400">
                        {info.recent?.[0]?.dimensions?.latency_score ?? '—'}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Diagnostic Score Trend */}
      <Card className="bg-dark-card border-dark-border">
        <CardHeader>
          <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
            <Activity className="w-4 h-4 text-orange-400" />
            诊断评分趋势
            {data?.diagnostic_trend && (
              <span className={`text-xs px-2 py-0.5 rounded ${data.diagnostic_trend.current_score >= 85 ? 'bg-green-900/20 text-green-300' : 'bg-yellow-900/20 text-yellow-300'}`}>
                {data.diagnostic_trend.current_score} {data.diagnostic_trend.current_grade}
              </span>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {scoreChart ? (
            <ReactEChartsCore echarts={echarts} option={scoreChart}
              style={{ width: '100%', height: '160px' }} notMerge lazyUpdate />
          ) : (
            <p className="text-xs text-gray-500">暂无诊断趋势数据</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default EvalDashboard;
