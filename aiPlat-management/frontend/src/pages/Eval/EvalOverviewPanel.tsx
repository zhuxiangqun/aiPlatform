/**
 * Overview — three artifact intents + pipe smoke. Artifact first.
 */
import { Bot, Boxes, Puzzle, ShieldCheck, Wrench } from 'lucide-react';
import EvalCollapsibleBanner from './EvalCollapsibleBanner';

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
  const jobReady = upstreamMode === 'proxy';

  return (
    <div className="space-y-4 text-sm" data-testid="eval-overview-panel">
      <section
        className="rounded-lg border border-violet-700/40 bg-violet-950/20 p-5 space-y-4"
        data-testid="eval-overview-start"
      >
        <div className="space-y-1">
          <h2 className="text-base font-medium text-violet-50">评测对象是什么？</h2>
          <p className="text-xs text-violet-100/75 leading-relaxed">
            下面三张<strong className="text-violet-50">成果物</strong>
            卡片分别评 Agent / Skill suite / 生成应用 Run。右侧「验管道」只检查计分/排队通不通，
            <strong className="text-violet-50">不评产品好不好</strong>，也不是准确率认证。
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          <button
            type="button"
            data-testid="eval-overview-intent-agent"
            onClick={() => onNavigate?.('agents')}
            className="text-left rounded-lg border border-violet-500/60 bg-gray-950/70 px-4 py-4 hover:bg-violet-950/50 transition-colors"
          >
            <div className="flex items-center gap-2 text-violet-50 font-medium">
              <Bot className="w-5 h-5 shrink-0" />
              评测 Agent
            </div>
            <p className="mt-2 text-[11px] text-violet-200/70">工作区 Agent · 用例集 dry/live</p>
            <ol className="mt-3 list-decimal pl-5 text-xs text-violet-100/85 space-y-1.5 leading-relaxed">
              <li>选 Agent + 用例集</li>
              <li>预检 → 正式评测</li>
              <li>历史工程分 + 可归因报告</li>
            </ol>
          </button>

          <button
            type="button"
            data-testid="eval-overview-intent-skill"
            onClick={() => onNavigate?.('skills')}
            className="text-left rounded-lg border border-violet-500/60 bg-gray-950/70 px-4 py-4 hover:bg-violet-950/50 transition-colors"
          >
            <div className="flex items-center gap-2 text-violet-50 font-medium">
              <Puzzle className="w-5 h-5 shrink-0" />
              评测 Skill
            </div>
            <p className="mt-2 text-[11px] text-violet-200/70">Skill suite · skill_evals</p>
            <ol className="mt-3 list-decimal pl-5 text-xs text-violet-100/85 space-y-1.5 leading-relaxed">
              <li>选已登记 suite</li>
              <li>跑 suite → 看 run/results</li>
              <li>≠ 验管道 Skill fixture</li>
            </ol>
          </button>

          <button
            type="button"
            data-testid="eval-overview-intent-apps"
            onClick={() => onNavigate?.('apps')}
            className="text-left rounded-lg border border-violet-500/60 bg-gray-950/70 px-4 py-4 hover:bg-violet-950/50 transition-colors"
          >
            <div className="flex items-center gap-2 text-violet-50 font-medium">
              <Boxes className="w-5 h-5 shrink-0" />
              评测生成应用
            </div>
            <p className="mt-2 text-[11px] text-violet-200/70">生成应用 Run · runs_eval</p>
            <ol className="mt-3 list-decimal pl-5 text-xs text-violet-100/85 space-y-1.5 leading-relaxed">
              <li>粘贴 run_id</li>
              <li>最新评测 / 自动评测</li>
              <li>看 runs_eval 报告摘要</li>
            </ol>
          </button>

          <button
            type="button"
            data-testid="eval-overview-intent-job"
            onClick={() => onNavigate?.('code-review')}
            className="text-left rounded-lg border border-sky-800/50 bg-gray-950/40 px-4 py-4 hover:bg-sky-950/30 transition-colors"
          >
            <div className="flex items-center gap-2 text-sky-50 font-medium">
              <Wrench className="w-5 h-5 shrink-0" />
              验管道（自检）
            </div>
            <p className="mt-2 text-[11px] text-sky-200/70">评测系统自己 · 不是产品</p>
            <ol className="mt-3 list-decimal pl-5 text-xs text-sky-100/80 space-y-1.5 leading-relaxed">
              <li>
                <strong>Code-review</strong>：match-only
              </li>
              <li>
                <strong>Session</strong>：Enqueue
              </li>
              <li>
                <strong>Skill 管道</strong>：fixture / Docker
              </li>
            </ol>
            <p className="mt-3 text-[11px] text-sky-100/55">
              {jobReady ? '可以 Enqueue' : '仍可先 match-only；Enqueue 需本机评测服务'}
            </p>
          </button>
        </div>
        <p className="text-[11px] text-violet-200/60">
          其它对象 Plan 链（prompt/workflow/model/dataset/system + L5 门槛核对）→{' '}
          <button
            type="button"
            className="underline text-violet-100 hover:text-white"
            data-testid="eval-overview-typed-plan"
            onClick={() => onNavigate?.('typed-plan')}
          >
            高级 · 对象Plan
          </button>
        </p>
      </section>

      <EvalCollapsibleBanner
        storageKey="eval.overview.snapshot.open"
        testId="eval-overview-snapshot"
        defaultOpen={false}
        toneClassName="border-gray-700 bg-gray-900/40 text-gray-200"
        icon={
          <ShieldCheck className={`w-5 h-5 ${locked ? 'text-green-400' : 'text-gray-500'}`} />
        }
        summary={
          <>
            其它状态（一般不用看）
            <span className="font-normal text-gray-500 text-xs ml-2">
              集 {setsCount} · 门禁 {gatesCount} · 上游 {upstreamMode || '—'}
            </span>
          </>
        }
      >
        {loading && !status ? (
          <p className="text-gray-500">加载中…</p>
        ) : status ? (
          <dl className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
            <div>
              <dt className="text-gray-500">黄金集锁定</dt>
              <dd>{String(status.v0_locked)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">校准就绪</dt>
              <dd>{String(status.g2a_ready)}</dd>
            </div>
            <div>
              <dt className="text-gray-500">任务数</dt>
              <dd>{status.task_count ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">已裁决</dt>
              <dd>
                {status.labels_adjudicated ?? '—'}/{status.v0_lock_target ?? 30}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500">待复核</dt>
              <dd>{pendingCount ?? status.labels_pending ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-gray-500">评测集 / 门禁</dt>
              <dd>
                {setsCount} / {gatesCount}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="text-gray-500 text-xs">无额外状态。</p>
        )}
        {onNavigate ? (
          <div className="flex flex-wrap gap-2 pt-2">
            {(
              [
                ['sets', '管题目'],
                ['reports', '看报告'],
                ['session', 'Session 管道'],
                ['skill', 'Skill 管道'],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                data-testid={`eval-overview-jump-${id}`}
                onClick={() => onNavigate(id)}
                className="px-2.5 py-1 rounded border border-gray-600 text-xs text-gray-300 hover:bg-gray-800"
              >
                {label}
              </button>
            ))}
          </div>
        ) : null}
      </EvalCollapsibleBanner>
    </div>
  );
}
