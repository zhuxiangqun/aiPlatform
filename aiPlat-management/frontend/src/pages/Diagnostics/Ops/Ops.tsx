import { useEffect, useMemo, useState } from 'react';
import { Download, RefreshCw, Trash2, RotateCw, Eye, Package, Activity } from 'lucide-react';
import { Button, Card, CardContent, CardHeader, Input, Table, toast, Tabs, Modal } from '../../../components/ui';
import { diagnosticsApi } from '../../../services';
import { gatewayDlqApi, jobApi, opsApi, quotaApi } from '../../../services';

type ExportButton = {
  label: string;
  path: string; // /core/... (under /api)
  params?: () => Record<string, any>;
  disabled?: () => boolean;
};

function getApiBaseUrl(): string {
  // keep consistent with apiClient.ts
  return (import.meta as any)?.env?.VITE_API_URL || '/api';
}

function getTenantHeaders(): Record<string, string> {
  const h: Record<string, string> = {};
  try {
    const tenantId = localStorage.getItem('active_tenant_id') || '';
    const actorId = localStorage.getItem('active_actor_id') || '';
    const actorRole = localStorage.getItem('active_actor_role') || '';
    if (tenantId.trim()) h['X-AIPLAT-TENANT-ID'] = tenantId.trim();
    if (actorId.trim()) h['X-AIPLAT-ACTOR-ID'] = actorId.trim();
    if (actorRole.trim()) h['X-AIPLAT-ACTOR-ROLE'] = actorRole.trim();
  } catch {
    // ignore
  }
  return h;
}

async function downloadCsv(endpoint: string, params: Record<string, any> = {}, filename?: string) {
  const q = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return;
    q.set(k, String(v));
  });
  const url = `${getApiBaseUrl()}${endpoint}${q.toString() ? `?${q.toString()}` : ''}`;
  const resp = await fetch(url, { method: 'GET', headers: { ...getTenantHeaders() } });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  const blob = await resp.blob();
  const a = document.createElement('a');
  const blobUrl = window.URL.createObjectURL(blob);
  a.href = blobUrl;
  a.download = filename || endpoint.split('/').pop() || 'export.csv';
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(blobUrl);
}

async function downloadZip(endpoint: string, params: Record<string, any> = {}, filename?: string) {
  const q = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return;
    q.set(k, String(v));
  });
  const url = `${getApiBaseUrl()}${endpoint}${q.toString() ? `?${q.toString()}` : ''}`;
  const resp = await fetch(url, { method: 'GET', headers: { ...getTenantHeaders() } });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error(txt || `HTTP ${resp.status}`);
  }
  const blob = await resp.blob();
  const a = document.createElement('a');
  const blobUrl = window.URL.createObjectURL(blob);
  a.href = blobUrl;
  a.download = filename || 'bundle.zip';
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(blobUrl);
}

const todayUtc = () => new Date().toISOString().slice(0, 10);

const Ops: React.FC = () => {
  const [tenantId, setTenantId] = useState<string>(() => localStorage.getItem('active_tenant_id') || '');
  const [runId, setRunId] = useState('');
  const [candidateId, setCandidateId] = useState('');
  const [dayStart, setDayStart] = useState(todayUtc());
  const [dayEnd, setDayEnd] = useState(todayUtc());

  // Quota
  const [quotaLoading, setQuotaLoading] = useState(false);
  const [quotaSnapshot, setQuotaSnapshot] = useState<any>(null);
  const [usageLoading, setUsageLoading] = useState(false);
  const [usageItems, setUsageItems] = useState<any[]>([]);

  // DLQ
  const [jobsDlqLoading, setJobsDlqLoading] = useState(false);
  const [jobsDlqItems, setJobsDlqItems] = useState<any[]>([]);
  const [gwDlqLoading, setGwDlqLoading] = useState(false);
  const [gwDlqItems, setGwDlqItems] = useState<any[]>([]);

  // Filters / selections / modal
  const [jobsDlqStatus, setJobsDlqStatus] = useState('pending');
  const [jobsDlqJobId, setJobsDlqJobId] = useState('');
  const [gwDlqStatus, setGwDlqStatus] = useState('pending');
  const [gwDlqTenant, setGwDlqTenant] = useState('');
  const [gwDlqConnector, setGwDlqConnector] = useState('');

  const [selectedJobsDlq, setSelectedJobsDlq] = useState<Record<string, boolean>>({});
  const [selectedGwDlq, setSelectedGwDlq] = useState<Record<string, boolean>>({});
  const [payloadModalOpen, setPayloadModalOpen] = useState(false);
  const [payloadModalTitle, setPayloadModalTitle] = useState('');
  const [payloadModalData, setPayloadModalData] = useState<any>(null);

  // Core health (via diagnosticsApi)
  const [coreHealthLoading, setCoreHealthLoading] = useState(false);
  const [coreHealth, setCoreHealth] = useState<any>(null);

  const loadQuota = async () => {
    if (!tenantId.trim()) {
      toast.error('请先填写 tenant_id');
      return;
    }
    setQuotaLoading(true);
    try {
      const res = await quotaApi.getSnapshot(tenantId.trim());
      setQuotaSnapshot(res);
    } catch (e: any) {
      setQuotaSnapshot(null);
      toast.error('加载 quota 失败', String(e?.message || ''));
    } finally {
      setQuotaLoading(false);
    }
  };

  const loadUsage = async () => {
    if (!tenantId.trim()) {
      toast.error('请先填写 tenant_id');
      return;
    }
    setUsageLoading(true);
    try {
      const res = await quotaApi.getUsage({
        tenant_id: tenantId.trim(),
        day_start: dayStart || undefined,
        day_end: dayEnd || undefined,
        limit: 200,
        offset: 0,
      });
      setUsageItems(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      setUsageItems([]);
      toast.error('加载 usage 失败', String(e?.message || ''));
    } finally {
      setUsageLoading(false);
    }
  };

  const loadJobsDlq = async () => {
    setJobsDlqLoading(true);
    try {
      const res = await jobApi.listDLQ({ status: jobsDlqStatus || 'pending', job_id: jobsDlqJobId || undefined, limit: 100, offset: 0 });
      setJobsDlqItems(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      setJobsDlqItems([]);
      toast.error('加载 Jobs DLQ 失败', String(e?.message || ''));
    } finally {
      setJobsDlqLoading(false);
    }
  };

  const loadGatewayDlq = async () => {
    setGwDlqLoading(true);
    try {
      const res = await gatewayDlqApi.list({
        status: gwDlqStatus || 'pending',
        connector: gwDlqConnector || undefined,
        tenant_id: gwDlqTenant || undefined,
        limit: 100,
        offset: 0,
      });
      setGwDlqItems(Array.isArray(res?.items) ? res.items : []);
    } catch (e: any) {
      setGwDlqItems([]);
      toast.error('加载 Gateway DLQ 失败', String(e?.message || ''));
    } finally {
      setGwDlqLoading(false);
    }
  };

  useEffect(() => {
    loadJobsDlq();
    loadGatewayDlq();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openPayload = (title: string, data: any) => {
    setPayloadModalTitle(title);
    setPayloadModalData(data);
    setPayloadModalOpen(true);
  };

  const loadCoreHealth = async () => {
    setCoreHealthLoading(true);
    try {
      const res = await diagnosticsApi.getHealth('core');
      setCoreHealth(res);
    } catch (e: any) {
      setCoreHealth(null);
      toast.error('加载 core health 失败', String(e?.message || ''));
    } finally {
      setCoreHealthLoading(false);
    }
  };

  const exports = useMemo<ExportButton[]>(
    () => [
      { label: '审计日志 audit_logs.csv', path: '/core/ops/export/audit_logs.csv', params: () => ({ tenant_id: tenantId, limit: 5000 }) },
      { label: 'Syscalls syscall_events.csv', path: '/core/ops/export/syscall_events.csv', params: () => ({ tenant_id: tenantId, limit: 5000 }) },
      { label: '审批 approvals.csv', path: '/core/ops/export/approvals.csv', params: () => ({ tenant_id: tenantId, limit: 5000 }) },
      { label: '用量 tenant_usage.csv', path: '/core/ops/export/tenant_usage.csv', params: () => ({ tenant_id: tenantId, day_start: dayStart, day_end: dayEnd, limit: 5000 }) },
      { label: 'Gateway DLQ gateway_dlq.csv', path: '/core/ops/export/gateway_dlq.csv', params: () => ({ tenant_id: tenantId, status: 'pending', limit: 5000 }) },
      { label: 'Connector attempts.csv', path: '/core/ops/export/connector_attempts.csv', params: () => ({ tenant_id: tenantId, limit: 5000 }) },
      { label: 'Jobs DLQ jobs_dlq.csv', path: '/core/ops/export/jobs_dlq.csv', params: () => ({ status: 'pending', limit: 5000 }) },
      { label: 'Job delivery attempts.csv', path: '/core/ops/export/job_delivery_attempts.csv', params: () => ({ run_id: runId || undefined, limit: 5000 }) },
      { label: 'Gateway tokens.csv', path: '/core/ops/export/gateway_tokens.csv', params: () => ({ limit: 5000 }) },
      { label: 'Gateway pairings.csv', path: '/core/ops/export/gateway_pairings.csv', params: () => ({ limit: 5000 }) },
      {
        label: 'Run events (需要 run_id)',
        path: '/core/ops/export/run_events.csv',
        params: () => ({ run_id: runId, limit: 5000 }),
        disabled: () => !runId.trim(),
      },
      { label: 'Release rollouts.csv', path: '/core/ops/export/release_rollouts.csv', params: () => ({ tenant_id: tenantId, limit: 5000 }), disabled: () => !tenantId.trim() },
      {
        label: 'Release metrics (需要 candidate_id)',
        path: '/core/ops/export/release_metrics.csv',
        params: () => ({ tenant_id: tenantId, candidate_id: candidateId, limit: 5000 }),
        disabled: () => !tenantId.trim() || !candidateId.trim(),
      },
      { label: 'Learning artifacts.csv', path: '/core/ops/export/learning_artifacts.csv', params: () => ({ kind: 'release_candidate', limit: 5000 }) },
      {
        label: '打包导出 bundle.zip（常用集合）',
        path: '/core/ops/export/bundle.zip',
        params: () => ({ tenant_id: tenantId, day_start: dayStart, day_end: dayEnd, run_id: runId || undefined, candidate_id: candidateId || undefined }),
        disabled: () => !tenantId.trim(),
      } as any,
    ],
    [tenantId, runId, candidateId, dayStart, dayEnd]
  );

  const jobsDlqColumns = useMemo(
    () => [
      {
        key: '_sel',
        title: '',
        width: 42,
        render: (_: any, r: any) => (
          <input
            type="checkbox"
            checked={!!selectedJobsDlq[String(r.id)]}
            onChange={(e) => setSelectedJobsDlq((prev) => ({ ...prev, [String(r.id)]: e.target.checked }))}
          />
        ),
      },
      { key: 'id', title: 'id', dataIndex: 'id', width: 140 },
      { key: 'job_id', title: 'job_id', dataIndex: 'job_id', width: 140 },
      { key: 'run_id', title: 'run_id', dataIndex: 'run_id', width: 160 },
      { key: 'attempts', title: 'attempts', dataIndex: 'attempts', width: 80 },
      { key: 'error', title: 'error', dataIndex: 'error' },
      {
        key: 'actions',
        title: '操作',
        width: 220,
        render: (_: any, r: any) => (
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="ghost"
              icon={<Eye size={14} />}
              onClick={(e: any) => {
                e?.stopPropagation?.();
                openPayload(`Jobs DLQ payload: ${r.id}`, { delivery: r.delivery, payload: r.payload });
              }}
            />
            <Button
              size="sm"
              variant="secondary"
              icon={<RotateCw size={14} />}
              onClick={async (e: any) => {
                e?.stopPropagation?.();
                try {
                  await jobApi.retryDLQ(String(r.id));
                  toast.success('已触发重试');
                  await loadJobsDlq();
                } catch (err: any) {
                  toast.error('重试失败', String(err?.message || ''));
                }
              }}
            >
              重试
            </Button>
            <Button
              size="sm"
              variant="ghost"
              icon={<Trash2 size={14} />}
              onClick={async (e: any) => {
                e?.stopPropagation?.();
                try {
                  await jobApi.deleteDLQ(String(r.id));
                  toast.success('已删除');
                  await loadJobsDlq();
                } catch (err: any) {
                  toast.error('删除失败', String(err?.message || ''));
                }
              }}
            />
          </div>
        ),
      },
    ],
    [selectedJobsDlq]
  );

  const gwDlqColumns = useMemo(
    () => [
      {
        key: '_sel',
        title: '',
        width: 42,
        render: (_: any, r: any) => (
          <input
            type="checkbox"
            checked={!!selectedGwDlq[String(r.id)]}
            onChange={(e) => setSelectedGwDlq((prev) => ({ ...prev, [String(r.id)]: e.target.checked }))}
          />
        ),
      },
      { key: 'id', title: 'id', dataIndex: 'id', width: 160 },
      { key: 'connector', title: 'connector', dataIndex: 'connector', width: 110 },
      { key: 'tenant_id', title: 'tenant', dataIndex: 'tenant_id', width: 120 },
      { key: 'run_id', title: 'run_id', dataIndex: 'run_id', width: 160 },
      { key: 'attempts', title: 'attempts', dataIndex: 'attempts', width: 80 },
      { key: 'error', title: 'error', dataIndex: 'error' },
      {
        key: 'actions',
        title: '操作',
        width: 220,
        render: (_: any, r: any) => (
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="ghost"
              icon={<Eye size={14} />}
              onClick={(e: any) => {
                e?.stopPropagation?.();
                openPayload(`Gateway DLQ payload: ${r.id}`, { url: r.url, payload: r.payload });
              }}
            />
            <Button
              size="sm"
              variant="secondary"
              icon={<RotateCw size={14} />}
              onClick={async (e: any) => {
                e?.stopPropagation?.();
                try {
                  await gatewayDlqApi.retry(String(r.id));
                  toast.success('已触发重试');
                  await loadGatewayDlq();
                } catch (err: any) {
                  toast.error('重试失败', String(err?.message || ''));
                }
              }}
            >
              重试
            </Button>
            <Button
              size="sm"
              variant="ghost"
              icon={<Trash2 size={14} />}
              onClick={async (e: any) => {
                e?.stopPropagation?.();
                try {
                  await gatewayDlqApi.delete(String(r.id));
                  toast.success('已删除');
                  await loadGatewayDlq();
                } catch (err: any) {
                  toast.error('删除失败', String(err?.message || ''));
                }
              }}
            />
          </div>
        ),
      },
    ],
    [selectedGwDlq]
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-200">运维控制台</h1>
        <p className="text-sm text-gray-500 mt-1">导出（CSV）/ DLQ / 配额用量</p>
      </div>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">上下文</div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <div className="text-xs text-gray-500 mb-1">tenant_id（用于导出/用量/发布证据链）</div>
              <Input value={tenantId} onChange={(e) => setTenantId(e.target.value)} placeholder="t_xxx" />
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">run_id（用于 run_events / job_delivery_attempts）</div>
              <Input value={runId} onChange={(e) => setRunId(e.target.value)} placeholder="run_xxx" />
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">candidate_id（用于 release_metrics）</div>
              <Input value={candidateId} onChange={(e) => setCandidateId(e.target.value)} placeholder="cand_xxx" />
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
            <div>
              <div className="text-xs text-gray-500 mb-1">day_start（UTC）</div>
              <Input value={dayStart} onChange={(e) => setDayStart(e.target.value)} placeholder="YYYY-MM-DD" />
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">day_end（UTC）</div>
              <Input value={dayEnd} onChange={(e) => setDayEnd(e.target.value)} placeholder="YYYY-MM-DD" />
            </div>
          </div>
        </CardContent>
      </Card>

      <Tabs
        defaultActiveKey="exports"
        tabs={[
          {
            key: 'exports',
            label: '导出',
            children: (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-semibold text-gray-200">导出（CSV / ZIP）</div>
                    <Button
                      variant="ghost"
                      icon={<RefreshCw size={14} />}
                      onClick={() => toast.info('提示', '导出会使用本地 active_tenant_id/actor headers 发起请求')}
                    />
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-2 mb-3">
                    <Button
                      size="sm"
                      variant="secondary"
                      icon={<Package size={14} />}
                      disabled={!tenantId.trim()}
                      onClick={async () => {
                        try {
                          await downloadZip(
                            '/core/ops/export/bundle.zip',
                            { tenant_id: tenantId, day_start: dayStart, day_end: dayEnd, run_id: runId || undefined, candidate_id: candidateId || undefined },
                            `ops_bundle_${tenantId || 'tenant'}.zip`
                          );
                          toast.success('已开始下载 bundle.zip');
                        } catch (e: any) {
                          toast.error('打包导出失败', String(e?.message || ''));
                        }
                      }}
                    >
                      打包导出（bundle.zip）
                    </Button>
                    <div className="text-xs text-gray-500">tenant_id 必填；run_id/candidate_id 可选</div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                    {exports
                      .filter((e) => !String(e.path).endsWith('bundle.zip'))
                      .map((ex) => {
                        const disabled = ex.disabled?.() || false;
                        return (
                          <Button
                            key={ex.path + ex.label}
                            variant="secondary"
                            icon={<Download size={14} />}
                            disabled={disabled}
                            onClick={async () => {
                              try {
                                await downloadCsv(ex.path, ex.params ? ex.params() : {});
                                toast.success('已开始下载');
                              } catch (e: any) {
                                toast.error('导出失败', String(e?.message || ''));
                              }
                            }}
                          >
                            {ex.label}
                          </Button>
                        );
                      })}
                  </div>
                </CardContent>
              </Card>
            ),
          },
          {
            key: 'dlq',
            label: 'DLQ',
            children: (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-semibold text-gray-200">DLQ（含批量操作与 payload 查看）</div>
                    <div className="flex items-center gap-2">
                      <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} loading={jobsDlqLoading} onClick={loadJobsDlq}>
                        刷新 Jobs
                      </Button>
                      <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} loading={gwDlqLoading} onClick={loadGatewayDlq}>
                        刷新 Gateway
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div>
                    <div className="flex items-end gap-3 mb-2">
                      <div className="flex-1">
                        <div className="text-xs text-gray-500 mb-1">Jobs DLQ status</div>
                        <Input value={jobsDlqStatus} onChange={(e) => setJobsDlqStatus(e.target.value)} placeholder="pending/resolved" />
                      </div>
                      <div className="flex-1">
                        <div className="text-xs text-gray-500 mb-1">job_id（可选）</div>
                        <Input value={jobsDlqJobId} onChange={(e) => setJobsDlqJobId(e.target.value)} placeholder="job_xxx" />
                      </div>
                      <Button size="sm" variant="secondary" onClick={loadJobsDlq}>
                        查询
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={Object.keys(selectedJobsDlq).filter((k) => selectedJobsDlq[k]).length === 0}
                        onClick={async () => {
                          const ids = Object.keys(selectedJobsDlq).filter((k) => selectedJobsDlq[k]);
                          for (const id of ids) {
                            try {
                              await jobApi.retryDLQ(id);
                            } catch {}
                          }
                          toast.success(`已触发批量重试：${ids.length} 条`);
                          setSelectedJobsDlq({});
                          await loadJobsDlq();
                        }}
                      >
                        批量重试
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={Object.keys(selectedJobsDlq).filter((k) => selectedJobsDlq[k]).length === 0}
                        onClick={async () => {
                          const ids = Object.keys(selectedJobsDlq).filter((k) => selectedJobsDlq[k]);
                          for (const id of ids) {
                            try {
                              await jobApi.deleteDLQ(id);
                            } catch {}
                          }
                          toast.success(`已批量删除：${ids.length} 条`);
                          setSelectedJobsDlq({});
                          await loadJobsDlq();
                        }}
                      >
                        批量删除
                      </Button>
                    </div>
                    <div className="text-xs text-gray-500 mb-2">Jobs delivery DLQ</div>
                    <Table rowKey={(r: any) => String(r.id)} loading={jobsDlqLoading} data={jobsDlqItems} columns={jobsDlqColumns as any} />
                  </div>

                  <div>
                    <div className="flex items-end gap-3 mb-2">
                      <div className="flex-1">
                        <div className="text-xs text-gray-500 mb-1">Gateway DLQ status</div>
                        <Input value={gwDlqStatus} onChange={(e) => setGwDlqStatus(e.target.value)} placeholder="pending/resolved" />
                      </div>
                      <div className="flex-1">
                        <div className="text-xs text-gray-500 mb-1">tenant_id（可选）</div>
                        <Input value={gwDlqTenant} onChange={(e) => setGwDlqTenant(e.target.value)} placeholder="t_xxx" />
                      </div>
                      <div className="flex-1">
                        <div className="text-xs text-gray-500 mb-1">connector（可选）</div>
                        <Input value={gwDlqConnector} onChange={(e) => setGwDlqConnector(e.target.value)} placeholder="slack/feishu/..." />
                      </div>
                      <Button size="sm" variant="secondary" onClick={loadGatewayDlq}>
                        查询
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={Object.keys(selectedGwDlq).filter((k) => selectedGwDlq[k]).length === 0}
                        onClick={async () => {
                          const ids = Object.keys(selectedGwDlq).filter((k) => selectedGwDlq[k]);
                          for (const id of ids) {
                            try {
                              await gatewayDlqApi.retry(id);
                            } catch {}
                          }
                          toast.success(`已触发批量重试：${ids.length} 条`);
                          setSelectedGwDlq({});
                          await loadGatewayDlq();
                        }}
                      >
                        批量重试
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={Object.keys(selectedGwDlq).filter((k) => selectedGwDlq[k]).length === 0}
                        onClick={async () => {
                          const ids = Object.keys(selectedGwDlq).filter((k) => selectedGwDlq[k]);
                          for (const id of ids) {
                            try {
                              await gatewayDlqApi.delete(id);
                            } catch {}
                          }
                          toast.success(`已批量删除：${ids.length} 条`);
                          setSelectedGwDlq({});
                          await loadGatewayDlq();
                        }}
                      >
                        批量删除
                      </Button>
                    </div>
                    <div className="text-xs text-gray-500 mb-2">Gateway/Connector delivery DLQ</div>
                    <Table rowKey={(r: any) => String(r.id)} loading={gwDlqLoading} data={gwDlqItems} columns={gwDlqColumns as any} />
                  </div>
                </CardContent>
              </Card>
            ),
          },
          {
            key: 'quota',
            label: '配额/用量',
            children: (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-semibold text-gray-200">Quota / Usage</div>
                    <div className="flex items-center gap-2">
                      <Button size="sm" variant="secondary" loading={quotaLoading} onClick={loadQuota}>
                        quota snapshot
                      </Button>
                      <Button size="sm" variant="secondary" loading={usageLoading} onClick={loadUsage}>
                        usage
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="text-xs text-gray-500 mb-2">quota snapshot</div>
                  <pre className="text-xs bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto max-h-60">
                    {quotaSnapshot ? JSON.stringify(quotaSnapshot, null, 2) : '—'}
                  </pre>
                  <div className="text-xs text-gray-500 mt-4 mb-2">usage（按天/指标）</div>
                  <Table
                    rowKey={(r: any) => `${r.tenant_id}-${r.day}-${r.metric_key}`}
                    loading={usageLoading}
                    data={usageItems}
                    columns={[
                      { key: 'day', title: 'day', dataIndex: 'day', width: 120 },
                      { key: 'metric_key', title: 'metric', dataIndex: 'metric_key', width: 160 },
                      { key: 'value', title: 'value', dataIndex: 'value', width: 100 },
                      { key: 'updated_at', title: 'updated_at', dataIndex: 'updated_at' },
                    ]}
                  />
                </CardContent>
              </Card>
            ),
          },
          {
            key: 'actions',
            label: '运维动作',
            children: (
              <Card>
                <CardHeader>
                  <div className="text-sm font-semibold text-gray-200">运维动作</div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      variant="secondary"
                      icon={<Activity size={14} />}
                      loading={coreHealthLoading}
                      onClick={loadCoreHealth}
                    >
                      刷新 core health
                    </Button>
                    <Button
                      variant="secondary"
                      icon={<Trash2 size={14} />}
                      onClick={async () => {
                        try {
                          await opsApi.prune({});
                          toast.success('已触发 prune');
                        } catch (e: any) {
                          toast.error('触发 prune 失败', String(e?.message || ''));
                        }
                      }}
                    >
                      立即 prune
                    </Button>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 mb-2">core health（来自 /diagnostics/health/core）</div>
                    <pre className="text-xs bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto max-h-80">
                      {coreHealth ? JSON.stringify(coreHealth, null, 2) : '—'}
                    </pre>
                  </div>
                </CardContent>
              </Card>
            ),
          },
        ]}
      />

      <Modal
        open={payloadModalOpen}
        onClose={() => setPayloadModalOpen(false)}
        title={payloadModalTitle || 'Payload'}
        width={900}
      >
        <pre className="text-xs bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto max-h-[70vh]">
          {payloadModalData ? JSON.stringify(payloadModalData, null, 2) : '—'}
        </pre>
      </Modal>
    </div>
  );
};

export default Ops;
