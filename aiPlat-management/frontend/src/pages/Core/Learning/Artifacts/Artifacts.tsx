import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Eye, RefreshCw } from 'lucide-react';

import { Badge, Button, Card, CardContent, CardHeader, Select, Table, toast } from '../../../../components/ui';
import { learningApi, type LearningArtifact } from '../../../../services';

const targetTypeOptions = [
  { label: 'system', value: 'system' },
  { label: 'project', value: 'project' },
  { label: 'agent', value: 'agent' },
  { label: 'skill', value: 'skill' },
  { label: 'run', value: 'run' },
  { label: 'canary', value: 'canary' },
  { label: 'prompt', value: 'prompt' },
  { label: 'policy', value: 'policy' },
];

const statusOptions = [
  { label: '全部', value: '' },
  { label: 'draft', value: 'draft' },
  { label: 'published', value: 'published' },
  { label: 'rolled_back', value: 'rolled_back' },
];

const kindOptions = [
  { label: '全部', value: '' },
  { label: 'release_candidate', value: 'release_candidate' },
  { label: 'prompt_revision', value: 'prompt_revision' },
  { label: 'regression_report', value: 'regression_report' },
  { label: 'evaluation_report', value: 'evaluation_report' },
  { label: 'investigate_report', value: 'investigate_report' },
  { label: 'canary_report', value: 'canary_report' },
  { label: 'evidence_pack', value: 'evidence_pack' },
  { label: 'evidence_diff', value: 'evidence_diff' },
  { label: 'evaluation_policy', value: 'evaluation_policy' },
  { label: 'feedback_summary', value: 'feedback_summary' },
  { label: 'run_state', value: 'run_state' },
  { label: 'skill_evolution', value: 'skill_evolution' },
  { label: 'skill_rollback', value: 'skill_rollback' },
];

const Artifacts: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [items, setItems] = useState<LearningArtifact[]>([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [kind, setKind] = useState('');
  const [targetType, setTargetType] = useState('agent');
  const [targetId, setTargetId] = useState('');
  const [runId, setRunId] = useState('');
  const [traceId, setTraceId] = useState('');

  const formatTs = (v: any): string => {
    if (v == null) return '-';
    const n = typeof v === 'string' ? Number(v) : v;
    if (Number.isFinite(n) && n > 1e12) return new Date(n).toISOString();
    if (Number.isFinite(n) && n > 1e9) return new Date(n * 1000).toISOString();
    return String(v);
  };

  const statusVariant = (s0: any) => {
    const s = String(s0 || '').toLowerCase();
    if (s === 'published') return 'success';
    if (s === 'rolled_back') return 'error';
    if (s === 'draft') return 'default';
    return 'default';
  };

  const kindVariant = (k0: any) => {
    const k = String(k0 || '').toLowerCase();
    if (k.includes('report')) return 'info';
    if (k.includes('policy')) return 'warning';
    if (k.includes('evidence')) return 'default';
    return 'default';
  };

  const summarize = (r: LearningArtifact): string => {
    const p: any = r.payload || {};
    try {
      if (r.kind === 'evaluation_report') {
        const pass = p.pass;
        const f = p?.score?.functionality;
        const reg = p?.regression?.is_regression;
        const issues = Array.isArray(p.issues) ? p.issues.length : 0;
        return `pass=${String(pass)}${typeof f !== 'undefined' ? `, functionality=${String(f)}` : ''}${reg ? ', regression=1' : ''}, issues=${issues}`;
      }
      if (r.kind === 'evidence_diff') {
        const sum = p.summary || '';
        const m = p.metrics || {};
        const e = m.new_console_errors ?? '-';
        const s5 = m.new_network_5xx ?? '-';
        const c = m.changed_screenshot_tags ?? '-';
        return `${String(sum || '').slice(0, 140)} (new_err=${e}, new_5xx=${s5}, changed_shots=${c})`;
      }
      if (r.kind === 'evidence_pack') {
        const url = p.url || '';
        const err = p.error || '';
        return `${String(url || '').slice(0, 80)}${err ? `, error=${String(err).slice(0, 60)}` : ''}`;
      }
      if (r.kind === 'run_state') {
        const next = p.next_step || '';
        const todo = Array.isArray(p.todo) ? p.todo.length : 0;
        return `todo=${todo}, next_step=${String(next).slice(0, 120)}`;
      }
      if (r.kind === 'evaluation_policy') {
        const dt = p.default_tag_template || '-';
        const th = p.thresholds || {};
        return `default_template=${dt}, thresholds=${Object.keys(th).join(',') || '-'}`;
      }
      if (r.kind === 'investigate_report') {
        const ev = p.evaluation || {};
        const sys = p.syscalls?.summary || {};
        const pass = ev.pass;
        const issues = ev.issues_count ?? '-';
        const errs = sys.errors ?? '-';
        return `pass=${String(pass)}, issues=${String(issues)}, sys_err=${String(errs)}`;
      }
      if (r.kind === 'canary_report') {
        const pass = p.pass;
        const cid = p.canary_id || '-';
        const st = p.status || (pass ? 'completed' : 'failed');
        return `canary=${String(cid)}, status=${String(st)}, pass=${String(pass)}`;
      }
    } catch {
      // ignore
    }
    return '';
  };

  const fetchList = async () => {
    setLoading(true);
    try {
      const res = await learningApi.listArtifacts({
        target_type: targetType,
        target_id: targetId || undefined,
        kind: kind || undefined,
        status: status || undefined,
        run_id: runId || undefined,
        trace_id: traceId || undefined,
        limit: 200,
        offset: 0,
      });
      setItems(res.items || []);
    } catch (e: any) {
      toast.error(e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Init filters from URL (best-effort)
    try {
      const tt = searchParams.get('target_type');
      const ti = searchParams.get('target_id');
      const k = searchParams.get('kind');
      const s = searchParams.get('status');
      const rid = searchParams.get('run_id');
      const tid = searchParams.get('trace_id');
      if (tt) setTargetType(tt);
      if (ti) setTargetId(ti);
      if (k) setKind(k);
      if (s) setStatus(s);
      if (rid) setRunId(rid);
      if (tid) setTraceId(tid);
    } catch {
      // ignore
    }
    fetchList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pinToUrl = () => {
    const q = new URLSearchParams();
    if (targetType) q.set('target_type', targetType);
    if (targetId) q.set('target_id', targetId);
    if (kind) q.set('kind', kind);
    if (status) q.set('status', status);
    if (runId) q.set('run_id', runId);
    if (traceId) q.set('trace_id', traceId);
    setSearchParams(q);
    toast.success('已固定到 URL');
  };

  const columns = useMemo(
    () => [
      {
        title: 'artifact_id',
        dataIndex: 'artifact_id',
        key: 'artifact_id',
        render: (v: string) => (
          <button
            className="text-left"
            onClick={() => navigate(`/core/learning/artifacts/${String(v)}`)}
            title="打开详情页"
          >
            <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{String(v || '').slice(0, 12)}</code>
          </button>
        ),
      },
      {
        title: 'kind',
        dataIndex: 'kind',
        key: 'kind',
        render: (v: any) => <Badge variant={kindVariant(v) as any}>{String(v || '-')}</Badge>,
      },
      {
        title: 'status',
        dataIndex: 'status',
        key: 'status',
        render: (v: any) => <Badge variant={statusVariant(v) as any}>{String(v || '-')}</Badge>,
      },
      {
        title: 'target',
        key: 'target',
        render: (_: any, r: LearningArtifact) => (
          <code className="text-xs text-gray-300">
            {String(r.target_type)}:{String(r.target_id || '').slice(0, 32)}
          </code>
        ),
      },
      {
        title: 'run/trace',
        key: 'run_trace',
        render: (_: any, r: LearningArtifact) => (
          <div className="flex flex-col gap-1">
            {r.run_id ? (
              <button className="text-left" onClick={() => navigate(`/diagnostics/runs?run_id=${encodeURIComponent(String(r.run_id))}`)}>
                <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{String(r.run_id).slice(0, 12)}</code>
              </button>
            ) : (
              <span className="text-xs text-gray-600">-</span>
            )}
            {r.trace_id ? (
              <button className="text-left" onClick={() => navigate(`/diagnostics/links?trace_id=${encodeURIComponent(String(r.trace_id))}`)}>
                <code className="text-xs bg-dark-hover px-1.5 py-0.5 rounded">{String(r.trace_id).slice(0, 12)}</code>
              </button>
            ) : null}
          </div>
        ),
      },
      {
        title: 'created_at',
        dataIndex: 'created_at',
        key: 'created_at',
        render: (v: any) => <span className="text-xs text-gray-500">{formatTs(v)}</span>,
      },
      { title: 'version', dataIndex: 'version', key: 'version', render: (v: any) => <span className="text-xs text-gray-300">{String(v || '').slice(0, 32)}</span> },
      {
        title: 'summary',
        key: 'summary',
        render: (_: any, r: LearningArtifact) => <span className="text-xs text-gray-400">{summarize(r)}</span>,
      },
      {
        title: 'actions',
        key: 'actions',
        render: (_: any, r: LearningArtifact) => (
          <Button
            variant="ghost"
            icon={<Eye size={14} />}
            onClick={() => navigate(`/core/learning/artifacts/${r.artifact_id}`)}
          >
            查看
          </Button>
        ),
      },
    ],
    [navigate]
  );

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-gray-200">Learning Artifacts</h1>
          <div className="text-sm text-gray-500 mt-1">learning_artifacts 列表（来自 core ExecutionStore）</div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={fetchList} loading={loading}>
            刷新
          </Button>
          <Button variant="ghost" onClick={pinToUrl}>
            固定到 URL
          </Button>
        </div>
      </div>

      <details className="bg-dark-card border border-dark-border rounded-lg px-3 py-2 text-xs text-gray-500 cursor-pointer group mb-3">
        <summary className="text-gray-400 hover:text-gray-200 select-none">📖 表头说明</summary>
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
          <div><span className="text-gray-300">artifact_id</span><span className="ml-2 text-gray-600">学习制品唯一标识，点击查看详情</span></div>
          <div><span className="text-gray-300">kind</span><span className="ml-2 text-gray-600">类型：release_candidate / prompt_revision / regression_report 等</span></div>
          <div><span className="text-gray-300">status</span><span className="ml-2 text-gray-600"><span className="text-green-400">published</span> 已发布 · <span className="text-red-400">rolled_back</span> 已回滚 · <span className="text-gray-400">draft</span> 草稿</span></div>
          <div><span className="text-gray-300">target</span><span className="ml-2 text-gray-600">关联的目标：type:id 格式</span></div>
          <div><span className="text-gray-300">run/trace</span><span className="ml-2 text-gray-600">关联的执行 run_id + 链路 trace_id</span></div>
          <div><span className="text-gray-300">created_at</span><span className="ml-2 text-gray-600">创建时间</span></div>
          <div><span className="text-gray-300">version</span><span className="ml-2 text-gray-600">版本号</span></div>
          <div><span className="text-gray-300">summary</span><span className="ml-2 text-gray-600">kind 相关的摘要信息（通过率/issues等）</span></div>
          <div><span className="text-gray-300">操作</span><span className="ml-2 text-gray-600">查看详情</span></div>
        </div>
      </details>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-3">
            <Select
              value={targetType}
              onChange={(v) => setTargetType(String(v))}
              options={targetTypeOptions}
              placeholder="target_type"
              className="w-40"
            />
            <Select
              value={kind}
              onChange={(v) => setKind(String(v))}
              options={kindOptions}
              placeholder="kind"
              className="w-56"
            />
            <Select
              value={status}
              onChange={(v) => setStatus(String(v))}
              options={statusOptions}
              placeholder="status"
              className="w-40"
            />
            <input
              className="h-10 px-3 rounded-lg bg-dark-bg border border-dark-border text-gray-200 text-sm w-64"
              placeholder="target_id（可选，例如 agent_id / run_id）"
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
            />
            <input
              className="h-10 px-3 rounded-lg bg-dark-bg border border-dark-border text-gray-200 text-sm w-64"
              placeholder="run_id（可选）"
              value={runId}
              onChange={(e) => setRunId(e.target.value)}
            />
            <input
              className="h-10 px-3 rounded-lg bg-dark-bg border border-dark-border text-gray-200 text-sm w-64"
              placeholder="trace_id（可选）"
              value={traceId}
              onChange={(e) => setTraceId(e.target.value)}
            />
            <Button variant="primary" onClick={fetchList}>
              查询
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <Table columns={columns as any} data={items} rowKey={(r: any) => String(r.artifact_id)} />
        </CardContent>
      </Card>

    </div>
  );
};

export default Artifacts;
