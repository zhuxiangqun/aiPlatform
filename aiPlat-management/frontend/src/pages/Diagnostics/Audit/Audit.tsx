import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Copy, Search } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Table } from '../../../components/ui';
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
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (filters?: { action?: string; actor_id?: string; run_id?: string; request_id?: string; limit?: number; offset?: number }) => {
    setLoading(true);
    setError(null);
    try {
      const res = await auditApi.listLogs({
        action: filters?.action ?? (action || undefined),
        actor_id: filters?.actor_id ?? (actorId || undefined),
        run_id: filters?.run_id ?? (runId || undefined),
        request_id: filters?.request_id ?? (requestId || undefined),
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
    const nextLimit = Number(searchParams.get('limit') || 50);
    const nextOffset = Number(searchParams.get('offset') || 0);

    setAction(nextAction);
    setActorId(nextActor);
    setRunId(nextRun);
    setRequestId(nextReq);
    setLimit(Number.isFinite(nextLimit) ? nextLimit : 50);
    setOffset(Number.isFinite(nextOffset) ? nextOffset : 0);

    load({
      action: nextAction || undefined,
      actor_id: nextActor || undefined,
      run_id: nextRun || undefined,
      request_id: nextReq || undefined,
      limit: Number.isFinite(nextLimit) ? nextLimit : 50,
      offset: Number.isFinite(nextOffset) ? nextOffset : 0,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const updateUrl = (next: { action?: string; actor_id?: string; run_id?: string; request_id?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    const a = next.action ?? action;
    const u = next.actor_id ?? actorId;
    const r = next.run_id ?? runId;
    const req = next.request_id ?? requestId;
    const l = next.limit ?? limit;
    const o = next.offset ?? offset;
    if (a) q.set('action', a);
    if (u) q.set('actor_id', u);
    if (r) q.set('run_id', r);
    if (req) q.set('request_id', req);
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
        key: 'request_id',
        title: 'request_id',
        dataIndex: 'request_id',
        render: (v: any) => <code className="text-xs text-gray-200">{shortId(v)}</code>,
      },
    ],
    []
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
          <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
            <Input label="action" value={action} onChange={(e: any) => setAction(e.target.value.trim())} placeholder="gateway_execute" />
            <Input label="actor_id" value={actorId} onChange={(e: any) => setActorId(e.target.value.trim())} placeholder="u_xxx" />
            <Input label="run_id" value={runId} onChange={(e: any) => setRunId(e.target.value.trim())} placeholder="run_<ulid>" />
            <Input label="request_id" value={requestId} onChange={(e: any) => setRequestId(e.target.value.trim())} placeholder="req_<ulid>" />
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
          </div>
          <div className="flex items-center justify-between mt-3">
            <div className="text-xs text-gray-500">total: {total}</div>
            <div className="flex items-center gap-2">
              <Input label="limit" type="number" value={String(limit)} onChange={(e: any) => setLimit(Number(e.target.value || 50))} />
              <Button
                icon={<Search size={16} />}
                onClick={() => {
                  setOffset(0);
                  updateUrl({ offset: 0, limit });
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
    </div>
  );
};

export default Audit;
