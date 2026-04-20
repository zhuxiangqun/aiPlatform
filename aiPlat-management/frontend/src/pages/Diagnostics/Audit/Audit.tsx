import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Copy, Search } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Modal, Table } from '../../../components/ui';
import { auditApi } from '../../../services';

const shortId = (id?: string, left: number = 10, right: number = 8) => {
  if (!id) return '-';
  if (id.length <= left + right + 3) return id;
  return `${id.slice(0, left)}...${id.slice(-right)}`;
};

const toBadgeVariant = (status?: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  const s = String(status || '').toLowerCase();
  if (s === 'ok' || s === 'success') return 'success';
  if (s.includes('warn')) return 'warning';
  if (s.includes('fail') || s === 'error') return 'error';
  return 'default';
};

const Audit: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [action, setAction] = useState('');
  const [actorId, setActorId] = useState('');
  const [runId, setRunId] = useState('');
  const [requestId, setRequestId] = useState('');
  const [changeId, setChangeId] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [status, setStatus] = useState('');
  const [createdAfter, setCreatedAfter] = useState<number | undefined>(undefined);
  const [createdBefore, setCreatedBefore] = useState<number | undefined>(undefined);
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailItem, setDetailItem] = useState<any>(null);

  const load = async (filters?: { action?: string; actor_id?: string; run_id?: string; request_id?: string; change_id?: string; limit?: number; offset?: number }) => {
    setLoading(true);
    setError(null);
    try {
      const res = await auditApi.listLogs({
        action: filters?.action ?? (action || undefined),
        actor_id: filters?.actor_id ?? (actorId || undefined),
        run_id: filters?.run_id ?? (runId || undefined),
        request_id: filters?.request_id ?? (requestId || undefined),
        change_id: filters?.change_id ?? (changeId || undefined),
        tenant_id: tenantId || undefined,
        status: status || undefined,
        created_after: createdAfter,
        created_before: createdBefore,
        limit: filters?.limit ?? limit,
        offset: filters?.offset ?? offset,
      });
      setItems(res.items || []);
      setTotal(Number(res.total || 0));
    } catch (e: any) {
      setError(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // URL 驱动：支持 /diagnostics/audit?action=...&run_id=...
    const nextAction = searchParams.get('action') || '';
    const nextActor = searchParams.get('actor_id') || '';
    const nextRun = searchParams.get('run_id') || '';
    const nextReq = searchParams.get('request_id') || '';
    const nextChange = searchParams.get('change_id') || '';
    const nextTenant = searchParams.get('tenant_id') || '';
    const nextStatus = searchParams.get('status') || '';
    const nextAfter = searchParams.get('created_after');
    const nextBefore = searchParams.get('created_before');
    const nextLimit = Number(searchParams.get('limit') || 50);
    const nextOffset = Number(searchParams.get('offset') || 0);

    setAction(nextAction);
    setActorId(nextActor);
    setRunId(nextRun);
    setRequestId(nextReq);
    setChangeId(nextChange);
    setTenantId(nextTenant);
    setStatus(nextStatus);
    setCreatedAfter(nextAfter ? Number(nextAfter) : undefined);
    setCreatedBefore(nextBefore ? Number(nextBefore) : undefined);
    setLimit(Number.isFinite(nextLimit) ? nextLimit : 50);
    setOffset(Number.isFinite(nextOffset) ? nextOffset : 0);

    load({
      action: nextAction || undefined,
      actor_id: nextActor || undefined,
      run_id: nextRun || undefined,
      request_id: nextReq || undefined,
      change_id: nextChange || undefined,
      limit: Number.isFinite(nextLimit) ? nextLimit : 50,
      offset: Number.isFinite(nextOffset) ? nextOffset : 0,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const updateUrl = (next: {
    action?: string;
    actor_id?: string;
    run_id?: string;
    request_id?: string;
    change_id?: string;
    tenant_id?: string;
    status?: string;
    created_after?: number | undefined;
    created_before?: number | undefined;
    limit?: number;
    offset?: number;
  }) => {
    const q = new URLSearchParams();
    const a = next.action ?? action;
    const u = next.actor_id ?? actorId;
    const r = next.run_id ?? runId;
    const req = next.request_id ?? requestId;
    const chg = next.change_id ?? changeId;
    const t = next.tenant_id ?? tenantId;
    const st = next.status ?? status;
    const ca = next.created_after ?? createdAfter;
    const cb = next.created_before ?? createdBefore;
    const l = next.limit ?? limit;
    const o = next.offset ?? offset;
    if (a) q.set('action', a);
    if (u) q.set('actor_id', u);
    if (r) q.set('run_id', r);
    if (req) q.set('request_id', req);
    if (chg) q.set('change_id', chg);
    if (t) q.set('tenant_id', t);
    if (st) q.set('status', st);
    if (ca != null) q.set('created_after', String(ca));
    if (cb != null) q.set('created_before', String(cb));
    q.set('limit', String(l));
    q.set('offset', String(o));
    setSearchParams(q);
  };

  const columns = useMemo(
    () => [
      { key: 'created_at', title: 'time', dataIndex: 'created_at', width: 150 },
      {
        key: 'action',
        title: 'action',
        dataIndex: 'action',
        render: (v: any) => (
          <button
            className="text-left"
            onClick={() => updateUrl({ action: String(v || ''), offset: 0 })}
            title="点击按 action 筛选"
          >
            <code className="text-xs text-gray-200">{String(v)}</code>
          </button>
        ),
      },
      {
        key: 'status',
        title: 'status',
        dataIndex: 'status',
        width: 110,
        render: (v: any) => <Badge variant={toBadgeVariant(v)}>{String(v || '-')}</Badge>,
      },
      {
        key: 'actor_id',
        title: 'actor',
        dataIndex: 'actor_id',
        render: (v: any) => <span className="text-xs text-gray-300">{String(v || '-')}</span>,
      },
      {
        key: 'run_id',
        title: 'run_id',
        dataIndex: 'run_id',
        render: (v: any) => (
          <div className="flex items-center gap-2">
            <code className="text-xs text-gray-200">{shortId(v)}</code>
            {v && (
              <>
                <Button variant="ghost" icon={<Copy size={14} />} onClick={() => navigator.clipboard.writeText(String(v))} />
                <Link to={`/diagnostics/runs?run_id=${encodeURIComponent(String(v))}`}>
                  <Button variant="ghost">打开 Runs</Button>
                </Link>
                <Button variant="ghost" onClick={() => updateUrl({ run_id: String(v), offset: 0 })}>
                  筛选本 run
                </Button>
                <Button variant="ghost" onClick={() => updateUrl({ run_id: String(v), action: 'tool_policy_denied', offset: 0 })}>
                  策略拦截
                </Button>
              </>
            )}
          </div>
        ),
      },
      {
        key: 'change_id',
        title: 'change_id',
        dataIndex: 'change_id',
        width: 150,
        render: (v: any) =>
          v ? (
            <div className="flex items-center gap-2">
              <code className="text-xs text-gray-200">{shortId(String(v), 8, 4)}</code>
              <Button variant="ghost" icon={<Copy size={14} />} onClick={() => navigator.clipboard.writeText(String(v))} />
              <Button variant="ghost" onClick={() => updateUrl({ change_id: String(v), offset: 0 })}>
                筛选
              </Button>
            </div>
          ) : (
            <span className="text-xs text-gray-500">-</span>
          ),
      },
      {
        key: 'tenant_id',
        title: 'tenant',
        dataIndex: 'tenant_id',
        width: 120,
        render: (v: any) => (
          <button className="text-left" onClick={() => updateUrl({ tenant_id: String(v || ''), offset: 0 })} title="点击按 tenant_id 筛选">
            <code className="text-xs text-gray-200">{shortId(v, 6, 4)}</code>
          </button>
        ),
      },
      {
        key: 'trace_id',
        title: 'trace_id',
        dataIndex: 'trace_id',
        width: 140,
        render: (v: any) =>
          v ? (
            <Link to={`/diagnostics/links?trace_id=${encodeURIComponent(String(v))}`}>
              <Button variant="ghost">{shortId(String(v), 6, 4)}</Button>
            </Link>
          ) : (
            <span className="text-xs text-gray-500">-</span>
          ),
      },
      {
        key: 'resource',
        title: 'resource',
        render: (_: any, row: any) => (
          <span className="text-xs text-gray-300">
            {String(row.resource_type || '-')}/{String(row.resource_id || '-')}
          </span>
        ),
      },
      {
        key: 'detail',
        title: 'detail',
        width: 90,
        render: (_: any, row: any) => (
          <Button
            variant="secondary"
            onClick={() => {
              setDetailItem(row);
              setDetailOpen(true);
            }}
          >
            查看
          </Button>
        ),
      },
      {
        key: 'request_id',
        title: 'request_id',
        dataIndex: 'request_id',
        render: (v: any) => <code className="text-xs text-gray-200">{shortId(v)}</code>,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [action, actorId, runId, requestId, changeId, tenantId, status, createdAfter, createdBefore]
  );

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Audit Logs</h1>
          <p className="text-sm text-gray-500 mt-1">核心执行与审批等关键操作的审计日志（best-effort）</p>
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
          <div className="grid grid-cols-1 md:grid-cols-6 gap-2">
            <Input label="action" value={action} onChange={(e: any) => setAction(e.target.value.trim())} placeholder="gateway_execute" />
            <Input label="actor_id" value={actorId} onChange={(e: any) => setActorId(e.target.value.trim())} placeholder="u_xxx" />
            <Input label="run_id" value={runId} onChange={(e: any) => setRunId(e.target.value.trim())} placeholder="run_<ulid>" />
            <Input label="request_id" value={requestId} onChange={(e: any) => setRequestId(e.target.value.trim())} placeholder="req_<ulid>" />
            <Input label="change_id" value={changeId} onChange={(e: any) => setChangeId(e.target.value.trim())} placeholder="chg_xxx" />
            <Input label="tenant_id" value={tenantId} onChange={(e: any) => setTenantId(e.target.value.trim())} placeholder="t1" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-6 gap-2 mt-3">
            <div className="md:col-span-5" />
            <Input label="status" value={status} onChange={(e: any) => setStatus(e.target.value.trim())} placeholder="ok/denied/approval_required" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-3">
            <Input
              label="created_after（epoch s）"
              type="number"
              value={createdAfter == null ? '' : String(createdAfter)}
              onChange={(e: any) => setCreatedAfter(e.target.value ? Number(e.target.value) : undefined)}
              placeholder="例如：1710000000"
            />
            <Input
              label="created_before（epoch s）"
              type="number"
              value={createdBefore == null ? '' : String(createdBefore)}
              onChange={(e: any) => setCreatedBefore(e.target.value ? Number(e.target.value) : undefined)}
              placeholder="例如：1710003600"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2 mt-3">
            <Button variant="secondary" onClick={() => updateUrl({ action: 'gateway_execute', offset: 0 })}>
              gateway_execute
            </Button>
            <Button variant="secondary" onClick={() => updateUrl({ action: 'tool_policy_denied', offset: 0 })}>
              tool_policy_denied
            </Button>
            <Button variant="secondary" onClick={() => updateUrl({ action: 'tool_policy_approval_required', offset: 0 })}>
              tool_policy_approval_required
            </Button>
            <Button variant="secondary" onClick={() => updateUrl({ action: 'approval_approve', offset: 0 })}>
              approval_approve
            </Button>
            <Button variant="secondary" onClick={() => updateUrl({ action: 'approval_reject', offset: 0 })}>
              approval_reject
            </Button>
            <Button variant="secondary" onClick={() => updateUrl({ action: '', offset: 0 })}>
              清空 action
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                const now = Math.floor(Date.now() / 1000);
                updateUrl({ created_after: now - 3600, created_before: undefined, offset: 0 });
              }}
            >
              最近 1h
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                const now = Math.floor(Date.now() / 1000);
                updateUrl({ created_after: now - 86400, created_before: undefined, offset: 0 });
              }}
            >
              最近 24h
            </Button>
            <Button
              variant="secondary"
              onClick={() => updateUrl({ created_after: undefined, created_before: undefined, offset: 0 })}
            >
              清空时间
            </Button>
          </div>
          <div className="flex items-center justify-between mt-3">
            <div className="text-xs text-gray-500">total: {total}</div>
            <div className="flex items-center gap-2">
              <Input label="limit" type="number" value={String(limit)} onChange={(e: any) => setLimit(Number(e.target.value || 50))} />
              <Button
                icon={<Search size={16} />}
                onClick={() => {
                  setOffset(0);
                  updateUrl({ offset: 0, limit, action, actor_id: actorId, run_id: runId, request_id: requestId, change_id: changeId, tenant_id: tenantId, status, created_after: createdAfter, created_before: createdBefore });
                }}
                loading={loading}
              >
                查询
              </Button>
            </div>
          </div>
          {error && <div className="text-sm text-error mt-2">{error}</div>}
        </CardHeader>
        <CardContent>
          <div className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
            <Table columns={columns as any} data={items} rowKey="id" loading={loading} emptyText="暂无审计记录" />
          </div>
          <div className="flex items-center justify-end gap-2 text-sm text-gray-400 mt-3">
            <Button onClick={() => updateUrl({ offset: Math.max(0, offset - limit) })} disabled={offset <= 0}>
              上一页
            </Button>
            <Button onClick={() => updateUrl({ offset: offset + limit })} disabled={offset + limit >= total}>
              下一页
            </Button>
          </div>
        </CardContent>
      </Card>

      <Modal open={detailOpen} onClose={() => setDetailOpen(false)} title="Audit Detail" width={900}>
        <div className="space-y-3">
          <div className="text-xs text-gray-500">
            action: <code className="text-xs text-gray-200">{String(detailItem?.action || '-')}</code> ｜ status:{' '}
            <code className="text-xs text-gray-200">{String(detailItem?.status || '-')}</code>
          </div>
          <pre className="text-[11px] text-gray-200 whitespace-pre-wrap">
            {JSON.stringify(detailItem || {}, null, 2)}
          </pre>
        </div>
      </Modal>
    </div>
  );
};

export default Audit;
