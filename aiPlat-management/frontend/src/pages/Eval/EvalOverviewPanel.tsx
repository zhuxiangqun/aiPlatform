/**
 * UI-6 — Overview: G2a snapshot + upstream mode + quick jumps (honesty intact).
 */
import { ShieldCheck } from 'lucide-react';

type G2aStatus = {
  v0_locked?: boolean;
  g2a_ready?: boolean;
  task_count?: number;
  labels_adjudicated?: number;
  labels_pending?: number;
  v0_lock_target?: number;
  accuracy_claim?: boolean;
  note?: string;
};

type Props = {
  status: G2aStatus | null;
  loading?: boolean;
  pendingCount?: number | null;
  setsCount?: number;
  gatesCount?: number;
  upstreamMode?: string | null;
  onNavigate?: (tab: string) => void;
};

const JUMPS = [
  { id: 'review', label: '复核' },
  { id: 'gates', label: '门禁' },
  { id: 'reports', label: '报告' },
  { id: 'g2b', label: 'G2b' },
  { id: 'preference', label: 'Preference' },
  { id: 'scorecard', label: 'Scorecard' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'code-review', label: 'Code-review' },
  { id: 'settings', label: 'G2c 设置' },
] as const;

export default function EvalOverviewPanel({
  status,
  loading,
  pendingCount,
  setsCount = 0,
  gatesCount = 0,
  upstreamMode,
  onNavigate,
}: Props) {
  const locked = Boolean(status?.v0_locked);

  return (
    <div className="space-y-4 text-sm" data-testid="eval-overview-panel">
      <section className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 font-medium">
            <ShieldCheck className={`w-4 h-4 ${locked ? 'text-green-400' : 'text-gray-500'}`} />
            G2a 总览
          </div>
          <span className="text-xs text-gray-500">
            upstream=<code className="text-gray-300">{upstreamMode || '—'}</code>
            {' · '}accuracy_claim=
            <span className="text-amber-200">{String(Boolean(status?.accuracy_claim))}</span>
          </span>
        </div>

        {loading && !status ? (
          <div className="text-gray-500">加载中…</div>
        ) : status ? (
          <dl className="grid grid-cols-2 sm:grid-cols-3 gap-3">
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
              <dd>{pendingCount ?? status.labels_pending ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">sets / gates</dt>
              <dd>
                {setsCount} / {gatesCount}
              </dd>
            </div>
            <div className="col-span-2 sm:col-span-3">
              <dt className="text-gray-500">note</dt>
              <dd className="text-gray-300">{status.note || '—'}</dd>
            </div>
          </dl>
        ) : (
          <p className="text-gray-500">无 G2a 状态。</p>
        )}

        {onNavigate ? (
          <div className="flex flex-wrap gap-2 pt-1">
            {JUMPS.map((j) => (
              <button
                key={j.id}
                type="button"
                data-testid={`eval-overview-jump-${j.id}`}
                onClick={() => onNavigate(j.id)}
                className="px-2.5 py-1 rounded border border-gray-600 text-xs text-gray-200 hover:bg-gray-800"
              >
                {j.label}
              </button>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}
