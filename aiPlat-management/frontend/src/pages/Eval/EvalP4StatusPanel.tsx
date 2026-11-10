/**
 * P4 honesty panel — benchmark quotas/holdout + judge engineering bar (claim closed).
 */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type P4Status = {
  ok?: boolean;
  profile_id?: string;
  ready_for_benchmark_quotas?: boolean;
  n_gaps?: number;
  case_count?: number;
  holdout?: { enabled?: boolean; n_holdout?: number; n_eval?: number };
  manifest_case_count?: number;
  manifest_hash?: string;
  judge_gate?: {
    meets_engineering_bar?: boolean;
    agreement?: number | null;
    threshold?: number;
    report_only?: boolean;
  };
  next_action?: string;
  review_links?: { case_packs_tab?: string; p1_regression_tab?: string };
  accuracy_claim?: boolean;
  claim_eligible?: boolean;
  report_only?: boolean;
  honesty?: string;
};

type Props = { tenantId?: string };

export default function EvalP4StatusPanel(_props: Props = {}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<P4Status | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get<Envelope<P4Status>>(
        `/platform/apps/eval/store/p4-status`,
      );
      setStatus(unwrap(res));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const packsHref = status?.review_links?.case_packs_tab || '/eval?tab=case-packs';
  const p1Href = status?.review_links?.p1_regression_tab || '/eval?tab=p1-regression';
  const judge = status?.judge_gate || {};
  const hold = status?.holdout || {};

  return (
    <div className="space-y-4 text-sm" data-testid="eval-p4-status-panel">
      <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90 space-y-1">
        <div className="font-medium">P4 Benchmark / Judge 诚实门（ADR）</div>
        <ul className="list-disc pl-5 space-y-0.5">
          <li>
            benchmark quotas：{status?.ready_for_benchmark_quotas ? '齐' : '缺口'} · gaps=
            {status?.n_gaps ?? '—'}
          </li>
          <li>
            judge engineering bar：
            {String(Boolean(judge.meets_engineering_bar))} · agreement=
            {judge.agreement == null ? 'null' : String(judge.agreement)} · threshold=
            {judge.threshold ?? '—'}
          </li>
          <li>
            claim_eligible={String(Boolean(status?.claim_eligible))} · accuracy_claim=
            {String(Boolean(status?.accuracy_claim))} · report_only=
            {String(Boolean(status?.report_only ?? true))}
          </li>
          <li>{status?.honesty || '配额齐 / 工程条达标 ≠ accuracy / Certification。'}</li>
        </ul>
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">
            {status?.profile_id || 'agent.benchmark.v1'} · P4 快照
          </h2>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-gray-600 text-xs text-gray-300 hover:bg-gray-800"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
        {error ? <p className="text-red-300 text-xs">{error}</p> : null}
        {loading && !status ? (
          <p className="text-gray-500">加载中…</p>
        ) : status ? (
          <>
            <p className="text-xs text-gray-400">
              cases={status.case_count ?? '—'} · manifest=
              {status.manifest_case_count ?? '—'} · holdout=
              {hold.enabled ? `on n=${hold.n_holdout ?? 0} eval=${hold.n_eval ?? 0}` : 'off'} ·
              hash=
              {status.manifest_hash
                ? `${String(status.manifest_hash).slice(0, 16)}…`
                : '—'}
            </p>
            <p className="text-xs text-sky-200/90">下一步：{status.next_action}</p>
            <div className="flex flex-wrap gap-3 text-xs">
              <Link className="text-sky-300 hover:underline" to={packsHref}>
                打开 Case Pack（judge / holdout）
              </Link>
              <Link className="text-sky-300 hover:underline" to={p1Href}>
                打开 P1 Regression
              </Link>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
