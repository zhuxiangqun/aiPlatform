import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Copy, Save, Search } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Modal, Table, Tabs, toast } from '../../../components/ui';
import { gatePolicyApi, onboardingApi, policyApi } from '../../../services';
import { toastGateError } from '../../../utils/governanceError';

const shortId = (id?: string, left: number = 10, right: number = 8) => {
  if (!id) return '-';
  if (id.length <= left + right + 3) return id;
  return `${id.slice(0, left)}...${id.slice(-right)}`;
};

const Policies: React.FC = () => {
  const [tab, setTab] = useState<'tenant' | 'gate'>('tenant');

  const [tenantId, setTenantId] = useState('');
  const [version, setVersion] = useState<number | undefined>(undefined);
  const [policyText, setPolicyText] = useState('{\n  "tool_policy": {\n    "deny_tools": [],\n    "approval_required_tools": []\n  }\n}\n');
  const [list, setList] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);
  const [toolName, setToolName] = useState('file_operations');
  const [preview, setPreview] = useState<any>(null);
  const [toggleLoading, setToggleLoading] = useState(false);
  const [toggleMsg, setToggleMsg] = useState<string | null>(null);

  // Gate policies
  const [gatePolicies, setGatePolicies] = useState<any[]>([]);
  const [gateDefaultId, setGateDefaultId] = useState<string>('');
  const [gatePolicyId, setGatePolicyId] = useState<string>('default');
  const [gatePolicyText, setGatePolicyText] = useState('{\n  "apply_gate": { "gate_policy": "autosmoke" },\n  "eval_gate": { "mode": "off" },\n  "security_gate": { "mode": "off" }\n}\n');
  const [gateLoading, setGateLoading] = useState(false);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [versionsPolicyId, setVersionsPolicyId] = useState<string>('');
  const [versionsData, setVersionsData] = useState<any | null>(null);

  const isStrongGate = useMemo(() => {
    try {
      const obj = JSON.parse(policyText || '{}');
      const arr = obj?.tool_policy?.approval_required_tools;
      return Array.isArray(arr) && arr.includes('*');
    } catch {
      return false;
    }
  }, [policyText]);

  const validatePolicy = (obj: any): string[] => {
    const errs: string[] = [];
    if (obj == null || typeof obj !== 'object' || Array.isArray(obj)) {
      errs.push('policy 必须是 JSON 对象');
      return errs;
    }
    const tp = (obj as any).tool_policy;
    if (tp != null && (typeof tp !== 'object' || Array.isArray(tp))) {
      errs.push('tool_policy 必须是对象');
      return errs;
    }
    if (tp) {
      if (tp.deny_tools != null && !Array.isArray(tp.deny_tools)) errs.push('tool_policy.deny_tools 必须是数组');
      if (tp.approval_required_tools != null && !Array.isArray(tp.approval_required_tools)) errs.push('tool_policy.approval_required_tools 必须是数组');
    }
    return errs;
  };

  const loadList = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await policyApi.listTenants({ limit, offset });
      setList(res.items || []);
      setTotal(Number(res.total || 0));
    } catch (e: any) {
      setError(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (tab === 'tenant') loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, limit, offset]);

  const loadGatePolicies = async () => {
    setGateLoading(true);
    try {
      const res = await gatePolicyApi.list();
      setGatePolicies(res.items || []);
      setGateDefaultId(String(res.default_id || ''));
    } catch (e: any) {
      toastGateError(e, '加载 Gate Policies 失败');
      setGatePolicies([]);
    } finally {
      setGateLoading(false);
    }
  };

  useEffect(() => {
    if (tab === 'gate') loadGatePolicies();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const loadGateOne = async (pid: string) => {
    if (!pid.trim()) return;
    setGateLoading(true);
    try {
      const res = await gatePolicyApi.get(pid.trim());
      setGatePolicyId(res.item.policy_id);
      setGatePolicyText(JSON.stringify(res.item.config || {}, null, 2));
      setGateDefaultId(String(res.default_id || gateDefaultId || ''));
    } catch (e: any) {
      toastGateError(e, '加载失败');
    } finally {
      setGateLoading(false);
    }
  };

  const bootstrapGatePolicies = async (force: boolean) => {
    setGateLoading(true);
    try {
      const res = await gatePolicyApi.bootstrap({ force });
      toast.success('已初始化 Gate Policies');
      await loadGatePolicies();
      return res;
    } catch (e: any) {
      toastGateError(e, '初始化失败');
      return null;
    } finally {
      setGateLoading(false);
    }
  };

  const openVersions = async (pid: string) => {
    setGateLoading(true);
    try {
      const res = await gatePolicyApi.versions(pid);
      setVersionsPolicyId(pid);
      setVersionsData(res);
      setVersionsOpen(true);
    } catch (e: any) {
      toastGateError(e, '加载版本失败');
    } finally {
      setGateLoading(false);
    }
  };

  const rollbackTo = async (pid: string, version: number) => {
    if (!confirm(`确认将 ${pid} 回滚到 version=${version} ?`)) return;
    setGateLoading(true);
    try {
      await gatePolicyApi.rollback(pid, version);
      toast.success('已回滚');
      await loadGatePolicies();
      await openVersions(pid);
    } catch (e: any) {
      toastGateError(e, '回滚失败');
    } finally {
      setGateLoading(false);
    }
  };

  const saveGatePolicy = async (setDefault: boolean) => {
    const pid = gatePolicyId.trim();
    if (!pid) {
      toast.error('保存失败', 'policy_id 不能为空');
      return;
    }
    setGateLoading(true);
    try {
      const cfg = JSON.parse(gatePolicyText || '{}');
      const res = await gatePolicyApi.upsert(pid, { config: cfg, name: pid }, { set_default: setDefault });
      toast.success('已保存 Gate Policy');
      setGateDefaultId(String(res.default_id || gateDefaultId || ''));
      await loadGatePolicies();
    } catch (e: any) {
      toastGateError(e, '保存失败');
    } finally {
      setGateLoading(false);
    }
  };

  const proposeGatePolicy = async () => {
    const pid = gatePolicyId.trim();
    if (!pid) {
      toast.error('提交失败', 'policy_id 不能为空');
      return;
    }
    setGateLoading(true);
    try {
      const cfg = JSON.parse(gatePolicyText || '{}');
      const res = await gatePolicyApi.propose(pid, { config: cfg, name: pid, set_default: pid === 'prod', require_approval: pid === 'prod' });
      toast.success('已提交变更（ChangeControl）');
      const url = res?.links?.change_control_ui;
      if (url) window.open(String(url), '_blank');
    } catch (e: any) {
      toastGateError(e, '提交失败');
    } finally {
      setGateLoading(false);
    }
  };

  const setGateDefault = async (pid: string) => {
    setGateLoading(true);
    try {
      const res = await gatePolicyApi.setDefault(pid);
      setGateDefaultId(res.default_id);
      toast.success('已设置默认 Gate Policy');
      await loadGatePolicies();
    } catch (e: any) {
      toastGateError(e, '设置失败');
    } finally {
      setGateLoading(false);
    }
  };

  const deleteGate = async (pid: string) => {
    if (!confirm(`确认删除 gate policy: ${pid} ?`)) return;
    setGateLoading(true);
    try {
      await gatePolicyApi.remove(pid);
      toast.success('已删除');
      await loadGatePolicies();
    } catch (e: any) {
      toastGateError(e, '删除失败');
    } finally {
      setGateLoading(false);
    }
  };

  const loadOne = async (tid: string) => {
    if (!tid) return;
    setLoading(true);
    setError(null);
    setOkMsg(null);
    try {
      const res = await policyApi.getTenant(tid);
      setTenantId(res.tenant_id);
      setVersion(res.version);
      setPolicyText(JSON.stringify(res.policy || {}, null, 2));
    } catch (e: any) {
      setError(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  const save = async () => {
    const tid = tenantId.trim();
    if (!tid) {
      setError('tenant_id 不能为空');
      return;
    }
    setLoading(true);
    setError(null);
    setOkMsg(null);
    try {
      const obj = JSON.parse(policyText || '{}');
      const errs = validatePolicy(obj);
      if (errs.length) {
        setError(errs.join('；'));
        return;
      }
      const res = await policyApi.upsertTenant(tid, { policy: obj as any, version });
      setVersion(res.version);
      if ((res as any)?.change_id) {
        setOkMsg(`已保存（version=${res.version} / change_id=${String((res as any).change_id)})`);
      } else {
        setOkMsg(`已保存（version=${res.version}）`);
      }
      await loadList();
    } catch (e: any) {
      setError(e?.message || '保存失败');
      try {
        toastGateError(e, '保存失败');
      } catch {}
    } finally {
      setLoading(false);
    }
  };

  const disableStrongGate = async () => {
    const tid = tenantId.trim();
    if (!tid) return;
    setToggleLoading(true);
    setToggleMsg(null);
    try {
      const res = await onboardingApi.setStrongGate({ tenant_id: tid, enabled: false, require_approval: true });
      setToggleMsg(JSON.stringify(res));
      if (res?.status === 'updated') {
        await loadOne(tid);
        await loadList();
      }
    } catch (e: any) {
      setToggleMsg(e?.message || '操作失败');
    } finally {
      setToggleLoading(false);
    }
  };

  const evaluate = async () => {
    const tid = tenantId.trim();
    const tn = toolName.trim();
    if (!tid || !tn) return;
    setLoading(true);
    setError(null);
    try {
      const res = await policyApi.evaluateTool(tid, tn);
      setPreview(res);
    } catch (e: any) {
      setError(e?.message || '预览失败');
    } finally {
      setLoading(false);
    }
  };

  const columns = useMemo(
    () => [
      {
        key: 'tenant_id',
        title: 'tenant_id',
        dataIndex: 'tenant_id',
        render: (v: any) => (
          <div className="flex items-center gap-2">
            <code className="text-xs text-gray-200">{shortId(v)}</code>
            <Button variant="ghost" icon={<Copy size={14} />} onClick={() => navigator.clipboard.writeText(String(v))} />
          </div>
        ),
      },
      { key: 'version', title: 'version', dataIndex: 'version', width: 90, align: 'right' as const },
      {
        key: 'updated_at',
        title: 'updated_at',
        dataIndex: 'updated_at',
        width: 160,
        render: (v: any) => <span className="text-xs text-gray-500">{v ? String(v) : '-'}</span>,
      },
      {
        key: 'op',
        title: 'op',
        dataIndex: 'tenant_id',
        width: 120,
        render: (v: any) => (
          <Button variant="secondary" onClick={() => loadOne(String(v))}>
            编辑
          </Button>
        ),
      },
    ],
    [version]
  );

  const renderTenantPolicies = () => (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Tenant Policies</h1>
          <p className="text-sm text-gray-500 mt-1">Policy-as-code：为 tenant 保存 JSON 策略快照（支持工具命中预览）</p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/diagnostics">
            <Button variant="secondary" icon={<ArrowLeft size={16} />}>
              返回
            </Button>
          </Link>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold text-gray-200">已有 tenant policies</div>
            <div className="flex items-center gap-2">
              <Input label="limit" type="number" value={String(limit)} onChange={(e: any) => setLimit(Number(e.target.value || 50))} />
              <Button icon={<Search size={16} />} onClick={() => { setOffset(0); loadList(); }} loading={loading}>
                刷新
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
            <Table columns={columns as any} data={list} rowKey="tenant_id" loading={loading} emptyText="暂无 tenant policies" />
          </div>
          <div className="flex items-center justify-between text-sm text-gray-400 mt-3">
            <div>total: {total}</div>
            <div className="flex items-center gap-2">
              <Button onClick={() => setOffset(Math.max(0, offset - limit))} disabled={offset <= 0}>
                上一页
              </Button>
              <Button onClick={() => setOffset(offset + limit)} disabled={offset + limit >= total}>
                下一页
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-semibold text-gray-200">编辑策略</div>
            <div className="flex items-center gap-2">
              {typeof version === 'number' && <Badge variant="info">version: {version}</Badge>}
              <Button variant="secondary" icon={<Copy size={16} />} onClick={() => navigator.clipboard.writeText(policyText || '')}>
                复制 JSON
              </Button>
              <Button icon={<Save size={16} />} onClick={save} loading={loading}>
                保存
              </Button>
            </div>
          </div>
          {isStrongGate && (
            <div className="mt-3 text-xs text-warning">
              当前策略已启用强门禁（approval_required_tools 包含 '*'）。如需回滚，请点击
              <Button variant="secondary" onClick={disableStrongGate} loading={toggleLoading} className="ml-2">
                解除强门禁（需审批）
              </Button>
              {toggleMsg && <span className="ml-2 text-gray-500">{toggleMsg}</span>}
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-3">
            <Input label="tenant_id" value={tenantId} onChange={(e: any) => setTenantId(e.target.value.trim())} placeholder="tenant_xxx" />
            <Input label="version（可选）" value={version == null ? '' : String(version)} onChange={(e: any) => setVersion(e.target.value ? Number(e.target.value) : undefined)} placeholder="用于并发更新，填则冲突返回 409" />
          </div>
          <div className="flex flex-wrap items-center gap-2 mt-3">
            <Button
              variant="secondary"
              onClick={() =>
                setPolicyText(
                  JSON.stringify({ tool_policy: { deny_tools: ['file_operations'], approval_required_tools: [] } }, null, 2)
                )
              }
            >
              模板：deny 文件工具
            </Button>
            <Button
              variant="secondary"
              onClick={() =>
                setPolicyText(
                  JSON.stringify({ tool_policy: { deny_tools: [], approval_required_tools: ['file_operations'] } }, null, 2)
                )
              }
            >
              模板：文件工具需审批
            </Button>
            <Button
              variant="secondary"
              onClick={() =>
                setPolicyText(JSON.stringify({ tool_policy: { deny_tools: ['calculator'], approval_required_tools: [] } }, null, 2))
              }
            >
              模板：deny calculator
            </Button>
          </div>
          {error && <div className="text-sm text-error mt-2">{error}</div>}
          {okMsg && <div className="text-sm text-green-300 mt-2">{okMsg}</div>}
        </CardHeader>
        <CardContent>
          <textarea
            className="w-full min-h-[320px] bg-dark-hover border border-dark-border rounded-lg p-3 text-xs text-gray-200 font-mono"
            value={policyText}
            onChange={(e) => setPolicyText(e.target.value)}
            spellCheck={false}
          />
          <div className="text-xs text-gray-500 mt-2">
            说明：当前已支持 tool deny / tool approval_required 的执行期生效；可以用下方“命中预览”验证策略是否会拦截某个工具。
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-semibold text-gray-200">命中预览</div>
            <Button onClick={evaluate} loading={loading}>
              预览
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            <Input label="tenant_id" value={tenantId} onChange={(e: any) => setTenantId(e.target.value.trim())} placeholder="tenant_xxx" />
            <Input label="tool_name" value={toolName} onChange={(e: any) => setToolName(e.target.value.trim())} placeholder="file_operations" />
          </div>
          {preview && (
            <div className="mt-3 text-sm text-gray-300">
              decision: <code className="text-xs text-gray-200">{String(preview.decision)}</code>，policy_version:{' '}
              <code className="text-xs text-gray-200">{String(preview.policy_version ?? '-')}</code>，matched_rule:{' '}
              <code className="text-xs text-gray-200">{String(preview.matched_rule ?? '-')}</code>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );

  const gateColumns = useMemo(
    () => [
      { key: 'policy_id', title: 'policy_id', dataIndex: 'policy_id', width: 220, render: (v: any) => <code className="text-xs">{String(v)}</code> },
      {
        key: 'default',
        title: 'default',
        width: 110,
        render: (_: any, r: any) =>
          String(r?.policy_id || '') === String(gateDefaultId || '') ? <Badge variant="success">default</Badge> : <Badge variant="default">-</Badge>,
      },
      { key: 'updated_at', title: 'updated_at', dataIndex: 'updated_at', width: 160, render: (v: any) => <span className="text-xs text-gray-500">{v || '-'}</span> },
      {
        key: 'op',
        title: 'op',
        width: 240,
        render: (_: any, r: any) => (
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => loadGateOne(String(r?.policy_id || ''))} disabled={gateLoading}>
              编辑
            </Button>
            <Button variant="secondary" onClick={() => openVersions(String(r?.policy_id || ''))} disabled={gateLoading}>
              版本
            </Button>
            <Button variant="secondary" onClick={() => setGateDefault(String(r?.policy_id || ''))} disabled={gateLoading}>
              设为默认
            </Button>
            <Button variant="danger" onClick={() => deleteGate(String(r?.policy_id || ''))} disabled={gateLoading}>
              删除
            </Button>
          </div>
        ),
      },
    ],
    [gateDefaultId, gateLoading],
  );

  const renderGatePolicies = () => (
    <div className="space-y-4">
      <Modal open={versionsOpen} onClose={() => setVersionsOpen(false)} title={`Gate Policy Versions: ${versionsPolicyId}`} width={900}>
        <div className="space-y-3">
          <div className="text-sm text-gray-300">
            current_version: <code>{String(versionsData?.current_version ?? '-')}</code>
          </div>
          <div className="bg-dark-card border border-dark-border rounded-lg overflow-hidden">
            <table className="w-full text-sm text-gray-300">
              <thead className="bg-dark-hover text-xs text-gray-400">
                <tr>
                  <th className="text-left px-3 py-2">version</th>
                  <th className="text-left px-3 py-2">updated_at</th>
                  <th className="text-left px-3 py-2">sha256</th>
                  <th className="text-left px-3 py-2">op</th>
                </tr>
              </thead>
              <tbody>
                {(versionsData?.revisions || []).map((r: any, idx: number) => (
                  <tr key={idx} className="border-t border-dark-border">
                    <td className="px-3 py-2">
                      <code>{String(r?.version ?? '-')}</code>
                    </td>
                    <td className="px-3 py-2">
                      <span className="text-xs text-gray-400">{String(r?.updated_at ?? '-')}</span>
                    </td>
                    <td className="px-3 py-2">
                      <code className="text-xs">{String(r?.sha256 || '').slice(0, 12)}</code>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <Button variant="secondary" onClick={() => navigator.clipboard.writeText(JSON.stringify(r?.config || {}, null, 2))}>
                          复制配置
                        </Button>
                        <Button variant="primary" onClick={() => rollbackTo(versionsPolicyId, Number(r?.version || 0))} disabled={!r?.version}>
                          回滚到此版本
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!Array.isArray(versionsData?.revisions) || versionsData.revisions.length === 0 ? (
                  <tr>
                    <td className="px-3 py-3 text-gray-500" colSpan={4}>
                      暂无历史版本
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </Modal>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold text-gray-200">Gate Policies</div>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => bootstrapGatePolicies(false)} loading={gateLoading}>
                初始化模板
              </Button>
              <Button variant="secondary" onClick={() => bootstrapGatePolicies(true)} loading={gateLoading}>
                强制重置
              </Button>
              <Button onClick={loadGatePolicies} loading={gateLoading}>
                刷新
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
            <Table columns={gateColumns as any} data={gatePolicies} rowKey="policy_id" loading={gateLoading} emptyText="暂无 Gate Policies" />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-semibold text-gray-200">编辑 Gate Policy</div>
            <div className="flex items-center gap-2">
              <Input label="policy_id" value={gatePolicyId} onChange={(e: any) => setGatePolicyId(String(e.target.value || ''))} />
              <Button variant="secondary" onClick={() => navigator.clipboard.writeText(gatePolicyText || '')}>
                复制 JSON
              </Button>
              <Button variant="secondary" onClick={proposeGatePolicy} loading={gateLoading}>
                提交变更
              </Button>
              <Button onClick={() => saveGatePolicy(false)} loading={gateLoading}>
                保存
              </Button>
              <Button variant="primary" onClick={() => saveGatePolicy(true)} loading={gateLoading}>
                保存并设为默认
              </Button>
            </div>
          </div>
          <p className="text-sm text-gray-500 mt-1">用于将 apply gate/eval/security/cost 等门禁参数封装成可复用策略（产品化 Phase 1）。</p>
        </CardHeader>
        <CardContent>
          <textarea
            className="w-full h-[320px] bg-dark-card border border-dark-border rounded-lg p-3 text-sm text-gray-200 font-mono"
            value={gatePolicyText}
            onChange={(e) => setGatePolicyText(e.target.value)}
          />
        </CardContent>
      </Card>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Policies</h1>
          <p className="text-sm text-gray-500 mt-1">Policy-as-code / Gate Policies（产品化入口）</p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/diagnostics">
            <Button variant="secondary" icon={<ArrowLeft size={16} />}>
              返回
            </Button>
          </Link>
        </div>
      </div>

      <Tabs
        defaultActiveKey="tenant"
        onChange={(k) => setTab((k as any) || 'tenant')}
        tabs={[
          { key: 'tenant', label: 'Tenant Policies', children: renderTenantPolicies() },
          { key: 'gate', label: 'Gate Policies', children: renderGatePolicies() },
        ]}
      />
    </div>
  );
};

export default Policies;
