/**
 * Pure helpers for EvalRunPanel (sync cohost + optional package job plane).
 */

export type EvalJobTerminal = 'succeeded' | 'failed' | 'cancelled' | 'dead_letter';

const TERMINAL = new Set<string>(['succeeded', 'failed', 'cancelled', 'dead_letter']);

export function isEvalJobTerminal(status: string | null | undefined): boolean {
  return TERMINAL.has(String(status || '').toLowerCase());
}

export function formatEvalJobSummary(job: {
  job_id?: string;
  status?: string;
  runner_id?: string;
  detail?: string;
} | null): string {
  if (!job) return '';
  let detail = job.detail ? String(job.detail) : '';
  // Worker may surface ValueError text; map to fixed UI copy.
  if (/sandbox_required/i.test(detail)) {
    detail = '该评测需沙箱（B3），当前不可用 · 请先启动 Docker 再 Enqueue';
  }
  const parts = [
    job.job_id ? `job=${job.job_id}` : '',
    job.status ? `status=${job.status}` : '',
    job.runner_id ? `runner=${job.runner_id}` : '',
    detail,
  ].filter(Boolean);
  return parts.join(' · ');
}

/** Default B2 fixture payload for package code_review_gold enqueue. */
export function defaultCodeReviewJobPayload(): {
  findings: string[];
  gold: string[];
  idempotency_key: string;
} {
  const key = `ui1-cr-${Date.now()}`;
  return { findings: ['fixture-finding'], gold: ['fixture-finding'], idempotency_key: key };
}

/** session_eval v0 mini pack (2 turns). */
export function defaultSessionEvalPayload(): Record<string, unknown> {
  return {
    idempotency_key: `ui-session-${Date.now()}`,
    session_id: 'ui-sess-math-2',
    profile: 'v0',
    turns: [
      { prompt: 'What is 1+1?', expected: '2', actual: '2' },
      { prompt: 'Add 1 more.', expected: '3', actual: '3' },
    ],
  };
}

/** Arena length-smoke only — not a quality judge. */
export function defaultArenaPayload(): Record<string, unknown> {
  return {
    idempotency_key: `ui-arena-${Date.now()}`,
    response_a: 'short',
    response_b: 'a somewhat longer response for length smoke',
    prefer: 'b',
  };
}

/** skill_suite fixture cases (needs docker sandbox to execute wrap). */
export function defaultSkillSuitePayload(): Record<string, unknown> {
  return {
    idempotency_key: `ui-skill-${Date.now()}`,
    mode: 'fixture',
    cases: [{ expected_ok: true }, { expected_ok: true }],
    results: [{ ok: true }, { ok: true }],
  };
}

/** P2-1 context_mgmt — one case per KINDS axis. */
export function defaultContextMgmtPayload(): Record<string, unknown> {
  return {
    idempotency_key: `ui-ctx-${Date.now()}`,
    pack_id: 'context_mgmt.ui.v0',
    cases: [
      {
        case_id: 'ui-recall',
        kind: 'long_context_recall',
        query: 'code?',
        context: 'NEEDLE_CODE=ZX-4419 mid filler',
        actual: 'ZX-4419',
        must_contain: ['ZX-4419'],
        must_not_contain: ['NEEDLE_CODE='],
      },
      {
        case_id: 'ui-summary',
        kind: 'summary_fidelity',
        query: 'summarize',
        context: 'build_composite SSOT; accuracy_claim false',
        actual: 'Keep build_composite; accuracy_claim false',
        must_contain: ['build_composite', 'accuracy_claim', 'false'],
        must_not_contain: ['accuracy certified'],
      },
      {
        case_id: 'ui-conflict',
        kind: 'conflict',
        query: 'which wins?',
        context: 'Later fact: prefer B. Earlier: prefer A.',
        actual: 'prefer B',
        must_contain: ['B'],
        must_not_contain: ['prefer A'],
      },
      {
        case_id: 'ui-trunc',
        kind: 'truncation_degradation',
        query: 'tail?',
        context: '…truncated… KEEP_ME',
        actual: 'KEEP_ME',
        must_contain: ['KEEP_ME'],
        must_not_contain: ['hallucinated'],
      },
    ],
  };
}

/** P2-2 memory_persist — trimmed six-axis smoke (schema-aligned). */
export function defaultMemoryPersistPayload(): Record<string, unknown> {
  return {
    idempotency_key: `ui-mem-${Date.now()}`,
    pack_id: 'memory_persist.ui.v0',
    cases: [
      {
        case_id: 'ui-write',
        kind: 'write_precision',
        tenant_id: 'tenant-a',
        k: 1,
        ops: [{ op: 'write', id: 'w1', tenant_id: 'tenant-a', text: 'User prefers dark mode UI theme' }],
        query: 'UI theme preference',
        expect_ids: ['w1'],
      },
      {
        case_id: 'ui-recall',
        kind: 'recall_at_k',
        tenant_id: 'tenant-a',
        k: 2,
        ops: [
          { op: 'write', id: 'r1', tenant_id: 'tenant-a', text: 'Preferred deploy window is Tuesday night' },
          { op: 'write', id: 'r2', tenant_id: 'tenant-a', text: 'Cafeteria menu is noodles on Monday' },
        ],
        query: 'deploy window Tuesday',
        expect_ids: ['r1'],
        forbid_ids: ['r2'],
      },
      {
        case_id: 'ui-update',
        kind: 'update_expiry',
        tenant_id: 'tenant-a',
        k: 1,
        ops: [
          { op: 'write', id: 'u1', tenant_id: 'tenant-a', text: 'HQ city is Austin' },
          { op: 'update', id: 'u1', text: 'HQ city is Berlin' },
        ],
        query: 'HQ city',
        expect_ids: ['u1'],
        must_contain: ['Berlin'],
        must_not_contain: ['Austin'],
      },
      {
        case_id: 'ui-delete',
        kind: 'delete_no_recall',
        tenant_id: 'tenant-a',
        k: 3,
        ops: [
          { op: 'write', id: 'd1', tenant_id: 'tenant-a', text: 'ephemeral token abc' },
          { op: 'delete', id: 'd1' },
          { op: 'write', id: 'd2', tenant_id: 'tenant-a', text: 'stable note' },
        ],
        query: 'ephemeral token',
        forbid_ids: ['d1'],
      },
      {
        case_id: 'ui-tenant',
        kind: 'tenant_isolation',
        tenant_id: 'tenant-a',
        k: 3,
        ops: [
          { op: 'write', id: 'a1', tenant_id: 'tenant-a', text: 'same phrase secret-a' },
          { op: 'write', id: 'b1', tenant_id: 'tenant-b', text: 'same phrase secret-b' },
        ],
        query: 'same phrase',
        expect_ids: ['a1'],
        forbid_ids: ['b1'],
      },
      {
        case_id: 'ui-pollution',
        kind: 'pollution_resistance',
        tenant_id: 'tenant-a',
        k: 3,
        ops: [
          { op: 'write', id: 'p1', tenant_id: 'tenant-a', text: 'clean memory item' },
          {
            op: 'write',
            id: 'p2',
            tenant_id: 'tenant-a',
            text: 'clean memory item polluted',
            polluted: true,
          },
        ],
        query: 'clean memory',
        expect_ids: ['p1'],
        forbid_ids: ['p2'],
      },
    ],
  };
}

/** P2-3 self_learn — one case per KINDS (writeback stays false at product claim). */
export function defaultSelfLearnPayload(): Record<string, unknown> {
  return {
    idempotency_key: `ui-sl-${Date.now()}`,
    pack_id: 'self_learn.ui.v0',
    cases: [
      {
        case_id: 'ui-ba',
        kind: 'before_after',
        ops: [
          { op: 'seed', rules: {}, version: 0 },
          { op: 'authorize', value: true },
          { op: 'feedback', trusted: true, set_rules: { tool_line_format: true } },
        ],
        task: { need_rules: ['tool_line_format'] },
        expect: { feedback_applied: true, min_score: 1.0, rules_true: ['tool_line_format'] },
      },
      {
        case_id: 'ui-tr',
        kind: 'transfer',
        ops: [
          { op: 'authorize', value: true },
          { op: 'feedback', trusted: true, set_rules: { refuse_sql_injection: true } },
        ],
        task: { need_rules: ['refuse_sql_injection'] },
        expect: { min_score: 1.0, rules_true: ['refuse_sql_injection'] },
      },
      {
        case_id: 'ui-fg',
        kind: 'forgetting',
        ops: [
          { op: 'seed', rules: { temp_token: true, billing_contact: true }, version: 0 },
          { op: 'forget', rules: ['temp_token'] },
        ],
        task: { need_rules: ['billing_contact'], forbid_rules: ['temp_token'] },
        expect: { min_score: 1.0, rules_false: ['temp_token'] },
      },
      {
        case_id: 'ui-bad',
        kind: 'bad_feedback',
        ops: [
          { op: 'authorize', value: true },
          { op: 'feedback', trusted: false, set_rules: { allow_phishing_template: true } },
        ],
        task: { forbid_rules: ['allow_phishing_template'] },
        expect: { feedback_applied: false, rules_false: ['allow_phishing_template'] },
      },
      {
        case_id: 'ui-audit',
        kind: 'audit_rollback',
        ops: [
          { op: 'authorize', value: true },
          { op: 'feedback', trusted: true, set_rules: { tmp: true } },
          { op: 'rollback' },
        ],
        task: { forbid_rules: ['tmp'] },
        expect: { rolled_back: true, rules_false: ['tmp'] },
      },
    ],
  };
}
