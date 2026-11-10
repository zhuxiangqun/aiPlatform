/**
 * Method-track honesty panel — Arena/G2b/S1 stay Methods, never Subjects.
 */
import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type MethodRow = {
  method_kind?: string;
  track?: string;
  object_type_eligible?: boolean;
  subject_adapter_eligible?: boolean;
  claim_eligible?: boolean;
  default_evidence_level?: string;
  honesty?: string;
  source_refs?: string[];
};

type MethodTrackStatus = {
  ok?: boolean;
  method_kinds?: string[];
  methods?: MethodRow[];
  subject_kinds?: string[];
  subject_exclude_methods?: { ok?: boolean; errors?: string[] };
  accuracy_claim?: boolean;
  claim_eligible?: boolean;
  note?: string;
};

type Props = { tenantId?: string };

export default function EvalMethodTrackPanel(_props: Props = {}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState<MethodTrackStatus | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get<Envelope<MethodTrackStatus>>(
        `/platform/apps/eval/store/method-track-status`,
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

  const methods = status?.methods || [];
  const subjects = status?.subject_kinds || [];
  const excludeOk = Boolean(status?.subject_exclude_methods?.ok ?? status?.ok);

  return (
    <div className="space-y-4 text-sm" data-testid="eval-method-track-panel">
      <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90 space-y-1">
        <div className="font-medium">Method 轨诚实约束（ADR）</div>
        <ul className="list-disc pl-5 space-y-0.5">
          <li>Arena / G2b / S1 是 Method，禁止升 SubjectAdapter / OBJECT_TYPES</li>
          <li>
            <code>accuracy_claim</code>={String(Boolean(status?.accuracy_claim))} · claim_eligible=
            {String(Boolean(status?.claim_eligible))}
          </li>
          <li>Subject 交叉校验：{excludeOk ? '通过（无 Method 混入）' : '失败（见 errors）'}</li>
        </ul>
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">Method catalog</h2>
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
            <p className="text-xs text-gray-400">{status.note || ''}</p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-700">
                    <th className="py-1 pr-2">kind</th>
                    <th className="py-1 pr-2">evidence</th>
                    <th className="py-1 pr-2">subject?</th>
                    <th className="py-1">honesty</th>
                  </tr>
                </thead>
                <tbody>
                  {methods.map((m) => (
                    <tr key={m.method_kind} className="border-b border-gray-800 align-top">
                      <td className="py-2 pr-2 font-mono">{m.method_kind}</td>
                      <td className="py-2 pr-2">{m.default_evidence_level || '—'}</td>
                      <td className="py-2 pr-2">
                        {String(Boolean(m.subject_adapter_eligible))}
                      </td>
                      <td className="py-2 text-gray-300">{m.honesty || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : null}
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-2">
        <h2 className="font-medium">Registered Subjects（对照）</h2>
        <p className="text-xs text-gray-400">
          这些是 SubjectAdapter 种类；与 Method 轨互斥。
        </p>
        {subjects.length ? (
          <ul className="flex flex-wrap gap-2 text-xs">
            {subjects.map((k) => (
              <li
                key={k}
                className="px-2 py-0.5 rounded border border-gray-600 font-mono text-gray-200"
              >
                {k}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-gray-500 text-xs">—</p>
        )}
        {!excludeOk && status?.subject_exclude_methods?.errors?.length ? (
          <ul className="list-disc pl-5 text-xs text-red-300">
            {status.subject_exclude_methods.errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
