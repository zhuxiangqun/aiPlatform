/**
 * UI-6 — Overview: G2a snapshot + upstream mode + quick jumps (honesty intact).
 */
import { ShieldCheck } from 'lucide-react';
import { EVAL_TAB_GUIDES } from './evalTabGuides';

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
  { id: 'worksheets', label: 'Worksheets' },
  { id: 'code-review', label: 'Code-review' },
  { id: 'session', label: 'Session' },
  { id: 'arena', label: 'Arena' },
  { id: 'skill', label: 'Skill' },
  { id: 'research', label: 'P2 Research' },
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
  const upstreamHint =
    upstreamMode === 'proxy'
      ? '（本机 Job 已接通）'
      : upstreamMode === 'cohost'
        ? '（Job 未接通）'
        : '';

  return (
    <div className="space-y-4 text-sm" data-testid="eval-overview-panel">
      <section className="rounded-lg border border-gray-700 bg-gray-900/40 p-4 space-y-3">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 font-medium">
            <ShieldCheck className={`w-4 h-4 ${locked ? 'text-green-400' : 'text-gray-500'}`} />
            G2a 总览（工程校准快照）
          </div>
          <span className="text-xs text-gray-500">
            上游=
            <code className="text-gray-300">{upstreamMode || '—'}</code>
            {upstreamHint}
            {' · '}宣称准确率=
            <span className="text-amber-200">{String(Boolean(status?.accuracy_claim))}</span>
          </span>
        </div>

        {loading && !status ? (
          <div className="text-gray-500">加载中…</div>
        ) : status ? (
          <dl className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div>
              <dt className="text-gray-500" title="本地黄金集是否已锁定">
                黄金集锁定 v0
              </dt>
              <dd className={locked ? 'text-green-300' : 'text-yellow-300'}>
                {String(status.v0_locked)}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500" title="工程校准是否就绪">
                校准就绪
              </dt>
              <dd>{String(status.g2a_ready)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">任务数</dt>
              <dd>{status.task_count ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500" title="已人工裁决 / 锁定目标">
                已裁决
              </dt>
              <dd>
                {status.labels_adjudicated ?? '—'}/{status.v0_lock_target ?? 30}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">待复核</dt>
              <dd>{pendingCount ?? status.labels_pending ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">评测集 / 门禁条数</dt>
              <dd>
                {setsCount} / {gatesCount}
              </dd>
            </div>
            <div className="col-span-2 sm:col-span-3">
              <dt className="text-gray-500">说明</dt>
              <dd className="text-gray-300">
                {status.note ||
                  'G2a＝本机工程校准预览，不是准确率；单人复核时没有 κ（一致性）指标。'}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="text-gray-500">无 G2a 状态。</p>
        )}

        {onNavigate ? (
          <div className="space-y-2 pt-1">
            <p className="text-xs text-gray-500">快捷跳转（鼠标悬停 Tab 也可看简介）：</p>
            <div className="flex flex-wrap gap-2">
              {JUMPS.map((j) => (
                <button
                  key={j.id}
                  type="button"
                  title={EVAL_TAB_GUIDES[j.id]?.what || j.label}
                  data-testid={`eval-overview-jump-${j.id}`}
                  onClick={() => onNavigate(j.id)}
                  className="px-2.5 py-1 rounded border border-gray-600 text-xs text-gray-200 hover:bg-gray-800"
                >
                  {j.label}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
