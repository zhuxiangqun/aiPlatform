/**
 * B1-L /eval — execute-plane degrade banner (store/read stay usable).
 * Collapsible — default collapsed; preference in localStorage.
 */
import { Info } from 'lucide-react';
import EvalCollapsibleBanner from './EvalCollapsibleBanner';
import {
  EXECUTION_NOT_MIGRATED_COPY,
  SANDBOX_REQUIRED_COPY,
  messageForEvalExecutionCode,
} from './evalExecutionErrors';

type Props = {
  code?: string | null;
  /** Extra one-liner under the title (e.g. proxy mode). */
  detail?: string | null;
};

export default function EvalExecutionPlaneBanner({ code, detail }: Props) {
  const mapped = messageForEvalExecutionCode(code);
  const title =
    mapped ||
    (code === 'sandbox_required' ? SANDBOX_REQUIRED_COPY : EXECUTION_NOT_MIGRATED_COPY);

  return (
    <EvalCollapsibleBanner
      storageKey="eval.banner.execution_plane.open"
      testId="eval-execution-plane-banner"
      toneClassName="border-sky-700/50 bg-sky-950/30 text-sky-100"
      icon={<Info className="w-5 h-5 text-sky-400" />}
      dataAttrs={{ 'data-error-code': code || 'execution_not_migrated' }}
      summary={
        <>
          {title}
          <span className="font-normal text-sky-200/70 text-xs sm:text-sm ml-2">
            本地联调 ≠ 生产迁移 · 点击展开
          </span>
        </>
      }
    >
      <div className="space-y-1 text-sky-100/80">
        <p>
          人话：评测「读写报告」和「正式拆成独立执行服务」在产品上还没签完；本机
          proxy/worker 能跑 Job，只代表本地联调，不代表生产已迁移。 评测集 / 报告 /
          只读 store 仍可用。
        </p>
        <p>
          双态分离：Banner「平面未迁移」≠ 某条 Job 的{' '}
          <code className="text-sky-200/90">runtime_tier=eval_worker</code>
          。当前「评测 Agent」正式 live 仍是{' '}
          <code className="text-sky-200/90">workspace_execute</code>
          ，不要读成 Agent exam 已上 Worker。
        </p>
        {detail ? <p className="text-sky-200/70">{detail}</p> : null}
      </div>
    </EvalCollapsibleBanner>
  );
}
