/**
 * Scorecard honesty panel — axes/attestation facts; never claims accuracy or authorize.
 */
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type AxisRow = {
  id?: string;
  score?: number | null;
  max?: number | null;
  full_score_eligible?: boolean;
  gaps_n?: number;
  gaps?: string[];
};

type ScorecardStatus = {
  ok?: boolean;
  recorded_at?: string;
  accuracy_claim?: boolean;
  process_split_authorized?: boolean;
  dual_human_attestation?: string;
  axes?: AxisRow[];
  dimensions_n?: number;
  dimensions_evidence_ok?: number;
  g2b_closeout_n?: number | null;
  g2b_target_n?: number | null;
  g2b_pass_rate?: number | null;
  honesty?: string;
  note?: string;
  runbook?: string;
};

type Props = { tenantId?: string };

export default function EvalScorecardPanel({ tenantId = 'eval-v1' }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<ScorecardStatus | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get<Envelope<ScorecardStatus>>(
        `/platform/apps/eval/store/scorecard-status?tenant_id=${encodeURIComponent(tenantId)}`,
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

  const axes = status?.axes || [];

  return (
    <div className="space-y-4 text-sm" data-testid="eval-scorecard-panel">
      <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90 space-y-1">
        <div className="font-medium">Scorecard 诚实约束</div>
        <ul className="list-disc pl-5 space-y-0.5">
          <li>功能 5 ≠ accuracy · κ/agreement ≠ accuracy_claim</li>
          <li>本地 5 ≠ process_split_authorized / staging</li>
          <li>
            <code>accuracy_claim</code>={String(Boolean(status?.accuracy_claim))} ·{' '}
            <code>process_split_authorized</code>=
            {String(Boolean(status?.process_split_authorized))}
          </li>
        </ul>
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">Scorecard v1 / attestation</h2>
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
              <dt className="text-gray-500">recorded_at</dt>
              <dd>{status.recorded_at || '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">dual_human_attestation</dt>
              <dd>{status.dual_human_attestation || '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">dimensions evidence_ok</dt>
              <dd>
                {status.dimensions_evidence_ok ?? '—'}/{status.dimensions_n ?? '—'}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">G2b closeout / target</dt>
              <dd>
                {status.g2b_closeout_n ?? '—'}/{status.g2b_target_n ?? '—'}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">G2b pass_rate (scoped n)</dt>
              <dd>{status.g2b_pass_rate ?? '—'}</dd>
            </div>
            <div className="col-span-2 sm:col-span-3">
              <dt className="text-gray-500">honesty</dt>
              <dd className="text-gray-300">{status.honesty || '—'}</dd>
            </div>
            <div className="col-span-2 sm:col-span-3">
              <dt className="text-gray-500">runbook</dt>
              <dd className="font-mono text-blue-200/90 break-all">{status.runbook || '—'}</dd>
            </div>
          </dl>
        ) : null}

        {axes.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="text-gray-500 border-b border-gray-700">
                  <th className="py-1.5 pr-2 font-medium">axis</th>
                  <th className="py-1.5 pr-2 font-medium">score</th>
                  <th className="py-1.5 pr-2 font-medium">eligible</th>
                  <th className="py-1.5 font-medium">gaps</th>
                </tr>
              </thead>
              <tbody>
                {axes.map((a) => (
                  <tr key={a.id} className="border-b border-gray-800/80">
                    <td className="py-1.5 pr-2 font-mono text-gray-200">{a.id}</td>
                    <td className="py-1.5 pr-2">
                      {a.score == null ? 'null' : a.score}/{a.max ?? '—'}
                    </td>
                    <td className="py-1.5 pr-2">{String(Boolean(a.full_score_eligible))}</td>
                    <td className="py-1.5 text-yellow-200/90">
                      {a.gaps_n ? (a.gaps || []).join(', ') : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </div>
  );
}
