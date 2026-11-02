import { describe, expect, it } from 'vitest';
import {
  EXECUTION_NOT_MIGRATED_COPY,
  SANDBOX_REQUIRED_COPY,
  evalExecutionErrorCode,
  messageForEvalExecutionCode,
  messageForEvalExecutionPayload,
  shouldShowExecutionPlaneBanner,
} from './evalExecutionErrors';

describe('evalExecutionErrors', () => {
  it('maps known codes to B1 route-matrix copy', () => {
    expect(messageForEvalExecutionCode('execution_not_migrated')).toBe(EXECUTION_NOT_MIGRATED_COPY);
    expect(messageForEvalExecutionCode('sandbox_required')).toBe(SANDBOX_REQUIRED_COPY);
    expect(messageForEvalExecutionCode('other')).toBe('');
  });

  it('parses nested and direct error bodies', () => {
    expect(
      evalExecutionErrorCode({
        error: { code: 'execution_not_migrated', retryable: false, runner_id: 'skill_suite' },
      }),
    ).toBe('execution_not_migrated');
    expect(
      evalExecutionErrorCode({
        data: { error: { code: 'sandbox_required', runner_id: 'http_probe' } },
      }),
    ).toBe('sandbox_required');
    expect(
      messageForEvalExecutionPayload({
        error: { code: 'execution_not_migrated', detail: 'x' },
      }),
    ).toBe(EXECUTION_NOT_MIGRATED_COPY);
  });

  it('shows banner for proxy / stubs / last error', () => {
    expect(shouldShowExecutionPlaneBanner({ upstreamMode: 'proxy' })).toBe(true);
    expect(shouldShowExecutionPlaneBanner({ b1lExecutionStubs: true })).toBe(true);
    expect(
      shouldShowExecutionPlaneBanner({ lastErrorCode: 'execution_not_migrated' }),
    ).toBe(true);
    expect(shouldShowExecutionPlaneBanner({ upstreamMode: 'cohost' })).toBe(false);
  });
});
