import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Copy, Download, RotateCw } from 'lucide-react';
import { Button, Card, CardContent, CardHeader, Input, Select, Textarea, toast, Badge } from '../../../components/ui';
import { policyApi } from '../../../services';
import { toastGateError } from '../../../utils/governanceError';

const PolicyDebug: React.FC = () => {
  const [kind, setKind] = useState<'tool' | 'mcp_server'>('tool');
  const [tenantId, setTenantId] = useState('t1');
  const [actorId, setActorId] = useState('admin');
  const [actorRole, setActorRole] = useState('operator');
  const [toolName, setToolName] = useState('file_operations');
  const [toolArgsText, setToolArgsText] = useState('{\n  "_risk_level": "high"\n}\n');
  const [serverName, setServerName] = useState('example');
  const [transport, setTransport] = useState<'sse' | 'http' | 'stdio'>('sse');
  const [serverMetaText, setServerMetaText] = useState('{\n  "prod_allowed": false\n}\n');
  const [loading, setLoading] = useState(false);
  const [out, setOut] = useState<any | null>(null);

  const badge = useMemo(() => {
    const d = String(out?.final_decision || '').toLowerCase();
    if (d === 'allow') return 'success';
    if (d === 'approval_required') return 'warning';
    if (d === 'deny') return 'error';
    return 'default';
  }, [out]);

  const downloadJson = (filename: string, obj: any) => {
    try {
      const blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      toastGateError(e, '导出失败');
    }
  };

  const run = async () => {
    setLoading(true);
    try {
      const body: any = {
        kind,
        tenant_id: tenantId || undefined,
        actor_id: actorId || undefined,
        actor_role: actorRole || undefined,
      };
      if (kind === 'tool') {
        body.tool_name = toolName;
        try {
          body.tool_args = JSON.parse(toolArgsText || '{}');
        } catch {
          toast.error('tool_args 不是合法 JSON');
          return;
        }
      } else {
        body.server_name = serverName;
        body.transport = transport;
        try {
          body.server_metadata = JSON.parse(serverMetaText || '{}');
        } catch {
          toast.error('server_metadata 不是合法 JSON');
          return;
        }
      }
      const res = await policyApi.evaluate(body);
      setOut(res);
      toast.success('评估完成');
    } catch (e: any) {
      setOut(null);
      toastGateError(e, '评估失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Policy 调试</h1>
          <p className="text-sm text-gray-500 mt-1">输入 tenant/actor/目标，查看 RBAC + policy engine 的决策与解释</p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/diagnostics">
            <Button variant="secondary" icon={<ArrowLeft size={16} />}>
              返回
            </Button>
          </Link>
          <Button variant="secondary" icon={<RotateCw size={16} />} onClick={run} loading={loading}>
            评估
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold text-gray-200">输入</div>
            <Badge variant={badge as any}>{out?.final_decision || '—'}</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Select
              value={kind}
              onChange={(v) => setKind((v as any) || 'tool')}
              options={[
                { value: 'tool', label: 'tool' },
                { value: 'mcp_server', label: 'mcp_server' },
              ]}
              placeholder="kind"
            />
            <Input label="tenant_id" value={tenantId} onChange={(e: any) => setTenantId(e.target.value)} />
            <Input label="actor_id" value={actorId} onChange={(e: any) => setActorId(e.target.value)} />
            <Input label="actor_role" value={actorRole} onChange={(e: any) => setActorRole(e.target.value)} placeholder="admin/operator/developer/viewer" />
          </div>

          {kind === 'tool' ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
              <Input label="tool_name" value={toolName} onChange={(e: any) => setToolName(e.target.value)} />
              <Textarea label="tool_args (JSON)" value={toolArgsText} onChange={(e: any) => setToolArgsText(e.target.value)} rows={10} />
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
              <Input label="server_name" value={serverName} onChange={(e: any) => setServerName(e.target.value)} />
              <Select
                value={transport}
                onChange={(v) => setTransport((v as any) || 'sse')}
                options={[
                  { value: 'sse', label: 'sse' },
                  { value: 'http', label: 'http' },
                  { value: 'stdio', label: 'stdio' },
                ]}
                placeholder="transport"
              />
              <div className="md:col-span-2">
                <Textarea label="server_metadata (JSON)" value={serverMetaText} onChange={(e: any) => setServerMetaText(e.target.value)} rows={10} />
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-semibold text-gray-200">输出</div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                icon={<Copy size={14} />}
                onClick={() => {
                  if (!out) return;
                  navigator.clipboard.writeText(JSON.stringify(out, null, 2));
                  toast.success('已复制 JSON');
                }}
                disabled={!out}
              >
                复制
              </Button>
              <Button variant="secondary" icon={<Download size={14} />} onClick={() => downloadJson('policy_eval.json', out)} disabled={!out}>
                导出
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <pre className="text-xs text-gray-300 bg-dark-card border border-dark-border rounded-lg p-3 overflow-auto max-h-[520px]">
            {out ? JSON.stringify(out, null, 2) : '—'}
          </pre>
        </CardContent>
      </Card>
    </div>
  );
};

export default PolicyDebug;
