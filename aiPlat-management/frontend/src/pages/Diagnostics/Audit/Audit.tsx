import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
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

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await auditApi.listLogs({
        action: action || undefined,
        actor_id: actorId || undefined,
        run_id: runId || undefined,
        request_id: requestId || undefined,
        limit,
        offset,
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
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [limit, offset]);

  const columns = useMemo(
    () => [
      { key: 'created_at', title: 'time', dataIndex: 'created_at', width: 150 },
      {
        key: 'action',
        title: 'action',
        dataIndex: 'action',
        render: (v: any) => <code className="text-xs text-gray-200">{String(v)}</code>,
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
          <div className="flex items-center justify-between mt-3">
            <div className="text-xs text-gray-500">total: {total}</div>
            <div className="flex items-center gap-2">
              <Input label="limit" type="number" value={String(limit)} onChange={(e: any) => setLimit(Number(e.target.value || 50))} />
              <Button icon={<Search size={16} />} onClick={() => { setOffset(0); load(); }} loading={loading}>
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
            <Button onClick={() => setOffset(Math.max(0, offset - limit))} disabled={offset <= 0}>
              上一页
            </Button>
            <Button onClick={() => setOffset(offset + limit)} disabled={offset + limit >= total}>
              下一页
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default Audit;

