import { Link } from 'react-router-dom';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, GitBranch, Share2, Zap, Wrench, FolderSearch, Wand2, ShieldCheck, AlertTriangle, BarChart3, ArrowLeftRight } from 'lucide-react';

import { Card, CardContent, CardHeader, Badge, Button, toast } from '../../components/ui';
import { diagnosticsApi } from '../../services';
import CategoryDetailPanel from './CategoryDetailPanel';

type Health = {
  layer: string;
  status: 'healthy' | 'degraded' | 'unhealthy' | string;
  timestamp?: string;
  checks?: { component: string; status: string; message: string; details?: any }[];
};

const toBadgeVariant = (status: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  if (status === 'healthy' || status === 'success') return 'success';
  if (status === 'degraded' || status === 'warn' || status === 'warning') return 'warning';
  if (status === 'unhealthy' || status === 'error' || status === 'failed') return 'error';
  if (status === 'running') return 'info';
  return 'default';
};

// Map diagnostic category → recommended toolbox tools (score below threshold or violations > 0)
const DIAG_TO_TOOL: Record<string, { tool: string; threshold: number }[]> = {
  code_intel: [{ tool: 'Code Intel', threshold: 75 }, { tool: 'Repo', threshold: 70 }],
  arch_guard: [{ tool: 'Code Intel', threshold: 100 }],
  skill_lint: [{ tool: 'Doctor', threshold: 75 }],
  wiki_health: [{ tool: 'Doctor', threshold: 60 }],
  capability: [{ tool: 'Capability→Policy', threshold: 75 }],
  core_runtime: [{ tool: 'Doctor', threshold: 80 }, { tool: 'Syscalls', threshold: 80 }, { tool: 'Runs', threshold: 75 }],
  traces: [{ tool: 'Traces', threshold: 80 }],
  graph_runs: [{ tool: 'Graph Runs', threshold: 80 }],
  context_metrics: [{ tool: 'Context', threshold: 80 }],
  e2e_smoke: [{ tool: 'E2E Smoke', threshold: 75 }],
  symbol_health: [{ tool: 'Code Intel', threshold: 75 }],
  lsp: [{ tool: 'Code Intel', threshold: 75 }],
  security: [{ tool: 'Audit Logs', threshold: 75 }],
  governance: [{ tool: 'Tenant Policies', threshold: 75 }],
  compliance: [{ tool: 'Audit Logs', threshold: 80 }, { tool: 'Tenant Policies', threshold: 75 }],
  overview_issues: [{ tool: 'Doctor', threshold: 80 }],
  doctor: [{ tool: 'Doctor', threshold: 80 }],
  cross_lang: [{ tool: 'Code Intel', threshold: 80 }],
  domain_coupling: [{ tool: 'Code Intel', threshold: 80 }],
  fragile_base: [{ tool: 'Code Intel', threshold: 80 }],
  route_coverage: [{ tool: 'Links', threshold: 80 }, { tool: 'Traces', threshold: 75 }],
  mcp: [{ tool: 'Syscalls', threshold: 75 }],
  frontend: [{ tool: 'Code Intel', threshold: 80 }],
  skill_realness: [{ tool: 'Doctor', threshold: 75 }],
};

const Diagnostics: React.FC = () => {
  const [health, setHealth] = useState<Record<string, Health | null>>({
    infra: null, core: null, platform: null, app: null,
  });
  const [error, setError] = useState<string | null>(null);
  // Architecture guard
  const [guardResult, setGuardResult] = useState<any>(null);
  const [guardRunning, setGuardRunning] = useState(false);
  // Unified diagnostic
  const [diagResult, setDiagResult] = useState<any>(null);
  const [diagRunId, setDiagRunId] = useState('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailCategory, setDetailCategory] = useState('');
  const [diagRunning, setDiagRunning] = useState(false);
  const [quickDiagRunning, setQuickDiagRunning] = useState(false);
  const [diagMode, setDiagMode] = useState<'full' | 'quick' | null>(null);
  const [expandedCat, setExpandedCat] = useState<string | null>(null);
  // 防止手动运行后 useEffect 中 latest 覆盖结果
  const manualRunRef = useRef(false);

  const runGuard = async () => {
    setGuardRunning(true); setGuardResult(null);
    try {
      const res = await fetch('/api/core/diagnostics/guard/run', { method: 'POST' });
      const data = await res.json();
      setGuardResult(data);
    } catch (e: any) { toast.error('守卫检测失败', e?.message || e); }
    finally { setGuardRunning(false); }
  };

  const runDiagnosticsInBg = async () => {
    setDiagRunning(true);
    setDiagMode('full');
    setDiagResult(null);
    manualRunRef.current = true;
    try {
      const res = await fetch('/api/core/diagnostics/run-all', { method: 'POST' });
      const data = await res.json();
      setDiagResult(data);
      setDiagRunId(data.run_id || '');
      setDiagRunning(false);
    } catch (e: any) {
      setDiagRunning(false);
      toast.error('诊断失败', e?.message || e);
    }
  };

  const runQuickDiagnostics = async () => {
    setQuickDiagRunning(true);
    setDiagMode('quick');
    setDiagResult(null);
    manualRunRef.current = true;
    try {
      const res = await fetch('/api/core/diagnostics/run-all?quick=true', { method: 'POST' });
      const data = await res.json();
      setDiagResult(data);
      setDiagRunId(data.run_id || '');
      setQuickDiagRunning(false);
    } catch (e: any) {
      setQuickDiagRunning(false);
      toast.error('快速诊断失败', e?.message || e);
    }
  };

  const catLabels: Record<string, string> = {
    core_runtime: 'Core 运行时', code_intel: '代码架构', capability: '能力图谱',
    wiki_health: 'Wiki 健康', arch_guard: '架构守卫',
    traces: '链路追踪', graph_runs: '图执行', context_metrics: '上下文',
    e2e_smoke: '冒烟测试', doctor: 'Doctor',
    compliance: '合规审计', overview_issues: '概览问题',     skill_lint: 'Skill Lint',
    symbol_health: '符号健康', lsp: 'LSP 诊断', security: '安全扫描',
    governance: '治理', cross_lang: '跨语言', domain_coupling: '领域耦合',
    fragile_base: '脆弱基类', route_coverage: '路由覆盖',
  };
  const catColors: Record<string, string> = {
    core_runtime: 'bg-blue-400', code_intel: 'bg-violet-400', capability: 'bg-amber-400',
    wiki_health: 'bg-purple-400', arch_guard: 'bg-green-400',
    traces: 'bg-cyan-400', graph_runs: 'bg-teal-400', context_metrics: 'bg-indigo-400',
    e2e_smoke: 'bg-orange-400', doctor: 'bg-red-400',
    compliance: 'bg-emerald-400', overview_issues: 'bg-rose-400', skill_lint: 'bg-violet-400',
    symbol_health: 'bg-teal-400', lsp: 'bg-fuchsia-400', security: 'bg-lime-400',
    governance: 'bg-amber-400', cross_lang: 'bg-gray-400', domain_coupling: 'bg-gray-400',
    fragile_base: 'bg-gray-400', route_coverage: 'bg-gray-400',
  };
  
  useEffect(() => {
    let mounted = true;
    (async () => {
      setError(null);
      try {
        const layers: Array<keyof typeof health> = ['infra', 'core', 'platform', 'app'];
        const results = await Promise.allSettled(layers.map((l) => diagnosticsApi.getHealth(l)));
        const next: Record<string, Health | null> = {};
        results.forEach((r, idx) => {
          const layer = layers[idx];
          if (r.status === 'fulfilled') next[layer] = r.value as any;
          else next[layer] = { layer, status: 'error' };
        });
        if (mounted) setHealth(next);
      } catch (e: any) {
        if (mounted) setError(e?.message || '加载失败');
      }
    })();
    return () => { mounted = false; };
  }, []);

  const isRunning = diagRunning || quickDiagRunning;

  // Load cached diagnostic on mount — skip if user already clicked manual run
  useEffect(() => {
    if (isRunning || manualRunRef.current) return;
    fetch('/api/core/diagnostics/latest')
      .then(r => r.json())
      .then(data => { if (data.cached !== false && data.overall_score != null) setDiagResult(data); })
      .catch(() => {});
  }, [isRunning]);

  const items = useMemo(() => [
    { title: 'Doctor', desc: '一键聚合诊断报告', href: '/diagnostics/doctor', icon: Activity },
    { title: 'Workflows', desc: '把评估/证据/门控串成一键流水线', href: '/diagnostics/workflows', icon: Wand2 },
    { title: 'Context', desc: 'Prompt/context 组装诊断（cache/search/注入）', href: '/diagnostics/context', icon: Activity },
    { title: 'Capability→Policy', desc: '从 skill capabilities 生成工具门禁策略', href: '/diagnostics/capability-policy', icon: Activity },
    { title: 'Exec Backends', desc: '执行后端 health 与当前 backend', href: '/diagnostics/exec-backends', icon: Activity },
    { title: 'Traces', desc: '链路追踪与 spans 定位', href: '/diagnostics/traces', icon: Activity },
    { title: 'Graph Runs', desc: '执行 runs / checkpoints / 恢复', href: '/diagnostics/graphs', icon: GitBranch },
    { title: 'Links', desc: '输入任意 ID 联动查询', href: '/diagnostics/links', icon: Share2 },
    { title: 'Repo', desc: 'Repo 索引/全文搜索（gitignore-aware）', href: '/diagnostics/repo', icon: FolderSearch },
    { title: 'Code Intel', desc: '代码架构/影响面/风险扫描', href: '/diagnostics/code-intel', icon: FolderSearch },
    { title: 'Runs', desc: 'run_id 维度的摘要与事件流', href: '/diagnostics/runs', icon: Share2 },
    { title: 'Audit Logs', desc: '关键操作审计日志', href: '/diagnostics/audit', icon: Share2 },
    { title: 'Tenant Policies', desc: 'Policy-as-code 策略快照', href: '/diagnostics/policies', icon: Share2 },
    { title: 'Policy Debug', desc: '策略评估调试（RBAC + Policy）', href: '/diagnostics/policy-debug', icon: Activity },
    { title: 'Syscalls', desc: 'syscall_events 检索（tool/llm/skill）', href: '/diagnostics/syscalls', icon: Zap },
    { title: 'Change Control', desc: '变更控制台（change_id / gates / approvals）', href: '/diagnostics/change-control', icon: GitBranch },
    { title: 'E2E Smoke', desc: '生产级全链路冒烟（自动清理）', href: '/diagnostics/smoke', icon: Zap },
    { title: 'Ops', desc: '导出（CSV）/ DLQ / 配额用量', href: '/diagnostics/ops', icon: Wrench },
    { title: 'Observability', desc: 'LLM 调用 / 延迟 / Token 消耗 / 错误率', href: '/diagnostics/observability', icon: BarChart3 },
    { title: 'Run 对比', desc: '并排对比两次执行的差异', href: '/diagnostics/run-comparison', icon: ArrowLeftRight },
    { title: 'Model Playground', desc: '同一 Prompt 并发多模型输出对比', href: '/diagnostics/model-playground', icon: Zap },
    { title: 'Eval Dashboard', desc: '统一评估：Arena排名、AB评分、进化适应度、Token效率', href: '/diagnostics/eval', icon: BarChart3 },
  ], []);

  // Count unhealthy/degraded layers
  const unhealthyLayers = (['infra', 'core', 'platform', 'app'] as const).filter(
    l => health[l]?.status && health[l]!.status !== 'healthy' && health[l]!.status !== 'error'
  );

  // Compute recommended tools from Layer Health + unified diagnostic results
  const recommendedTools = useMemo(() => {
    const tools = new Set<string>();
    // From layer health: Doctor + Syscalls
    if (unhealthyLayers.length > 0) {
      tools.add('Doctor');
      tools.add('Syscalls');
    }
    // From unified diagnostic results
    if (diagResult?.categories) {
      for (const [key, cat] of Object.entries(diagResult.categories) as [string, any][]) {
        const mappings = DIAG_TO_TOOL[key];
        if (!mappings) continue;
        const score = cat?.score;
        const violations = cat?.violations ?? 0;
        for (const m of mappings) {
          if ((m.threshold < 100 && score != null && score < m.threshold) ||
              (m.threshold >= 100 && violations > 0)) {
            tools.add(m.tool);
          }
        }
      }
    }
    return tools;
  }, [unhealthyLayers, diagResult]);

  // Collect layer component guidance
  return (
    <>
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-200">诊断中心</h1>
        <p className="text-sm text-gray-500 mt-1">综合诊断 · 合规审计 · 架构守卫 · 诊断工具</p>
      </div>

      {error && (
        <div className="text-sm text-error bg-error-light border border-dark-border rounded-lg p-3">{error}</div>
      )}

      {/* ═══════════ Unified Diagnostic ═══════ */}
      <Card className="border-primary/20 bg-dark-card">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Activity className="w-5 h-5 text-primary" />
              <span className="text-sm font-semibold text-gray-200">综合诊断报告</span>
              <span className="text-[10px] text-gray-500 bg-dark-bg px-1.5 py-0.5 rounded">
                {diagResult ? Object.keys(diagResult.categories || {}).length : '—'} 类检查
              </span>
              {diagResult && (
                <span className={`text-lg font-bold ${
                  diagResult.overall_score >= 75 ? 'text-green-400' : diagResult.overall_score >= 50 ? 'text-yellow-400' : 'text-red-400'
                }`}>
                  {diagResult.overall_score} {diagResult.overall_grade}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button variant="primary" size="sm" loading={diagRunning} disabled={quickDiagRunning} onClick={runDiagnosticsInBg}>
                🔍 一键诊断
              </Button>
              <Button variant="secondary" size="sm" loading={quickDiagRunning} disabled={diagRunning} onClick={runQuickDiagnostics} title="跳过LSP/安全扫描等慢检查">
                ⚡ 快速
              </Button>
            </div>
          </div>
        </CardHeader>
        {diagResult && (
          <CardContent>
            {/* Summary bar */}
            <div className="flex items-center gap-4 mb-4 text-xs">
              {diagMode && (
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${diagMode === 'quick' ? 'bg-amber-900/40 text-amber-300' : 'bg-blue-900/40 text-blue-300'}`}>
                  {diagMode === 'quick' ? '⚡ 快速模式' : '🔍 完整模式'}
                </span>
              )}
              <span className="text-green-400">✅ {diagResult.pass} 通过</span>
              <span className="text-yellow-400">⚠️ {diagResult.warn} 警告</span>
              <span className="text-red-400">❌ {diagResult.fail} 失败</span>
              <span className="text-gray-500">| {diagResult.duration_ms}ms</span>
            </div>
            {/* Category cards */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {Object.entries(diagResult.categories || {}).map(([key, cat]: [string, any]) => {
                const s = cat?.status || 'unknown';
                const bg = s === 'pass' ? 'bg-green-900/20 border-green-500/20' : s === 'warn' ? 'bg-yellow-900/20 border-yellow-500/20' : 'bg-red-900/20 border-red-500/20';
                return (
                  <div key={key} className="border rounded-lg overflow-hidden">
                    <div
                      onClick={() => setExpandedCat(expandedCat === key ? null : key)}
                      className={`flex items-center gap-2 p-3 cursor-pointer hover:border-gray-500 ${bg}`}
                    >
                      <div className={`w-2 h-2 rounded-full ${catColors[key] || 'bg-gray-400'}`} />
                      <span className="text-sm text-gray-200 flex-1">{catLabels[key] || key}</span>
                      <span className={`text-sm font-bold ${s === 'pass' ? 'text-green-400' : s === 'warn' ? 'text-yellow-400' : 'text-red-400'}`}>
                        {key === 'arch_guard' && cat?.violations != null ? `${cat.violations}违规` : cat?.score ?? '—'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center px-3 py-1.5 bg-dark-bg/50">
                      <span className="text-[10px] text-gray-600 cursor-pointer hover:text-gray-400" onClick={() => setExpandedCat(expandedCat === key ? null : key)}>
                        详情 {expandedCat === key ? '▲' : '▼'}
                      </span>
                      <Button size="sm" variant="ghost" onClick={() => { setDetailCategory(key); setDetailOpen(true); }}>
                        ▶ 执行
                      </Button>
                    </div>
                    {expandedCat === key && (
                      <div className="p-3 bg-dark-bg border-t border-dark-border text-xs text-gray-400 space-y-1">
                        {cat?.items && cat.items.length > 0 && (
                          <>
                            <div className="text-gray-500 mb-1 border-b border-dark-border pb-1">检测项</div>
                            {cat.items.slice(0, 10).map((item: any, i: number) => (
                              <div key={i} className="flex items-start gap-1.5 py-0.5">
                                <span className="shrink-0">{item.result || '✅'}</span>
                                <span className="text-gray-300">{item.check}</span>
                                {item.detail && <span className="text-gray-500 ml-1">— {item.detail}</span>}
                              </div>
                            ))}
                          </>
                        )}
                        {cat?.signals && Object.entries(cat.signals).filter(([k]) => k !== 'note').map(([k, v]) => (
                          <div key={k} className="flex justify-between py-0.5">
                            <span className="text-gray-600">{k}</span>
                            <span className="text-gray-300">{v != null ? String(v) : '-'}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            {/* Top issues */}
            {diagResult.top_issues?.length > 0 && (
              <div className="mt-3 p-2 bg-red-900/10 rounded border border-red-500/20 text-xs">
                <span className="text-yellow-400 font-medium">需关注：</span>
                  {diagResult.top_issues.map((iss: any, i: number) => (
                    <span key={i} className="ml-2 text-gray-400">
                      {iss.label || `${catLabels[iss.category] || iss.category}(${iss.score})`}
                      {i < diagResult.top_issues.length - 1 ? '、' : ''}
                  </span>
                ))}
              </div>
            )}
          </CardContent>
        )}
      </Card>

      {/* ═══════════ 分类诊断（折叠） ═══════ */}
      <details className="bg-dark-card border border-dark-border rounded-lg overflow-hidden">
        <summary className="px-4 py-3 cursor-pointer text-sm font-semibold text-gray-200 hover:text-gray-100 select-none">
          📊 分类诊断
          <span className="text-xs text-gray-500 ml-2">— 按类别手动运行各项诊断</span>
        </summary>
        <div className="px-4 pb-4 space-y-4">
      {/* ═══════════ 确认流程 1: Layer Health ═══════ */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {(['infra', 'core', 'platform', 'app'] as const).map((layer) => {
          const h = health[layer];
          const isBad = h?.status && h.status !== 'healthy' && h.status !== 'error';
          return (
            <Card key={layer}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-gray-200 uppercase">{layer}</div>
                  <Badge variant={toBadgeVariant(h?.status || 'default')}>{h?.status || '...'}</Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-xs text-gray-500">{h?.timestamp ? `更新时间：${h.timestamp}` : '—'}</div>
                {isBad && (
                  <div className="mt-2 p-2 rounded bg-yellow-900/10 border border-yellow-900/30 text-[10px]">
                    <div className="flex items-center gap-1 text-yellow-400 mb-1">
                      <AlertTriangle className="w-3 h-3" /> 建议确认：
                    </div>
                    <div className="text-gray-400">
                      点击「<b>Doctor</b>」查看组件级诊断 →
                    </div>
                    <div className="text-gray-400">
                      点击「<b>Syscalls</b>」查看调用链 →
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* ═══════ Architecture Guard ═══ */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-green-400" />
              <span className="text-sm font-semibold text-gray-200">架构守卫</span>
              {guardResult && (
                <span className={`text-xs px-2 py-0.5 rounded ${
                  guardResult.violations === 0 ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'
                }`}>
                  {guardResult.violations === 0 ? '✅ 通过' : `❌ ${guardResult.violations} 违规`}
                </span>
              )}
            </div>
            <Button variant="secondary" size="sm" loading={guardRunning} onClick={runGuard}>🛡️ 运行守卫</Button>
          </div>
        </CardHeader>
        {guardResult && guardResult.sections && (
          <CardContent>
            <div className="flex items-center gap-3 mb-3 text-xs text-gray-400">
              <span className="text-green-400">{guardResult.summary.pass} 通过</span>
              {guardResult.summary.warn > 0 && <span className="text-yellow-400">{guardResult.summary.warn} 警告</span>}
              {guardResult.summary.fail > 0 && <span className="text-red-400">{guardResult.summary.fail} 失败</span>}
              <span className="text-gray-600">| 共 {guardResult.summary.total} 项</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-1">
              {guardResult.sections.filter((s: any) => s.items?.length > 0).map((s: any) => {
                const color = s.status === 'fail' ? 'border-red-900/30 bg-red-900/10' : s.status === 'warn' ? 'border-yellow-900/30 bg-yellow-900/10' : 'border-dark-border/50';
                const icon = s.status === 'fail' ? '❌' : s.status === 'warn' ? '⚠️' : '✅';
                return (
                  <div key={s.number} className={`flex items-center gap-1.5 px-2 py-1 rounded border text-xs ${color}`}>
                    <span>{icon}</span>
                    <span className="text-gray-400 truncate">§{s.number} {s.name}</span>
                    {s.items.filter((i: any) => i.tag !== 'pass').length > 0 && (
                      <span className={`ml-auto text-[10px] ${s.status === 'fail' ? 'text-red-400' : 'text-yellow-400'}`}>
                        {s.items.filter((i: any) => i.tag !== 'pass').length} issues
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </CardContent>
        )}
      </Card>

      {/* ═══════ 确认流程: 诊断确认 ═══ */}
      {recommendedTools.size > 0 && (
        <Card className="border-primary/30 bg-primary/5">
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
              <AlertTriangle className="w-4 h-4 text-yellow-400" />
              诊断确认流程
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex items-start gap-3 text-xs">
                <div className="w-5 h-5 rounded-full bg-primary/20 text-primary flex items-center justify-center shrink-0 mt-0.5 font-bold">1</div>
                <div>
                  <div className="text-yellow-300 font-medium mb-1">
                    {unhealthyLayers.length > 0
                      ? `Layer 健康确认：${unhealthyLayers.join('、')} 层显示非健康状态`
                      : '综合诊断发现需关注项'}
                  </div>
                  <div className="text-gray-500 space-y-1">
                    {unhealthyLayers.length > 0 && (
                      <>
                        <div className="flex items-center gap-1">
                          <span className="text-gray-600">→</span>
                          <Link to="/diagnostics/doctor" className="text-blue-400 hover:text-blue-300">
                            打开 Doctor 查看每个组件的详细诊断报告
                          </Link>
                        </div>
                        <div className="flex items-center gap-1">
                          <span className="text-gray-600">→</span>
                          <Link to="/diagnostics/syscalls" className="text-blue-400 hover:text-blue-300">
                            打开 Syscalls 查看调用链是否有异常事件
                          </Link>
                        </div>
                      </>
                    )}
                    <div className="flex items-center gap-1">
                      <span className="text-gray-600">→</span>
                      <span className="text-gray-400">
                        查看下方「诊断工具箱」中标记
                        <span className="text-yellow-400"> ← 推荐</span> 的工具进行深入排查
                      </span>
                    </div>
                  </div>
                </div>
              </div>
              <div className="flex items-start gap-3 text-xs">
                <div className="w-5 h-5 rounded-full bg-primary/20 text-primary flex items-center justify-center shrink-0 mt-0.5 font-bold">2</div>
                <div>
                  <div className="text-gray-300 font-medium mb-1">汇总确认 → 运行 E2E Smoke</div>
                  <div className="text-gray-500">
                    <span className="text-gray-600">→</span>
                    <Link to="/diagnostics/smoke" className="text-blue-400 hover:text-blue-300 ml-1">
                      运行全链路冒烟测试
                    </Link>
                    <span className="text-gray-600"> 验证修复后系统是否恢复正常</span>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

        </div>
      </details>

      {/* Anthropic 5 Patterns — execution mode recommendation */}
      {diagResult && (
        <Card className="bg-dark-card border-primary/20 mb-4">
          <CardContent className="p-3">
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <span className="text-blue-400">💡</span>
              <span>
                执行模式建议：Anthropic 推荐首选
                <span className="text-green-400">链式/路由/并行</span>模式；
                只有子任务不可预知时才用
                <span className="text-yellow-400"> orchestrator/agent</span>。
                <a href="https://www.anthropic.com/engineering/building-effective-agents" target="_blank" rel="noreferrer"
                   className="text-blue-400 hover:text-blue-300 ml-1 underline">
                  Building Effective Agents →
                </a>
              </span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ═══════════ 诊断工具箱（折叠） ═══════ */}
      <details className="bg-dark-card border border-dark-border rounded-lg overflow-hidden">
        <summary className="px-4 py-3 cursor-pointer text-sm font-semibold text-gray-200 hover:text-gray-100 select-none">
          🛠️ 诊断工具箱
          <span className="text-xs text-gray-500 ml-2">— 按需使用以下工具深入排查（{items.length} 个工具）</span>
        </summary>
        <div className="px-4 pb-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {items.map((it) => {
            const isRecommended = recommendedTools.has(it.title);
            return (
              <Link key={it.href} to={it.href} className="block">
                <Card hoverable className={isRecommended ? 'border-primary/50 bg-primary/5' : ''}>
                  <CardHeader>
                    <div className="flex items-center gap-2">
                      <it.icon className={`w-4 h-4 ${isRecommended ? 'text-primary' : 'text-gray-500'}`} />
                      <div className={`text-sm font-semibold ${isRecommended ? 'text-primary' : 'text-gray-200'}`}>
                        {it.title}
                        {isRecommended && <span className="ml-1 text-[10px] text-yellow-400">← 推荐</span>}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="text-sm text-gray-500">{it.desc}</div>
                  </CardContent>
                </Card>
              </Link>
            );
          })}
        </div>
        </div>
      </details>
    </div>

    <CategoryDetailPanel
      open={detailOpen}
      runId={diagRunId}
      categoryKey={detailCategory}
      categoryName={catLabels[detailCategory] || detailCategory}
      categoryResult={diagResult?.categories?.[detailCategory]}
      onClose={() => setDetailOpen(false)}
    />
    </>
  );
};

export default Diagnostics;
