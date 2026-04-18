import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Copy, ExternalLink, Search } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Select, Table, Tabs } from '../../../components/ui';
import { diagnosticsApi } from '../../../services';

type Mode = 'trace_id' | 'execution_id' | 'graph_run_id';

const shortId = (id?: string, left: number = 8, right: number = 6) => {
  if (!id) return '-';
  if (id.length <= left + right + 3) return id;
  return `${id.slice(0, left)}...${id.slice(-right)}`;
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
    const spans = searchParams.get('include_spans') === 'true';
    setIncludeSpans(spans);
    if (executionId) {
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
    // aiPlat v2: run_id is used as execution_id (time-sortable ULID)
    if (v.startsWith('run_') || v.startsWith('exec-') || v.startsWith('execution_')) return 'execution_id';
    // assume UUID-like => trace_id by default
    if (/^[0-9a-fA-F-]{32,}$/.test(v)) return 'trace_id';
    // fallback: graph_run_id
    return 'graph_run_id';
  };

  const query = useMemo(() => {
    if (!value) return {};
    if (mode === 'execution_id') return { execution_id: value };
    if (mode === 'graph_run_id') return { graph_run_id: value };
    return { trace_id: value };
  }, [mode, value]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await diagnosticsApi.linksUi({ ...(query as any), include_spans: includeSpans });
      setData(res);
    } catch (e: any) {
      setError(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // auto load when query exists
    if (value) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, value, includeSpans]);

  const setUrl = () => {
    const next = new URLSearchParams();
    if (mode === 'trace_id') next.set('trace_id', value);
    if (mode === 'execution_id') next.set('execution_id', value);
    if (mode === 'graph_run_id') next.set('graph_run_id', value);
    if (includeSpans) next.set('include_spans', 'true');
    setSearchParams(next);
  };

  const summary = data?.summary || {};
  const trace = data?.trace || null;
  const executions = data?.executions || null;
  const graphRuns = data?.graph_runs || null;
  const lineage = Array.isArray(data?.lineage) ? data.lineage : [];

  const runs = Array.isArray(graphRuns?.runs) ? graphRuns.runs : [];
  const agentExecs = Array.isArray(executions?.items?.agent_executions)
    ? executions.items.agent_executions.map((x: any) => ({ ...x, type: x.type || 'agent' }))
    : [];
  const skillExecs = Array.isArray(executions?.items?.skill_executions)
    ? executions.items.skill_executions.map((x: any) => ({ ...x, type: x.type || 'skill' }))
    : [];

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
      { key: 'start_time', title: 'start_time', dataIndex: 'start_time' },
      { key: 'duration_ms', title: 'duration_ms', dataIndex: 'duration_ms', align: 'right' as const },
    ],
    [highlightId, highlightMode]
  );

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-gray-200">Links</h1>
            <p className="text-sm text-gray-500 mt-1">输入任意 ID 联动查询（trace / executions / graph runs / lineage）</p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" icon={<ArrowLeft size={16} />} onClick={() => navigate(-1)}>
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
              >
                spans: {includeSpans ? 'on' : 'off'}
              </Button>
              <Button onClick={() => { setUrl(); load(); }} loading={loading} icon={<Search size={16} />}>
                查询
              </Button>
            </div>
          </div>
          <div className="text-xs text-gray-500 mt-2">
            提示：Links 会联动返回 trace / executions / graph_runs / lineage；默认不含 spans，可手动打开。
          </div>
        </CardHeader>
        <CardContent>
          {error && <div className="text-sm text-error mb-3">{error}</div>}
          {!data ? (
            <div className="text-sm text-gray-500">请输入 ID 并查询</div>
          ) : (
            <div className="space-y-4">
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
                  <div className="flex items-center gap-2 mt-2">
                    <Badge variant={summary.actions?.has_trace ? 'success' : 'warning'}>{summary.actions?.has_trace ? 'has trace' : 'no trace'}</Badge>
                    <Badge variant={summary.actions?.can_resume ? 'info' : 'default'}>{summary.actions?.can_resume ? 'can resume' : 'readonly'}</Badge>
                  </div>
                </div>
              </div>

              <Tabs
                tabs={[
                  {
                    key: 'trace',
                    label: `Trace`,
                    children: (
                      <pre className="text-xs text-gray-200 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
                        {JSON.stringify(trace, null, 2)}
                      </pre>
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
                    key: 'runs',
                    label: `Graph Runs (${runs.length})`,
                    children: (
                      <Table
                        columns={runColumns as any}
                        data={runs}
                        rowKey="run_id"
                        onRow={(r: any) => ({
                          className: highlightMode === 'graph_run_id' && highlightId === r.run_id ? 'bg-primary-light/20' : '',
                        })}
                      />
                    ),
                  },
                  {
                    key: 'lineage',
                    label: `Lineage (${lineage.length})`,
                    children: (
                      <pre className="text-xs text-gray-200 bg-dark-hover border border-dark-border rounded-lg p-3 overflow-auto">
                        {JSON.stringify(lineage, null, 2)}
                      </pre>
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
