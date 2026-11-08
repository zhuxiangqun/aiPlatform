import { describe, expect, it } from 'vitest';
import { evaluateL5ClaimsGate } from './claimsGate';

function fullScope(over: Record<string, unknown> = {}) {
  return {
    object_type: 'agent',
    object_id: 'qa_agent',
    object_version: 'v1',
    runtime_tier: 'workspace_execute',
    plan_id: 'plan-1',
    set_ids: ['default/normal'],
    oracle_types: ['lexical_path'],
    dimensions: ['task_result'],
    sample_n: 120,
    has_run_evidence: true,
    untested_applicable_n: 0,
    runtime_claim: true,
    ...over,
  };
}

describe('evaluateL5ClaimsGate', () => {
  it('defaults claims false without authorize', () => {
    const r = evaluateL5ClaimsGate(fullScope());
    expect(r.accuracy_eligible).toBe(true);
    expect(r.accuracy_claim).toBe(false);
    expect(r.sufficiency_eligible).toBe(false);
  });

  it('authorizes accuracy only when explicit + gates', () => {
    const r = evaluateL5ClaimsGate(fullScope(), { explicitAuthorize: true });
    expect(r.accuracy_claim).toBe(true);
    expect(r.sufficiency_claim).toBe(false);
  });

  it('blocks fixture and incomplete coverage', () => {
    expect(
      evaluateL5ClaimsGate(fullScope({ runtime_tier: 'fixture' })).failed,
    ).toContain('fixture_runtime_not_l5');
    expect(
      evaluateL5ClaimsGate(fullScope({ untested_applicable_n: 2 })).failed,
    ).toContain('incomplete_coverage_untested');
  });
});
