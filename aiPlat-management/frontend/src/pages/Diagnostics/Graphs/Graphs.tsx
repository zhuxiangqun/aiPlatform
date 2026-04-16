import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Copy, ExternalLink, Share2 } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Pagination, Table } from '../../../components/ui';
import { diagnosticsApi } from '../../../services';

const toBadgeVariant = (status: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  if (status === 'completed' || status === 'success' || status === 'healthy') return 'success';
  if (status === 'degraded' || status === 'warn' || status === 'warning') return 'warning';
  if (status === 'failed' || status === 'error' || status === 'unhealthy') return 'error';
  if (status === 'running') return 'info';
  return 'default';
};

const Graphs: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const limit = Number(searchParams.get('limit') || '50');
  const offset = Number(searchParams.get('offset') || '0');
  const graphName = searchParams.get('graph_name') || '';
  const status = searchParams.get('status') || '';
  const traceId = searchParams.get('trace_id') || '';

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await diagnosticsApi.listGraphRuns({
        limit,
        offset,
        graph_name: graphName || undefined,
        status: status || undefined,
        trace_id: traceId || undefined,
      });
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
  }, [limit, offset, graphName, status, traceId]);

  const runs = useMemo(() => data?.runs?.runs || data?.runs || [], [data]);
  const total = Number(data?.runs?.total || 0);
  const currentPage = Math.floor(offset / limit) + 1;

  const columns = useMemo(
    () => [
      {
        title: 'run_id',
        dataIndex: 'run_id',
        key: 'run_id',
        render: (val: string) => (
          <div className="flex items-center gap-2">
            <code className="text-xs text-gray-200">{val}</code>
            <Button variant="ghost" onClick={() => navigator.clipboard.writeText(val)} icon={<Copy size={14} />} />
            <Link to={`/diagnostics/graphs/${val}`}>
              <Button variant="ghost" icon={<ExternalLink size={14} />} />
            </Link>
          </div>
        ),
      },
      { title: 'graph_name', dataIndex: 'graph_name', key: 'graph_name' },
      { title: 'status', dataIndex: 'status', key: 'status', render: (v: string) => <Badge variant={toBadgeVariant(v)}>{v}</Badge> },
      { title: 'start_time', dataIndex: 'start_time', key: 'start_time' },
      { title: 'duration_ms', dataIndex: 'duration_ms', key: 'duration_ms' },
      {
        title: 'trace_id',
        dataIndex: 'trace_id',
        key: 'trace_id',
        render: (val: string) =>
          val ? (
            <div className="flex items-center gap-2">
              <code className="text-xs text-gray-200">{val}</code>
              <Button variant="ghost" onClick={() => navigator.clipboard.writeText(val)} icon={<Copy size={14} />} />
              <Button variant="ghost" icon={<ExternalLink size={14} />} onClick={() => navigate(`/diagnostics/traces/${val}`)} />
              <Link to={`/diagnostics/links?trace_id=${encodeURIComponent(val)}`}>
                <Button variant="ghost" icon={<Share2 size={14} />} />
              </Link>
            </div>
          ) : (
            '-'
          ),
      },
    ],
    [navigate]
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-gray-200">Graph Runs</h1>
        <p className="text-sm text-gray-500 mt-1">执行 runs / checkpoints / 恢复</p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col md:flex-row gap-3 md:items-center md:justify-between">
            <div className="flex gap-2 flex-1">
              <Input
                value={graphName}
                placeholder="graph_name（可选）"
                onChange={(e: any) => {
                  const v = e.target.value.trim();
                  const next = new URLSearchParams(searchParams);
                  if (v) next.set('graph_name', v);
                  else next.delete('graph_name');
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
              <Input
                value={traceId}
                placeholder="trace_id（可选）"
                onChange={(e: any) => {
                  const v = e.target.value.trim();
                  const next = new URLSearchParams(searchParams);
                  if (v) next.set('trace_id', v);
                  else next.delete('trace_id');
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
          <Table columns={columns as any} data={runs} rowKey="run_id" loading={loading} />
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

export default Graphs;
