import { useEffect, useMemo, useState } from 'react';
import { Download, RefreshCw, Trash2, RotateCw } from 'lucide-react';
import { Button, Card, CardContent, CardHeader, Input, Table, toast } from '../../../components/ui';
import { gatewayDlqApi, jobApi, quotaApi } from '../../../services';

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
      const res = await jobApi.listDLQ({ status: 'pending', limit: 100, offset: 0 });
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
      const res = await gatewayDlqApi.list({ status: 'pending', limit: 100, offset: 0 });
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
    ],
    [tenantId, runId, candidateId, dayStart, dayEnd]
  );

  const jobsDlqColumns = useMemo(
    () => [
      { key: 'id', title: 'id', dataIndex: 'id', width: 140 },
      { key: 'job_id', title: 'job_id', dataIndex: 'job_id', width: 140 },
      { key: 'run_id', title: 'run_id', dataIndex: 'run_id', width: 160 },
      { key: 'attempts', title: 'attempts', dataIndex: 'attempts', width: 80 },
      { key: 'error', title: 'error', dataIndex: 'error' },
      {
        key: 'actions',
        title: '操作',
        width: 140,
        render: (_: any, r: any) => (
          <div className="flex items-center gap-2">
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
    []
  );

  const gwDlqColumns = useMemo(
    () => [
      { key: 'id', title: 'id', dataIndex: 'id', width: 160 },
      { key: 'connector', title: 'connector', dataIndex: 'connector', width: 110 },
      { key: 'tenant_id', title: 'tenant', dataIndex: 'tenant_id', width: 120 },
      { key: 'run_id', title: 'run_id', dataIndex: 'run_id', width: 160 },
      { key: 'attempts', title: 'attempts', dataIndex: 'attempts', width: 80 },
      { key: 'error', title: 'error', dataIndex: 'error' },
      {
        key: 'actions',
        title: '操作',
        width: 140,
        render: (_: any, r: any) => (
          <div className="flex items-center gap-2">
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
    []
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

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold text-gray-200">导出（CSV）</div>
            <Button
              variant="ghost"
              icon={<RefreshCw size={14} />}
              onClick={() => toast.info('提示', '导出会使用本地 active_tenant_id/actor headers 发起请求')}
            />
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {exports.map((ex) => {
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

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
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

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">DLQ</div>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} loading={jobsDlqLoading} onClick={loadJobsDlq}>
                  Jobs
                </Button>
                <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} loading={gwDlqLoading} onClick={loadGatewayDlq}>
                  Gateway
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <div className="text-xs text-gray-500 mb-2">Jobs delivery DLQ（pending）</div>
              <Table rowKey={(r: any) => String(r.id)} loading={jobsDlqLoading} data={jobsDlqItems} columns={jobsDlqColumns as any} />
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-2">Gateway/Connector delivery DLQ（pending）</div>
              <Table rowKey={(r: any) => String(r.id)} loading={gwDlqLoading} data={gwDlqItems} columns={gwDlqColumns as any} />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Ops;

