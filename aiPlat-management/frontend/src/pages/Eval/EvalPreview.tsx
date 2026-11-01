/**
 * EVAL_V1 /eval local preview (G2a after lock).
 * Honesty: engineering calibration only — never claim accuracy / κ / external gate.
 */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, RefreshCw, ShieldCheck } from 'lucide-react';
import { apiClient } from '../../services';

type G2aStatus = {
  ok?: boolean;
  schema_version?: string;
  tenant_id?: string;
  set_id?: string;
  task_count?: number;
  labels_pending?: number;
  labels_adjudicated?: number;
  v0_lock_target?: number;
  v0_lock_ready?: boolean;
  v0_locked?: boolean;
  g2a_ready?: boolean;
  accuracy_claim?: boolean;
  kappa?: number | null;
  note?: string;
};

type Envelope<T> = { data?: T } & T;

function unwrap<T>(res: Envelope<T>): T {
  return (res?.data ?? res) as T;
}

const EvalPreview: React.FC = () => {
  const [status, setStatus] = useState<G2aStatus | null>(null);
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await apiClient.get<Envelope<G2aStatus>>(
        '/platform/apps/eval/store/g2a-status?tenant_id=eval-v1',
      );
      setStatus(unwrap(res));
    } catch (e: any) {
      setError(String(e?.message || e));
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const locked = Boolean(status?.v0_locked);
  const accuracy = Boolean(status?.accuracy_claim);

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6 text-gray-200">
      <header className="space-y-2">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h1 className="text-2xl font-semibold tracking-tight">评测中心 · Preview</h1>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded border border-gray-600 text-sm hover:bg-gray-800"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
        <p className="text-sm text-gray-400">
          EVAL_V1 G2a local preview · canonical API{' '}
          <code className="text-blue-300">/api/platform/apps/eval</code>
        </p>
      </header>

      <div
        className="rounded-lg border border-amber-700/50 bg-amber-950/30 px-4 py-3 flex gap-3 items-start"
        role="status"
      >
        <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div className="text-sm space-y-1">
          <div className="font-medium text-amber-200">诚实约束（强制）</div>
          <ul className="list-disc pl-5 text-amber-100/90 space-y-0.5">
            <li>
              <code>accuracy_claim</code> 必须为 false（当前：{String(accuracy)}）
            </li>
            <li>κ = null（D5 单人复核，无第二标注者）</li>
            <li>local <code>gate_claim</code> ≠ 外部 / staging / authorize</li>
          </ul>
        </div>
      </div>

      {error ? (
        <div className="rounded border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-200">
          无法加载 G2a 状态：{error}
          <div className="mt-2 text-gray-400">
            请确认平台服务已启动，且本机已完成 bootstrap / lock-v0。
          </div>
        </div>
      ) : null}

      <section className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <ShieldCheck className={`w-4 h-4 ${locked ? 'text-green-400' : 'text-gray-500'}`} />
          G2a 状态（tenant=eval-v1）
        </div>
        {loading && !status ? (
          <div className="text-sm text-gray-500">加载中…</div>
        ) : status ? (
          <dl className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
            <div>
              <dt className="text-gray-500">v0_locked</dt>
              <dd className={locked ? 'text-green-300' : 'text-yellow-300'}>
                {String(status.v0_locked)}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">g2a_ready</dt>
              <dd>{String(status.g2a_ready)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">tasks</dt>
              <dd>{status.task_count ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">adjudicated</dt>
              <dd>
                {status.labels_adjudicated ?? '—'}/{status.v0_lock_target ?? 30}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">pending</dt>
              <dd>{status.labels_pending ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">set_id</dt>
              <dd className="truncate" title={status.set_id || ''}>
                {status.set_id || '—'}
              </dd>
            </div>
            <div className="col-span-2 sm:col-span-3">
              <dt className="text-gray-500">note</dt>
              <dd className="text-gray-300">{status.note || '—'}</dd>
            </div>
          </dl>
        ) : null}
      </section>

      <section className="text-sm text-gray-400 space-y-2">
        <div className="font-medium text-gray-300">相关入口</div>
        <ul className="list-disc pl-5 space-y-1">
          <li>
            <Link className="text-blue-400 hover:underline" to="/diagnostics/eval">
              Agent 评估（旧页）
            </Link>
          </li>
          <li>
            <Link className="text-blue-400 hover:underline" to="/governance">
              Governance · code-review-gold
            </Link>
          </li>
          <li>
            <span className="text-gray-500">完整 E6 评测中心</span> — 未解冻（G2b / 另批）
          </li>
        </ul>
      </section>
    </div>
  );
};

export default EvalPreview;
