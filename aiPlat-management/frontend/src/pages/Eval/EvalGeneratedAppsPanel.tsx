/**
 * 评测生成应用 — runs_eval（run_id）+ Pi 交付冒烟（sample/project）。
 * 身份权威 runs_eval = run_id；目标 target_runtime=pi；实际 runtime_tier 仅 live Pi 宿主为 pi，offline/runs_eval 为 fixture。
 */
import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, Play, Search, Flame } from 'lucide-react';
import { agentEvalApi, runApi } from '../../services';
import { formatRuntimeAnn, generatedAppRuntimeAnn } from './examRuntimeTier';

function pickReport(res: unknown): Record<string, unknown> | null {
  const body = res as {
    report?: Record<string, unknown>;
    item?: Record<string, unknown> | null;
    data?: { report?: Record<string, unknown>; item?: Record<string, unknown> };
    status?: string;
  };
  if (body?.report && typeof body.report === 'object') return body.report;
  if (body?.item && typeof body.item === 'object') return body.item;
  if (body?.data?.report && typeof body.data.report === 'object') return body.data.report;
  if (body?.data?.item && typeof body.data.item === 'object') return body.data.item;
  if (body && typeof body === 'object' && (body as Record<string, unknown>).composite_score != null) {
    return body as Record<string, unknown>;
  }
  return null;
}

export default function EvalGeneratedAppsPanel() {
  const [runId, setRunId] = useState('');
  const [projectId, setProjectId] = useState('');
  const [piSource, setPiSource] = useState<'sample' | 'project'>('sample');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [rawStatus, setRawStatus] = useState('');
  const [runtimeLine, setRuntimeLine] = useState(
    () => formatRuntimeAnn(generatedAppRuntimeAnn('runs_eval')),
  );
  const [piResult, setPiResult] = useState<Record<string, unknown> | null>(null);

  const loadLatest = useCallback(async () => {
    const rid = runId.trim();
    if (!rid) {
      setError('请填写 run_id');
      return;
    }
    setBusy(true);
    setError('');
    setMsg('读取最新评测…');
    setRuntimeLine(formatRuntimeAnn(generatedAppRuntimeAnn('runs_eval')));
    try {
      const res = await runApi.getLatestEvaluation(rid);
      setRawStatus(String((res as { status?: string })?.status || ''));
      const r = pickReport(res);
      setReport(r);
      setPiResult(null);
      setMsg(r ? `已加载 evaluation/latest · run=${rid}` : `无最新评测（run=${rid}）`);
    } catch (e: unknown) {
      setReport(null);
      setError(e instanceof Error ? e.message : String(e));
      setMsg('');
    } finally {
      setBusy(false);
    }
  }, [runId]);

  const autoEval = useCallback(async () => {
    const rid = runId.trim();
    if (!rid) {
      setError('请填写 run_id');
      return;
    }
    setBusy(true);
    setError('');
    setMsg('自动评测中…');
    setRuntimeLine(formatRuntimeAnn(generatedAppRuntimeAnn('runs_eval')));
    try {
      const body: { project_id?: string } = {};
      if (projectId.trim()) body.project_id = projectId.trim();
      const res = await runApi.autoEvaluate(rid, body);
      setRawStatus(String((res as { status?: string })?.status || 'ok'));
      const r = pickReport(res) || ((res as { report?: Record<string, unknown> }).report ?? null);
      setReport(r);
      setPiResult(null);
      setMsg(
        `autoEvaluate 完成 · artifact=${String((res as { artifact_id?: string }).artifact_id || '—')}`,
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setMsg('');
    } finally {
      setBusy(false);
    }
  }, [runId, projectId]);

  const runPiSmoke = useCallback(
    async (live: boolean) => {
      if (piSource === 'project' && !projectId.trim()) {
        setError('source=project 时请填写 project_id');
        return;
      }
      setBusy(true);
      setError('');
      setMsg(live ? 'Pi live 冒烟中…' : 'Pi 离线结构校验中…');
      setRuntimeLine(
        formatRuntimeAnn(generatedAppRuntimeAnn(live ? 'pi_live' : 'pi_offline')),
      );
      try {
        const res = await agentEvalApi.runGeneratedAppPiSmoke({
          source: piSource,
          project_id: projectId.trim() || undefined,
          live,
        });
        setPiResult(res as Record<string, unknown>);
        setReport(null);
        setRawStatus(res.ok ? 'ok' : 'error');
        if (res.runtime_tier) {
          setRuntimeLine(
            formatRuntimeAnn({
              runtime_tier: res.runtime_tier,
              runtime_claim: res.runtime_claim,
              runtime_claim_reason: res.runtime_claim_reason,
            }),
          );
        }
        if (res.ok) {
          setMsg(String(res.msg || (live ? 'Pi live 冒烟通过' : 'Pi 离线结构校验通过')));
          setError('');
        } else {
          setMsg(String(res.msg || ''));
          setError(String(res.error || 'pi smoke failed'));
        }
      } catch (e: unknown) {
        setPiResult(null);
        setError(e instanceof Error ? e.message : String(e));
        setMsg('');
      } finally {
        setBusy(false);
      }
    },
    [piSource, projectId],
  );

  const summaryEntries = report
    ? Object.entries(report).filter(
        ([, v]) =>
          typeof v === 'number' ||
          typeof v === 'string' ||
          typeof v === 'boolean' ||
          v == null,
      )
    : [];

  return (
    <div className="space-y-3" data-testid="eval-apps-panel">
      <p
        className="rounded-lg border border-violet-700/40 bg-violet-950/20 px-3 py-2 text-xs text-violet-100/90"
        data-testid="eval-apps-object"
      >
        <strong className="text-violet-50">本页评测对象：生成应用</strong>
        。两条入口勿混称：
        <br />
        ① runs_eval（run_id auto/latest）→{' '}
        <code className="text-[11px]">runtime_tier=fixture · target_runtime=pi · runtime_claim=false</code>
        （平台路径，≠ Pi 宿主）。
        <br />
        ② Pi 交付冒烟（sample / project 导出）→ 离线结构校验 claim=false；live{' '}
        <code className="text-[11px]">pi</code> CLI 成功才 claim=true。
      </p>

      <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3 text-sm">
        <div className="text-xs text-gray-400 font-medium">① 平台 runs_eval</div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-gray-400 min-w-[14rem] flex-1">
            run_id
            <input
              data-testid="eval-app-run-id"
              className="rounded border border-gray-600 bg-gray-950 px-2 py-1.5 text-sm text-gray-100 font-mono"
              value={runId}
              disabled={busy}
              placeholder="粘贴生成应用 run_id"
              onChange={(e) => setRunId(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-gray-400 min-w-[10rem]">
            project_id（可选）
            <input
              data-testid="eval-app-project-id"
              className="rounded border border-gray-600 bg-gray-950 px-2 py-1.5 text-sm text-gray-100 font-mono"
              value={projectId}
              disabled={busy}
              placeholder="可选 / Pi project"
              onChange={(e) => setProjectId(e.target.value)}
            />
          </label>
          <button
            type="button"
            data-testid="eval-app-latest"
            disabled={busy || !runId.trim()}
            onClick={() => void loadLatest()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-gray-600 text-xs text-gray-300 hover:bg-gray-800 disabled:opacity-50"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
            最新评测
          </button>
          <button
            type="button"
            data-testid="eval-app-auto"
            disabled={busy || !runId.trim()}
            onClick={() => void autoEval()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-violet-700/80 text-xs text-white hover:bg-violet-600 disabled:opacity-50"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            自动评测
          </button>
        </div>
        <p className="text-[11px] text-gray-500">
          可从{' '}
          <Link className="text-sky-400 hover:underline" to="/diagnostics/runs">
            诊断 · Runs
          </Link>{' '}
          复制 run_id。
        </p>
      </div>

      <div className="rounded-lg border border-emerald-800/50 bg-emerald-950/15 p-4 space-y-3 text-sm">
        <div className="text-xs text-emerald-200/90 font-medium">② Pi 交付冒烟</div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-gray-400">
            source
            <select
              data-testid="eval-app-pi-source"
              className="rounded border border-gray-600 bg-gray-950 px-2 py-1.5 text-sm text-gray-100"
              value={piSource}
              disabled={busy}
              onChange={(e) => setPiSource(e.target.value as 'sample' | 'project')}
            >
              <option value="sample">sample（夹具）</option>
              <option value="project">project（apps/…/current）</option>
            </select>
          </label>
          <button
            type="button"
            data-testid="eval-app-pi-offline"
            disabled={busy || (piSource === 'project' && !projectId.trim())}
            onClick={() => void runPiSmoke(false)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-emerald-700/60 text-xs text-emerald-100 hover:bg-emerald-950/40 disabled:opacity-50"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
            离线结构
          </button>
          <button
            type="button"
            data-testid="eval-app-pi-live"
            disabled={busy || (piSource === 'project' && !projectId.trim())}
            onClick={() => void runPiSmoke(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-emerald-800/80 text-xs text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Flame className="w-3.5 h-3.5" />}
            Live Pi CLI
          </button>
        </div>
        <p className="text-[11px] text-gray-500">
          Live 需本机 <code className="text-gray-400">pi</code> + 模型（默认{' '}
          <code className="text-gray-400">AIPLAT_PI_MODEL</code> / ollama/qwen2.5:3b）。
        </p>
      </div>

      {msg ? <p className="text-xs text-emerald-300/90">{msg}</p> : null}
      {error ? (
        <p className="text-xs text-red-300" data-testid="eval-app-error">
          {error}
        </p>
      ) : null}
      <p className="text-[11px] text-sky-200/80 font-mono" data-testid="eval-app-runtime">
        {runtimeLine}
      </p>

      {report || rawStatus || piResult ? (
        <div
          className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3 text-xs"
          data-testid="eval-app-report"
        >
          <div className="text-gray-300">
            status=<span className="font-mono text-gray-100">{rawStatus || '—'}</span>
          </div>
          {summaryEntries.length ? (
            <dl className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {summaryEntries.slice(0, 18).map(([k, v]) => (
                <div key={k} className="rounded border border-gray-700/80 bg-gray-950/40 px-2 py-1.5">
                  <dt className="text-gray-500">{k}</dt>
                  <dd className="font-mono text-gray-200 break-all">{v == null ? '—' : String(v)}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {piResult ? (
            <pre className="max-h-64 overflow-auto rounded border border-gray-800 bg-black/40 p-2 text-[10px] text-gray-400">
              {JSON.stringify(piResult, null, 2)}
            </pre>
          ) : null}
          {report ? (
            <pre className="max-h-64 overflow-auto rounded border border-gray-800 bg-black/40 p-2 text-[10px] text-gray-400">
              {JSON.stringify(report, null, 2)}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
