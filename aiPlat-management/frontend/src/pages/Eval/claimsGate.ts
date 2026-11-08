/**
 * L5 scope-bound claims gate (mirrors core claims_gate.py / eval.claims_gate.v1).
 * Formal reports call this check-only: explicitAuthorize defaults false → claims stay false.
 */

export const CLAIMS_GATE_SCHEMA = 'eval.claims_gate.v1';
export const DEFAULT_MIN_SAMPLE_N = 100;

export type ClaimsGateEvidence = {
  object_type?: string;
  object_id?: string;
  object_version?: string;
  runtime_tier?: string;
  plan_id?: string;
  set_ids?: string[];
  oracle_types?: string[];
  dimensions?: string[];
  sample_n?: number;
  min_sample_n?: number;
  has_run_evidence?: boolean;
  untested_applicable_n?: number;
  runtime_claim?: boolean;
  fixture_only?: boolean;
  human_review?: boolean;
  calibrated_rubric?: boolean;
};

export type ClaimsGateReport = {
  schema: typeof CLAIMS_GATE_SCHEMA;
  scope: {
    object_type: string;
    object_id: string;
    object_version: string;
    runtime_tier: string;
    plan_id: string;
    set_ids: string[];
    oracle_types: string[];
    dimensions: string[];
    sample_n: number;
    min_sample_n: number;
  };
  gates: {
    scope_complete: boolean;
    has_run_evidence: boolean;
    complete_coverage: boolean;
    non_fixture_runtime: boolean;
    runtime_claim: boolean;
    sample_n_met: boolean;
    human_review_or_calibrated_rubric: boolean;
  };
  missing: string[];
  failed: string[];
  failed_sufficiency: string[];
  accuracy_eligible: boolean;
  sufficiency_eligible: boolean;
  explicit_authorize: boolean;
  accuracy_claim: boolean;
  sufficiency_claim: boolean;
  honesty: string;
};

function asList(v: unknown): string[] {
  if (v == null) return [];
  if (typeof v === 'string') {
    const s = v.trim();
    return s ? [s] : [];
  }
  if (Array.isArray(v)) return v.map(String).map((x) => x.trim()).filter(Boolean);
  const s = String(v).trim();
  return s ? [s] : [];
}

const REQUIRED_SCOPE_KEYS = [
  'object_type',
  'object_id',
  'object_version',
  'runtime_tier',
  'plan_id',
  'set_ids',
  'oracle_types',
  'dimensions',
  'sample_n',
] as const;

/** Evaluate whether scope-bound L5 claims may be authorized. Default: never claim. */
export function evaluateL5ClaimsGate(
  evidence: ClaimsGateEvidence | null | undefined,
  opts: { explicitAuthorize?: boolean } = {},
): ClaimsGateReport {
  const ev = { ...(evidence || {}) };
  const missing: string[] = [];
  const failed: string[] = [];
  const explicitAuthorize = Boolean(opts.explicitAuthorize);

  for (const k of REQUIRED_SCOPE_KEYS) {
    const val = (ev as Record<string, unknown>)[k];
    if (val == null || val === '' || (Array.isArray(val) && val.length === 0)) {
      missing.push(`scope.${k}`);
    }
  }

  let sample_n = 0;
  try {
    sample_n = Number(ev.sample_n || 0);
    if (!Number.isFinite(sample_n)) throw new Error('bad');
  } catch {
    sample_n = 0;
    failed.push('sample_n_invalid');
  }
  let min_n = DEFAULT_MIN_SAMPLE_N;
  try {
    min_n = Number(ev.min_sample_n || DEFAULT_MIN_SAMPLE_N);
    if (!Number.isFinite(min_n)) min_n = DEFAULT_MIN_SAMPLE_N;
  } catch {
    min_n = DEFAULT_MIN_SAMPLE_N;
  }

  const has_run = Boolean(ev.has_run_evidence);
  if (!has_run) failed.push('no_run_evidence');

  let untested_n = 0;
  try {
    untested_n = Number(ev.untested_applicable_n || 0);
    if (!Number.isFinite(untested_n)) throw new Error('bad');
  } catch {
    untested_n = 0;
    failed.push('untested_applicable_n_invalid');
  }
  if (untested_n > 0) failed.push('incomplete_coverage_untested');

  const runtime_tier = String(ev.runtime_tier || '').trim();
  const fixture_only = Boolean(ev.fixture_only);
  if (fixture_only || runtime_tier === 'fixture') failed.push('fixture_runtime_not_l5');
  if (runtime_tier === 'mixed') failed.push('mixed_runtime_not_l5');
  if (!Boolean(ev.runtime_claim)) failed.push('runtime_claim_false');
  if (sample_n < min_n) failed.push(`sample_n<${min_n}`);

  const set_ids = asList(ev.set_ids);
  const oracle_types = asList(ev.oracle_types);
  const dimensions = asList(ev.dimensions);
  if (!set_ids.length) missing.push('scope.set_ids');
  if (!oracle_types.length) missing.push('scope.oracle_types');
  if (!dimensions.length) missing.push('scope.dimensions');

  const gates_ok = missing.length === 0 && failed.length === 0;
  const sufficiency_extra_ok = Boolean(ev.human_review) || Boolean(ev.calibrated_rubric);
  const accuracy_eligible = gates_ok;
  const sufficiency_eligible = gates_ok && sufficiency_extra_ok;
  const failed_sufficiency =
    gates_ok && !sufficiency_extra_ok ? ['need_human_review_or_calibrated_rubric'] : [];

  return {
    schema: CLAIMS_GATE_SCHEMA,
    scope: {
      object_type: String(ev.object_type || ''),
      object_id: String(ev.object_id || ''),
      object_version: String(ev.object_version || ''),
      runtime_tier,
      plan_id: String(ev.plan_id || ''),
      set_ids,
      oracle_types,
      dimensions,
      sample_n,
      min_sample_n: min_n,
    },
    gates: {
      scope_complete: !missing.some((m) => m.startsWith('scope.')),
      has_run_evidence: has_run,
      complete_coverage: untested_n === 0,
      non_fixture_runtime: !(
        fixture_only || runtime_tier === 'fixture' || runtime_tier === 'mixed' || !runtime_tier
      ),
      runtime_claim: Boolean(ev.runtime_claim),
      sample_n_met: sample_n >= min_n,
      human_review_or_calibrated_rubric: sufficiency_extra_ok,
    },
    missing,
    failed,
    failed_sufficiency,
    accuracy_eligible,
    sufficiency_eligible,
    explicit_authorize: explicitAuthorize,
    accuracy_claim: Boolean(explicitAuthorize && accuracy_eligible),
    sufficiency_claim: Boolean(explicitAuthorize && sufficiency_eligible),
    honesty:
      'claims_gate check-only on formal report; accuracy_claim stays false unless explicitAuthorize + gates',
  };
}
