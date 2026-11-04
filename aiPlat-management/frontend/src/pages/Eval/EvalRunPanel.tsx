/**
 * UI-1 — unified Eval Run Panel.
 * Sync plane: cohost CoreFacade (match_only / prompt runs / kb-eval).
 * Job plane: package enqueue + poll/cancel when upstream mode=proxy.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Play, Square, RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';
import {
  evalExecutionErrorCode,
  messageForEvalExecutionPayload,
} from './evalExecutionErrors';
import {
  defaultCodeReviewJobPayload,
  formatEvalJobSummary,
  isEvalJobTerminal,
} from './evalRunPanelHelpers';

export type EvalRunKind = 'code_review' | 'prompt_eval' | 'kb_rag';

type Props = {
  kind: EvalRunKind;
  upstreamMode?: string | null;
  tenantId?: string;
};

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type JobRow = {
  job_id?: string;
  status?: string;
  runner_id?: string;
  detail?: string;
  result_json?: unknown;
};

const KIND_META: Record<
  EvalRunKind,
  { title: string; syncHint: string; packagePath: string; runnerId: string }
> = {
  code_review: {
    title: 'Code-review gold',
    syncHint: 'Cohost match_only（fixture predicted，无 LLM）',
    packagePath: '/platform/apps/eval/package/code-review-gold/run',
    runnerId: 'code_review_gold',
  },
  prompt_eval: {
    title: 'Prompt eval',
    syncHint: 'Cohost POST …/prompts/eval/runs（需 template + 两版本）',
    packagePath: '/platform/apps/eval/package/prompts/eval/runs',
    runnerId: 'prompt_eval',
  },
  kb_rag: {
    title: 'Knowledge eval',
    syncHint: 'Cohost POST …/kb-eval/run（样本库为空会 404）',
    packagePath: '/platform/apps/eval/package/kb-eval/run',
    runnerId: 'kb_rag',
  },
};

export default function EvalRunPanel({ kind, upstreamMode, tenantId = 'eval-v1' }: Props) {
  const meta = KIND_META[kind];
  const jobPlane = String(upstreamMode || '').toLowerCase() === 'proxy';

  const [syncBusy, setSyncBusy] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [reportsPreview, setReportsPreview] = useState<string>('');

  const [templateId, setTemplateId] = useState('');
  const [versionA, setVersionA] = useState('v1');
  const [versionB, setVersionB] = useState('v2');
  const [kbTag, setKbTag] = useState('');

  const [jobBusy, setJobBusy] = useState(false);
  const [job, setJob] = useState<JobRow | null>(null);
  const [jobMsg, setJobMsg] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPoll(), [stopPoll]);

  const loadReports = useCallback(async () => {
    try {
      if (kind === 'code_review') {
        const res = await apiClient.get<Envelope<{ items?: unknown[]; total?: number }>>(
          `/platform/apps/eval/code-review-gold/reports?tenant_id=${encodeURIComponent(tenantId)}&limit=5`,
        );
        const d = unwrap(res) as { items?: unknown[]; total?: number };
        const n = d?.total ?? (Array.isArray(d?.items) ? d.items.length : 0);
        setReportsPreview(`reports total≈${n}（最近 ${Math.min(5, n)} 条可读）`);
      } else if (kind === 'prompt_eval') {
        const res = await apiClient.get<Envelope<{ items?: unknown[]; total?: number }>>(
          `/platform/apps/eval/prompts/eval/runs?limit=5`,
        );
        const d = unwrap(res) as { items?: unknown[]; total?: number };
        const n = d?.total ?? (Array.isArray(d?.items) ? d.items.length : 0);
        setReportsPreview(`prompt runs ≈${n}`);
      } else {
        const res = await apiClient.get<Envelope<{ items?: unknown[]; total?: number }>>(
          `/platform/apps/eval/kb-eval/reports?limit=5`,
        );
        const d = unwrap(res) as { items?: unknown[]; total?: number };
        const n = d?.total ?? (Array.isArray(d?.items) ? d.items.length : 0);
        setReportsPreview(`kb reports ≈${n}`);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setReportsPreview(`读取失败: ${msg}`);
    }
  }, [kind, tenantId]);

  useEffect(() => {
    void loadReports();
  }, [loadReports]);

  const runSync = async () => {
    setSyncBusy(true);
    setSyncMsg(null);
    try {
      if (kind === 'code_review') {
        const res = await apiClient.post<{
          data?: {
            ok?: boolean;
            reason?: string;
            precision?: number | null;
            recall?: number | null;
            p0_recall?: number | null;
            case_count?: number;
            gold_dir?: string;
          };
        }>('/platform/apps/eval/code-review-gold/evaluate', {
          match_only: true,
          persist: true,
          limit: 5,
          record_novel: false,
          profile: 'balanced',
          tenant_id: tenantId,
        });
        const d = unwrap(res) as {
          ok?: boolean;
          reason?: string;
          precision?: number | null;
          recall?: number | null;
          p0_recall?: number | null;
          case_count?: number;
          gold_dir?: string;
        };
        if (!d?.ok) {
          setSyncMsg(
            `失败: ${d?.reason || 'unknown'}${d?.gold_dir ? ` · dir=${d.gold_dir}` : ''} · tip: ops_harness_ready_check.sh --install-seeds`,
          );
        } else {
          setSyncMsg(
            `match-only ok · cases=${d.case_count ?? '—'} · P=${d.precision ?? '—'} · R=${d.recall ?? '—'} · P0=${d.p0_recall ?? '—'}`,
          );
        }
      } else if (kind === 'prompt_eval') {
        if (!templateId.trim()) {
          setSyncMsg('请填写 template_id');
          return;
        }
        const res = await apiClient.post<Envelope<{ run_id?: string; status?: string; ok?: boolean }>>(
          '/platform/apps/eval/prompts/eval/runs',
          {
            template_id: templateId.trim(),
            version_a: versionA.trim() || 'v1',
            version_b: versionB.trim() || 'v2',
            model: '',
            case_ids: [],
          },
        );
        const d = unwrap(res) as { run_id?: string; status?: string; ok?: boolean; id?: string };
        setSyncMsg(
          `sync run · id=${d.run_id || d.id || '—'} · status=${d.status || (d.ok ? 'ok' : '—')}`,
        );
      } else {
        const body: Record<string, unknown> = {};
        if (kbTag.trim()) body.tag = kbTag.trim();
        const res = await apiClient.post<Envelope<{ session_id?: string; ok?: boolean; status?: string }>>(
          '/platform/apps/eval/kb-eval/run',
          body,
        );
        const d = unwrap(res) as { session_id?: string; ok?: boolean; status?: string };
        setSyncMsg(
          `kb sync · session=${d.session_id || '—'} · status=${d.status || (d.ok ? 'ok' : '—')}`,
        );
      }
      await loadReports();
    } catch (e: unknown) {
      const err = e as { message?: string; payload?: unknown };
      const mapped = messageForEvalExecutionPayload(err?.payload);
      setSyncMsg(mapped || `请求失败: ${err?.message || String(e)}`);
    } finally {
      setSyncBusy(false);
    }
  };

  const pollJob = useCallback(
    async (jobId: string) => {
      try {
        const res = await apiClient.get<Envelope<JobRow>>(
          `/platform/apps/eval/jobs/${encodeURIComponent(jobId)}`,
        );
        const row = unwrap(res) as JobRow;
        setJob(row);
        setJobMsg(formatEvalJobSummary(row));
        if (isEvalJobTerminal(row.status)) {
          stopPoll();
          setJobBusy(false);
        }
      } catch (e: unknown) {
        const err = e as { message?: string; payload?: unknown };
        const code = evalExecutionErrorCode(err?.payload);
        const mapped = messageForEvalExecutionPayload(err?.payload);
        setJobMsg(mapped || `poll 失败: ${err?.message || String(e)}${code ? ` (${code})` : ''}`);
        stopPoll();
        setJobBusy(false);
      }
    },
    [stopPoll],
  );

  const enqueueJob = async () => {
    if (!jobPlane) return;
    setJobBusy(true);
    setJobMsg(null);
    setJob(null);
    stopPoll();
    try {
      let body: Record<string, unknown> = { idempotency_key: `ui1-${kind}-${Date.now()}` };
      if (kind === 'code_review') {
        body = { ...defaultCodeReviewJobPayload() };
      } else if (kind === 'prompt_eval') {
        body = {
          ...body,
          template_id: templateId.trim() || 'demo',
          version_a: versionA.trim() || 'v1',
          version_b: versionB.trim() || 'v2',
        };
      } else if (kbTag.trim()) {
        body = { ...body, tag: kbTag.trim() };
      }
      const res = await apiClient.post<Envelope<JobRow>>(meta.packagePath, body);
      const row = unwrap(res) as JobRow;
      const jobId = String(row.job_id || '');
      if (!jobId) {
        setJobMsg('enqueue 无 job_id');
        setJobBusy(false);
        return;
      }
      setJob(row);
      setJobMsg(formatEvalJobSummary(row));
      pollRef.current = setInterval(() => {
        void pollJob(jobId);
      }, 2000);
      void pollJob(jobId);
    } catch (e: unknown) {
      const err = e as { message?: string; payload?: unknown };
      const mapped = messageForEvalExecutionPayload(err?.payload);
      setJobMsg(mapped || `enqueue 失败: ${err?.message || String(e)}`);
      setJobBusy(false);
    }
  };

  const cancelJob = async () => {
    const jobId = job?.job_id;
    if (!jobId) return;
    try {
      const res = await apiClient.post<Envelope<JobRow & { ok?: boolean; job?: JobRow }>>(
        `/platform/apps/eval/jobs/${encodeURIComponent(jobId)}/cancel`,
        {},
      );
      const body = unwrap(res) as { ok?: boolean; job?: JobRow };
      const next = body.job || (body as JobRow);
      setJob(next);
      setJobMsg(formatEvalJobSummary(next));
      if (isEvalJobTerminal(next.status)) {
        stopPoll();
        setJobBusy(false);
      }
    } catch (e: unknown) {
      const err = e as { message?: string; payload?: unknown };
      const mapped = messageForEvalExecutionPayload(err?.payload);
      setJobMsg(mapped || `cancel 失败: ${err?.message || String(e)}`);
    }
  };

  return (
    <div
      className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-4 text-sm"
      data-testid="eval-run-panel"
      data-kind={kind}
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h3 className="font-medium text-gray-100">{meta.title} · Run</h3>
          <p className="text-gray-500 mt-0.5">{meta.syncHint}</p>
        </div>
        <button
          type="button"
          onClick={() => void loadReports()}
          className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-gray-600 text-xs text-gray-300 hover:bg-gray-800"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          刷新报告
        </button>
      </div>

      {kind === 'prompt_eval' ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <label className="space-y-1">
            <span className="text-xs text-gray-500">template_id</span>
            <input
              className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-200"
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              placeholder="prompt template id"
            />
          </label>
          <label className="space-y-1">
            <span className="text-xs text-gray-500">version_a</span>
            <input
              className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-200"
              value={versionA}
              onChange={(e) => setVersionA(e.target.value)}
            />
          </label>
          <label className="space-y-1">
            <span className="text-xs text-gray-500">version_b</span>
            <input
              className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-200"
              value={versionB}
              onChange={(e) => setVersionB(e.target.value)}
            />
          </label>
        </div>
      ) : null}

      {kind === 'kb_rag' ? (
        <label className="block space-y-1 max-w-xs">
          <span className="text-xs text-gray-500">tag（可选）</span>
          <input
            className="w-full px-2 py-1.5 rounded bg-gray-950 border border-gray-700 text-gray-200"
            value={kbTag}
            onChange={(e) => setKbTag(e.target.value)}
            placeholder="filter samples by tag"
          />
        </label>
      ) : null}

      <div className="flex flex-wrap gap-2 items-center">
        <button
          type="button"
          data-testid="eval-run-sync"
          disabled={syncBusy}
          onClick={() => void runSync()}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded bg-blue-700/80 hover:bg-blue-600 disabled:opacity-50 text-white"
        >
          {syncBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          {kind === 'code_review' ? 'Run match-only' : 'Run sync'}
        </button>
        {jobPlane ? (
          <>
            <button
              type="button"
              data-testid="eval-run-enqueue"
              disabled={jobBusy && !job?.job_id}
              onClick={() => void enqueueJob()}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded border border-violet-600/80 text-violet-200 hover:bg-violet-950/40 disabled:opacity-50"
            >
              {jobBusy && !isEvalJobTerminal(job?.status) ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Play className="w-4 h-4" />
              )}
              Enqueue job
            </button>
            <button
              type="button"
              data-testid="eval-run-cancel"
              disabled={!job?.job_id || isEvalJobTerminal(job?.status)}
              onClick={() => void cancelJob()}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded border border-gray-600 text-gray-300 hover:bg-gray-800 disabled:opacity-40"
            >
              <Square className="w-3.5 h-3.5" />
              Cancel
            </button>
          </>
        ) : (
          <span className="text-xs text-gray-500">
            Job 平面需 <code className="text-gray-400">AIPLAT_EVAL_SERVICE_URL</code>（mode=proxy）
          </span>
        )}
      </div>

      {syncMsg ? (
        <p className="text-gray-300 font-mono text-xs whitespace-pre-wrap" data-testid="eval-run-sync-msg">
          {syncMsg}
        </p>
      ) : null}
      {jobMsg ? (
        <p className="text-violet-200/90 font-mono text-xs whitespace-pre-wrap" data-testid="eval-run-job-msg">
          {jobMsg}
        </p>
      ) : null}
      {reportsPreview ? <p className="text-gray-500 text-xs">{reportsPreview}</p> : null}
      <p className="text-[11px] text-gray-600">
        accuracy_claim=false · process_split_authorized=false · runner={meta.runnerId}
      </p>
    </div>
  );
}
