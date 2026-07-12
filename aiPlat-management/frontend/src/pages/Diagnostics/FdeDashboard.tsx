/**
 * FdeDashboard — FDE 工作台 (Field Deployment Engineer Toolkit, 方向一)
 *
 * 8 Tab 统一入口:
 *   Tab 1: 系统进化 (Evolution 监控)
 *   Tab 2: 部署管理 (离线部署包 打包/下载 + 执行日志)
 *   Tab 3: 客户诊断 (field_assessment Skill → 报告)
 *   Tab 4: 客户列表 (多客户视图 + 健康摘要)
 *   Tab 5: 现场反馈 (结构化提交 + 历史)
 *   Tab 6: POC 工具箱 (行业模板 + 数据注入)
 *   Tab 7: 灰度发布 (Canary status + 一键回滚)
 *   Tab 8: 验证验收 (Checklist + 签收 + 移交 + 归档 + 首月护航)
 */
import React, { useEffect, useState, useCallback } from 'react';
import { Card, CardContent, CardHeader, Button } from '../../components/ui';
import { Wrench, RefreshCw, Package, Download, Users, FileText, Target, Activity, AlertTriangle, Send, Clipboard, TrendingUp, CheckCircle, UserCheck, BookOpen } from 'lucide-react';

const API = (path: string) => `/api/core/fde${path}`;

// ── Tab labels ──
const TABS = [
  { key: 'evolution', label: '系统进化', icon: Activity },
  { key: 'deploy',    label: '部署管理', icon: Package },
  { key: 'assess',    label: '客户诊断', icon: FileText },
  { key: 'customers', label: '客户列表', icon: Users },
  { key: 'feedback',  label: '现场反馈', icon: Clipboard },
  { key: 'poc',       label: 'POC 工具箱', icon: Wrench },
  { key: 'canary',    label: '灰度发布', icon: TrendingUp },
  { key: 'accept',    label: '验证验收', icon: CheckCircle },
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
      {tab === 'poc'       && <PocTab />}
      {tab === 'canary'    && <CanaryTab />}
      {tab === 'accept'    && <AcceptTab />}
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
    setStatus(null);
    try {
      const r = await fetch(API('/package'), { method: 'POST' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const { task_id } = await r.json();
      setTaskId(task_id);
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
// Tab 3: 客户诊断
// ═══════════════════════════════════════════════════════════
const AssessTab: React.FC = () => {
  const [form, setForm] = useState<Record<string, string>>({});
  const [report, setReport] = useState('');
  const [loading, setLoading] = useState(false);
  const [manual, setManual] = useState<any>(null);
  const [reportExpanded, setReportExpanded] = useState(false);
  const [pendingFeedback, setPendingFeedback] = useState('');
  const [updating, setUpdating] = useState(false);
  const [templates, setTemplates] = useState<Array<{
    name: string; form: Record<string, string>; report: string;
  }>>([]);
  const [showTemplates, setShowTemplates] = useState(false);
  // ── Clarification dialog state ──
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogTurn, setDialogTurn] = useState(1);
  const [dialogContext, setDialogContext] = useState<Record<string, string>>({});
  const [dialogHistory, setDialogHistory] = useState<Array<{role: string; content: string}>>([]);
  const [dialogQuestion, setDialogQuestion] = useState('');
  const [dialogOptions, setDialogOptions] = useState<string[]>([]);
  const [dialogReady, setDialogReady] = useState(false);
  const [dialogFinished, setDialogFinished] = useState(false);
  const [dialogLoading, setDialogLoading] = useState(false);
  const [dialogInput, setDialogInput] = useState('');

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
    { key: 'pain_points', label: '痛点', placeholder: '例如：客服效率低、数据孤岛、合规成本高 (逗号分隔)', desc: '客户核心业务痛点，最多 5 个；最关键的放前面', required: true },
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
        if (Array.isArray(data.pain_points)) mapped.pain_points = data.pain_points.join(', ');
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
  const dialogCall = async (answer?: string) => {
    setDialogLoading(true);
    try {
      const r = await fetch('/api/core/fde/assess/dialog', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          turn: dialogTurn,
          answer: answer || '',
          industry: form.industry || dialogContext.industry || '',
          company_name: form.company_name || dialogContext.company_name || '',
          pain_points: form.pain_points || dialogContext.pain_points || '',
          team_size: form.team_size || dialogContext.team_size || '',
          budget: form.budget_range || dialogContext.budget || '',
        }),
      });
      const data = await r.json();
      setDialogContext(data.context || {});
      setDialogReady(data.can_finalize);
      setDialogQuestion(data.question || '');
      setDialogOptions(data.options || []);
      setDialogTurn(data.turn || 2);
      setDialogHistory(prev => [
        ...prev,
        ...(answer ? [{ role: 'user', content: answer }] : []),
        { role: 'assistant', content: data.question },
      ]);

      // ── Handle "finished" flag: close dialog + generate diagnosis ──
      if (data.finished) {
        setDialogFinished(true);
        setTimeout(() => {
          setDialogOpen(false);
          // Write back collected context to form
          setForm(prev => ({
            ...prev,
            ...(data.context?.company_name ? { company_name: data.context.company_name } : {}),
            ...(data.context?.pain_points ? { pain_points: data.context.pain_points } : {}),
            ...(data.context?.team_size ? { team_size: data.context.team_size } : {}),
            ...(data.context?.budget ? { budget_range: data.context.budget } : {}),
          }));
          setTimeout(() => submit(), 100);
        }, 500); // brief delay so user sees the "finished" message
      }
    } catch { setDialogQuestion('网络错误，请重试'); }
    setDialogLoading(false);
  };

  const openDialog = () => {
    setDialogOpen(true);
    setDialogTurn(1);
    setDialogHistory([]);
    setDialogReady(false);
    setDialogContext({});
    dialogCall();
  };

  const submit = async (extraInput?: Record<string, any>) => {
    setLoading(true);
    try {
      const input = {
        company_name: form.company_name || '',
        industry: form.industry || '',
        custom_industry: form.custom_industry || '',
        team_size: parseInt(form.team_size) || 0,
        pain_points: (form.pain_points || '').split(',').map(s => s.trim()).filter(Boolean),
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

        // 仅诊断成功时自动生成交付手册草稿
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
        try {
          const diagSummary = outputText ? outputText.replace(/```[\s\S]*?```/g, '').replace(/`{1,2}([^`]+)`{1,2}/g, '$1').trim() : '';
          const specId = generateSpecId(form.industry || '通用');
          const mr = await fetch(API(`/manual/generate?requirements=${encodeURIComponent(reqStr)}&industry=${encodeURIComponent(form.industry || '通用')}&agent_guide=1&workflow_guide=1&spec_id=${encodeURIComponent(specId)}&diagnosis_report=${encodeURIComponent(diagSummary)}`));
          const md = await mr.json();
          setManual(md);
        } catch {}
      }
    } catch {}
    setLoading(false);
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
                <div key={f.key}>
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
            <Button variant="outline" size="sm" onClick={openDialog}>
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
      {/* ── 智能澄清 Dialog ── */}
      {dialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setDialogOpen(false)}>
          <div className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-md mx-4 shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
              <span className="text-sm font-medium text-gray-200">⚡ 智能澄清</span>
              <button onClick={() => setDialogOpen(false)} className="text-gray-500 hover:text-gray-300 text-lg">&times;</button>
            </div>
            <div className="max-h-64 overflow-y-auto px-4 py-3 space-y-2">
              {dialogHistory.map((msg, i) => (
                <div key={i} className={`text-xs leading-relaxed ${msg.role === 'user' ? 'text-blue-300' : 'text-gray-300'}`}>
                  <span className="font-medium text-gray-500">{msg.role === 'user' ? '你' : '系统'}</span>
                  <p className="mt-0.5">{msg.content}</p>
                </div>
              ))}
              {dialogLoading && <p className="text-xs text-gray-500">分析中...</p>}
            </div>
            <div className="px-4 py-3 border-t border-gray-700 space-y-2">
              {dialogOptions.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {dialogOptions.map(opt => (
                    <button key={opt} className="px-2 py-1 text-xs rounded bg-blue-500/15 text-blue-300 border border-blue-500/25 hover:bg-blue-500/25"
                      onClick={() => {
                        setDialogHistory(prev => [...prev, { role: 'user', content: opt }]);
                        dialogCall(opt);
                      }}>{opt}</button>
                  ))}
                </div>
              )}
              <div className="flex gap-1">
                <input className="flex-1 h-8 px-3 bg-dark-bg border border-dark-border rounded text-xs text-gray-200" placeholder="输入回复...输入「结束」可结束澄清"
                  value={dialogInput} onChange={e => setDialogInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') { dialogCall(dialogInput); setDialogInput(''); }}} />
                <Button variant="ghost" size="sm" onClick={() => { dialogCall(dialogInput); setDialogInput(''); }}
                  disabled={!dialogInput.trim()}>发送</Button>
              </div>
              <Button variant="ghost" size="sm" className="w-full text-gray-500" onClick={() => setDialogOpen(false)}>取消</Button>
            </div>
          </div>
        </div>
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

// ═══════════════════════════════════════════════════════════
// Tab 6: POC 工具箱
// ═══════════════════════════════════════════════════════════
const PocTab: React.FC = () => {
  const [profile, setProfile] = useState('');
  const [injectResult, setInjectResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const industries = [
    { key: 'manufacturing', label: '制造业', desc: '质检+设备运维' },
    { key: 'finance',       label: '金融业', desc: '合规+风险' },
    { key: 'retail',        label: '零售业', desc: '客服+选品' },
    { key: 'general',       label: '通用',   desc: '知识问答' },
  ];

  const loadTemplate = async (industry: string) => {
    setLoading(true);
    try {
      await fetch(API(`/switch-profile/poc-${industry}`), { method: 'POST' });
      setProfile(industry);
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
            {industries.map(ind => (
              <button key={ind.key}
                onClick={() => loadTemplate(ind.key)}
                disabled={loading}
                className={`p-3 rounded-md border text-left text-xs transition-colors ${
                  profile === ind.key ? 'border-blue-500 bg-blue-500/10' : 'border-gray-700 hover:border-gray-500'
                }`}>
                <div className="text-gray-200 font-medium">{ind.label}</div>
                <div className="text-gray-500">{ind.desc}</div>
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
// Tab 7: 灰度发布 (Canary Release)
// ═══════════════════════════════════════════════════════════
const CanaryTab: React.FC = () => {
  const [status, setStatus] = useState<any>(null);
  const [rollbackSpec, setRollbackSpec] = useState('');
  const [rollbackResult, setRollbackResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    const r = await fetch(API('/canary/status'));
    setStatus(await r.json());
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
// Tab 8: 验证验收 + 移交 + 归档
// ═══════════════════════════════════════════════════════════
const AcceptTab: React.FC = () => {
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
