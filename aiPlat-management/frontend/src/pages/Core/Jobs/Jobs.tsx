import React, { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Plus, RotateCw, PlayCircle, PauseCircle, Trash2, Clock, ExternalLink, Copy } from 'lucide-react';
import PageHeader from '../../../components/common/PageHeader';
import { Button, Modal, Input, Textarea, toast, Table } from '../../../components/ui';
import { jobApi, type Job, type JobRun } from '../../../services';

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
            <Input label="target_id" value={targetId} onChange={(e: any) => setTargetId(e.target.value)} />
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
          <Input label="名称" value={name} onChange={(e: any) => setName(e.target.value)} />
          <Input label="cron（5段）" value={cron} onChange={(e: any) => setCron(e.target.value)} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input label="user_id" value={userId} onChange={(e: any) => setUserId(e.target.value)} />
            <Input label="session_id" value={sessionId} onChange={(e: any) => setSessionId(e.target.value)} />
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
                        <Button
                          variant="secondary"
                          icon={<ExternalLink size={14} />}
                          onClick={() => window.open(`/diagnostics/links?trace_id=${encodeURIComponent(String(r.trace_id))}`, '_blank', 'noopener,noreferrer')}
                        >
                          Links
                        </Button>
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
    </div>
  );
};

export default Jobs;
