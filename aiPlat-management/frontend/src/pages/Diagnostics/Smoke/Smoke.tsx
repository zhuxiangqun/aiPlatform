import React, { useMemo, useState } from 'react';
import { diagnosticsApi, onboardingApi } from '../../../services';
import { Button, Card, CardContent, CardHeader, Input, Select, Textarea, toast, Badge, Table } from '../../../components/ui';

const Smoke: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [tenantId, setTenantId] = useState('ops_smoke');
  const [actorId, setActorId] = useState('admin');
  const [agentModel, setAgentModel] = useState('deepseek-reasoner');
  const [extraJson, setExtraJson] = useState('');
  const [result, setResult] = useState<any>(null);

  // AutoSmoke (resource-scoped)
  const [asType, setAsType] = useState<'agent' | 'skill' | 'mcp'>('agent');
  const [asId, setAsId] = useState('');
  const [asLoading, setAsLoading] = useState(false);
  const [asStatus, setAsStatus] = useState<any>(null);
  const [asRuns, setAsRuns] = useState<any>(null);

  const run = async () => {
    setLoading(true);
    setResult(null);
    try {
      let extra: any = {};
      if (extraJson.trim()) {
        try {
          extra = JSON.parse(extraJson);
        } catch {
          toast.error('extra 不是合法 JSON');
          setLoading(false);
          return;
        }
      }
      const res = await diagnosticsApi.runE2ESmoke({
        tenant_id: tenantId,
        actor_id: actorId,
        agent_model: agentModel,
        ...extra,
      });
      setResult(res);
      toast.success(res?.ok ? '冒烟通过' : '冒烟失败');
    } catch (e: any) {
      toast.error('冒烟失败', String(e?.message || 'unknown'));
      setResult({ ok: false, error: String(e?.message || e) });
    } finally {
      setLoading(false);
    }
  };

  const badgeVariant = (ok: any) => (ok === true ? 'success' : ok === false ? 'error' : 'default');

  const loadAutosmoke = async () => {
    if (!asId.trim()) {
      toast.error('请填写 resource_id');
      return;
    }
    setAsLoading(true);
    try {
      const st = await onboardingApi.autosmokeStatus({ resource_type: asType, resource_id: asId.trim() });
      const runs = await onboardingApi.autosmokeRuns({ resource_type: asType, resource_id: asId.trim(), limit: 50, offset: 0 });
      setAsStatus(st);
      setAsRuns(runs);
    } catch (e: any) {
      toast.error('加载 autosmoke 失败', String(e?.message || 'unknown'));
      setAsStatus(null);
      setAsRuns(null);
    } finally {
      setAsLoading(false);
    }
  };

  const triggerAutosmoke = async () => {
    if (!asId.trim()) {
      toast.error('请填写 resource_id');
      return;
    }
    setAsLoading(true);
    try {
      const res = await onboardingApi.autosmokeRun({
        resource_type: asType,
        resource_id: asId.trim(),
        tenant_id: tenantId,
        actor_id: actorId,
        detail: { source: 'diagnostics_smoke' },
      });
      toast.success(res?.enqueued ? '已触发 autosmoke' : `未触发：${res?.reason || 'unknown'}`);
      await loadAutosmoke();
    } catch (e: any) {
      toast.error('触发失败', String(e?.message || 'unknown'));
    } finally {
      setAsLoading(false);
    }
  };

  const runColumns = useMemo(
    () => [
      { key: 'id', title: 'job_run_id', dataIndex: 'id', width: 180 },
      { key: 'status', title: 'status', dataIndex: 'status', width: 110 },
      { key: 'created_at', title: 'created_at', dataIndex: 'created_at', width: 120 },
      { key: 'started_at', title: 'started_at', dataIndex: 'started_at', width: 120 },
      { key: 'finished_at', title: 'finished_at', dataIndex: 'finished_at', width: 120 },
      {
        key: 'links',
        title: 'links',
        width: 220,
        render: (_: any, r: any) => (
          <div className="flex items-center gap-2 text-xs">
            {r?.links?.run_ui ? (
              <a className="underline text-gray-300 hover:text-white" href={r.links.run_ui} target="_blank" rel="noreferrer">
                Run
              </a>
            ) : null}
            {r?.links?.syscalls_ui ? (
              <a className="underline text-gray-300 hover:text-white" href={r.links.syscalls_ui} target="_blank" rel="noreferrer">
                Syscalls
              </a>
            ) : null}
            {r?.links?.audit_ui ? (
              <a className="underline text-gray-300 hover:text-white" href={r.links.audit_ui} target="_blank" rel="noreferrer">
                Audit
              </a>
            ) : null}
          </div>
        ),
      },
    ],
    []
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-200">全链路冒烟</h1>
        <p className="text-sm text-gray-500 mt-1">生产级 E2E：创建→执行→审计→立即清理（best-effort）</p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold text-gray-200">运行参数</div>
            <Button variant="primary" onClick={run} loading={loading}>
              立即运行
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Input label="tenant_id" value={tenantId} onChange={(e: any) => setTenantId(e.target.value)} />
            <Input label="actor_id" value={actorId} onChange={(e: any) => setActorId(e.target.value)} />
            <Select
              value={agentModel}
              onChange={(v) => setAgentModel(v || 'deepseek-reasoner')}
              options={[
                { value: 'deepseek-reasoner', label: 'deepseek-reasoner（推理）' },
                { value: 'deepseek-chat', label: 'deepseek-chat（对话）' },
              ]}
              placeholder="agent_model"
            />
          </div>

          <div className="mt-4">
            <Textarea
              label="extra（可选 JSON）"
              rows={4}
              value={extraJson}
              onChange={(e: any) => setExtraJson(e.target.value)}
              placeholder='例如：{"timeout_s": 60}'
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold text-gray-200">AutoSmoke（资源级历史/手动触发）</div>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={loadAutosmoke} loading={asLoading}>
                刷新
              </Button>
              <Button variant="primary" onClick={triggerAutosmoke} loading={asLoading}>
                触发 autosmoke
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Select
              value={asType}
              onChange={(v) => setAsType((v as any) || 'agent')}
              options={[
                { value: 'agent', label: 'agent' },
                { value: 'skill', label: 'skill' },
                { value: 'mcp', label: 'mcp' },
              ]}
              placeholder="resource_type"
            />
            <Input label="resource_id" value={asId} onChange={(e: any) => setAsId(e.target.value)} placeholder="例如：a-xxx / s-xxx / mcp-server-id" />
            <Input label="job_id（派生）" value={asRuns?.job_id || ''} onChange={() => {}} disabled />
          </div>

          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-dark-card border border-dark-border rounded-lg p-3">
              <div className="text-sm text-gray-200 font-medium mb-2">verification</div>
              <pre className="text-xs text-gray-300 overflow-auto max-h-[240px]">{JSON.stringify(asStatus?.verification || null, null, 2)}</pre>
            </div>
            <div className="bg-dark-card border border-dark-border rounded-lg p-3">
              <div className="text-sm text-gray-200 font-medium mb-2">latest_run</div>
              <pre className="text-xs text-gray-300 overflow-auto max-h-[240px]">{JSON.stringify(asStatus?.latest_run || null, null, 2)}</pre>
            </div>
          </div>

          <div className="mt-4">
            <div className="text-sm text-gray-200 font-medium mb-2">runs</div>
            <Table
              rowKey={(r: any) => String(r.id)}
              loading={asLoading}
              data={asRuns?.items || []}
              columns={runColumns as any}
              emptyText="暂无 runs（可能尚未触发 autosmoke）"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold text-gray-200">执行结果</div>
            <Badge variant={badgeVariant(result?.ok)}>{result?.ok === true ? 'pass' : result?.ok === false ? 'fail' : '—'}</Badge>
          </div>
        </CardHeader>
        <CardContent>
          {result ? (
            <pre className="text-xs text-gray-300 overflow-auto max-h-[520px] bg-dark-card border border-dark-border rounded-lg p-3">
              {JSON.stringify(result, null, 2)}
            </pre>
          ) : (
            <div className="text-sm text-gray-500">尚未运行</div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default Smoke;
