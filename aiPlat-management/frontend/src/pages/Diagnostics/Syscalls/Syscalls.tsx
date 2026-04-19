import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Copy, ExternalLink, RotateCw, Search, Share2 } from 'lucide-react';
import { Button, Input, Select, Table, toast } from '../../../components/ui';
import { diagnosticsApi } from '../../../services';

const Syscalls: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(100);
  const [offset, setOffset] = useState(0);

  const [statsLoading, setStatsLoading] = useState(false);
  const [stats, setStats] = useState<any | null>(null);
  const [windowHours, setWindowHours] = useState(24);
  const [topN, setTopN] = useState(10);

  const [traceId, setTraceId] = useState('');
  const [runId, setRunId] = useState('');
  const [kind, setKind] = useState<string>('');
  const [name, setName] = useState('');
  const [status, setStatus] = useState<string>('');
  const [errorContains, setErrorContains] = useState('');
  const [approvalRequestId, setApprovalRequestId] = useState('');
  const [targetType, setTargetType] = useState('');
  const [targetId, setTargetId] = useState('');

  const loadStats = async (ovr?: Partial<{ kind: string; windowHours: number; topN: number }>) => {
    setStatsLoading(true);
    try {
      const effectiveKind = ovr?.kind != null ? ovr.kind : kind;
      const effectiveWindow = ovr?.windowHours != null ? ovr.windowHours : windowHours;
      const effectiveTopN = ovr?.topN != null ? ovr.topN : topN;
      const res = await diagnosticsApi.getSyscallStats({
        window_hours: effectiveWindow,
        top_n: effectiveTopN,
        kind: effectiveKind || undefined,
      });
      setStats(res?.stats || null);
    } catch (e: any) {
      setStats(null);
      toast.error('加载统计失败', String(e?.message || ''));
    } finally {
      setStatsLoading(false);
    }
  };

  const load = async (
    ovr?: Partial<{
      limit: number;
      offset: number;
      traceId: string;
      runId: string;
      kind: string;
      name: string;
      status: string;
      errorContains: string;
      approvalRequestId: string;
      targetType: string;
      targetId: string;
    }>,
  ) => {
    setLoading(true);
    try {
      const effectiveLimit = ovr?.limit != null ? ovr.limit : limit;
      const effectiveOffset = ovr?.offset != null ? ovr.offset : offset;
      const effectiveTraceId = ovr?.traceId != null ? ovr.traceId : traceId;
      const effectiveRunId = ovr?.runId != null ? ovr.runId : runId;
      const effectiveKind = ovr?.kind != null ? ovr.kind : kind;
      const effectiveName = ovr?.name != null ? ovr.name : name;
      const effectiveStatus = ovr?.status != null ? ovr.status : status;
      const effectiveErrorContains = ovr?.errorContains != null ? ovr.errorContains : errorContains;
      const effectiveApproval = ovr?.approvalRequestId != null ? ovr.approvalRequestId : approvalRequestId;
      const effectiveTargetType = ovr?.targetType != null ? ovr.targetType : targetType;
      const effectiveTargetId = ovr?.targetId != null ? ovr.targetId : targetId;
      const res = await diagnosticsApi.listSyscalls({
        limit: effectiveLimit,
        offset: effectiveOffset,
        trace_id: effectiveTraceId || undefined,
        run_id: effectiveRunId || undefined,
        kind: effectiveKind || undefined,
        name: effectiveName || undefined,
        status: effectiveStatus || undefined,
        error_contains: effectiveErrorContains || undefined,
        approval_request_id: effectiveApproval || undefined,
        target_type: effectiveTargetType || undefined,
        target_id: effectiveTargetId || undefined,
      });
      const data = res?.syscalls || {};
      setItems(Array.isArray(data.items) ? data.items : []);
      setTotal(Number(data.total || 0));
    } catch (e: any) {
      toast.error('加载失败', String(e?.message || ''));
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [limit, offset]);

  useEffect(() => {
    loadStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [windowHours, topN]);

  // Read query params on mount (for deep links from Doctor page).
  useEffect(() => {
    const q = new URLSearchParams(location.search || '');
    const qKind = q.get('kind') || '';
    const qTrace = q.get('trace_id') || '';
    const qRun = q.get('run_id') || '';
    const qName = q.get('name') || '';
    const qStatus = q.get('status') || '';
    const qError = q.get('error_contains') || '';
    const qApproval = q.get('approval_request_id') || '';
    const qTargetType = q.get('target_type') || '';
    const qTargetId = q.get('target_id') || '';
    const qLimit = q.get('limit');
    const qOffset = q.get('offset');

    const nextLimit = qLimit ? Math.max(1, parseInt(qLimit, 10) || 100) : limit;
    const nextOffset = qOffset ? Math.max(0, parseInt(qOffset, 10) || 0) : 0;

    if (qKind || qTrace || qRun || qName || qStatus || qError || qLimit || qOffset) {
      setKind(qKind);
      setTraceId(qTrace);
      setRunId(qRun);
      setName(qName);
      setStatus(qStatus);
      setErrorContains(qError);
      setApprovalRequestId(qApproval);
      setTargetType(qTargetType);
      setTargetId(qTargetId);
      setLimit(nextLimit);
      setOffset(nextOffset);
      // Load with parsed values immediately (avoid waiting for setState)
      load({
        kind: qKind,
        traceId: qTrace,
        runId: qRun,
        name: qName,
        status: qStatus,
        errorContains: qError,
        approvalRequestId: qApproval,
        targetType: qTargetType,
        targetId: qTargetId,
        limit: nextLimit,
        offset: nextOffset,
      });
      loadStats({ kind: qKind });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const columns = useMemo(
    () => [
      {
        key: 'id',
        title: 'id',
        width: 160,
        render: (_: unknown, r: any) => (
          <div className="flex items-center gap-2">
            <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{String(r.id || '').slice(0, 10)}...</code>
            <Button variant="ghost" icon={<Copy size={14} />} onClick={() => navigator.clipboard.writeText(String(r.id || ''))} />
          </div>
        ),
      },
      { key: 'kind', title: 'kind', width: 90, render: (_: unknown, r: any) => <span className="text-gray-300">{r.kind}</span> },
      { key: 'name', title: 'name', width: 180, render: (_: unknown, r: any) => <span className="text-gray-200">{r.name}</span> },
      { key: 'status', title: 'status', width: 90, render: (_: unknown, r: any) => <span className="text-gray-400">{r.status}</span> },
      {
        key: 'trace_id',
        title: 'trace_id',
        width: 210,
        render: (_: unknown, r: any) => {
          const tid = String(r.trace_id || '');
          if (!tid) return <span className="text-xs text-gray-500">-</span>;
          return (
            <div className="flex items-center gap-1">
              <code className="text-xs text-gray-400">{tid.slice(0, 8)}...</code>
              <Button variant="ghost" icon={<Copy size={14} />} onClick={() => navigator.clipboard.writeText(tid)} />
              <Button variant="ghost" icon={<ExternalLink size={14} />} onClick={() => navigate(`/diagnostics/traces?trace_id=${encodeURIComponent(tid)}`)} />
              <Link to={`/diagnostics/links?trace_id=${encodeURIComponent(tid)}`}>
                <Button variant="ghost" icon={<Share2 size={14} />} />
              </Link>
            </div>
          );
        },
      },
      {
        key: 'run_id',
        title: 'run_id',
        width: 210,
        render: (_: unknown, r: any) => {
          const rid = String(r.run_id || '');
          if (!rid) return <span className="text-xs text-gray-500">-</span>;
          return (
            <div className="flex items-center gap-1">
              <code className="text-xs text-gray-400">{rid.slice(0, 10)}...</code>
              <Button variant="ghost" icon={<Copy size={14} />} onClick={() => navigator.clipboard.writeText(rid)} />
              <Button variant="ghost" icon={<ExternalLink size={14} />} onClick={() => navigate(`/diagnostics/runs?run_id=${encodeURIComponent(rid)}`)} />
            </div>
          );
        },
      },
      {
        key: 'duration_ms',
        title: 'ms',
        width: 80,
        align: 'right' as const,
        render: (_: unknown, r: any) => <span className="text-gray-400">{r.duration_ms != null ? Math.round(Number(r.duration_ms)) : '-'}</span>,
      },
      {
        key: 'error',
        title: 'error',
        render: (_: unknown, r: any) => <span className="text-gray-400">{r.error || '-'}</span>,
      },
    ],
    [navigate],
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-200">Syscalls</h1>
        <p className="text-sm text-gray-500 mt-1">查询 syscall_events（tool/llm/skill 调用事件）</p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <Input label="trace_id" value={traceId} onChange={(e: any) => setTraceId(e.target.value)} />
        <Input label="run_id" value={runId} onChange={(e: any) => setRunId(e.target.value)} />
        <Select
          value={kind}
          onChange={(v: string) => setKind(v)}
          options={[
            { value: '', label: 'kind(全部)' },
            { value: 'tool', label: 'tool' },
            { value: 'llm', label: 'llm' },
            { value: 'skill', label: 'skill' },
            { value: 'changeset', label: 'changeset' },
          ]}
        />
        <Input label="name(模糊)" value={name} onChange={(e: any) => setName(e.target.value)} />
        <Select
          value={status}
          onChange={(v: string) => setStatus(v)}
          options={[
            { value: '', label: 'status(全部)' },
            { value: 'success', label: 'success' },
            { value: 'failed', label: 'failed' },
            { value: 'ok', label: 'ok(legacy)' },
            { value: 'error', label: 'error(legacy)' },
          ]}
        />
        <Input label="error(模糊)" value={errorContains} onChange={(e: any) => setErrorContains(e.target.value)} />
        <Input label="approval_id" value={approvalRequestId} onChange={(e: any) => setApprovalRequestId(e.target.value)} />
        <Input label="target_type" value={targetType} onChange={(e: any) => setTargetType(e.target.value)} />
        <Input label="target_id" value={targetId} onChange={(e: any) => setTargetId(e.target.value)} />

        <Button
          icon={<Search className="w-4 h-4" />}
          onClick={() => {
            setOffset(0);
            load();
            loadStats();
          }}
          loading={loading || statsLoading}
        >
          查询
        </Button>
        <Button
          icon={<RotateCw className="w-4 h-4" />}
          onClick={() => {
            load();
            loadStats();
          }}
          loading={loading || statsLoading}
        >
          刷新
        </Button>
      </div>

      <div className="bg-dark-card rounded-xl border border-dark-border p-4">
        <div className="flex flex-wrap items-end gap-3 justify-between">
          <div>
            <div className="text-sm text-gray-400">统计（近 {windowHours} 小时）</div>
            <div className="text-xs text-gray-500 mt-1">TopN / 分布 / 失败趋势（按小时）</div>
          </div>
          <div className="flex items-end gap-3">
            <Input
              label="window_hours"
              type="number"
              value={String(windowHours)}
              onChange={(e: any) => setWindowHours(Math.max(1, Number(e.target.value || 24)))}
            />
            <Input
              label="top_n"
              type="number"
              value={String(topN)}
              onChange={(e: any) => setTopN(Math.max(1, Number(e.target.value || 10)))}
            />
            <Button variant="ghost" icon={<RotateCw className="w-4 h-4" />} onClick={() => loadStats()} loading={statsLoading}>
              刷新统计
            </Button>
          </div>
        </div>

        {!stats ? (
          <div className="text-sm text-gray-500 mt-4">{statsLoading ? '加载中...' : '暂无统计数据'}</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
            <div className="rounded-lg border border-dark-border bg-dark-hover p-3">
              <div className="text-xs text-gray-500">总量</div>
              <div className="text-lg text-gray-200 mt-1">{Number(stats.total || 0)}</div>
              <div className="text-xs text-gray-500 mt-2">
                by_status:{' '}
                {Object.entries(stats.by_status || {})
                  .map(([k, v]) => `${k}:${v}`)
                  .join(' / ') || '-'}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                by_kind:{' '}
                {Object.entries(stats.by_kind || {})
                  .map(([k, v]) => `${k}:${v}`)
                  .join(' / ') || '-'}
              </div>
            </div>

            <div className="rounded-lg border border-dark-border bg-dark-hover p-3">
              <div className="text-xs text-gray-500">Top 调用（kind/name）</div>
              <div className="mt-2 space-y-1">
                {(stats.top_names || []).slice(0, 8).map((x: any) => (
                  <div key={`${x.kind}-${x.name}`} className="text-xs text-gray-300 flex justify-between gap-2">
                    <span className="truncate">
                      {x.kind}/{x.name}
                    </span>
                    <span className="text-gray-500">{Number(x.count || 0)}</span>
                  </div>
                ))}
                {(stats.top_names || []).length === 0 && <div className="text-xs text-gray-500">-</div>}
              </div>
            </div>

            <div className="rounded-lg border border-dark-border bg-dark-hover p-3">
              <div className="text-xs text-gray-500">Top 失败（kind/name）</div>
              <div className="mt-2 space-y-1">
                {(stats.top_failed || []).slice(0, 8).map((x: any) => (
                  <div key={`${x.kind}-${x.name}`} className="text-xs text-red-300 flex justify-between gap-2">
                    <span className="truncate">
                      {x.kind}/{x.name}
                    </span>
                    <span className="text-gray-500">{Number(x.count || 0)}</span>
                  </div>
                ))}
                {(stats.top_failed || []).length === 0 && <div className="text-xs text-gray-500">-</div>}
              </div>
              <div className="text-xs text-gray-500 mt-3">失败趋势（hourly）</div>
              <div className="mt-1 space-y-1">
                {(stats.failed_trend_hourly || []).slice(-6).map((x: any) => (
                  <div key={String(x.bucket)} className="text-xs text-gray-400 flex justify-between gap-2">
                    <span className="truncate">{String(x.bucket).slice(5, 16)}</span>
                    <span className="text-gray-500">{Number(x.failed || 0)}</span>
                  </div>
                ))}
                {(stats.failed_trend_hourly || []).length === 0 && <div className="text-xs text-gray-500">-</div>}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
        <Table columns={columns} data={items} rowKey="id" loading={loading} emptyText="暂无 syscall events" />
      </div>

      <div className="flex items-center justify-between text-sm text-gray-400">
        <div>total: {total}</div>
        <div className="flex items-center gap-2">
          <Input label="limit" type="number" value={String(limit)} onChange={(e: any) => setLimit(Number(e.target.value || 100))} />
          <Button onClick={() => setOffset(Math.max(0, offset - limit))} disabled={offset <= 0}>
            上一页
          </Button>
          <Button onClick={() => setOffset(offset + limit)} disabled={offset + limit >= total}>
            下一页
          </Button>
        </div>
      </div>
    </div>
  );
};

export default Syscalls;
