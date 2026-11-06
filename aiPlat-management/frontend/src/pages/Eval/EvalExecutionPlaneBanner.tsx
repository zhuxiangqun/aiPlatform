/**
 * B1-L /eval — execute-plane degrade banner (store/read stay usable).
 */
import { Info } from 'lucide-react';
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
    <div
      className="rounded-lg border border-sky-700/50 bg-sky-950/30 px-4 py-3 flex gap-3 items-start"
      role="status"
      data-testid="eval-execution-plane-banner"
      data-error-code={code || 'execution_not_migrated'}
    >
      <Info className="w-5 h-5 text-sky-400 shrink-0 mt-0.5" />
      <div className="text-sm space-y-1">
        <div className="font-medium text-sky-100">{title}</div>
        <p className="text-sky-100/80">
          人话：评测「读写报告」和「正式拆成独立执行服务」在产品上还没签完；本机
          proxy/worker 能跑 Job，只代表本地联调，不代表生产已迁移。
          评测集 / 报告 / 只读 store 仍可用。
          {detail ? <span className="block mt-1 text-sky-200/70">{detail}</span> : null}
        </p>
      </div>
    </div>
  );
}
