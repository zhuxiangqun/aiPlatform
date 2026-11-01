# DIAGNOSIS_V1 fixtures — core + adversarial (desensitized)

- **core count**: 10 (`dx.s1.*` / `dx.s2.*`)
- **adversarial count**: 6 (`dx.adv.*`) — C3.5 holdout
- **provenance**: `desensitized_local_export` — local five-products / Pi slice / evaluation rehearsal; **not** production customer data
- **packaged_at**: 2026-11-01T11:00:00+00:00 (core); adversarial 2026-11-02
- **rules**: `accuracy_claim=false`; report **core** and **adversarial** subsets separately; never market core Top-1 as diagnosis accuracy

## Core

| case_id | scenario | gold / expect |
|---|---|---|
| `dx.s1.tool_timeout` | run_failure | timeout |
| `dx.s1.tool_wrong_args` | run_failure | tool_error |
| `dx.s1.model_route_cheap` | run_failure | wrong_model_route |
| `dx.s1.policy_tool_deny` | run_failure | policy_deny |
| `dx.s1.context_trunc` | run_failure | context_missing |
| `dx.s1.no_trace` | run_failure | insufficient_evidence → unknown |
| `dx.s1.stale_kb` | run_failure | data_stale → stale |
| `dx.s2.prompt_edit` | version_regression | prompt_regression |
| `dx.s2.eval_gate_fail` | version_regression | eval_score_drop |
| `dx.s2.no_baseline` | version_regression | insufficient_evidence → unknown |

## Adversarial (C3.5)

| case_id | trap | gold |
|---|---|---|
| `dx.adv.tool_masks_route` | tool 4xx distractor | wrong_model_route |
| `dx.adv.gate_masks_onto` | gate drop distractor | ontology_coverage_gap |
| `dx.adv.stale_without_flag` | stale semantics, freshness=fresh | data_stale |
| `dx.adv.sparse_hard_guess` | almost no evidence | insufficient_evidence |
| `dx.adv.timeout_masks_context` | timeout distractor | context_missing |
| `dx.adv.eval_masks_retrieval` | eval delta distractor | retrieval_miss |

Metrics: `fixture_metrics(subset="core"|"adversarial"|"all")`.

Each directory: `evidence.json`, `expected.json`, `README.md`.
