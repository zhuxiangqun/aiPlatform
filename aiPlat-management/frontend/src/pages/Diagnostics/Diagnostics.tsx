import { Link } from 'react-router-dom';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, GitBranch, Share2, Zap, Wrench, FolderSearch, Wand2, ShieldCheck, AlertTriangle, BarChart3, ArrowLeftRight, Fingerprint, Heart, Cpu, Users, TrendingUp, Database } from 'lucide-react';

import { Card, CardContent, CardHeader, Badge, Button, toast } from '../../components/ui';
import { diagnosticsApi } from '../../services';
import CategoryDetailPanel from './CategoryDetailPanel';
import ModelTierPanel from '../../components/model/ModelTierPanel';
import ControlProfilePanel from '../../components/model/ControlProfilePanel';
import { reportPageData, clearPageData } from '../../lib/pageDataBridge';

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
  llm_review: [{ tool: 'Code Intel', threshold: 75 }, { tool: 'Syscalls', threshold: 70 }],
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
  full_stack: [{ tool: 'E2E Smoke', threshold: 100 }, { tool: 'Traces', threshold: 90 }, { tool: 'Doctor', threshold: 80 }],
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
  // Per-project scoping
  const [projectId, setProjectId] = useState<string>(() => localStorage.getItem('diag_project_id') || '');
  const [projectList, setProjectList] = useState<Array<{ project_id: string; name: string }>>([]);

  // RAG quality summary

  // Fetch project list + persist selection
  useEffect(() => {
    fetch('/api/platform/builder/projects')
      .then(r => r.json())
      .then(d => setProjectList(d.projects || []))
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (projectId) localStorage.setItem('diag_project_id', projectId);
    else localStorage.removeItem('diag_project_id');
  }, [projectId]);

  const [ragQuality, setRagQuality] = useState<any>(null);
  useEffect(() => {
    fetch('/api/core/diagnostics/rag-quality?hours=24')
      .then(r => r.json())
      .then(d => setRagQuality(d))
      .catch(() => {});
  }, []);

  const runGuard = async () => {
    setGuardRunning(true); setGuardResult(null);
    try {
      const res = await fetch('/api/core/diagnostics/guard/run', { method: 'POST' });
      const data = await res.json();
      setGuardResult(data);
    } catch (e: any) { toast.error('守卫检测失败', e?.message || e); }
    finally { setGuardRunning(false); }
  };

  // ── Retry helper: covers core startup window (10-15s) ──
  const fetchWithRetry = async (url: string, opts: RequestInit = {}, retries = 3): Promise<any> => {
    let lastErr: any;
    for (let i = 0; i < retries; i++) {
      try {
        const res = await fetch(url, opts);
        if (res.status === 502) {
          // Core still initializing — wait and retry
          lastErr = new Error('Core 初始化中');
          await new Promise(r => setTimeout(r, Math.pow(2, i + 1) * 1000));
          continue;
        }
        if (!res.ok) throw new Error(`请求失败 (${res.status})`);
        return await res.json();
      } catch (e: any) {
        lastErr = e;
        if (i < retries - 1) {
          await new Promise(r => setTimeout(r, Math.pow(2, i + 1) * 1000)); // 2s, 4s, 8s
        }
      }
    }
    throw lastErr;
  };

  const runDiagnosticsInBg = async () => {
    setDiagRunning(true);
    setDiagMode('full');
    setDiagResult(null);
    manualRunRef.current = true;
    try {
      const data = await fetchWithRetry('/api/core/diagnostics/run-all', { method: 'POST' });
      if (data.run_id === 'skipped') {
        toast.warning(data.message || '诊断引擎正忙，请等当前诊断完成后再试');
        setDiagRunning(false);
        return;
      }
      // Background mode: poll /latest until complete
      if (data.status === 'started') {
        setDiagRunId(data.run_id || '');
        toast.info('诊断已启动，正在运行中...');
        await pollUntilComplete();
      } else {
        setDiagResult(data);
        setDiagRunId(data.run_id || '');
        setDiagRunning(false);
      }
    } catch (e: any) {
      toast.error('诊断失败', e?.message || String(e));
      setDiagRunning(false);
    } finally {
      manualRunRef.current = false;
    }
  };

  const runQuickDiagnostics = async () => {
    setQuickDiagRunning(true);
    setDiagMode('quick');
    setDiagResult(null);
    manualRunRef.current = true;
    try {
      const data = await fetchWithRetry('/api/core/diagnostics/run-all?quick=true', { method: 'POST' });
      if (data.run_id === 'skipped') {
        toast.warning(data.message || '诊断引擎正忙，请等当前诊断完成后再试');
        setQuickDiagRunning(false);
        return;
      }
      if (data.status === 'started') {
        setDiagRunId(data.run_id || '');
        toast.info('快速诊断已启动，正在运行中...');
        await pollUntilComplete();
      } else {
        setDiagResult(data);
        setDiagRunId(data.run_id || '');
        setQuickDiagRunning(false);
      }
    } catch (e: any) {
      toast.error('快速诊断失败', e?.message || String(e));
      setQuickDiagRunning(false);
    } finally {
      manualRunRef.current = false;
    }
  };

  const pollUntilComplete = async () => {
    for (let i = 0; i < 120; i++) {
      await new Promise(r => setTimeout(r, 1000));
      try {
        const res = await fetch('/api/core/diagnostics/latest');
        if (!res.ok) continue;
        const latest = await res.json();
        if (latest.categories && Object.keys(latest.categories).length > 0 && !latest.status?.startsWith('running')) {
          setDiagResult(latest);
          setDiagRunning(false);
          setQuickDiagRunning(false);
          return;
        }
        // Show visible progress while diagnostic is running
        if (latest.status?.startsWith('running')) {
          const catCount = Object.keys(latest.categories || {}).length;
          setDiagResult({
            overall_score: '...', overall_grade: `运行中 (${catCount}/30)`,
            categories: latest.categories,
            pass: latest.pass || 0, warn: latest.warn || 0, fail: latest.fail || 0,
            status: latest.status,
          });
        }
      } catch { /* retry */ }
    }
    setDiagRunning(false);
    setQuickDiagRunning(false);
    toast.warning('诊断超时（120s），部分结果可能未完成');
  };

  const catLabels: Record<string, string> = {
    core_runtime: 'Core 运行时', code_intel: '代码架构', capability: '能力图谱',
    wiki_health: 'Wiki 健康', arch_guard: '架构守卫',
    wiki_content_quality: 'Wiki内容质量',
    traces: '链路追踪', graph_runs: '图执行', context_metrics: '上下文',
    e2e_smoke: '冒烟测试', doctor: 'Doctor',
    compliance: '合规审计', overview_issues: '概览问题',     skill_lint: 'Skill Lint',
    symbol_health: '符号健康', lsp: 'LSP 诊断', security: '安全扫描',
    governance: '治理', cross_lang: '跨语言', domain_coupling: '领域耦合',
    fragile_base: '脆弱基类', route_coverage: '路由覆盖',
    full_stack: '全域测试', llm_review: 'LLM审查',
  };
  const catColors: Record<string, string> = {
    core_runtime: 'bg-blue-400', code_intel: 'bg-violet-400', capability: 'bg-amber-400',
    wiki_health: 'bg-purple-400', arch_guard: 'bg-green-400',
    wiki_content_quality: 'bg-indigo-400',
    traces: 'bg-cyan-400', graph_runs: 'bg-teal-400', context_metrics: 'bg-indigo-400',
    e2e_smoke: 'bg-orange-400', doctor: 'bg-red-400',
    compliance: 'bg-emerald-400', overview_issues: 'bg-rose-400', skill_lint: 'bg-violet-400',
    symbol_health: 'bg-teal-400', lsp: 'bg-fuchsia-400', security: 'bg-lime-400',
    governance: 'bg-amber-400', cross_lang: 'bg-gray-400', domain_coupling: 'bg-gray-400',
    fragile_base: 'bg-gray-400', route_coverage: 'bg-gray-400',
    full_stack: 'bg-sky-400', llm_review: 'bg-cyan-400',
  };
  
  const ON_DEMAND_GUIDE: Record<string, {label: string; href: string; action: string}> = {
    arch_guard:  { label: '架构守卫', href: '', action: 'runGuard' },
    compliance:  { label: '架构守卫', href: '', action: 'runGuard' },
    e2e_smoke:   { label: 'E2E Smoke', href: '/diagnostics/smoke', action: '' },
    llm_review:  { label: 'LLM审查', href: '/diagnostics/llm-review', action: '' },
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
    const ctrl = new AbortController();
    fetch('/api/core/diagnostics/latest', { signal: ctrl.signal })
      .then(r => r.json())
      .then(data => {
        // Only load completed diagnostics (not partial/incremental cache)
        if (!manualRunRef.current && data.status === 'complete') {
          setDiagResult(data);
        }
      })
      .catch(() => {});
    return () => ctrl.abort();
  }, [isRunning]);

  const items = useMemo(() => [
    { title: 'Doctor', desc: '一键聚合诊断报告', href: '/diagnostics/doctor', icon: Activity },
    { title: 'LLM审查', desc: 'DeepSeek 深度代码审查 — ~150K tokens/次，按需运行', href: '/diagnostics/llm-review', icon: Zap },
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
    { title: '能力边界', desc: '各业务域的数据成熟度、可用Skill、Golden Query通过率', href: '/diagnostics/capability-boundary', icon: BarChart3 },
    { title: 'Observability', desc: 'LLM 调用 / 延迟 / Token 消耗 / 错误率', href: '/diagnostics/observability', icon: BarChart3 },
    { title: 'Run 对比', desc: '并排对比两次执行的差异', href: '/diagnostics/run-comparison', icon: ArrowLeftRight },
    { title: 'Model Playground', desc: '同一 Prompt 并发多模型输出对比', href: '/diagnostics/model-playground', icon: Zap },
    { title: 'Model Audit', desc: 'LLM 指纹溯源与身份验证', href: '/diagnostics/model-audit', icon: Fingerprint },
    { title: 'Safety', desc: '对话危机检测与情感安全监控', href: '/diagnostics/safety', icon: Heart },
    { title: 'Eval Dashboard', desc: '统一评估：Arena排名、AB评分、进化适应度、Token效率', href: '/diagnostics/eval', icon: BarChart3 },
    { title: 'RAG 质量', desc: 'RAG检索+生成质量仪表盘（忠实度/检索通过率/用户信号）', href: '/diagnostics/rag-quality', icon: BarChart3 },
    { title: '控制画像', desc: '6维控制画像状态与切换（上下文/工具/模型/编排/记忆/输出）', href: '/diagnostics/control-profile', icon: Cpu },
  ], []);

  // Count unhealthy/degraded layers
  const unhealthyLayers = (['infra', 'core', 'platform', 'app'] as const).filter(
    l => health[l]?.status && health[l]!.status !== 'healthy' && health[l]!.status !== 'error'
  );

  // P2-4: 向数字人上报当前诊断页的实时状态（健康概览 + 最近诊断结果）
  useEffect(() => {
    const layerStatus: Record<string, string> = {};
    (['infra', 'core', 'platform', 'app'] as const).forEach(l => {
      if (health[l]?.status) layerStatus[l] = health[l]!.status;
    });
    reportPageData('/diagnostics', {
      layerStatus,
      unhealthyLayers: unhealthyLayers.join(','),
      guardResult: guardResult ? (guardResult.passed !== undefined ? `guard=${guardResult.passed ? 'PASS' : 'FAIL'}` : undefined) : undefined,
      diagRunId: diagRunId || undefined,
      diagMode: diagMode || undefined,
    });
    return () => clearPageData('/diagnostics');
  }, [health, guardResult, diagRunId, diagMode, unhealthyLayers]);

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

  // v2.9: Knowledge drift status
  const [driftStatus, setDriftStatus] = useState<any>(null);
  const [driftRebuilding, setDriftRebuilding] = useState(false);
  useEffect(() => {
    fetch('/api/core/diagnostics/drift-status')
      .then(r => r.json()).then(setDriftStatus).catch(() => {});
    fetch('/api/core/diagnostics/ontology-audit/summary')
      .then(r => r.json()).then(setAuditSummary).catch(() => {});
    fetch('/api/core/diagnostics/adoption-metrics')
      .then(r => r.json()).then(setAdoptionMetrics).catch(() => {});
    fetch('/api/core/diagnostics/system-health')
      .then(r => r.json()).then(setSysHealth).catch(() => {});
  }, []);

  // v2.9: System health
  const [sysHealth, setSysHealth] = useState<any>(null);

  // v2.9: Ontology audit summary
  const [auditSummary, setAuditSummary] = useState<any>(null);
  const [adoptionMetrics, setAdoptionMetrics] = useState<any>(null);

  const handleDriftRebuild = async () => {
    setDriftRebuilding(true);
    try {
      const r = await fetch('/api/core/diagnostics/drift-rebuild', { method: 'POST' });
      const d = await r.json();
      toast.success(`重建完成: ${d.rebuilt} 个页面`);
      setDriftStatus(null); // refetch
      fetch('/api/core/diagnostics/drift-status').then(r => r.json()).then(setDriftStatus);
    } catch { toast.error('重建失败'); }
    setDriftRebuilding(false);
  };

  return (
    <>
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-200">诊断概览</h1>
        <p className="text-sm text-gray-500 mt-1">平台健康 · 知识健康 · 项目健康 · 运行时安全</p>
      </div>

      {/* Project scoping */}
      {projectList.length > 0 && (
        <div className="flex items-center gap-3 bg-dark-card border border-dark-border rounded-lg px-4 py-2.5">
          <span className="text-xs text-gray-400 whitespace-nowrap">📂 诊断项目</span>
          <select
            value={projectId}
            onChange={e => setProjectId(e.target.value)}
            className="flex-1 bg-dark-bg border border-dark-border rounded px-3 py-1.5 text-sm text-gray-200 outline-none focus:border-blue-500/50"
          >
            <option value="">-- 系统全局 --</option>
            {projectList.map(p => (
              <option key={p.project_id} value={p.project_id}>{p.name}</option>
            ))}
          </select>
          {!projectId && (
            <span className="text-[11px] text-gray-500">选择项目后，控制画像、可观测性等数据将按项目筛选</span>
          )}
          {projectId && (
            <button
              onClick={() => setProjectId('')}
              className="text-[11px] text-gray-400 hover:text-gray-200 transition-colors whitespace-nowrap"
            >
              清除选择
            </button>
          )}
        </div>
      )}

      {/* v2.9: System Health Index Card */}
      {sysHealth && (
        <Card className={sysHealth.grade?.startsWith('A') ? 'border-green-700/40 bg-green-950/10' :
          sysHealth.grade?.startsWith('B') ? 'border-blue-700/40 bg-blue-950/10' :
          'border-yellow-700/40 bg-yellow-950/10'}>
          <CardContent className="p-4">
            <div className="flex items-center gap-6">
              <div className="text-center">
                <div className="text-4xl font-bold text-gray-100">{sysHealth.health_index}</div>
                <div className={`text-sm font-semibold mt-1 ${sysHealth.grade?.startsWith('A') ? 'text-green-400' :
                  sysHealth.grade?.startsWith('B') ? 'text-blue-400' : 'text-yellow-400'}`}>
                  {sysHealth.grade}级 {sysHealth.trend} {sysHealth.trend_delta > 0 ? '+' : ''}{sysHealth.trend_delta}
                </div>
              </div>
              <div className="flex-1">
                <div className="text-sm font-medium text-gray-200 mb-2">系统健康指数</div>
                <div className="grid grid-cols-4 gap-2">
                  {Object.entries(sysHealth.sub_scores || {}).map(([k, v]: [string, any]) => (
                    <div key={k} className="text-center p-1.5 rounded bg-dark-bg">
                      <div className={`text-lg font-bold ${v.score >= 80 ? 'text-green-400' : v.score >= 60 ? 'text-yellow-400' : 'text-red-400'}`}>{v.score}</div>
                      <div className="text-xs text-gray-500">{v.label}</div>
                    </div>
                  ))}
                </div>
                {sysHealth.recommendations?.length > 0 && (
                  <div className="mt-2 text-xs text-blue-400">
                    💡 {sysHealth.recommendations[0]}
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ═══════════ 4-Category Navigation ═══════ */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <Link to="/diagnostics" className="p-4 rounded-lg border border-blue-700/30 bg-blue-950/10 hover:bg-blue-950/20 transition-colors">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-5 h-5 text-blue-400" />
            <span className="text-sm font-semibold text-gray-200">📊 平台健康</span>
          </div>
          <p className="text-xs text-gray-500">综合诊断 · 控制画像 · 可观测性</p>
        </Link>
        <Link to="/diagnostics/knowledge-health" className="p-4 rounded-lg border border-purple-700/30 bg-purple-950/10 hover:bg-purple-950/20 transition-colors">
          <div className="flex items-center gap-2 mb-2">
            <Database className="w-5 h-5 text-purple-400" />
            <span className="text-sm font-semibold text-gray-200">🧠 知识健康</span>
          </div>
          <p className="text-xs text-gray-500">本体审计 · 知识漂移 · LLM 审查</p>
        </Link>
        <Link to="/diagnostics/eval" className="p-4 rounded-lg border border-green-700/30 bg-green-950/10 hover:bg-green-950/20 transition-colors">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-5 h-5 text-green-400" />
            <span className="text-sm font-semibold text-gray-200">📈 项目健康</span>
          </div>
          <p className="text-xs text-gray-500">业务价值 · Agent 评估 · 修复中心</p>
        </Link>
        <Link to="/diagnostics/safety" className="p-4 rounded-lg border border-red-700/30 bg-red-950/10 hover:bg-red-950/20 transition-colors">
          <div className="flex items-center gap-2 mb-2">
            <ShieldCheck className="w-5 h-5 text-red-400" />
            <span className="text-sm font-semibold text-gray-200">🔍 安全与合规</span>
          </div>
          <p className="text-xs text-gray-500">安全监控 · 审计 · 变更控制</p>
        </Link>
      </div>

      {/* ── Below: existing detailed diagnostic cards ── */}

      {error && (
        <div className="text-sm text-error bg-error-light border border-dark-border rounded-lg p-3">{error}</div>
      )}

      {/* v2.9: Knowledge Drift Card */}
      {driftStatus && driftStatus.total_stale > 0 && (
        <Card className={driftStatus.status === 'critical' ? 'border-red-700/40 bg-red-950/20' : 'border-yellow-700/40 bg-yellow-950/20'}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className={`w-4 h-4 ${driftStatus.status === 'critical' ? 'text-red-400' : 'text-yellow-400'}`} />
                <span className="text-sm font-semibold text-gray-200">知识漂移</span>
                <Badge variant={driftStatus.status === 'critical' ? 'error' : 'warning'}>
                  {driftStatus.total_stale} stale
                </Badge>
              </div>
              <Button variant="ghost" size="sm" onClick={handleDriftRebuild} loading={driftRebuilding}>
                <Wrench className="w-3 h-3 mr-1" />自动重建
              </Button>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              扫描 {driftStatus.total_scanned} 页，{driftStatus.total_stale} 页源文档已发生变化，漂移率 {(driftStatus.drift_ratio * 100).toFixed(1)}%
            </p>
          </CardHeader>
          {driftStatus.stale_pages?.length > 0 && (
            <CardContent>
              <div className="space-y-1 max-h-32 overflow-y-auto">
                {driftStatus.stale_pages.slice(0, 5).map((p: any, i: number) => (
                  <div key={i} className="text-xs text-gray-400 flex items-center gap-2">
                    <span className="text-yellow-500">⚠</span>
                    <span className="text-gray-300">{p.title}</span>
                    <span className="text-gray-600">({p.stale_sources?.length || 0} 源已变化)</span>
                  </div>
                ))}
                {driftStatus.stale_pages.length > 5 && (
                  <div className="text-xs text-gray-500">... 还有 {driftStatus.stale_pages.length - 5} 页</div>
                )}
              </div>
            </CardContent>
          )}
        </Card>
      )}

      {/* v2.9: Ontology Audit Card */}
      {auditSummary && auditSummary.total_entities > 0 && (
        <Card className={auditSummary.total_orphans > 0 ? 'border-yellow-700/40 bg-yellow-950/20' : 'border-green-700/40 bg-green-950/20'}>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <GitBranch className={`w-4 h-4 ${auditSummary.total_orphans > 0 ? 'text-yellow-400' : 'text-green-400'}`} />
                <span className="text-sm font-semibold text-gray-200">本体审计</span>
                <Badge variant={auditSummary.total_orphans > 0 ? 'warning' : 'success'}>
                  {auditSummary.total_entities} 实体
                </Badge>
              </div>
              <Link to="/infra/ontology" className="text-xs text-blue-400 hover:underline">本体管理</Link>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              {auditSummary.domains_scanned} 个域审计 — {auditSummary.total_orphans} 个孤儿类（YAML中有定义但无实体）
            </p>
          </CardHeader>
          {auditSummary.worst_domains?.length > 0 && (
            <CardContent>
              <div className="space-y-1 max-h-28 overflow-y-auto">
                {auditSummary.worst_domains.slice(0, 5).map((d: any, i: number) => (
                  <div key={i} className="text-xs text-gray-400 flex items-center gap-2">
                    <span className={d.orphans > 0 ? 'text-yellow-500' : 'text-green-500'}>
                      {d.orphans > 0 ? '⚠' : '✅'}
                    </span>
                    <span className="text-gray-300 w-28 truncate">{d.domain}</span>
                    <span className="text-gray-600">{d.entities} entities, {d.edge_count} edges, {d.orphans} orphans</span>
                  </div>
                ))}
              </div>
            </CardContent>
          )}
        </Card>
      )}

      {/* v2.9: Employee Adoption Metrics Card */}
      {adoptionMetrics?.report && (
        <Card className="border-blue-700/40 bg-blue-950/20">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Users className="w-4 h-4 text-blue-400" />
                <span className="text-sm font-semibold text-gray-200">员工采纳度</span>
                <Badge variant={adoptionMetrics.report.adoption_trend === 'rising' ? 'success' : adoptionMetrics.report.adoption_trend === 'declining' ? 'error' : 'warning'}>
                  {adoptionMetrics.report.adoption_trend}
                </Badge>
              </div>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              {adoptionMetrics.report.total_users} 用户 · {adoptionMetrics.report.active_users_7d} 活跃(7d) · {adoptionMetrics.report.total_agent_calls} 次调用
            </p>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-4 gap-3 mb-3">
              <div className="text-center p-2 rounded bg-dark-bg">
                <div className="text-lg font-bold text-blue-400">{(adoptionMetrics.report.grill_trigger_rate * 100).toFixed(0)}%</div>
                <div className="text-xs text-gray-500">需求澄清率</div>
              </div>
              <div className="text-center p-2 rounded bg-dark-bg">
                <div className="text-lg font-bold text-green-400">{(adoptionMetrics.report.grill_completion_rate * 100).toFixed(0)}%</div>
                <div className="text-xs text-gray-500">澄清完成率</div>
              </div>
              <div className="text-center p-2 rounded bg-dark-bg">
                <div className="text-lg font-bold text-yellow-400">{(adoptionMetrics.report.hitl_approval_rate * 100).toFixed(0)}%</div>
                <div className="text-xs text-gray-500">审批通过率</div>
              </div>
              <div className="text-center p-2 rounded bg-dark-bg">
                <div className="text-lg font-bold text-red-400">{(adoptionMetrics.report.hitl_rejection_rate * 100).toFixed(0)}%</div>
                <div className="text-xs text-gray-500">审批驳回率</div>
              </div>
            </div>
            {adoptionMetrics.report.resistance_hotspots?.length > 0 && (
              <div className="space-y-1 max-h-24 overflow-y-auto border-t border-gray-700/50 pt-2">
                <div className="text-xs text-gray-500 mb-1">抵触热点</div>
                {adoptionMetrics.report.resistance_hotspots.slice(0, 3).map((h: any, i: number) => (
                  <div key={i} className="text-xs text-gray-400 flex items-center gap-2">
                    <span className={h.severity === 'high' ? 'text-red-400' : 'text-yellow-400'}>
                      {h.severity === 'high' ? '🔴' : '🟡'}
                    </span>
                    <span className="text-gray-500">{h.user}</span>
                    <span>{h.signals.slice(0, 2).join(', ')}</span>
                  </div>
                ))}
              </div>
            )}
            {adoptionMetrics.report.recommendations?.length > 0 && (
              <div className="border-t border-gray-700/50 pt-2 mt-2">
                {adoptionMetrics.report.recommendations.slice(0, 2).map((r: string, i: number) => (
                  <div key={i} className="text-xs text-blue-400">💡 {r}</div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ═══════════ Unified Diagnostic ═══════ */}
      <Card className="border-primary/20 bg-dark-card">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Activity className="w-5 h-5 text-primary" />
              <span className="text-sm font-semibold text-gray-200">综合诊断报告</span>
              <span className="text-[10px] text-gray-500 bg-dark-bg px-1.5 py-0.5 rounded">
                {diagResult ? Object.keys(diagResult.categories || {}).filter(k => !['wiki_health','wiki_content_quality','rag_quality','compliance'].includes(k)).length : '—'} 类检查
              </span>
              {diagResult && (
                <span className={`text-lg font-bold ${
                  diagResult.status?.startsWith('running') ? 'text-blue-400' :
                  diagResult.overall_score >= 75 ? 'text-green-400' : diagResult.overall_score >= 50 ? 'text-yellow-400' : 'text-red-400'
                }`}>
                  {diagResult.status?.startsWith('running')
                    ? diagResult.overall_grade
                    : `${diagResult.overall_score} ${diagResult.overall_grade}`}
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
              {Object.entries(diagResult.categories || {})
                .filter(([key]) => !['wiki_health','wiki_content_quality','rag_quality','compliance'].includes(key))
                .map(([key, cat]: [string, any]) => {
                const s = cat?.status || 'unknown';
                const bg = s === 'pass' ? 'bg-green-900/20 border-green-500/20'
                  : s === 'warn' ? 'bg-yellow-900/20 border-yellow-500/20'
                  : s === 'info' ? 'bg-blue-900/20 border-blue-500/20'
                  : s === 'timeout' ? 'bg-gray-900/20 border-gray-500/20'
                  : 'bg-red-900/20 border-red-500/20';
                const guide = ON_DEMAND_GUIDE[key];
                const handleGuideClick = (e: React.MouseEvent) => {
                  e.stopPropagation();
                  if (guide?.action === 'runGuard') {
                    // Scroll to the guard section and trigger it, or call the API directly
                    const section = document.getElementById('arch-guard-section');
                    if (section) {
                      section.scrollIntoView({ behavior: 'smooth' });
                    }
                    // Always trigger the guard run
                    setGuardRunning(true); setGuardResult(null);
                    fetch('/api/core/diagnostics/guard/run', { method: 'POST' })
                      .then(r => r.json())
                      .then(d => setGuardResult(d))
                      .catch(e => toast.error('守卫检测失败', e?.message || e))
                      .finally(() => setGuardRunning(false));
                  } else if (guide?.href) {
                    window.location.href = guide.href;
                  }
                };

                // ── On-demand check: simplified one-button card ──
                if (s === 'info' && guide) {
                  return (
                    <div key={key} className="border border-blue-500/20 rounded-lg overflow-hidden">
                      <div className={`flex items-center gap-2 p-3 ${bg}`}>
                        <div className={`w-2 h-2 rounded-full ${catColors[key] || 'bg-gray-400'}`} />
                        <span className="text-sm text-gray-200 flex-1">
                          {catLabels[key] || key}
                          <span className="text-[10px] text-blue-400 ml-1">🏃 按需运行</span>
                        </span>
                      </div>
                      <div className="p-3 bg-dark-bg/50 flex flex-col items-center gap-2">
                        <p className="text-xs text-gray-500 text-center">
                          {cat?.items?.[0]?.detail || '重量级检查，点击下方按钮单独运行'}
                        </p>
                        <Button variant="primary" size="sm" onClick={handleGuideClick}>
                          {guide.label === '架构守卫' ? '🛡️ 运行架构守卫' :
                           guide.label === 'E2E Smoke' ? '🚀 运行 E2E Smoke' :
                           guide.label === 'LLM审查' ? '🤖 运行 LLM 审查' : `运行 ${guide.label}`}
                        </Button>
                      </div>
                    </div>
                  );
                }

                // ── Normal check: expandable card ──
                return (
                  <div key={key} className="border rounded-lg overflow-hidden">
                    <div
                      onClick={() => setExpandedCat(expandedCat === key ? null : key)}
                      className={`flex items-center gap-2 p-3 cursor-pointer hover:border-gray-500 ${bg}`}
                    >
                      <div className={`w-2 h-2 rounded-full ${catColors[key] || 'bg-gray-400'}`} />
                      <span className="text-sm text-gray-200 flex-1">
                        {catLabels[key] || key}
                        {s === 'info' && guide && (
                          <span className="text-[10px] text-blue-400 ml-1 cursor-pointer hover:underline" onClick={handleGuideClick}>
                            🏃 按需 → {guide.label}
                          </span>
                        )}
                      </span>
                      <span className={`text-sm font-bold ${s === 'pass' ? 'text-green-400' : s === 'warn' ? 'text-yellow-400' : s === 'info' ? 'text-blue-400' : s === 'timeout' ? 'text-gray-400' : 'text-red-400'}`}>
                        {s === 'info' ? '→ 运行' : cat?.score ?? '—'}
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
                        {/* v2.2: autoreview evidence chain status */}
                        {cat?._autoreview && (cat._autoreview.last_clean || cat._autoreview.total_runs > 0) && (
                          <div className="mt-2 pt-2 border-t border-gray-800 text-xs text-gray-400 space-y-1">
                            {cat._autoreview.last_clean && (
                              <div>
                                <span className="text-green-400">✓</span>
                                {` Last clean: ${new Date(cat._autoreview.last_clean * 1000).toLocaleString()}`}
                              </div>
                            )}
                            <div>
                              {`Mode: ${cat._autoreview.mode_used || 'N/A'}`}
                              {cat._autoreview.engines?.length > 0
                                ? ` · Engines: ${(cat._autoreview.engines as string[]).join(', ')}`
                                : ''}
                              {cat._autoreview.total_runs > 0
                                ? ` · Clean rate: ${cat._autoreview.clean_rate}`
                                : ''}
                            </div>
                          </div>
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
                  {diagResult.top_issues.map((iss: any, i: number) => {
                    const isOnDemand = ON_DEMAND_GUIDE[iss.category];
                    return (
                    <span key={i} className={`ml-2 ${isOnDemand ? 'text-blue-400' : 'text-gray-400'}`}>
                      {isOnDemand 
                        ? `${iss.label || catLabels[iss.category]} → 点击${isOnDemand.label}单独运行`
                        : iss.label || `${catLabels[iss.category] || iss.category}(${iss.score})`}
                      {i < diagResult.top_issues.length - 1 ? '、' : ''}
                    </span>
                  )})}
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
      <Card id="arch-guard-section">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-green-400" />
              <span className="text-sm font-semibold text-gray-200">架构守卫</span>
              {guardResult && (
                <span className={`text-xs px-2 py-0.5 rounded ${
                  guardResult.summary.fail === 0 ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'
                }`}>
                  {guardResult.summary.fail === 0 ? '✅ 通过' : `❌ ${guardResult.summary.fail} 失败`}
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

      {ragQuality?.metrics && (
      <Card className="border-green-500/30 bg-green-500/5">
        <CardHeader>
          <div className="flex items-center gap-2 text-sm font-semibold text-gray-200">
            <BarChart3 className="w-4 h-4 text-green-400" />
            RAG 质量概览（过去24h）
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-5 gap-3 text-center text-xs">
            {[
              { label: '忠实度', value: ragQuality.metrics.faithfulness_score ?? '-', unit: '' },
              { label: '回答相关度', value: ragQuality.metrics.answer_relevancy_score ?? '-', unit: '' },
              { label: '检索精度', value: ragQuality.metrics.retrieval_precision ?? '-', unit: '' },
              { label: '会话数', value: ragQuality.metrics.total_sessions ?? 0, unit: '' },
              { label: '重试率', value: ragQuality.metrics.retry_rate ?? '-', unit: '%' },
            ].map(m => (
              <div key={m.label}>
                <div className="text-gray-500">{m.label}</div>
                <div className={`text-lg font-bold ${
                  typeof m.value === 'number' && m.label !== '会话数' && m.label !== '重试率'
                    ? m.value >= 0.8 ? 'text-green-400' : m.value >= 0.6 ? 'text-yellow-400' : 'text-red-400'
                    : 'text-gray-200'
                }`}>
                  {m.value}{m.unit}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-2 text-right">
            <Link to="/platform/kb?tab=eval" className="text-blue-400 hover:text-blue-300 text-xs">
              查看趋势 →
            </Link>
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

      {/* ═══════════ Phase 14: Model Tier Panel ═══════ */}
      <ModelTierPanel />

      {/* ═══════════ ControlProfile Panel ═══════ */}
      <ControlProfilePanel projectId={projectId || undefined} />

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
