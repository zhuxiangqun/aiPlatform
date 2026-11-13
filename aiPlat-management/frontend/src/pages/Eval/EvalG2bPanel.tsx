/**
 * G2b facilitation panel — pack/closeout facts; never claims accuracy.
 */
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type G2bStatus = {
  ok?: boolean;
  task_count?: number;
  target_n?: number;
  pack_ready?: boolean;
  closeout_n?: number;
  kappa_n?: number;
  accuracy_aggregate_n?: number;
  pending_dual_human?: number;
  dual_human_complete?: boolean;
  kappa?: number | null;
  kappa_kind?: string;
  accuracy_claim?: boolean;
  note?: string;
  runbook?: string;
  families?: Record<string, number>;
};

type G2bClaimUnlock = {
  schema?: string;
  accuracy_claim?: boolean;
  g2b_scoped_ready?: boolean;
  g2b_scoped_blockers?: string[];
  broader_trust_blockers?: string[];
  gates?: Record<string, boolean>;
  honesty?: string;
};

type G2bL5Gap = {
  ok?: boolean;
  pass_rate?: number | null;
  wilson_ci95?: Array<number | null>;
  wilson_lower_threshold?: number;
  pass_rate_target?: number;
  sample_n?: number;
  l5_default_min_sample_n?: number;
  gaps?: string[];
  distance_summary?: string;
  accuracy_claim?: boolean;
  explicit_authorize?: boolean;
  claims_gate?: { accuracy_claim?: boolean; ok?: boolean };
  claim_unlock?: G2bClaimUnlock;
  note?: string;
};

type Props = { tenantId?: string };

export default function EvalG2bPanel({ tenantId = 'eval-v1' }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<G2bStatus | null>(null);
  const [l5Gap, setL5Gap] = useState<G2bL5Gap | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get<Envelope<G2bStatus>>(
        `/platform/apps/eval/store/g2b-status?tenant_id=${encodeURIComponent(tenantId)}`,
      );
      setStatus(unwrap(res));
      try {
        const gapRes = await apiClient.get<Envelope<G2bL5Gap>>(
          `/platform/apps/eval/store/g2b-l5-gap?tenant_id=${encodeURIComponent(tenantId)}`,
        );
        setL5Gap(unwrap(gapRes));
      } catch {
        setL5Gap(null);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  const families = status?.families || {};

  return (
    <div className="space-y-4 text-sm" data-testid="eval-g2b-panel">
      <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90 space-y-1">
        <div className="font-medium">G2b 诚实约束</div>
        <ul className="list-disc pl-5 space-y-0.5">
          <li>
            pack n=100 · dual-human closeout{' '}
            {status?.dual_human_complete ? '已完成' : '未完成'}（scoped observed only）
          </li>
          <li>
            §4 数值可达时仍默认 claim 关（需 owner accept）· L5 gap 以聚合为准 · 勿把 κ 当准确率
          </li>
          <li>κ / agreement ≠ accuracy · 不可由 agent 伪造标注</li>
          <li>
            <code>accuracy_claim</code>={String(Boolean(status?.accuracy_claim))} · ≠ process_split / staging
          </li>
        </ul>
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">G2b pack / closeout</h2>
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
          <dl className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
            <div>
              <dt className="text-gray-500">pack tasks</dt>
              <dd>
                {status.task_count ?? '—'}/{status.target_n ?? '—'}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">pack_ready</dt>
              <dd>{String(status.pack_ready)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">closeout_n</dt>
              <dd>{status.closeout_n ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">pending_dual_human</dt>
              <dd className="text-yellow-200">{status.pending_dual_human ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">dual_human_complete</dt>
              <dd>{String(status.dual_human_complete)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">κ (inter)</dt>
              <dd>
                {status.kappa ?? '—'}
                <span className="text-gray-500 ml-1">({status.kappa_kind || '—'})</span>
              </dd>
            </div>
            <div className="col-span-2 sm:col-span-3">
              <dt className="text-gray-500">note</dt>
              <dd className="text-gray-300">{status.note || '—'}</dd>
            </div>
            <div className="col-span-2 sm:col-span-3">
              <dt className="text-gray-500">runbook</dt>
              <dd className="font-mono text-blue-200/90 break-all">{status.runbook || '—'}</dd>
            </div>
          </dl>
        ) : null}

        {Object.keys(families).length > 0 ? (
          <div className="text-xs text-gray-400">
            families:{' '}
            {Object.entries(families)
              .map(([k, v]) => `${k}=${v}`)
              .join(' · ')}
          </div>
        ) : null}
      </div>

      {l5Gap ? (
        <div
          className="rounded-lg border border-slate-700 bg-slate-950/40 p-4 space-y-2 text-xs"
          data-testid="eval-g2b-l5-gap"
        >
          <h3 className="font-medium text-slate-100 text-sm">L5 / G2b 差距披露</h3>
          <dl className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div>
              <dt className="text-gray-500">pass_rate</dt>
              <dd>{l5Gap.pass_rate ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">Wilson lo / thr</dt>
              <dd>
                {l5Gap.wilson_ci95?.[0] ?? '—'} / {l5Gap.wilson_lower_threshold ?? 0.7}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">sample_n / L5</dt>
              <dd>
                {l5Gap.sample_n ?? '—'}/{l5Gap.l5_default_min_sample_n ?? 100}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">distance</dt>
              <dd data-testid="eval-g2b-l5-distance">{l5Gap.distance_summary ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">accuracy_claim</dt>
              <dd>{String(Boolean(l5Gap.accuracy_claim))}</dd>
            </div>
            <div>
              <dt className="text-gray-500">authorize</dt>
              <dd>{String(Boolean(l5Gap.explicit_authorize))}</dd>
            </div>
          </dl>
          {l5Gap.gaps?.length ? (
            <p className="text-amber-200/80">gaps: {l5Gap.gaps.join('; ')}</p>
          ) : null}
          {l5Gap.claim_unlock ? (
            <div
              className="rounded border border-slate-600/60 bg-slate-900/50 p-3 space-y-1"
              data-testid="eval-g2b-claim-unlock"
            >
              <div className="font-medium text-slate-200">Claim 解锁核对（仍关）</div>
              <p className="text-gray-400">
                G2b scoped ready={String(Boolean(l5Gap.claim_unlock.g2b_scoped_ready))} ·
                blockers={(l5Gap.claim_unlock.g2b_scoped_blockers || []).join(', ') || '—'}
              </p>
              <p className="text-gray-500">
                broader: {(l5Gap.claim_unlock.broader_trust_blockers || []).join(', ') || '—'}
              </p>
              <p className="text-gray-500">
                {l5Gap.claim_unlock.honesty ||
                  '需 owner accept_accuracy_claim=true；Arena QA / staging / 审计另轨'}
              </p>
            </div>
          ) : null}
          <p className="text-gray-500">{l5Gap.note}</p>
        </div>
      ) : null}

      <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2 text-xs text-gray-400">
        <h3 className="font-medium text-gray-200 text-sm">Facilitator checklist</h3>
        <ol className="list-decimal pl-5 space-y-1">
          <li>
            Pack / evidence: <code>docs/a3/G2B_N100.md</code>（n=100 closeout 已归档）
          </li>
          <li>若重开标注：Fill model outputs → annotator A/B sheets（blind; no gold）</li>
          <li>Humans label independently · 不可由 agent 伪造</li>
          <li>
            After return: <code>g2b_kappa.py</code> + <code>g2b_accuracy_closeout.py</code>（仍
            accuracy_claim=false）
          </li>
        </ol>
      </div>
    </div>
  );
}
