/**
 * FdeDashboard — FDE 工作台 (Field Deployment Engineer Toolkit, 方向一)
 *
 * 5 Tab 统一入口:
 *   Tab 1: 系统进化 (Evolution 监控 — 迁移自 workbench FDE Dashboard)
 *   Tab 2: 部署管理 (离线部署包 打包/下载)
 *   Tab 3: 客户诊断 (field_assessment Skill → 报告)
 *   Tab 4: 客户列表 (多客户视图 + 健康摘要)
 *   Tab 5: 现场反馈 (结构化提交 + 历史)
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { Wrench, RefreshCw, Package, Download, Users, FileText, Target, Activity, AlertTriangle, Send, Clipboard } from 'lucide-react';

const API = (path: string) => `/api/core/fde${path}`;

// ── Tab labels ──
const TABS = [
  { key: 'evolution', label: '系统进化', icon: Activity },
  { key: 'deploy',    label: '部署管理', icon: Package },
  { key: 'assess',    label: '客户诊断', icon: FileText },
  { key: 'customers', label: '客户列表', icon: Users },
  { key: 'feedback',  label: '现场反馈', icon: Clipboard },
] as const;

type TabKey = typeof TABS[number]['key'];

// ── Dashboard ──
const FdeDashboard: React.FC = () => {
  const [tab, setTab] = useState<TabKey>('evolution');
  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-gray-100">FDE 工作台</h1>
      </div>
      <div className="flex gap-1 border-b border-gray-700/50 pb-0">
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 px-3 py-2 text-sm border-b-2 transition-colors ${
              tab === t.key ? 'border-blue-500 text-white' : 'border-transparent text-gray-500 hover:text-gray-300'
            }`}
          >
            <t.icon className="w-3.5 h-3.5" />{t.label}
          </button>
        ))}
      </div>
      {tab === 'evolution' && <EvolutionTab />}
      {tab === 'deploy'    && <DeployTab />}
      {tab === 'assess'    && <AssessTab />}
      {tab === 'customers' && <CustomersTab />}
      {tab === 'feedback'  && <FeedbackTab />}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// Tab 1: 系统进化 (原 workbench FDE Dashboard)
// ═══════════════════════════════════════════════════════════
const EvolutionTab: React.FC = () => {
  const [data, setData] = useState<any>(null);
  useEffect(() => { fetch(API('/dashboard')).then(r => r.json()).then(setData); }, []);
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
// Tab 2: 部署管理
// ═══════════════════════════════════════════════════════════
const DeployTab: React.FC = () => {
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
    const r = await fetch(API('/package'), { method: 'POST' });
    const { task_id } = await r.json();
    setTaskId(task_id);
    setLoading(false);
    poll(task_id);
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><span className="text-sm font-medium">离线部署包</span></CardHeader>
        <CardContent className="space-y-3">
          <Button variant="default" size="sm" onClick={startPackage} loading={loading}>
            <Package className="w-3.5 h-3.5 mr-1" />打包离线部署包
          </Button>
          {taskId && status && (
            <div className="space-y-1 text-sm">
              <div className="flex items-center gap-2">
                <div className="bg-gray-700 rounded-full h-2 flex-1">
                  <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${status.progress || 0}%` }} />
                </div>
                <span className="text-gray-400 text-xs">{status.progress || 0}%</span>
              </div>
              <p className="text-gray-400 text-xs">{status.detail}</p>
              {status.download_url && (
                <a href={`/api/core/fde/package/${taskId}/download`}
                   className="inline-flex items-center gap-1 text-blue-400 text-xs hover:underline">
                  <Download className="w-3 h-3" />下载 ({status.size_mb} MB)
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
// Tab 3: 客户诊断
// ═══════════════════════════════════════════════════════════
const AssessTab: React.FC = () => {
  const [form, setForm] = useState<Record<string, string>>({});
  const [report, setReport] = useState('');
  const [loading, setLoading] = useState(false);

  const fields = [
    { key: 'company_name', label: '企业名称' },
    { key: 'industry', label: '行业' },
    { key: 'custom_industry', label: '自定义行业' },
    { key: 'team_size', label: '团队规模' },
    { key: 'pain_points', label: '痛点 (逗号分隔)' },
    { key: 'existing_tech_stack', label: '现有技术栈 (逗号分隔)' },
    { key: 'data_sources', label: '数据源 (逗号分隔)' },
    { key: 'compliance_requirements', label: '合规要求 (逗号分隔)' },
    { key: 'budget_range', label: '预算范围' },
    { key: 'timeline', label: '时间线' },
  ];

  const submit = async () => {
    setLoading(true);
    try {
      const r = await fetch('/api/core/skills/field-assessment/execute', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_name: form.company_name,
          industry: form.industry,
          custom_industry: form.custom_industry,
          team_size: parseInt(form.team_size) || 0,
          pain_points: (form.pain_points || '').split(',').map(s => s.trim()).filter(Boolean),
          existing_tech_stack: (form.existing_tech_stack || '').split(',').map(s => s.trim()).filter(Boolean),
          data_sources: (form.data_sources || '').split(',').map(s => s.trim()).filter(Boolean),
          compliance_requirements: (form.compliance_requirements || '').split(',').map(s => s.trim()).filter(Boolean),
          budget_range: form.budget_range,
          timeline: form.timeline,
        }),
      });
      const data = await r.json();
      setReport(data.output || data.report || JSON.stringify(data, null, 2));
    } catch {}
    setLoading(false);
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><span className="text-sm font-medium">新客户AI落地诊断</span></CardHeader>
        <CardContent className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            {fields.map(f => (
              <div key={f.key}>
                <label className="text-xs text-gray-400">{f.label}</label>
                <input className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200"
                       value={form[f.key] || ''} onChange={e => setForm({...form, [f.key]: e.target.value})} />
              </div>
            ))}
          </div>
          <Button variant="default" size="sm" onClick={submit} loading={loading}>
            <FileText className="w-3.5 h-3.5 mr-1" />提交诊断
          </Button>
        </CardContent>
      </Card>
      {report && (
        <Card>
          <CardHeader><span className="text-sm font-medium">诊断报告</span></CardHeader>
          <CardContent>
            <pre className="text-xs text-gray-300 whitespace-pre-wrap max-h-96 overflow-y-auto">{report}</pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// Tab 4: 客户列表
// ═══════════════════════════════════════════════════════════
const CustomersTab: React.FC = () => {
  const [customers, setCustomers] = useState<any[]>([]);
  const load = () => fetch(API('/customers')).then(r => r.json()).then(d => setCustomers(d.customers || []));
  useEffect(() => { load(); }, []);
  const switchProfile = async (name: string) => {
    await fetch(API(`/switch-profile/${name}`), { method: 'POST' });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500">共 {customers.length} 个客户 Profile</span>
        <Button variant="ghost" size="sm" onClick={load}><RefreshCw className="w-3 h-3" /></Button>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {customers.map(c => (
          <Card key={c.name} className="cursor-pointer hover:border-gray-600" onClick={() => switchProfile(c.name)}>
            <CardContent className="p-3 space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-200">{c.name}</span>
                {c.default && <span className="text-[10px] bg-blue-500/20 text-blue-300 px-1 rounded">默认</span>}
              </div>
              <div className="text-[11px] text-gray-500">{c.namespace}</div>
              {c.mcp_servers?.length > 0 && <div className="text-[10px] text-gray-600">MCP: {c.mcp_servers.length}</div>}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
};

// ═══════════════════════════════════════════════════════════
// Tab 5: 现场反馈
// ═══════════════════════════════════════════════════════════
const FeedbackTab: React.FC = () => {
  const [form, setForm] = useState<Record<string, string>>({});
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const loadHistory = () => fetch(API('/feedback/history')).then(r => r.json()).then(d => setHistory(d.feedback || []));
  useEffect(() => { loadHistory(); }, []);

  const submit = async () => {
    setLoading(true);
    await fetch(API('/feedback'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        fde_id: localStorage.getItem('aiplat_role') || 'fde',
        customer_profile_id: form.customer || 'unknown',
        environment: { deployment_mode: form.mode || 'online', aiplat_version: '', python_version: '', os: '' },
        issue: { category: form.category || 'bug', description: form.description || '',
                 affected_component: form.component || '', reproduction_steps: form.steps || '' },
        workaround: { description: form.workaround || '', code_snippet: '', deployed_to_customer: false },
        suggested_improvement: { description: form.suggestion || '', priority: form.priority || 'medium' },
      }),
    });
    setLoading(false);
    setForm({});
    loadHistory();
  };

  const fbFields = [
    { key: 'customer', label: '客户 Profile' },
    { key: 'category', label: '问题类别 (bug/missing_feature/performance/usability/integration)' },
    { key: 'component', label: '影响组件 (agent/skill/pipeline/mcp/frontend/core)' },
    { key: 'description', label: '问题描述' },
    { key: 'steps', label: '复现步骤 (可选)' },
    { key: 'workaround', label: '临时方案' },
    { key: 'suggestion', label: '建议改进' },
    { key: 'priority', label: '优先级 (high/medium/low)' },
    { key: 'mode', label: '部署模式 (airgap/online/hybrid)' },
  ];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><span className="text-sm font-medium">提交现场反馈</span></CardHeader>
        <CardContent className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            {fbFields.map(f => (
              <div key={f.key} className={f.key === 'description' || f.key === 'workaround' || f.key === 'suggestion' ? 'col-span-2' : ''}>
                <label className="text-xs text-gray-400">{f.label}</label>
                {f.key === 'description' || f.key === 'workaround' || f.key === 'suggestion' ? (
                  <textarea className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200 h-16"
                            value={form[f.key] || ''} onChange={e => setForm({...form, [f.key]: e.target.value})} />
                ) : (
                  <input className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200"
                         value={form[f.key] || ''} onChange={e => setForm({...form, [f.key]: e.target.value})} />
                )}
              </div>
            ))}
          </div>
          <Button variant="default" size="sm" onClick={submit} loading={loading}>
            <Send className="w-3.5 h-3.5 mr-1" />提交反馈
          </Button>
        </CardContent>
      </Card>
      {history.length > 0 && (
        <Card>
          <CardHeader><span className="text-sm font-medium">最近反馈 ({history.length})</span></CardHeader>
          <CardContent className="space-y-1 max-h-64 overflow-y-auto">
            {history.filter((f): f is any => f).map((f: any, i: number) => (
              <div key={f.id || i} className="flex justify-between text-xs py-1 border-b border-gray-800/50">
                <span className="text-gray-300 truncate">{(f.issue?.description || '').slice(0, 60)}</span>
                <span className="text-gray-500">{f.created_at?.slice(0, 10) || ''}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default FdeDashboard;
