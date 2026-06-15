import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Copy, ExternalLink, Share2 } from 'lucide-react';

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

      <Link to="/diagnostics" className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 transition-colors mb-4">
        <ArrowLeft className="w-3 h-3" />返回诊断中心
      </Link>

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
          <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group mb-3">
            <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
            <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
              <div><span className="text-gray-300">trace_id</span><span className="ml-2 text-gray-600">链路追踪唯一 ID，可复制/跳转详情</span></div>
              <div><span className="text-gray-300">name</span><span className="ml-2 text-gray-600">Trace 名称</span></div>
              <div><span className="text-gray-300">status</span><span className="ml-2 text-gray-600">healthy/success/completed/degraded/warn/failed/error</span></div>
              <div><span className="text-gray-300">start_time</span><span className="ml-2 text-gray-600">追踪开始时间</span></div>
              <div><span className="text-gray-300">end_time</span><span className="ml-2 text-gray-600">追踪结束时间</span></div>
              <div><span className="text-gray-300">操作</span><span className="ml-2 text-gray-600">跳转详情 / 查看关联 Links</span></div>
            </div>
          </details>
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
