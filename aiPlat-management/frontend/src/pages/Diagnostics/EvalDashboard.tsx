import { useEffect, useState, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Trophy, Brain, Target } from 'lucide-react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart } from 'echarts/charts';
import { TooltipComponent, GridComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { Card, CardContent, CardHeader } from '../../components/ui';

echarts.use([BarChart, TooltipComponent, GridComponent, LegendComponent, CanvasRenderer]);

interface EvalAgent {
  agent_id: string;
  latest_score: number;
  avg_score: number;
  evals_count: number;
  trend: 'up' | 'down' | 'stable';
}

interface EvalOverview {
  total_evals: number;
  eval_sets: number;
  agents_evaluated: number;
  agents: EvalAgent[];
}

interface AgentScore {
  agent_id: string;
  latest_score: number;
  grade: string;
  eval_time: number;
  total_evals: number;
  dimensions?: {
    task_completion: { score?: number; complete?: number; total?: number; reliability?: number };
    tool_quality: { overall?: number; selection_rate?: number; violations?: number };
    step_efficiency: { avg_steps?: number; score?: number };
    error_recovery: { rate?: number; total_failures?: number };
    safety: { score?: number; violations?: number; bypass_attempts?: number };
    cost: { tokens_per_task?: number; calls_per_task?: number };
  };
}

interface EvalHistory {
  agent_id: string;
  history: { eval_time: number; composite_score: number; grade: string; eval_set_id: string; total_tasks: number }[];
  count: number;
}

const GRADE_CLASS: Record<string, string> = {
  A: 'text-green-400 bg-green-900/20',
  B: 'text-blue-400 bg-blue-900/20',
  C: 'text-yellow-400 bg-yellow-900/20',
  D: 'text-orange-400 bg-orange-900/20',
  F: 'text-red-400 bg-red-900/20',
};

const TREND_ICON: Record<string, string> = {
  up: '↗️',
  down: '↘️',
  stable: '→',
};

const EvalDashboard: React.FC = () => {
  const [overview, setOverview] = useState<EvalOverview | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string>('');
  const [agentScore, setAgentScore] = useState<AgentScore | null>(null);
  const [agentHistory, setAgentHistory] = useState<EvalHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchParams] = useSearchParams();

  useEffect(() => {
    fetch('/api/core/evaluation/overview')
      .then(r => r.json())
      .then(data => {
        setOverview(data);
        const urlAgent = searchParams.get('agent');
        if (urlAgent && data.agents?.some((a: any) => a.agent_id === urlAgent)) {
          setSelectedAgent(urlAgent);
        } else if (data.agents?.length > 0) {
          setSelectedAgent(data.agents[0].agent_id);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [searchParams]);

  useEffect(() => {
    if (!selectedAgent) return;
    fetch(`/api/core/evaluation/agents/${selectedAgent}/score`)
      .then(r => r.json())
      .then(setAgentScore)
      .catch(() => {});
    fetch(`/api/core/evaluation/agents/${selectedAgent}/history?limit=20`)
      .then(r => r.json())
      .then(setAgentHistory)
      .catch(() => {});
  }, [selectedAgent]);

  const scoreBar = useMemo(() => {
    if (!overview?.agents?.length) return null;
    const top = [...overview.agents].sort((a, b) => b.latest_score - a.latest_score).slice(0, 15);
    return {
      tooltip: { trigger: 'axis' as const, axisPointer: { type: 'shadow' as const } },
      grid: { top: 10, right: 20, bottom: 20, left: 100 },
      xAxis: { type: 'value' as const, max: 100, axisLabel: { fontSize: 9, color: '#8b949e' } },
      yAxis: { type: 'category' as const, data: top.map(a => a.agent_id).reverse(),
        axisLabel: { fontSize: 10, color: '#c9d1d9' }, inverse: true },
      series: [{
        name: '评分', type: 'bar', data: top.map(a => a.latest_score).reverse(),
        itemStyle: { color: (p: any) => {
          const v = p.value ?? 0;
          return v >= 90 ? '#3fb950' : v >= 75 ? '#58a6ff' : v >= 60 ? '#d29922' : '#f85149';
        }},
        barWidth: 16,
      }],
    };
  }, [overview]);

  const trendChart = useMemo(() => {
    if (!agentHistory?.history?.length) return null;
    const h = [...agentHistory.history].reverse();
    return {
      tooltip: { trigger: 'axis' as const },
      grid: { top: 10, right: 10, bottom: 20, left: 40 },
      xAxis: { type: 'category' as const, data: h.map((_, i) => `#${i + 1}`),
        axisLabel: { fontSize: 9, color: '#8b949e' } },
      yAxis: { type: 'value' as const, min: 0, max: 100, axisLabel: { fontSize: 9, color: '#8b949e' } },
      series: [{
        name: '评分', type: 'line', data: h.map(e => e.composite_score || 0),
        smooth: true, lineStyle: { color: '#58a6ff', width: 2 },
        itemStyle: { color: '#58a6ff' }, symbol: 'circle', symbolSize: 4,
        areaStyle: { color: 'rgba(88,166,255,0.1)' },
      }],
    };
  }, [agentHistory]);

  if (loading) return <div className="p-6 text-gray-400">加载中...</div>;

  return (
    <div className="space-y-6 p-4">
      <div>
        <h1 className="text-2xl font-semibold text-gray-200">Agent 运行评估</h1>
        <p className="text-sm text-gray-500 mt-1">
          六维实时评分 · 任务完成率 · 工具调用质量 · 步骤效率 · 错误恢复 · 安全边界 · 成本
        </p>
      </div>

      <Link to="/diagnostics" className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 transition-colors">
        <ArrowLeft className="w-3 h-3" />返回诊断中心
      </Link>

      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="bg-dark-card border-dark-border">
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-green-400">{overview?.agents_evaluated ?? 0}</div>
            <div className="text-xs text-gray-500 mt-1">已评估 Agent</div>
          </CardContent>
        </Card>
        <Card className="bg-dark-card border-dark-border">
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-blue-400">{overview?.total_evals ?? 0}</div>
            <div className="text-xs text-gray-500 mt-1">评估记录</div>
          </CardContent>
        </Card>
        <Card className="bg-dark-card border-dark-border">
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-purple-400">{overview?.eval_sets ?? 0}</div>
            <div className="text-xs text-gray-500 mt-1">评估集</div>
          </CardContent>
        </Card>
        <Card className="bg-dark-card border-dark-border">
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-yellow-400">
              {overview?.agents?.length
                ? Math.round(overview.agents.reduce((s, a) => s + a.latest_score, 0) / overview.agents.length)
                : '—'}
            </div>
            <div className="text-xs text-gray-500 mt-1">平均分</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Agent Scoreboard */}
        <Card className="bg-dark-card border-dark-border lg:col-span-1">
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
              <Trophy className="w-4 h-4 text-yellow-400" />
              Agent 评分榜
            </div>
          </CardHeader>
          <CardContent>
            {overview?.agents?.length ? (
              <div className="space-y-1">
                {[...overview.agents].sort((a, b) => b.latest_score - a.latest_score).map((a, i) => (
                  <div
                    key={a.agent_id}
                    onClick={() => setSelectedAgent(a.agent_id)}
                    className={`flex items-center justify-between px-2 py-1.5 rounded cursor-pointer text-xs transition-colors
                      ${selectedAgent === a.agent_id ? 'bg-primary/10 border border-primary/30' : 'hover:bg-dark-hover'}`}
                  >
                    <span className="flex items-center gap-1.5 text-gray-300">
                      <span className="text-gray-500 w-4">#{i + 1}</span>
                      {a.agent_id}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span className={a.latest_score >= 90 ? 'text-green-400' : a.latest_score >= 75 ? 'text-blue-400' : a.latest_score >= 60 ? 'text-yellow-400' : 'text-red-400'}>
                        {a.latest_score}
                      </span>
                      <span>{TREND_ICON[a.trend] || ''}</span>
                      <span className="text-gray-500">{a.evals_count}次</span>
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-gray-500">
                暂无评估数据。设置 <code className="text-blue-400">AIPLAT_ENABLE_AUTO_EVAL=true</code> 启用自动评估，或运行
                <code className="text-blue-400 ml-1">bash scripts/eval.sh run default/normal --live</code>
              </p>
            )}
          </CardContent>
        </Card>

        {/* Score Bar Chart */}
        <Card className="bg-dark-card border-dark-border lg:col-span-1">
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
              <Target className="w-4 h-4 text-green-400" />
              评分分布
            </div>
          </CardHeader>
          <CardContent>
            {scoreBar ? (
              <ReactEChartsCore echarts={echarts} option={scoreBar}
                style={{ width: '100%', height: overview?.agents?.length ? Math.max(200, overview.agents.length * 20) : 200 }} notMerge lazyUpdate />
            ) : (
              <p className="text-xs text-gray-500">暂无数据</p>
            )}
          </CardContent>
        </Card>

        {/* Selected Agent Detail */}
        <Card className="bg-dark-card border-dark-border lg:col-span-1">
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
              <Brain className="w-4 h-4 text-purple-400" />
              {selectedAgent || '选择 Agent'}
              {agentScore?.grade && (
                <span className={`text-xs px-2 py-0.5 rounded ${GRADE_CLASS[agentScore.grade] || ''}`}>
                  {agentScore.grade}
                </span>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {agentScore?.latest_score !== undefined ? (
              <div className="space-y-3">
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">最新评分</span>
                  <span className={agentScore.latest_score >= 90 ? 'text-green-400' : agentScore.latest_score >= 75 ? 'text-blue-400' : agentScore.latest_score >= 60 ? 'text-yellow-400' : 'text-red-400'}>
                    {agentScore.latest_score}
                  </span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">评估次数</span>
                  <span className="text-gray-300">{agentScore.total_evals}</span>
                </div>
                {trendChart ? (
                  <ReactEChartsCore echarts={echarts} option={trendChart}
                    style={{ width: '100%', height: '140px' }} notMerge lazyUpdate />
                ) : (
                  <p className="text-xs text-gray-500">至少 2 次评估才显示趋势</p>
                )}
              </div>
            ) : (
              <p className="text-xs text-gray-500">
                {selectedAgent ? '暂无评估数据' : '选择一个 Agent 查看详情'}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Six-Dimension Detail for Selected Agent */}
      {agentScore?.dimensions && (
        <Card className="bg-dark-card border-dark-border">
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
              <Target className="w-4 h-4 text-green-400" />
              {selectedAgent} · 六维详情
              <span className={`text-xs px-2 py-0.5 rounded ${GRADE_CLASS[agentScore.grade] || ''}`}>
                {agentScore.grade}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 md:grid-cols-6 gap-3 text-xs">
              <div className="text-center p-2 rounded bg-dark-hover">
                <div className="text-gray-500 mb-1">任务完成</div>
                <div className={agentScore.dimensions.task_completion.score ? 'text-green-400 text-lg font-bold' : 'text-gray-500'}>
                  {agentScore.dimensions.task_completion.score ?? '—'}
                </div>
                <div className="text-gray-500">
                  {agentScore.dimensions.task_completion.complete ?? 0}/{agentScore.dimensions.task_completion.total ?? 0} tasks
                </div>
              </div>
              <div className="text-center p-2 rounded bg-dark-hover">
                <div className="text-gray-500 mb-1">工具质量</div>
                <div className={agentScore.dimensions.tool_quality.overall != null ? 'text-blue-400 text-lg font-bold' : 'text-gray-500'}>
                  {agentScore.dimensions.tool_quality.overall != null ? `${agentScore.dimensions.tool_quality.overall}%` : '—'}
                </div>
                <div className="text-gray-500">
                  {agentScore.dimensions.tool_quality.violations != null ? `${agentScore.dimensions.tool_quality.violations} 违规` : ''}
                </div>
              </div>
              <div className="text-center p-2 rounded bg-dark-hover">
                <div className="text-gray-500 mb-1">步骤效率</div>
                <div className={agentScore.dimensions.step_efficiency.score != null ? 'text-purple-400 text-lg font-bold' : 'text-gray-500'}>
                  {agentScore.dimensions.step_efficiency.score != null ? `${agentScore.dimensions.step_efficiency.score}%` : '—'}
                </div>
                <div className="text-gray-500">
                  {agentScore.dimensions.step_efficiency.avg_steps != null ? `${agentScore.dimensions.step_efficiency.avg_steps} 步` : ''}
                </div>
              </div>
              <div className="text-center p-2 rounded bg-dark-hover">
                <div className="text-gray-500 mb-1">错误恢复</div>
                <div className={agentScore.dimensions.error_recovery.rate != null ? 'text-yellow-400 text-lg font-bold' : 'text-gray-500'}>
                  {agentScore.dimensions.error_recovery.rate != null ? `${agentScore.dimensions.error_recovery.rate}%` : '—'}
                </div>
                <div className="text-gray-500">
                  {agentScore.dimensions.error_recovery.total_failures != null ? `${agentScore.dimensions.error_recovery.total_failures} 失败` : ''}
                </div>
              </div>
              <div className="text-center p-2 rounded bg-dark-hover">
                <div className="text-gray-500 mb-1">安全边界</div>
                <div className={agentScore.dimensions.safety.score != null ? 'text-red-400 text-lg font-bold' : 'text-gray-500'}>
                  {agentScore.dimensions.safety.score != null ? `${agentScore.dimensions.safety.score}%` : '—'}
                </div>
                <div className="text-gray-500">
                  {agentScore.dimensions.safety.violations != null ? `${agentScore.dimensions.safety.violations} 违规` : ''}
                </div>
              </div>
              <div className="text-center p-2 rounded bg-dark-hover">
                <div className="text-gray-500 mb-1">成本效率</div>
                <div className={agentScore.dimensions.cost.calls_per_task != null ? 'text-orange-400 text-lg font-bold' : 'text-gray-500'}>
                  {agentScore.dimensions.cost.calls_per_task != null ? `${agentScore.dimensions.cost.calls_per_task}` : '—'}
                </div>
                <div className="text-gray-500">
                  {agentScore.dimensions.cost.tokens_per_task != null ? `${agentScore.dimensions.cost.tokens_per_task} tok` : ''}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default EvalDashboard;
