import { useEffect, useState, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Trophy, Brain, Target } from 'lucide-react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart, LineChart } from 'echarts/charts';
import { TooltipComponent, GridComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { Button, Card, CardContent, CardHeader, Input } from '../../components/ui';
import { agentEvalApi, workspaceAgentApi } from '../../services';
import type { Agent } from '../../services';
import EvalAttributableReportCard, {
  type AttributableReport,
} from '../Eval/EvalAttributableReportCard';
import { namedWorkspaceHeaders } from '../Eval/namedWorkspace';

echarts.use([BarChart, LineChart, TooltipComponent, GridComponent, LegendComponent, CanvasRenderer]);

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
  production_success?: {
    success_rate: number;
    total_runs: number;
    avg_score: number;
    trend: 'up' | 'down' | 'stable';
    window: number;
  };
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
    trajectory: { matched?: boolean; score?: number; missing?: string[] };
    text_quality: { coherence?: number; conciseness?: number; instruction_following?: number; overall?: number };
    step_efficiency: { avg_steps?: number; score?: number };
    error_recovery: { rate?: number; total_failures?: number };
    safety: { score?: number; violations?: number; bypass_attempts?: number };
    content_safety: { harmful?: number; stereotype?: number; flagged?: string[] };
    refusal: { is_refusal?: boolean; refusal_type?: string };
    cost: { tokens_per_task?: number; calls_per_task?: number };
  };
  attributable_report?: AttributableReport;
  gate_pass?: boolean;
  safety_veto?: boolean;
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

type EvalDashboardProps = {
  /** When true (Eval Center Agents tab): hide legacy /eval promo; emphasize manual pick. */
  embedded?: boolean;
  /** Prefill agent picker (e.g. after 正式评测). */
  initialAgentId?: string;
  /** When historyOnly: scope score/history to this exam paper. */
  initialSetId?: string;
  /** Artifact-eval embed: score history only — no scaffold / pipe copy. */
  historyOnly?: boolean;
};

const EvalDashboard: React.FC<EvalDashboardProps> = ({
  embedded = false,
  initialAgentId = '',
  initialSetId = '',
  historyOnly = false,
}) => {
  const [overview, setOverview] = useState<EvalOverview | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string>(
    () => (initialAgentId || '').trim(),
  );
  const [agentScore, setAgentScore] = useState<AgentScore | null>(null);
  const [agentHistory, setAgentHistory] = useState<EvalHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchParams] = useSearchParams();
  const [evalSnap, setEvalSnap] = useState<Record<string, unknown> | null>(null);
  const [evalSnapError, setEvalSnapError] = useState<string | null>(null);
  const [evalBusy, setEvalBusy] = useState(false);
  const [agentDraft, setAgentDraft] = useState(() => (initialAgentId || '').trim());
  const [workspaceAgents, setWorkspaceAgents] = useState<Agent[]>([]);

  const pickAgent = (id: string) => {
    const next = id.trim();
    if (!next) return;
    setSelectedAgent(next);
    setAgentDraft(next);
  };

  useEffect(() => {
    const urlAgent = (searchParams.get('agent') || '').trim();
    const pref = (initialAgentId || '').trim() || urlAgent;
    fetch('/api/core/evaluation/overview', { headers: namedWorkspaceHeaders() })
      .then(r => r.json())
      .then(data => {
        setOverview(data);
        if (pref) {
          pickAgent(pref);
        } else if (!historyOnly && data.agents?.length > 0) {
          // Standalone dashboard: default to first scored agent.
          // historyOnly (Eval Agents tab): stay empty until exam panel picks one.
          pickAgent(data.agents[0].agent_id);
        } else if (historyOnly && !pref) {
          setSelectedAgent('');
          setAgentDraft('');
        }
      })
      .catch(() => {
        if (pref) pickAgent(pref);
        else if (historyOnly) {
          setSelectedAgent('');
          setAgentDraft('');
        }
      })
      .finally(() => setLoading(false));
  }, [searchParams, initialAgentId, historyOnly]);

  // Keep focus locked to the agent under exam when parent changes selection.
  useEffect(() => {
    if (!historyOnly) return;
    const pref = (initialAgentId || '').trim();
    if (pref && pref !== selectedAgent) {
      pickAgent(pref);
    }
    if (!pref && selectedAgent) {
      setSelectedAgent('');
      setAgentDraft('');
      setAgentScore(null);
      setAgentHistory(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only react to parent agent id
  }, [historyOnly, initialAgentId]);

  useEffect(() => {
    workspaceAgentApi
      .list({ limit: 200 })
      .then((res) => {
        const list = Array.isArray(res?.agents) ? res.agents : [];
        setWorkspaceAgents(list);
      })
      .catch(() => setWorkspaceAgents([]));
  }, []);

  const scopedSetId = historyOnly ? (initialSetId || '').trim() : '';

  useEffect(() => {
    if (!selectedAgent) return;
    setAgentScore(null);
    setAgentHistory(null);
    const scoreQs = scopedSetId
      ? `?set_id=${encodeURIComponent(scopedSetId)}`
      : '';
    fetch(
      `/api/core/evaluation/agents/${encodeURIComponent(selectedAgent)}/score${scoreQs}`,
      { headers: namedWorkspaceHeaders() },
    )
      .then(async (r) => {
        if (!r.ok) throw new Error(`score HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => setAgentScore(data as AgentScore))
      .catch(() => setAgentScore(null));
    fetch(
      `/api/core/evaluation/agents/${encodeURIComponent(selectedAgent)}/history?limit=20${
        scopedSetId ? `&set_id=${encodeURIComponent(scopedSetId)}` : ''
      }`,
      { headers: namedWorkspaceHeaders() },
    )
      .then(async (r) => {
        if (!r.ok) throw new Error(`history HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => setAgentHistory(data as EvalHistory))
      .catch(() => setAgentHistory(null));
    setEvalSnapError(null);
    agentEvalApi.inspect(selectedAgent)
      .then((res) => setEvalSnap(res as Record<string, unknown>))
      .catch((e: { message?: string }) => {
        setEvalSnap(null);
        setEvalSnapError(e?.message || '无法读取评估脚手架');
      });
  }, [selectedAgent, scopedSetId]);

  const runGenerateEval = async (force: boolean) => {
    if (!selectedAgent) return;
    setEvalBusy(true);
    setEvalSnapError(null);
    try {
      const res = await agentEvalApi.generate(selectedAgent, force);
      setEvalSnap(res);
    } catch (e: unknown) {
      const msg = e && typeof e === 'object' && 'message' in e ? String((e as { message?: string }).message) : '生成失败';
      setEvalSnapError(msg);
    } finally {
      setEvalBusy(false);
    }
  };

  const scoreBar = useMemo(() => {
    if (!overview?.agents?.length) return null;
    // Prefer avg: latest is often inflated (e.g. auto_session→100) and looks "all perfect".
    const top = [...overview.agents]
      .sort((a, b) => Number(b.avg_score ?? b.latest_score) - Number(a.avg_score ?? a.latest_score))
      .slice(0, 15);
    return {
      tooltip: {
        trigger: 'axis' as const,
        axisPointer: { type: 'shadow' as const },
        formatter: (params: unknown) => {
          const row = Array.isArray(params) ? params[0] : params;
          const p = row as { name?: string; value?: number; dataIndex?: number };
          const agent = top[top.length - 1 - Number(p.dataIndex ?? 0)];
          if (!agent) return String(p.name || '');
          return `${agent.agent_id}<br/>平均 ${agent.avg_score}<br/>最新 ${agent.latest_score} · ${agent.evals_count} 次`;
        },
      },
      grid: { top: 10, right: 20, bottom: 20, left: 100 },
      xAxis: { type: 'value' as const, max: 100, axisLabel: { fontSize: 9, color: '#8b949e' } },
      yAxis: {
        type: 'category' as const,
        data: top.map((a) => a.agent_id).reverse(),
        axisLabel: { fontSize: 10, color: '#c9d1d9' },
        inverse: true,
      },
      series: [
        {
          name: '平均分',
          type: 'bar',
          data: top.map((a) => Number(a.avg_score ?? a.latest_score)).reverse(),
          itemStyle: {
            color: (p: { value?: number }) => {
              const v = p.value ?? 0;
              return v >= 90 ? '#3fb950' : v >= 75 ? '#58a6ff' : v >= 60 ? '#d29922' : '#f85149';
            },
          },
          barWidth: 16,
        },
      ],
    };
  }, [overview]);

  const trendChart = useMemo(() => {
    if (!agentHistory?.history?.length) return null;
    // API returns newest-first; chart left→right chronological.
    const h = [...agentHistory.history].reverse();
    const points = h.map((e) =>
      e.composite_score == null || Number.isNaN(Number(e.composite_score))
        ? null
        : Number(e.composite_score),
    );
    if (!points.some((v) => v != null)) return null;
    return {
      tooltip: { trigger: 'axis' as const },
      grid: { top: 16, right: 12, bottom: 24, left: 40 },
      xAxis: {
        type: 'category' as const,
        data: h.map((_, i) => `#${i + 1}`),
        axisLabel: { fontSize: 9, color: '#8b949e' },
      },
      yAxis: {
        type: 'value' as const,
        min: 0,
        max: 100,
        axisLabel: { fontSize: 9, color: '#8b949e' },
      },
      series: [
        {
          name: '评分',
          type: 'line',
          data: points,
          connectNulls: false,
          smooth: true,
          lineStyle: { color: '#58a6ff', width: 2 },
          itemStyle: { color: '#58a6ff' },
          symbol: 'circle',
          symbolSize: 6,
          areaStyle: { color: 'rgba(88,166,255,0.12)' },
        },
      ],
    };
  }, [agentHistory]);

  if (loading) return <div className="p-6 text-gray-400">加载中...</div>;

  return (
    <>
    {!embedded ? (
      <div className="mx-4 mt-4 mb-0 rounded border border-blue-800/40 bg-blue-950/20 px-3 py-2 text-sm text-blue-100">
        EVAL_V1 评测中心 Preview 已解冻（G2a local，非 accuracy）→{' '}
        <Link to="/eval" className="text-blue-300 underline hover:text-blue-200">
          /eval
        </Link>
      </div>
    ) : null}
    <div className={`space-y-6 ${embedded ? 'p-0 pt-2' : 'p-4'}`}>
      {historyOnly ? (
        <p className="text-xs text-gray-500 -mt-1" data-testid="eval-history-scope-note">
          {selectedAgent
            ? scopedSetId
              ? `仅展示 Agent「${selectedAgent}」在用例集「${scopedSetId}」上的正式评测；不含其它 set（如 auto_session）。工程分，不是准确率认证。`
              : '仅展示上方所选 Agent 的正式评测记录与趋势。工程分，不是准确率认证。'
            : '请先在上方选择正在评测的 Agent；此处不再展示全站评分榜。'}
        </p>
      ) : (
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">
            {embedded ? 'Agent 评估诊断（历史分 / 脚手架）' : 'Agent 运行评估'}
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            {embedded
              ? '评分榜只列「已经跑过评估」的 Agent；榜空时请在下方选工作区 Agent 或手填 agent_id。'
              : '六维实时评分 · 任务完成率 · 工具调用质量 · 步骤效率 · 错误恢复 · 安全边界 · 成本'}
          </p>
        </div>
      )}

      {!historyOnly ? (
        <Link to="/diagnostics" className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 transition-colors">
          <ArrowLeft className="w-3 h-3" />返回诊断中心
        </Link>
      ) : null}

      {/* Stats Row — agent-scoped when historyOnly */}
      {historyOnly ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <Card className="bg-dark-card border-dark-border">
            <CardContent className="p-4 text-center">
              <div className="text-2xl font-bold text-green-400">
                {agentScore?.latest_score ?? '—'}
              </div>
              <div className="text-xs text-gray-500 mt-1">最新分</div>
            </CardContent>
          </Card>
          <Card className="bg-dark-card border-dark-border">
            <CardContent className="p-4 text-center">
              <div className="text-2xl font-bold text-blue-400">
                {agentScore?.total_evals ?? agentHistory?.count ?? '—'}
              </div>
              <div className="text-xs text-gray-500 mt-1">本 Agent 评估次数</div>
            </CardContent>
          </Card>
          <Card className="bg-dark-card border-dark-border">
            <CardContent className="p-4 text-center">
              <div
                className={`text-2xl font-bold ${
                  agentScore?.grade ? GRADE_CLASS[agentScore.grade]?.split(' ')[0] || 'text-gray-300' : 'text-gray-500'
                }`}
              >
                {agentScore?.grade || '—'}
              </div>
              <div className="text-xs text-gray-500 mt-1">最新等级</div>
            </CardContent>
          </Card>
          <Card className="bg-dark-card border-dark-border">
            <CardContent className="p-4 text-center">
              <div className="text-sm font-mono text-purple-300 truncate px-1">
                {selectedAgent || '未选择'}
              </div>
              <div className="text-xs text-gray-500 mt-1">当前评测对象</div>
            </CardContent>
          </Card>
        </div>
      ) : (
      <div className="grid grid-cols-5 gap-4">
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
        {overview?.production_success ? (
          <Card className="bg-dark-card border-dark-border">
            <CardContent className="p-4 text-center">
              <div className="text-2xl font-bold text-emerald-400">{overview.production_success.success_rate}%</div>
              <div className="text-xs text-gray-500 mt-1">
                生产成功率 · {overview.production_success.total_runs ?? 0} 次
                <span className={`ml-1 ${overview.production_success.trend === 'up' ? 'text-emerald-400' : overview.production_success.trend === 'down' ? 'text-red-400' : 'text-gray-500'}`}>
                  {overview.production_success.trend === 'up' ? '↑' : overview.production_success.trend === 'down' ? '↓' : '–'}
                </span>
              </div>
            </CardContent>
          </Card>
        ) : null}
      </div>
      )}

      {!historyOnly ? (
      <Card className="bg-dark-card border-dark-border">
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="text-sm font-semibold text-gray-200">评估脚手架（generate_agent_eval）</div>
                <p className="text-xs text-gray-500 mt-1">
                  「生成评估代码」= 为该 Agent 写 scoring_dimensions + eval_metric/eval_runner 脚手架（POST
                  /entropy/eval/generate）；「强制重生成」= force=true 覆盖已有文件。都不是 Skill-eval
                  suite，也不跑模型准确率 Job。上架 listed 会自动入队；失败不挡上架。
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <select
                  data-testid="eval-dashboard-agent-select"
                  className="h-8 min-w-[12rem] rounded border border-dark-border bg-dark-card px-2 text-xs text-gray-200"
                  value={
                    workspaceAgents.some((a) => a.id === selectedAgent) ? selectedAgent : ''
                  }
                  onChange={(e) => pickAgent(e.target.value)}
                  aria-label="从工作区选择 Agent"
                >
                  <option value="">从工作区选择 Agent…</option>
                  {workspaceAgents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.display_name || a.name || a.id}
                      {a.id !== (a.display_name || a.name) ? ` (${a.id})` : ''}
                    </option>
                  ))}
                </select>
                <div className="w-48">
                <Input
                  placeholder="或手填 agent_id"
                  value={agentDraft}
                  onChange={(e) => setAgentDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') pickAgent(agentDraft);
                  }}
                />
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={!agentDraft.trim()}
                  onClick={() => pickAgent(agentDraft)}
                >
                  查看
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={evalBusy || !selectedAgent}
                  onClick={() => runGenerateEval(false)}
                >
                  {evalBusy ? '处理中…' : '生成评估代码'}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={evalBusy || !selectedAgent}
                  onClick={() => runGenerateEval(true)}
                >
                  强制重生成
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {evalSnapError ? (
              <div className="text-sm text-amber-300">{evalSnapError}</div>
            ) : evalSnap ? (
              <div className="space-y-2 text-xs text-gray-400">
                <div>
                  agent_id <code className="text-gray-200">{String(evalSnap.agent_id || selectedAgent)}</code>
                  {' · '}
                  {evalSnap.complete ? <span className="text-green-400">已齐全</span> : <span className="text-amber-300">未齐全</span>}
                  {' · 轨迹 '}{String(evalSnap.trace_count ?? '—')}
                  {' · 维度 '}{evalSnap.has_scoring ? '有' : '无'}
                  {' · 文件 '}{evalSnap.has_eval_files ? '有' : '无'}
                </div>
                {evalSnap.eval_dir ? (
                  <div className="break-all">目录 {String(evalSnap.eval_dir)}</div>
                ) : null}
                {Array.isArray(evalSnap.scoring_dimensions) && evalSnap.scoring_dimensions.length > 0 ? (
                  <ul className="list-disc pl-4 space-y-1 text-gray-300">
                    {(evalSnap.scoring_dimensions as Array<{ name?: string; weight?: number; description?: string; threshold?: number }>).map((d) => (
                      <li key={String(d.name)}>
                        <code className="text-gray-100">{String(d.name)}</code>
                        {d.weight != null ? ` · w=${d.weight}` : ''}
                        {d.threshold != null ? ` · 阈=${d.threshold}` : ''}
                        {d.description ? ` — ${d.description}` : ''}
                      </li>
                    ))}
                  </ul>
                ) : null}
                {evalSnap.last_action && typeof evalSnap.last_action === 'object' ? (
                  <div className="text-gray-300">
                    最近：{String((evalSnap.last_action as { action?: string }).action || '—')}
                    {' — '}
                    {String((evalSnap.last_action as { message?: string }).message || evalSnap.message || '')}
                  </div>
                ) : evalSnap.message ? (
                  <div className="text-gray-300">{String(evalSnap.message)}</div>
                ) : null}
                {evalSnap.action ? (
                  <div>本次：{String(evalSnap.action)} — {String(evalSnap.message || '')}</div>
                ) : null}
                {evalSnap.last_report && typeof evalSnap.last_report === 'object' ? (
                  <div className="text-gray-300">
                    试跑 composite{' '}
                    {String(
                      (evalSnap.last_report as { composite?: number }).composite ?? '—',
                    )}
                    {' · '}completed {(evalSnap.last_report as { completed?: number }).completed ?? '—'}
                    {' / '}total {(evalSnap.last_report as { total_runs?: number }).total_runs ?? '—'}
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="text-sm text-gray-500">
                输入或选择 agent_id 后显示脚手架状态（主入口{' '}
                <code className="text-gray-400">/eval?tab=agents&amp;agent=…</code>）。
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}

      {historyOnly ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" data-testid="eval-history-focused">
          <Card className="bg-dark-card border-dark-border">
            <CardHeader>
              <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
                <Brain className="w-4 h-4 text-purple-400" />
                {selectedAgent || '未选择 Agent'}
                {agentScore?.grade ? (
                  <span className={`text-xs px-2 py-0.5 rounded ${GRADE_CLASS[agentScore.grade] || ''}`}>
                    {agentScore.grade}
                  </span>
                ) : null}
              </div>
              <p className="text-[11px] text-gray-500 mt-1 font-normal">
                分数趋势（仅当前 Agent）
              </p>
            </CardHeader>
            <CardContent>
              {!selectedAgent ? (
                <p className="text-xs text-gray-500">在上方「评测 Agent」选择对象后，这里显示该 Agent 的历史趋势。</p>
              ) : agentScore?.latest_score != null || (agentHistory?.history?.length || 0) > 0 ? (
                <div className="space-y-3">
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">最新评分</span>
                    <span
                      className={
                        (agentScore?.latest_score ?? 0) >= 90
                          ? 'text-green-400'
                          : (agentScore?.latest_score ?? 0) >= 75
                            ? 'text-blue-400'
                            : (agentScore?.latest_score ?? 0) >= 60
                              ? 'text-yellow-400'
                              : 'text-red-400'
                      }
                    >
                      {agentScore?.latest_score ?? '—'}
                    </span>
                  </div>
                  {trendChart ? (
                    <ReactEChartsCore
                      echarts={echarts}
                      option={trendChart}
                      style={{ width: '100%', height: '180px' }}
                      notMerge
                      lazyUpdate
                    />
                  ) : (agentHistory?.history?.length || 0) > 0 ? (
                    <p className="text-xs text-gray-500">历史记录无有效 composite_score，无法画趋势</p>
                  ) : (
                    <p className="text-xs text-gray-500">暂无历史曲线（正式评测写入后会出现）</p>
                  )}
                </div>
              ) : (
                <p className="text-xs text-gray-500">
                  该 Agent 尚无 eval_results。请上方正式评测（live）写入后再看。
                </p>
              )}
            </CardContent>
          </Card>

          <Card className="bg-dark-card border-dark-border">
            <CardHeader>
              <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
                <Trophy className="w-4 h-4 text-yellow-400" />
                {scopedSetId ? '本卷评测记录' : '本 Agent 评测记录'}
              </div>
              <p className="text-[11px] text-gray-500 mt-1 font-normal">
                最近 {agentHistory?.history?.length || 0} 条
                {scopedSetId ? ` · set=${scopedSetId}` : '（非全站榜）'}
              </p>
            </CardHeader>
            <CardContent>
              {!selectedAgent ? (
                <p className="text-xs text-gray-500">选择 Agent 后列出其正式评测记录。</p>
              ) : (agentHistory?.history?.length || 0) > 0 ? (
                <div className="space-y-1 max-h-72 overflow-y-auto">
                  {agentHistory!.history.map((row, i) => {
                    const when =
                      row.eval_time && Number(row.eval_time) > 0
                        ? new Date(
                            Number(row.eval_time) < 1e12
                              ? Number(row.eval_time) * 1000
                              : Number(row.eval_time),
                          ).toLocaleString()
                        : '';
                    return (
                    <div
                      key={`${row.eval_time}-${row.eval_set_id}-${i}`}
                      className="flex items-center justify-between gap-2 px-2 py-1.5 rounded text-xs bg-dark-hover/40"
                    >
                      <span className="text-gray-400 shrink-0">#{i + 1}</span>
                      <span
                        className="text-gray-300 truncate flex-1"
                        title={`${row.eval_set_id || ''}${when ? ` · ${when}` : ''}`}
                      >
                        {row.eval_set_id || '—'}
                        {when ? (
                          <span className="text-gray-500 ml-1.5 font-normal">{when}</span>
                        ) : null}
                      </span>
                      <span
                        className={`font-mono shrink-0 ${
                          row.composite_score >= 90
                            ? 'text-green-400'
                            : row.composite_score >= 75
                              ? 'text-blue-400'
                              : row.composite_score >= 60
                                ? 'text-yellow-400'
                                : 'text-red-400'
                        }`}
                      >
                        {row.composite_score}
                      </span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${GRADE_CLASS[row.grade] || 'text-gray-400'}`}
                      >
                        {row.grade || '—'}
                      </span>
                      <span className="text-gray-500 shrink-0">{row.total_tasks ?? '—'}题</span>
                    </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-gray-500">暂无该 Agent 的评测记录。</p>
              )}
            </CardContent>
          </Card>
        </div>
      ) : (
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Agent Scoreboard */}
        <Card className="bg-dark-card border-dark-border lg:col-span-1">
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
              <Trophy className="w-4 h-4 text-yellow-400" />
              Agent 评分榜
            </div>
            <p className="text-[11px] text-gray-500 mt-1 font-normal">显示 平均/最新</p>
          </CardHeader>
          <CardContent>
            {overview?.agents?.length ? (
              <div className="space-y-1">
                {[...overview.agents]
                  .sort(
                    (a, b) =>
                      Number(b.avg_score ?? b.latest_score) -
                      Number(a.avg_score ?? a.latest_score),
                  )
                  .map((a, i) => (
                  <div
                    key={a.agent_id}
                    onClick={() => {
                      setSelectedAgent(a.agent_id);
                      setAgentDraft(a.agent_id);
                    }}
                    className={`flex items-center justify-between px-2 py-1.5 rounded cursor-pointer text-xs transition-colors
                      ${selectedAgent === a.agent_id ? 'bg-primary/10 border border-primary/30' : 'hover:bg-dark-hover'}`}
                  >
                    <span className="flex items-center gap-1.5 text-gray-300">
                      <span className="text-gray-500 w-4">#{i + 1}</span>
                      {a.agent_id}
                    </span>
                    <span className="flex items-center gap-1.5">
                      <span
                        className={
                          a.avg_score >= 90
                            ? 'text-green-400'
                            : a.avg_score >= 75
                              ? 'text-blue-400'
                              : a.avg_score >= 60
                                ? 'text-yellow-400'
                                : 'text-red-400'
                        }
                        title={`平均 ${a.avg_score} · 最新 ${a.latest_score}`}
                      >
                        {a.avg_score}
                      </span>
                      <span className="text-gray-600">/{a.latest_score}</span>
                      <span>{TREND_ICON[a.trend] || ''}</span>
                      <span className="text-gray-500">{a.evals_count}次</span>
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-gray-500 space-y-2">
                <p>
                  评分榜为空＝还没有任何 Agent 的历史评估结果，所以这里点不了行。
                  <strong className="text-gray-300"> 不等于不能评测。</strong>
                </p>
                <p>
                  请用上方「从工作区选择 Agent」或手填 <code className="text-blue-400">agent_id</code> 后点「查看 / 生成评估代码」。
                </p>
                <p>
                  或启用 <code className="text-blue-400">AIPLAT_ENABLE_AUTO_EVAL=true</code> / 跑
                  <code className="text-blue-400 ml-1">bash scripts/eval.sh run default/normal --live</code>
                  产生历史分后再出现在榜上。
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Score Bar Chart */}
        <Card className="bg-dark-card border-dark-border lg:col-span-1">
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
              <Target className="w-4 h-4 text-green-400" />
              平均分分布
            </div>
            <p className="text-[11px] text-gray-500 mt-1 font-normal">
              用历史平均分，避免「最新一次 auto_session=100」把图刷成全满分
            </p>
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
            {agentScore?.latest_score != null ? (
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
                  <ReactEChartsCore
                    echarts={echarts}
                    option={trendChart}
                    style={{ width: '100%', height: '140px' }}
                    notMerge
                    lazyUpdate
                  />
                ) : agentHistory && (agentHistory.history?.length || 0) > 0 ? (
                  <p className="text-xs text-gray-500">历史记录无有效 composite_score，无法画趋势</p>
                ) : (
                  <p className="text-xs text-gray-500">暂无历史曲线（正式评测写入后会出现）</p>
                )}
              </div>
            ) : (
              <p className="text-xs text-gray-500">
                {selectedAgent
                  ? '暂无评估数据（还没有 eval_results）。请上方正式评测（live）或 scripts/eval.sh run … --live。'
                  : '选择一个 Agent 查看详情'}
              </p>
            )}
          </CardContent>
        </Card>
      </div>
      )}

      {/* historyOnly: attributable already shown above in exam panel — avoid duplicate. */}
      {!historyOnly && agentScore?.attributable_report ? (
        <EvalAttributableReportCard report={agentScore.attributable_report} />
      ) : null}

      {/* Central legacy dimensions — not a full agent capability taxonomy */}
      {agentScore?.dimensions && (
        <Card className="bg-dark-card border-dark-border" data-testid="eval-dimension-panel">
          <CardHeader>
            <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-gray-200">
              <Target className="w-4 h-4 text-green-400" />
              {selectedAgent} · 工程维度明细
              <span className={`text-xs px-2 py-0.5 rounded ${GRADE_CLASS[agentScore.grade] || ''}`}>
                {agentScore.grade}
              </span>
            </div>
            <p className="text-[11px] text-gray-500 mt-1 font-normal leading-relaxed">
              这不是「Agent 该有的全部能力维度」。当前 Central 总分只加权下面
              <strong className="text-gray-300"> 7 项工程维</strong>
              （任务完成 30% · 工具 20% · 轨迹 5% · 步骤 15% · 错误恢复 15% · 安全 10% · 成本 5%）。
              文本质量 / 内容安全 / 拒答仅展示、不进总分。业务侧自定义
              scoring_dimensions 也不会自动出现在这里。
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="text-xs text-gray-400 mb-2">计入总分（7）</div>
              <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2 text-xs">
                <div className="text-center p-2 rounded bg-dark-hover">
                  <div className="text-gray-500 mb-1">任务完成</div>
                  <div className={agentScore.dimensions.task_completion?.score != null ? 'text-green-400 text-lg font-bold' : 'text-gray-500'}>
                    {agentScore.dimensions.task_completion?.score ?? '—'}
                  </div>
                  <div className="text-gray-500">
                    {agentScore.dimensions.task_completion?.complete ?? 0}/
                    {agentScore.dimensions.task_completion?.total ?? 0} tasks
                  </div>
                </div>
                <div className="text-center p-2 rounded bg-dark-hover">
                  <div className="text-gray-500 mb-1">工具质量</div>
                  <div className={agentScore.dimensions.tool_quality?.overall != null ? 'text-blue-400 text-lg font-bold' : 'text-gray-500'}>
                    {agentScore.dimensions.tool_quality?.overall != null
                      ? `${agentScore.dimensions.tool_quality.overall}%`
                      : '—'}
                  </div>
                  <div className="text-gray-500">
                    {agentScore.dimensions.tool_quality?.violations != null
                      ? `${agentScore.dimensions.tool_quality.violations} 违规`
                      : ''}
                  </div>
                </div>
                <div className="text-center p-2 rounded bg-dark-hover">
                  <div className="text-gray-500 mb-1">轨迹匹配</div>
                  <div className={agentScore.dimensions.trajectory?.score != null ? 'text-teal-400 text-lg font-bold' : 'text-gray-500'}>
                    {agentScore.dimensions.trajectory?.score != null
                      ? `${(agentScore.dimensions.trajectory.score * 100).toFixed(0)}%`
                      : '—'}
                  </div>
                  <div className="text-gray-500 text-xs">
                    {agentScore.dimensions.trajectory?.matched ? '匹配' : '不匹配'}
                  </div>
                </div>
                <div className="text-center p-2 rounded bg-dark-hover">
                  <div className="text-gray-500 mb-1">步骤效率</div>
                  <div className={agentScore.dimensions.step_efficiency?.score != null ? 'text-purple-400 text-lg font-bold' : 'text-gray-500'}>
                    {agentScore.dimensions.step_efficiency?.score != null
                      ? `${agentScore.dimensions.step_efficiency.score}%`
                      : '—'}
                  </div>
                  <div className="text-gray-500">
                    {agentScore.dimensions.step_efficiency?.avg_steps != null
                      ? `${agentScore.dimensions.step_efficiency.avg_steps} 步`
                      : ''}
                  </div>
                </div>
                <div className="text-center p-2 rounded bg-dark-hover">
                  <div className="text-gray-500 mb-1">错误恢复</div>
                  <div className={agentScore.dimensions.error_recovery?.rate != null ? 'text-yellow-400 text-lg font-bold' : 'text-gray-500'}>
                    {agentScore.dimensions.error_recovery?.rate != null
                      ? `${agentScore.dimensions.error_recovery.rate}%`
                      : '—'}
                  </div>
                  <div className="text-gray-500">
                    {agentScore.dimensions.error_recovery?.total_failures != null
                      ? `${agentScore.dimensions.error_recovery.total_failures} 失败`
                      : ''}
                  </div>
                </div>
                <div className="text-center p-2 rounded bg-dark-hover">
                  <div className="text-gray-500 mb-1">安全边界</div>
                  <div className={agentScore.dimensions.safety?.score != null ? 'text-red-400 text-lg font-bold' : 'text-gray-500'}>
                    {agentScore.dimensions.safety?.score != null
                      ? `${agentScore.dimensions.safety.score}%`
                      : '—'}
                  </div>
                  <div className="text-gray-500">
                    {agentScore.dimensions.safety?.violations != null
                      ? `${agentScore.dimensions.safety.violations} 违规`
                      : ''}
                  </div>
                </div>
                <div className="text-center p-2 rounded bg-dark-hover">
                  <div className="text-gray-500 mb-1">成本效率</div>
                  <div className={agentScore.dimensions.cost?.calls_per_task != null ? 'text-orange-400 text-lg font-bold' : 'text-gray-500'}>
                    {agentScore.dimensions.cost?.calls_per_task != null
                      ? `${agentScore.dimensions.cost.calls_per_task}`
                      : '—'}
                  </div>
                  <div className="text-gray-500">
                    {agentScore.dimensions.cost?.tokens_per_task != null
                      ? `${agentScore.dimensions.cost.tokens_per_task} tok`
                      : ''}
                  </div>
                </div>
              </div>
            </div>

            <div>
              <div className="text-xs text-gray-400 mb-2">仅展示 · 不进总分（3）</div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                <div className="text-center p-2 rounded border border-gray-800 bg-dark-hover/60">
                  <div className="text-gray-500 mb-1">文本质量</div>
                  <div className="flex gap-3 justify-center text-xs">
                    <span className="text-cyan-400">
                      连贯{' '}
                      {agentScore.dimensions.text_quality?.coherence != null
                        ? `${(agentScore.dimensions.text_quality.coherence * 100).toFixed(0)}%`
                        : '—'}
                    </span>
                    <span className="text-pink-400">
                      简洁{' '}
                      {agentScore.dimensions.text_quality?.conciseness != null
                        ? `${(agentScore.dimensions.text_quality.conciseness * 100).toFixed(0)}%`
                        : '—'}
                    </span>
                    <span className="text-amber-400">
                      指令{' '}
                      {agentScore.dimensions.text_quality?.instruction_following != null
                        ? `${(agentScore.dimensions.text_quality.instruction_following * 100).toFixed(0)}%`
                        : '—'}
                    </span>
                  </div>
                </div>
                <div className="text-center p-2 rounded border border-gray-800 bg-dark-hover/60">
                  <div className="text-gray-500 mb-1">内容安全</div>
                  <div className={agentScore.dimensions.content_safety?.harmful != null ? 'text-green-400 text-lg font-bold' : 'text-gray-500'}>
                    {agentScore.dimensions.content_safety?.harmful != null
                      ? `${(agentScore.dimensions.content_safety.harmful * 100).toFixed(0)}%`
                      : '—'}
                  </div>
                  <div className="text-gray-500 text-xs">
                    {agentScore.dimensions.content_safety?.flagged?.length
                      ? `${agentScore.dimensions.content_safety.flagged.length} 标记`
                      : '清洁'}
                  </div>
                </div>
                <div className="text-center p-2 rounded border border-gray-800 bg-dark-hover/60">
                  <div className="text-gray-500 mb-1">拒答检测</div>
                  <div className={agentScore.dimensions.refusal?.is_refusal ? 'text-red-400 text-lg font-bold' : 'text-green-400 text-lg font-bold'}>
                    {agentScore.dimensions.refusal?.is_refusal ? '是' : '否'}
                  </div>
                  <div className="text-gray-500 text-xs">
                    {agentScore.dimensions.refusal?.refusal_type || '—'}
                  </div>
                </div>
              </div>
            </div>

            {Array.isArray(evalSnap?.scoring_dimensions) &&
            (evalSnap!.scoring_dimensions as unknown[]).length > 0 ? (
              <div>
                <div className="text-xs text-gray-400 mb-2">
                  该 Agent 声明的业务维度（来自脚手架 / AGENT.md · 未并入上方工程总分）
                </div>
                <ul className="list-disc pl-4 space-y-1 text-xs text-gray-300">
                  {(
                    evalSnap!.scoring_dimensions as Array<{
                      name?: string;
                      weight?: number;
                      description?: string;
                      threshold?: number;
                    }>
                  ).map((d) => (
                    <li key={String(d.name)}>
                      <code className="text-gray-100">{String(d.name)}</code>
                      {d.weight != null ? ` · w=${d.weight}` : ''}
                      {d.threshold != null ? ` · 阈=${d.threshold}` : ''}
                      {d.description ? ` — ${d.description}` : ''}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </CardContent>
        </Card>
      )}
    </div>
    </>
  );
};

export default EvalDashboard;
