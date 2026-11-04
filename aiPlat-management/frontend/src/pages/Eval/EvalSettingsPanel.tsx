/**
 * UI-5 — Settings + G2c self-consistency (intra-rater; never accuracy / G2b).
 */
import { useCallback, useEffect, useState } from 'react';
import { Check, Loader2, RefreshCw, X } from 'lucide-react';
import { apiClient } from '../../services';

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

type G2cStatus = {
  ok?: boolean;
  set_id?: string;
  claim_kind?: string;
  accuracy_claim?: boolean;
  kappa_kind?: string;
  v0_locked?: boolean;
  primary_adjudicated?: number;
  retest_count?: number;
  paired_count?: number;
  g2c_ready?: boolean;
  note?: string;
};

type RetestItem = {
  task_id?: string;
  primary_label_id?: string;
  primary_pass?: boolean | null;
};

type Props = { tenantId?: string };

export default function EvalSettingsPanel({ tenantId = 'eval-v1' }: Props) {
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState('');
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [status, setStatus] = useState<G2cStatus | null>(null);
  const [pending, setPending] = useState<RetestItem[]>([]);
  const [report, setReport] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [stRes, qRes] = await Promise.all([
        apiClient.get<Envelope<G2cStatus>>(
          `/platform/apps/eval/store/g2c-status?tenant_id=${encodeURIComponent(tenantId)}`,
        ),
        apiClient.get<Envelope<{ pending?: RetestItem[]; total?: number }>>(
          `/platform/apps/eval/store/g2c-retest-queue?tenant_id=${encodeURIComponent(tenantId)}&limit=50`,
        ),
      ]);
      setStatus(unwrap(stRes));
      const q = unwrap(qRes) as { pending?: RetestItem[] };
      setPending(Array.isArray(q?.pending) ? q.pending : []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
  }, [load]);

  const retest = async (taskId: string, passed: boolean) => {
    if (!taskId) return;
    setBusyId(taskId);
    setMsg('');
    try {
      const res = await apiClient.post<Envelope<{ ok?: boolean; error?: string }>>(
        `/platform/apps/eval/store/g2c-retest`,
        {
          tenant_id: tenantId,
          task_id: taskId,
          pass: passed,
          notes: passed ? 'ui5-retest-pass' : 'ui5-retest-fail',
          accuracy_claim: false,
        },
      );
      const d = unwrap(res) as { ok?: boolean; error?: string };
      if (d && d.ok === false) {
        setMsg(`retest 失败: ${d.error || 'unknown'}`);
      } else {
        setMsg(`g2c-retest ${taskId} → pass=${passed}（intra-rater ≠ accuracy / G2b）`);
        await load();
      }
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId('');
    }
  };

  const computeReport = async () => {
    setActionBusy(true);
    setMsg('');
    try {
      const res = await apiClient.post<Envelope<Record<string, unknown>>>(
        `/platform/apps/eval/store/g2c-report`,
        { tenant_id: tenantId, persist: true, accuracy_claim: false },
      );
      const d = unwrap(res) as Record<string, unknown> & { ok?: boolean; error?: string };
      if (d && d.ok === false) {
        setMsg(`g2c-report 失败: ${String(d.error || 'unknown')}`);
        setReport(null);
      } else {
        setReport(d);
        setMsg(
          `g2c-report ok · claim_kind=${String(d.claim_kind || 'self_consistency')} · accuracy_claim=${String(Boolean(d.accuracy_claim))}`,
        );
      }
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setActionBusy(false);
    }
  };

  return (
    <div className="space-y-4 text-sm" data-testid="eval-settings-panel">
      <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 px-4 py-3 text-xs text-amber-100/90 space-y-1">
        <div className="font-medium">诚实约束</div>
        <ul className="list-disc pl-5 space-y-0.5">
          <li>
            G2c = 同人二次盲测（<code>intra_rater</code>）· ≠ accuracy · ≠ 第二标注者 / G2b
          </li>
          <li>tenant 默认 <code>{tenantId}</code> · UI 不暴露 accuracy 开关</li>
          <li>G2b / 外部 gate：仍 defer</li>
        </ul>
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/50 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="font-medium">G2c 自洽状态</h2>
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
        {status ? (
          <dl className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
            <div>
              <dt className="text-gray-500">v0_locked</dt>
              <dd>{String(status.v0_locked)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">paired</dt>
              <dd>
                {status.paired_count ?? '—'}/{status.primary_adjudicated ?? '—'}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">retest_count</dt>
              <dd>{status.retest_count ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">g2c_ready</dt>
              <dd>{String(status.g2c_ready)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">accuracy_claim</dt>
              <dd className="text-amber-200">{String(Boolean(status.accuracy_claim))}</dd>
            </div>
            <div>
              <dt className="text-gray-500">kappa_kind</dt>
              <dd>{status.kappa_kind || '—'}</dd>
            </div>
            <div className="col-span-2 sm:col-span-3">
              <dt className="text-gray-500">note</dt>
              <dd className="text-gray-300">{status.note || '—'}</dd>
            </div>
          </dl>
        ) : loading ? (
          <p className="text-gray-500">加载中…</p>
        ) : null}

        <button
          type="button"
          data-testid="eval-g2c-report"
          disabled={actionBusy}
          onClick={() => void computeReport()}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded bg-blue-700/80 hover:bg-blue-600 disabled:opacity-50 text-white"
        >
          {actionBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
          Compute G2c report
        </button>
        {msg ? (
          <p className="text-gray-300 font-mono text-xs whitespace-pre-wrap" data-testid="eval-settings-msg">
            {msg}
          </p>
        ) : null}
        {report ? (
          <pre
            className="text-xs bg-gray-950/80 border border-gray-800 rounded p-3 overflow-auto max-h-56 text-gray-300"
            data-testid="eval-g2c-report-detail"
          >
            {JSON.stringify(report, null, 2)}
          </pre>
        ) : null}
      </div>

      <div className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-2">
        <h3 className="font-medium">G2c retest queue</h3>
        <p className="text-xs text-gray-500">
          对已 adjudicated 任务做同人复测（blind）· 不写入第二标注者
        </p>
        {loading && pending.length === 0 ? (
          <p className="text-gray-500">加载中…</p>
        ) : pending.length === 0 ? (
          <p className="text-gray-500">无待复测任务（或尚无 primary adjudicated）。</p>
        ) : (
          <ul className="divide-y divide-gray-800 max-h-80 overflow-auto" data-testid="eval-g2c-pending">
            {pending.map((row, i) => {
              const tid = String(row.task_id || '');
              const busy = busyId === tid;
              return (
                <li key={tid || i} className="py-2 flex flex-wrap gap-2 items-center justify-between">
                  <div className="min-w-0 text-xs">
                    <div className="font-mono text-blue-200 truncate">{tid || `task-${i}`}</div>
                    <div className="text-gray-500">
                      primary_pass={row.primary_pass === undefined || row.primary_pass === null ? '—' : String(row.primary_pass)}
                    </div>
                  </div>
                  <div className="flex gap-1.5 shrink-0">
                    <button
                      type="button"
                      disabled={busy || !tid}
                      data-testid="eval-g2c-pass"
                      onClick={() => void retest(tid, true)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded bg-green-800/70 hover:bg-green-700 disabled:opacity-40 text-white text-xs"
                    >
                      {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                      Pass
                    </button>
                    <button
                      type="button"
                      disabled={busy || !tid}
                      data-testid="eval-g2c-fail"
                      onClick={() => void retest(tid, false)}
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
