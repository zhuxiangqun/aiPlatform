import { Link } from 'react-router-dom';
import { useEffect, useMemo, useState } from 'react';
import { Activity, GitBranch, Share2, Zap, Wrench, FolderSearch, Wand2, ShieldCheck, ArrowRight, AlertTriangle, Search, RefreshCw, ChevronRight } from 'lucide-react';

import { Card, CardContent, CardHeader, Badge, Button, toast } from '../../components/ui';
import { diagnosticsApi } from '../../services';

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

// Map audit failures → diagnostic tools
const AUDIT_TO_TOOL: Record<string, { tool: string; href: string; reason: string }> = {
  'model_registry/model_router deprecated': { tool: 'Code Intel', href: '/diagnostics/code-intel', reason: '查看代码依赖图确认 module 引用情况' },
  'Harness→apps 反向依赖': { tool: 'Code Intel', href: '/diagnostics/code-intel', reason: '在 layer 模式查看 harness→apps 的 28 条违规边' },
  'CLAUDE.md 文件存在': { tool: 'Repo', href: '/diagnostics/repo', reason: '全文搜索确认文档覆盖范围' },
  '架构守卫': { tool: 'Audit Logs', href: '/diagnostics/audit', reason: '查看架构违规的审计记录' },
  '平台层→core.harness': { tool: 'Code Intel', href: '/diagnostics/code-intel', reason: '在 file 模式搜索 harness 直导入' },
};

// Map layer + component → diagnostic tools
const LAYER_GUIDANCE: Record<string, { message: string; tool: string; href: string }> = {
  'infra:llm': { message: 'LLM 组件异常，模型调用可能受影响', tool: 'Syscalls', href: '/diagnostics/syscalls' },
  'infra:model': { message: '模型注册异常，检查模型列表', tool: 'Doctor', href: '/diagnostics/doctor' },
  'infra:vector': { message: '向量数据库异常，检索可能降级', tool: 'Syscalls', href: '/diagnostics/syscalls' },
  'core:harness': { message: '执行引擎异常，检查 pipeline 运行状态', tool: 'Runs', href: '/diagnostics/runs' },
  'platform:gateway': { message: 'API 网关异常，检查端点可达性', tool: 'Links', href: '/diagnostics/links' },
};

const Diagnostics: React.FC = () => {
  const [health, setHealth] = useState<Record<string, Health | null>>({
    infra: null, core: null, platform: null, app: null,
  });
  const [error, setError] = useState<string | null>(null);
  const [auditResult, setAuditResult] = useState<any>(null);
  const [auditRunning, setAuditRunning] = useState(false);
  const [auditTab, setAuditTab] = useState('');
  // Architecture guard
  const [guardResult, setGuardResult] = useState<any>(null);
  const [guardRunning, setGuardRunning] = useState(false);
  // Unified diagnostic
  const [diagResult, setDiagResult] = useState<any>(null);
  const [diagRunning, setDiagRunning] = useState(false);
  const [expandedCat, setExpandedCat] = useState<string | null>(null);

  const runGuard = async () => {
    setGuardRunning(true); setGuardResult(null);
    try {
      const res = await fetch('/api/core/diagnostics/guard/run', { method: 'POST' });
      const data = await res.json();
      setGuardResult(data);
    } catch (e: any) { toast.error('守卫检测失败', e?.message || e); }
    finally { setGuardRunning(false); }
  };

  const runAllDiagnostics = async () => {
    setDiagRunning(true); setDiagResult(null);
    try {
      const res = await fetch('/api/core/diagnostics/run-all', { method: 'POST' });
      setDiagResult(await res.json());
    } catch (e: any) { toast.error('诊断失败', e?.message || e); }
    finally { setDiagRunning(false); }
  };

  const catLabels: Record<string, string> = {
    layer_health: '层健康', code_intel: '代码架构', capability: '能力图谱',
    wiki_health: 'Wiki 健康', arch_guard: '架构守卫', compliance: '合规审计',
  };
  const catColors: Record<string, string> = {
    layer_health: 'bg-blue-400', code_intel: 'bg-violet-400', capability: 'bg-amber-400',
    wiki_health: 'bg-purple-400', arch_guard: 'bg-green-400', compliance: 'bg-cyan-400',
  };
  const catLinks: Record<string, string> = {
    code_intel: '/diagnostics/code-intel', capability: '/diagnostics/capability-graph',
    wiki_health: '/platform/kb', arch_guard: '/diagnostics', compliance: '/diagnostics',
  };

  const runAudit = async () => {
    setAuditRunning(true); setAuditResult(null);
    try {
      const res = await fetch('/api/core/entropy/audit');
      const data = await res.json();
      setAuditResult(data);
      const pass = data.items?.filter((i:any) => i.result === '✅')?.length || 0;
      toast.success(`${pass}/${data.items?.length || 11} 项通过`);
    } catch (e: any) { toast.error(`审计失败: ${e?.message || e}`); }
    finally { setAuditRunning(false); }
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
  ], []);

  // Count unhealthy/degraded layers
  const unhealthyLayers = (['infra', 'core', 'platform', 'app'] as const).filter(
    l => health[l]?.status && health[l]!.status !== 'healthy' && health[l]!.status !== 'error'
  );

  // Collect failed audit items with tool guidance
  const auditGuidance = useMemo(() => {
    if (!auditResult?.sections) return [];
    const guidance: any[] = [];
    for (const sec of auditResult.sections) {
      for (const item of (sec.items || [])) {
        if (item.result !== '✅') {
          const key = Object.keys(AUDIT_TO_TOOL).find(k => (item.desc || '').includes(k));
          if (key) guidance.push({ ...AUDIT_TO_TOOL[key], auditItem: item.desc });
        }
      }
    }
    return guidance;
  }, [auditResult]);

  // Compute recommended tools from both Layer Health guidance AND Audit guidance
  const recommendedTools = useMemo(() => {
    const tools = new Set<string>();
    if (unhealthyLayers.length > 0) {
      tools.add('Doctor');
      tools.add('Syscalls');
    }
    for (const g of auditGuidance) {
      tools.add(g.tool);
    }
    return tools;
  }, [unhealthyLayers, auditGuidance]);

  // Collect layer component guidance
  const layerGuidance = useMemo(() => {
    const guidance: any[] = [];
    for (const layer of unhealthyLayers) {
      const h = health[layer];
      const checks = h?.checks || [];
      for (const c of checks) {
        if (c.status === 'unhealthy' || c.status === 'degraded' || c.status === 'unknown') {
          const key = `${layer}:${c.component}`;
          const g = LAYER_GUIDANCE[key];
          if (g) {
            guidance.push({ ...g, layer, component: c.component, status: c.status });
          }
        }
      }
    }
    return guidance;
  }, [health, unhealthyLayers]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-200">可观测性</h1>
        <p className="text-sm text-gray-500 mt-1">Trace / Graph Runs / Links 联动定位问题</p>
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
              {diagResult && (
                <span className={`text-lg font-bold ${
                  diagResult.overall_score >= 75 ? 'text-green-400' : diagResult.overall_score >= 50 ? 'text-yellow-400' : 'text-red-400'
                }`}>
                  {diagResult.overall_score} {diagResult.overall_grade}
                </span>
              )}
            </div>
            <Button variant="primary" size="sm" loading={diagRunning} onClick={runAllDiagnostics}>
              🔍 一键诊断
            </Button>
          </div>
        </CardHeader>
        {diagResult && (
          <CardContent>
            {/* Summary bar */}
            <div className="flex items-center gap-4 mb-4 text-xs">
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
                const icon = s === 'pass' ? '✅' : s === 'warn' ? '⚠️' : s === 'error' ? '❌' : '⚪';
                const isExpanded = expandedCat === key;
                const link = catLinks[key];
                return (
                  <div key={key}>
                    <div
                      onClick={() => setExpandedCat(isExpanded ? null : key)}
                      className={`flex items-center gap-2 p-3 rounded-lg border cursor-pointer hover:border-gray-500 transition-colors ${bg}`}
                    >
                      <div className={`w-2 h-2 rounded-full ${catColors[key] || 'bg-gray-400'}`} />
                      <span className="text-sm text-gray-200 flex-1">{catLabels[key] || key}</span>
                      <span className={`text-sm font-bold ${s === 'pass' ? 'text-green-400' : s === 'warn' ? 'text-yellow-400' : 'text-red-400'}`}>
                        {cat?.score ?? '—'}
                      </span>
                      <ChevronRight className={`w-3 h-3 text-gray-500 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                    </div>
                    {isExpanded && (
                      <div className="mt-1 p-2 bg-dark-bg rounded border border-dark-border text-xs text-gray-400 space-y-1">
                        {cat?.signals && Object.entries(cat.signals).map(([k, v]) => (
                          <div key={k} className="flex justify-between">
                            <span>{k}</span>
                            <span className="text-gray-300">{String(v)}</span>
                          </div>
                        ))}
                        {cat?.violations !== undefined && <div className="flex justify-between"><span>violations</span><span className="text-red-400">{cat.violations}</span></div>}
                        {cat?.issue_count !== undefined && <div className="flex justify-between"><span>issues</span><span className="text-yellow-400">{cat.issue_count}</span></div>}
                        {cat?.error && <div className="text-red-400">{cat.error}</div>}
                        {link && (
                          <Link to={link} className="text-blue-400 hover:text-blue-300 block mt-1">查看详情 →</Link>
                        )}
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
                    {catLabels[iss.category] || iss.category}({iss.score})
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

      {/* ═══════ 确认流程 2: Compliance Audit ═══ */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold text-gray-200">系统合规审计</span>
              {auditResult && (
                <span className={`text-xs px-2 py-0.5 rounded ${
                  (auditResult.passed || 0) >= (auditResult.total || 1) * 0.9 ? 'bg-green-900/50 text-green-300' : 'bg-yellow-900/50 text-yellow-300'
                }`}>
                  {auditResult.verdict} ({auditResult.passed}/{auditResult.total})
                </span>
              )}
            </div>
            <Button variant="primary" size="sm" loading={auditRunning} onClick={runAudit}>🔍 一键审计</Button>
          </div>
        </CardHeader>
        {auditResult && auditResult.sections && (
          <CardContent>
            <div className="flex gap-1 mb-3 border-b border-dark-border pb-2">
              {(auditResult.sections || []).map((sec: any) => (
                <button key={sec.name} onClick={() => setAuditTab(auditTab === sec.name ? '' : sec.name)}
                  className={`px-3 py-1 rounded-t text-xs transition-colors ${
                    auditTab === sec.name || !auditTab ? 'text-primary border-b-2 border-primary' : 'text-gray-500 hover:text-gray-300'
                  }`}>
                  {sec.name} <span className="opacity-60">{sec.score}</span>
                </button>
              ))}
            </div>
            {(auditResult.sections || []).map((sec: any) => {
              if (auditTab && auditTab !== sec.name) return null;
              return (
                <div key={sec.name} className="space-y-1">
                  <div className="text-xs font-medium text-gray-400 mb-1">{sec.name} — {sec.score} 通过</div>
                  {(sec.items || []).map((item: any, idx: number) => {
                    const isFail = item.result !== '✅';
                    const toolEntry = isFail ? Object.entries(AUDIT_TO_TOOL).find(([k]) => (item.desc || '').includes(k)) : null;
                    return (
                      <div key={idx} className={`flex items-start gap-2 text-xs py-1 ${isFail ? 'p-2 rounded bg-dark-bg/50' : ''}`}>
                        <span className="w-4 shrink-0">{item.result}</span>
                        <div className="flex-1">
                          <span className="text-gray-300">{item.desc}</span>
                          {item.detail && <div className="text-gray-500">{item.detail}</div>}
                          {toolEntry && (
                            <Link to={toolEntry[1].href} className="inline-flex items-center gap-1 mt-1 text-blue-400 hover:text-blue-300 text-[10px]">
                              <Search className="w-2.5 h-2.5" />
                              用「{toolEntry[1].tool}」确认 → {toolEntry[1].reason}
                            </Link>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </CardContent>
        )}
      </Card>

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

      {/* ═══════ 确认流程 3: 诊断确认流程（当有问题时显示） ═══ */}
      {(unhealthyLayers.length > 0 || auditGuidance.length > 0) && (
        <Card className="border-primary/30 bg-primary/5">
          <CardHeader>
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
              <AlertTriangle className="w-4 h-4 text-yellow-400" />
              诊断确认流程
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {unhealthyLayers.length > 0 && (
                <div className="flex items-start gap-3 text-xs">
                  <div className="w-5 h-5 rounded-full bg-primary/20 text-primary flex items-center justify-center shrink-0 mt-0.5 font-bold">1</div>
                  <div>
                    <div className="text-yellow-300 font-medium mb-1">
                      Layer 健康确认：{unhealthyLayers.join('、')} 层显示非健康状态
                    </div>
                    <div className="text-gray-500 space-y-1">
                      <div className="flex items-center gap-1">
                        <span className="text-gray-600">→</span>
                        <Link to="/diagnostics/doctor" className="text-blue-400 hover:text-blue-300">
                          打开 Doctor 查看每个组件的详细诊断报告
                        </Link>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="text-gray-600">→</span>
                        <Link to="/diagnostics/syscalls" className="text-blue-400 hover:text-blue-300">
                          打开 Syscalls 查看 sys_llm_generate / sys_tool_call 是否有异常事件
                        </Link>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {auditResult !== null && auditGuidance.length > 0 && (
                <div className="flex items-start gap-3 text-xs">
                  <div className="w-5 h-5 rounded-full bg-primary/20 text-primary flex items-center justify-center shrink-0 mt-0.5 font-bold">2</div>
                  <div>
                    <div className="text-yellow-300 font-medium mb-1">
                      合规审计确认：{auditGuidance.length} 个检查项需要排查
                    </div>
                    <div className="text-gray-500 space-y-1">
                      {auditGuidance.map((g, i) => (
                        <div key={i} className="flex items-center gap-1">
                          <span className="text-gray-600">→</span>
                          <Link to={g.href} className="text-blue-400 hover:text-blue-300">
                            用「{g.tool}」确认：{g.auditItem} — {g.reason}
                          </Link>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {auditResult !== null && (
              <div className="flex items-start gap-3 text-xs">
                <div className="w-5 h-5 rounded-full bg-primary/20 text-primary flex items-center justify-center shrink-0 mt-0.5 font-bold">3</div>
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
              )}
            </div>
          </CardContent>
        </Card>
      )}

        </div>
      </details>

      {/* ═══════════ 诊断工具箱（折叠） ═══════ */}
      <details className="bg-dark-card border border-dark-border rounded-lg overflow-hidden">
        <summary className="px-4 py-3 cursor-pointer text-sm font-semibold text-gray-200 hover:text-gray-100 select-none">
          🛠️ 诊断工具箱
          <span className="text-xs text-gray-500 ml-2">— 按需使用以下工具深入排查（18 个工具）</span>
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
  );
};

export default Diagnostics;
