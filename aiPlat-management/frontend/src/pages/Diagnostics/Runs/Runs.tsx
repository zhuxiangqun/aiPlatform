import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Copy, RefreshCw } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Table } from '../../../components/ui';
import { runApi } from '../../../services';

const shortId = (id?: string, left: number = 10, right: number = 8) => {
  if (!id) return '-';
  if (id.length <= left + right + 3) return id;
  return `${id.slice(0, left)}...${id.slice(-right)}`;
};

const toBadgeVariant = (status?: string): 'success' | 'warning' | 'error' | 'info' | 'default' => {
  const s = String(status || '').toLowerCase();
  if (s === 'completed' || s === 'success') return 'success';
  if (s.includes('approval')) return 'warning';
  if (s.includes('fail') || s === 'error') return 'error';
  if (s === 'running' || s === 'accepted') return 'info';
  return 'default';
};

const Runs: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [runId, setRunId] = useState('');
  const [run, setRun] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [lastSeq, setLastSeq] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const rid = searchParams.get('run_id');
    if (rid) setRunId(rid);
  }, [searchParams]);

  const load = async (opts: { reset?: boolean } = {}) => {
    const rid = runId.trim();
    if (!rid) return;
    setLoading(true);
    setError(null);
    try {
      const [r, ev] = await Promise.all([
        runApi.get(rid),
        runApi.listEvents(rid, { after_seq: opts.reset ? 0 : lastSeq, limit: 200 }),
      ]);
      setRun(r);
      const newItems = Array.isArray(ev?.items) ? ev.items : [];
      setEvents((prev) => (opts.reset ? newItems : [...prev, ...newItems]));
      setLastSeq(Number(ev?.last_seq || lastSeq));
    } catch (e: any) {
      setError(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  const waitOnce = async () => {
    const rid = runId.trim();
    if (!rid) return;
    setLoading(true);
    setError(null);
    try {
      const res = await runApi.wait(rid, { timeout_ms: 30000, after_seq: lastSeq });
      if (res?.run) setRun(res.run);
      const newItems = Array.isArray(res?.events) ? res.events : [];
      if (newItems.length) setEvents((prev) => [...prev, ...newItems]);
      setLastSeq(Number(res?.last_seq || lastSeq));
    } catch (e: any) {
      setError(e?.message || '等待失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (runId) load({ reset: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  const columns = useMemo(
    () => [
      { key: 'seq', title: 'seq', dataIndex: 'seq', width: 80 },
      {
        key: 'type',
        title: 'type',
        dataIndex: 'type',
        render: (v: any) => <code className="text-xs text-gray-200">{String(v)}</code>,
      },
      {
        key: 'created_at',
        title: 'created_at',
        dataIndex: 'created_at',
        render: (v: any) => <span className="text-xs text-gray-500">{v ? String(v) : '-'}</span>,
      },
      {
        key: 'payload',
        title: 'payload',
        dataIndex: 'payload',
        render: (v: any) => (
          <pre className="text-[11px] text-gray-300 whitespace-pre-wrap max-w-[640px] overflow-hidden">
            {JSON.stringify(v || {}, null, 2)}
          </pre>
        ),
      },
    ],
    []
  );

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Runs</h1>
          <p className="text-sm text-gray-500 mt-1">按 run_id 查询 run 摘要与 run_events（tool_start/tool_end/approval 等）</p>
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
          <div className="flex flex-col md:flex-row gap-3 md:items-center md:justify-between">
            <div className="flex gap-2 flex-1">
              <Input
                value={runId}
                placeholder="run_<ulid>"
                onChange={(e: any) => setRunId(e.target.value.trim())}
              />
            </div>
            <div className="flex items-center gap-2">
              <Button variant="secondary" icon={<Copy size={16} />} onClick={() => runId && navigator.clipboard.writeText(runId)}>
                复制
              </Button>
              <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={() => load({ reset: true })} loading={loading}>
                刷新
              </Button>
              <Button onClick={waitOnce} loading={loading}>
                wait（30s）
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  const next = new URLSearchParams();
                  if (runId) next.set('run_id', runId);
                  setSearchParams(next);
                }}
              >
                固定到 URL
              </Button>
            </div>
          </div>
          {error && <div className="text-sm text-error mt-2">{error}</div>}
        </CardHeader>
        <CardContent>
          {!run && <div className="text-sm text-gray-500">请输入 run_id</div>}
          {run && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="rounded-lg border border-dark-border bg-dark-hover p-3">
                <div className="text-xs text-gray-500">run_id</div>
                <div className="mt-1 flex items-center gap-2">
                  <code className="text-xs text-gray-200">{shortId(run.run_id)}</code>
                  <Button variant="ghost" icon={<Copy size={14} />} onClick={() => navigator.clipboard.writeText(run.run_id)} />
                </div>
              </div>
              <div className="rounded-lg border border-dark-border bg-dark-hover p-3">
                <div className="text-xs text-gray-500">status</div>
                <div className="mt-1">
                  <Badge variant={toBadgeVariant(run.status)}>{String(run.status || '-')}</Badge>
                </div>
              </div>
              <div className="rounded-lg border border-dark-border bg-dark-hover p-3">
                <div className="text-xs text-gray-500">trace_id</div>
                <div className="mt-1 flex items-center gap-2">
                  <code className="text-xs text-gray-200">{shortId(run.trace_id)}</code>
                  {run.trace_id && (
                    <Link to={`/diagnostics/links?trace_id=${encodeURIComponent(run.trace_id)}`}>
                      <Button variant="ghost">打开 Links</Button>
                    </Link>
                  )}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
        <Table columns={columns as any} data={events} rowKey={(r: any) => String(r.seq)} loading={loading} emptyText="暂无 events" />
      </div>
    </div>
  );
};

export default Runs;

