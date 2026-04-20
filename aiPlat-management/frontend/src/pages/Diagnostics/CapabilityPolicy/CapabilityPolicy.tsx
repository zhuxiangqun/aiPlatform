import React, { useEffect, useMemo, useState } from 'react';
import { RefreshCw, Save, Search, PlusCircle } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Table, Textarea, toast } from '../../../components/ui';
import { policyApi, skillApi, workspaceSkillApi } from '../../../services';
import { toastGateError } from '../../../utils/governanceError';

type ToolAgg = { tool: string; count: number; examples: Array<{ scope: string; skill_id: string; name: string }> };

function uniq(arr: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const x of arr) {
    const s = String(x || '').trim();
    if (!s) continue;
    if (seen.has(s)) continue;
    seen.add(s);
    out.push(s);
  }
  return out;
}

function parsePolicy(text: string): any | null {
  try {
    return JSON.parse(text || '{}');
  } catch {
    return null;
  }
}

function extractToolsFromCapabilities(caps: any): string[] {
  // Convention:
  // - "tool:<tool_name>" -> map directly to tool_policy lists
  const out: string[] = [];
  const arr: any[] = Array.isArray(caps) ? caps : typeof caps === 'string' ? [caps] : [];
  for (const c of arr) {
    const s = String(c || '').trim();
    if (!s) continue;
    if (s.startsWith('tool:')) {
      const t = s.slice('tool:'.length).trim();
      if (t) out.push(t);
    }
  }
  return uniq(out);
}

const CapabilityPolicy: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [skills, setSkills] = useState<any[]>([]);
  const [tenantId, setTenantId] = useState('');
  const [version, setVersion] = useState<number | undefined>(undefined);
  const [policyText, setPolicyText] = useState('{\n  "tool_policy": {\n    "deny_tools": [],\n    "approval_required_tools": []\n  }\n}\n');

  const loadSkills = async () => {
    setLoading(true);
    try {
      const [core, ws] = await Promise.all([
        skillApi.list({ limit: 300, offset: 0 }),
        workspaceSkillApi.list({ limit: 300, offset: 0 }),
      ]);
      const coreItems = (core?.skills || []).map((s: any) => ({ ...s, scope: 'core' }));
      const wsItems = (ws?.skills || []).map((s: any) => ({ ...s, scope: 'workspace' }));
      setSkills([...coreItems, ...wsItems]);
    } catch (e: any) {
      setSkills([]);
      toastGateError(e, '加载 skills 失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSkills();
  }, []);

  const tools: ToolAgg[] = useMemo(() => {
    const m = new Map<string, ToolAgg>();
    for (const s of skills) {
      const caps = (s?.metadata as any)?.capabilities;
      const ts = extractToolsFromCapabilities(caps);
      for (const t of ts) {
        if (!m.has(t)) m.set(t, { tool: t, count: 0, examples: [] });
        const agg = m.get(t)!;
        agg.count += 1;
        if (agg.examples.length < 6) {
          agg.examples.push({ scope: String(s.scope || ''), skill_id: String(s.id || ''), name: String(s.name || '') });
        }
      }
    }
    return Array.from(m.values()).sort((a, b) => b.count - a.count);
  }, [skills]);

  const policyObj = useMemo(() => parsePolicy(policyText), [policyText]);
  const approvalTools: string[] = useMemo(() => {
    const arr = policyObj?.tool_policy?.approval_required_tools;
    return Array.isArray(arr) ? arr.map(String) : [];
  }, [policyObj]);
  const denyTools: string[] = useMemo(() => {
    const arr = policyObj?.tool_policy?.deny_tools;
    return Array.isArray(arr) ? arr.map(String) : [];
  }, [policyObj]);

  const applyTool = (kind: 'approval' | 'deny', toolName: string) => {
    const obj = parsePolicy(policyText);
    if (!obj) {
      toast.error('policy JSON 无法解析');
      return;
    }
    obj.tool_policy = obj.tool_policy && typeof obj.tool_policy === 'object' && !Array.isArray(obj.tool_policy) ? obj.tool_policy : {};
    obj.tool_policy.approval_required_tools = Array.isArray(obj.tool_policy.approval_required_tools) ? obj.tool_policy.approval_required_tools : [];
    obj.tool_policy.deny_tools = Array.isArray(obj.tool_policy.deny_tools) ? obj.tool_policy.deny_tools : [];
    if (kind === 'approval') {
      obj.tool_policy.approval_required_tools = uniq([...(obj.tool_policy.approval_required_tools as any[]).map(String), toolName]);
    } else {
      obj.tool_policy.deny_tools = uniq([...(obj.tool_policy.deny_tools as any[]).map(String), toolName]);
    }
    setPolicyText(JSON.stringify(obj, null, 2));
  };

  const loadTenantPolicy = async () => {
    const tid = tenantId.trim();
    if (!tid) {
      toast.error('tenant_id 不能为空');
      return;
    }
    setLoading(true);
    try {
      const res = await policyApi.getTenant(tid);
      setVersion(res.version);
      setPolicyText(JSON.stringify(res.policy || {}, null, 2));
      toast.success(`已加载（version=${res.version}）`);
    } catch (e: any) {
      toastGateError(e, '加载 tenant policy 失败');
    } finally {
      setLoading(false);
    }
  };

  const saveTenantPolicy = async () => {
    const tid = tenantId.trim();
    if (!tid) {
      toast.error('tenant_id 不能为空');
      return;
    }
    const obj = parsePolicy(policyText);
    if (!obj) {
      toast.error('policy JSON 无法解析');
      return;
    }
    setLoading(true);
    try {
      const res = await policyApi.upsertTenant(tid, { policy: obj as any, version });
      setVersion(res.version);
      toast.success(`已保存（version=${res.version}）`);
    } catch (e: any) {
      toastGateError(e, '保存失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Capability → Policy（工具门禁）</h1>
          <p className="text-sm text-gray-500 mt-1">从 skills 的 capabilities（tool:xxx）汇总建议，并一键写入 tenant policy 的 tool_policy</p>
        </div>
        <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={loadSkills} loading={loading}>
          刷新 skills
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-2">
            <Input value={tenantId} onChange={(e) => setTenantId(e.target.value)} placeholder="tenant_id" className="w-72" />
            <Button variant="secondary" icon={<Search size={16} />} onClick={loadTenantPolicy} loading={loading}>
              加载 tenant policy
            </Button>
            <Button variant="primary" icon={<Save size={16} />} onClick={saveTenantPolicy} loading={loading}>
              保存 tenant policy
            </Button>
            {version != null && <Badge variant="info">version={version}</Badge>}
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-gray-500 mb-1">approval_required_tools</div>
              <pre className="text-xs text-gray-200 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto max-h-[180px]">
                {JSON.stringify(approvalTools, null, 2)}
              </pre>
            </div>
            <div>
              <div className="text-xs text-gray-500 mb-1">deny_tools</div>
              <pre className="text-xs text-gray-200 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto max-h-[180px]">
                {JSON.stringify(denyTools, null, 2)}
              </pre>
            </div>
          </div>
          <div className="mt-3">
            <div className="text-xs text-gray-500 mb-1">policy JSON（可直接编辑）</div>
            <Textarea value={policyText} onChange={(e) => setPolicyText(e.target.value)} rows={10} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-semibold text-gray-200">从 Skill Capabilities 汇总的工具</div>
            <Badge variant="default">tools={tools.length}</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <Table
            data={tools}
            rowKey={(r: any) => String(r.tool)}
            loading={loading}
            columns={[
              { key: 'tool', title: 'tool', dataIndex: 'tool', width: 220, render: (v: any) => <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{String(v)}</code> },
              { key: 'count', title: 'skills', dataIndex: 'count', width: 80 },
              {
                key: 'examples',
                title: 'examples',
                dataIndex: 'examples',
                render: (v: any) =>
                  Array.isArray(v) ? (
                    <div className="text-xs text-gray-400 space-y-1">
                      {v.map((x: any, idx: number) => (
                        <div key={idx}>
                          <span className="text-gray-500">[{x.scope}]</span> {x.skill_id}: {x.name}
                        </div>
                      ))}
                    </div>
                  ) : (
                    '-'
                  ),
              },
              {
                key: 'actions',
                title: '',
                width: 220,
                render: (_: any, r: ToolAgg) => (
                  <div className="flex items-center gap-2">
                    <Button variant="secondary" icon={<PlusCircle size={14} />} onClick={() => applyTool('approval', r.tool)}>
                      加入审批
                    </Button>
                    <Button variant="secondary" icon={<PlusCircle size={14} />} onClick={() => applyTool('deny', r.tool)}>
                      加入 deny
                    </Button>
                  </div>
                ),
              },
            ]}
            emptyText="未发现 tool:xxx capabilities（请检查 SKILL.md front matter 是否包含 capabilities: ['tool:xxx']）"
          />
        </CardContent>
      </Card>
    </div>
  );
};

export default CapabilityPolicy;

