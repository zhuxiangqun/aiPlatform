/**
 * B1 Route Matrix — map eval execution error bodies to /eval UI copy.
 * Store/read remain usable; dynamic execute uses these codes until B2/B3.
 */

export type EvalExecutionErrorCode =
  | 'execution_not_migrated'
  | 'sandbox_required'
  | 'runner_forbidden'
  | string;

export type EvalExecutionErrorBody = {
  error?: {
    code?: string;
    runner_id?: string;
    retryable?: boolean;
    detail?: string;
  };
  code?: string;
};

export const EXECUTION_NOT_MIGRATED_COPY = '执行平面尚未迁移（B2）';
export const SANDBOX_REQUIRED_COPY = '该评测需沙箱（B3），当前不可用';
export const RUNNER_FORBIDDEN_COPY = '该 runner 不在允许列表，已拒绝执行';

/** Fixed copy for known B1/B2/B3 execution error codes. */
export function messageForEvalExecutionCode(code: EvalExecutionErrorCode | null | undefined): string {
  const c = String(code || '').trim();
  if (c === 'execution_not_migrated') return EXECUTION_NOT_MIGRATED_COPY;
  if (c === 'sandbox_required') return SANDBOX_REQUIRED_COPY;
  if (c === 'runner_forbidden') return RUNNER_FORBIDDEN_COPY;
  return '';
}

/** Pull `error.code` from a JSON body (direct or `{ data: { error } }`). */
export function evalExecutionErrorCode(payload: unknown): string {
  if (!payload || typeof payload !== 'object') return '';
  const root = payload as EvalExecutionErrorBody & { data?: EvalExecutionErrorBody };
  const nested = root.data?.error?.code || root.data?.code;
  const direct = root.error?.code || root.code;
  return String(nested || direct || '').trim();
}

export function messageForEvalExecutionPayload(payload: unknown): string {
  return messageForEvalExecutionCode(evalExecutionErrorCode(payload));
}

/** True when UI should show the B1 execute-plane banner (standalone proxy or explicit stubs). */
export function shouldShowExecutionPlaneBanner(input: {
  upstreamMode?: string | null;
  b1lExecutionStubs?: boolean | null;
  lastErrorCode?: string | null;
}): boolean {
  if (input.b1lExecutionStubs === true) return true;
  if (String(input.upstreamMode || '').toLowerCase() === 'proxy') return true;
  const code = String(input.lastErrorCode || '').trim();
  return code === 'execution_not_migrated' || code === 'sandbox_required';
}
