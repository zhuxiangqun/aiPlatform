import React, { useState } from 'react';
import { diagnosticsApi } from '../../../services';
import { Button, Card, CardContent, CardHeader, Input, Select, Textarea, toast, Badge } from '../../../components/ui';

const Smoke: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [tenantId, setTenantId] = useState('ops_smoke');
  const [actorId, setActorId] = useState('admin');
  const [agentModel, setAgentModel] = useState('deepseek-reasoner');
  const [extraJson, setExtraJson] = useState('');
  const [result, setResult] = useState<any>(null);

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

