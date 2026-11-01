# DIAGNOSIS_V1 C1 — real evidence fixtures (desensitized)

- **count**: 10
- **provenance**: `desensitized_local_export` — local five-products / Pi slice / evaluation rehearsal; **not** production customer data
- **packaged_at**: 2026-11-01T11:00:00+00:00
- **rules**: do not claim diagnosis accuracy until these are used by the C1 engine; keep `accuracy_claim=false`

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

Each directory: `evidence.json`, `expected.json`, `README.md`.
