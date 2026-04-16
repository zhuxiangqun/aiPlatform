import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Copy, ExternalLink, Share2 } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Pagination, Table } from '../../../components/ui';
import { diagnosticsApi } from '../../../services';

const toBadgeVariant = (status: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  if (status === 'healthy' || status === 'success' || status === 'completed') return 'success';
  if (status === 'degraded' || status === 'warn' || status === 'warning') return 'warning';
  if (status === 'unhealthy' || status === 'error' || status === 'failed') return 'error';
  if (status === 'running') return 'info';
  return 'default';
};

const Traces: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const limit = Number(searchParams.get('limit') || '50');
  const offset = Number(searchParams.get('offset') || '0');
  const status = searchParams.get('status') || '';
  const traceId = searchParams.get('trace_id') || '';

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = traceId
        ? await diagnosticsApi.getTrace(traceId, { limit, offset })
        : await diagnosticsApi.listTraces({ limit, offset, status: status || undefined });
      setData(res);
    } catch (e: any) {
      setError(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [limit, offset, status, traceId]);

  const traces = useMemo(() => {
    // list mode: { layer, supported, traces: { traces: [...] } }
    if (Array.isArray(data?.traces?.traces)) return data.traces.traces;
    // detail mode shouldn't render list
    return [];
  }, [data]);

  const total = Number(data?.traces?.total || 0);
  const currentPage = Math.floor(offset / limit) + 1;

  const columns = useMemo(
    () => [
      {
        title: 'trace_id',
        dataIndex: 'trace_id',
        key: 'trace_id',
        render: (val: string) => (
          <div className="flex items-center gap-2">
            <code className="text-xs text-gray-200">{val}</code>
            <Button
              variant="ghost"
              onClick={() => navigator.clipboard.writeText(val)}
              icon={<Copy size={14} />}
            />
            <Link to={`/diagnostics/traces/${val}`}>
              <Button variant="ghost" icon={<ExternalLink size={14} />} />
            </Link>
          </div>
        ),
      },
      { title: 'name', dataIndex: 'name', key: 'name' },
      {
        title: 'status',
        dataIndex: 'status',
        key: 'status',
        render: (val: string) => <Badge variant={toBadgeVariant(val)}>{val}</Badge>,
      },
      { title: 'start_time', dataIndex: 'start_time', key: 'start_time' },
      { title: 'end_time', dataIndex: 'end_time', key: 'end_time' },
      {
        title: 'actions',
        key: 'actions',
        render: (_: any, record: any) => (
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              icon={<ExternalLink size={14} />}
              onClick={() => navigate(`/diagnostics/traces/${record.trace_id}`)}
            />
            <Link to={`/diagnostics/links?trace_id=${encodeURIComponent(record.trace_id)}`}>
              <Button variant="ghost" icon={<Share2 size={14} />} />
            </Link>
          </div>
        ),
      },
    ],
    [navigate]
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-gray-200">Traces</h1>
        <p className="text-sm text-gray-500 mt-1">链路追踪列表（默认不加载 spans）</p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col md:flex-row gap-3 md:items-center md:justify-between">
            <div className="flex gap-2">
              <Input
                value={traceId}
                placeholder="按 trace_id 精确查询（可选）"
                onChange={(e: any) => {
                  const v = e.target.value.trim();
                  const next = new URLSearchParams(searchParams);
                  if (v) next.set('trace_id', v);
                  else next.delete('trace_id');
                  next.set('offset', '0');
                  setSearchParams(next);
                }}
              />
              <Input
                value={status}
                placeholder="status（可选）"
                onChange={(e: any) => {
                  const v = e.target.value.trim();
                  const next = new URLSearchParams(searchParams);
                  if (v) next.set('status', v);
                  else next.delete('status');
                  next.set('offset', '0');
                  setSearchParams(next);
                }}
              />
            </div>
            <Button onClick={load} loading={loading}>
              刷新
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {error && <div className="text-sm text-error mb-3">{error}</div>}
          <Table columns={columns as any} data={traces} rowKey="trace_id" loading={loading} />
          <div className="mt-4">
            <Pagination
              current={currentPage}
              total={total}
              pageSize={limit}
              onChange={(page) => {
                const next = new URLSearchParams(searchParams);
                next.set('offset', String((page - 1) * limit));
                setSearchParams(next);
              }}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default Traces;
