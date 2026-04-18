import React, { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Plus, RotateCw, PlayCircle, PauseCircle, Trash2, Clock, ExternalLink, Copy } from 'lucide-react';
import PageHeader from '../../../components/common/PageHeader';
import { Button, Modal, Input, Textarea, toast, Table } from '../../../components/ui';
import { jobApi, agentApi, skillApi, toolApi, type Job, type JobRun, type JobDeliveryDLQItem } from '../../../services';

const shortId = (id: string) => (id && id.length > 12 ? `${id.slice(0, 6)}…${id.slice(-4)}` : id);

const fmtTs = (ts?: number | null) => {
  if (!ts) return '-';
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return String(ts);
  }
};

const Jobs: React.FC = () => {
  const location = useLocation();
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [runsOpen, setRunsOpen] = useState(false);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [runs, setRuns] = useState<JobRun[]>([]);
  const [runsTotal, setRunsTotal] = useState(0);
  const [runsOffset, setRunsOffset] = useState(0);
  const runsLimit = 50;
  const [highlightRunId, setHighlightRunId] = useState<string | null>(null);

  const [dlqOpen, setDlqOpen] = useState(false);
  const [dlqLoading, setDlqLoading] = useState(false);
  const [dlqItems, setDlqItems] = useState<JobDeliveryDLQItem[]>([]);
  const [dlqTotal, setDlqTotal] = useState(0);
  const [dlqStatus, setDlqStatus] = useState<'pending' | 'resolved' | ''>('pending');
  const [dlqOffset, setDlqOffset] = useState(0);
  const dlqLimit = 50;

  // form
  const [name, setName] = useState('');
  const [kind, setKind] = useState<'agent' | 'skill' | 'tool' | 'graph'>('agent');
  const [targetId, setTargetId] = useState('');
  const [cron, setCron] = useState('*/1 * * * *');
  const [userId, setUserId] = useState('system');
  const [sessionId, setSessionId] = useState('default');
  const [payloadText, setPayloadText] = useState('{\n  "input": {}\n}');
  const [optionsText, setOptionsText] = useState('{\n  "toolset": "workspace_default"\n}');
  const [deliveryText, setDeliveryText] = useState('');
  const [targetSuggestions, setTargetSuggestions] = useState<{ value: string; label: string }[]>([]);
  const [targetsLoading, setTargetsLoading] = useState(false);

  const loadTargets = async (k: 'agent' | 'skill' | 'tool' | 'graph') => {
    // graph 暂不提供可选列表（后续可做：列出内置 graph_name）
    if (k === 'graph') {
      setTargetSuggestions([]);
      return;
    }
    setTargetsLoading(true);
    try {
      if (k === 'agent') {
        const res = await agentApi.list({ limit: 200, offset: 0 });
        const opts = (res.agents || []).map((a) => ({ value: a.id, label: `${a.name} (${a.id})` }));
        setTargetSuggestions(opts);
      } else if (k === 'skill') {
        const res = await skillApi.list({ limit: 200, offset: 0 });
        const opts = (res.skills || []).map((s) => ({ value: s.id, label: `${s.name} (${s.id})` }));
        setTargetSuggestions(opts);
      } else if (k === 'tool') {
        const res = await toolApi.list({ limit: 200, offset: 0 });
        const opts = (res.tools || []).map((t) => ({ value: t.name, label: `${t.name}${t.category ? ` (${t.category})` : ''}` }));
        setTargetSuggestions(opts);
      }
    } catch (e: any) {
      setTargetSuggestions([]);
      toast.error('加载 target 列表失败', String(e?.message || ''));
    } finally {
      setTargetsLoading(false);
    }
  };

  useEffect(() => {
    if (createOpen || editOpen) {
      loadTargets(kind);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [createOpen, editOpen, kind]);

  const setToolsetQuick = (toolset: 'safe_readonly' | 'workspace_default' | 'full') => {
    try {
      const cur = optionsText?.trim() ? JSON.parse(optionsText) : {};
      const next = typeof cur === 'object' && cur ? cur : {};
      (next as any).toolset = toolset;
      setOptionsText(JSON.stringify(next, null, 2));
    } catch {
      setOptionsText(JSON.stringify({ toolset }, null, 2));
    }
  };

  const applyTemplate = (tpl: 'tool_calculator' | 'agent_basic' | 'skill_basic' | 'webhook_delivery') => {
    if (tpl === 'tool_calculator') {
      setKind('tool');
      setTargetId('calculator');
      setPayloadText(JSON.stringify({ input: { expression: '1+1' } }, null, 2));
      setToolsetQuick('safe_readonly');
      return;
    }
    if (tpl === 'agent_basic') {
      setKind('agent');
      setTargetId(selectedJob?.target_id || '');
      setPayloadText(JSON.stringify({ input: { message: '请执行任务并给出结果' } }, null, 2));
      setToolsetQuick('workspace_default');
      return;
    }
    if (tpl === 'skill_basic') {
      setKind('skill');
      setTargetId(selectedJob?.target_id || '');
      setPayloadText(JSON.stringify({ input: {} }, null, 2));
      setToolsetQuick('workspace_default');
      return;
    }
    if (tpl === 'webhook_delivery') {
      setDeliveryText(
        JSON.stringify(
          {
            type: 'webhook',
            url: 'https://example.com/hook',
            headers: { Authorization: 'Bearer <token>' },
            include: ['job', 'run', 'result'],
          },
          null,
          2
        )
      );
      return;
    }
  };

  const resetForm = () => {
    setName('');
    setKind('agent');
    setTargetId('');
    setCron('*/1 * * * *');
    setUserId('system');
    setSessionId('default');
    setPayloadText('{\n  "input": {}\n}');
    setOptionsText('{\n  "toolset": "workspace_default"\n}');
    setDeliveryText('');
  };

  const loadJobs = async () => {
    setLoading(true);
    try {
      const res = await jobApi.list({ limit: 200, offset: 0 });
      setJobs(res.items || []);
      setTotal(res.total || 0);
    } catch (e: any) {
      toast.error('加载 Jobs 失败', String(e?.message || ''));
      setJobs([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadJobs();
  }, []);

  const loadDLQ = async () => {
    setDlqLoading(true);
    try {
      const res = await jobApi.listDLQ({
        limit: dlqLimit,
        offset: dlqOffset,
        status: dlqStatus || undefined,
        job_id: selectedJob?.id || undefined,
      });
      setDlqItems(res.items || []);
      setDlqTotal(res.total || 0);
    } catch (e: any) {
      toast.error('加载 DLQ 失败', String(e?.message || ''));
      setDlqItems([]);
      setDlqTotal(0);
    } finally {
      setDlqLoading(false);
    }
  };

  useEffect(() => {
    if (dlqOpen) loadDLQ();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dlqOpen, dlqOffset, dlqStatus, selectedJob?.id]);

  const openDLQ = (job: Job) => {
    setSelectedJob(job);
    setDlqOffset(0);
    setDlqStatus('pending');
    setDlqOpen(true);
  };

  const retryDLQ = async (id: string) => {
    try {
      const res = await jobApi.retryDLQ(id);
      if (res?.ok) toast.success('重试成功');
      else toast.error('重试失败', String(res?.error || ''));
      await loadDLQ();
    } catch (e: any) {
      toast.error('重试失败', String(e?.message || ''));
    }
  };

  const deleteDLQ = async (id: string) => {
    try {
      await jobApi.deleteDLQ(id);
      toast.success('已删除 DLQ 记录');
      await loadDLQ();
    } catch (e: any) {
      toast.error('删除失败', String(e?.message || ''));
    }
  };

  const openCreate = () => {
    resetForm();
    setCreateOpen(true);
  };

  const openEdit = (job: Job) => {
    setSelectedJob(job);
    setName(job.name || '');
    setKind((job.kind as any) || 'agent');
    setTargetId(job.target_id || '');
    setCron(job.cron || '*/1 * * * *');
    setUserId(String(job.user_id || 'system'));
    setSessionId(String(job.session_id || 'default'));
    setPayloadText(JSON.stringify(job.payload || { input: {} }, null, 2));
    setOptionsText(JSON.stringify(job.options || { toolset: 'workspace_default' }, null, 2));
    setDeliveryText(job.delivery ? JSON.stringify(job.delivery, null, 2) : '');
    setEditOpen(true);
  };

  const parseJsonOrEmpty = (text: string, label: string) => {
    if (!text.trim()) return undefined;
    try {
      return JSON.parse(text);
    } catch {
      throw new Error(`${label} JSON 格式错误`);
    }
  };

  const submitCreate = async () => {
    try {
      if (!name.trim()) return toast.error('请输入名称');
      if (!targetId.trim()) return toast.error('请输入 target_id');
      const payload = parseJsonOrEmpty(payloadText, 'payload') || {};
      const options = parseJsonOrEmpty(optionsText, 'options') || {};
      const delivery = parseJsonOrEmpty(deliveryText, 'delivery') || undefined;
      await jobApi.create({
        name: name.trim(),
        kind,
        target_id: targetId.trim(),
        cron: cron.trim() || '*/1 * * * *',
        enabled: true,
        user_id: userId.trim() || 'system',
        session_id: sessionId.trim() || 'default',
        payload,
        options,
        ...(delivery ? { delivery } : {}),
      });
      toast.success('创建成功');
      setCreateOpen(false);
      await loadJobs();
    } catch (e: any) {
      toast.error('创建失败', String(e?.message || ''));
    }
  };

  const submitEdit = async () => {
    if (!selectedJob) return;
    try {
      const payload = parseJsonOrEmpty(payloadText, 'payload');
      const options = parseJsonOrEmpty(optionsText, 'options');
      const delivery = parseJsonOrEmpty(deliveryText, 'delivery');
      const patch: any = {
        name: name.trim() || undefined,
        cron: cron.trim() || undefined,
        user_id: userId.trim() || undefined,
        session_id: sessionId.trim() || undefined,
      };
      if (payload !== undefined) patch.payload = payload;
      if (options !== undefined) patch.options = options;
      if (delivery !== undefined) patch.delivery = delivery;
      await jobApi.update(selectedJob.id, patch);
      toast.success('更新成功');
      setEditOpen(false);
      await loadJobs();
    } catch (e: any) {
      toast.error('更新失败', String(e?.message || ''));
    }
  };

  const toggleEnabled = async (job: Job) => {
    try {
      if (job.enabled) await jobApi.disable(job.id);
      else await jobApi.enable(job.id);
      await loadJobs();
    } catch (e: any) {
      toast.error('操作失败', String(e?.message || ''));
    }
  };

  const runNow = async (job: Job) => {
    try {
      const res = await jobApi.runNow(job.id);
      toast.success('已触发');
      await loadJobs();
      // Auto open runs and highlight the latest run if returned
      const rid = String((res as any)?.id || (res as any)?.run_id || '');
      setHighlightRunId(rid || null);
      await openRuns(job);
    } catch (e: any) {
      const msg = String(e?.message || '');
      if (msg.includes('409')) {
        toast.error('Job 正在运行/被锁占用');
        setHighlightRunId(null);
        await openRuns(job);
      } else {
        toast.error('触发失败', msg);
      }
    }
  };

  const removeJob = async (job: Job) => {
    if (!confirm(`确认删除 Job：${job.name}？`)) return;
    try {
      await jobApi.delete(job.id);
      toast.success('已删除');
      await loadJobs();
    } catch (e: any) {
      toast.error('删除失败', String(e?.message || ''));
    }
  };

  const openRuns = async (job: Job) => {
    setSelectedJob(job);
    setRunsOpen(true);
    setRunsOffset(0);
    try {
      const res = await jobApi.listRuns(job.id, { limit: runsLimit, offset: 0 });
      setRuns(res.items || []);
      setRunsTotal(res.total || 0);
    } catch (e: any) {
      setRuns([]);
      setRunsTotal(0);
      toast.error('加载运行历史失败', String(e?.message || ''));
    }
  };

  // Deep link support: /core/jobs?job_id=...&run_id=...
  useEffect(() => {
    const qs = new URLSearchParams(location.search || '');
    const jobId = qs.get('job_id');
    const runId = qs.get('run_id');
    if (!jobId) return;
    let mounted = true;
    (async () => {
      try {
        const job = await jobApi.get(jobId);
        if (!mounted) return;
        setHighlightRunId(runId || null);
        await openRuns(job);
      } catch (e: any) {
        if (mounted) toast.error('打开 Job 失败', String(e?.message || ''));
      }
    })();
    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  const refreshRuns = async () => {
    if (!selectedJob) return;
    try {
      const res = await jobApi.listRuns(selectedJob.id, { limit: runsLimit, offset: runsOffset });
      setRuns(res.items || []);
      setRunsTotal(res.total || 0);
    } catch (e: any) {
      toast.error('刷新运行历史失败', String(e?.message || ''));
    }
  };

  const columns = useMemo(
    () => [
      { key: 'name', title: '名称', dataIndex: 'name' },
      { key: 'kind', title: 'kind', dataIndex: 'kind', width: 90 },
      { key: 'target_id', title: 'target_id', dataIndex: 'target_id', width: 160, render: (v: string) => <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{v}</code> },
      { key: 'cron', title: 'cron', dataIndex: 'cron', width: 140 },
      { key: 'enabled', title: 'enabled', dataIndex: 'enabled', width: 90, render: (v: boolean) => <span className={`text-xs ${v ? 'text-green-300' : 'text-gray-500'}`}>{v ? 'true' : 'false'}</span> },
      { key: 'last_run_at', title: 'last_run', dataIndex: 'last_run_at', width: 170, render: (v: any) => <span className="text-xs text-gray-300">{fmtTs(v)}</span> },
      { key: 'next_run_at', title: 'next_run', dataIndex: 'next_run_at', width: 170, render: (v: any) => <span className="text-xs text-gray-300">{fmtTs(v)}</span> },
      {
        key: 'lock',
        title: 'lock',
        width: 170,
        render: (_: unknown, job: Job) => {
          const until = (job as any)?.lock_until as number | null | undefined;
          const owner = (job as any)?.lock_owner as string | null | undefined;
          const locked = until != null && until * 1000 > Date.now();
          if (!locked) return <span className="text-xs text-gray-500">-</span>;
          return (
            <div className="text-xs">
              <div className="text-amber-300">locked</div>
              <div className="text-gray-500" title={String(owner || '')}>{shortId(String(owner || ''))}</div>
            </div>
          );
        },
      },
      {
        key: 'action',
        title: '操作',
        width: 260,
        align: 'center' as const,
        render: (_: unknown, job: Job) => (
          <div className="flex items-center justify-center gap-2">
            <Button variant="secondary" onClick={() => openRuns(job)} icon={<Clock size={14} />}>
              runs
            </Button>
            <Button variant="secondary" onClick={() => openDLQ(job)} icon={<Clock size={14} />}>
              DLQ
            </Button>
            <Button variant="secondary" onClick={() => openEdit(job)}>
              编辑
            </Button>
            <Button variant="secondary" onClick={() => runNow(job)} icon={<PlayCircle size={14} />}>
              触发
            </Button>
            <Button variant="secondary" onClick={() => toggleEnabled(job)} icon={job.enabled ? <PauseCircle size={14} /> : <PlayCircle size={14} />}>
              {job.enabled ? '停用' : '启用'}
            </Button>
            <Button variant="secondary" onClick={() => removeJob(job)} icon={<Trash2 size={14} />}>
              删除
            </Button>
          </div>
        ),
      },
    ],
    []
  );

  const dlqColumns = useMemo(
    () => [
      {
        key: 'id',
        title: 'id',
        width: 120,
        render: (_: unknown, r: any) => <code className="text-xs text-gray-400">{shortId(String(r.id || ''))}</code>,
      },
      { key: 'status', title: 'status', width: 90, render: (_: unknown, r: any) => <span className="text-gray-300">{String(r.status || '')}</span> },
      { key: 'attempts', title: 'attempts', width: 90, render: (_: unknown, r: any) => <span className="text-gray-400">{Number(r.attempts || 0)}</span> },
      { key: 'run_id', title: 'run_id', width: 140, render: (_: unknown, r: any) => <code className="text-xs text-gray-400">{shortId(String(r.run_id || ''))}</code> },
      { key: 'url', title: 'url', width: 220, render: (_: unknown, r: any) => <span className="text-gray-400">{String(r.url || '-')}</span> },
      { key: 'error', title: 'error', render: (_: unknown, r: any) => <span className="text-gray-400">{String(r.error || '-')}</span> },
      {
        key: 'action',
        title: '操作',
        width: 220,
        align: 'center' as const,
        render: (_: unknown, r: any) => (
          <div className="flex items-center justify-center gap-2">
            <Button size="sm" variant="secondary" onClick={() => retryDLQ(String(r.id))} disabled={dlqLoading || String(r.status) !== 'pending'}>
              重试
            </Button>
            <Button size="sm" variant="secondary" onClick={() => deleteDLQ(String(r.id))} disabled={dlqLoading}>
              删除
            </Button>
            {r.run_id ? (
              <Button
                size="sm"
                variant="secondary"
                icon={<ExternalLink size={14} />}
                onClick={() => window.open(`/diagnostics/links?execution_id=${encodeURIComponent(String(r.run_id))}`, '_blank', 'noopener,noreferrer')}
              >
                Links
              </Button>
            ) : null}
          </div>
        ),
      },
    ],
    [dlqLoading],
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Jobs / Cron"
        description={`定时任务调度（共 ${total} 条）`}
        extra={
          <div className="flex items-center gap-3">
            <Button icon={<Plus size={16} />} onClick={openCreate}>
              创建
            </Button>
            <Button icon={<RotateCw size={16} />} onClick={loadJobs} loading={loading}>
              刷新
            </Button>
          </div>
        }
      />

      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
        <Table columns={columns as any} data={jobs} rowKey="id" loading={loading} emptyText="暂无 Jobs" />
      </motion.div>

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="创建 Job"
        width={780}
        footer={
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              取消
            </Button>
            <Button variant="primary" onClick={submitCreate}>
              创建
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-xs text-gray-500 mr-1">模板：</div>
            <Button variant="secondary" onClick={() => applyTemplate('tool_calculator')}>
              Tool-Calculator
            </Button>
            <Button variant="secondary" onClick={() => applyTemplate('agent_basic')}>
              Agent（基础）
            </Button>
            <Button variant="secondary" onClick={() => applyTemplate('skill_basic')}>
              Skill（基础）
            </Button>
            <Button variant="secondary" onClick={() => applyTemplate('webhook_delivery')}>
              Webhook delivery
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-xs text-gray-500 mr-1">快捷设置：</div>
            <Button variant="secondary" onClick={() => setCron('*/1 * * * *')}>
              cron: 每分钟
            </Button>
            <Button variant="secondary" onClick={() => setCron('*/5 * * * *')}>
              cron: 每5分钟
            </Button>
            <Button variant="secondary" onClick={() => setCron('0 * * * *')}>
              cron: 每小时
            </Button>
            <Button variant="secondary" onClick={() => setCron('0 2 * * *')}>
              cron: 每天2点
            </Button>
            <span className="mx-1 text-gray-700">|</span>
            <Button variant="secondary" onClick={() => setToolsetQuick('safe_readonly')}>
              toolset: safe_readonly
            </Button>
            <Button variant="secondary" onClick={() => setToolsetQuick('workspace_default')}>
              toolset: workspace_default
            </Button>
            <Button variant="secondary" onClick={() => setToolsetQuick('full')}>
              toolset: full
            </Button>
          </div>
          <Input label="名称" value={name} onChange={(e: any) => setName(e.target.value)} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="text-sm font-medium text-gray-300 mb-2">kind</div>
              <select value={kind} onChange={(e) => setKind(e.target.value as any)} className="w-full h-10 px-3 bg-dark-card border border-dark-border rounded-lg text-sm text-gray-100">
                <option value="agent">agent</option>
                <option value="skill">skill</option>
                <option value="tool">tool</option>
                <option value="graph">graph</option>
              </select>
            </div>
            <div>
              <Input
                label={`target_id${targetsLoading ? '（加载中...）' : ''}`}
                value={targetId}
                list="job-target-datalist"
                onChange={(e: any) => setTargetId(e.target.value)}
                placeholder={kind === 'tool' ? '例如：calculator' : '例如：<id>'}
              />
              <datalist id="job-target-datalist">
                {targetSuggestions.map((x) => (
                  <option key={x.value} value={x.value}>
                    {x.label}
                  </option>
                ))}
              </datalist>
              <div className="text-xs text-gray-500 mt-1">提示：可手动输入，也可从浏览器下拉建议中选择</div>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input label="cron（5段）" value={cron} onChange={(e: any) => setCron(e.target.value)} />
            <Input label="user_id" value={userId} onChange={(e: any) => setUserId(e.target.value)} />
          </div>
          <Input label="session_id" value={sessionId} onChange={(e: any) => setSessionId(e.target.value)} />
          <Textarea label="payload（JSON）" rows={8} value={payloadText} onChange={(e: any) => setPayloadText(e.target.value)} />
          <Textarea label="options（JSON，可选）" rows={6} value={optionsText} onChange={(e: any) => setOptionsText(e.target.value)} />
          <Textarea label="delivery（JSON，可选；webhook）" rows={6} value={deliveryText} onChange={(e: any) => setDeliveryText(e.target.value)} />
        </div>
      </Modal>

      <Modal
        open={editOpen}
        onClose={() => setEditOpen(false)}
        title={`编辑 Job: ${selectedJob?.name || ''}`}
        width={780}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditOpen(false)}>
              取消
            </Button>
            <Button variant="primary" onClick={submitEdit}>
              保存
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-xs text-gray-500 mr-1">模板：</div>
            <Button variant="secondary" onClick={() => applyTemplate('tool_calculator')}>
              Tool-Calculator
            </Button>
            <Button variant="secondary" onClick={() => applyTemplate('agent_basic')}>
              Agent（基础）
            </Button>
            <Button variant="secondary" onClick={() => applyTemplate('skill_basic')}>
              Skill（基础）
            </Button>
            <Button variant="secondary" onClick={() => applyTemplate('webhook_delivery')}>
              Webhook delivery
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-xs text-gray-500 mr-1">快捷设置：</div>
            <Button variant="secondary" onClick={() => setCron('*/1 * * * *')}>
              cron: 每分钟
            </Button>
            <Button variant="secondary" onClick={() => setCron('*/5 * * * *')}>
              cron: 每5分钟
            </Button>
            <Button variant="secondary" onClick={() => setCron('0 * * * *')}>
              cron: 每小时
            </Button>
            <Button variant="secondary" onClick={() => setCron('0 2 * * *')}>
              cron: 每天2点
            </Button>
            <span className="mx-1 text-gray-700">|</span>
            <Button variant="secondary" onClick={() => setToolsetQuick('safe_readonly')}>
              toolset: safe_readonly
            </Button>
            <Button variant="secondary" onClick={() => setToolsetQuick('workspace_default')}>
              toolset: workspace_default
            </Button>
            <Button variant="secondary" onClick={() => setToolsetQuick('full')}>
              toolset: full
            </Button>
          </div>
          <Input label="名称" value={name} onChange={(e: any) => setName(e.target.value)} />
          <Input label="cron（5段）" value={cron} onChange={(e: any) => setCron(e.target.value)} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input label="user_id" value={userId} onChange={(e: any) => setUserId(e.target.value)} />
            <Input label="session_id" value={sessionId} onChange={(e: any) => setSessionId(e.target.value)} />
          </div>
          <div>
            <Input
              label={`target_id${targetsLoading ? '（加载中...）' : ''}`}
              value={targetId}
              list="job-target-datalist-edit"
              onChange={(e: any) => setTargetId(e.target.value)}
            />
            <datalist id="job-target-datalist-edit">
              {targetSuggestions.map((x) => (
                <option key={x.value} value={x.value}>
                  {x.label}
                </option>
              ))}
            </datalist>
            <div className="text-xs text-gray-500 mt-1">提示：可手动输入，也可从浏览器下拉建议中选择</div>
          </div>
          <Textarea label="payload（JSON）" rows={8} value={payloadText} onChange={(e: any) => setPayloadText(e.target.value)} />
          <Textarea label="options（JSON，可选）" rows={6} value={optionsText} onChange={(e: any) => setOptionsText(e.target.value)} />
          <Textarea label="delivery（JSON，可选；webhook）" rows={6} value={deliveryText} onChange={(e: any) => setDeliveryText(e.target.value)} />
        </div>
      </Modal>

      <Modal
        open={runsOpen}
        onClose={() => setRunsOpen(false)}
        title={`运行历史: ${selectedJob?.name || ''}`}
        width={980}
        footer={
          <>
            <Button variant="secondary" onClick={refreshRuns} disabled={!selectedJob}>
              刷新
            </Button>
            <Button variant="secondary" onClick={() => setRunsOpen(false)}>
              关闭
            </Button>
          </>
        }
      >
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-gray-500">
            <div>total: {runsTotal}</div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                disabled={runsOffset <= 0}
                onClick={() => {
                  const next = Math.max(0, runsOffset - runsLimit);
                  setRunsOffset(next);
                  setTimeout(refreshRuns, 0);
                }}
              >
                上一页
              </Button>
              <Button
                variant="secondary"
                disabled={runsOffset + runsLimit >= runsTotal}
                onClick={() => {
                  const next = runsOffset + runsLimit;
                  setRunsOffset(next);
                  setTimeout(refreshRuns, 0);
                }}
              >
                下一页
              </Button>
            </div>
          </div>
          {runs.length === 0 ? (
            <div className="text-sm text-gray-500">暂无运行记录</div>
          ) : (
            <div className="space-y-2">
              {runs.map((r) => (
                <div
                  key={r.id}
                  className={`border rounded-lg bg-dark-bg p-3 ${
                    highlightRunId && (String(r.id) === highlightRunId || String(r.run_id) === highlightRunId)
                      ? 'border-primary'
                      : 'border-dark-border'
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm text-gray-200">
                      <span className="font-medium">{r.status}</span>
                      <span className="text-xs text-gray-500 ml-2">run_id: {shortId(String(r.run_id || r.id))}</span>
                      <Button
                        variant="ghost"
                        icon={<Copy size={14} />}
                        onClick={async () => {
                          try {
                            await navigator.clipboard.writeText(String(r.run_id || r.id));
                            toast.success('已复制 run_id');
                          } catch {
                            toast.error('复制失败');
                          }
                        }}
                      />
                    </div>
                    <div className="flex items-center gap-2">
                      {r.trace_id && (
                        <>
                          <span className="text-xs text-gray-500">trace_id: {shortId(String(r.trace_id))}</span>
                          <Button
                            variant="ghost"
                            icon={<Copy size={14} />}
                            onClick={async () => {
                              try {
                                await navigator.clipboard.writeText(String(r.trace_id));
                                toast.success('已复制 trace_id');
                              } catch {
                                toast.error('复制失败');
                              }
                            }}
                          />
                        </>
                      )}
                      {r.trace_id ? (
                        <>
                          <Button
                            variant="secondary"
                            icon={<ExternalLink size={14} />}
                            onClick={() => window.open(`/diagnostics/links?trace_id=${encodeURIComponent(String(r.trace_id))}`, '_blank', 'noopener,noreferrer')}
                          >
                            Links
                          </Button>
                          <Button
                            variant="secondary"
                            icon={<ExternalLink size={14} />}
                            onClick={() => window.open(`/diagnostics/traces/${encodeURIComponent(String(r.trace_id))}`, '_blank', 'noopener,noreferrer')}
                          >
                            Trace详情
                          </Button>
                        </>
                      ) : (
                        <span className="text-xs text-gray-500">无 trace</span>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 text-xs text-gray-400">
                    <div>scheduled_for: {fmtTs(r.scheduled_for)}</div>
                    <div>started_at: {fmtTs(r.started_at)}</div>
                    <div>finished_at: {fmtTs(r.finished_at)}</div>
                  </div>
                  {r.error && <div className="mt-2 text-xs text-red-300">error: {r.error}</div>}
                  {r.result != null && (
                    <pre className="mt-2 text-xs text-gray-300 overflow-auto max-h-56 bg-dark-card border border-dark-border rounded-lg p-3">
                      {typeof r.result === 'string' ? r.result : JSON.stringify(r.result, null, 2)}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>

      <Modal
        open={dlqOpen}
        onClose={() => setDlqOpen(false)}
        title={`Delivery DLQ: ${selectedJob?.name || ''}`}
        width={1100}
        footer={
          <>
            <Button variant="secondary" onClick={loadDLQ} loading={dlqLoading}>
              刷新
            </Button>
            <Button variant="secondary" onClick={() => setDlqOpen(false)}>
              关闭
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="flex flex-wrap items-end gap-3">
            <Input label="job_id" value={selectedJob?.id || ''} onChange={() => {}} disabled />
            <Input
              label="status"
              value={dlqStatus}
              placeholder="pending/resolved"
              onChange={(e: any) => {
                setDlqOffset(0);
                setDlqStatus((e.target.value || '') as any);
              }}
            />
          </div>
          <div className="text-xs text-gray-500">提示：该列表展示 webhook delivery 多次失败后的死信记录，可手动重试或删除。</div>
          <div className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
            <Table columns={dlqColumns as any} data={dlqItems} rowKey="id" loading={dlqLoading} emptyText="暂无 DLQ 记录" />
          </div>
          <div className="flex items-center justify-between text-sm text-gray-400">
            <div>total: {dlqTotal}</div>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => setDlqOffset(Math.max(0, dlqOffset - dlqLimit))} disabled={dlqOffset <= 0}>
                上一页
              </Button>
              <Button variant="secondary" onClick={() => setDlqOffset(dlqOffset + dlqLimit)} disabled={dlqOffset + dlqLimit >= dlqTotal}>
                下一页
              </Button>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default Jobs;
