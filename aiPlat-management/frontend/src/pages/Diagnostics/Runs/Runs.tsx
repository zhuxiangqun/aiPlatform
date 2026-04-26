import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Copy, RefreshCw, Ban, RotateCcw } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Input, Table, Tabs, Textarea, toast } from '../../../components/ui';
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
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [runId, setRunId] = useState('');
  const [run, setRun] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [lastSeq, setLastSeq] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'events' | 'evaluation'>('events');
  const [evaluation, setEvaluation] = useState<any | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [manualReport, setManualReport] = useState('{\n  "pass": false,\n  "score": { "functionality": 0 },\n  "issues": []\n}');
  const [evalUrl, setEvalUrl] = useState('');
  const [evalProjectId, setEvalProjectId] = useState('');
  const [evalExpectedTags, setEvalExpectedTags] = useState('login,create,save');
  const [evalStepsJson, setEvalStepsJson] = useState('[]');
  const [evalTagExpectationsJson, setEvalTagExpectationsJson] = useState(
    '{\n  "login": { "text_contains": ["登录"], "max_console_errors": 0, "max_network_5xx": 0, "max_duration_ms": 8000 },\n  "create": { "max_console_errors": 0, "max_network_5xx": 0 },\n  "save": { "max_console_errors": 0, "max_network_5xx": 0 }\n}'
  );
  const [evalTagTemplate, setEvalTagTemplate] = useState('webapp_basic');
  const [runState, setRunState] = useState<any | null>(null);
  const [runStateText, setRunStateText] = useState('{\n  "schema_version": "0.1",\n  "task": "",\n  "todo": [],\n  "open_issues": [],\n  "next_step": "",\n  "locked": false\n}');
  const [runStateLock, setRunStateLock] = useState(false);
  const [evalPolicy, setEvalPolicy] = useState<any | null>(null);
  const [evalPolicyText, setEvalPolicyText] = useState(
    '{\n  "schema_version": "0.1",\n  "thresholds": { "functionality_min": 7 },\n  "weights": {\n    "functionality": 0.55,\n    "product_depth": 0.2,\n    "design_ux": 0.15,\n    "code_architecture": 0.1\n  },\n  "regression_gate": {\n    "max_new_console_errors": 0,\n    "max_new_network_5xx": 0,\n    "max_new_network_4xx": 5\n  }\n}'
  );

  const parseRunStateText = () => {
    try {
      return JSON.parse(runStateText);
    } catch {
      return null;
    }
  };

  const setTodoStatus = (todoId: string, completed: boolean) => {
    const obj = parseRunStateText();
    if (!obj || typeof obj !== 'object') return;
    const todo = Array.isArray((obj as any).todo) ? (obj as any).todo : [];
    const next = todo.map((t: any) => {
      if (!t || typeof t !== 'object') return t;
      if (String(t.id) !== String(todoId)) return t;
      return { ...t, status: completed ? 'completed' : 'pending' };
    });
    (obj as any).todo = next;
    setRunStateText(JSON.stringify(obj, null, 2));
  };

  const autoNextStepFromTodo = () => {
    const obj = parseRunStateText();
    if (!obj || typeof obj !== 'object') return;
    const todo = Array.isArray((obj as any).todo) ? (obj as any).todo : [];
    const rank = (p: string) => {
      const s = String(p || '').toUpperCase();
      if (s === 'P0') return 0;
      if (s === 'P1') return 1;
      if (s === 'P2') return 2;
      return 9;
    };
    const pending = todo.filter((t: any) => t && typeof t === 'object' && String(t.status || '').toLowerCase() !== 'completed' && String(t.status || '').toLowerCase() !== 'done');
    pending.sort((a: any, b: any) => rank(a.priority) - rank(b.priority));
    if (pending[0]?.title) {
      (obj as any).next_step = `执行 todo: ${String(pending[0].title)}`;
      setRunStateText(JSON.stringify(obj, null, 2));
    } else {
      toast.info('没有未完成的 todo');
    }
  };

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

  const cancel = async () => {
    const rid = runId.trim();
    if (!rid) return;
    setLoading(true);
    setError(null);
    try {
      await runApi.cancel(rid, { reason: 'ui_cancel' });
      await load({ reset: true });
    } catch (e: any) {
      setError(e?.message || '取消失败');
    } finally {
      setLoading(false);
    }
  };

  const retry = async () => {
    const rid = runId.trim();
    if (!rid) return;
    setLoading(true);
    setError(null);
    try {
      const res: any = await runApi.retry(rid);
      const newId = String(res?.new_run_id || res?.run_id || '');
      if (newId) {
        setRunId(newId);
        const next = new URLSearchParams();
        next.set('run_id', newId);
        setSearchParams(next);
      } else {
        await load({ reset: true });
      }
    } catch (e: any) {
      setError(e?.message || '重试失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (runId) load({ reset: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  const loadEvaluation = async () => {
    const rid = runId.trim();
    if (!rid) return;
    try {
      const res: any = await runApi.getLatestEvaluation(rid);
      setEvaluation(res?.item || null);
    } catch (e: any) {
      toast.error(e?.message || '加载评估失败');
    }
  };

  const loadRunState = async () => {
    const rid = runId.trim();
    if (!rid) return;
    try {
      const res: any = await runApi.getLatestRunState(rid);
      const item = res?.item || null;
      setRunState(item);
      const payload = item?.payload || item?.state || item?.item?.payload || null;
      if (payload) {
        setRunStateText(JSON.stringify(payload, null, 2));
        setRunStateLock(Boolean(payload.locked));
      }
    } catch (e: any) {
      toast.error(e?.message || '加载 RunState 失败');
    }
  };

  const loadEvalPolicy = async () => {
    try {
      const res: any = await runApi.getLatestEvaluationPolicy();
      const item = res?.item || null;
      setEvalPolicy(item);
      const payload = item?.payload || null;
      if (payload) setEvalPolicyText(JSON.stringify(payload, null, 2));
    } catch (e: any) {
      toast.error(e?.message || '加载评估策略失败');
    }
  };

  const [projectPolicy, setProjectPolicy] = useState<any | null>(null);
  const [projectPolicyText, setProjectPolicyText] = useState('{}');
  const [projectMergedPolicyText, setProjectMergedPolicyText] = useState('');

  const severityBadge = (sev: any) => {
    const s = String(sev || '').toUpperCase();
    if (s === 'P0') return 'error';
    if (s === 'P1') return 'warning';
    if (s === 'P2') return 'info';
    return 'default';
  };

  const runAutoEvaluate = async () => {
    const rid = runId.trim();
    if (!rid) return;
    setEvaluating(true);
    try {
      let steps: any = undefined;
      try {
        const parsed = JSON.parse(evalStepsJson || '[]');
        steps = Array.isArray(parsed) ? parsed : undefined;
      } catch {
        steps = undefined;
      }
      let tag_expectations: any = undefined;
      try {
        const parsed = JSON.parse(evalTagExpectationsJson || '{}');
        tag_expectations = parsed && typeof parsed === 'object' ? parsed : undefined;
      } catch {
        tag_expectations = undefined;
      }
      const expected_tags = evalExpectedTags
        .split(',')
        .map((x) => x.trim())
        .filter(Boolean);
      const res: any = await runApi.autoEvaluate(rid, {
        evaluator: 'auto-llm',
        project_id: evalProjectId.trim() || undefined,
        url: evalUrl.trim() || undefined,
        steps,
        expected_tags,
        tag_expectations,
        tag_template: evalTagTemplate.trim() || undefined,
      });
      toast.success('已生成评估报告');
      setEvaluation(res?.report ? { payload: res.report, artifact_id: res.artifact_id, created_at: Date.now() / 1000 } : null);
      await loadEvaluation();
    } catch (e: any) {
      toast.error(e?.message || '自动评估失败（请检查 LLM 配置）');
    } finally {
      setEvaluating(false);
    }
  };

  const saveGlobalPolicy = async () => {
    try {
      const obj = JSON.parse(evalPolicyText);
      await runApi.upsertEvaluationPolicy(obj);
      toast.success('已保存评估策略');
      await loadEvalPolicy();
    } catch (e: any) {
      toast.error(e?.message || '保存失败（请检查 JSON 格式）');
    }
  };

  const saveProjectPolicy = async () => {
    const pid = evalProjectId.trim();
    if (!pid) return;
    try {
      const obj = JSON.parse(projectPolicyText || '{}');
      const res: any = await runApi.upsertProjectEvaluationPolicy(pid, obj, 'merge');
      toast.success('已保存项目策略');
      if (res?.links?.change_control_ui) toast.info(`变更控制：${res.links.change_control_ui}`);
      await loadProjectPolicy();
    } catch (e: any) {
      toast.error(e?.message || '保存失败（请检查 JSON 格式 / 或需审批）');
    }
  };

  const loadProjectPolicy = async () => {
    const pid = evalProjectId.trim();
    if (!pid) return;
    try {
      const res: any = await runApi.getLatestProjectEvaluationPolicy(pid);
      setProjectPolicy(res?.item || null);
      if (res?.item?.payload) setProjectPolicyText(JSON.stringify(res.item.payload, null, 2));
      if (res?.merged) setProjectMergedPolicyText(JSON.stringify(res.merged, null, 2));
      toast.success('已加载项目策略');
    } catch (e: any) {
      toast.error(e?.message || '加载项目策略失败');
    }
  };

  const applyTemplateFromPolicy = async () => {
    try {
      const res: any = await runApi.getLatestEvaluationPolicy();
      const payload = res?.item?.payload;
      const tname = (evalTagTemplate || '').trim();
      const templates = payload?.tag_templates || {};
      const tcfg = templates?.[tname];
      if (!tcfg) {
        toast.error(`模板不存在：${tname}`);
        return;
      }
      if (Array.isArray(tcfg.expected_tags)) setEvalExpectedTags(String(tcfg.expected_tags.join(',')));
      if (tcfg.tag_expectations) setEvalTagExpectationsJson(JSON.stringify(tcfg.tag_expectations, null, 2));
      toast.success('已从策略加载模板');
    } catch (e: any) {
      toast.error(e?.message || '加载模板失败');
    }
  };

  useEffect(() => {
    if (activeTab !== 'evaluation') return;
    loadEvaluation();
    loadRunState();
    loadEvalPolicy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, runId]);

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
              {runId ? (
                <>
                  <Button variant="secondary" icon={<Ban size={16} />} onClick={cancel} loading={loading}>
                    stop
                  </Button>
                  <Button variant="secondary" icon={<RotateCcw size={16} />} onClick={retry} loading={loading}>
                    retry
                  </Button>
                </>
              ) : null}
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
                  {run.run_id && (
                    <Link to={`/diagnostics/audit?run_id=${encodeURIComponent(run.run_id)}`}>
                      <Button variant="ghost">打开 Audit</Button>
                    </Link>
                  )}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Tabs
        defaultActiveKey="events"
        onChange={(k) => setActiveTab((k as any) === 'evaluation' ? 'evaluation' : 'events')}
        tabs={[
          {
            key: 'events',
            label: 'Events',
            children: (
              <div className="bg-dark-card rounded-xl border border-dark-border overflow-hidden">
                <Table columns={columns as any} data={events} rowKey={(r: any) => String(r.seq)} loading={loading} emptyText="暂无 events" />
              </div>
            ),
          },
          {
            key: 'evaluation',
            label: '评估',
            children: (
              <div className="space-y-3">
                <div className="rounded-xl border border-dark-border bg-dark-card p-3 flex flex-col md:flex-row md:items-center md:justify-between gap-2">
                  <div className="text-sm text-gray-300">
                    <span className="font-medium text-gray-200">核心动作</span>
                    <span className="text-xs text-gray-500 ml-2">自动评估 / 保存策略（全局、项目）</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button onClick={runAutoEvaluate} loading={evaluating}>
                      自动评估
                    </Button>
                    <Button variant="secondary" onClick={saveGlobalPolicy}>
                      保存全局策略
                    </Button>
                    <Button variant="secondary" onClick={saveProjectPolicy} disabled={!evalProjectId.trim()}>
                      保存项目策略
                    </Button>
                    <Button variant="ghost" onClick={loadEvaluation}>
                      刷新评估
                    </Button>
                  </div>
                </div>

                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="text-sm font-medium text-gray-200">自动评估（可选取证）</div>
                        <div className="text-xs text-gray-500 mt-1">输入 URL/步骤/断言后执行；结果在下方“评估结果”查看</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button variant="secondary" onClick={applyTemplateFromPolicy}>
                          从策略加载模板
                        </Button>
                        <Button onClick={runAutoEvaluate} loading={evaluating}>
                          执行自动评估
                        </Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                      <Input
                        value={evalUrl}
                        placeholder="可选：待评估的应用 URL（启用 integrated_browser 后将自动采集 snapshot/screenshot/console/network）"
                        onChange={(e: any) => setEvalUrl(e.target.value)}
                      />
                      <Input value={evalProjectId} placeholder="可选：project_id（用于选择项目级评估策略/模板）" onChange={(e: any) => setEvalProjectId(e.target.value)} />
                      <Input
                        value={evalExpectedTags}
                        placeholder="可选：关键路径标签（逗号分隔），例如 login,create,save（回归门控会校验）"
                        onChange={(e: any) => setEvalExpectedTags(e.target.value)}
                      />
                      <div className="flex items-center gap-2">
                        <Input
                          value={evalTagTemplate}
                          placeholder="可选：tag_template（例如 webapp_basic）"
                          onChange={(e: any) => setEvalTagTemplate(e.target.value)}
                        />
                        <Button variant="ghost" onClick={loadEvalPolicy}>
                          刷新全局策略
                        </Button>
                      </div>
                      <div className="text-xs text-gray-500 flex items-center">
                        提示：需要在 MCP库 启用 <code className="mx-1">integrated_browser</code>，并配置可用的 auto-eval LLM。
                      </div>
                    </div>
                    <div className="mb-3">
                      <div className="text-xs text-gray-500 mb-1">可选：评估步骤 steps（JSON 数组，支持 tag 字段）</div>
                      <Textarea rows={6} value={evalStepsJson} onChange={(e) => setEvalStepsJson(e.target.value)} />
                      <div className="text-xs text-gray-600 mt-1">
                        示例：[{`{"tool":"browser_click","tag":"login","args":{"ref":"..."}},{"tool":"browser_type","tag":"login","args":{"ref":"...","text":"u"}}`}]
                      </div>
                    </div>
                    <div className="mb-3">
                      <div className="text-xs text-gray-500 mb-1">可选：关键路径断言 tag_expectations（JSON，对每个 tag 定义断言；失败会直接 P0）</div>
                      <Textarea rows={8} value={evalTagExpectationsJson} onChange={(e) => setEvalTagExpectationsJson(e.target.value)} />
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="text-sm font-medium text-gray-200">评估结果（evaluation_report）</div>
                        <div className="text-xs text-gray-500 mt-1">来源：/runs/&lt;run_id&gt;/evaluation/latest</div>
                      </div>
                      <Button variant="secondary" onClick={loadEvaluation}>
                        刷新
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {!evaluation && <div className="text-sm text-gray-500">暂无评估报告</div>}
                    {evaluation && (
                      <div className="space-y-3">
                        {(() => {
                          const rep = evaluation.payload || {};
                          const pass = rep?.pass;
                          const score = rep?.score?.functionality;
                          const regression = rep?.regression;
                          return (
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant={pass ? 'success' : 'error'}>{pass ? 'PASS' : 'FAIL'}</Badge>
                              {typeof score !== 'undefined' && <Badge variant="info">functionality: {String(score)}</Badge>}
                              {regression?.is_regression && <Badge variant="warning">Regression</Badge>}
                            </div>
                          );
                        })()}

                        <div className="flex flex-wrap items-center gap-2">
                          {evaluation.artifact_id && (
                            <Link to={`/core/learning/artifacts/${encodeURIComponent(String(evaluation.artifact_id))}`}>
                              <Button variant="secondary">Artifact</Button>
                            </Link>
                          )}
                          {runId && (
                            <Button
                              variant="ghost"
                              onClick={async () => {
                                try {
                                  const res: any = await runApi.autoInvestigate(String(runId));
                                  if (res?.artifact_id) navigate(`/core/learning/artifacts/${encodeURIComponent(String(res.artifact_id))}`);
                                } catch (e: any) {
                                  toast.error(e?.message || '生成 Investigate 报告失败');
                                }
                              }}
                            >
                              Investigate
                            </Button>
                          )}
                          {runId && (
                            <>
                              <Link to={`/core/learning/artifacts?run_id=${encodeURIComponent(String(runId))}`}>
                                <Button variant="ghost">本 Run Artifacts</Button>
                              </Link>
                              <Link to={`/core/learning/artifacts?run_id=${encodeURIComponent(String(runId))}&kind=evaluation_report`}>
                                <Button variant="ghost">仅评估报告</Button>
                              </Link>
                              <Link to={`/core/learning/artifacts?run_id=${encodeURIComponent(String(runId))}&kind=evidence_pack`}>
                                <Button variant="ghost">仅证据包</Button>
                              </Link>
                            </>
                          )}
                          {(() => {
                            const evId = (evaluation?.payload?.evidence_pack_id || evaluation?.evidence_pack_id) as any;
                            if (!evId) return null;
                            return (
                              <Link to={`/core/learning/artifacts/${encodeURIComponent(String(evId))}`}>
                                <Button variant="ghost">Evidence Pack</Button>
                              </Link>
                            );
                          })()}
                          {(() => {
                            const diffId = (evaluation?.payload?.evidence_diff_id || evaluation?.evidence_diff_id) as any;
                            if (!diffId) return null;
                            return (
                              <Link to={`/core/learning/artifacts/${encodeURIComponent(String(diffId))}`}>
                                <Button variant="ghost">Evidence Diff</Button>
                              </Link>
                            );
                          })()}
                        </div>

                        {(() => {
                          const rep = evaluation.payload || {};
                          const issues = Array.isArray(rep?.issues) ? rep.issues : [];
                          if (!issues.length) return null;
                          return (
                            <div className="rounded-lg border border-dark-border bg-dark-hover p-3">
                              <div className="text-xs text-gray-400 mb-2">Issues</div>
                              <div className="space-y-2">
                                {issues.slice(0, 20).map((it: any, idx: number) => (
                                  <div key={idx} className="flex items-start gap-2">
                                    <Badge variant={severityBadge(it?.severity) as any}>{String(it?.severity || 'P?')}</Badge>
                                    <div className="min-w-0">
                                      <div className="text-sm text-gray-200 break-words">{String(it?.title || '')}</div>
                                      {it?.suggested_fix && <div className="text-xs text-gray-500 mt-0.5 break-words">{String(it.suggested_fix)}</div>}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          );
                        })()}

                        <details className="rounded-lg border border-dark-border bg-dark-hover p-3">
                          <summary className="text-xs text-gray-400 cursor-pointer select-none">查看原始 JSON</summary>
                          <pre className="mt-2 text-[12px] text-gray-200 whitespace-pre-wrap">{JSON.stringify(evaluation.payload || evaluation, null, 2)}</pre>
                        </details>
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="text-sm font-medium text-gray-200">评估策略（全局）</div>
                        <div className="text-xs text-gray-500 mt-1">来源：/evaluation/policy/latest（auto-eval 默认使用）</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button variant="ghost" onClick={loadEvalPolicy}>
                          刷新
                        </Button>
                        <Button onClick={saveGlobalPolicy}>保存</Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <Textarea rows={10} value={evalPolicyText} onChange={(e) => setEvalPolicyText(e.target.value)} />
                    {evalPolicy?.artifact_id && (
                      <div className="mt-2">
                        <Link to={`/core/learning/artifacts/${encodeURIComponent(String(evalPolicy.artifact_id))}`}>
                          <Button variant="secondary">打开 Artifact</Button>
                        </Link>
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="text-sm font-medium text-gray-200">项目评估策略（project_id）</div>
                        <div className="text-xs text-gray-500 mt-1">项目策略会覆盖全局策略；可只保存差异字段</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button variant="ghost" onClick={loadProjectPolicy} disabled={!evalProjectId.trim()}>
                          加载
                        </Button>
                        <Button onClick={saveProjectPolicy} disabled={!evalProjectId.trim()}>
                          保存(merge)
                        </Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="text-xs text-gray-500 mb-1">项目策略（payload）</div>
                    <Textarea rows={10} value={projectPolicyText} onChange={(e) => setProjectPolicyText(e.target.value)} />
                    {!!projectMergedPolicyText && (
                      <>
                        <div className="text-xs text-gray-500 mt-3 mb-1">预览：合并后策略（project ⊕ global）</div>
                        <Textarea rows={10} value={projectMergedPolicyText} readOnly />
                      </>
                    )}
                    {projectPolicy?.artifact_id && (
                      <div className="mt-2">
                        <Link to={`/core/learning/artifacts/${encodeURIComponent(String(projectPolicy.artifact_id))}`}>
                          <Button variant="secondary">打开 Artifact</Button>
                        </Link>
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="text-sm font-medium text-gray-200">RunState（Restatement）</div>
                        <div className="text-xs text-gray-500 mt-1">用于长任务控制：会被置顶注入到 prompt 尾部</div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button variant="secondary" onClick={loadRunState}>
                          刷新
                        </Button>
                        <Button
                          variant="secondary"
                          onClick={async () => {
                            const rid = runId.trim();
                            if (!rid) return;
                            try {
                              const obj = JSON.parse(runStateText);
                              await runApi.upsertRunState(rid, { state: obj, lock: runStateLock });
                              toast.success('已保存 RunState');
                              await loadRunState();
                            } catch (e: any) {
                              toast.error(e?.message || '保存失败（请检查 JSON 格式）');
                            }
                          }}
                        >
                          保存
                        </Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="flex items-center gap-2 mb-2">
                      <label className="text-xs text-gray-400">locked</label>
                      <input type="checkbox" checked={runStateLock} onChange={(e) => setRunStateLock(e.target.checked)} />
                      <span className="text-xs text-gray-500">锁定后自动更新不会覆盖（仅手动改动）</span>
                    </div>

                    {(() => {
                      const obj = parseRunStateText();
                      const todo = obj && Array.isArray((obj as any).todo) ? (obj as any).todo : [];
                      if (!todo.length) return null;
                      return (
                        <div className="mb-3">
                          <div className="flex items-center justify-between mb-2">
                            <div className="text-xs text-gray-400">Todo（可勾选完成）</div>
                            <Button variant="secondary" onClick={autoNextStepFromTodo}>
                              从 todo 生成 next_step
                            </Button>
                          </div>
                          <div className="space-y-1">
                            {todo.slice(0, 50).map((t: any) => {
                              const id = String(t?.id || '');
                              const title = String(t?.title || '');
                              const priority = String(t?.priority || '');
                              const done = String(t?.status || '').toLowerCase() === 'completed' || String(t?.status || '').toLowerCase() === 'done';
                              return (
                                <label key={id || title} className="flex items-center gap-2 text-sm text-gray-200">
                                  <input type="checkbox" checked={done} onChange={(e) => setTodoStatus(id, e.target.checked)} />
                                  <span className={done ? 'line-through text-gray-500' : ''}>{title}</span>
                                  {priority && <span className="text-xs text-gray-500">({priority})</span>}
                                </label>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })()}

                    <Textarea rows={10} value={runStateText} onChange={(e) => setRunStateText(e.target.value)} />
                    {runState?.artifact_id && (
                      <div className="mt-2">
                        <Link to={`/core/learning/artifacts/${encodeURIComponent(String(runState.artifact_id))}`}>
                          <Button variant="secondary">打开 Artifact</Button>
                        </Link>
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <div className="text-sm font-medium text-gray-200">手动提交评估（可选）</div>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      <Textarea rows={10} value={manualReport} onChange={(e) => setManualReport(e.target.value)} />
                      <div className="flex items-center justify-end">
                        <Button
                          variant="secondary"
                          onClick={async () => {
                            const rid = runId.trim();
                            if (!rid) return;
                            try {
                              const obj = JSON.parse(manualReport);
                              await runApi.submitEvaluation(rid, { evaluator: 'manual', report: obj });
                              toast.success('已提交评估报告');
                              await loadEvaluation();
                            } catch (e: any) {
                              toast.error(e?.message || '提交失败（请检查 JSON 格式）');
                            }
                          }}
                        >
                          提交
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            ),
          },
        ]}
      />
    </div>
  );
};

export default Runs;
