/**
 * Shared Skill execute contract — workspace + engine Core Skills.
 * Default: stream (immediate run_id + live flow) + trial (local signature bypass).
 */
export type SkillExecuteOptions = Record<string, unknown>;

export type SkillExecutePayload = {
  input?: Record<string, unknown>;
  context?: Record<string, unknown>;
  options?: SkillExecuteOptions;
  config?: Record<string, unknown>;
};

/** Merge caller options with platform defaults. Explicit values win. */
export function withSkillExecuteDefaults(
  data: SkillExecutePayload = {},
  extras?: SkillExecuteOptions,
): SkillExecutePayload {
  const incoming = (data.options && typeof data.options === 'object' ? data.options : {}) as SkillExecuteOptions;
  return {
    ...data,
    options: {
      stream: true,
      trial: true,
      ...extras,
      ...incoming,
    },
  };
}

export type NormalizedSkillExecuteResult = {
  status: string;
  run_id?: string;
  execution_id?: string;
  output?: unknown;
  error?: any;
  error_message?: string;
  error_detail?: any;
  duration_ms?: number;
  tokens?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
};

export function normalizeSkillExecuteResult(res: any): NormalizedSkillExecuteResult {
  if (!res || typeof res !== 'object') {
    return { status: 'failed', error: '空结果' };
  }
  let output: unknown =
    res.output !== undefined && res.output !== null
      ? res.output
      : res.result !== undefined && typeof res.result === 'object'
        ? res.result
        : undefined;

  if (
    output == null &&
    (typeof res.markdown === 'string' ||
      (typeof res.result === 'string' && /\.(pptx|potx|docx|xlsx|pdf)$/i.test(res.result)))
  ) {
    output = {
      result: res.result,
      markdown: res.markdown,
      page_count: res.page_count,
      template_used: res.template_used,
      generated_at: res.generated_at,
      warnings: res.warnings,
    };
  }

  return {
    status: String(res.status || (res.ok === false || res.success === false ? 'failed' : 'completed')),
    run_id: res.run_id || res.execution_id,
    execution_id: res.execution_id || res.run_id,
    output,
    error: res.error,
    error_message: res.error_message,
    error_detail: res.error_detail,
    duration_ms: res.duration_ms,
    tokens: res.tokens,
  };
}

export function isSkillRunInFlight(status: string): boolean {
  const s = String(status || '').toLowerCase();
  // unknown: stream race before run_start / skill_executions row exists — keep polling
  return s === 'running' || s === 'accepted' || s === 'queued' || s === 'pending' || s === 'unknown';
}

export function shouldOpenSkillFlow(status: string): boolean {
  const s = String(status || '').toLowerCase();
  return (
    isSkillRunInFlight(s) ||
    s === 'completed' ||
    s === 'failed' ||
    s === 'timeout' ||
    s === 'error'
  );
}
