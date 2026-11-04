/**
 * Evidence audit panel — hash/attestation facts; never claims accuracy.
 */
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type HashRow = {
  id?: string;
  path?: string;
  present?: boolean;
  match?: boolean;
  status?: string;
  required_for_feature_5?: boolean;
  gitignored?: boolean;
};

type EvidenceStatus = {
  ok?: boolean;
  accuracy_claim?: boolean;
  process_split_authorized?: boolean;
  dual_human_attestation?: string;
  attestation_ok?: boolean;
  tracked_aggregates?: HashRow[];
  tracked_ok_n?: number;
  tracked_n?: number;
  required_for_feature_5_ok?: boolean;
  all_tracked_ok?: boolean;
  local_worksheets?: HashRow[];
  worksheets_present_n?: number;
  worksheets_n?: number;
  feature5_audit_ready?: boolean;
  note?: string;
  runbook?: string;
};

type Props = { tenantId?: string };

function statusClass(s?: string): string {
  if (s === 'ok') return 'text-green-300';
  if (s === 'absent_ok') return 'text-gray-400';
  if (s === 'missing' || s === 'mismatch') return 'text-yellow-200';
  return 'text-gray-300';
}

export default function EvalEvidencePanel({ tenantId = 'eval-v1' }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<EvidenceStatus | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get<Envelope<EvidenceStatus>>(
        `/platform/apps/eval/store/evidence-audit-status?tenant_id=${encodeURIComponent(tenantId)}`,
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

  const tracked = status?.tracked_aggregates || [];
  const worksheets = status?.local_worksheets || [];

  return (
    <div className="space-y-4 text-sm" data-testid="eval-evidence-panel">
      <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90 space-y-1">
        <div className="font-medium">Evidence 诚实约束</div>
        <ul className="list-disc pl-5 space-y-0.5">
          <li>feature5_audit_ready ≠ accuracy_claim</li>
          <li>κ / agreement ≠ accuracy · raw worksheets stay gitignored</li>
          <li>
            <code>accuracy_claim</code>={String(Boolean(status?.accuracy_claim))} ·{' '}
            <code>process_split_authorized</code>=
            {String(Boolean(status?.process_split_authorized))}
          </li>
        </ul>
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">Evidence manifest audit</h2>
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
              <dt className="text-gray-500">dual_human_attestation</dt>
              <dd>{status.dual_human_attestation || '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">attestation_ok</dt>
              <dd>{String(status.attestation_ok)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">feature5_audit_ready</dt>
              <dd>{String(status.feature5_audit_ready)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">tracked hashes</dt>
              <dd>
                {status.tracked_ok_n ?? '—'}/{status.tracked_n ?? '—'}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">required_for_feature_5_ok</dt>
              <dd>{String(status.required_for_feature_5_ok)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">worksheets present</dt>
              <dd>
                {status.worksheets_present_n ?? '—'}/{status.worksheets_n ?? '—'}
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

      {tracked.length > 0 ? (
        <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2">
          <h3 className="font-medium text-sm">Tracked aggregates</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="text-gray-500 border-b border-gray-700">
                  <th className="py-1.5 pr-2 font-medium">id</th>
                  <th className="py-1.5 pr-2 font-medium">status</th>
                  <th className="py-1.5 font-medium">feat5</th>
                </tr>
              </thead>
              <tbody>
                {tracked.map((r) => (
                  <tr key={r.id} className="border-b border-gray-800/80">
                    <td className="py-1.5 pr-2 font-mono text-gray-200">{r.id}</td>
                    <td className={`py-1.5 pr-2 ${statusClass(r.status)}`}>{r.status}</td>
                    <td className="py-1.5">{r.required_for_feature_5 ? 'yes' : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {worksheets.length > 0 ? (
        <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2">
          <h3 className="font-medium text-sm">Local worksheets (gitignored)</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="text-gray-500 border-b border-gray-700">
                  <th className="py-1.5 pr-2 font-medium">id</th>
                  <th className="py-1.5 font-medium">status</th>
                </tr>
              </thead>
              <tbody>
                {worksheets.map((r) => (
                  <tr key={r.id} className="border-b border-gray-800/80">
                    <td className="py-1.5 pr-2 font-mono text-gray-200">{r.id}</td>
                    <td className={`py-1.5 ${statusClass(r.status)}`}>{r.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
