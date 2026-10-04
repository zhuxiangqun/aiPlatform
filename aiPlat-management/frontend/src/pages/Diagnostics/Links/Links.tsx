import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Copy, ExternalLink, Search } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Select, Table, Tabs } from '../../../components/ui';
import { diagnosticsApi } from '../../../services';

type Mode = 'trace_id' | 'execution_id' | 'graph_run_id' | 'change_id';

const shortId = (id?: string, left: number = 8, right: number = 6) => {
  if (!id) return '-';
  if (id.length <= left + right + 3) return id;
  return `${id.slice(0, left)}...${id.slice(-right)}`;
};

/** Format epoch seconds / ms / ISO for Links tables. Heal start=0 via end - duration. */
const formatTs = (raw: unknown, row?: { end_time?: unknown; duration_ms?: unknown }): string => {
  let n = typeof raw === 'number' ? raw : Number(raw);
  if ((!Number.isFinite(n) || n <= 0) && row) {
    const end = typeof row.end_time === 'number' ? row.end_time : Number(row.end_time);
    const dur = typeof row.duration_ms === 'number' ? row.duration_ms : Number(row.duration_ms);
    if (Number.isFinite(end) && end > 0 && Number.isFinite(dur) && dur > 0) {
      n = end - dur / 1000;
    }
  }
  if (!Number.isFinite(n) || n <= 0) {
    const s = raw == null || raw === '' ? '' : String(raw);
    return s && s !== '0' ? s : '—';
  }
  const ms = n > 1e12 ? n : n * 1000;
  try {
    return new Date(ms).toLocaleString();
  } catch {
    return String(raw);
  }
};

const Links: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [value, setValue] = useState('');
  const [mode, setMode] = useState<Mode>('trace_id');
  const [includeSpans, setIncludeSpans] = useState(false);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // init from URL
  useEffect(() => {
    const traceId = searchParams.get('trace_id');
    const executionId = searchParams.get('execution_id');
    const runId = searchParams.get('graph_run_id');
    const changeId = searchParams.get('change_id');
    const spansParam = searchParams.get('include_spans');
    // From Agent「查看诊断详情」默认打开 spans，否则 Trace 只有空壳元数据
    const spans =
      spansParam === 'true' || (spansParam !== 'false' && !!executionId);
    setIncludeSpans(spans);
    if (changeId) {
      setMode('change_id');
      setValue(changeId);
    } else if (executionId) {
      setMode('execution_id');
      setValue(executionId);
    } else if (runId) {
      setMode('graph_run_id');
      setValue(runId);
    } else if (traceId) {
      setMode('trace_id');
      setValue(traceId);
    }
  }, [searchParams]);

  const guessMode = (input: string): Mode => {
    const v = input.trim();
    if (!v) return 'trace_id';
    if (v.startsWith('chg-')) return 'change_id';
    // aiPlat v2: run_id is used as execution_id (time-sortable ULID / hex suffix)
    if (
      v.startsWith('run_') ||
      v.startsWith('run-') ||
      v.startsWith('exec-') ||
      v.startsWith('execution_') ||
      v.startsWith('execution-')
    ) {
      return 'execution_id';
    }
    // assume UUID-like => trace_id by default
    if (/^[0-9a-fA-F-]{32,}$/.test(v)) return 'trace_id';
    // fallback: graph_run_id
    return 'graph_run_id';
  };

  const query = useMemo(() => {
    if (!value) return {};
    if (mode === 'execution_id') return { execution_id: value };
    if (mode === 'graph_run_id') return { graph_run_id: value };
    if (mode === 'change_id') return { change_id: value };
    return { trace_id: value };
  }, [mode, value]);

  const load = async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      if (mode === 'change_id') {
        const res = await diagnosticsApi.getChangeControl(value, { limit: 200, offset: 0 });
        if (signal?.aborted) return;
        setData({ mode: 'change_id', change: res?.change || null });
      } else {
        const res = await diagnosticsApi.linksUi({ ...(query as any), include_spans: includeSpans });
        if (signal?.aborted) return;
        setData(res);
      }
    } catch (e: any) {
      if (signal?.aborted) return;
      const msg = String(e?.message || '');
      setError(
        msg.includes('aborted') || msg.includes('AbortError') || msg.includes('timeout')
          ? '加载超时（25s）。请确认 management/core 已启动后点「查询」重试。'
          : msg || '加载失败',
      );
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  };

  useEffect(() => {
    if (!value) return;
    const ac = new AbortController();
    void load(ac.signal);
    return () => ac.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, value, includeSpans]);

  const setUrl = () => {
    const next = new URLSearchParams();
    if (mode === 'trace_id') next.set('trace_id', value);
    if (mode === 'execution_id') next.set('execution_id', value);
    if (mode === 'graph_run_id') next.set('graph_run_id', value);
    if (mode === 'change_id') next.set('change_id', value);
    if (includeSpans) next.set('include_spans', 'true');
    setSearchParams(next);
  };

  const summary = data?.summary || {};
  const trace = data?.trace || null;
  const executions = data?.executions || null;
  const graphRuns = data?.graph_runs || null;
  const lineage = Array.isArray(data?.lineage) ? data.lineage : [];
  const traceSpans: any[] = Array.isArray(trace?.spans) ? trace.spans : [];
  const runGraph = data?.run_graph && typeof data.run_graph === 'object' ? data.run_graph : null;
  const runGraphNodes: any[] = Array.isArray(runGraph?.nodes) ? runGraph.nodes : [];
  const syscallItems: any[] = Array.isArray(data?.syscalls?.items) ? data.syscalls.items : [];
  const primaryExec = data?.primary_execution && typeof data.primary_execution === 'object' ? data.primary_execution : null;

  const runs = Array.isArray(graphRuns?.runs) ? graphRuns.runs : [];
  const agentExecs = Array.isArray(executions?.items?.agent_executions)
    ? executions.items.agent_executions.map((x: any) => ({ ...x, type: x.type || 'agent' }))
    : [];
  const skillExecs = Array.isArray(executions?.items?.skill_executions)
    ? executions.items.skill_executions.map((x: any) => ({ ...x, type: x.type || 'skill' }))
    : [];
  const displayRunId = summary.run_id || summary.execution_id || (mode === 'execution_id' ? value : '') || '';
  const isWorkspaceAgentView =
    mode === 'execution_id' ||
    String(graphRuns?.source || '') === 'run_graph' ||
    String(graphRuns?.source || '') === 'execution_stub' ||
    Boolean(primaryExec?.agent_id);

  const runStatus = String(
    primaryExec?.status ||
      agentExecs[0]?.status ||
      skillExecs[0]?.status ||
      summary?.exec_status ||
      trace?.status ||
      summary?.status ||
      '',
  ).toLowerCase();
  const runError = String(
    primaryExec?.error || agentExecs[0]?.error || skillExecs[0]?.error || summary?.exec_error || trace?.attributes?.error || '',
  ).trim();
  const verdict = (() => {
    if (!data || mode === 'change_id') return null;
    if (runStatus === 'running' || runStatus === 'accepted' || runStatus === 'started') {
      return { label: '执行中', hint: '尚未结束，可稍后刷新。', tone: 'blue' as const };
    }
    if (runStatus === 'failed' || runStatus === 'error' || runStatus === 'timeout') {
      return {
        label: runStatus === 'timeout' ? '超时' : '未成功',
        hint:
          runError ||
          summary.diagnosis_hint ||
          '请看 Trace spans / Syscalls / Executions.error（Graph Runs 对单次 Agent 通常为空）。',
        tone: 'red' as const,
      };
    }
    if (runStatus === 'completed' || runStatus === 'ok' || runStatus === 'success') {
      if (runError) return { label: '已结束（有告警）', hint: runError, tone: 'amber' as const };
      return {
        label: '已正常结束',
        hint: `耗时 ${
          primaryExec?.duration_ms != null || trace?.duration_ms != null
            ? `${(Number(primaryExec?.duration_ms ?? trace?.duration_ms) / 1000).toFixed(1)}s`
            : '—'
        } · spans ${includeSpans ? summary.span_count ?? traceSpans.length : '（请打开 spans）'} · syscalls ${
          summary.syscall_counts?.total ?? syscallItems.length
        }`,
        tone: 'green' as const,
      };
    }
    if (!runStatus) return null;
    return { label: `状态 ${runStatus}`, hint: '可打开 spans / Syscalls 或 Executions 核对。', tone: 'gray' as const };
  })();
  const verdictClass: Record<string, string> = {
    green: 'border-green-700/40 bg-green-950/30 text-green-100',
    red: 'border-red-700/40 bg-red-950/30 text-red-100',
    amber: 'border-amber-700/40 bg-amber-950/30 text-amber-100',
    blue: 'border-blue-700/40 bg-blue-950/30 text-blue-100',
    gray: 'border-gray-600/40 bg-gray-900/40 text-gray-200',
  };

  const highlightId = value;
  const highlightMode = mode;

  const runColumns = useMemo(
    () => [
      {
        key: 'run_id',
        title: 'run_id',
        dataIndex: 'run_id',
        render: (val: string) => (
          <div className="flex items-center gap-2">
            <code className={`text-xs ${highlightMode === 'graph_run_id' && highlightId === val ? 'text-primary' : 'text-gray-200'}`}>
              {shortId(val)}
            </code>
            <Button variant="ghost" icon={<Copy size={14} />} onClick={() => navigator.clipboard.writeText(val)} />
            <Button variant="ghost" icon={<ExternalLink size={14} />} onClick={() => navigate(`/diagnostics/graphs/${val}`)} />
          </div>
        ),
      },
      { key: 'graph_name', title: 'graph_name', dataIndex: 'graph_name' },
      { key: 'status', title: 'status', dataIndex: 'status' },
      { key: 'start_time', title: 'start_time', dataIndex: 'start_time' },
      { key: 'duration_ms', title: 'duration_ms', dataIndex: 'duration_ms', align: 'right' as const },
    ],
    [navigate, highlightId, highlightMode]
  );

  const execColumns = useMemo(
    () => [
      {
        key: 'execution_id',
        title: 'execution_id',
        dataIndex: 'execution_id',
        render: (val: string) => (
          <div className="flex items-center gap-2">
            <code className={`text-xs ${highlightMode === 'execution_id' && highlightId === val ? 'text-primary' : 'text-gray-200'}`}>
              {shortId(val)}
            </code>
            <Button variant="ghost" icon={<Copy size={14} />} onClick={() => navigator.clipboard.writeText(val)} />
            <Link to={`/diagnostics/links?execution_id=${encodeURIComponent(val)}`}>
              <Button variant="ghost" icon={<ExternalLink size={14} />} />
            </Link>
          </div>
        ),
      },
      { key: 'type', title: 'type', dataIndex: 'type' },
      { key: 'status', title: 'status', dataIndex: 'status' },
      {
        key: 'error',
        title: 'error',
        dataIndex: 'error',
        render: (val: any, row: any) => {
          const detail = row?.metadata?.error_detail;
          const detailCode = typeof detail?.code === 'string' ? detail.code : (typeof row?.error_code === 'string' ? row.error_code : '');
          const detailMsg = typeof detail?.message === 'string' ? detail.message : '';
          const text0 = detailMsg || (typeof val === 'string' ? val : '');
          const text = detailCode ? `[${detailCode}] ${text0}` : text0;
          if (!text) return <span className="text-xs text-gray-500">-</span>;
          const short = text.length > 80 ? `${text.slice(0, 77)}...` : text;
          const isFailed = String(row?.status || '').toLowerCase().includes('fail');
          return (
            <span
              className={`text-xs ${isFailed ? 'text-red-300' : 'text-gray-300'}`}
              title={text}
            >
              {short}
            </span>
          );
        },
      },
      {
        key: 'start_time',
        title: 'start_time',
        dataIndex: 'start_time',
        render: (val: any, row: any) => (
          <span className="text-xs text-gray-300 whitespace-nowrap">{formatTs(val, row)}</span>
        ),
      },
      {
        key: 'duration_ms',
        title: 'duration_ms',
        dataIndex: 'duration_ms',
        align: 'right' as const,
        render: (val: any) => {
          const n = Number(val);
          if (!Number.isFinite(n) || n <= 0) return <span className="text-xs text-gray-500">—</span>;
          return <span className="text-xs text-gray-300">{n < 1000 ? `${Math.round(n)}ms` : `${(n / 1000).toFixed(1)}s`}</span>;
        },
      },
    ],
    [highlightId, highlightMode]
  );

  return (
    <div className="space-y-4">
      <Link to="/diagnostics" className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-200 transition-colors">
        <ArrowLeft className="w-3 h-3" />返回诊断中心
      </Link>
      <div>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-gray-200">Links</h1>
            <p className="text-sm text-gray-500 mt-1">输入任意 ID 联动查询（trace / executions / graph runs / lineage）</p>
          </div>
          <div className="flex items-center gap-2">
              <Button variant="secondary" icon={<ArrowLeft size={16} />} onClick={() => {
                if (window.history.length > 1) { navigate(-1); return; }
                const ref = document.referrer;
                if (ref && ref.includes(window.location.host)) { window.location.href = ref; return; }
                navigate('/workspace/agents');
              }}>
              返回上一页
            </Button>
          </div>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col md:flex-row gap-3 md:items-center md:justify-between">
            <div className="flex gap-2 flex-1">
              <Select
                value={mode}
                onChange={(v) => setMode(v as Mode)}
                options={[
                  { value: 'trace_id', label: 'trace_id' },
                  { value: 'execution_id', label: 'execution_id' },
                  { value: 'graph_run_id', label: 'graph_run_id' },
                  { value: 'change_id', label: 'change_id' },
                ]}
              />
              <Input
                value={value}
                placeholder="trace_id / execution_id / graph_run_id"
                onChange={(e: any) => {
                  const v = e.target.value;
                  setValue(v.trim());
                  // best-effort auto-detect when user pastes a value
                  if (v.length >= 8) setMode(guessMode(v));
                }}
              />
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                onClick={() => value && navigator.clipboard.writeText(value)}
                icon={<Copy size={16} />}
              >
                复制
              </Button>
              <Button
                variant={includeSpans ? 'primary' : 'secondary'}
                onClick={() => setIncludeSpans((v) => !v)}
                disabled={mode === 'change_id'}
              >
                spans: {includeSpans ? 'on' : 'off'}
              </Button>
              <Button onClick={() => { setUrl(); load(); }} loading={loading} icon={<Search size={16} />}>
                查询
              </Button>
            </div>
          </div>
          <div className="text-xs text-gray-500 mt-2">
            提示：Links 支持 trace/execution/graph_run 的联动查询；也支持 change_id 快捷生成变更证据链入口。
          </div>
        </CardHeader>
        <CardContent>
          {error && <div className="text-sm text-error mb-3">{error}</div>}
          {loading && !data && (
            <div className="text-sm text-gray-400 mb-3">正在查询执行关联数据…</div>
          )}
          {!data ? (
            <div className="text-sm text-gray-500">
              {loading
                ? '请稍候…'
                : error
                  ? '查询未返回数据。若刚执行完 Agent，可刷新后重试；或确认 execution_id / trace_id 是否正确。'
                  : '请输入 ID 并查询'}
            </div>
          ) : mode === 'change_id' ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                <div className="p-3 bg-dark-bg rounded-lg">
                  <div className="text-xs text-gray-400 mb-1">change_id</div>
                  <div className="flex items-center gap-2">
                    <code className="text-xs break-all text-gray-200">{value || '-'}</code>
                    <Button variant="ghost" icon={<Copy size={14} />} onClick={() => value && navigator.clipboard.writeText(value)} />
                    <Button variant="ghost" icon={<ExternalLink size={14} />} onClick={() => navigate(`/diagnostics/change-control/${encodeURIComponent(value)}`)} />
                  </div>
                </div>
                <div className="p-3 bg-dark-bg rounded-lg">
                  <div className="text-xs text-gray-400 mb-1">latest</div>
                  <div className="text-xs text-gray-200">
                    <code>{String(data?.change?.latest?.name || '-')}</code>
                    <span className="ml-2 text-gray-400">{String(data?.change?.latest?.status || '-')}</span>
                  </div>
                </div>
                <div className="p-3 bg-dark-bg rounded-lg">
                  <div className="text-xs text-gray-400 mb-1">Syscalls</div>
                  <Button
                    variant="secondary"
                    onClick={() => navigate(`/diagnostics/syscalls?kind=changeset&target_type=change&target_id=${encodeURIComponent(value)}`)}
                  >
                    打开
                  </Button>
                </div>
                <div className="p-3 bg-dark-bg rounded-lg">
                  <div className="text-xs text-gray-400 mb-1">联动</div>
                  <div className="flex items-center gap-2">
                    {data?.change?.links?.audit_ui ? (
                      <a className="text-xs underline text-gray-300 hover:text-white" href={String(data.change.links.audit_ui)} target="_blank" rel="noreferrer">
                        Audit <ExternalLink size={12} className="inline ml-1" />
                      </a>
                    ) : (
                      <span className="text-xs text-gray-500">-</span>
                    )}
                    {data?.change?.links?.approvals_ui ? (
                      <a
                        className="text-xs underline text-gray-300 hover:text-white"
                        href={String(data.change.links.approvals_ui)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Approvals <ExternalLink size={12} className="inline ml-1" />
                      </a>
                    ) : null}
                    {data?.change?.links?.runs_ui ? (
                      <a className="text-xs underline text-gray-300 hover:text-white" href={String(data.change.links.runs_ui)} target="_blank" rel="noreferrer">
                        Runs <ExternalLink size={12} className="inline ml-1" />
                      </a>
                    ) : null}
                    {data?.change?.links?.traces_ui ? (
                      <a className="text-xs underline text-gray-300 hover:text-white" href={String(data.change.links.traces_ui)} target="_blank" rel="noreferrer">
                        Traces <ExternalLink size={12} className="inline ml-1" />
                      </a>
                    ) : null}
                    {data?.change?.links?.links_ui ? (
                      <a className="text-xs underline text-gray-300 hover:text-white" href={String(data.change.links.links_ui)} target="_blank" rel="noreferrer">
                        Links <ExternalLink size={12} className="inline ml-1" />
                      </a>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className="text-xs text-gray-500">
                说明：change_id 模式下不做 trace 联动聚合；请通过 Change Control 详情页/ Syscalls 展开查看证据与上下游关联。
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {verdict && (
                <div className={`p-3 rounded-lg border text-sm ${verdictClass[verdict.tone]}`}>
                  <div className="font-medium">{verdict.label}</div>
                  <div className="text-xs opacity-80 mt-1">{verdict.hint}</div>
                </div>
              )}
              {/* Summary cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
                <div className="p-3 bg-dark-bg rounded-lg">
                  <div className="text-xs text-gray-400 mb-1">trace_id</div>
                  <div className="flex items-center gap-2">
                    <code
                      className={`text-xs break-all ${
                        highlightMode === 'trace_id' && highlightId && highlightId === summary.trace_id ? 'text-primary' : 'text-gray-200'
                      }`}
                    >
                      {summary.trace_id || '-'}
                    </code>
                    {summary.trace_id && (
                      <>
                        <Button variant="ghost" icon={<Copy size={14} />} onClick={() => navigator.clipboard.writeText(summary.trace_id)} />
                        <Button variant="ghost" icon={<ExternalLink size={14} />} onClick={() => navigate(`/diagnostics/traces/${summary.trace_id}`)} />
                      </>
                    )}
                  </div>
                </div>
                <div className="p-3 bg-dark-bg rounded-lg">
                  <div className="text-xs text-gray-400 mb-1">run_id</div>
                  <div className="flex items-center gap-2">
                    <code
                      className={`text-xs break-all ${
                        highlightMode === 'graph_run_id' && highlightId && highlightId === summary.run_id ? 'text-primary' : 'text-gray-200'
                      }`}
                    >
                      {summary.run_id || '-'}
                    </code>
                    {summary.run_id && (
                      <>
                        <Button variant="ghost" icon={<Copy size={14} />} onClick={() => navigator.clipboard.writeText(summary.run_id)} />
                        <Button variant="ghost" icon={<ExternalLink size={14} />} onClick={() => navigate(`/diagnostics/graphs/${summary.run_id}`)} />
                      </>
                    )}
                  </div>
                </div>
                <div className="p-3 bg-dark-bg rounded-lg">
                  <div className="text-xs text-gray-400 mb-1">executions</div>
                  <div className="text-sm font-medium text-gray-100">
                    {summary.execution_counts?.total ?? (agentExecs.length + skillExecs.length)}
                  </div>
                  <div className="text-xs text-gray-500">
                    agents {summary.execution_counts?.agents ?? agentExecs.length} / skills {summary.execution_counts?.skills ?? skillExecs.length}
                  </div>
                </div>
                <div className="p-3 bg-dark-bg rounded-lg">
                  <div className="text-xs text-gray-400 mb-1">graph runs</div>
                  <div className="text-sm font-medium text-gray-100">{summary.graph_run_counts?.total ?? (graphRuns?.total || 0)}</div>
                  <div className="text-xs text-gray-500 mt-1">
                    {summary.graph_run_counts?.source === 'run_graph' || summary.run_graph_counts?.has_graph
                      ? `观测树 nodes ${summary.run_graph_counts?.nodes ?? runGraphNodes.length}`
                      : 'LangGraph resume 链（Agent 通常无此项）'}
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <Badge variant={summary.actions?.has_trace ? 'success' : 'warning'}>{summary.actions?.has_trace ? 'has trace' : 'no trace'}</Badge>
                    <Badge variant={summary.actions?.has_run_graph ? 'success' : 'default'}>
                      {summary.actions?.has_run_graph ? 'has run_graph' : 'no run_graph'}
                    </Badge>
                    <Badge variant={summary.actions?.can_resume ? 'info' : 'default'}>{summary.actions?.can_resume ? 'can resume' : 'readonly'}</Badge>
                  </div>
                </div>
              </div>

              <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group mb-3">
                <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
                <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
                  <div><span className="text-gray-300">run_id / execution_id</span><span className="ml-2 text-gray-600">Run / 执行唯一 ID，可复制/跳转</span></div>
                  <div><span className="text-gray-300">graph_name / type</span><span className="ml-2 text-gray-600">Graph 名称 / 执行类型（agent/skill）</span></div>
                  <div><span className="text-gray-300">status</span><span className="ml-2 text-gray-600">执行状态</span></div>
                  <div><span className="text-gray-300">start_time</span><span className="ml-2 text-gray-600">开始时间</span></div>
                  <div><span className="text-gray-300">duration_ms</span><span className="ml-2 text-gray-600">耗时（毫秒）</span></div>
                  <div><span className="text-gray-300">error</span><span className="ml-2 text-gray-600">错误详情（含 error_code）</span></div>
                </div>
              </details>

              <Tabs
                defaultActiveKey={mode === 'execution_id' ? 'executions' : 'trace'}
                tabs={[
                  {
                    key: 'trace',
                    label: `Trace${includeSpans ? ` · spans ${traceSpans.length}` : ''}`,
                    children: (
                      <div className="space-y-3">
                        {!includeSpans && (
                          <div className="text-xs text-amber-200/90 bg-amber-950/20 border border-amber-800/40 rounded-lg px-3 py-2">
                            当前 spans: off，Trace 只有元数据。点上方「spans: on」可看步骤轨迹（llm / skill / tool）。
                          </div>
                        )}
                        {includeSpans && traceSpans.length > 0 && (
                          <div className="bg-dark-hover border border-dark-border rounded-lg p-3 max-h-64 overflow-auto">
                            <div className="text-xs text-gray-400 mb-2">步骤轨迹（{traceSpans.length}）</div>
                            <ol className="space-y-1 text-xs text-gray-200 font-mono">
                              {traceSpans.slice(0, 80).map((s: any, i: number) => (
                                <li key={String(s.span_id || i)} className="flex gap-2">
                                  <span className="text-gray-500 w-5 shrink-0">{i + 1}.</span>
                                  <span className={s.status === 'failed' || s.status === 'error' ? 'text-red-300' : ''}>
                                    {String(s.name || s.kind || 'span')}
                                  </span>
                                  <span className="text-gray-500">{String(s.status || '')}</span>
                                  {s.duration_ms != null ? (
                                    <span className="text-gray-600">{Number(s.duration_ms).toFixed?.(0) ?? s.duration_ms}ms</span>
                                  ) : null}
                                </li>
                              ))}
                            </ol>
                          </div>
                        )}
                        <pre className="text-xs text-gray-200 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto max-h-80">
                          {JSON.stringify(trace, null, 2)}
                        </pre>
                      </div>
                    ),
                  },
                  {
                    key: 'executions',
                    label: `Executions (${agentExecs.length + skillExecs.length})`,
                    children: (
                      <Tabs
                        tabs={[
                          {
                            key: 'agent',
                            label: `Agent (${agentExecs.length})`,
                            children: (
                              <Table
                                columns={execColumns as any}
                                data={agentExecs.map((x: any) => ({ ...x, type: 'agent' }))}
                                rowKey={(r: any) => String(r.execution_id || Math.random())}
                                onRow={(r: any) => ({
                                  className: highlightMode === 'execution_id' && highlightId === r.execution_id ? 'bg-primary-light/20' : '',
                                })}
                              />
                            ),
                          },
                          {
                            key: 'skill',
                            label: `Skill (${skillExecs.length})`,
                            children: (
                              <Table
                                columns={execColumns as any}
                                data={skillExecs.map((x: any) => ({ ...x, type: 'skill' }))}
                                rowKey={(r: any) => String(r.execution_id || Math.random())}
                                onRow={(r: any) => ({
                                  className: highlightMode === 'execution_id' && highlightId === r.execution_id ? 'bg-primary-light/20' : '',
                                })}
                              />
                            ),
                          },
                        ]}
                      />
                    ),
                  },
                  {
                    key: 'run_graph',
                    label: `Run Graph (${runGraphNodes.length})`,
                    children: (
                      <div className="space-y-3">
                        <div className="text-xs text-gray-400">
                          Agent/Skill 观测树（ExecutionViewer 同源）。LangGraph resume 的 Graph Runs 是另一套表。
                          {summary.run_id ? (
                            <button
                              type="button"
                              className="ml-2 text-primary hover:underline"
                              onClick={() => navigate(`/diagnostics/runs?run_id=${encodeURIComponent(String(summary.run_id))}`)}
                            >
                              打开执行流程
                            </button>
                          ) : null}
                        </div>
                        {runGraphNodes.length === 0 ? (
                          <div className="text-xs text-amber-200/90 bg-amber-950/20 border border-amber-800/40 rounded-lg px-3 py-2">
                            无 run_graph 节点。常见原因：执行在首个 LLM 调用前被超时杀掉，或观测写入失败。可对照 Trace spans / Executions.error。
                          </div>
                        ) : (
                          <ol className="space-y-1 text-xs text-gray-200 font-mono bg-dark-hover border border-dark-border rounded-lg p-3 max-h-72 overflow-auto">
                            {runGraphNodes.slice(0, 100).map((n: any, i: number) => (
                              <li key={String(n.node_id || n.id || i)} className="flex gap-2 flex-wrap">
                                <span className="text-gray-500 w-5 shrink-0">{i + 1}.</span>
                                <span>{String(n.kind || 'node')}:{String(n.name || n.label || '')}</span>
                                <span className="text-gray-500">{String(n.status || '')}</span>
                                {n.duration_ms != null ? (
                                  <span className="text-gray-600">{Number(n.duration_ms).toFixed?.(0) ?? n.duration_ms}ms</span>
                                ) : null}
                              </li>
                            ))}
                          </ol>
                        )}
                      </div>
                    ),
                  },
                  {
                    key: 'runs',
                    label: `Graph Runs (${runs.length})`,
                    children: (
                      <div className="space-y-2">
                        {runs.length === 0 && (
                          <div className="text-xs text-gray-500 px-1">
                            无 LangGraph graph_runs。Workspace Agent 执行走 run_graph，请看「Run Graph」页签。
                          </div>
                        )}
                        <Table
                          columns={runColumns as any}
                          data={runs}
                          rowKey="run_id"
                          onRow={(r: any) => ({
                            className: highlightMode === 'graph_run_id' && highlightId === r.run_id ? 'bg-primary-light/20' : '',
                          })}
                        />
                      </div>
                    ),
                  },
                  {
                    key: 'lineage',
                    label: `Lineage (${lineage.length})`,
                    children: (
                      <div className="space-y-2">
                        {lineage.length === 1 && lineage[0]?.source === 'execution_stub' && (
                          <div className="text-xs text-gray-500">
                            Agent 单次执行无父 resume 链；以下为执行 stub（非多跳 lineage）。
                          </div>
                        )}
                        <pre className="text-xs text-gray-200 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
                          {JSON.stringify(lineage, null, 2)}
                        </pre>
                      </div>
                    ),
                  },
                ]}
              />
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default Links;
