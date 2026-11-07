/**
 * Local standard smoke: Evaluation Plan selects papers; BUILTIN_EXAM_SUITE is template only.
 * Requires local LLM preflight; does not cover online/κ.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Eye, Loader2, Play, Square } from 'lucide-react';
import { agentEvalApi } from '../../services';
import {
  clearSmokeEvalPageFields,
  patchPageData,
} from '../../lib/pageDataBridge';
import type { AttributableReport } from './EvalAttributableReportCard';
import {
  BUILTIN_EXAM_SUITE,
  DEFAULT_SMOKE_PURPOSES,
  EXAM_SUITE_HONESTY,
  SMOKE_PURPOSE_OPTIONS,
  SUITE_TEMPLATE_SET_IDS,
  buildDimensionMatrix,
  formatSmokeIssuesForPage,
  initialSuitePaperResults,
  mapPlanToPaperRows,
  matrixActionItems,
  matrixStatusLabel,
  papersFromPlanPreview,
  planIntentPreviewLabel,
  preferredSetForDim,
  suiteRunLabel,
  type MatrixStatus,
  type PlanCaseRow,
  type PlanPreviewInput,
  type SuitePaperResult,
} from './examSuite';
import { buildFullSmokeReport } from './fullExamReport';
import EvalFullReportPanel from './EvalFullReportPanel';
import { checkLocalExamPreflight } from './localExamPreflight';
import { formatRuntimeAnn, agentExamRuntimeAnn } from './examRuntimeTier';

type PlanPreviewState = PlanPreviewInput & {
  plan_id: string;
  selected_cases: PlanCaseRow[];
  excluded_cases: PlanCaseRow[];
  counts: Record<string, number>;
  eval_profile_source: string;
  purpose: string[];
};

type Props = {
  agentId: string;
  /** Single-paper exam busy — disable suite start. */
  disabled?: boolean;
  onBusyChange?: (busy: boolean) => void;
  /** After each paper finishes (local focus only — avoid heavy parent refresh here). */
  onPaperDone?: (setId: string) => void;
  /** After whole suite settles — safe place to refresh history dashboard once. */
  onSuiteDone?: (lastSetId?: string) => void;
  /** Jump to single-paper tab to inspect a failing/warn dimension. */
  onInspectDim?: (payload: {
    dimId: string;
    setId: string;
    title: string;
    status: MatrixStatus;
  }) => void;
};

function statusClass(s: MatrixStatus): string {
  if (s === 'pass') return 'text-green-300';
  if (s === 'fail') return 'text-red-300';
  if (s === 'warn' || s === 'inconclusive') return 'text-amber-300';
  if (s === 'not_applicable') return 'text-slate-400';
  if (s === 'missing' || s === 'untested') return 'text-gray-400';
  return 'text-sky-300';
}

function paperStatusLabel(p: SuitePaperResult): string {
  if (p.status === 'running') return '跑卷中';
  if (p.status === 'done') {
    const score = p.composite_score != null ? String(p.composite_score) : '—';
    const grade = p.grade || '—';
    const veto = p.safety_veto ? ' · VETO' : '';
    return `${score} (${grade})${veto}`;
  }
  if (p.status === 'error') return `error: ${p.error || '?'}`;
  if (p.status === 'skipped') {
    const mr = p.attributable?.match_report as
      | { excluded_cases?: Array<{ set_id?: string; status?: string }> }
      | undefined;
    const ex = Array.isArray(mr?.excluded_cases)
      ? mr!.excluded_cases.find((x) => x.set_id === p.set_id)
      : undefined;
    if (ex?.status === 'not_applicable') return '不适用（Plan）';
    if (ex?.status === 'untested') return '未测·专项（Plan）';
    return '已跳过';
  }
  return '待跑';
}

function profileSourceHint(src: string): string {
  if (src === 'derived_hints') return '能力=skills/tools 推导（非锁定）';
  if (src === 'explicit') return '能力=显式 eval_profile';
  return src ? `profile=${src}` : '';
}

export default function EvalExamSuitePanel({
  agentId,
  disabled = false,
  onBusyChange,
  onPaperDone,
  onSuiteDone,
  onInspectDim,
}: Props) {
  const [papers, setPapers] = useState<SuitePaperResult[]>(() => initialSuitePaperResults());
  const [busy, setBusy] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [error, setError] = useState('');
  const [purposes, setPurposes] = useState<string[]>(() => [...DEFAULT_SMOKE_PURPOSES]);
  const [planPreview, setPlanPreview] = useState<PlanPreviewState | null>(null);
  const [planDirty, setPlanDirty] = useState(true);
  const abortRef = useRef(false);

  const matrix = useMemo(() => buildDimensionMatrix(papers), [papers]);
  const actions = useMemo(() => matrixActionItems(matrix), [matrix]);
  /** Any paper produced a result — used for live matrix while still running. */
  const suiteHasResults = papers.some((p) => p.status === 'done' || p.status === 'error');
  /**
   * Whole suite finished (or aborted after some papers): every row terminal and not busy.
   * Formal report / 待办 / 小朱 smoke feed only then — never mid-run.
   */
  const suiteComplete =
    !busy &&
    suiteHasResults &&
    papers.every(
      (p) => p.status === 'done' || p.status === 'error' || p.status === 'skipped',
    );
  /** Idle first paint: do not show a fake "in progress" result matrix. */
  const suiteStarted = busy || papers.some((p) => p.status !== 'pending');
  const fullReport = useMemo(
    () =>
      suiteComplete ? buildFullSmokeReport({ agentId, papers }) : null,
    [suiteComplete, agentId, papers],
  );

  const planRows = useMemo(
    () => (planPreview && !planDirty ? mapPlanToPaperRows(planPreview) : null),
    [planPreview, planDirty],
  );

  const planReady = Boolean(planPreview && !planDirty);

  // Feed 小朱 only after the full suite settles (avoid mid-run partial report).
  useEffect(() => {
    if (!suiteComplete) return;
    patchPageData('/eval', formatSmokeIssuesForPage(matrix, agentId));
  }, [suiteComplete, matrix, agentId]);

  // Keep-alive across single↔suite tabs: only wipe snapshot when Agent changes.
  const prevAgentRef = useRef(agentId);
  useEffect(() => {
    if (prevAgentRef.current === agentId) return;
    prevAgentRef.current = agentId;
    if (busy) return;
    clearSmokeEvalPageFields('/eval');
    setPapers(initialSuitePaperResults());
    setPlanPreview(null);
    setPlanDirty(true);
    setMsg('');
    setError('');
  }, [agentId, busy]);

  const setBusyBoth = useCallback(
    (v: boolean) => {
      setBusy(v);
      onBusyChange?.(v);
    },
    [onBusyChange],
  );

  const patchPaper = useCallback((runKey: string, patch: Partial<SuitePaperResult>) => {
    setPapers((prev) => prev.map((p) => (p.run_key === runKey ? { ...p, ...patch } : p)));
  }, []);

  const stop = useCallback(() => {
    abortRef.current = true;
    setMsg('将在当前卷结束后中止…');
  }, []);

  const togglePurpose = useCallback((id: string) => {
    setPurposes((prev) => {
      const has = prev.includes(id);
      if (has) {
        if (prev.length <= 1) return prev;
        return prev.filter((x) => x !== id);
      }
      return [...prev, id];
    });
    setPlanDirty(true);
  }, []);

  const compilePlanSnapshot = useCallback(async (aid: string, purposeList: string[]) => {
    const planRes = await agentEvalApi.compilePlan({
      agent_id: aid,
      set_ids: SUITE_TEMPLATE_SET_IDS,
      purpose: purposeList,
      live: true,
    });
    if (planRes?.ok === false || !planRes?.plan) {
      throw new Error(String(planRes?.error || 'compile-plan failed'));
    }
    const plan = planRes.plan;
    const src = String(
      planRes.eval_profile_source ||
        (plan as { eval_profile_source?: string }).eval_profile_source ||
        '',
    ).trim();
    const snap: PlanPreviewState = {
      plan_id: String(plan.plan_id || ''),
      selected_cases: plan.selected_cases || [],
      excluded_cases: plan.excluded_cases || [],
      counts: plan.counts || {},
      eval_profile_source: src,
      purpose: [...purposeList],
    };
    if (!snap.selected_cases.length && !snap.excluded_cases.length) {
      throw new Error('compile-plan returned empty selected/excluded');
    }
    return snap;
  }, []);

  const previewPlan = useCallback(async () => {
    const aid = agentId.trim();
    if (!aid) {
      setError('请先选择 Agent');
      return;
    }
    if (aid.startsWith('ext:')) {
      setError('本地冒烟仅支持本机 Agent；请切换到「本机 Agent」，不要用外部目标。');
      return;
    }
    if (!purposes.length) {
      setError('至少选择一个评测目的');
      return;
    }
    setError('');
    setPreviewBusy(true);
    setMsg('编译 Evaluation Plan…');
    try {
      const snap = await compilePlanSnapshot(aid, purposes);
      setPlanPreview(snap);
      setPlanDirty(false);
      const c = snap.counts;
      const hint = profileSourceHint(snap.eval_profile_source);
      setMsg(
        `Plan ${snap.plan_id || 'ok'}：跑 ${c.selected ?? snap.selected_cases.length}` +
          ` · 不适用 ${c.not_applicable ?? 0}` +
          ` · 专项未测 ${c.untested ?? 0}` +
          (hint ? ` · ${hint}` : ''),
      );
    } catch (e: unknown) {
      setPlanPreview(null);
      setPlanDirty(true);
      setError(`Plan 编译失败：${e instanceof Error ? e.message : String(e)}（已阻断开跑，请修正后重试预览）`);
      setMsg('');
    } finally {
      setPreviewBusy(false);
    }
  }, [agentId, purposes, compilePlanSnapshot]);

  const runSuite = useCallback(async () => {
    const aid = agentId.trim();
    if (!aid) {
      setError('请先选择 Agent');
      return;
    }
    if (aid.startsWith('ext:')) {
      setError('本地冒烟仅支持本机 Agent；请切换到「本机 Agent」，不要用外部目标。');
      return;
    }
    if (!purposes.length) {
      setError('至少选择一个评测目的');
      return;
    }

    setError('');
    setMsg('检查本机模型…');
    const pre = await checkLocalExamPreflight();
    if (!pre.ok) {
      setError(pre.message);
      setMsg('');
      return;
    }

    let snap = planPreview && !planDirty ? planPreview : null;
    if (!snap) {
      setMsg(`编译 Evaluation Plan… ${pre.message}`);
      try {
        snap = await compilePlanSnapshot(aid, purposes);
        setPlanPreview(snap);
        setPlanDirty(false);
      } catch (e: unknown) {
        setError(
          `Plan 编译失败：${e instanceof Error ? e.message : String(e)}（已阻断开跑，不再回退全套）`,
        );
        setMsg('');
        return;
      }
    }

    const selectedSets = new Set(
      snap.selected_cases.map((x) => String(x.set_id || '').trim()).filter(Boolean),
    );
    if (!selectedSets.size) {
      setError('Plan 入选为空：没有可执行的卷（请检查 eval_profile / purpose）');
      setMsg('');
      return;
    }

    abortRef.current = false;
    clearSmokeEvalPageFields('/eval');
    setPapers(papersFromPlanPreview(snap, snap.plan_id));
    setBusyBoth(true);
    let lastFinishedSet = '';

    const hint = profileSourceHint(snap.eval_profile_source);
    setMsg(
      `Plan ${snap.plan_id || 'ok'}：跑 ${snap.counts.selected ?? selectedSets.size}` +
        ` · 不适用 ${snap.counts.not_applicable ?? 0}` +
        ` · 专项未测 ${snap.counts.untested ?? 0}` +
        (hint ? ` · ${hint}` : '') +
        `。开始 live… ${pre.message}`,
    );

    try {
      for (const paper of BUILTIN_EXAM_SUITE) {
        if (abortRef.current) {
          setPapers((prev) =>
            prev.map((p) =>
              p.status === 'pending' || p.status === 'running'
                ? { ...p, status: 'skipped' as const }
                : p,
            ),
          );
          setMsg('已中止；已完成卷的结果保留在矩阵中');
          break;
        }

        if (!selectedSets.has(paper.set_id)) {
          // Already seeded as skipped by papersFromPlanPreview; keep as-is.
          continue;
        }

        patchPaper(paper.run_key, { status: 'running', error: undefined });
        setMsg(`正在正式评测 ${suiteRunLabel(paper)}…`);

        try {
          const res = await agentEvalApi.runExam({
            agent_id: aid,
            set_id: paper.set_id,
            live: true,
          });
          if (res?.ok === false || res?.error) {
            patchPaper(paper.run_key, {
              status: 'error',
              error: String(res.error || 'exam failed'),
            });
          } else {
            const ar = (res.attributable_report || {}) as AttributableReport;
            const dims = (ar.dimensions || {}) as SuitePaperResult['dimensions'];
            const arAny = ar as unknown as Record<string, unknown>;
            const resAny = res as Record<string, unknown>;
            const slimAr = {
              composite_score: res.composite_score ?? ar.composite_score ?? null,
              grade: res.grade || ar.grade,
              dimensions: dims,
              legacy_dim_scores: arAny.legacy_dim_scores ?? null,
              gate: ar.gate,
              publish: ar.publish,
              eval_time: arAny.eval_time ?? null,
              model: arAny.model ?? resAny.model ?? null,
              model_params: arAny.model_params ?? null,
              agent_version: arAny.agent_version ?? null,
              agent_skills: arAny.agent_skills ?? null,
              code_revision: arAny.code_revision ?? resAny.code_revision ?? null,
              run_id: arAny.run_id ?? arAny.eval_run_id ?? resAny.run_id ?? null,
              runtime_tier: resAny.runtime_tier ?? arAny.runtime_tier ?? null,
              runtime_claim: resAny.runtime_claim ?? arAny.runtime_claim ?? null,
              runtime_claim_reason:
                resAny.runtime_claim_reason ?? arAny.runtime_claim_reason ?? null,
              match_report: resAny.match_report ?? arAny.match_report ?? null,
              target_contract: resAny.target_contract ?? arAny.target_contract ?? null,
              evaluation_plan: resAny.evaluation_plan ?? arAny.evaluation_plan ?? null,
              eval_profile_source:
                resAny.eval_profile_source ??
                arAny.eval_profile_source ??
                snap.eval_profile_source ??
                null,
              plan_id: (resAny.plan_id ?? arAny.plan_id ?? snap.plan_id) || null,
              conclusion: {
                failure_evidence: ar.conclusion?.failure_evidence || [],
                failure_evidence_count: ar.conclusion?.failure_evidence_count,
              },
            };
            patchPaper(paper.run_key, {
              status: 'done',
              composite_score: res.composite_score ?? ar.composite_score ?? null,
              grade: res.grade || ar.grade,
              total_tasks: res.total_tasks,
              safety_veto: Boolean(res.safety_veto || ar.gate?.veto || ar.publish?.veto),
              dimensions: dims,
              attributable: slimAr as unknown as Record<string, unknown>,
            });
          }
          lastFinishedSet = paper.set_id;
          onPaperDone?.(paper.set_id);
        } catch (e: unknown) {
          patchPaper(paper.run_key, {
            status: 'error',
            error: e instanceof Error ? e.message : String(e),
          });
          lastFinishedSet = paper.set_id;
          onPaperDone?.(paper.set_id);
        }
      }

      if (!abortRef.current) {
        setMsg(
          '连跑完成。请看下方待办和结果表；Plan 跳过的不适用/专项未测与线上未覆盖项均不算合格。',
        );
      }
      onSuiteDone?.(lastFinishedSet || undefined);
    } finally {
      setBusyBoth(false);
      abortRef.current = false;
    }
  }, [
    agentId,
    purposes,
    planPreview,
    planDirty,
    compilePlanSnapshot,
    onPaperDone,
    onSuiteDone,
    patchPaper,
    setBusyBoth,
  ]);

  return (
    <section
      className="rounded-lg border border-violet-700/40 bg-violet-950/15 p-4 space-y-3 text-sm"
      data-testid="eval-exam-suite-panel"
    >
      <div>
        <h2 className="font-medium text-violet-100">连跑冒烟</h2>
        <p className="text-xs text-violet-100/70 mt-1">
          按 Evaluation Plan 选题连跑（模板=内置卷，含正常题复跑、多轮记忆）。用本机模型，不连外网商业 API。
          先预览 Plan 再开跑；跑完看「待办」和「结果表」——这是体检，不是上线认证。
        </p>
        <details className="mt-1">
          <summary className="cursor-pointer text-[11px] text-gray-500">技术说明（可展开）</summary>
          <p className="text-[11px] text-gray-500 mt-1 font-mono">{EXAM_SUITE_HONESTY}</p>
          <p className="text-[11px] text-sky-200/80 mt-0.5 font-mono">
            {formatRuntimeAnn(agentExamRuntimeAnn(true))}
          </p>
        </details>
      </div>

      <div className="space-y-1.5" data-testid="eval-exam-suite-purpose">
        <div className="text-[11px] text-gray-400">评测目的（改勾后需重新预览 Plan）</div>
        <div className="flex flex-wrap gap-3">
          {SMOKE_PURPOSE_OPTIONS.map((opt) => {
            const checked = purposes.includes(opt.id);
            return (
              <label
                key={opt.id}
                className="inline-flex items-center gap-1.5 text-xs text-gray-200 cursor-pointer"
              >
                <input
                  type="checkbox"
                  data-testid={`eval-exam-suite-purpose-${opt.id}`}
                  checked={checked}
                  disabled={busy || previewBusy}
                  onChange={() => togglePurpose(opt.id)}
                  className="rounded border-gray-600"
                />
                {opt.label}
                <span className="font-mono text-gray-500">{opt.id}</span>
              </label>
            );
          })}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          data-testid="eval-exam-suite-preview"
          disabled={busy || previewBusy || disabled || !agentId.trim()}
          onClick={() => void previewPlan()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-sky-600/60 text-sky-100 hover:bg-sky-950/40 disabled:opacity-50 text-xs"
        >
          {previewBusy ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Eye className="w-3.5 h-3.5" />
          )}
          预览 Plan
        </button>
        <button
          type="button"
          data-testid="eval-exam-suite-run"
          disabled={busy || previewBusy || disabled || !agentId.trim()}
          onClick={() => void runSuite()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-violet-500/70 text-violet-100 hover:bg-violet-950/50 disabled:opacity-50 text-xs"
        >
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
          开始连跑
        </button>
        <button
          type="button"
          data-testid="eval-exam-suite-stop"
          disabled={!busy}
          onClick={stop}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-gray-600 text-gray-200 hover:bg-gray-800 disabled:opacity-50 text-xs"
        >
          <Square className="w-3.5 h-3.5" />
          中止（当前这套跑完后停）
        </button>
      </div>

      {planDirty && planPreview ? (
        <p className="text-[11px] text-amber-200/90" data-testid="eval-exam-suite-plan-dirty">
          目的已改，当前预览已过期——请重新「预览 Plan」或直接「开始连跑」（会先编译）。
        </p>
      ) : null}

      {planReady && planPreview ? (
        <div
          className="rounded border border-sky-800/50 bg-sky-950/20 px-3 py-2 space-y-1"
          data-testid="eval-exam-suite-plan-preview"
        >
          <div className="text-xs text-sky-100 font-medium">Evaluation Plan 预览</div>
          <p className="text-[11px] font-mono text-sky-100/80">
            plan_id={planPreview.plan_id || '—'}
            {planPreview.eval_profile_source
              ? ` · ${profileSourceHint(planPreview.eval_profile_source) || planPreview.eval_profile_source}`
              : ''}
          </p>
          <p className="text-[11px] text-gray-300">
            入选 {planPreview.counts.selected ?? planPreview.selected_cases.length}
            {' · '}不适用 {planPreview.counts.not_applicable ?? 0}
            {' · '}专项未测 {planPreview.counts.untested ?? 0}
          </p>
          <div className="text-[11px] text-gray-400 space-y-0.5 max-h-28 overflow-y-auto">
            {(planPreview.selected_cases || []).map((c) => (
              <div key={`sel-${c.set_id}`} className="font-mono text-green-300/90">
                + {c.set_id}
                {c.pack ? ` (${c.pack})` : ''}
              </div>
            ))}
            {(planPreview.excluded_cases || []).map((c) => (
              <div key={`ex-${c.set_id}-${c.status}`} className="font-mono text-gray-400">
                − {c.set_id} · {c.status || 'excluded'}
                {Array.isArray(c.reasons) && c.reasons.length
                  ? ` · ${c.reasons.slice(0, 2).join('; ')}`
                  : ''}
              </div>
            ))}
          </div>
        </div>
      ) : !busy ? (
        <p className="text-[11px] text-gray-500" data-testid="eval-exam-suite-plan-hint">
          尚未预览 Plan。可先点「预览 Plan」看入选/排除；或点「开始连跑」时自动编译（失败则阻断，不回退全套）。
        </p>
      ) : null}

      {error ? <p className="text-xs text-red-300" data-testid="eval-exam-suite-error">{error}</p> : null}
      {msg ? (
        <p className="text-xs font-mono text-violet-100/90" data-testid="eval-exam-suite-msg">
          {msg}
        </p>
      ) : null}

      <div className="overflow-x-auto" data-testid="eval-exam-suite-progress">
        <h3 className="text-xs font-medium text-gray-200 mb-1">
          {suiteStarted
            ? '本轮步骤进度'
            : planRows
              ? 'Plan 映射步骤（尚未开跑）'
              : '模板步骤（预览 Plan 后显示入选/跳过）'}
        </h3>
        <table className="w-full text-xs text-left border-collapse">
          <thead>
            <tr className="text-gray-500 border-b border-gray-700">
              <th className="py-1.5 pr-2 font-medium">步骤</th>
              <th className="py-1.5 pr-2 font-medium">测什么</th>
              <th className="py-1.5 pr-2 font-medium">状态</th>
            </tr>
          </thead>
          <tbody>
            {(planRows || BUILTIN_EXAM_SUITE.map((m) => ({
              run_key: m.run_key,
              set_id: m.set_id,
              probes_what: m.probes_what,
              intent: 'run' as const,
            }))).map((meta) => {
              const paperMeta =
                BUILTIN_EXAM_SUITE.find((p) => p.run_key === meta.run_key) ||
                ({
                  run_key: meta.run_key,
                  set_id: meta.set_id,
                  probes_what: meta.probes_what,
                  probes: [],
                  slice_keys: [],
                } as const);
              const row = papers.find((p) => p.run_key === meta.run_key) || {
                run_key: meta.run_key,
                set_id: meta.set_id,
                status: 'pending' as const,
              };
              const statusText =
                suiteStarted || row.status !== 'pending'
                  ? paperStatusLabel(row)
                  : planRows
                    ? planIntentPreviewLabel(meta.intent)
                    : '待预览';
              return (
                <tr key={meta.run_key} className="border-b border-gray-800/80 text-gray-200">
                  <td className="py-1.5 pr-2 font-mono">{suiteRunLabel(paperMeta)}</td>
                  <td className="py-1.5 pr-2 text-gray-400">{meta.probes_what}</td>
                  <td className="py-1.5 pr-2 font-mono">{statusText}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {suiteComplete && actions.length ? (
        <div
          className="rounded-lg border border-amber-800/50 bg-amber-950/20 px-3 py-2 space-y-2"
          data-testid="eval-exam-suite-actions"
        >
          <h3 className="text-xs font-medium text-amber-100">待办（先改未通过的）</h3>
          <p className="text-[11px] text-amber-100/70">
            未通过优先改；「无法判定」=证据不够（如空工具轨迹）；「需留意」多半是信号弱；「未测」别当成过了。点「查看详情」会打开对应题集并带出当时结果——先看问题再改，别马上重跑。
          </p>
          <ul className="space-y-2">
            {actions.map((r) => {
              const jumpSet =
                r.covering_sets[0] || preferredSetForDim(r.id) || '';
              const canJump = Boolean(onInspectDim && jumpSet && !busy);
              return (
                <li
                  key={r.id}
                  className="text-xs border-b border-amber-900/40 pb-2 last:border-0 last:pb-0"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-amber-50 font-medium">{r.title}</span>
                    <span className={`font-mono ${statusClass(r.status)}`}>
                      {matrixStatusLabel(r.status)}
                    </span>
                    {canJump ? (
                      <button
                        type="button"
                        data-testid={`eval-exam-suite-inspect-${r.id}`}
                        className="ml-auto px-2 py-0.5 rounded border border-violet-600/60 text-violet-100 hover:bg-violet-950/50 text-[11px]"
                        onClick={() =>
                          onInspectDim?.({
                            dimId: r.id,
                            setId: jumpSet,
                            title: r.title,
                            status: r.status,
                          })
                        }
                      >
                        查看详情 · {jumpSet}
                      </button>
                    ) : r.status === 'untested' && !jumpSet ? (
                      <span className="ml-auto text-[11px] text-gray-500">
                        本地不覆盖 · 无需跳转
                      </span>
                    ) : null}
                  </div>
                  <p className="text-gray-300 mt-0.5">
                    <span className="text-gray-500">原因：</span>
                    {r.meaning}
                  </p>
                  <p className="text-violet-100/90 mt-0.5">
                    <span className="text-gray-500">怎么做：</span>
                    {r.next}
                  </p>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {fullReport ? (
        <EvalFullReportPanel
          report={fullReport}
          onInspectSet={
            onInspectDim
              ? (setId) =>
                  onInspectDim({
                    dimId: 'task_result',
                    setId,
                    title: setId,
                    status: 'fail',
                  })
              : undefined
          }
        />
      ) : null}

      {!suiteStarted ? (
        <p className="text-xs text-gray-500" data-testid="eval-exam-suite-matrix-empty">
          还没开始跑。预览 Plan 后点「开始连跑」，这里会出现完整报告、待办和各项结果。
        </p>
      ) : (
        <div className="overflow-x-auto" data-testid="eval-exam-suite-matrix">
          <h3 className="text-xs font-medium text-gray-200 mb-1">各项结果（本轮）</h3>
          <p className="text-[11px] text-gray-500 mb-2">
            看「结果」和「怎么做」即可。没测到的项（如真实线上）不要当成通过。这里不算总分榜。
          </p>
          <table className="w-full text-xs text-left border-collapse min-w-[720px]">
            <thead>
              <tr className="text-gray-500 border-b border-gray-700">
                <th className="py-1.5 pr-2 font-medium">检查项</th>
                <th className="py-1.5 pr-2 font-medium">结果</th>
                <th className="py-1.5 pr-2 font-medium">原因 / 怎么做</th>
                <th className="py-1.5 pr-2 font-medium">依据</th>
              </tr>
            </thead>
            <tbody>
              {matrix.map((r) => (
                <tr key={r.id} className="border-b border-gray-800/80 align-top">
                  <td className="py-1.5 pr-2 text-gray-200 whitespace-nowrap">
                    <div>{r.title}</div>
                    <div className="text-[10px] text-gray-500 font-mono">
                      {r.covering_sets.length ? r.covering_sets.join(', ') : '—'}
                    </div>
                  </td>
                  <td className={`py-1.5 pr-2 font-mono ${statusClass(r.status)}`}>
                    {matrixStatusLabel(r.status)}
                  </td>
                  <td className="py-1.5 pr-2 text-gray-300 max-w-[320px]">
                    <div>{r.meaning}</div>
                    <div className="text-violet-100/80 mt-0.5">{r.next}</div>
                  </td>
                  <td className="py-1.5 pr-2 text-gray-500 max-w-[240px] break-words font-mono text-[10px]">
                    {r.evidence}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
