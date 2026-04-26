import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Copy, ExternalLink, Link2, RotateCw } from 'lucide-react';
import { Button, Card, CardContent, CardHeader, Input, Modal, Select, Table, toast, Badge } from '../../../components/ui';
import { diagnosticsApi } from '../../../services';
import { extractGateEnvelope, toastGateError } from '../../../utils/governanceError';

const fmtTs = (v: any) => {
  const n = Number(v);
  if (!Number.isFinite(n) || n <= 0) return '-';
  const d = new Date(n * 1000);
  return d.toISOString().replace('T', ' ').slice(0, 19);
};

const badge = (status: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  const s = String(status || '').toLowerCase();
  if (s === 'success' || s === 'completed' || s === 'ok' || s === 'enabled' || s === 'published') return 'success';
  if (s === 'approval_required') return 'warning';
  if (s === 'blocked' || s === 'failed' || s === 'error') return 'error';
  return 'default';
};

const recBadge = (a: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  const s = String(a || '').toLowerCase();
  if (s === 'continue') return 'success';
  if (s === 'investigate') return 'warning';
  if (s === 'block') return 'error';
  return 'default';
};

const ChangeControl: React.FC = () => {
  const { changeId } = useParams();
  const navigate = useNavigate();

  // list
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [limit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState('');
  const [state, setState] = useState<string>('');

  // detail
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<any | null>(null);
  const [applyGatePolicyId, setApplyGatePolicyId] = useState<string>('');
  const [gateEnvelope, setGateEnvelope] = useState<any | null>(null);
  const [gateDetailOpen, setGateDetailOpen] = useState(false);
  const [gateDetailTitle, setGateDetailTitle] = useState<string>('');
  const [gateDetailPayload, setGateDetailPayload] = useState<any>(null);

  const loadList = async () => {
    setLoading(true);
    try {
      const res = await diagnosticsApi.listChangeControls({ limit, offset });
      const data = res?.changes || {};
      const rows = Array.isArray(data.items) ? data.items : [];
      const filtered0 = q.trim()
        ? rows.filter((r: any) => String(r?.change_id || r?.target_id || '').includes(q.trim()))
        : rows;
      const filtered = state
        ? filtered0.filter((r: any) => String(r?.summary?.derived_state || '').toLowerCase() === String(state).toLowerCase())
        : filtered0;
      setItems(filtered);
      setTotal(Number(data.total || 0));
    } catch (e: any) {
      toastGateError(e, '加载失败');
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  const loadDetail = async (cid: string) => {
    setDetailLoading(true);
    try {
      const res = await diagnosticsApi.getChangeControl(cid, { limit: 200, offset: 0 });
      setDetail(res?.change || null);
      // Best-effort: populate last known gate block from persisted changeset event.
      try {
        const ev = res?.change?.events?.items || [];
        const lastFail = Array.isArray(ev) ? ev.find((e: any) => String(e?.name || '') === 'apply_gate.failed') : null;
        if (lastFail?.result?.next_actions) setGateEnvelope({ ...(lastFail.result || {}), code: 'apply_gate_failed', message: 'apply_gate_failed' });
      } catch {}
    } catch (e: any) {
      toastGateError(e, '加载失败');
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

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

  const autosmoke = async (cid: string) => {
    setDetailLoading(true);
    try {
      const res = await diagnosticsApi.autosmokeChangeControl(cid);
      toast.success('已触发 autosmoke');
      // reload detail to capture new changeset event
      await loadDetail(cid);
      return res;
    } catch (e: any) {
      toastGateError(e, '触发失败');
      try {
        const env = extractGateEnvelope(e);
        if (env) setGateEnvelope(env);
      } catch {}
      return null;
    } finally {
      setDetailLoading(false);
    }
  };

  const applyPatch = async (cid: string) => {
    setDetailLoading(true);
    try {
      const res = await diagnosticsApi.applyEngineSkillMdPatchChangeControl(cid, { gate_policy_id: applyGatePolicyId.trim() || undefined });
      toast.success('已触发 apply');
      setGateEnvelope(null);
      await loadDetail(cid);
      return res;
    } catch (e: any) {
      toastGateError(e, '触发失败');
      try {
        const env = extractGateEnvelope(e);
        if (env) setGateEnvelope(env);
      } catch {}
      return null;
    } finally {
      setDetailLoading(false);
    }
  };

  const execNextAction = async (cid: string, act: any) => {
    const api = act?.api;
    const method = String(api?.method || '').toUpperCase();
    let path = String(api?.path || '');
    if (!method || !path) return;
    // Backend actions may return absolute "/api/..." paths; apiClient base is "/api".
    if (path.startsWith('/api')) path = path.slice(4);
    const base = (import.meta as any).env?.VITE_API_URL || '/api';
    const url = `${base}${path}`;
    const headers: any = { 'Content-Type': 'application/json' };
    try {
      const tenantId = localStorage.getItem('active_tenant_id') || '';
      const actorId = localStorage.getItem('active_actor_id') || '';
      const actorRole = localStorage.getItem('active_actor_role') || '';
      if (tenantId.trim()) headers['X-AIPLAT-TENANT-ID'] = tenantId.trim();
      if (actorId.trim()) headers['X-AIPLAT-ACTOR-ID'] = actorId.trim();
      if (actorRole.trim()) headers['X-AIPLAT-ACTOR-ROLE'] = actorRole.trim();
    } catch {}
    try {
      const resp = await fetch(url, { method, headers, body: method === 'POST' ? JSON.stringify({}) : undefined });
      if (!resp.ok) {
        const payload: any = await resp.json().catch(() => null);
        const err: any = new Error(payload?.detail?.message || payload?.detail || payload?.message || `HTTP ${resp.status}`);
        err.payload = payload;
        err.detail = payload?.detail;
        throw err;
      }
      toast.success('操作成功');
      setGateEnvelope(null);
      await loadDetail(cid);
    } catch (e: any) {
      toastGateError(e, '操作失败');
      try {
        const env = extractGateEnvelope(e);
        if (env) setGateEnvelope(env);
      } catch {}
    }
  };

  const openGateDetail = (title: string, payload: any) => {
    setGateDetailTitle(title);
    setGateDetailPayload(payload);
    setGateDetailOpen(true);
  };

  useEffect(() => {
    if (!changeId) loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [changeId, limit, offset]);

  useEffect(() => {
    if (changeId) loadDetail(changeId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [changeId]);

  const listColumns = useMemo(
    () => [
      { key: 'change_id', title: 'change_id', dataIndex: 'change_id', width: 190 },
      {
        key: 'name',
        title: 'operation',
        width: 220,
        render: (_: any, r: any) => <code className="text-xs">{String(r?.name || '-')}</code>,
      },
      {
        key: 'status',
        title: 'status',
        width: 140,
        render: (_: any, r: any) => {
          const st = String(r?.summary?.derived_state || r?.status || '-');
          return <Badge variant={badge(st)}>{st}</Badge>;
        },
      },
      {
        key: 'rec',
        title: 'recommendation',
        width: 160,
        render: (_: any, r: any) => {
          // Prefer explicit recommendation for change-control gates.
          const name = String(r?.name || '');
          if (name === 'apply_gate.failed') {
            const rec = r?.result?.recommended_next_action || r?.result?.recommended || '';
            const na = Array.isArray(r?.result?.next_actions) ? r.result.next_actions : [];
            const rec2 = na.find((x: any) => x?.recommended)?.type || na[0]?.type || '';
            const label = String(rec || rec2 || 'blocked');
            return <Badge variant={recBadge(label)}>{label}</Badge>;
          }
          const a = r?.result?.recommendation?.action;
          if (!a) return <span className="text-xs text-gray-500">-</span>;
          return <Badge variant={recBadge(String(a))}>{String(a)}</Badge>;
        },
      },
      {
        key: 'reason',
        title: 'reason',
        width: 260,
        render: (_: any, r: any) => {
          const name = String(r?.name || '');
          if (name === 'apply_gate.failed') {
            const missing = [];
            if (r?.result?.autosmoke_ok === false) missing.push('autosmoke');
            if (r?.result?.approval_ok === false) missing.push('approval');
            const msg = missing.length ? `missing: ${missing.join(',')}` : 'blocked';
            return <span className="text-xs text-gray-400">{msg}</span>;
          }
          const reason0 = r?.result?.recommendation?.reason;
          if (!reason0) return <span className="text-xs text-gray-500">-</span>;
          return <span className="text-xs text-gray-400">{String(reason0).slice(0, 80)}</span>;
        },
      },
      {
        key: 'updated_at',
        title: 'updated_at',
        width: 170,
        render: (_: any, r: any) => <span className="text-xs text-gray-300">{fmtTs(r?.created_at)}</span>,
      },
      {
        key: 'approval',
        title: 'approval',
        width: 140,
        render: (_: any, r: any) => (
          <span className="text-xs text-gray-300">{r?.approval_request_id ? String(r.approval_request_id).slice(0, 12) : '-'}</span>
        ),
      },
      {
        key: 'targets',
        title: 'targets',
        render: (_: any, r: any) => {
          const ts = r?.args?.targets;
          if (!Array.isArray(ts) || ts.length === 0) return <span className="text-xs text-gray-500">-</span>;
          return (
            <div className="text-xs text-gray-300">
              {ts.slice(0, 3).map((t: any, idx: number) => (
                <span key={idx} className="mr-2">
                  {String(t?.type || '?')}:{String(t?.id || '').slice(0, 10)}
                </span>
              ))}
              {ts.length > 3 ? <span className="text-gray-500">+{ts.length - 3}</span> : null}
            </div>
          );
        },
      },
      {
        key: 'actions',
        title: 'actions',
        width: 220,
        render: (_: any, r: any) => (
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => navigate(`/diagnostics/change-control/${encodeURIComponent(String(r.change_id))}`)}>
              查看
            </Button>
            {String(r?.name || '') === 'apply_gate.failed' && Array.isArray(r?.result?.next_actions) ? (
              <Button
                variant="primary"
                onClick={() => {
                  const na = r.result.next_actions || [];
                  const rec = na.find((x: any) => x?.recommended) || na[0];
                  if (rec) execNextAction(String(r.change_id), rec);
                }}
              >
                执行推荐
              </Button>
            ) : null}
            {r?.links?.syscalls_ui ? (
              <a className="text-xs underline text-gray-300 hover:text-white" href={String(r.links.syscalls_ui)} target="_blank" rel="noreferrer">
                Syscalls <ExternalLink size={12} className="inline ml-1" />
              </a>
            ) : null}
          </div>
        ),
      },
    ],
    [navigate],
  );

  const eventColumns = useMemo(
    () => [
      { key: 'created_at', title: 'time', width: 180, render: (_: any, r: any) => <span className="text-xs">{fmtTs(r?.created_at)}</span> },
      { key: 'name', title: 'name', width: 220, render: (_: any, r: any) => <code className="text-xs">{String(r?.name || '-')}</code> },
      { key: 'status', title: 'status', width: 140, render: (_: any, r: any) => <Badge variant={badge(String(r?.status || ''))}>{String(r?.status || '-')}</Badge> },
      { key: 'approval', title: 'approval', width: 140, render: (_: any, r: any) => <span className="text-xs">{r?.approval_request_id ? String(r.approval_request_id).slice(0, 12) : '-'}</span> },
      {
        key: 'payload',
        title: 'payload',
        render: (_: any, r: any) => (
          <pre className="text-xs text-gray-300 bg-dark-card border border-dark-border rounded-lg p-2 overflow-auto max-h-[220px]">
            {JSON.stringify({ args: r?.args, result: r?.result, error: r?.error, error_code: r?.error_code }, null, 2)}
          </pre>
        ),
      },
    ],
    [],
  );

  if (changeId) {
    const latest = detail?.latest || null;
    const ev = detail?.events?.items || [];
    const summary = detail?.summary || null;
    const cfgEvents = Array.isArray(ev) ? ev.filter((e: any) => String(e?.name || '').startsWith('config_')) : [];
    const cfgLatest = cfgEvents[0] || null;
    const gatePolicyEv = Array.isArray(ev) ? ev.find((e: any) => String(e?.name || '') === 'gate_policy.resolved') : null;
    const codeIntelEv = Array.isArray(ev) ? ev.find((e: any) => String(e?.name || '') === 'code_intel.report') : null;
    const trigEv = Array.isArray(ev) ? ev.find((e: any) => String(e?.name || '') === 'skill_eval.gate.trigger_eval') : null;
    const qualEv = Array.isArray(ev) ? ev.find((e: any) => String(e?.name || '') === 'skill_eval.gate.quality_eval') : null;
    const secEv = Array.isArray(ev) ? ev.find((e: any) => String(e?.name || '') === 'skill_eval.gate.security_scan') : null;
    const smokeEv = Array.isArray(ev) ? ev.find((e: any) => String(e?.name || '') === 'change_control.autosmoke.result') : null;
    return (
      <div className="space-y-6">
        <Modal
          open={gateDetailOpen}
          onClose={() => setGateDetailOpen(false)}
          title={gateDetailTitle || '详情'}
          width={900}
        >
          <pre className="text-xs text-gray-300 overflow-auto max-h-[70vh] bg-dark-card border border-dark-border rounded-lg p-3">
            {JSON.stringify(gateDetailPayload, null, 2)}
          </pre>
        </Modal>
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => navigate('/diagnostics/change-control')}>
                <ArrowLeft size={14} className="mr-1" />
                返回列表
              </Button>
              <h1 className="text-2xl font-semibold text-gray-200">Change Control</h1>
            </div>
            <div className="text-sm text-gray-500">change_id：{changeId}</div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={() => loadDetail(changeId)} loading={detailLoading} icon={<RotateCw size={14} />}>
              刷新
            </Button>
            <Button variant="primary" onClick={() => autosmoke(changeId)} loading={detailLoading}>
              触发 autosmoke
            </Button>
            <Input
              label="gate_policy_id(可选)"
              value={applyGatePolicyId}
              onChange={(e: any) => setApplyGatePolicyId(String(e.target.value || ''))}
              placeholder="留空=使用默认"
            />
            <Button variant="primary" onClick={() => applyPatch(changeId)} loading={detailLoading}>
              应用 Patch
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                try {
                  navigator.clipboard.writeText(String(changeId));
                  toast.success('已复制 change_id');
                } catch {
                  // ignore
                }
              }}
            >
              <Copy size={14} className="mr-1" />
              复制 change_id
            </Button>
            <Button
              variant="secondary"
              onClick={async () => {
                try {
                  const resp = await diagnosticsApi.exportChangeControlEvidence(changeId, { format: 'zip', limit: 500 });
                  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                  const blob = await resp.blob();
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `change_${changeId}_evidence.zip`;
                  a.click();
                  URL.revokeObjectURL(url);
                  toast.success('已导出证据包（zip）');
                } catch (e: any) {
                  toast.error('导出失败', String(e?.message || e));
                }
              }}
            >
              导出证据包（zip）
            </Button>
            <Button variant="secondary" onClick={() => downloadJson(`change_${changeId}.json`, detail)}>
              导出当前页 JSON
            </Button>
            {detail?.links?.syscalls_ui ? (
              <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.syscalls_ui)} target="_blank" rel="noreferrer">
                打开 Syscalls <ExternalLink size={14} className="inline ml-1" />
              </a>
            ) : null}
            {latest?.approval_request_id ? (
              <Link className="text-sm underline text-gray-300 hover:text-white" to="/core/approvals">
                Approvals
              </Link>
            ) : null}
            {detail?.links?.audit_ui ? (
              <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.audit_ui)} target="_blank" rel="noreferrer">
                Audit <ExternalLink size={14} className="inline ml-1" />
              </a>
            ) : null}
            {detail?.links?.runs_ui ? (
              <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.runs_ui)} target="_blank" rel="noreferrer">
                Runs <ExternalLink size={14} className="inline ml-1" />
              </a>
            ) : null}
            {detail?.links?.traces_ui ? (
              <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.traces_ui)} target="_blank" rel="noreferrer">
                Traces <ExternalLink size={14} className="inline ml-1" />
              </a>
            ) : null}
          </div>
        </div>

        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">联动跳转</div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="secondary"
                icon={<Link2 size={14} />}
                onClick={() => {
                  const url = `/diagnostics/links?change_id=${encodeURIComponent(changeId)}`;
                  navigate(url);
                }}
              >
                打开 Links
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  const links = detail?.links || {};
                  const payload = { change_id: changeId, links };
                  navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
                  toast.success('已复制 links JSON');
                }}
              >
                复制 links
              </Button>
              {detail?.links?.syscalls_ui ? (
                <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.syscalls_ui)} target="_blank" rel="noreferrer">
                  Syscalls <ExternalLink size={14} className="inline ml-1" />
                </a>
              ) : null}
              {detail?.links?.audit_ui ? (
                <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.audit_ui)} target="_blank" rel="noreferrer">
                  Audit <ExternalLink size={14} className="inline ml-1" />
                </a>
              ) : null}
              {detail?.links?.approvals_ui ? (
                <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.approvals_ui)} target="_blank" rel="noreferrer">
                  Approvals <ExternalLink size={14} className="inline ml-1" />
                </a>
              ) : null}
              {detail?.links?.runs_ui ? (
                <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.runs_ui)} target="_blank" rel="noreferrer">
                  Runs <ExternalLink size={14} className="inline ml-1" />
                </a>
              ) : null}
              {detail?.links?.traces_ui ? (
                <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.traces_ui)} target="_blank" rel="noreferrer">
                  Traces <ExternalLink size={14} className="inline ml-1" />
                </a>
              ) : null}
              {detail?.links?.links_ui ? (
                <a className="text-sm underline text-gray-300 hover:text-white" href={String(detail.links.links_ui)} target="_blank" rel="noreferrer">
                  Links <ExternalLink size={14} className="inline ml-1" />
                </a>
              ) : null}
            </div>
          </CardContent>
        </Card>

        {latest?.result?.recommendation?.action ? (
          <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-gray-200">建议动作</div>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={recBadge(String(latest.result.recommendation.action))}>{String(latest.result.recommendation.action)}</Badge>
                <span className="text-xs text-gray-400 break-all">{String(latest.result.recommendation.reason || '')}</span>
              </div>
            </CardContent>
          </Card>
        ) : null}

        {cfgLatest ? (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-gray-200">Config 发布变更</div>
                <Badge variant={badge(String(cfgLatest?.status || ''))}>{String(cfgLatest?.status || '-')}</Badge>
              </div>
            </CardHeader>
            <CardContent>
              {(() => {
                const a = cfgLatest?.args || {};
                const asset = String(a.asset_type || '-');
                const scope0 = String(a.scope || '-');
                const channel0 = String(a.channel || '-');
                const tenant0 = String(a.tenant_id || '-');
                const fromVer = a.from_version != null ? String(a.from_version) : '';
                const toVer = String(a.to_version || a.version || '-');
                const rid = cfgLatest?.approval_request_id ? String(cfgLatest.approval_request_id) : '';
                const rolloutsUrl = `/core/skills-rollouts?tenant_id=${encodeURIComponent(tenant0)}&scope=${encodeURIComponent(scope0)}&channel=${encodeURIComponent(channel0)}&asset_type=${encodeURIComponent(asset)}`;
                return (
                  <div className="space-y-2 text-sm text-gray-300">
                    <div>
                      asset=<code>{asset}</code> scope=<code>{scope0}</code> channel=<code>{channel0}</code> tenant=<code>{tenant0}</code>
                    </div>
                    {fromVer ? (
                      <div>
                        from_version=<code>{fromVer}</code>
                      </div>
                    ) : null}
                    <div>
                      to_version=<code>{toVer}</code>
                    </div>
                    {rid ? (
                      <div>
                        approval_request_id=<code>{rid}</code>
                      </div>
                    ) : null}
                    <div className="flex items-center gap-2">
                      <Button variant="secondary" onClick={() => navigate(rolloutsUrl)}>
                        打开灰度发布页定位
                      </Button>
                      {rid ? (
                        <Link to={`/core/approvals`}>
                          <Button variant="secondary">打开审批中心</Button>
                        </Link>
                      ) : null}
                    </div>
                    {cfgEvents.length > 1 ? (
                      <pre className="text-xs text-gray-300 overflow-auto max-h-[180px] bg-dark-card border border-dark-border rounded-lg p-3">
                        {JSON.stringify(
                          cfgEvents.map((x: any) => ({ name: x.name, status: x.status, created_at: x.created_at, args: x.args, approval_request_id: x.approval_request_id })),
                          null,
                          2
                        )}
                      </pre>
                    ) : null}
                  </div>
                );
              })()}
            </CardContent>
          </Card>
        ) : null}

        {gatePolicyEv ? (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-gray-200">Gate Policy（门禁策略）</div>
                <Badge variant={badge(String(gatePolicyEv?.status || ''))}>{String(gatePolicyEv?.status || '-')}</Badge>
              </div>
            </CardHeader>
            <CardContent>
              {(() => {
                const a = gatePolicyEv?.args || {};
                const r = gatePolicyEv?.result || {};
                const pid = String(a.gate_policy_id || '-');
                const src = String(a.source || '-');
                return (
                  <div className="space-y-3">
                    <div className="text-sm text-gray-300">
                      policy_id=<code>{pid}</code> source=<code>{src}</code>
                    </div>
                    <pre className="text-xs text-gray-300 overflow-auto max-h-[220px] bg-dark-card border border-dark-border rounded-lg p-3">
                      {JSON.stringify(r, null, 2)}
                    </pre>
                    <div className="flex items-center gap-2">
                      <Link to="/diagnostics/policies">
                        <Button variant="secondary">打开 Policies（可编辑 Gate Policies）</Button>
                      </Link>
                    </div>
                  </div>
                );
              })()}
            </CardContent>
          </Card>
        ) : null}

        {codeIntelEv ? (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-gray-200">Code Intel Report</div>
                <Badge variant={badge(String(codeIntelEv?.status || ''))}>{String(codeIntelEv?.status || '-')}</Badge>
              </div>
            </CardHeader>
            <CardContent>
              {(() => {
                const r = codeIntelEv?.result || {};
                const touched = Array.isArray(r?.touched) ? r.touched : [];
                return (
                  <div className="space-y-3">
                    <div className="text-sm text-gray-300">
                      files={Number(r?.stats?.files || 0)} edges={Number(r?.stats?.edges || 0)} issues={Number(r?.stats?.issues || 0)} cycles=
                      {Number(r?.stats?.cycles_back_edges || 0)}
                    </div>
                    {touched.length ? (
                      <div className="text-sm text-gray-300">
                        touched:
                        <pre className="text-xs text-gray-300 overflow-auto max-h-[140px] bg-dark-card border border-dark-border rounded-lg p-3 mt-2">
                          {JSON.stringify(touched, null, 2)}
                        </pre>
                      </div>
                    ) : (
                      <div className="text-sm text-gray-500">（本次变更未匹配到可分析的 repo 文件路径，仍提供全局扫描统计）</div>
                    )}
                    <div className="flex items-center gap-2">
                      <Link to="/diagnostics/code-intel">
                        <Button variant="secondary">打开 Code Intel</Button>
                      </Link>
                      <Button variant="secondary" onClick={() => openGateDetail('Code Intel Report 详情', codeIntelEv)}>
                        查看原始 JSON
                      </Button>
                    </div>
                  </div>
                );
              })()}
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">Gate Report（门禁面板）</div>
              <Badge variant={badge(String(summary?.derived_state || ''))}>{String(summary?.derived_state || 'unknown')}</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm text-gray-300">
              <div className="bg-dark-card border border-dark-border rounded-lg p-3">
                <div className="flex items-center justify-between">
                  <div className="font-semibold">Autosmoke</div>
                  <Badge variant={badge(String(smokeEv?.result?.job_run_status || ''))}>{String(smokeEv?.result?.job_run_status || '-')}</Badge>
                </div>
                <div className="text-xs text-gray-400 mt-2 break-all">run_id: {String(smokeEv?.result?.job_run_id || '-')}</div>
                <div className="mt-2">
                  <Button variant="secondary" onClick={() => openGateDetail('Autosmoke 详情', smokeEv)} disabled={!smokeEv}>
                    查看详情
                  </Button>
                </div>
              </div>
              <div className="bg-dark-card border border-dark-border rounded-lg p-3">
                <div className="flex items-center justify-between">
                  <div className="font-semibold">Trigger Eval</div>
                  <Badge variant={badge(String(trigEv?.result?.passed ? 'success' : trigEv ? 'failed' : 'unknown'))}>
                    {trigEv ? (trigEv?.result?.passed ? 'passed' : 'failed') : '-'}
                  </Badge>
                </div>
                <div className="text-xs text-gray-400 mt-2">f1: {String(trigEv?.result?.metrics?.f1 ?? '-')}</div>
                <div className="mt-2">
                  <Button variant="secondary" onClick={() => openGateDetail('Trigger Eval 详情', trigEv)} disabled={!trigEv}>
                    查看详情
                  </Button>
                </div>
              </div>
              <div className="bg-dark-card border border-dark-border rounded-lg p-3">
                <div className="flex items-center justify-between">
                  <div className="font-semibold">Quality Eval</div>
                  <Badge variant={badge(String(qualEv?.result?.passed ? 'success' : qualEv ? 'failed' : 'unknown'))}>
                    {qualEv ? (qualEv?.result?.passed ? 'passed' : 'failed') : '-'}
                  </Badge>
                </div>
                <div className="text-xs text-gray-400 mt-2">pass_rate: {String(qualEv?.result?.metrics?.pass_rate ?? '-')}</div>
                <div className="mt-2">
                  <Button variant="secondary" onClick={() => openGateDetail('Quality Eval 详情', qualEv)} disabled={!qualEv}>
                    查看详情
                  </Button>
                </div>
              </div>
              <div className="bg-dark-card border border-dark-border rounded-lg p-3">
                <div className="flex items-center justify-between">
                  <div className="font-semibold">Security Scan</div>
                  <Badge variant={badge(String(secEv?.result?.passed ? 'success' : secEv ? 'failed' : 'unknown'))}>
                    {secEv ? (secEv?.result?.passed ? 'passed' : 'failed') : '-'}
                  </Badge>
                </div>
                <div className="text-xs text-gray-400 mt-2">vulns: {String((secEv?.result?.vulnerabilities || []).length ?? '-')}</div>
                <div className="mt-2">
                  <Button variant="secondary" onClick={() => openGateDetail('Security Scan 详情', secEv)} disabled={!secEv}>
                    查看详情
                  </Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {gateEnvelope?.next_actions ? (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-gray-200">门禁阻断</div>
                <Badge variant="warning">{String(gateEnvelope.code || 'gate_block')}</Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-sm text-gray-300 mb-3">{String(gateEnvelope.message || '请求被门禁拦截')}</div>
              <div className="flex flex-wrap items-center gap-2">
                {(gateEnvelope.next_actions || []).map((a: any, idx: number) => {
                  const label = String(a?.label || a?.type || `action_${idx}`);
                  if (a?.ui && !a?.api) {
                    return (
                      <a key={idx} href={String(a.ui)} target="_blank" rel="noreferrer">
                        <Button variant="secondary">{label}</Button>
                      </a>
                    );
                  }
                  return (
                    <Button key={idx} variant={a?.recommended ? 'primary' : 'secondary'} onClick={() => execNextAction(changeId, a)} disabled={detailLoading}>
                      {label}
                    </Button>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-200">summary</div>
              {summary?.derived_state ? <Badge variant={badge(String(summary.derived_state))}>{String(summary.derived_state)}</Badge> : null}
            </div>
          </CardHeader>
          <CardContent>
            {summary ? (
              <pre className="text-xs text-gray-300 overflow-auto max-h-[220px] bg-dark-card border border-dark-border rounded-lg p-3">
                {JSON.stringify(summary, null, 2)}
              </pre>
            ) : (
              <div className="text-sm text-gray-500">暂无 summary</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">latest</div>
          </CardHeader>
          <CardContent>
            {latest ? (
              <pre className="text-xs text-gray-300 overflow-auto max-h-[320px] bg-dark-card border border-dark-border rounded-lg p-3">
                {JSON.stringify(latest, null, 2)}
              </pre>
            ) : (
              <div className="text-sm text-gray-500">暂无记录</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-gray-200">events</div>
          </CardHeader>
          <CardContent>
            <Table rowKey={(r: any) => String(r.id)} loading={detailLoading} data={ev} columns={eventColumns as any} emptyText="暂无 events" />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Change Control</h1>
          <p className="text-sm text-gray-500 mt-1">统一的变更控制台（change_id → Syscalls/Audit/Approvals）</p>
        </div>
        <Button variant="secondary" onClick={loadList} loading={loading} icon={<RotateCw size={14} />}>
          刷新
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-gray-200">列表</div>
            <div className="flex items-center gap-2">
              <Input value={q} onChange={(e: any) => setQ(e.target.value)} placeholder="按 change_id 过滤（本地过滤）" />
              <Select
                value={state}
                onChange={(v) => setState(String(v || ''))}
                options={[
                  { value: '', label: '全部状态' },
                  { value: 'blocked', label: 'blocked' },
                  { value: 'approval_required', label: 'approval_required' },
                  { value: 'success', label: 'success' },
                  { value: 'failed', label: 'failed' },
                  { value: 'unknown', label: 'unknown' },
                ]}
                placeholder="状态筛选"
              />
              <Button
                variant="secondary"
                onClick={() => {
                  setOffset(0);
                  loadList();
                }}
              >
                应用
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <Table
            rowKey={(r: any) => String(r.change_id || r.target_id)}
            loading={loading}
            data={items}
            columns={listColumns as any}
            emptyText="暂无变更记录"
          />
          <div className="flex items-center justify-between mt-3 text-xs text-gray-500">
            <div>
              total：{total}，limit：{limit}，offset：{offset}
            </div>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => setOffset(Math.max(0, offset - limit))} disabled={offset <= 0}>
                上一页
              </Button>
              <Button variant="secondary" onClick={() => setOffset(offset + limit)} disabled={offset + limit >= total}>
                下一页
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default ChangeControl;
