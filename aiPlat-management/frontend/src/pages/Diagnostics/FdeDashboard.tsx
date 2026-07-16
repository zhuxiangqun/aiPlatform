/**
 * FdeDashboard — FDE 工作台 (Field Deployment Engineer Toolkit, 方向一)
  *
  * FDE 流程步骤 (按 FDE 七项能力流程排列):
  *   ① 业务认知 → ② 评估域 → ③ 问题重构 → ④ 验证价值 →
  *   ⑤ 快速构建 → ⑥ 评测护栏 → ⑦ 验收移交 → ⑧ 运营监控
  */
import React, { useEffect, useState, useCallback, useRef } from 'react';
import { Card, CardContent, CardHeader, Button, toast } from '../../components/ui';
import { Wrench, RefreshCw, Package, Download, Users, FileText, Target, Activity, AlertTriangle, Send, Clipboard, TrendingUp, CheckCircle, UserCheck, BookOpen, Plus, ChevronDown, ChevronRight, X, ArrowRightLeft, Trash2, Pencil } from 'lucide-react';
import CapabilityBoundary from './CapabilityBoundary';
import FloatingFeedback from './FloatingFeedback';

const API = (path: string) => `/api/core/fde${path}`;

// ── 工作流状态类型 (append-only pipeline, 每个 Tab 只写 1 个 key) ──
interface CustomerInfo {
  name: string;
  namespace: string;
  industry?: string;
  description?: string;
  deployment_mode?: string;
}
interface DomainInfo {
  id: string;
  maturity: string;
  skillsAvailable: number;
}
interface DiagnosisInfo {
  deepProblem: string;
  recommendedDomain: string;
  reportText: string;
}
interface CanaryResult {
  passed: boolean;
  qualityScore: number;
}

// ── 行业 → 域推荐映射 ──
const INDUSTRY_DOMAIN_MAP: Record<string, string[]> = {
  'manufacturing': ['supply-chain', 'ship-design', 'it-ops'],
  'finance': ['finance', 'procurement-mvo'],
  'retail': ['supply-chain', 'procurement-mvo'],
  'general': ['ai-knowledge', 'default'],
};

// ── FDE 流程步骤 (按 FDE 七项能力 → 运营监控) ──
const FDE_STEPS = [
  { key: 'customers',  label: '① 业务认知', icon: Users,      hint: '了解客户业务模式、痛点、关键流程' },
  { key: 'capability', label: '② 评估域',   icon: Target,      hint: '查看各域数据成熟度、可用Skill、已知缺口' },
  { key: 'assess',     label: '③ 问题重构', icon: FileText,    hint: 'field_assessment 诊断 → 表层需求翻译为真实问题' },
  { key: 'poc',        label: '④ 验证价值', icon: Wrench,      hint: '行业模板 + 数据注入 → 快速POC验证 ROI' },
  { key: 'deploy',     label: '⑤ 快速构建', icon: Package,     hint: '打包部署到客户环境，先跑通核心链路' },
  { key: 'canary',     label: '⑥ 评测护栏', icon: TrendingUp,  hint: '灰度发布 + 质量门禁 + 回滚预案' },
  { key: 'accept',     label: '⑦ 验收移交', icon: CheckCircle, hint: '签收 + 移交 + 首月护航' },
  { key: 'evolution',  label: '⑧ 运营监控', icon: Activity,    hint: '运营指标 + 反馈闭环 + 资产沉淀' },
] as const;

type TabKey = typeof FDE_STEPS[number]['key'];

// ── Dashboard ──
const FdeDashboard: React.FC = () => {
  const [tab, setTab] = useState<TabKey>('customers');
  const [customer, setCustomer] = useState<CustomerInfo | null>(null);
  const [domain, setDomain] = useState<DomainInfo | null>(null);
  const [diagnosis, setDiagnosis] = useState<DiagnosisInfo | null>(null);
  const [pocProfile, setPocProfile] = useState<string | null>(null);
  const [deployVersion, setDeployVersion] = useState<string | null>(null);
  const [canaryResult, setCanaryResult] = useState<CanaryResult | null>(null);
  const [adopted, setAdopted] = useState(false);
  const [workflowStages, setWorkflowStages] = useState<any[]>([]);
  const [workflowState, setWorkflowState] = useState<Record<string, any>>({});
  const [workflowName, setWorkflowName] = useState('');
  const [domainStats, setDomainStats] = useState<Record<string, number>>({});
  const [domainStatsExpanded, setDomainStatsExpanded] = useState(true);

  useEffect(() => {
    fetch('/api/core/diagnostics/capability-boundary')
      .then(r => r.json())
      .then(d => {
        const stats: Record<string, number> = {};
        const domains = d.domains || d.data || d || {};
        for (const [, v] of Object.entries(domains)) {
          const m = (v as any)?.maturity || 'unknown';
          stats[m] = (stats[m] || 0) + 1;
        }
        setDomainStats(stats);
      })
      .catch(() => setDomainStats({ error: 1 }));
  }, []);

  const loadWorkflow = async (name: string) => {
    if (!name) { setWorkflowStages([]); setWorkflowName(''); return; }
    try {
      const r = await fetch(`/api/core/workflow/templates/${name}`);
      const d = await r.json();
      setWorkflowStages(d.stages || []);
      setWorkflowName(d.name || name);
    } catch { setWorkflowStages([]); }
  };

  const progressItems = React.useMemo(() => {
    if (workflowStages.length > 0) {
      const stateMap: Record<string, boolean> = {
        customer_profile: !!customer,
        solution_design: !!(diagnosis || domain),
        deployment_package: !!(deployVersion || canaryResult?.passed),
        acceptance_report: adopted,
      };
      const tabMap: Record<string, string> = {
        customer_profile: '①',
        solution_design: '②③',
        deployment_package: '④⑤⑥',
        acceptance_report: '⑦⑧',
      };
      const stageTab: Record<string, TabKey> = {
        customer_profile: 'customers',
        solution_design: 'capability',
        deployment_package: 'poc',
        acceptance_report: 'accept',
      };
      const stages = workflowStages.map(s => ({
        key: s.output_artifact,
        label: (s.agent_name || s.id || '').replace('FDE', '').trim() || s.id,
        tabs: tabMap[s.output_artifact] || '',
        tabKey: stageTab[s.output_artifact],
        done: stateMap[s.output_artifact] || false,
        active: false,
      }));
      const currentIdx = stages.findIndex(s => !s.done);
      if (currentIdx !== -1) stages[currentIdx].active = true;
      return stages;
    }
    return [
      { key: 'customers',  label: '客户', tabs: '①', tabKey: 'customers',  done: !!customer, active: tab === 'customers' },
      { key: 'capability', label: '域',   tabs: '②', tabKey: 'capability', done: !!domain, active: tab === 'capability' },
      { key: 'assess',     label: '诊断',  tabs: '③', tabKey: 'assess',     done: !!diagnosis, active: tab === 'assess' },
      { key: 'poc',        label: 'POC',  tabs: '④', tabKey: 'poc',        done: !!pocProfile, active: tab === 'poc' },
      { key: 'deploy',     label: '部署',  tabs: '⑤', tabKey: 'deploy',     done: !!deployVersion, active: tab === 'deploy' },
      { key: 'canary',     label: '灰度',  tabs: '⑥', tabKey: 'canary',     done: !!canaryResult?.passed, active: tab === 'canary' },
      { key: 'accept',     label: '验收',  tabs: '⑦', tabKey: 'accept',     done: adopted, active: tab === 'accept' },
      { key: 'evolution',  label: '监控',  tabs: '⑧', tabKey: 'evolution',  done: adopted, active: tab === 'evolution' },
    ];
  }, [workflowStages, customer, domain, diagnosis, pocProfile, deployVersion, canaryResult, adopted, tab]);

  const nextStepHint = React.useMemo(() => {
    const isWorkflow = workflowStages.length > 0;
    if (!customer) return { 
      text: isWorkflow ? '请先完成 ① 业务认知：选择或创建客户 Profile → BA 完成后自动流转' : '请先在 ① 业务认知 中选择或创建客户',
      tab: 'customers' as TabKey
    };
    if (!domain) return {
      text: isWorkflow ? '✅ BA 已完成。请前往 ② 评估域 选择业务领域 → SA 自动匹配方案' : '✅ 客户已就绪，请前往 ② 评估域 选择业务领域',
      tab: 'capability' as TabKey
    };
    if (!diagnosis) return {
      text: isWorkflow ? '✅ 域已匹配，SA 已启动诊断。请前往 ③ 问题重构 查看方案设计' : '✅ 域已匹配，请前往 ③ 问题重构 运行诊断',
      tab: 'assess' as TabKey
    };
    if (!pocProfile) return {
      text: '✅ 诊断完成，请前往 ④ 验证价值 加载 POC 模板',
      tab: 'poc' as TabKey
    };
    if (!deployVersion) return {
      text: isWorkflow ? '✅ POC 已通过，DE 正在构建部署包。请前往 ⑤ 快速构建 查看进度' : '✅ POC 验证通过，请前往 ⑤ 快速构建 打包部署',
      tab: 'deploy' as TabKey
    };
    if (!canaryResult?.passed) return {
      text: isWorkflow ? '✅ 部署包已生成，DE 正在灰度发布。请前往 ⑥ 评测护栏 查看质量指标' : '✅ 部署完成，请前往 ⑥ 评测护栏 灰度发布',
      tab: 'canary' as TabKey
    };
    if (!adopted) return {
      text: isWorkflow ? '✅ 灰度已通过，请前往 ⑦ 验收移交 签字确认 → DM 完成后项目移交' : '✅ 灰度通过，请前往 ⑦ 验收移交 签字确认',
      tab: 'accept' as TabKey
    };
    return {
      text: isWorkflow ? '🎉 工作流全部完成！请前往 ⑧ 运营监控 查看运行状态' : '🎉 所有步骤已完成，⑧ 运营监控 查看运行状态',
      tab: 'evolution' as TabKey
    };
  }, [workflowStages.length, customer, domain, diagnosis, pocProfile, deployVersion, canaryResult, adopted]);

  return (
    <div className="space-y-4 p-4">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-100">FDE 工作台
            <span className="text-xs text-gray-500 ml-2 font-normal">
              {workflowName || '自由模式'}
            </span>
          </h1>
          <select onChange={e => loadWorkflow(e.target.value)} value={workflowName ? 'fde_delivery_v1' : ''}
            className="text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-400">
            <option value="">自由模式（默认）</option>
            <option value="fde_delivery_v1">FDE 标准交付 v1</option>
          </select>
       </div>
      {/* ── 流程进度指示 ── */}
      <div className="flex items-center gap-1.5 text-xs text-gray-500 flex-wrap">
        <span className="mr-1">进度：</span>
        {progressItems.map((p, i) => (
          <span key={p.key} className="flex items-center gap-1">
            <span onClick={() => p.tabKey && setTab(p.tabKey)}
              className={p.active ? 'text-blue-400 font-semibold cursor-pointer hover:underline' : p.done ? 'text-green-400 cursor-pointer hover:underline' : 'text-gray-600 cursor-pointer hover:text-gray-400'}>
              {p.done ? `${p.label} ✓` : p.label}
            </span>
            {p.tabs && <span className="text-[10px] opacity-70">{p.tabs}</span>}
            {i < progressItems.length - 1 && <span className="text-gray-700">→</span>}
          </span>
        ))}
      </div>
      {nextStepHint && (
        <div className="flex items-center gap-2 px-3 py-2 rounded bg-blue-500/10 border border-blue-500/20 text-xs">
          <span className="text-blue-300">{nextStepHint.text}</span>
          <button onClick={() => setTab(nextStepHint.tab)}
            className="px-2 py-0.5 rounded bg-blue-600 hover:bg-blue-500 text-white text-xs font-medium shrink-0">
            前往 →
          </button>
        </div>
      )}
      {Object.keys(domainStats).length > 0 && (
        <div className="flex items-center gap-2 px-3 py-1.5 rounded bg-gray-800/50 border border-gray-700/50 text-xs text-gray-400">
          <span className="text-gray-500">域健康：</span>
          {domainStatsExpanded ? (
            <>
              {(['production-ready', 'stable', 'building', 'seeding'] as string[]).map(m => {
                const cnt = domainStats[m] || 0;
                if (!cnt) return null;
                const cs: Record<string, string> = {
                  'production-ready': 'text-green-400', 'stable': 'text-blue-400',
                  'building': 'text-yellow-400', 'seeding': 'text-gray-500',
                };
                const lb: Record<string, string> = {
                  'production-ready': '生产', 'stable': '稳定', 'building': '构建中', 'seeding': '播种',
                };
                return <span key={m} className={cs[m] || ''}>{lb[m]} {cnt}</span>;
              })}
              {Object.values(domainStats).every(v => v === 0 || v === undefined) ? (
                <span className="text-gray-600">无数据</span>
              ) : domainStats.error ? (
                <span className="text-red-500">API 不可达</span>
              ) : null}
              <button onClick={() => setDomainStatsExpanded(false)}
                className="text-gray-600 hover:text-gray-400 ml-1">▲</button>
            </>
          ) : (
            <>
            <span className="text-gray-500">
              {['production-ready','stable','building','seeding'].filter(m => domainStats[m]).map(m => {
                const lb: Record<string,string> = {'production-ready':'生产','stable':'稳定','building':'构建中','seeding':'播种'};
                return `${lb[m]} ${domainStats[m]}`;
              }).join('  ') || '无数据'}
            </span>
            <button onClick={() => setDomainStatsExpanded(true)}
              className="text-gray-600 hover:text-gray-400 ml-1">▼</button>
            </>
          )}
        </div>
      )}
      <div className="flex gap-1 border-b border-gray-700/50 pb-0">
        {FDE_STEPS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            title={t.hint}
            className={`flex items-center gap-1.5 px-3 py-2 text-sm border-b-2 whitespace-nowrap transition-colors ${
              tab === t.key ? 'border-blue-500 text-white' : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            <t.icon className="w-3.5 h-3.5" />{t.label}
          </button>
        ))}
      </div>
      {tab === 'customers'  && <CustomersTab onSelect={setCustomer} diagnosis={diagnosis} />}
      {tab === 'capability' && <CapabilityBoundary industry={customer?.industry} onSelect={setDomain} />}
      {tab === 'assess'     && <AssessTab domain={domain?.id ?? null} customerDesc={customer?.description || ''} customerName={customer?.name || ''} customerIndustry={customer?.industry || ''} onReport={setDiagnosis} />}
      {tab === 'poc'        && <PocTab domain={domain} onProfileSet={setPocProfile} />}
      {tab === 'deploy'     && <DeployTab profile={pocProfile} onDeployed={setDeployVersion} />}
      {tab === 'canary'     && <CanaryTab deployVersion={deployVersion} onResult={setCanaryResult} />}
      {tab === 'accept'     && <AcceptTab canaryResult={canaryResult} diagnosisReport={diagnosis?.reportText || ''} onAdopted={() => setAdopted(true)} />}
      {tab === 'evolution'  && <EvolutionTab namespace={customer?.namespace ?? null} />}
      <FloatingFeedback currentStep={tab} autoValues={{
        customer: customer?.name || '',
        customer_desc: customer?.description || '',
        customer_deploy: customer?.deployment_mode || '',
        customer_ns: customer?.namespace || '',
        customer_industry: customer?.industry || '',
        domain: domain?.id || '',
        diagnosis: diagnosis?.deepProblem?.slice(0, 80) || '',
        template: pocProfile || '',
        version: deployVersion || '',
        _workflow_stages: workflowStages,
        _agent_id: tab,
      }} />
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// ⑧ 运营监控 — 系统进化 (原 workbench FDE Dashboard)
// ═══════════════════════════════════════════════════════════
const EvolutionTab: React.FC<{ readonly namespace: string | null }> = ({ namespace }) => {
  const [data, setData] = useState<any>(null);
  useEffect(() => { fetch(API('/dashboard') + (namespace ? `?namespace=${namespace}` : '')).then(r => r.json()).then(setData); }, []);
  if (!data) return <div className="text-gray-500 text-sm p-4">加载中…</div>;
  const cards = [
    { label: '待处理决策', value: data.pending_decisions?.length ?? 0, color: 'text-yellow-400' },
    { label: '信号告警',   value: data.signal_alerts?.length ?? 0,     color: 'text-red-400' },
    { label: '追踪异常',   value: data.trace_anomalies?.length ?? 0,   color: 'text-orange-400' },
    { label: '训练状态',   value: data.training?.ready_to_trigger ? '就绪' : '待命中', color: 'text-blue-400' },
  ];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-3">
        {cards.map(c => (
          <Card key={c.label}><CardContent className="p-3 text-center">
            <div className={`text-xl font-bold ${c.color}`}>{c.value}</div>
            <div className="text-xs text-gray-500 mt-1">{c.label}</div>
          </CardContent></Card>
        ))}
      </div>
      {data.timeline?.length > 0 && (
        <Card><CardHeader><span className="text-sm font-medium">最近时间线</span></CardHeader>
          <CardContent className="text-xs space-y-1 max-h-48 overflow-y-auto">
            {data.timeline.slice(0, 10).map((e: any, i: number) => (
              <div key={i} className="flex justify-between py-1 border-b border-gray-800/50">
                <span className="text-gray-300">{e.spec_id}</span>
                <span className="text-gray-500">{e.event} {e.version}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// ⑤ 快速构建 — 部署管理
// ═══════════════════════════════════════════════════════════
const DeployTab: React.FC<{ readonly profile: string | null; readonly onDeployed: (taskId: string) => void }> = ({ profile, onDeployed }) => {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const poll = useCallback(async (id: string) => {
    const r = await fetch(API(`/package/${id}`));
    const s = await r.json();
    setStatus(s);
    if (s.status === 'running') setTimeout(() => poll(id), 2000);
  }, []);

  const startPackage = async () => {
    setLoading(true);
    setStatus(null);
    try {
      const r = await fetch(API('/package'), { method: 'POST' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const { task_id } = await r.json();
      setTaskId(task_id);
      onDeployed(task_id);
      poll(task_id);
    } catch (e: any) {
      setStatus({ status: 'error', progress: 0, detail: `启动失败: ${e.message || '未知错误'}`, log: [{ icon: 'error', msg: '无法连接到打包服务，请重试' }] });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><span className="text-sm font-medium">离线部署包</span></CardHeader>
        <CardContent className="space-y-3">
          <Button variant="default" size="sm" onClick={startPackage} loading={loading}>
            <Package className="w-3.5 h-3.5 mr-1" />打包离线部署包
          </Button>
          {status && (
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <div className="bg-gray-700 rounded-full h-2 flex-1">
                  <div className={`h-2 rounded-full ${status.status === 'error' ? 'bg-red-500' : 'bg-blue-500'}`} style={{ width: `${status.progress || 0}%` }} />
                </div>
                <span className="text-gray-400 text-xs">{status.progress || 0}%</span>
              </div>
              <p className={`text-xs ${status.status === 'error' ? 'text-red-400' : 'text-gray-400'}`}>{status.detail}</p>
              {status.log && status.log.length > 0 && (
                <div className="space-y-0.5 mt-1">
                  {status.log.map((entry: any, i: number) => {
                    const icons: Record<string, { icon: string; color: string }> = { check: { icon: '✓', color: 'text-green-400' }, warn: { icon: '⚠', color: 'text-yellow-400' }, error: { icon: '✗', color: 'text-red-400' }, skip: { icon: '—', color: 'text-gray-500' }, info: { icon: 'ℹ', color: 'text-blue-400' } };
                    const ic = icons[entry.icon] || icons.info;
                    return (<div key={i} className={`text-[11px] ${ic.color}`}><span className="w-4 inline-block">{ic.icon}</span> {entry.msg}</div>);
                  })}
                </div>
              )}
              {status.download_url && (
                <a href={`/api/core/fde/package/${taskId}/download`} className="inline-flex items-center gap-1 text-blue-400 text-xs hover:underline">
                  <Download className="w-3 h-3" />下载 ({status.size_display || `${status.size_mb || 0} MB`})
                </a>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};
// ═══════════════════════════════════════════════════════════
// ③ 问题重构 — 客户诊断
// ═══════════════════════════════════════════════════════════
const AssessTab: React.FC<{ readonly domain: string | null; readonly customerDesc: string; readonly customerName: string; readonly customerIndustry: string; readonly onReport: (diagnosis: DiagnosisInfo) => void }> = ({ domain, customerDesc, customerName, customerIndustry, onReport }) => {
  const [form, setForm] = useState<Record<string, string>>({});
  const [report, setReport] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (domain) setForm(prev => ({ ...prev, domain }));
    if (customerDesc) setForm(prev => ({ ...prev, current_flow: customerDesc }));
    if (customerName) setForm(prev => ({ ...prev, company_name: customerName }));
    if (customerIndustry) setForm(prev => ({ ...prev, industry: customerIndustry }));
  }, [domain, customerDesc, customerName, customerIndustry]);
  const [manual, setManual] = useState<any>(null);
  const [manualLoading, setManualLoading] = useState(false);
  const [reportExpanded, setReportExpanded] = useState(false);
  const [diagnosisSessionId, setDiagnosisSessionId] = useState('');
  const [pendingFeedback, setPendingFeedback] = useState('');
  const [updating, setUpdating] = useState(false);
  const [templates, setTemplates] = useState<Array<{
    name: string; form: Record<string, string>; report: string;
  }>>([]);
  const [showTemplates, setShowTemplates] = useState(false);
  // ── Clarification dialog state ──
  const dialogLockRef = useRef(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogTurn, setDialogTurn] = useState(1);
  const [dialogContext, setDialogContext] = useState<Record<string, string>>({});
  const [dialogHistory, setDialogHistory] = useState<Array<{role: string; content: string}>>([]);
  const [dialogOptions, setDialogOptions] = useState<string[]>([]);
  const [dialogLoading, setDialogLoading] = useState(false);
  const [dialogInput, setDialogInput] = useState('');
  const [dialogComposing, setDialogComposing] = useState(false);
  const [dialogSessionId, setDialogSessionId] = useState('');

  useEffect(() => {
    try {
      const saved = localStorage.getItem('fde_templates');
      if (saved) setTemplates(JSON.parse(saved));
    } catch {}
  }, []);

  const fields = [
    { key: 'company_name', label: '企业名称 (选填)', placeholder: '例如：XX科技有限公司', desc: '客户企业的完整注册名称' },
    { key: 'industry', label: '行业', type: 'select', desc: '选择客户所属行业，不在清单则选「其他」并在下方填写', required: true,
      options: ['政务', '金融', '制造', '医疗', '能源', '教育', '交通', '零售', '科技', '其他'] },
    { key: 'custom_industry', label: '自定义行业 (选填)', placeholder: '例如：新能源、物流', desc: '仅当行业选了「其他」或需更细分时填写' },
    { key: 'team_size', label: '团队规模 (选填)', placeholder: '例如：50', desc: '客户企业中与 AI 落地相关的技术/业务团队人数，不填则默认中等规模' },
    { key: 'pain_points', label: '痛点', type: 'textarea', placeholder: '每行输入一个痛点，例如：\n客服效率低，客户等待时间过长，影响满意度\n数据孤岛严重，各部门系统不互通\n合规成本高', desc: '客户核心业务痛点，每行一个；最关键的放前面', required: true },
    { key: 'existing_tech_stack', label: '现有技术栈 (选填)', placeholder: '例如：Python, PostgreSQL, Kubernetes, Kafka (逗号分隔)', desc: '客户已有的技术基础；不填则按行业典型方案推荐' },
    { key: 'internal_data_sources', label: '内部数据源 (选填)', placeholder: '例如：Oracle（投标人信息表）, 文件服务器（标书PDF）(逗号分隔)', desc: '客户内部已有的数据存储系统' },
    { key: 'external_data_sources', label: '外部可接入数据源 (选填)', placeholder: '例如：公共资源交易平台API, 企业信用公示系统 (逗号分隔)', desc: '可通过接口或爬虫获取的外部数据' },
    { key: 'compliance_requirements', label: '合规要求 (选填)', type: 'checkboxes', desc: '客户需满足的法规；不填则列出该行业默认合规清单',
      options: ['等保二级', '等保三级', 'GDPR', '数据不出境', '信创适配'] },
    { key: 'budget_range', label: '预算范围 (选填)', placeholder: '例如：50-100万/年 或 一期200万', desc: 'AI 落地预期预算；不填则用行业均值估算' },
    { key: 'poc_timeline', label: 'POC 期望时间 (选填)', placeholder: '例如：3个月', desc: '客户期望的 POC 完成时间' },
    { key: 'production_timeline', label: '正式上线期望 (选填)', placeholder: '例如：6个月', desc: '客户期望的正式上线时间' },
  ];

  const generateSpecId = (industry: string): string => {
    const code = industry === '其他' ? 'GEN' : industry.slice(0, 2);
    const date = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    const suffix = Date.now().toString(36).slice(-3).toUpperCase();
    return `FDE-${code}-${date}-${suffix}`;
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target?.result as string);
        const mapped: Record<string, string> = {};
        if (typeof data.company_name === 'string') mapped.company_name = data.company_name;
        if (typeof data.industry === 'string') mapped.industry = data.industry;
        if (typeof data.custom_industry === 'string') mapped.custom_industry = data.custom_industry;
        if (data.team_size !== undefined && data.team_size !== null) mapped.team_size = String(data.team_size);
        if (Array.isArray(data.pain_points)) mapped.pain_points = data.pain_points.join('\n');
        if (Array.isArray(data.existing_tech_stack)) mapped.existing_tech_stack = data.existing_tech_stack.join(', ');
        // v2 fields: internal/external data sources (preserve as-is for form split)
        if (Array.isArray(data.internal_data_sources)) mapped.internal_data_sources = data.internal_data_sources.join(', ');
        if (Array.isArray(data.external_data_sources)) mapped.external_data_sources = data.external_data_sources.join(', ');
        // v1 fallback: legacy data_sources
        if (Array.isArray(data.data_sources) && !mapped.internal_data_sources && !mapped.external_data_sources) {
          mapped.internal_data_sources = data.data_sources.join(', ');
        }
        if (Array.isArray(data.compliance_requirements)) mapped.compliance_requirements = data.compliance_requirements.join(', ');
        if (typeof data.budget_range === 'string') mapped.budget_range = data.budget_range;
        // v2 fields: split timeline
        if (typeof data.poc_timeline === 'string' && data.poc_timeline.trim() && !data.poc_timeline.startsWith('示例')) mapped.poc_timeline = data.poc_timeline;
        if (typeof data.production_timeline === 'string' && data.production_timeline.trim() && !data.production_timeline.startsWith('示例')) mapped.production_timeline = data.production_timeline;
        // v1 fallback: legacy timeline string
        if (typeof data.timeline === 'string' && !mapped.poc_timeline && !mapped.production_timeline) mapped.poc_timeline = data.timeline;
        setForm(mapped);
      } catch {}
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const [editingReport, setEditingReport] = useState(false);

  // ── Clarification dialog: initiate or continue ──
  const dialogCall = async (answer?: string, turn?: number, sessionId?: string) => {
    setDialogLoading(true);
    try {
      const body = JSON.stringify({
        turn: Number(turn ?? dialogTurn),
        answer: answer || '',
        session_id: sessionId || dialogSessionId || '',
        industry: form.industry || dialogContext.industry || '',
        company_name: form.company_name || dialogContext.company_name || '',
        pain_points: form.pain_points || dialogContext.pain_points || '',
        team_size: form.team_size || dialogContext.team_size || '',
        budget: form.budget_range || dialogContext.budget || '',
        existing_tech_stack: form.existing_tech_stack || dialogContext.existing_tech_stack || '',
        internal_data_sources: form.internal_data_sources || dialogContext.internal_data_sources || '',
        external_data_sources: form.external_data_sources || dialogContext.external_data_sources || '',
        compliance_requirements: form.compliance_requirements || dialogContext.compliance_requirements || '',
        poc_timeline: form.poc_timeline || dialogContext.poc_timeline || '',
        production_timeline: form.production_timeline || dialogContext.production_timeline || '',
      });
      const r = await fetch('/api/core/fde/assess/dialog', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body,
      });
      const data = await r.json();
      setDialogContext(data.context || {});
      setDialogOptions(data.options || []);
      setDialogTurn(data.turn || 2);
      setDialogHistory(prev => [
        ...prev,
        { role: 'assistant', content: data.question || '' },
      ]);

      // ── Handle "finished" flag ──
      if (data.finished) {
        const isFollowUp = !!diagnosisSessionId;

        if (isFollowUp) {
          // ── §8 follow-up: collect Q&A into pendingFeedback ──
          const qaPairs: string[] = [];
          for (let i = 1; i < dialogHistory.length - 1; i++) {
            const msg = dialogHistory[i];
            if (msg.role === 'assistant' && msg.content !== dialogHistory[0]?.content) {
              const nextMsg = dialogHistory[i + 1];
              if (nextMsg?.role === 'user') {
                qaPairs.push(`Q: ${msg.content}\nA: ${nextMsg.content}`);
              }
            }
          }
          const qaText = qaPairs.join('\n\n');
          setPendingFeedback((pf: string) => {
            const parts = [pf.trim(), '--- 澄清对话记录 ---', qaText].filter(Boolean);
            return parts.join('\n\n');
          });
          setTimeout(() => {
            closeDialog();
          }, 200);
        } else {
          setTimeout(() => {
            closeDialog();
            // Build extraInput from dialog context for immediate submit
            const ctx = data.context || {};
            const extra: Record<string, any> = {};
            for (const [k, v] of Object.entries(ctx)) {
              if (v) {
                // Map dialog context keys to form keys
                if (k === 'budget') extra.budget_range = v;
                else extra[k] = v;
              }
            }
            // Write back to form for UI display
            setForm(prev => ({ ...prev, ...extra,
              ...(ctx.company_name ? { company_name: ctx.company_name } : {}),
              ...(ctx.pain_points ? { pain_points: ctx.pain_points } : {}),
              ...(ctx.team_size ? { team_size: ctx.team_size } : {}),
              ...(ctx.budget ? { budget_range: ctx.budget } : {}),
              ...(ctx.existing_tech_stack ? { existing_tech_stack: ctx.existing_tech_stack } : {}),
              ...(ctx.internal_data_sources ? { internal_data_sources: ctx.internal_data_sources } : {}),
              ...(ctx.external_data_sources ? { external_data_sources: ctx.external_data_sources } : {}),
              ...(ctx.compliance_requirements ? { compliance_requirements: ctx.compliance_requirements } : {}),
              ...(ctx.poc_timeline ? { poc_timeline: ctx.poc_timeline } : {}),
              ...(ctx.production_timeline ? { production_timeline: ctx.production_timeline } : {}),
            }));
            submit(extra);  // ← pass directly, bypass setForm async delay
          }, 500);
        }
      }
    } catch (e: any) {
      const detail = e?.message || String(e || '');
      setDialogHistory(prev => [...prev, { role: 'assistant', content: `抱歉，连接失败${detail ? ` (${detail.slice(0, 80)})` : ''}。请确认后端服务已启动。` }]);
    }
    setDialogLoading(false);
  };

  const closeDialog = () => {
    setDialogOpen(false);
    dialogLockRef.current = false;
  };

  const openDialog = (sessionId?: string) => {
    if (dialogLockRef.current) return;
    dialogLockRef.current = true;
    setDialogOpen(true);
    setDialogTurn(1);
    setDialogHistory([{ role: 'assistant', content: '你好！我是 AI 诊断助手。让我先了解一下你的情况……' }]);
    setDialogContext({});
    setDialogSessionId(sessionId || '');
    dialogCall(undefined, 1, sessionId);
  };

  const submit = async (extraInput?: Record<string, any>) => {
    setLoading(true);
    try {
      const input = {
        company_name: form.company_name || '',
        industry: form.industry || '',
        custom_industry: form.custom_industry || '',
        team_size: parseInt(form.team_size) || 0,
        pain_points: (form.pain_points || '').split('\n').map(s => s.trim()).filter(Boolean),
        existing_tech_stack: (form.existing_tech_stack || '').split(',').map(s => s.trim()).filter(Boolean),
        internal_data_sources: (form.internal_data_sources || '').split(',').map(s => s.trim()).filter(Boolean),
        external_data_sources: (form.external_data_sources || '').split(',').map(s => s.trim()).filter(Boolean),
        compliance_requirements: (form.compliance_requirements || '').split(',').map(s => s.trim()).filter(Boolean),
        budget_range: form.budget_range || '',
        poc_timeline: form.poc_timeline || '',
        production_timeline: form.production_timeline || '',
        ...(extraInput || {}),
      };
      const r = await fetch('/api/core/skills/field-assessment/execute', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input, mode: 'inline' }),
      });
      const data = await r.json();
      if (!data.ok) {
        const errMsg = data.error_message || data.error?.message || '未知错误';
        setReport('__ERROR__:' + errMsg);
      } else {
        const rawOutput = data.output || data.report;
        const outputText = typeof rawOutput === 'string' ? rawOutput
          : (rawOutput && typeof rawOutput === 'object' ? (rawOutput.text || rawOutput.output || JSON.stringify(rawOutput, null, 2)) : JSON.stringify(data, null, 2));
        setReport(outputText);
        // Capture session_id for §8 follow-up
        if (data.metadata?.session_id) {
          setDiagnosisSessionId(data.metadata.session_id);
        }
        // Fire pipeline event: report ready
        const deepMatch = outputText.match(/深层问题[：:]\s*(.+)/);
        const domainMatch = outputText.match(/推荐本体域[：:]\s*(\S+)/);
        onReport({
          deepProblem: deepMatch?.[1]?.trim() || outputText.slice(0, 120),
          recommendedDomain: domainMatch?.[1]?.trim() || form.domain || '',
          reportText: outputText,
        });
      }

      setLoading(false);
    } catch (e: any) {
      setReport('__ERROR__:' + (e?.message || '请求失败'));
      setLoading(false);
    }
  };

  const generateManual = async () => {
    if (!report || report.startsWith('__ERROR__:')) return;
    setManualLoading(true);
    try {
      const projectLabel = form.company_name || (form.industry ? form.industry + 'AI落地项目' : 'AI落地项目');
      const parts = [projectLabel];
      if (form.industry) parts.push(form.industry + '行业AI落地');
      if (form.pain_points) parts.push('痛点：' + form.pain_points);
      if (form.existing_tech_stack) parts.push('现有技术栈：' + form.existing_tech_stack);
      if (form.internal_data_sources || form.external_data_sources) {
        const parts_s = [];
        if (form.internal_data_sources) parts_s.push('内部数据源：' + form.internal_data_sources);
        if (form.external_data_sources) parts_s.push('外部数据源：' + form.external_data_sources);
        parts.push(parts_s.join('，'));
      }
      if (form.compliance_requirements) parts.push('合规要求：' + form.compliance_requirements);
      if (form.budget_range) parts.push('预算：' + form.budget_range);
      if (form.poc_timeline || form.production_timeline) {
        const parts_t = [];
        if (form.poc_timeline) parts_t.push('POC：' + form.poc_timeline);
        if (form.production_timeline) parts_t.push('上线：' + form.production_timeline);
        parts.push(parts_t.join('，'));
      }
      if (form.team_size) parts.push('团队：' + form.team_size + '人');
      const reqStr = parts.join('，');
      const diagSummary = report.replace(/```[\s\S]*?```/g, '').replace(/`{1,2}([^`]+)`{1,2}/g, '$1').trim();
      const specId = generateSpecId(form.industry || '通用');
      const mr = await fetch(API(`/manual/generate?requirements=${encodeURIComponent(reqStr)}&industry=${encodeURIComponent(form.industry || '通用')}&agent_guide=1&workflow_guide=1&spec_id=${encodeURIComponent(specId)}&diagnosis_report=${encodeURIComponent(diagSummary)}`));
      const md = await mr.json();
      setManual(md);
    } catch {}
    setManualLoading(false);
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><span className="text-sm font-medium">新客户AI落地诊断</span></CardHeader>
        <CardContent className="space-y-2">
          <p className="text-xs text-blue-300 bg-blue-900/30 border border-blue-800 rounded px-3 py-2">
            点击「<b>提交诊断</b>」后 AI 将自动生成结构化分析报告（含 Top 3 落地机会、部署路线图、风险清单）。
            标注 <span className="text-red-400 font-bold">*</span> 的为必填项（FDE 在现场一定能获取），其余选填项不填则 AI 按行业典型默认值推断。
          </p>
          <div className="grid grid-cols-2 gap-2">
            {fields.map(f => {
              const isRequired = (f as any).required;
              const fieldType = (f as any).type as string || 'input';
              return (
                <div key={f.key} className={fieldType === 'textarea' ? 'col-span-2' : ''}>
                  <label className="text-xs text-gray-400">
                    {f.label}
                    {isRequired && <span className="text-red-400 ml-0.5 font-bold">*</span>}
                  </label>
                  {fieldType === 'select' ? (
                    <select
                      className={`w-full bg-gray-800 border rounded px-2 py-1 text-sm text-gray-200 ${isRequired && !form[f.key] ? 'border-red-700' : 'border-gray-700'}`}
                      value={form[f.key] || ''}
                      onChange={e => setForm({...form, [f.key]: e.target.value})}
                    >
                      <option value="">-- 请选择 --</option>
                      {((f as any).options as string[]).map(o => (
                        <option key={o} value={o}>{o}</option>
                      ))}
                    </select>
                  ) : fieldType === 'checkboxes' ? (
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {((f as any).options as string[]).map(o => {
                        const selected = (form[f.key] || '').split(',').map((s: string) => s.trim()).filter(Boolean);
                        const checked = selected.includes(o);
                        return (
                          <label key={o} className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs cursor-pointer border ${checked ? 'bg-blue-500/15 text-blue-300 border-blue-500/25' : 'bg-dark-hover text-gray-400 border-dark-border'}`}>
                            <input type="checkbox" className="w-3 h-3" checked={checked}
                              onChange={e => {
                                const next = e.target.checked
                                  ? [...selected, o]
                                  : selected.filter((x: string) => x !== o);
                                setForm({...form, [f.key]: next.join(', ')});
                              }}
                            />
                            {o}
                          </label>
                        );
                      })}
                    </div>
                  ) : fieldType === 'textarea' ? (
                    <textarea
                      className={`w-full bg-gray-800 border rounded px-2 py-1.5 text-sm text-gray-200 resize-y ${isRequired && !form[f.key] ? 'border-red-700' : 'border-gray-700'}`}
                      placeholder={(f as any).placeholder || ''}
                      rows={4}
                      value={form[f.key] || ''}
                      onChange={e => setForm({...form, [f.key]: e.target.value})}
                    />
                  ) : (
                    <input
                      className={`w-full bg-gray-800 border rounded px-2 py-1 text-sm text-gray-200 ${isRequired && !form[f.key] ? 'border-red-700' : 'border-gray-700'}`}
                      placeholder={(f as any).placeholder || ''}
                      value={form[f.key] || ''}
                      onChange={e => setForm({...form, [f.key]: e.target.value})}
                    />
                  )}
                  <p className="text-xs text-gray-500 mt-0.5">{f.desc}</p>
                </div>
              );
            })}
          </div>
           <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => openDialog(diagnosisSessionId)}>
               ⚡ 智能澄清
            </Button>
            <Button variant="default" size="sm" onClick={() => submit()} loading={loading}>
              <FileText className="w-3.5 h-3.5 mr-1" />提交诊断
            </Button>
            <a
              href="/customer-diagnosis-template.json"
              download="客户诊断模板.json"
              className="inline-flex items-center gap-1 px-3 py-1.5 text-sm bg-dark-hover border border-dark-border rounded-lg text-gray-400 hover:text-white transition-colors no-underline"
            >
              📋 下载模板
            </a>
            <button
              className="inline-flex items-center gap-1 px-3 py-1.5 text-sm bg-dark-hover border border-dark-border rounded-lg text-gray-400 hover:text-white transition-colors"
              onClick={() => setShowTemplates(!showTemplates)}
            >
              📂 加载 {templates.length > 0 && `(${templates.length})`}
            </button>
          </div>
          {showTemplates && (
            <div className="mt-3 border-t border-dark-border pt-3">
              <div className="flex gap-2 mb-2">
                <label className="inline-flex items-center gap-1 px-2 py-1 text-xs bg-blue-500/10 border border-blue-500/25 rounded text-blue-300 cursor-pointer hover:bg-blue-500/20">
                  📁 从文件
                  <input type="file" accept=".json" className="hidden" onChange={handleFileUpload} />
                </label>
                <span className="text-xs text-gray-500 self-center">或从历史模板加载：</span>
              </div>
              {templates.length > 0 ? (
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {templates.map((t, i) => (
                    <div key={i} className="flex items-center justify-between text-xs p-1.5 rounded hover:bg-dark-hover">
                      <button
                        className="text-blue-400 hover:underline text-left flex-1"
                        onClick={() => {
                          setForm(t.form);
                          setReport(t.report);
                          setShowTemplates(false);
                        }}
                      >
                        📋 {t.name}
                      </button>
                      <button
                        className="text-gray-500 hover:text-red-400 ml-2"
                        onClick={() => {
                          const next = templates.filter((_, j) => j !== i);
                          localStorage.setItem('fde_templates', JSON.stringify(next));
                          setTemplates(next);
                        }}
                      >
                        🗑️
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-gray-500">暂无模板。诊断成功后点击「💾 保存为模板」即可创建。</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>
      {report && (report.startsWith('__ERROR__:') ? (
        <Card className="border-red-800 bg-red-900/10">
          <CardHeader>
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-400" />
              <span className="text-sm font-medium text-red-300">诊断失败</span>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-red-400">{report.replace('__ERROR__:', '')}</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card className="border-green-800 bg-green-900/10">
            <CardContent className="py-2">
              <div className="flex items-center gap-2 text-xs">
                <CheckCircle className="w-3.5 h-3.5 text-green-400" />
                <span className="text-green-300">诊断完成</span>
                <span className="text-gray-500">|</span>
                <span className="text-gray-400">报告 {report.length} 字</span>
                {manual && <><span className="text-gray-500">|</span><span className="text-gray-400">交付手册已自动生成</span></>}
          </div>
        </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">诊断报告</span>
                <div className="flex items-center gap-2">
                  <a
                    href={`data:text/markdown;charset=utf-8,${encodeURIComponent(report)}`}
                    download="诊断报告.md"
                    className="text-xs text-blue-400 hover:underline"
                  >
                    <Download className="w-3 h-3 inline mr-0.5" />下载
                  </a>
                  <button className="text-xs text-gray-500 hover:text-gray-300" onClick={() => setEditingReport(!editingReport)}>
                    {editingReport ? '预览' : '✏️ 编辑'}
                  </button>
                  <button className="text-xs text-gray-500 hover:text-gray-300" onClick={() => setReportExpanded(!reportExpanded)}>
                    {reportExpanded ? '收起' : '展开'} ({report.length} 字)
                  </button>
                  <button
                    className="text-xs text-green-400 hover:text-green-300"
                    onClick={() => {
                      const name = prompt('模板名称：', `${form.industry || '通用'}-${new Date().toISOString().slice(0, 10)}`);
                      if (!name) return;
                      const saved = [...templates, { name, form: { ...form }, report }];
                      localStorage.setItem('fde_templates', JSON.stringify(saved));
                      setTemplates(saved);
                    }}
                  >
                    💾 保存为模板
                  </button>
                  <Button variant="outline" size="sm" onClick={generateManual} loading={manualLoading}>
                    📋 生成交付手册
                  </Button>
                  {diagnosisSessionId && (
                    <Button variant="outline" size="sm" onClick={() => openDialog(diagnosisSessionId)}>
                      ⚡ 继续澄清
                    </Button>
                  )}
                </div>
              </div>
            </CardHeader>
            {reportExpanded && (
              <CardContent>
                {editingReport ? (
                  <textarea
                    className="w-full h-96 bg-gray-800 border border-gray-700 rounded p-2 text-xs text-gray-200 font-mono resize-y"
                    value={report}
                    onChange={e => setReport(e.target.value)}
                  />
                ) : (
                  <pre className="text-xs text-gray-300 whitespace-pre-wrap max-h-96 overflow-y-auto">{report}</pre>
                )}
              </CardContent>
            )}
          </Card>
          {report.includes('待确认问题清单') && (
            <Card className="border-yellow-800 bg-yellow-900/10">
              <CardHeader>
                <span className="text-sm font-medium text-yellow-300">📝 待确认问题反馈</span>
                <p className="text-xs text-gray-500 mt-1">
                  填写客户对上述待确认问题的答复，点击「更新诊断」后 AI 将基于更完整的信息重新生成报告。
                </p>
              </CardHeader>
              <CardContent className="space-y-2">
                <textarea
                  className="w-full h-28 bg-gray-800 border border-gray-600 rounded p-2 text-sm text-gray-200 resize-y"
                  placeholder={`例如：\n1. 数据可获取性：已有近5年招投标数据，数字化程度约60%…\n2. 算力环境：暂无GPU服务器，可采购华为昇腾…\n3. …`}
                  value={pendingFeedback}
                  onChange={e => setPendingFeedback(e.target.value)}
                />
                <Button variant="default" size="sm" loading={updating} onClick={async () => {
                  setUpdating(true);
                  await submit({ pending_feedback: pendingFeedback.trim() });
                  setPendingFeedback('');
                  setUpdating(false);
                }}>
                  🔄 更新诊断
                </Button>
              </CardContent>
            </Card>
          )}
          </>
        ))}
      {manual && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">📋 交付手册草稿</span>
              <span className="text-xs text-yellow-400 bg-yellow-400/10 px-2 py-0.5 rounded">自动生成</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-xs text-blue-300 bg-blue-900/30 border border-blue-800 rounded px-3 py-2">
              已基于诊断信息自动生成交付手册草稿。可在此预览和下载，也可前往<span className="text-blue-400 font-medium"> Tab 8 验证验收</span>随时更新为正式版。
            </p>
            <div className="flex items-center gap-2">
              <a href={`data:text/markdown;charset=utf-8,${encodeURIComponent(manual.manual || '')}`} className="text-xs text-blue-400 hover:underline" download={`${manual.project_name || 'delivery-manual'}.md`}><Download className="w-3 h-3 inline mr-1" />下载交付手册 (.md)</a>
              <button className="text-xs text-gray-500 hover:text-gray-300" onClick={() => setManual((prev: any) => ({ ...prev, _expanded: !prev?._expanded }))}>{manual?._expanded ? '收起' : '展开'}</button>
            </div>
            <pre className="text-xs text-gray-300 bg-gray-800 p-2 rounded max-h-48 overflow-y-auto">{manual._expanded ? (manual.manual || '') : (manual.manual || '').slice(0, 1500)}</pre>
          </CardContent>
        </Card>
      )}
      {/* ── 智能澄清 Dialog ── */}
      {dialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => closeDialog()}>
          <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md mx-4 shadow-2xl flex flex-col" style={{height: '480px'}} onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0">
              <div className="flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-blue-500/20 flex items-center justify-center text-xs">🤖</span>
                <span className="text-sm font-medium text-gray-200">AI 诊断助手</span>
              </div>
              <button onClick={() => closeDialog()} className="text-gray-500 hover:text-gray-300 text-lg">&times;</button>
            </div>
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
              {dialogHistory.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] px-3 py-2 rounded-lg text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-blue-600/30 text-blue-100 rounded-br-sm'
                      : 'bg-gray-800 text-gray-200 rounded-bl-sm'
                  }`}>
                    {msg.content}
                  </div>
                </div>
              ))}
              {dialogLoading && (
                <div className="flex justify-start">
                  <div className="bg-gray-800 text-gray-400 text-sm px-3 py-2 rounded-lg rounded-bl-sm">
                    <span className="inline-flex gap-1">
                      <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" style={{animationDelay: '0ms'}}></span>
                      <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" style={{animationDelay: '150ms'}}></span>
                      <span className="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce" style={{animationDelay: '300ms'}}></span>
                    </span>
                  </div>
                </div>
              )}
            </div>
            <div className="px-4 py-3 border-t border-gray-700 shrink-0 space-y-2">
              {dialogOptions.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {dialogOptions.map(opt => (
                    <button key={opt} className={`px-3 py-1.5 text-sm rounded-full bg-blue-500/15 text-blue-300 border border-blue-500/25 transition-colors ${dialogLoading ? 'opacity-50 cursor-not-allowed' : 'hover:bg-blue-500/25'}`}
                      disabled={dialogLoading}
                      onClick={() => {
                        if (dialogLoading) return;
                        setDialogHistory(prev => [...prev, { role: 'user', content: opt }]);
                        dialogCall(opt);
                      }}>{opt}</button>
                  ))}
                </div>
              )}
              <div className="flex gap-2">
                <input className="flex-1 h-9 px-3 bg-gray-800 border border-gray-600 rounded-lg text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500/50"
                  placeholder="输入你的回答..."
                  value={dialogInput} onChange={e => setDialogInput(e.target.value)}
                  onCompositionStart={() => setDialogComposing(true)}
                  onCompositionEnd={() => setDialogComposing(false)}
                  onKeyDown={e => { if (e.key === 'Enter' && !dialogComposing && dialogInput.trim()) { e.preventDefault(); const msg = dialogInput.trim(); setDialogInput(''); setDialogHistory(prev => [...prev, { role: 'user', content: msg }]); dialogCall(msg); }}} />
                <Button variant="ghost" size="sm" className="px-3" onClick={() => { if (dialogInput.trim()) { const msg = dialogInput.trim(); setDialogInput(''); setDialogHistory(prev => [...prev, { role: 'user', content: msg }]); dialogCall(msg); }}} disabled={!dialogInput.trim() || dialogLoading}>
                  <Send className="w-4 h-4" />
                </Button>
              </div>
              <button className="w-full text-xs text-gray-500 hover:text-gray-400 py-1" onClick={() => closeDialog()}>结束对话</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// ① 业务认知 — 客户列表 (with create modal + expandable cards)
// ═══════════════════════════════════════════════════════════
const CustomersTab: React.FC<{ readonly onSelect: (c: CustomerInfo) => void; readonly diagnosis: Readonly<DiagnosisInfo> | null }> = ({ onSelect, diagnosis }) => {
  const [customers, setCustomers] = useState<any[]>([]);
  const [expanded, setExpanded] = useState<string[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<Record<string, string>>({});
  const [createLoading, setCreateLoading] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [editForm, setEditForm] = useState<Record<string, string>>({});
  const [editId, setEditId] = useState('');
  const [editLoading, setEditLoading] = useState(false);

  const load = () => fetch(API('/customers')).then(r => r.json()).then(d => setCustomers(d.customers || []));
  useEffect(() => { load(); }, []);

  const switchProfile = async (name: string) => {
    await fetch(API(`/switch-profile/${name}`), { method: 'POST' });
    toast?.success?.('已切换至 ' + name) || console.log('已切换至', name);
    load();
  };

  const deleteProfile = async (namespace: string) => {
    await fetch(API(`/customers/${namespace}`), { method: 'DELETE' });
    setExpanded(prev => prev.filter(x => x !== namespace));
    load();
  };

  const startEdit = (c: any) => {
    const id = displayId(c);
    setEditId(id);
    setEditForm({ name: c.name || '', namespace: c.namespace || '', description: c.description || '', deployment_mode: c.deployment_mode || 'online' });
    setShowEdit(true);
  };

  const handleEdit = async () => {
    if (!editForm.name?.trim()) return;
    setEditLoading(true);
    try {
      await fetch(API(`/customers/${editId}`), {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editForm),
      });
      setShowEdit(false);
      load();
    } catch {}
    setEditLoading(false);
  };

  const toggleExpand = async (id: string) => {
    setExpanded(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const handleCreate = async () => {
    if (!createForm.name?.trim()) return;
    setCreateLoading(true);
    try {
      await fetch(API('/customers'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(createForm),
      });
      setShowCreate(false);
      setCreateForm({});
      load();
    } catch {}
    setCreateLoading(false);
  };

  // Deduplicate by namespace (prefer namespace as key)
  const displayId = (c: any) => c.namespace || c.name;
  const labelText = (c: any) => c.namespace && c.namespace !== c.name ? `${c.name} @ ${c.namespace}` : c.name;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500">共 {customers.length} 个客户 Profile</span>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={load}><RefreshCw className="w-3 h-3" /></Button>
          <Button variant="default" size="sm" onClick={() => { setShowCreate(true); setCreateForm({}); }}>
            <Plus className="w-3 h-3 mr-1" />新建
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {customers.map(c => {
          const id = displayId(c);
          const isExpanded = expanded.includes(id);
          return (
            <Card key={id} className="border-gray-700/50 hover:border-gray-600 transition-colors">
              <div className="p-3 cursor-pointer" onClick={() => { toggleExpand(id); onSelect({ name: c.name, namespace: c.namespace, industry: c.health?.industry, description: c.description, deployment_mode: c.deployment_mode }); }}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    {isExpanded ? <ChevronDown className="w-3 h-3 text-gray-500" /> : <ChevronRight className="w-3 h-3 text-gray-500" />}
                    <span className="text-sm font-medium text-gray-200">{labelText(c)}</span>
                    {c.default && <span className="text-[10px] bg-blue-500/20 text-blue-300 px-1 rounded">默认</span>}
                  </div>
                  <button onClick={e => { e.stopPropagation(); switchProfile(c.name); }}
                    className="text-[10px] text-gray-500 hover:text-blue-400 flex items-center gap-0.5"
                    title="切换至此 Profile">
                    <ArrowRightLeft className="w-3 h-3" />切换
                  </button>
                </div>
                <div className="text-[11px] text-gray-500 mt-0.5">
                  {c.description || c.namespace || ''}
                </div>
              </div>
              {isExpanded && (
                <div className="px-3 pb-3 border-t border-gray-700/50 space-y-2 pt-2">
                  <div className="text-xs text-gray-500">
                    {c.description || c.namespace || ''}
                  </div>
                  {diagnosis && (
                    <div className="text-xs p-2 rounded bg-blue-500/10 border border-blue-500/20">
                      <div className="text-blue-400 font-medium">最近诊断</div>
                      <div className="text-blue-300 mt-0.5">{diagnosis.deepProblem.slice(0, 100)}</div>
                      {diagnosis.recommendedDomain && <div className="text-blue-500 mt-0.5">推荐域：{diagnosis.recommendedDomain}</div>}
                    </div>
                  )}
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); switchProfile(c.name); }}>
                      <ArrowRightLeft className="w-3 h-3 mr-1" />切换至此
                    </Button>
                    <Button variant="ghost" size="sm" className="text-red-400 hover:text-red-300"
                      onClick={e => { e.stopPropagation(); if (confirm(`确认删除客户 "${labelText(c)}"?`)) deleteProfile(id); }}>
                      <Trash2 className="w-3 h-3 mr-1" />删除
                    </Button>
                    <Button variant="ghost" size="sm"
                      onClick={e => { e.stopPropagation(); startEdit(c); }}>
                      <Pencil className="w-3 h-3 mr-1" />编辑
                    </Button>
                  </div>
                </div>
              )}
            </Card>
          );
        })}
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh] bg-black/60">
          <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-sm mx-4 p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-200">新建客户 Profile</h3>
              <button onClick={() => setShowCreate(false)} className="text-gray-500 hover:text-gray-300"><X className="w-4 h-4" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-400">客户名称 *</label>
                <input className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
                  value={createForm.name || ''} onChange={e => setCreateForm({ ...createForm, name: e.target.value })}
                  placeholder="例如：某省政务云中心" />
              </div>
              <div>
                <label className="text-xs text-gray-400">命名空间</label>
                <input className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
                  value={createForm.namespace || ''} onChange={e => setCreateForm({ ...createForm, namespace: e.target.value })}
                  placeholder="默认根据名称生成" />
              </div>
              <div>
                <label className="text-xs text-gray-400">描述</label>
                <textarea className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 h-16 resize-none"
                  value={createForm.description || ''} onChange={e => setCreateForm({ ...createForm, description: e.target.value })}
                  placeholder="客户业务模式、行业、关键需求等" />
              </div>
              <div>
                <label className="text-xs text-gray-400">部署模式</label>
                <select className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
                  value={createForm.deployment_mode || 'online'}
                  onChange={e => setCreateForm({ ...createForm, deployment_mode: e.target.value })}>
                  <option value="online">online</option>
                  <option value="airgap">airgap（离线）</option>
                  <option value="hybrid">hybrid（混合）</option>
                </select>
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setShowCreate(false)} className="flex-1 px-3 py-1.5 text-sm rounded-lg border border-gray-700 text-gray-400 hover:text-white">取消</button>
              <button onClick={handleCreate} disabled={createLoading || !createForm.name?.trim()}
                className="flex-1 px-3 py-1.5 text-sm rounded-lg bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50">
                {createLoading ? '创建中…' : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showEdit && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-[10vh] bg-black/60">
          <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-sm mx-4 p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-200">编辑客户 Profile</h3>
              <button onClick={() => setShowEdit(false)} className="text-gray-500 hover:text-gray-300"><X className="w-4 h-4" /></button>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-400">客户名称 *</label>
                <input className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
                  value={editForm.name || ''} onChange={e => setEditForm({ ...editForm, name: e.target.value })} />
              </div>
              <div>
                <label className="text-xs text-gray-400">命名空间</label>
                <input className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
                  value={editForm.namespace || ''} onChange={e => setEditForm({ ...editForm, namespace: e.target.value })} />
              </div>
              <div>
                <label className="text-xs text-gray-400">描述</label>
                <textarea className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 h-16 resize-none"
                  value={editForm.description || ''} onChange={e => setEditForm({ ...editForm, description: e.target.value })} />
              </div>
              <div>
                <label className="text-xs text-gray-400">部署模式</label>
                <select className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200"
                  value={editForm.deployment_mode || 'online'}
                  onChange={e => setEditForm({ ...editForm, deployment_mode: e.target.value })}>
                  <option value="online">online</option>
                  <option value="airgap">airgap（离线）</option>
                  <option value="hybrid">hybrid（混合）</option>
                </select>
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setShowEdit(false)} className="flex-1 px-3 py-1.5 text-sm rounded-lg border border-gray-700 text-gray-400 hover:text-white">取消</button>
              <button onClick={handleEdit} disabled={editLoading || !editForm.name?.trim()}
                className="flex-1 px-3 py-1.5 text-sm rounded-lg bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50">
                {editLoading ? '保存中…' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════

// Tab 6: POC 工具箱
// ═══════════════════════════════════════════════════════════
const PocTab: React.FC<{ readonly domain: Readonly<DomainInfo> | null; readonly onProfileSet: (profileKey: string) => void }> = ({ domain, onProfileSet }) => {
  const [profile, setProfile] = useState('');
  const [injectResult, setInjectResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [templates, setTemplates] = useState<any[]>([]);

  useEffect(() => {
    fetch(API('/templates')).then(r => r.json()).then(d => setTemplates(d.templates || []));
  }, []);

  const loadTemplate = async (key: string) => {
    setLoading(true);
    try {
      const t = templates.find(tp => tp.key === key);
      await fetch(API(`/switch-profile/${t?.namespace || `poc-${key}`}`), { method: 'POST' });
      setProfile(key);
      onProfileSet?.(key);
    } catch {}
    setLoading(false);
  };

  const quickInject = async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/core/skills/poc_data_inject/execute', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_paths: [] }),
      });
      setInjectResult(await r.json());
    } catch {}
    setLoading(false);
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><span className="text-sm font-medium">加载行业模板</span></CardHeader>
        <CardContent>
          <div className="grid grid-cols-4 gap-2">
            {templates.map(t => (
              <button key={t.key}
                onClick={() => loadTemplate(t.key)}
                disabled={loading}
                className={`p-3 rounded-md border text-left text-xs transition-colors ${
                  profile === t.key ? 'border-blue-500 bg-blue-500/10' : 'border-gray-700 hover:border-gray-500'
                }`}>
                <div className="text-gray-200 font-medium">{t.key.replace('poc-', '')}</div>
                <div className="text-gray-500">{t.description?.slice(0, 40)}</div>
              </button>
            ))}
          </div>
          {profile && <p className="text-xs text-green-400 mt-2">✓ 当前 Profile: poc-{profile}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><span className="text-sm font-medium">注入客户数据</span></CardHeader>
        <CardContent className="space-y-2">
          <p className="text-xs text-gray-500">
            支持 PDF、CSV、Excel、TXT、Markdown — 拖入文件后自动解析注入 kb/poc 知识库
          </p>
          <Button variant="default" size="sm" onClick={quickInject} loading={loading}>
            <Send className="w-3.5 h-3.5 mr-1" />执行数据注入
          </Button>
          {injectResult && (
            <div className="text-xs space-y-1 mt-2">
              <p className="text-gray-300">
                状态: {injectResult.status} | 文件: {injectResult.total_files || 0} | 记录: {injectResult.records || 0}
              </p>
              {(injectResult.errors || []).length > 0 && (
                <div className="text-red-400">错误: {(injectResult.errors || []).slice(0, 3).join('; ')}</div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><span className="text-sm font-medium">POC 操作手册</span></CardHeader>
        <CardContent>
          <div className="text-xs text-gray-400 space-y-1">
            <p>1. 加载行业模板 → 系统自动配置 Agent</p>
            <p>2. 注入客户数据 (PDF/Excel/CSV/TXT) → kb/poc 可检索</p>
            <p>3. 打开 Agent 对话 → 问"我们的X数据如何？" → AI 即时回答</p>
            <p>4. 如需离线部署 → Tab 2 "部署管理" → 打包 → 客户现场安装</p>
            <p className="text-gray-600 mt-1">详见 docs/fde/fde-poc-playbook.md</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// ⑥ 评测护栏 — 灰度发布 (Canary Release)
// ═══════════════════════════════════════════════════════════
const CanaryTab: React.FC<{ readonly deployVersion: string | null; readonly onResult: (result: CanaryResult) => void }> = ({ deployVersion, onResult }) => {
  const [status, setStatus] = useState<any>(null);
  const [rollbackSpec, setRollbackSpec] = useState('');
  const [rollbackResult, setRollbackResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    const r = await fetch(API('/canary/status'));
    const data = await r.json();
    setStatus(data);
    if (data?.passed !== undefined) {
      onResult({ passed: !!data.passed, qualityScore: data.quality_score ?? data.score ?? 0 });
    }
  };
  useEffect(() => { load(); }, []);

  const doRollback = async () => {
    if (!rollbackSpec) return;
    setLoading(true);
    try {
      const r = await fetch(API('/canary/rollback'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ spec_id: rollbackSpec }) });
      setRollbackResult(await r.json());
      await load();
    } catch {} finally { setLoading(false); }
  };

  return (
    <div className="space-y-4">
      {deployVersion && <div className="text-xs text-blue-400 mb-1">部署版本: {deployVersion} — 可用作回滚目标</div>}
      <Card><CardHeader><div className="flex items-center justify-between"><span className="text-sm font-medium">灰度发布状态</span><Button variant="ghost" size="sm" onClick={load}><RefreshCw className="w-3 h-3" /></Button></div></CardHeader>
        <CardContent>
          {!status ? <div className="text-gray-500 text-sm">加载中…</div> : (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-3">
                <Card><CardContent className="p-3 text-center"><div className="text-xl font-bold text-blue-400">{status.total_skills ?? 0}</div><div className="text-xs text-gray-500">灰度 Skill 数</div></CardContent></Card>
                <Card><CardContent className="p-3 text-center"><div className="text-xl font-bold text-yellow-400">{status.active_ab_tests ?? 0}</div><div className="text-xs text-gray-500">活跃 A/B 测试</div></CardContent></Card>
                <Card><CardContent className="p-3 text-center"><div className="text-xl font-bold text-red-400">{status.rollout?.filter((s: any) => s.needs_rollback).length ?? 0}</div><div className="text-xs text-gray-500">待回滚</div></CardContent></Card>
              </div>
              {status.rollout?.length > 0 && (<div className="space-y-1 max-h-48 overflow-y-auto">{status.rollout.map((s: any, i: number) => (<div key={i} className="flex items-center justify-between text-xs py-1.5 px-2 bg-gray-800/50 rounded"><span className="text-gray-300">{s.skill_name}</span><span className={s.needs_rollback ? 'text-red-400' : 'text-green-400'}>{s.needs_rollback ? '需回滚' : `v${s.current_version || '?'} → v${s.target_version || '?'}`}</span></div>))}</div>)}
            </div>)}
        </CardContent>
      </Card>
      <Card><CardHeader><span className="text-sm font-medium">一键回滚</span></CardHeader>
        <CardContent className="space-y-2">
          <div className="flex gap-2">
            <input className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200" placeholder="Spec ID / Skill 名称" value={rollbackSpec} onChange={e => setRollbackSpec(e.target.value)} />
            <Button variant="default" size="sm" onClick={doRollback} loading={loading} disabled={!rollbackSpec}><AlertTriangle className="w-3.5 h-3.5 mr-1" />执行回滚</Button>
          </div>
          {rollbackResult && <pre className="text-xs text-gray-300 bg-gray-800 p-2 rounded max-h-32 overflow-y-auto">{JSON.stringify(rollbackResult, null, 2)}</pre>}
        </CardContent>
      </Card>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// ⑦ 验收移交 — 验证验收 + 移交 + 归档
// ═══════════════════════════════════════════════════════════
const AcceptTab: React.FC<{ readonly canaryResult: Readonly<CanaryResult> | null; readonly diagnosisReport: string; readonly onAdopted: () => void }> = ({ canaryResult, diagnosisReport, onAdopted }) => {
  const [specId, setSpecId] = useState('');
  const [requirements, setRequirements] = useState('');
  const [needAgent, setNeedAgent] = useState(true);
  const [needWorkflow, setNeedWorkflow] = useState(false);
  const [checklist, setChecklist] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [signoffResult, setSignoffResult] = useState<any>(null);
  const [manualDraft, setManualDraft] = useState<any>(null);
  const [manualDraftDate, setManualDraftDate] = useState('');
  const [fdeName, setFdeName] = useState(localStorage.getItem('aiplat_role') || 'fde');
  const [clientAdmin, setClientAdmin] = useState('');
  const [handoverResult, setHandoverResult] = useState<any>(null);
  const [summary, setSummary] = useState('');
  const [closeResult, setCloseResult] = useState<any>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      const r = requirements.toLowerCase();
      setNeedWorkflow(['流程', '步骤', '审批', '审核', '多轮', '分支', '判断', '协同', '编排'].some(kw => r.includes(kw)));
    }, 300);
    return () => clearTimeout(timer);
  }, [requirements]);

  useEffect(() => {
    if (diagnosisReport && !requirements) {
      setRequirements(diagnosisReport);
    }
  }, [diagnosisReport]);

  const loadChecklist = async () => { setLoading(true); try { const q = specId ? `?spec_id=${encodeURIComponent(specId)}` : ''; const r = await fetch(API(`/acceptance/checklist${q}`)); setChecklist(await r.json()); } catch {} finally { setLoading(false); } };
  const doSignoff = async () => { setLoading(true); try { const r = await fetch(API('/acceptance/signoff'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ spec_id: specId, signed_by: fdeName }) }); setSignoffResult(await r.json()); } catch {} finally { setLoading(false); } };
  const doTransfer = async () => { if (!clientAdmin) return; setLoading(true); try { const r = await fetch(API('/handover/transfer'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ spec_id: specId, client_admin: clientAdmin }) }); setHandoverResult(await r.json()); } catch {} finally { setLoading(false); } };
  const doClose = async () => { setLoading(true); try { const r = await fetch(API('/handover/close'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ spec_id: specId, summary, fde_name: fdeName }) }); setCloseResult(await r.json()); } catch {} finally { setLoading(false); } };
  const sb = (s: string) => { const m: Record<string, string> = { pass: 'bg-green-500/20 text-green-400', fail: 'bg-red-500/20 text-red-400', pending: 'bg-yellow-500/20 text-yellow-400' }; return <span className={`text-[10px] px-1.5 py-0.5 rounded ${m[s] || 'bg-gray-500/20 text-gray-400'}`}>{s === 'pass' ? '✓' : s === 'fail' ? '✗' : '…'}</span>; };

  const generateManual = async () => {
    const params = new URLSearchParams();
    if (specId) params.set('spec_id', specId);
    params.set('requirements', requirements);
    params.set('agent_guide', needAgent ? '1' : '0');
    params.set('workflow_guide', needWorkflow ? '1' : '0');
    params.set('fde_name', fdeName);
    const r = await fetch(API(`/manual/generate?${params}`));
    const d = await r.json();
    if (d.draft) {
      setManualDraft(d);
      setManualDraftDate(d.generated_at);
    } else {
      setSignoffResult((prev: any) => ({ ...prev, manual: d.manual, agentGuide: d.agent_creation_guide, workflowGuide: d.workflow_creation_guide, manualProjectName: d.project_name }));
    }
  };

  const displayManualData = signoffResult?.manual ? signoffResult : manualDraft;
  const isDraft = !!manualDraft && !signoffResult?.manual;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <input className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200" placeholder="Spec ID" value={specId} onChange={e => setSpecId(e.target.value)} />
        <Button variant="default" size="sm" onClick={loadChecklist} loading={loading}><CheckCircle className="w-3.5 h-3.5 mr-1" />检查验收</Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">项目交付手册</span>
            {isDraft && <span className="text-xs text-yellow-400 bg-yellow-400/10 px-2 py-0.5 rounded">草稿 — Phase 0 生成</span>}
            {signoffResult?.manual && !isDraft && <span className="text-xs text-green-400 bg-green-400/10 px-2 py-0.5 rounded">正式版</span>}
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-blue-300 bg-blue-900/30 border border-blue-800 rounded px-3 py-2 mb-3">
            Phase 0 出发前生成草稿 → 每个阶段实施后回来更新 → Phase 4 验收时定稿。不确定的字段留空，系统自动填入占位符提示下一步需补充什么。
          </p>
          <div className="space-y-2">
            <label className="text-xs text-gray-400">客户需求描述（用于自动生成/更新交付手册）</label>
            <div className="flex gap-2">
              <input className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200" placeholder="描述客户需求，系统自动生成项目交付手册" value={requirements} onChange={e => setRequirements(e.target.value)} />
              <Button variant="ghost" size="sm" onClick={generateManual}>
                <BookOpen className="w-3.5 h-3.5 mr-1" />{displayManualData ? '更新交付手册' : '生成交付手册'}
              </Button>
            </div>
            <div className="flex gap-4">
              <label className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer"><input type="checkbox" checked={needAgent} onChange={e => setNeedAgent(e.target.checked)} />Agent 创建指南 {needAgent && <span className="text-blue-400">(推荐)</span>}</label>
              <label className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer"><input type="checkbox" checked={needWorkflow} onChange={e => setNeedWorkflow(e.target.checked)} />Workflow 创建指南 {needWorkflow && <span className="text-blue-400">(推荐)</span>}</label>
            </div>
          </div>
          {displayManualData && (
            <div className="mt-3 pt-3 border-t border-gray-700/50">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <a href={`data:text/markdown;charset=utf-8,${encodeURIComponent(displayManualData.manual || '')}`} className="text-xs text-blue-400 hover:underline" download={`${displayManualData.manualProjectName || displayManualData.project_name || 'delivery-manual'}.md`}><Download className="w-3 h-3 inline mr-1" />下载交付手册 (.md)</a>
                  <button className="text-xs text-gray-500 hover:text-gray-300" onClick={() => isDraft ? setManualDraft((prev: any) => ({ ...prev, _editingManual: !prev?._editingManual })) : setSignoffResult((prev: any) => ({ ...prev, _editingManual: !prev?._editingManual }))}>{displayManualData?._editingManual ? '预览' : '编辑'}</button>
                </div>
                <button className="text-xs text-gray-500 hover:text-gray-300" onClick={() => isDraft ? setManualDraft((prev: any) => ({ ...prev, _expandedManual: !prev?._expandedManual })) : setSignoffResult((prev: any) => ({ ...prev, _expandedManual: !prev?._expandedManual }))}>{displayManualData?._expandedManual ? '收起' : '展开'}</button>
              </div>
              {displayManualData?._editingManual ? (
                <textarea className="w-full bg-gray-800 border border-gray-700 rounded p-2 mt-1 text-xs text-gray-200 font-mono h-64 resize-y" value={displayManualData.manual || ''} onChange={e => isDraft ? setManualDraft((prev: any) => ({ ...prev, manual: e.target.value })) : setSignoffResult((prev: any) => ({ ...prev, manual: e.target.value }))} />
              ) : (
                <pre className="text-xs text-gray-300 bg-gray-800 p-2 rounded mt-1 max-h-48 overflow-y-auto">{displayManualData._expandedManual ? (displayManualData.manual || '') : (displayManualData.manual || '').slice(0, 2000)}</pre>
              )}
            </div>
          )}
          {displayManualData?.agentGuide && (
            <div className="pt-2 border-t border-gray-700/50"><div className="flex items-center justify-between"><span className="text-xs text-gray-400 font-medium">Agent 创建指南</span><button className="text-xs text-gray-500 hover:text-gray-300" onClick={() => isDraft ? setManualDraft((prev: any) => ({ ...prev, _expandedAgentGuide: !prev?._expandedAgentGuide })) : setSignoffResult((prev: any) => ({ ...prev, _expandedAgentGuide: !prev?._expandedAgentGuide }))}>{displayManualData?._expandedAgentGuide ? '收起' : '展开'}</button></div><pre className="text-xs text-gray-300 bg-gray-800 p-2 rounded mt-1 max-h-48 overflow-y-auto">{displayManualData._expandedAgentGuide ? displayManualData.agentGuide : displayManualData.agentGuide.slice(0, 2000)}</pre></div>
          )}
          {displayManualData?.workflowGuide && (
            <div className="pt-2 border-t border-gray-700/50"><div className="flex items-center justify-between"><span className="text-xs text-gray-400 font-medium">Workflow 创建指南</span><button className="text-xs text-gray-500 hover:text-gray-300" onClick={() => isDraft ? setManualDraft((prev: any) => ({ ...prev, _expandedWorkflowGuide: !prev?._expandedWorkflowGuide })) : setSignoffResult((prev: any) => ({ ...prev, _expandedWorkflowGuide: !prev?._expandedWorkflowGuide }))}>{displayManualData?._expandedWorkflowGuide ? '收起' : '展开'}</button></div><pre className="text-xs text-gray-300 bg-gray-800 p-2 rounded mt-1 max-h-48 overflow-y-auto">{displayManualData._expandedWorkflowGuide ? displayManualData.workflowGuide : displayManualData.workflowGuide.slice(0, 2000)}</pre></div>
          )}
        </CardContent>
      </Card>

      {checklist && (
        <Card><CardHeader><div className="flex items-center justify-between"><span className="text-sm font-medium">验收 Checklist</span><span className="text-xs text-gray-500">{checklist.passed}/{checklist.total} 通过</span></div></CardHeader>
          <CardContent className="space-y-1">
            {checklist.checklist?.map((c: any) => (<div key={c.id} className="flex items-center justify-between text-xs py-1.5 px-2 bg-gray-800/50 rounded"><div><span className="text-gray-300">{c.label}</span><span className="text-gray-600 ml-2">{c.detail}</span></div>{sb(c.status)}</div>))}
            {checklist.ready_for_signoff ? (<div className="flex items-center gap-2 pt-3"><input className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200" placeholder="FDE 姓名" value={fdeName} onChange={e => setFdeName(e.target.value)} /><Button variant="default" size="sm" onClick={doSignoff} loading={loading}><CheckCircle className="w-3.5 h-3.5 mr-1" />签收验收</Button></div>) : (<p className="text-xs text-gray-600 pt-2">请解决 fail 项后签收</p>)}
            {signoffResult && <div className="text-xs text-green-400 mt-1">✓ 已签收 — {signoffResult.record_id}</div>}
          </CardContent>
        </Card>
      )}
      {handoverResult && (<Card><CardHeader><span className="text-sm font-medium">移交管理员</span></CardHeader><CardContent className="space-y-2"><div className="flex items-center gap-2"><UserCheck className="w-4 h-4 text-blue-400" /><span className="text-xs text-gray-400">将项目所有权转移给客户方管理员</span></div><div className="flex gap-2"><input className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200" placeholder="客户管理员用户名" value={clientAdmin} onChange={e => setClientAdmin(e.target.value)} /><Button variant="default" size="sm" onClick={doTransfer} loading={loading} disabled={!clientAdmin}>执行移交</Button></div><pre className="text-xs text-gray-300 bg-gray-800 p-2 rounded max-h-32 overflow-y-auto">{JSON.stringify(handoverResult, null, 2)}</pre></CardContent></Card>)}
      {handoverResult && (<Card><CardHeader><span className="text-sm font-medium">项目归档</span></CardHeader><CardContent className="space-y-2"><textarea className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200 h-16" placeholder="项目交付总结..." value={summary} onChange={e => setSummary(e.target.value)} /><Button variant="default" size="sm" onClick={doClose} loading={loading}>关闭项目并归档</Button>{closeResult && <div className="text-xs text-green-400 mt-1">✓ 项目已归档 — {closeResult.archive_id}</div>}</CardContent></Card>)}
      {closeResult && (<Card><CardHeader><span className="text-sm font-medium">首月护航</span></CardHeader><CardContent className="space-y-3"><div className="space-y-2"><div className="flex items-center gap-2"><Activity className="w-4 h-4 text-green-400" /><span className="text-xs text-gray-400">安排 30 天后自动健康检查</span></div><div className="flex gap-2"><input className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200" placeholder="通知邮箱 (可选)" onChange={e => (window as any).__health_email = e.target.value} /><Button variant="ghost" size="sm" onClick={async () => { const r = await fetch(API('/handover/schedule-health'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ spec_id: specId, notify_email: (window as any).__health_email || '' }) }); const d = await r.json(); setCloseResult((prev: any) => ({ ...prev, health: d })); }}>安排健康检查</Button></div>{closeResult?.health && <div className="text-xs text-green-400">✓ 已安排 — 将于 {closeResult.health.due_at?.slice(0,10)} 执行</div>}</div><div className="space-y-2 pt-2 border-t border-gray-700/50"><div className="flex items-center gap-2"><Users className="w-4 h-4 text-blue-400" /><span className="text-xs text-gray-400">创建培训沙盒环境</span></div><div className="flex gap-2"><select className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200" onChange={e => (window as any).__sandbox_count = parseInt(e.target.value)} defaultValue="5">{[1,3,5,10,20,50].map(n => <option key={n} value={n}>{n} 人</option>)}</select><Button variant="ghost" size="sm" onClick={async () => { const count = (window as any).__sandbox_count || 5; const r = await fetch(API('/training/sandbox'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ spec_id: specId, trainee_count: count }) }); const d = await r.json(); setCloseResult((prev: any) => ({ ...prev, sandbox: d })); }}>创建培训沙盒</Button></div>{closeResult?.sandbox && <div className="text-xs text-green-400">✓ 沙盒已创建 | {closeResult.sandbox.trainee_count} 人 | 有效期: {closeResult.sandbox.access?.expires_in}</div>}</div></CardContent></Card>)}
    </div>
  );
};

export default FdeDashboard;
