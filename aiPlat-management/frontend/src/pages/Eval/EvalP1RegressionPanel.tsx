/**
 * P1 Regression readiness — quotas may be complete; human purpose_ok/freeze is the gate.
 */
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type CheckRow = {
  id?: string;
  ok?: boolean;
  detail?: string;
  required_for_profile_complete?: boolean;
};

type P1Status = {
  ok?: boolean;
  profile_id?: string;
  quota_inventory_ok?: boolean;
  profile_complete?: boolean;
  case_count?: number;
  purpose_ok_or_better?: number;
  review_status_counts?: Record<string, number>;
  checks?: CheckRow[];
  blockers?: string[];
  coverage?: { n_gaps?: number; covered_capabilities?: number; total_in_scope?: number };
  snapshot?: { manifest_hash?: string; case_count?: number };
  next_action?: string;
  accuracy_claim?: boolean;
  claim_eligible?: boolean;
  certification_eligible?: boolean;
  honesty?: string;
};

type Props = { tenantId?: string };

export default function EvalP1RegressionPanel(_props: Props = {}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<P1Status | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get<Envelope<P1Status>>(
        `/platform/apps/eval/store/p1-regression-status`,
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

  const reviews = status?.review_status_counts || {};
  const checks = status?.checks || [];
  const blockers = status?.blockers || [];

  return (
    <div className="space-y-4 text-sm" data-testid="eval-p1-regression-panel">
      <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90 space-y-1">
        <div className="font-medium">P1 Regression 诚实门（ADR）</div>
        <ul className="list-disc pl-5 space-y-0.5">
          <li>
            配额盘点：{status?.quota_inventory_ok ? '齐' : '缺口'} · profile_complete=
            {String(Boolean(status?.profile_complete))}
          </li>
          <li>
            claim_eligible={String(Boolean(status?.claim_eligible))} · accuracy_claim=
            {String(Boolean(status?.accuracy_claim))} · certification=
            {String(Boolean(status?.certification_eligible))}
          </li>
          <li>{status?.honesty || '人审 purpose_ok / freeze 前不得宣称 profile 收口。'}</li>
        </ul>
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">
            {status?.profile_id || 'agent.regression.v1'} · 就绪快照
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
              cases={status.case_count ?? '—'} · purpose_ok+=
              {status.purpose_ok_or_better ?? 0} · gaps=
              {status.coverage?.n_gaps ?? '—'} · manifest=
              {status.snapshot?.manifest_hash
                ? `${String(status.snapshot.manifest_hash).slice(0, 16)}…`
                : '—'}
            </p>
            <p className="text-xs text-sky-200/90">下一步：{status.next_action}</p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-700">
                    <th className="py-1 pr-2">review.status</th>
                    <th className="py-1">count</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.keys(reviews).length ? (
                    Object.entries(reviews).map(([k, v]) => (
                      <tr key={k} className="border-b border-gray-800">
                        <td className="py-2 pr-2 font-mono">{k}</td>
                        <td className="py-2">{v}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="py-2 text-gray-500" colSpan={2}>
                        —
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-2">
        <h2 className="font-medium">Checklist / blockers</h2>
        {blockers.length ? (
          <ul className="list-disc pl-5 text-xs text-amber-200">
            {blockers.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-gray-400">无 blockers（仍不开放 claim）。</p>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-700">
                <th className="py-1 pr-2">check</th>
                <th className="py-1 pr-2">ok</th>
                <th className="py-1">detail</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((c) => (
                <tr key={c.id || c.detail} className="border-b border-gray-800 align-top">
                  <td className="py-2 pr-2 font-mono">{c.id || '—'}</td>
                  <td className="py-2 pr-2">{String(Boolean(c.ok))}</td>
                  <td className="py-2 text-gray-300">{c.detail || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
