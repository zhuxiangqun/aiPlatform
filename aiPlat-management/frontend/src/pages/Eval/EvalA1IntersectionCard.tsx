/**
 * Read-only A1 intersection rank gate / Pareto card.
 * No one-click certification; rank_claim never auto-true.
 */
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type A1Status = {
  ok?: boolean;
  eligible_n?: number;
  eligible_case_ids?: string[];
  signoff_status?: string;
  evidence_present?: boolean;
  rank_claim_allowed?: boolean;
  rank_claim?: boolean;
  accuracy_claim?: boolean;
  claim_sentence_template?: string;
  gate?: {
    ok?: boolean;
    blockers?: string[];
  } | null;
  pareto?: {
    frontier?: string[];
    single_winner?: string | null;
  } | null;
  min_n_protocol?: {
    engineering_min_n?: number;
    l5_default_min_sample_n?: number;
  };
  honesty?: string;
  modes_locked?: string[];
};

export default function EvalA1IntersectionCard() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<A1Status | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get<Envelope<A1Status>>(
        '/platform/apps/eval/store/a1-intersection-status',
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

  const gateOk = Boolean(status?.gate?.ok);
  const allowed = Boolean(status?.rank_claim_allowed);

  return (
    <div
      className="rounded-lg border border-teal-800/50 bg-teal-950/20 p-3 space-y-2 text-xs"
      data-testid="eval-a1-intersection-card"
    >
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h3 className="font-medium text-teal-100">A1 交集相对比较（只读）</h3>
        <button
          type="button"
          onClick={() => void load()}
          className="inline-flex items-center gap-1 px-2 py-1 rounded border border-gray-600 text-gray-300 hover:bg-gray-800"
          data-testid="eval-a1-intersection-refresh"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>
      <p className="text-teal-100/70">
        仅 plan_execute vs conversational · env tools/retrieval/session=none · 无一键认证
      </p>
      {error ? <p className="text-red-300">{error}</p> : null}
      {loading && !status ? (
        <p className="text-gray-500">加载中…</p>
      ) : status ? (
        <dl className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          <div>
            <dt className="text-gray-500">eligible</dt>
            <dd data-testid="eval-a1-eligible-n">{status.eligible_n ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-gray-500">signoff</dt>
            <dd>{status.signoff_status ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-gray-500">evidence</dt>
            <dd>{status.evidence_present ? 'present' : 'missing'}</dd>
          </div>
          <div>
            <dt className="text-gray-500">gate</dt>
            <dd data-testid="eval-a1-gate-ok">{gateOk ? 'ok' : 'blocked'}</dd>
          </div>
          <div>
            <dt className="text-gray-500">Pareto frontier</dt>
            <dd data-testid="eval-a1-pareto">
              {(status.pareto?.frontier || []).join(', ') || '—'}
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">rank_claim_allowed</dt>
            <dd data-testid="eval-a1-rank-allowed">{String(allowed)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">rank_claim</dt>
            <dd data-testid="eval-a1-rank-claim">{String(Boolean(status.rank_claim))}</dd>
          </div>
          <div>
            <dt className="text-gray-500">eng min_n / L5</dt>
            <dd>
              {status.min_n_protocol?.engineering_min_n ?? 2}/
              {status.min_n_protocol?.l5_default_min_sample_n ?? 100}
            </dd>
          </div>
        </dl>
      ) : null}
      {status?.claim_sentence_template ? (
        <p className="text-gray-400 italic" data-testid="eval-a1-claim-template">
          {status.claim_sentence_template}
        </p>
      ) : null}
      {status?.gate?.blockers?.length ? (
        <p className="text-amber-200/80">blockers: {status.gate.blockers.join('; ')}</p>
      ) : null}
    </div>
  );
}
