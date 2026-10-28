# core/tests/unit — known red surface (expand-green track)

Baseline after #469 (`66177bc`). PR CI stays focused; nightly collect is hard-fail,
full run informational (`not integration and not slow`).

## Snapshot (local, 2026-10-27)

| Metric | Value |
|--------|------:|
| `pytest core/tests --collect-only` | 3177 / 0 error |
| `core/tests/unit` (maxfail=40) | **40 failed**, 1204 passed, 11 skipped (~5m) |
| Estimated remaining reds | ≫40 (run stopped at maxfail) |

## Failure clusters (first 40)

| Count | Path / theme |
|------:|--------------|
| 10 | `test_harness/test_integration.py` (Harness API drift) |
| 4 | `test_harness/test_graphs/test_planning.py` |
| 3 | `test_apps/test_execution_quality_review.py` |
| 2 | hooks security_scan / architecture_health / adapter_model_injection |
| 1 each | loop defaults, langgraph duration, approval/coding gates, document converters, … |

Do **not** deselect these in nightly yet — keep informational visibility. Fix or
xfail with ticket only when expanding PR green into that package.

## Week track (PR execute expand)

Already green in PR (#468/#469):

- `test_harness/test_observability.py`
- `tool_correctness/test_code_graph.py`
- `apps/fde/test_slice_five_products.py`

**Week 1 (+):**

- `unit/test_agents/` (37 passed)
- `unit/test_utils/` (8 passed)
- `unit/test_harness/test_eval_verdict.py`
- `unit/test_harness/test_completion_receipt.py`
- `unit/test_harness/test_circuit_half_open.py`

**Week 2 (+):**

- `unit/test_api/` (100 passed) — fixed ROLE appendix collapse eating
  `build_sop_role_appendix` body; engine-only skill fixture uses rich SOP.

**Week 3 (+):**

- `unit/test_harness/test_execution/test_loop.py` (18 passed) — stale
  `max_steps` default assertion (10→20) aligned with `LoopConfig`.

**Week 4 (+):**

- `unit/test_harness/test_graphs/test_planning.py` (22 passed) —
  `PlanningState` TypedDict→dataclass (matches attribute access); parse
  `depends_on: 无` as empty deps.
- `unit/test_harness/test_integration.py` (18 passed) — restore
  HarnessIntegration facade methods mis-nested under KernelRuntime;
  `start()` schedules monitor loop as background task.

**Week 5 (+):**

- `unit/test_harness/test_feedback_loops.py` (19 passed / 10 skipped)
- `unit/test_harness/test_coordination/` (22 passed)
- `unit/test_harness/test_execution/test_langgraph_core.py` (21 passed) —
  `ExecutionTrace.duration_ms` normalizes naive/aware datetimes.

**Week 6 (+):** (CI expand only — already green)

- `unit/test_persistence/` (22)
- `unit/test_exec_drivers/` (3)
- `unit/test_mcp/` (1)
- `unit/test_docs/` (3)
- `unit/test_harness/test_convergence/` (1)
- `unit/test_harness/test_diagnostics/` (11)

**Week 7 (+):**

- `unit/test_permissions/` (2 passed) — grant/revoke HTTP moved to
  `platform/api/routers/permissions.py`; unit test targets PermissionManager.

**Week 8 (+):**

- `unit/test_tools/` (29 passed)
- `unit/test_gates/` (15 passed)
- `unit/test_document_protocol.py` (46 passed) — category assert `text`→`txt`

**Week 9 (+):** (CI expand only — already green, 180 passed / 1.4s)

- `unit/test_approval_gate.py` (23)
- `unit/test_error_translator.py` (39)
- `unit/test_delegate_tool.py` (15)
- `unit/test_file_checkpoint.py` (12)
- `unit/test_conversation_summary.py` (12)
- `unit/test_dynamic_router.py` + `test_dynamic_router_opt_in.py` (20) — default-model test hermetic (no live catalog)
- `unit/test_architecture_profile.py` (11)
- `unit/test_core_modules.py` + `test_core_module_deps.py` (4)
- `unit/test_execution_modules.py` + `test_execution_snapshot_facade.py` (12)
- `unit/test_data_recipes.py` (12)
- `unit/test_claude_md_enforcement.py` + `test_claude_md_pre_reasoning_infer.py` (5)
- `unit/test_guard_regression.py` + `test_graph_incremental_paths.py` (12)
- `unit/test_harness/test_ontology_engine/` (3)

**Week 10 (+):** (CI expand only — already green, 187 passed / ~12s)

- `unit/test_autosmoke_dedup_and_callback.py` (1)
- `unit/test_governance_preview_permission_details.py` (1)
- `unit/test_harness/test_auto_done_finalize.py` (11)
- `unit/test_harness/test_backpressure_protocol.py` (5)
- `unit/test_harness/test_canary_escalation.py` + `test_canary_recommendation.py` (8)
- `unit/test_harness/test_cc_hooks_bridge.py` (16)
- `unit/test_harness/test_code_review_gold.py` (8)
- `unit/test_harness/test_coding_deliverable_veto.py` (25)
- `unit/test_harness/test_coding_intensity.py` + `test_coding_stage_defaults.py` (28)
- `unit/test_harness/test_context_*` (compaction / engine / shaping) (7)
- `unit/test_harness/test_coverage_gate.py` (2)
- `unit/test_harness/test_done_verify.py` (32)
- `unit/test_harness/test_evaluation_policy_{merge,parse}.py` (2)
- `unit/test_harness/test_event_bus_dlq_filter.py` (3)
- `unit/test_harness/test_evidence_{diff,envelope}.py` (15)
- `unit/test_harness/test_executable_skill_policy_gate.py` (1)
- `unit/test_harness/test_execute_session.py` (22)

**Not yet (still red or partial):**

- Remaining unit reds: scattered (hooks / apps / skills / adapter injection /
  `test_management` status drift / oversized AGENT.md / approval_expiry hang /
  architecture_health / chaos_fault_injection / …);
  ~25 fail / 1013 pass on maxfail=25 sample after week-4 greens ignored.

## Process

1. Pick a green package → add to `.github/workflows/ci.yml` execute list (+ COLLECT if new).
2. Prefer fixing ≤3 cheap fails to unlock a package over mass deselect.
3. Re-run `pytest core/tests/unit --maxfail=40` periodically; update this table.
