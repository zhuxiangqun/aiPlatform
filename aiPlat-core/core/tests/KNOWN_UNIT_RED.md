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

- `unit/test_autosmoke_dedup_and_callback.py` (1) — stub `_default_agent_model` (CI catalog empty)
- `unit/test_governance_preview_permission_details.py` (1)
- `unit/test_harness/test_auto_done_finalize.py` (11)
- `unit/test_harness/test_backpressure_protocol.py` (5)
- `unit/test_harness/test_canary_escalation.py` + `test_canary_recommendation.py` (8)
- `unit/test_harness/test_cc_hooks_bridge.py` (16)
- `unit/test_harness/test_code_review_gold.py` (8)
- `unit/test_harness/test_coding_deliverable_veto.py` (25) — hermetic `best_model_for_purpose`
- `unit/test_harness/test_coding_intensity.py` + `test_coding_stage_defaults.py` (28)
- `unit/test_harness/test_context_*` (compaction / engine / shaping) (7)
- `unit/test_harness/test_coverage_gate.py` (2)
- `unit/test_harness/test_done_verify.py` (32)
- `unit/test_harness/test_evaluation_policy_{merge,parse}.py` (2)
- `unit/test_harness/test_event_bus_dlq_filter.py` (3)
- `unit/test_harness/test_evidence_{diff,envelope}.py` (15)
- `unit/test_harness/test_executable_skill_policy_gate.py` (1)
- `unit/test_harness/test_execute_session.py` (22)

**Week 11 (+):** (CI expand only — already green, 184 passed / ~3s)

- `unit/test_harness/test_adapter_model_injection.py` (2)
- `unit/test_harness/test_app_page_skill_inject.py` (10)
- `unit/test_harness/test_auto_eval_prompt_includes_browser_evidence.py` (1)
- `unit/test_harness/test_evaluator_workbench.py` (1)
- `unit/test_harness/test_execution_decision_e3.py` (7)
- `unit/test_harness/test_graphs/` (22; includes planning already unlocked)
- `unit/test_harness/test_factory_mode_f2b.py` (5)
- `unit/test_harness/test_openworker_governance_p1.py` (18)
- `unit/test_harness/test_pipeline_run_events.py` + `test_pipeline_context_clean.py` (11)
- `unit/test_harness/test_prd_gate_loader.py` (5)
- `unit/test_harness/test_review_known_defects.py` (15)
- `unit/test_harness/test_self_correct_skip_skill_error.py` (4)
- `unit/test_harness/test_skill_delivery_finalize.py` (19)
- `unit/test_harness/test_stage_handoff.py` (15)
- `unit/test_harness/test_post_llm_no_nested_hang.py` (7)
- `unit/test_sandbox.py` + `test_skills_base.py` (13)
- `unit/test_tool_error_enrichment.py` (12)
- `unit/test_stage_change_contract.py` (4)
- `unit/test_skill_routing_triggers.py` + `test_skill_invocation_mode.py` (13)


**Week 12 (+):** (CI expand only — green after dropping CI-env deps; ~470 local; `\` continuations fixed)

- 69 harness/unit singles: factory/openworker/org metrics/os_sandbox, gates,
  run_state/*, team_*, skill_*, pipeline_engine p0/p1b/eval, team_planner,
  physical_merge_gates, stdio_kernel, writing_profile, …
- Skipped reds: production_depth_gaps / stage_reflection / true_test_runtime /
  l2_import_context / llm_syscall_store / model_injection_updates_loop / output_style /
  media_skill_handlers_vocab (CI no ffmpeg) / stage_runner_preferred_language (CI no model) /
  team_wave4 (push dry-run env)


**Week 13 (+):** (CI expand only — 83 local after dropping event-loop-order flakes)

- dropped `production_depth_gaps` / `stage_reflection` (event-loop order flake on CI)
- builder/cross_role/four_agent e2e, immune_memory, infra_llm_adapter_response_format
- job_scheduler_delivery_events, kb_qa_retrieve, knowledge_db_utils/retriever
- lint_change_contract / conflict_pair / engine_skills_script
- policy_approval_integration, rl_trainer
- Skipped slow (~100s) config_registry / permissions_catalog / routing_explain


**Week 14 (+):** (CI expand only — 120 passed local batch / ~5m)

- routing funnel/metrics/replay APIs + skill conflicts/metrics/spec/lint_scan/stable_schema
- run_contract_ok, semi_auto_agents, skill_config/fix_proposals/lint_*, skillopt_*,
  skills_guard(+wiring), smoke_e2e_dispatch, tool_drift/search, value_calculator
- Still red (omit): sft_rl_integration / trend_detector / v27_modules
- Still skip slow singles: config_registry_* / permissions_catalog / routing_explain /
  apply_lint_fix_workspace / coding_policy_profile_injection


**Week 15 (+):** (CI expand only — 450 passed local batch / ~4m after dropping order flakes)

- langgraph_resume + previously-skipped ~100s API singles (apply_lint / coding_policy /
  config_registry_* / permissions_catalog / routing_explain)
- digital_human greens (omit voice_pipeline_fixes)
- knowledge greens (~70 files; omit factory_confirm / fde_phase1* / phase3 / org_* reds /
  security_review_phase_b / types; drop batch flakes clarify_dialog /
  extraction_parse_filter / ontology_version_sidecar_layout)
- apps greens (~20 files; omit agent_bound_skill_approval / code_generation_input /
  execution_quality_review / skill_autofill_parse; drop batch flake agent_dedupe)


**Week 16 (+):** (CI expand only — 143 passed local batch / ~1.5s)

- memory greens (base/ide_*/long_term/session_wiki/short_term/team_brain; omit hang session.py)
- skills greens (autoreview/discovery/evolution/skillmanager_*/trigger/version/…)
- Omit reds: hooks, observability_control, management status/uninstall, executor_fork,
  skill_installer, skill_rollback_semantics, skill_timeout_metadata
- Drop batch flake: test_executor_pytest_assemble (event-loop order)


**Week 17 (+):** (CI expand only — constitution 12 passed / ~0.2s)

- `core/tests/constitution` (core_genericity + engine_agnostic)
- Integration probe deferred (many hang / no hermetic summary under 60s)
- Remaining unit surface mostly known reds / 1-fail cheap-fix candidates


**Week 18 (+):** (CI expand + cheap fix — 68 passed / 3 skipped / ~27s)

- tool_correctness greens: batch / capability_graph / capability_manifest / graph /
  guard_ast / guard_frontend / method_verify (omit eval red; arch_guard/caller_verify/
  phase_check/tool_invariants hang or incomplete under timeout)
- Fix fork-mode `model_name` NameError in `apps/skills/executor.py`; unlock
  `test_executor_fork` (test stubs adapter creation)


**Week 19 (+):** (cheap fix + CI expand — 8 passed)

- Add `timeout: 600` to `engine/skills/code_generation/SKILL.md` (covers nested
  code_gen 420s + slack); unlock `test_skill_timeout_metadata`
- Remaining unit surface still red / tool_correctness hang under long runs

**Week 20 (+):** (CI expand + isolation fix — 22 passed)

- Re-admit `production_depth_gaps` / `stage_reflection` / `agent_dedupe` /
  `extraction_parse_filter`: replace `get_event_loop().run_until_complete` with
  `@pytest.mark.asyncio` (batch event-loop order flake).
- `test_org_h_wave_approvals`: inbox query `kind=arbitration`; ActionStore /
  PendingExtractionStore default via `default_action_db_path()` + pytest pin
  `AIPLAT_ACTION_DB_PATH` / `AIPLAT_PROFILE_DIR`.
- `test_stage_runner_preferred_language` (1; stub `best_model_for_purpose`)
- Also: `syscalls/__init__.py` move `import logging` out of docstring (react_loop
  NameError swallow); conftest clears `GIT_DIR`/`GIT_WORK_TREE` between tests.

**Week 21 (+):** (CI expand + clarify stub fix — hermetic greens only)

- `test_sft_rl_integration` (8; previously listed red, now green)
- `test_autoreview_diff_timeout` (6)
- `test_execution/test_tool_calling` (11)
- `test_clarify_dialog` (5; stub `best_model_for_purpose` via CoreFacade path) +
  `test_ontology_version_sidecar_layout` (3; `@pytest.mark.asyncio`)
- `test_apps/test_agent_bound_skill_approval` (7)
- Withdrawn after CI red: `media_skill_handlers_vocab` (ffmpeg_not_found on
  runners) / `team_wave4` (push dry-run flake under full COLLECT)

**Week 22 (+):** (cheap expectation sync + asyncio — 46 passed / flake ×2)

- `test_types` (21; KnowledgeType count 8→9 + WEB)
- `test_security_review_phase_b` (10; stages 4→5 + hitl on report)
- `test_skill_autofill_parse` (4; auto invocation_mode for trigger pad)
- `test_test_executor_pytest_assemble` (6; `@pytest.mark.asyncio`)
- `test_skill_installer` (5)

**Week 23 (+):** (cheap expectation sync — 39 passed / flake ×2)

- `test_llm_syscall_store` (3; AST-guard ModelManager + `_record_cached_model_outcome`)
- `test_agent_status_canonical` (1; ready + runtime_state start/stop)
- `test_voice_pipeline_fixes` (25; factory handoff CTA after LLM)
- `test_factory_confirm_proposal` (2; entity name from extraction row)
- `test_fde_phase1_audit` (8; stub KPI keys = trace_anomalies/training)

**Week 24 (+):** (product fix + cheap sync — 5 passed / flake ×2)

- `llm_env.py`: import `logging` on base_url except path (NameError)
- `PackageInfo`: required fields before defaults (dataclass TypeError)
- `test_model_injection_updates_loop` (1; stub `create_selected_adapter`)
- `test_package_manager_uninstall` (1)
- `test_org_gap_draft` (3; preview must not write live domain YAML)

**Week 25 (+):** (seed + cheap sync — 39 passed)

- Seed `workspace_seeds/skills/output_style_adhd/SKILL.md` (style hash)
- `test_production_readiness` (13; nightly steps 12→14 + handlers)
- `test_trend_detector` (15; await async `_record_classification`)
- `test_output_style` (6)
- `test_slice_fault_injection` (5)

**Week 26 (+):** (typing + cheap sync — 9 passed; media withdraw)

- `kanban_engine.py`: `from __future__ import annotations` (3.9 `|` TypeError)
- `test_pipeline_engine_core` (9; stub `best_model_for_purpose`)
- Withdrawn after CI red: `test_true_test_runtime` (ffmpeg_not_found on runners)

**Week 27 (+):** (seed + hermetic embed — 10 passed)

- Domain pack manifests (+ alert_triage ontology.yaml) so S3 catalog lists packs
- `test_knowledge_embedder` (7; AIPLAT_EMBED_BACKEND=hash)
- `test_org_s_wave` (3)

**Week 28 (+):** (stub sync + COLLECT parity — 24 passed)

- `test_org_v_wave_approve` (5; `_Store` + core_facade patches for
  `update_ontology_proposal_impact` / status)
- `test_l2_import_context` (4; `best_model_for_purpose(..., messages=)`)
- COLLECT parity: `test_slice_five_products` (15; already on execute)

**Week 29 (+):** (seed restore + stub sync — 13 passed)

- Restore `workspace_seeds/workflow_templates/fde_delivery_v1/workflow.yaml`
- `test_fde_phase1b_delivery` (5) + `test_fde_phase3_builder_link` (3)
- `test_chaos_fault_injection` (3; healing strategies live in pipeline_healing)
- `test_skill_rollback_semantics` (2; SkillConfig.effects for §5.19)

**Week 30 (+):** (fixture + ActionRegistry v3 sync — 46 passed)

- `test_code_generation_input_and_substance` (9; locked-lang fixture passes
  frontend_module_incomplete + auth-todo gates)
- `test_v27_modules` (37; ActionRegistry → AsyncActionRegistry / builtin_* ids)

**Week 31 (+):** (permission grant + tool-dispatch guard — 5 passed)

- `test_observability_control` (1; grant EXECUTE + model `_config`; facade
  guards `result is None` after tool exception)
- Re-admit `test_team_wave4` (4; was withdrawn for push dry-run flake)

**Not yet (still red or partial):**

- Remaining unit reds: scattered (hooks / apps / skills / adapter injection /
  oversized AGENT.md / approval_expiry hang / architecture_health /
  chaos_fault_injection / observability_control policy early-pause / …);
  ~25 fail / 1013 pass on maxfail=25 sample after week-4 greens ignored.

## Process

1. Pick a green package → add to `.github/workflows/ci.yml` execute list (+ COLLECT if new).
2. Prefer fixing ≤3 cheap fails to unlock a package over mass deselect.
3. Re-run `pytest core/tests/unit --maxfail=40` periodically; update this table.
