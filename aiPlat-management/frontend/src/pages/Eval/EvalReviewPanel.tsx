/**
 * UI-3 — Review queue: pending labels + adjudicate + optional preannotate / lock-v0.
 * Honesty: adjudicate ≠ accuracy; lock-v0 is local gold lock only.
 */
import { useCallback, useEffect, useState } from 'react';
import { Check, Loader2, RefreshCw, X } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type LabelRow = {
  id?: string;
  task_id?: string;
  annotator?: string;
  label?: { pass?: boolean; status?: string; notes?: string };
  rationale?: string;
  adjudicated?: boolean;
  created_at?: string;
};

type QueueBody = {
  ok?: boolean;
  set_id?: string;
  annotator?: string;
  pending?: LabelRow[];
  total?: number;
};

type G2aStatus = {
  labels_adjudicated?: number;
  labels_pending?: number;
  v0_lock_ready?: boolean;
  v0_locked?: boolean;
  v0_lock_target?: number;
  accuracy_claim?: boolean;
};

type Props = { tenantId?: string };

export default function EvalReviewPanel({ tenantId = 'eval-v1' }: Props) {
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState('');
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [queue, setQueue] = useState<QueueBody | null>(null);
  const [status, setStatus] = useState<G2aStatus | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [qRes, stRes] = await Promise.all([
        apiClient.get<Envelope<QueueBody>>(
          `/platform/apps/eval/store/review-queue?tenant_id=${encodeURIComponent(tenantId)}&limit=50`,
        ),
        apiClient.get<Envelope<G2aStatus>>(
          `/platform/apps/eval/store/g2a-status?tenant_id=${encodeURIComponent(tenantId)}`,
        ),
      ]);
      setQueue(unwrap(qRes));
      setStatus(unwrap(stRes));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  const pending = Array.isArray(queue?.pending) ? queue!.pending! : [];

  const adjudicate = async (labelId: string, passed: boolean) => {
    if (!labelId) return;
    setBusyId(labelId);
    setMsg('');
    try {
      const res = await apiClient.post<Envelope<{ ok?: boolean; error?: string; id?: string }>>(
        `/platform/apps/eval/store/labels/${encodeURIComponent(labelId)}/adjudicate`,
        { pass: passed, tenant_id: tenantId, notes: passed ? 'ui3-pass' : 'ui3-fail' },
      );
      const d = unwrap(res) as { ok?: boolean; error?: string };
      if (d && d.ok === false) {
        setMsg(`adjudicate 失败: ${d.error || 'unknown'}`);
      } else {
        setMsg(`adjudicated ${labelId} → pass=${passed}（≠ accuracy）`);
        await load();
      }
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId('');
    }
  };

  const preannotate = async () => {
    setActionBusy(true);
    setMsg('');
    try {
      const res = await apiClient.post<Envelope<{ ok?: boolean; error?: string; updated?: number }>>(
        `/platform/apps/eval/store/review-queue/preannotate`,
        { tenant_id: tenantId },
      );
      const d = unwrap(res) as { ok?: boolean; error?: string; updated?: number };
      if (d && d.ok === false) {
        setMsg(`preannotate 失败: ${d.error || 'unknown'}`);
      } else {
        setMsg(`preannotate ok · updated≈${d.updated ?? '—'}（仍须人工 adjudicate）`);
        await load();
      }
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setActionBusy(false);
    }
  };

  const lockV0 = async () => {
    if (!window.confirm('确认 lock-v0？仅本地黄金集锁定，accuracy_claim 仍为 false。')) return;
    setActionBusy(true);
    setMsg('');
    try {
      const res = await apiClient.post<Envelope<{ ok?: boolean; error?: string; v0_locked?: boolean }>>(
        `/platform/apps/eval/store/lock-v0`,
        { tenant_id: tenantId },
      );
      const d = unwrap(res) as { ok?: boolean; error?: string; v0_locked?: boolean };
      if (d && d.ok === false) {
        setMsg(`lock-v0 失败: ${d.error || 'unknown'}`);
      } else {
        setMsg(`lock-v0 · locked=${String(d.v0_locked ?? d.ok)} · accuracy_claim=false`);
        await load();
      }
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setActionBusy(false);
    }
  };

  return (
    <div className="space-y-4 text-sm" data-testid="eval-review-panel">
      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">人工复核队列（D5）</h2>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1.5 px-2 py-1 rounded border border-gray-600 text-xs text-gray-300 hover:bg-gray-800"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
        <p className="text-xs text-amber-200/90">
          adjudicate = 单人标定 · κ=null · <code>accuracy_claim</code>=
          {String(Boolean(status?.accuracy_claim))} · lock-v0 ≠ 外部 gate
        </p>
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          <div>
            <dt className="text-gray-500">pending</dt>
            <dd>{queue?.total ?? pending.length}</dd>
          </div>
          <div>
            <dt className="text-gray-500">adjudicated</dt>
            <dd>
              {status?.labels_adjudicated ?? '—'}/{status?.v0_lock_target ?? 30}
            </dd>
          </div>
          <div>
            <dt className="text-gray-500">v0_lock_ready</dt>
            <dd>{String(status?.v0_lock_ready)}</dd>
          </div>
          <div>
            <dt className="text-gray-500">v0_locked</dt>
            <dd>{String(status?.v0_locked)}</dd>
          </div>
        </dl>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            data-testid="eval-review-preannotate"
            disabled={actionBusy}
            onClick={() => void preannotate()}
            className="px-3 py-1.5 rounded border border-gray-600 text-gray-200 hover:bg-gray-800 disabled:opacity-50"
          >
            {actionBusy ? <Loader2 className="w-4 h-4 animate-spin inline" /> : null} Preannotate
          </button>
          <button
            type="button"
            data-testid="eval-review-lock-v0"
            disabled={actionBusy || !status?.v0_lock_ready || Boolean(status?.v0_locked)}
            onClick={() => void lockV0()}
            className="px-3 py-1.5 rounded border border-amber-700/70 text-amber-100 hover:bg-amber-950/40 disabled:opacity-40"
          >
            Lock v0
          </button>
        </div>
        {error ? <p className="text-red-300 text-xs">{error}</p> : null}
        {msg ? (
          <p className="text-gray-300 font-mono text-xs whitespace-pre-wrap" data-testid="eval-review-msg">
            {msg}
          </p>
        ) : null}
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2">
        <h3 className="font-medium">Pending labels</h3>
        {loading && pending.length === 0 ? (
          <p className="text-gray-500">加载中…</p>
        ) : pending.length === 0 ? (
          <p className="text-gray-500">队列为空（或已全部 adjudicated）。</p>
        ) : (
          <ul className="divide-y divide-gray-800 max-h-96 overflow-auto" data-testid="eval-review-pending">
            {pending.map((row, i) => {
              const id = String(row.id || '');
              const busy = busyId === id;
              const suggest = row.label?.pass;
              return (
                <li key={id || i} className="py-2 flex flex-wrap gap-2 items-start justify-between">
                  <div className="min-w-0 space-y-0.5">
                    <div className="font-mono text-xs text-blue-200 truncate">{id || `label-${i}`}</div>
                    <div className="text-xs text-gray-500 truncate">
                      task={row.task_id || '—'} · suggest=
                      {suggest === undefined ? '—' : String(suggest)}
                    </div>
                  </div>
                  <div className="flex gap-1.5 shrink-0">
                    <button
                      type="button"
                      disabled={busy || !id}
                      data-testid="eval-adjudicate-pass"
                      onClick={() => void adjudicate(id, true)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded bg-green-800/70 hover:bg-green-700 disabled:opacity-40 text-white text-xs"
                    >
                      {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                      Pass
                    </button>
                    <button
                      type="button"
                      disabled={busy || !id}
                      data-testid="eval-adjudicate-fail"
                      onClick={() => void adjudicate(id, false)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded bg-red-900/60 hover:bg-red-800 disabled:opacity-40 text-white text-xs"
                    >
                      {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <X className="w-3.5 h-3.5" />}
                      Fail
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
