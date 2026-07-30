/**
 * LineageViewer — 决策血缘可视化 (Palantir Decision Lineage 对齐)
 *
 * 展示 Agent 的完整决策链:
 *   - 谁 (agent_id, role)
 *   - 何时 (decided_at)
 *   - 基于哪个数据版本 (ontology_version, kb_collection_version)
 *   - 选了哪个工具/技能 (chosen_option)
 *   - 为什么 (choice_reasoning)
 *   - 结果如何 (outcome_status)
 *
 * 使用方式: 在 FDE 工作台或其他诊断页面中以 Tab 或 Panel 形式嵌入
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import {
  Search, GitCommit, Clock, User, Cpu, CheckCircle, XCircle,
  AlertTriangle, ArrowRight, ChevronDown, ChevronRight, RefreshCw,
} from 'lucide-react';

const API_BASE = '/api/platform/apps/fde';

// ── Types ────────────────────────────────────────────────────────────────

interface DecisionRecord {
  decision_id: string;
  run_id: string;
  trace_id?: string;
  agent_id?: string;
  actor_role?: string;
  decided_at: number;
  context_snapshot_id?: string;
  ontology_version?: string;
  kb_collection_version?: string;
  decision_type: string;
  options_considered?: string;
  chosen_option: string;
  choice_reasoning?: string;
  outcome_status: string;
  outcome_summary?: string;
  cascaded_decisions?: string;
  policy_version?: string;
  constraint_checks?: string;
  created_at: number;
}

interface RunEntry {
  run_id: string;
  decision_count: number;
  last_decision_at: number;
  success_count: number;
}

interface GraphData {
  nodes: Array<{ id: string; type: string; label: string; [key: string]: any }>;
  edges: Array<{ source: string; target: string; type: string }>;
  summary: Record<string, any>;
}

// ── Component ─────────────────────────────────────────────────────────────

const LineageViewer: React.FC = () => {
  const [runs, setRuns] = useState<RunEntry[]>([]);
  const [selectedRun, setSelectedRun] = useState('');
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [viewMode, setViewMode] = useState<'list' | 'graph'>('list');

  // Load recent runs on mount
  useEffect(() => {
    fetch(`${API_BASE}/lineage/recent?limit=20`)
      .then(r => r.json()).then(d => setRuns(d.runs || []))
      .catch(() => {});
  }, []);

  const loadRun = useCallback(async (runId: string) => {
    setSelectedRun(runId);
    setLoading(true);
    try {
      const [decRes, graphRes] = await Promise.all([
        fetch(`${API_BASE}/lineage/${runId}?limit=200`).then(r => r.json()),
        fetch(`${API_BASE}/lineage/${runId}/graph`).then(r => r.json()).catch(() => null),
      ]);
      setDecisions(decRes.decisions || []);
      setGraph(graphRes);
    } catch (e: any) {
      toast?.error?.(e?.message || '加载失败');
    }
    setLoading(false);
  }, []);

  const toggleExpand = (id: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  // ── Render Helpers ──────────────────────────────────────────────────

  const typeLabel = (t: string) => {
    const m: Record<string, string> = {
      tool_selection: '工具选择', skill_selection: '技能选择',
      fallback_trigger: '降级触发', parameter_choice: '参数选择',
      action_selection: '动作选择', approval_override: '审批越权',
    };
    return m[t] || t;
  };

  const typeColor = (t: string) => {
    const m: Record<string, string> = {
      tool_selection: 'text-blue-400', skill_selection: 'text-purple-400',
      fallback_trigger: 'text-orange-400', parameter_choice: 'text-gray-400',
      action_selection: 'text-green-400', approval_override: 'text-red-400',
    };
    return m[t] || 'text-gray-400';
  };

  const statusIcon = (status: string) => {
    switch (status) {
      case 'success': return <CheckCircle className="w-3.5 h-3.5 text-green-400" />;
      case 'failed': return <XCircle className="w-3.5 h-3.5 text-red-400" />;
      case 'pending': return <Clock className="w-3.5 h-3.5 text-yellow-400" />;
      default: return <AlertTriangle className="w-3.5 h-3.5 text-gray-400" />;
    }
  };

  const timeAgo = (ts: number) => {
    const diff = Date.now() / 1000 - ts;
    if (diff < 60) return '刚刚';
    if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
    return `${Math.floor(diff / 86400)}天前`;
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">决策血缘</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            追踪 Agent 的完整决策链 — 谁在何时基于什么数据选择了哪个工具
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={viewMode}
            onChange={e => setViewMode(e.target.value as 'list' | 'graph')}
            className="bg-gray-800 border border-gray-700 text-gray-300 text-xs rounded px-2 py-1"
          >
            <option value="list">列表视图</option>
            <option value="graph">图谱视图</option>
          </select>
          <Button variant="ghost" size="sm" onClick={() => {
            fetch(`${API_BASE}/lineage/recent?limit=20`)
              .then(r => r.json()).then(d => setRuns(d.runs || []));
          }}>
            <RefreshCw className="w-3 h-3" />
          </Button>
        </div>
      </div>

      {/* Run List */}
      {runs.length > 0 && (
        <Card className="border-gray-700/50">
          <CardHeader><span className="text-sm font-medium text-gray-200">最近决策链</span></CardHeader>
          <CardContent>
            <div className="space-y-1 max-h-60 overflow-y-auto">
              {runs.map(r => (
                <button
                  key={r.run_id}
                  onClick={() => loadRun(r.run_id)}
                  className={`w-full text-left p-2 rounded text-xs flex items-center justify-between transition-colors ${
                    selectedRun === r.run_id
                      ? 'bg-blue-500/10 border border-blue-500/20'
                      : 'hover:bg-gray-800/50 border border-transparent'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <GitCommit className="w-3 h-3 text-gray-500" />
                    <span className="text-gray-300 font-mono">{r.run_id?.slice(0, 16)}</span>
                    <span className="text-gray-600">{timeAgo(r.last_decision_at)}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-gray-400">{r.decision_count} 决策</span>
                    <span className="text-green-400">{r.success_count} 成功</span>
                    {r.decision_count - r.success_count > 0 && (
                      <span className="text-red-400">{r.decision_count - r.success_count} 失败</span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Graph View */}
      {viewMode === 'graph' && graph && (
        <Card className="border-gray-700/50">
          <CardHeader>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-200">决策图谱</span>
              <div className="flex gap-3 text-xs text-gray-500">
                <span>总决策: {graph.summary?.total_decisions}</span>
                <span>成功率: {graph.summary?.success_rate}%</span>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {graph.nodes
                .filter(n => n.type === 'decision')
                .map(node => (
                  <div key={node.id} className="p-2.5 rounded bg-gray-800/50 border border-gray-700/30">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-200">{node.label}</span>
                        <span className={`text-[10px] ${typeColor(node.decision_type)}`}>
                          {typeLabel(node.decision_type)}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {node.context_version && (
                          <span className="text-[10px] text-gray-600">v{node.context_version}</span>
                        )}
                        <span className={`text-[10px] px-1 py-0.5 rounded ${
                          node.outcome === 'success' ? 'bg-green-500/10 text-green-400' :
                          node.outcome === 'failed' ? 'bg-red-500/10 text-red-400' : 'bg-gray-500/10 text-gray-400'
                        }`}>{node.outcome || '?'}</span>
                      </div>
                    </div>
                    {node.reasoning && (
                      <div className="text-[10px] text-gray-500 mt-1">"{node.reasoning}"</div>
                    )}
                  </div>
                ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* List View */}
      {viewMode === 'list' && decisions.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs text-gray-500">
            {decisions.length} 条决策记录
            {graph?.summary?.success_rate !== undefined && (
              <span className="ml-2">· 成功率 {graph.summary.success_rate}%</span>
            )}
          </div>
          {decisions.map((d, i) => {
            const isExpanded = expanded.has(d.decision_id);
            let options: any[] = [];
            try { options = JSON.parse(d.options_considered || '[]'); } catch {}

            return (
              <Card key={d.decision_id} className="border-gray-700/50">
                <div
                  className="p-3 cursor-pointer"
                  onClick={() => toggleExpand(d.decision_id)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {isExpanded ? <ChevronDown className="w-3 h-3 text-gray-500" /> : <ChevronRight className="w-3 h-3 text-gray-500" />}
                      <span className="text-sm text-gray-200 font-medium">
                        {d.chosen_option?.slice(0, 60)}
                      </span>
                      <span className={`text-[10px] ${typeColor(d.decision_type)}`}>
                        {typeLabel(d.decision_type)}
                      </span>
                      {statusIcon(d.outcome_status)}
                    </div>
                    <div className="flex items-center gap-3 text-[10px] text-gray-500">
                      <span className="flex items-center gap-1"><User className="w-3 h-3" />{d.agent_id || '-'}</span>
                      <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{timeAgo(d.decided_at)}</span>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="mt-2 pt-2 border-t border-gray-700/50 space-y-2">
                      {/* Context versions */}
                      {(d.ontology_version || d.kb_collection_version || d.context_snapshot_id) && (
                        <div className="flex gap-3 text-[10px]">
                          {d.ontology_version && (
                            <span className="text-gray-500">本体: <span className="text-purple-400">v{d.ontology_version}</span></span>
                          )}
                          {d.kb_collection_version && (
                            <span className="text-gray-500">知识库: <span className="text-blue-400">{d.kb_collection_version}</span></span>
                          )}
                          {d.context_snapshot_id && (
                            <span className="text-gray-500">快照: <span className="text-green-400">{d.context_snapshot_id?.slice(0, 12)}</span></span>
                          )}
                        </div>
                      )}

                      {/* Reasoning */}
                      {d.choice_reasoning && (
                        <div className="text-xs text-gray-400 bg-gray-800/70 rounded p-2">
                          💭 {d.choice_reasoning}
                        </div>
                      )}

                      {/* Outcome */}
                      {d.outcome_summary && (
                        <div className={`text-xs rounded p-2 ${
                          d.outcome_status === 'success' ? 'bg-green-500/5 text-green-300' :
                          d.outcome_status === 'failed' ? 'bg-red-500/5 text-red-300' : 'bg-gray-500/5 text-gray-400'
                        }`}>
                          结果: {d.outcome_summary?.slice(0, 200)}
                        </div>
                      )}

                      {/* Alternatives */}
                      {options.length > 1 && (
                        <div>
                          <div className="text-[10px] text-gray-600 mb-1">候选方案</div>
                          {options.slice(0, 5).map((opt: any, j: number) => (
                            <div key={j} className="flex items-center gap-2 text-[10px] py-0.5">
                              <span className={opt.tool === d.chosen_option ? 'text-green-400' : 'text-gray-600'}>
                                {opt.tool === d.chosen_option ? '✓' : '·'}
                              </span>
                              <span className="text-gray-400">{opt.tool}</span>
                              {opt.score !== undefined && (
                                <span className="text-gray-600">置信度 {opt.score}</span>
                              )}
                              {opt.reason && (
                                <span className="text-gray-600">— {opt.reason}</span>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Governance */}
                      {(d.policy_version || d.constraint_checks) && (
                        <div className="text-[10px] text-gray-600">
                          {d.policy_version && <span>策略版本: {d.policy_version}</span>}
                          {d.constraint_checks && d.constraint_checks !== '{}' && (
                            <span className="ml-2">约束检查: {d.constraint_checks?.slice(0, 100)}</span>
                          )}
                        </div>
                      )}

                      {/* Meta */}
                      <div className="text-[10px] text-gray-600 flex gap-3">
                        <span>ID: {d.decision_id}</span>
                        {d.trace_id && <span>Trace: {d.trace_id?.slice(0, 12)}</span>}
                        {d.actor_role && <span>角色: {d.actor_role}</span>}
                      </div>
                    </div>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Empty state */}
      {!loading && runs.length === 0 && (
        <Card className="border-dashed border-gray-700">
          <CardContent className="p-8 text-center">
            <div className="text-gray-600 mb-2">
              <GitCommit className="w-8 h-8 mx-auto" />
            </div>
            <div className="text-sm text-gray-500">暂无决策记录</div>
            <div className="text-xs text-gray-600 mt-1">
              运行 Agent 或 Pipeline 后，工具选择和技能调用将被自动记录
            </div>
          </CardContent>
        </Card>
      )}

      {loading && (
        <div className="text-center text-gray-500 py-8 animate-pulse">加载决策链...</div>
      )}
    </div>
  );
};

export default LineageViewer;
