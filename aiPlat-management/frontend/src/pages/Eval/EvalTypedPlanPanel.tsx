/**
 * Typed Plan-chain exams + L5 claims-gate (Object Contract §0.8 / §0.9).
 * Honesty: dry fixture ≠ live host; claims_gate default authorize=false.
 */
import { useCallback, useMemo, useState } from 'react';
import { Loader2, Play, ShieldAlert } from 'lucide-react';
import { agentEvalApi } from '../../services';
import { evaluateL5ClaimsGate, type ClaimsGateEvidence } from './claimsGate';

type TypedKind = 'prompt' | 'workflow' | 'model' | 'dataset' | 'system';

const KIND_LABEL: Record<TypedKind, string> = {
  prompt: 'Prompt Plan',
  workflow: 'Workflow Plan',
  model: 'Model Plan',
  dataset: 'Dataset Plan',
  system: 'System 组合',
};

function parseCsv(s: string): string[] {
  return s
    .split(/[,，\s]+/)
    .map((x) => x.trim())
    .filter(Boolean);
}

export default function EvalTypedPlanPanel() {
  const [kind, setKind] = useState<TypedKind>('prompt');
  const [objectId, setObjectId] = useState('');
  const [live, setLive] = useState(false);
  const [includeSpecial, setIncludeSpecial] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const [evObjectType, setEvObjectType] = useState('agent');
  const [evObjectId, setEvObjectId] = useState('qa_agent');
  const [evVersion, setEvVersion] = useState('v1');
  const [evTier, setEvTier] = useState('workspace_execute');
  const [evPlanId, setEvPlanId] = useState('');
  const [evSetIds, setEvSetIds] = useState('default/normal');
  const [evOracles, setEvOracles] = useState('lexical_path');
  const [evDims, setEvDims] = useState('task_result');
  const [evSampleN, setEvSampleN] = useState('20');
  const [evUntested, setEvUntested] = useState('0');
  const [evHasRun, setEvHasRun] = useState(true);
  const [evRuntimeClaim, setEvRuntimeClaim] = useState(true);
  const [evHumanReview, setEvHumanReview] = useState(false);
  const [explicitAuthorize, setExplicitAuthorize] = useState(false);
  const [gateLocal, setGateLocal] = useState(true);
  const [gateBusy, setGateBusy] = useState(false);
  const [gateResult, setGateResult] = useState<Record<string, unknown> | null>(null);
  const [gateError, setGateError] = useState('');

  const evidence = useMemo((): ClaimsGateEvidence => {
    return {
      object_type: evObjectType.trim(),
      object_id: evObjectId.trim(),
      object_version: evVersion.trim(),
      runtime_tier: evTier.trim(),
      plan_id: evPlanId.trim(),
      set_ids: parseCsv(evSetIds),
      oracle_types: parseCsv(evOracles),
      dimensions: parseCsv(evDims),
      sample_n: Number(evSampleN) || 0,
      has_run_evidence: evHasRun,
      untested_applicable_n: Number(evUntested) || 0,
      runtime_claim: evRuntimeClaim,
      fixture_only: evTier.trim() === 'fixture',
      human_review: evHumanReview,
    };
  }, [
    evObjectType,
    evObjectId,
    evVersion,
    evTier,
    evPlanId,
    evSetIds,
    evOracles,
    evDims,
    evSampleN,
    evUntested,
    evHasRun,
    evRuntimeClaim,
    evHumanReview,
  ]);

  const runExam = useCallback(async () => {
    setBusy(true);
    setError('');
    setMsg('');
    setResult(null);
    try {
      const oid = objectId.trim() || undefined;
      const body = {
        object_id: oid,
        live,
        include_special: includeSpecial,
        max_tasks_per_set: 20,
      };
      const res =
        kind === 'system'
          ? await agentEvalApi.systemPlanExam(body)
          : await agentEvalApi.typedPlanExam(kind, body);
      setResult(res || null);
      if (res?.ok === false || res?.error) {
        setError(String(res.error || 'plan-exam failed'));
      } else {
        const counts = (res?.counts || res?.totals || {}) as Record<string, unknown>;
        setMsg(
          `${KIND_LABEL[kind]} ok · runtime_tier=${String(res?.runtime_tier || '—')} · claim=${String(Boolean(res?.accuracy_claim))} · tasks=${String(counts.tasks ?? counts.total ?? '—')}`,
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [kind, objectId, live, includeSpecial]);

  const runGate = useCallback(async () => {
    setGateBusy(true);
    setGateError('');
    setGateResult(null);
    try {
      if (gateLocal) {
        const r = evaluateL5ClaimsGate(evidence, {
          explicitAuthorize,
        });
        setGateResult(r as unknown as Record<string, unknown>);
      } else {
        const r = await agentEvalApi.claimsGate({
          evidence: evidence as Record<string, unknown>,
          explicit_authorize: explicitAuthorize,
        });
        setGateResult(r || null);
        if (r?.ok === false || r?.error) {
          setGateError(String(r.error || 'claims-gate failed'));
        }
      }
    } catch (e) {
      setGateError(e instanceof Error ? e.message : String(e));
    } finally {
      setGateBusy(false);
    }
  }, [evidence, explicitAuthorize, gateLocal]);

  const blockers = useMemo(() => {
    const failed = Array.isArray(gateResult?.failed) ? (gateResult!.failed as string[]) : [];
    const missing = Array.isArray(gateResult?.missing) ? (gateResult!.missing as string[]) : [];
    return [...failed, ...missing];
  }, [gateResult]);

  return (
    <div className="space-y-4 text-sm" data-testid="eval-typed-plan-panel">
      <section className="rounded-lg border border-violet-700/40 bg-violet-950/20 p-4 space-y-3">
        <h2 className="text-base font-medium text-violet-50">对象 Plan 链 exam</h2>
        <p className="text-xs text-violet-100/75 leading-relaxed">
          调用 <code>*-plan-exam</code> / <code>system-plan-exam</code>。默认 dry→fixture stub；live 可能走
          LLM。≠ 页面 Prompt 评测、≠ 真实 pipeline 宿主、≠ 模型榜、≠ KB 样本路径。
        </p>
        <div className="flex flex-wrap gap-3 items-end">
          <label className="space-y-1">
            <span className="text-[11px] text-violet-200/70">对象类型</span>
            <select
              className="block rounded border border-violet-700/50 bg-gray-950 px-2 py-1.5 text-violet-50"
              value={kind}
              onChange={(e) => setKind(e.target.value as TypedKind)}
              data-testid="eval-typed-plan-kind"
            >
              {(Object.keys(KIND_LABEL) as TypedKind[]).map((k) => (
                <option key={k} value={k}>
                  {KIND_LABEL[k]}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 flex-1 min-w-[12rem]">
            <span className="text-[11px] text-violet-200/70">object_id（可空=默认）</span>
            <input
              className="w-full rounded border border-violet-700/50 bg-gray-950 px-2 py-1.5 text-violet-50"
              value={objectId}
              onChange={(e) => setObjectId(e.target.value)}
              placeholder={`${kind}_under_test`}
            />
          </label>
          <label className="inline-flex items-center gap-2 text-xs text-violet-100/85">
            <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
            live
          </label>
          <label className="inline-flex items-center gap-2 text-xs text-violet-100/85">
            <input
              type="checkbox"
              checked={includeSpecial}
              onChange={(e) => setIncludeSpecial(e.target.checked)}
            />
            include_special
          </label>
          <button
            type="button"
            data-testid="eval-typed-plan-run"
            disabled={busy}
            onClick={() => void runExam()}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded border border-violet-500/60 bg-violet-950/60 text-violet-50 hover:bg-violet-900/60 disabled:opacity-50"
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            跑 Plan exam
          </button>
        </div>
        {msg ? <p className="text-xs text-emerald-200/90">{msg}</p> : null}
        {error ? <p className="text-xs text-red-300">{error}</p> : null}
        {result ? (
          <pre
            className="max-h-64 overflow-auto rounded border border-violet-800/40 bg-gray-950/80 p-2 text-[11px] text-violet-100/80"
            data-testid="eval-typed-plan-result"
          >
            {JSON.stringify(result, null, 2)}
          </pre>
        ) : null}
      </section>

      <section className="rounded-lg border border-amber-700/40 bg-amber-950/20 p-4 space-y-3">
        <div className="flex items-center gap-2 text-amber-50 font-medium">
          <ShieldAlert className="w-4 h-4" />
          L5 claims_gate（核对门槛）
        </div>
        <p className="text-xs text-amber-100/75 leading-relaxed">
          默认 <code>explicit_authorize=false</code> → claim 恒 false。勾选授权也仅在门槛全过时才可能
          claim=true；正式报告仍默认 false。fixture / mixed / 适用未测不可解禁。
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {(
            [
              ['object_type', evObjectType, setEvObjectType],
              ['object_id', evObjectId, setEvObjectId],
              ['object_version', evVersion, setEvVersion],
              ['runtime_tier', evTier, setEvTier],
              ['plan_id', evPlanId, setEvPlanId],
              ['set_ids', evSetIds, setEvSetIds],
              ['oracle_types', evOracles, setEvOracles],
              ['dimensions', evDims, setEvDims],
              ['sample_n', evSampleN, setEvSampleN],
              ['untested_applicable_n', evUntested, setEvUntested],
            ] as Array<[string, string, (v: string) => void]>
          ).map(([label, val, set]) => (
            <label key={label} className="space-y-1">
              <span className="text-[11px] text-amber-200/70">{label}</span>
              <input
                className="w-full rounded border border-amber-800/50 bg-gray-950 px-2 py-1 text-amber-50"
                value={val}
                onChange={(e) => set(e.target.value)}
              />
            </label>
          ))}
        </div>
        <div className="flex flex-wrap gap-4 text-xs text-amber-100/85">
          <label className="inline-flex items-center gap-2">
            <input type="checkbox" checked={evHasRun} onChange={(e) => setEvHasRun(e.target.checked)} />
            has_run_evidence
          </label>
          <label className="inline-flex items-center gap-2">
            <input
              type="checkbox"
              checked={evRuntimeClaim}
              onChange={(e) => setEvRuntimeClaim(e.target.checked)}
            />
            runtime_claim
          </label>
          <label className="inline-flex items-center gap-2">
            <input
              type="checkbox"
              checked={evHumanReview}
              onChange={(e) => setEvHumanReview(e.target.checked)}
            />
            human_review（充分性）
          </label>
          <label className="inline-flex items-center gap-2">
            <input
              type="checkbox"
              checked={gateLocal}
              onChange={(e) => setGateLocal(e.target.checked)}
            />
            本机镜像（不调 API）
          </label>
          <label className="inline-flex items-center gap-2 text-amber-200">
            <input
              type="checkbox"
              checked={explicitAuthorize}
              onChange={(e) => setExplicitAuthorize(e.target.checked)}
              data-testid="eval-claims-authorize"
            />
            explicit_authorize（危险：仅门槛全过时抬 claim）
          </label>
        </div>
        <button
          type="button"
          data-testid="eval-claims-gate-run"
          disabled={gateBusy}
          onClick={() => void runGate()}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded border border-amber-600/60 bg-amber-950/50 text-amber-50 hover:bg-amber-900/40 disabled:opacity-50"
        >
          {gateBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldAlert className="w-4 h-4" />}
          核对 L5 门槛
        </button>
        {gateError ? <p className="text-xs text-red-300">{gateError}</p> : null}
        {gateResult ? (
          <div className="space-y-1" data-testid="eval-claims-gate-result">
            <p className="text-xs text-amber-100">
              eligible={String(gateResult.accuracy_eligible)}/
              {String(gateResult.sufficiency_eligible)} · claim=
              {String(gateResult.accuracy_claim)}/{String(gateResult.sufficiency_claim)} · authorize=
              {String(gateResult.explicit_authorize)}
            </p>
            {blockers.length ? (
              <p className="text-xs text-amber-200/80">阻断：{blockers.slice(0, 8).join('；')}</p>
            ) : (
              <p className="text-xs text-emerald-200/80">门槛全过（仍须显式授权才 claim）</p>
            )}
            <pre className="max-h-48 overflow-auto rounded border border-amber-800/40 bg-gray-950/80 p-2 text-[11px] text-amber-100/80">
              {JSON.stringify(gateResult, null, 2)}
            </pre>
          </div>
        ) : null}
      </section>
    </div>
  );
}
