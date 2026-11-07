import { describe, expect, it } from 'vitest';
import {
  defaultCodeReviewJobPayload,
  formatEvalJobSummary,
  isEvalJobTerminal,
} from './evalRunPanelHelpers';

describe('evalRunPanelHelpers', () => {
  it('detects terminal job statuses', () => {
    expect(isEvalJobTerminal('succeeded')).toBe(true);
    expect(isEvalJobTerminal('FAILED')).toBe(true);
    expect(isEvalJobTerminal('queued')).toBe(false);
    expect(isEvalJobTerminal('running')).toBe(false);
  });

  it('formats job summary', () => {
    expect(
      formatEvalJobSummary({
        job_id: 'j1',
        status: 'queued',
        runner_id: 'code_review_gold',
      }),
    ).toBe('job=j1 · status=queued · runner=code_review_gold');
  });

  it('maps sandbox_required detail to fixed copy', () => {
    const s = formatEvalJobSummary({
      job_id: 'j2',
      status: 'failed',
      runner_id: 'skill_suite',
      detail: 'sandbox_required:skill_suite',
    });
    expect(s).toContain('job=j2');
    expect(s).toContain('Docker');
    expect(s).not.toContain('sandbox_required:skill_suite');
  });

  it('builds fixture enqueue payload', () => {
    const p = defaultCodeReviewJobPayload();
    expect(p.findings).toEqual(p.gold);
    expect(p.idempotency_key).toMatch(/^ui1-cr-/);
  });
});
