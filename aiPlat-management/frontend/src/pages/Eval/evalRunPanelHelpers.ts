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
  const parts = [
    job.job_id ? `job=${job.job_id}` : '',
    job.status ? `status=${job.status}` : '',
    job.runner_id ? `runner=${job.runner_id}` : '',
    job.detail ? String(job.detail) : '',
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
