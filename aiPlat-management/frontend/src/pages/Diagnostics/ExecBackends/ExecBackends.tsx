import React, { useEffect, useMemo, useState } from 'react';
import { RefreshCw, ExternalLink } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Select, Table, toast } from '../../../components/ui';
import { diagnosticsApi, onboardingApi } from '../../../services/apiClient';
import { toastGateError } from '../../../utils/governanceError';

const ExecBackends: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<any>(null);
  const [metrics, setMetrics] = useState<any>(null);
  const [targetBackend, setTargetBackend] = useState('local');
  const [approvalRequestId, setApprovalRequestId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [res, m] = await Promise.all([diagnosticsApi.getExecBackends(), diagnosticsApi.getExecBackendMetricsSummary({ window_hours: 24, limit: 20 })]);
      setData(res);
      setMetrics(m);
      const cur = String(res?.current_backend || 'local');
      setTargetBackend(cur);
    } catch (e: any) {
      setData(null);
      toastGateError(e, '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const backends = Array.isArray(data?.backends) ? data.backends : [];
  const current = String(data?.current_backend || '-');
  const nonLocalRequiresApproval = !!data?.non_local_requires_approval;
  const metricItems = Array.isArray(metrics?.items) ? metrics.items : [];

  const backendOptions = useMemo(() => {
    const known = new Set<string>();
    for (const b of backends) {
      const id = String((b as any)?.driver_id || (b as any)?.backend || '').trim();
      if (id) known.add(id);
    }
    if (!known.size) {
      known.add('local');
      known.add('docker');
    }
    return Array.from(known).sort().map((x) => ({ label: x, value: x }));
  }, [backends]);

  const doSwitch = async (opts: { retryApproval?: boolean } = {}) => {
    try {
      const backend = String(targetBackend || '').trim();
      if (!backend) return;
      setLoading(true);
      const requireApproval = backend !== 'local' ? nonLocalRequiresApproval : false;
      const res: any = await onboardingApi.setExecBackend({
        backend,
        require_approval: requireApproval,
        approval_request_id: opts.retryApproval ? approvalRequestId : undefined,
        details: `switch exec backend to ${backend}`,
      });
      if (res?.status === 'approval_required' && res?.approval_request_id) {
        setApprovalRequestId(String(res.approval_request_id));
        toast.error(`需要审批：${String(res.approval_request_id)}`);
        try {
          window.open('/core/approvals', '_blank', 'noopener,noreferrer');
        } catch {
          // ignore
        }
        return;
      }
      setApprovalRequestId(null);
      toast.success('已提交切换');
      await load();
    } catch (e: any) {
      toastGateError(e, '切换失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Exec Backends</h1>
          <p className="text-sm text-gray-500 mt-1">当前执行后端与健康检查（用于排查非本地执行/沙箱/容器问题）</p>
        </div>
        <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={load} loading={loading}>
          刷新
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">current_backend</div>
          </CardHeader>
          <CardContent>
            <Badge variant={current === 'local' ? 'success' : 'warning'}>{current}</Badge>
            <div className="text-xs text-gray-500 mt-2">非 local 时通常需要更严格的审批/门禁。</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">non_local_requires_approval</div>
          </CardHeader>
          <CardContent>
            <Badge variant={nonLocalRequiresApproval ? 'warning' : 'default'}>{String(nonLocalRequiresApproval)}</Badge>
            <div className="text-xs text-gray-500 mt-2">当执行后端不是 local 时，默认建议强制审批。</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">快捷跳转</div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              <a className="inline-flex" href="/core/approvals">
                <Button variant="secondary" icon={<ExternalLink size={14} />}>
                  打开审批中心
                </Button>
              </a>
              <a className="inline-flex" href="/diagnostics/doctor">
                <Button variant="secondary" icon={<ExternalLink size={14} />}>
                  打开 Doctor
                </Button>
              </a>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">切换执行后端</div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col md:flex-row gap-3 md:items-center md:justify-between">
            <div className="flex items-center gap-2">
              <div className="text-xs text-gray-500">target_backend</div>
              <Select value={targetBackend} onChange={(v: any) => setTargetBackend(String(v))} options={backendOptions} />
              <div className="text-xs text-gray-500">
                {targetBackend !== 'local' && nonLocalRequiresApproval ? '非 local 默认强制审批' : '本地切换不强制审批'}
              </div>
            </div>
            <div className="flex items-center gap-2">
              {approvalRequestId ? (
                <Button variant="secondary" onClick={() => doSwitch({ retryApproval: true })} loading={loading}>
                  已申请审批，点此重试应用
                </Button>
              ) : null}
              <Button onClick={() => doSwitch()} loading={loading} disabled={!targetBackend || targetBackend === current}>
                应用切换
              </Button>
            </div>
          </div>
          <div className="text-xs text-gray-500 mt-2">
            注意：该操作会写入 global_setting.exec_backend；新请求会使用新后端，已在跑的任务不一定会迁移。
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">backends health</div>
        </CardHeader>
        <CardContent>
          <Table
            data={backends}
            loading={loading}
            rowKey={(r: any) => String(r.driver_id || r.backend || Math.random())}
            columns={[
              { key: 'driver_id', title: 'driver_id', dataIndex: 'driver_id', width: 160 },
              {
                key: 'ok',
                title: 'ok',
                dataIndex: 'ok',
                width: 90,
                render: (v: any) => <Badge variant={v ? 'success' : 'error'}>{String(!!v)}</Badge>,
              },
              { key: 'detail', title: 'detail', render: (_: any, r: any) => <span className="text-xs text-gray-300">{JSON.stringify(r)}</span> },
            ]}
            emptyText="暂无数据"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="text-sm font-semibold text-gray-200">backend metrics（24h）</div>
        </CardHeader>
        <CardContent>
          <Table
            data={metricItems}
            loading={loading}
            rowKey={(r: any) => String(r.exec_backend || Math.random())}
            columns={[
              { key: 'exec_backend', title: 'exec_backend', dataIndex: 'exec_backend', width: 140 },
              { key: 'success_rate', title: 'success_rate', dataIndex: 'success_rate', width: 120, render: (v: any) => <span className="text-xs text-gray-300">{v == null ? '-' : String(v)}</span> },
              { key: 'avg_latency_ms', title: 'avg_latency_ms', dataIndex: 'avg_latency_ms', width: 140, render: (v: any) => <span className="text-xs text-gray-300">{v == null ? '-' : String(v)}</span> },
              { key: 'policy_denied_count', title: 'policy_denied', dataIndex: 'policy_denied_count', width: 120 },
              { key: 'total_runs', title: 'total', dataIndex: 'total_runs', width: 90 },
              { key: 'ok_runs', title: 'ok', dataIndex: 'ok_runs', width: 80 },
              { key: 'failed_runs', title: 'failed', dataIndex: 'failed_runs', width: 90 },
              { key: 'done_runs', title: 'done', dataIndex: 'done_runs', width: 90 },
            ]}
            emptyText="暂无数据"
          />
        </CardContent>
      </Card>
    </div>
  );
};

export default ExecBackends;
