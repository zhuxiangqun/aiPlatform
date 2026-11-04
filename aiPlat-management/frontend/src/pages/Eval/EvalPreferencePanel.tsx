/**
 * Preference facilitation panel — pairs/aggregate facts; never claims accuracy.
 */
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type PreferenceStatus = {
  ok?: boolean;
  pairs_n?: number;
  pack_ready?: boolean;
  labeled_a?: number;
  labeled_b?: number;
  pending_a?: number;
  pending_b?: number;
  dual_human_complete?: boolean;
  fixture_solo?: boolean;
  agreement?: number | null;
  preference_kappa?: number | null;
  kappa_kind?: string;
  accuracy_claim?: boolean;
  note?: string;
  runbook?: string;
};

type Props = { tenantId?: string };

export default function EvalPreferencePanel({ tenantId = 'eval-v1' }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<PreferenceStatus | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get<Envelope<PreferenceStatus>>(
        `/platform/apps/eval/store/preference-status?tenant_id=${encodeURIComponent(tenantId)}`,
      );
      setStatus(unwrap(res));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4 text-sm" data-testid="eval-preference-panel">
      <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90 space-y-1">
        <div className="font-medium">Preference 诚实约束</div>
        <ul className="list-disc pl-5 space-y-0.5">
          <li>agreement / preference_κ ≠ accuracy certification</li>
          <li>fixture solo ≠ human dual-label κ</li>
          <li>
            <code>accuracy_claim</code>={String(Boolean(status?.accuracy_claim))} · ≠ G2b
            closeout / staging
          </li>
        </ul>
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">Preference pairs / report</h2>
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
              <dt className="text-gray-500">pairs_n</dt>
              <dd>{status.pairs_n ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">pack_ready</dt>
              <dd>{String(status.pack_ready)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">labeled A / B</dt>
              <dd>
                {status.labeled_a ?? '—'} / {status.labeled_b ?? '—'}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">pending A / B</dt>
              <dd className="text-yellow-200">
                {status.pending_a ?? '—'} / {status.pending_b ?? '—'}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">dual_human_complete</dt>
              <dd>{String(status.dual_human_complete)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">fixture_solo</dt>
              <dd>{String(status.fixture_solo)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">agreement</dt>
              <dd>{status.agreement ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">preference_κ</dt>
              <dd>
                {status.preference_kappa ?? '—'}
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
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2 text-xs text-gray-400">
        <h3 className="font-medium text-gray-200 text-sm">Facilitator checklist</h3>
        <ol className="list-decimal pl-5 space-y-1">
          <li>
            Pack:{' '}
            <code>bash packages/aiplat-evaluation/scripts/human_worksheet_pack.sh</code>
          </li>
          <li>Humans fill pref_annotator_a/b.json (preferred: a|b|tie; blind)</li>
          <li>
            Gate:{' '}
            <code>
              AIPLAT_EVAL_PREF_A=… AIPLAT_EVAL_PREF_B=… bash
              packages/aiplat-evaluation/scripts/preference_v0_gate.sh
            </code>
          </li>
          <li>Still accuracy_claim=false · ≠ G2b accuracy closeout</li>
        </ol>
      </div>
    </div>
  );
}
