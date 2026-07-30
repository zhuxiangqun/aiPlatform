/**
 * SimulationPanel — 多场景沙盒推演面板 (Palantir Scenario 对齐)
 *
 * 功能:
 *   1. 从当前 PipelineState 生成变异场景 (换模型 / 改提示词 / 跳过阶段 / 参数变异)
 *   2. 并发执行所有场景的 dry_run 推演
 *   3. 展示基线 vs 各变体的对比报告 (Token / 质量 / 速度 / 产物差异)
 *   4. 风险评估 + 部署建议
 */
import React, { useState, useCallback, useEffect } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import { Play, Cpu, GitBranch, Zap, AlertTriangle, CheckCircle, XCircle, Clock, RefreshCw, ArrowRight } from 'lucide-react';

const API_BASE = '/api/platform/apps/fde';

// ── Types ────────────────────────────────────────────────────────────────

interface SimulationScenario {
  scenario_id: string;
  label: string;
  status: string;
  error?: string;
  artifact_count?: number;
  tokens_used?: number;
  execution_time_ms?: number;
  stages_completed?: number;
  stages_total?: number;
  quality_score?: number;
  risk_level?: number;
  tool_calls?: string[];
}

interface ComparisonEntry {
  scenario: string;
  status: string;
  risk_level: number;
  vs_baseline: {
    tokens_delta: number;
    tokens_pct: number;
    quality_delta: number;
    speed_ratio: number;
    artifact_count_delta: number;
  };
  artifact_diffs?: Array<{ key: string; baseline: string; variant: string }>;
}

interface SimulationReport {
  simulation_id: string;
  total_scenarios: number;
  completed: number;
  failed: number;
  baseline_label: string;
  comparison: ComparisonEntry[];
  scenarios: SimulationScenario[];
  risk_summary: Record<string, any>;
  deployment_readiness: Record<string, any>;
  recommendation: string;
  created_at: string;
  total_tokens_used: number;
  total_execution_time_ms: number;
}

interface HistoryEntry {
  simulation_id: string;
  created_at: string;
  completed: number;
  failed: number;
  recommendation: string;
}

// ── Scenario Presets ──────────────────────────────────────────────────────

const SCENARIO_PRESETS = [
  { id: 'model_deepseek', type: 'model_variant', label: '方案A: DeepSeek-V4', model_overrides: { '*': 'deepseek-v4-pro' } },
  { id: 'model_qwen', type: 'model_variant', label: '方案B: Qwen2.5-7B', model_overrides: { '*': 'qwen2.5-coder:7b' } },
  { id: 'model_gpt4o', type: 'model_variant', label: '方案C: GPT-4o', model_overrides: { '*': 'gpt-4o' } },
  { id: 'skip_qa', type: 'skip_stage', label: '方案D: 跳过QA阶段', skip_stages: [4] },
  { id: 'skip_test', type: 'skip_stage', label: '方案E: 跳过测试', skip_stages: [3] },
  { id: 'tool_restrict', type: 'tool_restriction', label: '方案F: 限制工具集', tool_whitelist: ['kb_query', 'file_read'] },
];

// ── Component ─────────────────────────────────────────────────────────────

const SimulationPanel: React.FC = () => {
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<SimulationReport | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [selectedPresets, setSelectedPresets] = useState<Set<string>>(
    new Set(['model_deepseek', 'model_qwen'])
  );
  const [configOpen, setConfigOpen] = useState(false);
  const [customSeed, setCustomSeed] = useState('');
  const [customRubric, setCustomRubric] = useState('');
  const [mode, setMode] = useState<'full' | 'quick'>('full');
  const [activeTab, setActiveTab] = useState<'compare' | 'scenarios' | 'history'>('compare');

  // Load history on mount
  useEffect(() => {
    fetch(`${API_BASE}/simulations?limit=10`)
      .then(r => r.json()).then(d => setHistory(d.simulations || []))
      .catch(() => {});
  }, []);

  const togglePreset = (id: string) => {
    setSelectedPresets(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const runSimulation = useCallback(async () => {
    setRunning(true);
    setReport(null);
    try {
      if (mode === 'quick') {
        // Quick param mutation mode
        let seedParams = {};
        if (customSeed) {
          try { seedParams = JSON.parse(customSeed); } catch { toast?.error?.('JSON 格式错误'); setRunning(false); return; }
        } else {
          seedParams = { description: '测试场景', gross_demand: 100, safety_stock: 50, on_hand_inventory: 200, collection_id: 'default' };
        }

        let rubric = undefined;
        if (customRubric) {
          try { rubric = JSON.parse(customRubric); } catch { /* ignore */ }
        }

        const r = await fetch(`${API_BASE}/simulate/quick`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ seed_params: seedParams, scenario_count: 5, assessment_rubric: rubric }),
        });
        const d = await r.json();
        setReport(d as SimulationReport);
      } else {
        // Full simulation mode
        const selectedScenarios = SCENARIO_PRESETS.filter(p => selectedPresets.has(p.id));
        const r = await fetch(`${API_BASE}/simulate`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            seed_state: {},
            scenarios: selectedScenarios,
            baseline_label: '基线 (当前配置)',
          }),
        });
        const d = await r.json();
        setReport(d as SimulationReport);
        // Refresh history
        fetch(`${API_BASE}/simulations?limit=10`)
          .then(r => r.json()).then(d => setHistory(d.simulations || []))
          .catch(() => {});
      }
    } catch (e: any) {
      toast?.error?.(e?.message || '推演失败');
    }
    setRunning(false);
  }, [selectedPresets, mode, customSeed, customRubric]);

  // ── Render Helpers ──────────────────────────────────────────────────

  const statusIcon = (status: string) => {
    switch (status) {
      case 'completed': return <CheckCircle className="w-4 h-4 text-green-400" />;
      case 'failed': return <XCircle className="w-4 h-4 text-red-400" />;
      case 'timeout': return <Clock className="w-4 h-4 text-yellow-400" />;
      default: return <AlertTriangle className="w-4 h-4 text-gray-400" />;
    }
  };

  const riskColor = (level: number) => {
    if (level >= 4) return 'text-red-400';
    if (level >= 3) return 'text-orange-400';
    if (level >= 2) return 'text-yellow-400';
    return 'text-green-400';
  };

  const deltaColor = (value: number) => {
    if (value > 0) return 'text-green-400';
    if (value < 0) return 'text-red-400';
    return 'text-gray-400';
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">沙盒推演</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            多场景并发推演 → 对比分析 → 风险评估 → 部署建议
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={mode}
            onChange={e => setMode(e.target.value as 'full' | 'quick')}
            className="bg-gray-800 border border-gray-700 text-gray-300 text-xs rounded px-2 py-1"
          >
            <option value="full">完整推演</option>
            <option value="quick">快速参数变异</option>
          </select>
          <Button variant="ghost" size="sm" onClick={() => setConfigOpen(!configOpen)}>
            {configOpen ? '收起配置' : '展开配置'}
          </Button>
          <Button variant="default" size="sm" onClick={runSimulation} loading={running}>
            <Play className="w-3.5 h-3.5 mr-1" />开始推演
          </Button>
        </div>
      </div>

      {/* Configuration Panel */}
      {configOpen && (
        <Card className="border-gray-700/50">
          <CardContent className="p-3 space-y-3">
            {mode === 'full' ? (
              <>
                <div className="text-xs text-gray-500 font-medium">选择测试场景</div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {SCENARIO_PRESETS.map(p => (
                    <button
                      key={p.id}
                      onClick={() => togglePreset(p.id)}
                      className={`p-2 rounded border text-left text-xs transition-colors ${
                        selectedPresets.has(p.id)
                          ? 'border-blue-500 bg-blue-500/10 text-blue-300'
                          : 'border-gray-700 text-gray-500 hover:border-gray-500'
                      }`}
                    >
                      <div className="font-medium">{p.label}</div>
                      <div className="text-[10px] text-gray-600 mt-0.5">
                        {p.type === 'model_variant' ? '模型切换' : p.type === 'skip_stage' ? '跳过阶段' : '工具限制'}
                      </div>
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <>
                <div className="text-xs text-gray-500 font-medium">种子参数 (JSON)</div>
                <textarea
                  className="w-full h-24 bg-gray-800 border border-gray-700 rounded p-2 text-xs text-gray-200 font-mono"
                  placeholder='{"description":"测试","gross_demand":100,"safety_stock":50}'
                  value={customSeed}
                  onChange={e => setCustomSeed(e.target.value)}
                />
                <div className="text-xs text-gray-500 font-medium">评估规则 (JSON, 可选)</div>
                <textarea
                  className="w-full h-16 bg-gray-800 border border-gray-700 rounded p-2 text-xs text-gray-200 font-mono"
                  placeholder='[{"field":"gross_demand","constraint":"range","expected":[0,10000]}]'
                  value={customRubric}
                  onChange={e => setCustomRubric(e.target.value)}
                />
              </>
            )}
          </CardContent>
        </Card>
      )}

      {/* Report */}
      {report && (
        <div className="space-y-4">
          {/* Dashboard cards */}
          <div className="grid grid-cols-4 gap-3">
            <Card className="border-gray-700/50">
              <CardContent className="p-3 text-center">
                <div className="text-2xl font-bold text-gray-200">{report.completed}/{report.total_scenarios}</div>
                <div className="text-[10px] text-gray-500">通过场景</div>
              </CardContent>
            </Card>
            <Card className="border-gray-700/50">
              <CardContent className="p-3 text-center">
                <div className="text-2xl font-bold text-gray-200">{(report.total_tokens_used / 1000).toFixed(0)}K</div>
                <div className="text-[10px] text-gray-500">Token 总消耗</div>
              </CardContent>
            </Card>
            <Card className="border-gray-700/50">
              <CardContent className="p-3 text-center">
                <div className={`text-2xl font-bold ${riskColor(report.risk_summary?.worst_risk || 0)}`}>
                  {report.risk_summary?.level || '-'}
                </div>
                <div className="text-[10px] text-gray-500">风险等级</div>
              </CardContent>
            </Card>
            <Card className={`border ${report.deployment_readiness?.blocked ? 'border-red-500/30' : 'border-green-500/30'}`}>
              <CardContent className="p-3 text-center">
                <div className={`text-2xl font-bold ${report.deployment_readiness?.blocked ? 'text-red-400' : 'text-green-400'}`}>
                  {report.deployment_readiness?.level || '-'}
                </div>
                <div className="text-[10px] text-gray-500">部署就绪</div>
              </CardContent>
            </Card>
          </div>

          {/* Recommendation */}
          {report.recommendation && (
            <div className={`p-3 rounded text-sm ${
              report.deployment_readiness?.blocked ? 'bg-red-500/10 border border-red-500/20 text-red-400' :
              report.deployment_readiness?.level === 'caution' ? 'bg-yellow-500/10 border border-yellow-500/20 text-yellow-400' :
              'bg-green-500/10 border border-green-500/20 text-green-400'
            }`}>
              {report.deployment_readiness?.blocked ? <AlertTriangle className="w-4 h-4 inline mr-1" /> : <CheckCircle className="w-4 h-4 inline mr-1" />}
              {report.recommendation}
            </div>
          )}

          {/* Tab switcher */}
          <div className="flex gap-2 border-b border-gray-700/50 pb-2">
            {(['compare', 'scenarios', 'history'] as const).map(t => (
              <button
                key={t}
                onClick={() => setActiveTab(t)}
                className={`text-xs px-3 py-1 rounded ${
                  activeTab === t ? 'bg-gray-700 text-gray-200' : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {t === 'compare' ? '对比报告' : t === 'scenarios' ? '场景详情' : '历史记录'}
              </button>
            ))}
          </div>

          {/* Compare Tab */}
          {activeTab === 'compare' && report.comparison.length > 0 && (
            <div className="space-y-3">
              <div className="text-xs text-gray-500">
                基线: {report.baseline_label} | {report.total_scenarios} 个变体场景
              </div>
              {report.comparison.map((c, i) => (
                <Card key={i} className="border-gray-700/50">
                  <CardContent className="p-3">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-gray-200 font-medium">{c.scenario}</span>
                        {statusIcon(c.status)}
                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${riskColor(c.risk_level)}`}>
                          风险 {c.risk_level}
                        </span>
                      </div>
                    </div>
                    <div className="grid grid-cols-5 gap-3 text-xs">
                      <div>
                        <span className="text-gray-500">Token</span>
                        <div className={deltaColor(-c.vs_baseline.tokens_delta)}>
                          {c.vs_baseline.tokens_delta > 0 ? '+' : ''}{c.vs_baseline.tokens_delta} ({c.vs_baseline.tokens_pct > 0 ? '+' : ''}{c.vs_baseline.tokens_pct}%)
                        </div>
                      </div>
                      <div>
                        <span className="text-gray-500">质量</span>
                        <div className={deltaColor(c.vs_baseline.quality_delta)}>
                          {c.vs_baseline.quality_delta > 0 ? '+' : ''}{c.vs_baseline.quality_delta}
                        </div>
                      </div>
                      <div>
                        <span className="text-gray-500">速度</span>
                        <div className="text-gray-300">{c.vs_baseline.speed_ratio}x</div>
                      </div>
                      <div>
                        <span className="text-gray-500">产物</span>
                        <div className={deltaColor(c.vs_baseline.artifact_count_delta)}>
                          {c.vs_baseline.artifact_count_delta > 0 ? '+' : ''}{c.vs_baseline.artifact_count_delta}
                        </div>
                      </div>
                      <div>
                        <span className="text-gray-500">风险</span>
                        <div className={riskColor(c.risk_level)}>
                          {'⬤'.repeat(c.risk_level)}{'⬦'.repeat(5 - c.risk_level)}
                        </div>
                      </div>
                    </div>
                    {c.artifact_diffs && c.artifact_diffs.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-gray-700/50">
                        <div className="text-[10px] text-gray-500 mb-1">产物差异</div>
                        {c.artifact_diffs.slice(0, 5).map((d, j) => (
                          <div key={j} className="text-[10px] mb-1">
                            <span className="text-blue-400">{d.key}</span>
                            <span className="text-gray-600 mx-1">:</span>
                            <span className="text-green-400">{d.baseline}</span>
                            <span className="text-gray-600 mx-1">→</span>
                            <span className="text-purple-400">{d.variant}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {/* Scenarios Tab */}
          {activeTab === 'scenarios' && (
            <div className="space-y-2">
              {report.scenarios.map((s, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded bg-gray-800/50 border border-gray-700/30">
                  <div className="flex items-center gap-2">
                    {statusIcon(s.status)}
                    <span className="text-sm text-gray-200">{s.label}</span>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-gray-500">
                    {s.status === 'completed' && (
                      <>
                        <span>{s.tokens_used?.toLocaleString()} tokens</span>
                        <span>{(s.execution_time_ms! / 1000).toFixed(1)}s</span>
                        <span>质量 {s.quality_score?.toFixed(0)}</span>
                        <span className={riskColor(s.risk_level || 0)}>风险 {s.risk_level}</span>
                      </>
                    )}
                    {s.error && <span className="text-red-400 truncate max-w-[200px]" title={s.error}>{s.error}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* History Tab */}
          {activeTab === 'history' && (
            <div className="space-y-2">
              {history.length === 0 ? (
                <div className="text-xs text-gray-600 text-center py-4">暂无历史记录</div>
              ) : history.map((h, i) => (
                <div key={i} className="flex items-center justify-between p-3 rounded bg-gray-800/50 border border-gray-700/30">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-400 font-mono">{h.simulation_id}</span>
                    <span className="text-[10px] text-gray-600">{h.created_at}</span>
                  </div>
                  <div className="flex items-center gap-3 text-xs">
                    <span className="text-green-400">{h.completed} 通过</span>
                    {h.failed > 0 && <span className="text-red-400">{h.failed} 失败</span>}
                    <span className="text-gray-500">{h.recommendation}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Risk factors */}
          {report.risk_summary?.risk_factors?.length > 0 && (
            <Card className="border-orange-500/20">
              <CardHeader><span className="text-sm font-medium text-gray-200">风险因子</span></CardHeader>
              <CardContent>
                <div className="space-y-1">
                  {report.risk_summary.risk_factors.map((f: string, i: number) => (
                    <div key={i} className="text-xs text-orange-400 flex items-center gap-1">
                      <AlertTriangle className="w-3 h-3" /> {f}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Empty state */}
      {!report && !running && (
        <Card className="border-dashed border-gray-700">
          <CardContent className="p-8 text-center">
            <div className="text-gray-600 mb-2">
              <GitBranch className="w-8 h-8 mx-auto" />
            </div>
            <div className="text-sm text-gray-500">选择场景并点击"开始推演"</div>
            <div className="text-xs text-gray-600 mt-1">
              系统将并发执行所有场景的 dry_run 推演并提供对比报告
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default SimulationPanel;
