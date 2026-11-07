/**
 * 评测 Skill — 成果物入口：选 suite → 跑 skill_evals → 看 run/results。
 * 管道 fixture（Run 面板 skill_suite Job）不在本页。
 */
import { useCallback, useEffect, useState } from 'react';
import { Loader2, Play, RefreshCw } from 'lucide-react';
import { skillEvalApi } from '../../services';
import { formatRuntimeAnn, skillEvalRuntimeAnn } from './examRuntimeTier';

type SuiteRow = {
  suite_id?: string;
  id?: string;
  name?: string;
  title?: string;
  description?: string;
  case_count?: number;
  cases?: unknown[];
  [k: string]: unknown;
};

function suiteKey(s: SuiteRow): string {
  return String(s.suite_id || s.id || '').trim();
}

function unwrapSuites(res: unknown): SuiteRow[] {
  const body = res as {
    data?: { items?: SuiteRow[]; suites?: SuiteRow[] };
    items?: SuiteRow[];
  };
  if (Array.isArray(body?.data?.items)) return body.data.items;
  if (Array.isArray(body?.data?.suites)) return body.data.suites;
  if (Array.isArray(body?.items)) return body.items;
  return [];
}

function unwrapResults(res: unknown): Array<Record<string, unknown>> {
  const body = res as {
    data?: { items?: Array<Record<string, unknown>> };
    items?: Array<Record<string, unknown>>;
  };
  if (Array.isArray(body?.data?.items)) return body.data.items;
  if (Array.isArray(body?.items)) return body.items;
  return [];
}

type Props = {
  tenantId?: string;
};

export default function EvalSkillsPanel({ tenantId }: Props) {
  const [suites, setSuites] = useState<SuiteRow[]>([]);
  const [suiteId, setSuiteId] = useState('');
  const [evalKind, setEvalKind] = useState<'trigger' | 'quality'>('trigger');
  const [mode, setMode] = useState<'heuristic' | 'live'>('heuristic');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [runId, setRunId] = useState('');
  const [runRow, setRunRow] = useState<Record<string, unknown> | null>(null);
  const [results, setResults] = useState<Array<Record<string, unknown>>>([]);
  const [runtimeLine, setRuntimeLine] = useState(() =>
    formatRuntimeAnn(skillEvalRuntimeAnn('trigger', 'heuristic')),
  );
  const [preflight, setPreflight] = useState<{
    ok?: boolean;
    checks?: Record<string, unknown>;
    blockers?: string[];
    hints?: string[];
    honesty?: string;
  } | null>(null);

  const loadPreflight = useCallback(async () => {
    try {
      const pf = await skillEvalApi.preflight({
        tenant_id: tenantId || 'eval-v1',
        eval_kind: evalKind,
        mode,
      });
      setPreflight(pf && typeof pf === 'object' ? pf : null);
    } catch (e: unknown) {
      setPreflight({
        ok: false,
        blockers: [e instanceof Error ? e.message : String(e)],
      });
    }
  }, [tenantId, evalKind, mode]);

  const loadSuites = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await skillEvalApi.listSuites({
        limit: 100,
        tenant_id: tenantId || undefined,
      });
      const items = unwrapSuites(res);
      setSuites(items);
      if (items.length && !items.some((s) => suiteKey(s) === suiteId)) {
        setSuiteId(suiteKey(items[0]));
      }
      if (!items.length) setSuiteId('');
    } catch (e: unknown) {
      setSuites([]);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [tenantId, suiteId]);

  const ensureBuiltin = useCallback(async () => {
    setBusy(true);
    setError('');
    setMsg('登记内置样例…');
    try {
      const res = await skillEvalApi.ensureBuiltinSuites({
        tenant_id: tenantId || 'eval-v1',
      });
      const sid = String(res.suite_id || 'builtin_trigger_demo');
      setMsg(
        res.created
          ? `已登记内置样例 ${sid}`
          : `内置样例已存在 ${sid}`,
      );
      await loadSuites();
      setSuiteId(sid);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setMsg('');
    } finally {
      setBusy(false);
    }
  }, [tenantId, loadSuites]);

  useEffect(() => {
    void loadSuites();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initial + tenant
  }, [tenantId]);

  useEffect(() => {
    setRuntimeLine(formatRuntimeAnn(skillEvalRuntimeAnn(evalKind, mode)));
    void loadPreflight();
  }, [evalKind, mode, loadPreflight]);

  const loadResults = useCallback(async (rid: string) => {
    if (!rid.trim()) {
      setRunRow(null);
      setResults([]);
      return;
    }
    try {
      const [runRes, resultRes] = await Promise.all([
        skillEvalApi.getRun(rid.trim()),
        skillEvalApi.listResults(rid.trim(), { limit: 200 }),
      ]);
      const runBody = (runRes as { data?: Record<string, unknown> })?.data || runRes;
      setRunRow(runBody && typeof runBody === 'object' ? (runBody as Record<string, unknown>) : null);
      setResults(unwrapResults(resultRes));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const run = useCallback(async () => {
    const sid = suiteId.trim();
    if (!sid) {
      setError('请选择 Skill suite');
      return;
    }
    setBusy(true);
    setError('');
    setMsg(`正在跑 suite（${evalKind}/${mode}）…`);
    setRuntimeLine(formatRuntimeAnn(skillEvalRuntimeAnn(evalKind, mode)));
    try {
      const pf = await skillEvalApi.preflight({
        tenant_id: tenantId || 'eval-v1',
        eval_kind: evalKind,
        mode,
      });
      setPreflight(pf && typeof pf === 'object' ? pf : null);
      if (pf && pf.ok === false) {
        const block = Array.isArray(pf.blockers) ? pf.blockers.join('；') : '预检未通过';
        setError(block);
        setMsg('');
        setBusy(false);
        return;
      }
      const res = await skillEvalApi.runSuite(sid, {
        eval_kind: evalKind,
        mode,
      });
      const rid = String(res?.run_id || '').trim();
      const body = res as {
        error?: string;
        runtime_tier?: string;
        runtime_claim?: boolean;
        runtime_claim_reason?: string;
        exec_path?: string;
      };
      if (body.runtime_tier) {
        setRuntimeLine(
          formatRuntimeAnn({
            runtime_tier: body.runtime_tier,
            runtime_claim: body.runtime_claim,
            runtime_claim_reason: body.runtime_claim_reason,
          }),
        );
      }
      if (!rid && body?.error) {
        setError(String(body.error));
        setMsg('');
        return;
      }
      if (!rid) {
        setError('未返回 run_id（预检曾通过但执行未落库；请看服务端日志）');
        setMsg('');
        return;
      }
      setRunId(rid);
      const path = String((res as { exec_path?: string }).exec_path || '');
      setMsg(
        `suite ${sid} → run ${rid} · ${evalKind}/${mode}${path ? ` · path=${path}` : ''}`,
      );
      await loadResults(rid);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setMsg('');
    } finally {
      setBusy(false);
    }
  }, [suiteId, evalKind, mode, tenantId, loadResults]);

  const metrics =
    runRow && typeof runRow.metrics === 'object' && runRow.metrics
      ? (runRow.metrics as Record<string, unknown>)
      : null;

  return (
    <div className="space-y-3" data-testid="eval-skills-panel">
      <p
        className="rounded-lg border border-violet-700/40 bg-violet-950/20 px-3 py-2 text-xs text-violet-100/90"
        data-testid="eval-skills-object"
      >
        <strong className="text-violet-50">本页评测对象：Skill suite（成果物）</strong>
        。走 platform <code className="text-[11px]">skill_evals</code>
        （list → run → results）。
        <br />
        归档 <code className="text-[11px]">runtime_tier=fixture</code> · claim=false
        （trigger=仅路由评分；quality=Core skill_manager，≠ Agent workspace_execute）。
        <br />
        不是 Run 面板「Skill · 技能 fixture」Job，也不是 Agent 可归因报告。
      </p>

      <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3 text-sm">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-gray-400 min-w-[12rem] flex-1">
            Suite
            <select
              data-testid="eval-skill-suite"
              className="rounded border border-gray-600 bg-gray-950 px-2 py-1.5 text-sm text-gray-100"
              value={suiteId}
              disabled={busy || loading}
              onChange={(e) => setSuiteId(e.target.value)}
            >
              {!suites.length ? <option value="">（无 suite）</option> : null}
              {suites.map((s) => {
                const id = suiteKey(s);
                const label = String(s.name || s.title || id);
                return (
                  <option key={id} value={id}>
                    {label}
                    {s.case_count != null ? ` · ${s.case_count} cases` : ''}
                  </option>
                );
              })}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-gray-400">
            eval_kind
            <select
              data-testid="eval-skill-kind"
              className="rounded border border-gray-600 bg-gray-950 px-2 py-1.5 text-sm text-gray-100"
              value={evalKind}
              disabled={busy}
              onChange={(e) => setEvalKind(e.target.value as 'trigger' | 'quality')}
            >
              <option value="trigger">trigger</option>
              <option value="quality">quality</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-gray-400">
            mode
            <select
              data-testid="eval-skill-mode"
              className="rounded border border-gray-600 bg-gray-950 px-2 py-1.5 text-sm text-gray-100"
              value={mode}
              disabled={busy || evalKind !== 'trigger'}
              onChange={(e) => setMode(e.target.value as 'heuristic' | 'live')}
            >
              <option value="heuristic">heuristic</option>
              <option value="live">live</option>
            </select>
          </label>
          <button
            type="button"
            data-testid="eval-skill-refresh"
            disabled={busy || loading}
            onClick={() => void loadSuites()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-gray-600 text-xs text-gray-300 hover:bg-gray-800 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
          <button
            type="button"
            data-testid="eval-skill-run"
            disabled={busy || !suiteId.trim()}
            onClick={() => void run()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-violet-700/80 text-xs text-white hover:bg-violet-600 disabled:opacity-50"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            跑 suite
          </button>
        </div>

        {!loading && !suites.length ? (
          <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500">
            <span>
              暂无 Skill suite。可一键登记内置样例（heuristic 可跑 · fixture · claim=false），或自行 API upsert。
            </span>
            <button
              type="button"
              data-testid="eval-skill-ensure-builtin"
              disabled={busy}
              onClick={() => void ensureBuiltin()}
              className="inline-flex items-center gap-1 px-2 py-1 rounded border border-violet-700/50 text-violet-100 hover:bg-violet-950/40 disabled:opacity-50"
            >
              登记内置样例
            </button>
          </div>
        ) : null}

        {msg ? <p className="text-xs text-emerald-300/90">{msg}</p> : null}
        {error ? (
          <p className="text-xs text-red-300" data-testid="eval-skill-error">
            {error}
          </p>
        ) : null}
        <p className="text-[11px] text-sky-200/80 font-mono" data-testid="eval-skill-runtime">
          {runtimeLine}
        </p>
        {preflight ? (
          <div
            className={`rounded border px-2 py-1.5 text-[11px] ${
              preflight.ok
                ? 'border-emerald-800/50 text-emerald-200/90'
                : 'border-amber-800/50 text-amber-100/90'
            }`}
            data-testid="eval-skill-preflight"
          >
            预检 {preflight.ok ? '通过' : '未通过'}
            {preflight.checks?.path != null
              ? ` · path=${String(preflight.checks.path)}`
              : ''}
            {preflight.checks?.skill_manager_ok
              ? ' · skill_manager'
              : preflight.checks?.trigger_direct_ok
                ? ' · store_direct 可用'
                : ''}
            {Array.isArray(preflight.blockers) && preflight.blockers.length
              ? ` · ${preflight.blockers.join('；')}`
              : ''}
            {Array.isArray(preflight.hints) && preflight.hints.length
              ? ` · ${preflight.hints[0]}`
              : ''}
          </div>
        ) : null}
      </div>

      {runId ? (
        <div
          className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3 text-xs"
          data-testid="eval-skill-run-result"
        >
          <div className="flex flex-wrap justify-between gap-2 text-gray-300">
            <span>
              Run <code className="text-gray-100">{runId}</code>
            </span>
            <button
              type="button"
              className="text-sky-300 hover:underline"
              onClick={() => void loadResults(runId)}
            >
              刷新结果
            </button>
          </div>
          {metrics ? (
            <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {Object.entries(metrics)
                .filter(([, v]) => typeof v === 'number' || typeof v === 'string' || typeof v === 'boolean')
                .slice(0, 12)
                .map(([k, v]) => (
                  <div key={k} className="rounded border border-gray-700/80 bg-gray-950/40 px-2 py-1.5">
                    <dt className="text-gray-500">{k}</dt>
                    <dd className="font-mono text-gray-200">{String(v)}</dd>
                  </div>
                ))}
            </dl>
          ) : (
            <p className="text-gray-500">暂无 metrics 摘要</p>
          )}
          {results.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="text-gray-500 border-b border-gray-700">
                    <th className="py-1 pr-2 font-normal">case</th>
                    <th className="py-1 pr-2 font-normal">pass</th>
                    <th className="py-1 font-normal">detail</th>
                  </tr>
                </thead>
                <tbody>
                  {results.slice(0, 50).map((r, i) => (
                    <tr key={String(r.case_id || r.id || i)} className="border-b border-gray-800">
                      <td className="py-1 pr-2 text-gray-300">
                        {String(r.case_id || r.query || r.id || i)}
                      </td>
                      <td className="py-1 pr-2 font-mono">
                        {String(r.passed ?? r.pass ?? r.ok ?? '—')}
                      </td>
                      <td className="py-1 text-gray-500 truncate max-w-md">
                        {String(r.reason || r.message || r.detail || '').slice(0, 120) || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {results.length > 50 ? (
                <p className="text-gray-500 mt-1">仅显示前 50 / {results.length}</p>
              ) : null}
            </div>
          ) : (
            <p className="text-gray-500">暂无 case 结果行</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
