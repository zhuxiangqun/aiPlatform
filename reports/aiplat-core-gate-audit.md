# aiPlat-core 绕过路径审计（启发式）

- 扫描文件：`/sessions/69df99acf22671cacf117ebb/workspace/aiPlat-core/core/server.py`
- 范围：仅枚举 `@api_router.post/put/delete`，并用字符串匹配判断是否调用 `_rbac_guard` / `add_audit_log` 等。
- 目的：快速发现“明显未接门控/审计”的写操作端点，作为 review 与回归 guard。

## 端点清单（写操作）

| method | path | function | rbac_guard | audit_log | changeset | approval |
|---|---|---|---:|---:|---:|---:|
| POST | `/adapters` | `create_adapter` | ❌ | ❌ | ✅ | ❌ |
| DELETE | `/adapters/{adapter_id}` | `delete_adapter` | ❌ | ❌ | ✅ | ❌ |
| PUT | `/adapters/{adapter_id}` | `update_adapter` | ❌ | ❌ | ✅ | ❌ |
| POST | `/adapters/{adapter_id}/disable` | `disable_adapter` | ❌ | ❌ | ✅ | ❌ |
| POST | `/adapters/{adapter_id}/enable` | `enable_adapter` | ❌ | ❌ | ✅ | ❌ |
| POST | `/adapters/{adapter_id}/models` | `add_adapter_model` | ❌ | ❌ | ✅ | ❌ |
| DELETE | `/adapters/{adapter_id}/models/{model_name}` | `delete_adapter_model` | ❌ | ❌ | ✅ | ❌ |
| PUT | `/adapters/{adapter_id}/models/{model_name}` | `update_adapter_model` | ❌ | ❌ | ❌ | ❌ |
| POST | `/adapters/{adapter_id}/test` | `test_adapter` | ❌ | ❌ | ❌ | ❌ |
| POST | `/agents` | `create_agent` | ❌ | ❌ | ❌ | ❌ |
| POST | `/agents/executions/{execution_id}/resume` | `resume_agent_execution` | ❌ | ❌ | ❌ | ✅ |
| DELETE | `/agents/{agent_id}` | `delete_agent` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/agents/{agent_id}` | `update_agent` | ❌ | ❌ | ❌ | ❌ |
| POST | `/agents/{agent_id}/execute` | `execute_agent` | ✅ | ❌ | ❌ | ✅ |
| POST | `/agents/{agent_id}/skills` | `bind_agent_skills` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/agents/{agent_id}/skills/{skill_id}` | `unbind_agent_skill` | ❌ | ❌ | ❌ | ❌ |
| POST | `/agents/{agent_id}/start` | `start_agent` | ❌ | ❌ | ❌ | ❌ |
| POST | `/agents/{agent_id}/stop` | `stop_agent` | ❌ | ❌ | ❌ | ❌ |
| POST | `/agents/{agent_id}/tools` | `bind_agent_tools` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/agents/{agent_id}/tools/{tool_id}` | `unbind_agent_tool` | ❌ | ❌ | ❌ | ❌ |
| POST | `/agents/{agent_id}/versions` | `create_agent_version` | ❌ | ❌ | ❌ | ❌ |
| POST | `/agents/{agent_id}/versions/{version}/rollback` | `rollback_agent_version` | ❌ | ❌ | ❌ | ❌ |
| POST | `/approvals/{request_id}/approve` | `approve_request` | ✅ | ✅ | ❌ | ✅ |
| POST | `/approvals/{request_id}/reject` | `reject_request` | ✅ | ✅ | ❌ | ✅ |
| POST | `/approvals/{request_id}/replay` | `replay_approval` | ❌ | ❌ | ❌ | ✅ |
| POST | `/autosmoke/run` | `run_autosmoke` | ❌ | ❌ | ❌ | ❌ |
| POST | `/change-control/changes/{change_id}/autosmoke` | `autosmoke_change_control` | ❌ | ❌ | ✅ | ❌ |
| POST | `/diagnostics/e2e/smoke` | `run_e2e_smoke` | ❌ | ❌ | ❌ | ❌ |
| POST | `/diagnostics/prompt/assemble` | `diagnostics_prompt_assemble` | ❌ | ❌ | ❌ | ❌ |
| POST | `/diagnostics/repo/changeset/preview` | `diagnostics_repo_changeset_preview` | ❌ | ❌ | ❌ | ❌ |
| POST | `/diagnostics/repo/changeset/record` | `diagnostics_repo_changeset_record` | ❌ | ❌ | ✅ | ✅ |
| POST | `/diagnostics/repo/git/branch` | `diagnostics_repo_git_branch` | ❌ | ❌ | ✅ | ✅ |
| POST | `/diagnostics/repo/git/commit` | `diagnostics_repo_git_commit` | ❌ | ❌ | ✅ | ✅ |
| POST | `/diagnostics/repo/staged/preview` | `diagnostics_repo_staged_preview` | ❌ | ❌ | ❌ | ❌ |
| POST | `/diagnostics/repo/tests/run` | `diagnostics_repo_tests_run` | ❌ | ❌ | ✅ | ❌ |
| DELETE | `/gateway/dlq/{dlq_id}` | `delete_gateway_delivery_dlq` | ❌ | ❌ | ❌ | ❌ |
| POST | `/gateway/dlq/{dlq_id}/retry` | `retry_gateway_delivery_dlq` | ❌ | ❌ | ❌ | ❌ |
| POST | `/gateway/execute` | `gateway_execute` | ✅ | ✅ | ❌ | ❌ |
| DELETE | `/gateway/pairings` | `delete_gateway_pairing` | ❌ | ❌ | ❌ | ❌ |
| POST | `/gateway/pairings` | `upsert_gateway_pairing` | ❌ | ❌ | ❌ | ❌ |
| POST | `/gateway/slack/command` | `gateway_slack_command` | ❌ | ❌ | ❌ | ❌ |
| POST | `/gateway/slack/events` | `gateway_slack_events` | ❌ | ❌ | ❌ | ❌ |
| POST | `/gateway/tokens` | `create_gateway_token` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/gateway/tokens/{token_id}` | `delete_gateway_token` | ❌ | ❌ | ❌ | ❌ |
| POST | `/gateway/webhook/message` | `gateway_webhook_message` | ❌ | ❌ | ❌ | ❌ |
| POST | `/graphs/compiled/react/execute` | `execute_compiled_react_graph` | ❌ | ❌ | ❌ | ❌ |
| POST | `/graphs/runs/{run_id}/resume` | `resume_graph_run` | ❌ | ❌ | ❌ | ❌ |
| POST | `/graphs/runs/{run_id}/resume/execute` | `resume_and_execute_compiled_graph` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/harness/config` | `update_harness_config` | ❌ | ❌ | ❌ | ❌ |
| POST | `/harness/coordinators` | `create_coordinator` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/harness/coordinators/{coordinator_id}` | `delete_coordinator` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/harness/coordinators/{coordinator_id}` | `update_coordinator` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/harness/feedback/config` | `update_feedback_config` | ❌ | ❌ | ❌ | ❌ |
| POST | `/harness/hooks` | `create_hook` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/harness/hooks/{hook_id}` | `delete_hook` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/harness/hooks/{hook_id}` | `update_hook` | ❌ | ❌ | ❌ | ❌ |
| POST | `/jobs` | `create_job` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/jobs/dlq/{dlq_id}` | `delete_job_delivery_dlq` | ❌ | ❌ | ❌ | ❌ |
| POST | `/jobs/dlq/{dlq_id}/retry` | `retry_job_delivery_dlq` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/jobs/{job_id}` | `delete_job` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/jobs/{job_id}` | `update_job` | ❌ | ❌ | ❌ | ❌ |
| POST | `/jobs/{job_id}/disable` | `disable_job` | ❌ | ❌ | ❌ | ❌ |
| POST | `/jobs/{job_id}/enable` | `enable_job` | ❌ | ❌ | ❌ | ❌ |
| POST | `/jobs/{job_id}/run` | `run_job_now` | ❌ | ❌ | ❌ | ❌ |
| POST | `/knowledge/collections` | `create_collection` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/knowledge/collections/{collection_id}` | `delete_collection` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/knowledge/collections/{collection_id}` | `update_collection` | ❌ | ❌ | ❌ | ❌ |
| POST | `/knowledge/collections/{collection_id}/reindex` | `reindex_collection` | ❌ | ❌ | ❌ | ❌ |
| POST | `/knowledge/documents` | `create_document` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/knowledge/documents/{document_id}` | `delete_document` | ❌ | ❌ | ❌ | ❌ |
| POST | `/knowledge/search` | `search_knowledge` | ❌ | ❌ | ❌ | ❌ |
| POST | `/learning/approvals/cleanup-rollback-approvals` | `api_cleanup_rollback_approvals` | ❌ | ❌ | ❌ | ❌ |
| POST | `/learning/artifacts/{artifact_id}/status` | `set_learning_artifact_status` | ❌ | ❌ | ❌ | ❌ |
| POST | `/learning/auto-rollback/regression` | `api_auto_rollback_regression` | ❌ | ❌ | ❌ | ✅ |
| POST | `/learning/autocapture` | `autocapture_learning_suggestion` | ❌ | ❌ | ❌ | ❌ |
| POST | `/learning/autocapture/to_prompt_revision` | `autocapture_to_prompt_revision` | ❌ | ❌ | ❌ | ❌ |
| POST | `/learning/autocapture/to_skill_evolution` | `autocapture_to_skill_evolution` | ❌ | ❌ | ❌ | ❌ |
| POST | `/learning/releases/expire` | `expire_releases` | ❌ | ❌ | ❌ | ❌ |
| POST | `/learning/releases/{candidate_id}/metrics/snapshots` | `add_release_metric_snapshot` | ❌ | ❌ | ❌ | ❌ |
| POST | `/learning/releases/{candidate_id}/publish` | `publish_release_candidate` | ❌ | ❌ | ✅ | ✅ |
| POST | `/learning/releases/{candidate_id}/rollback` | `rollback_release_candidate` | ❌ | ❌ | ✅ | ✅ |
| DELETE | `/learning/rollouts` | `delete_release_rollout` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/learning/rollouts` | `upsert_release_rollout` | ❌ | ❌ | ❌ | ❌ |
| POST | `/mcp/servers/{server_name}/disable` | `disable_mcp_server` | ❌ | ❌ | ❌ | ❌ |
| POST | `/mcp/servers/{server_name}/enable` | `enable_mcp_server` | ❌ | ❌ | ✅ | ❌ |
| POST | `/memory/cleanup` | `cleanup_memory` | ❌ | ❌ | ❌ | ❌ |
| POST | `/memory/import` | `import_memory` | ❌ | ❌ | ❌ | ❌ |
| POST | `/memory/longterm` | `add_long_term_memory` | ❌ | ❌ | ❌ | ❌ |
| POST | `/memory/longterm/search` | `search_long_term_memory` | ❌ | ❌ | ❌ | ❌ |
| POST | `/memory/pins` | `pin_memory` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/memory/pins/{message_id}` | `unpin_memory` | ❌ | ❌ | ❌ | ❌ |
| POST | `/memory/search` | `search_memory` | ❌ | ❌ | ❌ | ❌ |
| POST | `/memory/sessions` | `create_session` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/memory/sessions/{session_id}` | `delete_session` | ❌ | ❌ | ❌ | ❌ |
| POST | `/memory/sessions/{session_id}/messages` | `add_message` | ❌ | ❌ | ❌ | ❌ |
| POST | `/onboarding/autosmoke` | `set_autosmoke_config` | ❌ | ❌ | ✅ | ✅ |
| POST | `/onboarding/context-config` | `set_context_config` | ❌ | ❌ | ✅ | ✅ |
| POST | `/onboarding/default-llm` | `set_default_llm` | ❌ | ❌ | ✅ | ✅ |
| POST | `/onboarding/evidence/runs` | `create_onboarding_evidence` | ❌ | ✅ | ❌ | ✅ |
| POST | `/onboarding/exec-backend` | `set_exec_backend` | ❌ | ❌ | ✅ | ✅ |
| POST | `/onboarding/init-tenant` | `init_default_tenant` | ❌ | ❌ | ✅ | ✅ |
| POST | `/onboarding/secrets/migrate` | `migrate_secrets` | ❌ | ❌ | ✅ | ✅ |
| POST | `/onboarding/strong-gate` | `set_strong_gate` | ❌ | ❌ | ✅ | ✅ |
| POST | `/onboarding/trusted-skill-keys` | `set_trusted_skill_keys` | ❌ | ❌ | ✅ | ✅ |
| POST | `/ops/prune` | `ops_prune` | ✅ | ✅ | ❌ | ❌ |
| POST | `/packages/{pkg_name}/install` | `install_package` | ❌ | ❌ | ✅ | ✅ |
| POST | `/packages/{pkg_name}/publish` | `publish_package` | ❌ | ❌ | ✅ | ✅ |
| POST | `/packages/{pkg_name}/uninstall` | `uninstall_package` | ❌ | ❌ | ✅ | ✅ |
| POST | `/permissions/grant` | `grant_permission` | ❌ | ❌ | ❌ | ❌ |
| POST | `/permissions/revoke` | `revoke_permission` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/plugins` | `upsert_plugin` | ✅ | ✅ | ❌ | ❌ |
| POST | `/plugins/{plugin_id}/enable` | `set_plugin_enabled` | ✅ | ✅ | ❌ | ❌ |
| POST | `/plugins/{plugin_id}/rollback` | `rollback_plugin` | ✅ | ✅ | ❌ | ❌ |
| POST | `/plugins/{plugin_id}/run` | `run_plugin` | ✅ | ✅ | ❌ | ✅ |
| POST | `/policies/evaluate` | `evaluate_policy_debug` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/policies/tenants/{tenant_id}` | `upsert_tenant_policy` | ✅ | ✅ | ✅ | ❌ |
| PUT | `/policy/snapshot` | `put_policy_snapshot` | ✅ | ❌ | ❌ | ❌ |
| POST | `/prompts` | `upsert_prompt_template` | ❌ | ❌ | ✅ | ✅ |
| DELETE | `/prompts/{template_id}` | `delete_prompt_template` | ❌ | ❌ | ✅ | ✅ |
| POST | `/prompts/{template_id}/release` | `set_prompt_template_release` | ❌ | ❌ | ✅ | ✅ |
| POST | `/prompts/{template_id}/release/rollback` | `rollback_prompt_template_release` | ❌ | ❌ | ✅ | ✅ |
| POST | `/prompts/{template_id}/rollback` | `rollback_prompt_template` | ❌ | ❌ | ✅ | ✅ |
| PUT | `/quota/snapshot` | `put_quota_snapshot` | ✅ | ✅ | ❌ | ❌ |
| POST | `/runs/{run_id}/cancel` | `cancel_run` | ❌ | ❌ | ❌ | ❌ |
| POST | `/runs/{run_id}/retry` | `retry_run` | ❌ | ❌ | ❌ | ❌ |
| POST | `/runs/{run_id}/undo` | `undo_run` | ❌ | ❌ | ❌ | ❌ |
| POST | `/runs/{run_id}/wait` | `wait_run` | ❌ | ❌ | ❌ | ✅ |
| POST | `/skill-packs` | `create_skill_pack` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/skill-packs/{pack_id}` | `delete_skill_pack` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/skill-packs/{pack_id}` | `update_skill_pack` | ❌ | ❌ | ❌ | ❌ |
| POST | `/skill-packs/{pack_id}/install` | `install_skill_pack` | ❌ | ❌ | ✅ | ❌ |
| POST | `/skill-packs/{pack_id}/publish` | `publish_skill_pack` | ❌ | ❌ | ✅ | ❌ |
| POST | `/skills` | `create_skill` | ❌ | ❌ | ✅ | ❌ |
| DELETE | `/skills/{skill_id}` | `delete_skill` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/skills/{skill_id}` | `update_skill` | ❌ | ❌ | ✅ | ❌ |
| POST | `/skills/{skill_id}/disable` | `disable_skill` | ❌ | ❌ | ❌ | ❌ |
| POST | `/skills/{skill_id}/enable` | `enable_skill` | ❌ | ❌ | ✅ | ❌ |
| POST | `/skills/{skill_id}/evolution` | `trigger_skill_evolution` | ❌ | ❌ | ❌ | ❌ |
| POST | `/skills/{skill_id}/execute` | `execute_skill` | ✅ | ❌ | ❌ | ❌ |
| POST | `/skills/{skill_id}/restore` | `restore_skill` | ❌ | ❌ | ❌ | ❌ |
| POST | `/skills/{skill_id}/test-trigger` | `test_skill_trigger` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/skills/{skill_id}/trigger-conditions` | `update_skill_trigger_conditions` | ❌ | ❌ | ❌ | ❌ |
| POST | `/skills/{skill_id}/versions/{version}/rollback` | `rollback_skill_version` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/tools/{tool_name}` | `update_tool_config` | ❌ | ❌ | ❌ | ❌ |
| POST | `/tools/{tool_name}/execute` | `execute_tool` | ✅ | ❌ | ❌ | ❌ |
| POST | `/workspace/agents` | `create_workspace_agent` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/workspace/agents/{agent_id}` | `delete_workspace_agent` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/workspace/agents/{agent_id}` | `update_workspace_agent` | ❌ | ❌ | ❌ | ❌ |
| POST | `/workspace/agents/{agent_id}/execute` | `execute_workspace_agent` | ✅ | ❌ | ❌ | ❌ |
| POST | `/workspace/agents/{agent_id}/skills` | `bind_workspace_agent_skills` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/workspace/agents/{agent_id}/skills/{skill_id}` | `unbind_workspace_agent_skill` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/workspace/agents/{agent_id}/sop` | `update_workspace_agent_sop` | ❌ | ❌ | ❌ | ❌ |
| POST | `/workspace/agents/{agent_id}/start` | `start_workspace_agent` | ❌ | ❌ | ❌ | ❌ |
| POST | `/workspace/agents/{agent_id}/stop` | `stop_workspace_agent` | ❌ | ❌ | ❌ | ❌ |
| POST | `/workspace/agents/{agent_id}/tools` | `bind_workspace_agent_tools` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/workspace/agents/{agent_id}/tools/{tool_id}` | `unbind_workspace_agent_tool` | ❌ | ❌ | ❌ | ❌ |
| POST | `/workspace/agents/{agent_id}/versions` | `create_workspace_agent_version` | ❌ | ❌ | ❌ | ❌ |
| POST | `/workspace/agents/{agent_id}/versions/{version}/rollback` | `rollback_workspace_agent_version` | ❌ | ❌ | ❌ | ❌ |
| POST | `/workspace/mcp/servers` | `upsert_workspace_mcp_server` | ❌ | ❌ | ❌ | ❌ |
| PUT | `/workspace/mcp/servers/{server_name}` | `update_workspace_mcp_server` | ❌ | ❌ | ❌ | ❌ |
| POST | `/workspace/mcp/servers/{server_name}/disable` | `disable_workspace_mcp_server` | ❌ | ❌ | ❌ | ❌ |
| POST | `/workspace/mcp/servers/{server_name}/enable` | `enable_workspace_mcp_server` | ❌ | ❌ | ✅ | ❌ |
| POST | `/workspace/packages` | `create_workspace_package` | ❌ | ❌ | ❌ | ❌ |
| DELETE | `/workspace/packages/{pkg_name}` | `delete_workspace_package` | ❌ | ❌ | ❌ | ❌ |
| POST | `/workspace/packages/{pkg_name}/install` | `install_workspace_package` | ❌ | ❌ | ❌ | ❌ |
| POST | `/workspace/packages/{pkg_name}/uninstall` | `uninstall_workspace_package` | ❌ | ❌ | ❌ | ❌ |
| POST | `/workspace/skills` | `create_workspace_skill` | ✅ | ✅ | ✅ | ❌ |
| POST | `/workspace/skills/installer/install` | `workspace_skills_installer_install` | ✅ | ✅ | ❌ | ✅ |
| POST | `/workspace/skills/installer/plan` | `workspace_skills_installer_plan` | ✅ | ❌ | ❌ | ❌ |
| POST | `/workspace/skills/installer/resolve-head` | `workspace_skills_installer_resolve_head` | ✅ | ✅ | ❌ | ❌ |
| POST | `/workspace/skills/installer/uninstall/{skill_id}` | `workspace_skills_installer_uninstall` | ✅ | ✅ | ❌ | ❌ |
| POST | `/workspace/skills/installer/update/{skill_id}` | `workspace_skills_installer_update` | ✅ | ✅ | ❌ | ❌ |
| DELETE | `/workspace/skills/{skill_id}` | `delete_workspace_skill` | ✅ | ✅ | ❌ | ❌ |
| PUT | `/workspace/skills/{skill_id}` | `update_workspace_skill` | ✅ | ✅ | ✅ | ❌ |
| POST | `/workspace/skills/{skill_id}/disable` | `disable_workspace_skill` | ✅ | ✅ | ❌ | ❌ |
| POST | `/workspace/skills/{skill_id}/enable` | `enable_workspace_skill` | ✅ | ✅ | ✅ | ✅ |
| POST | `/workspace/skills/{skill_id}/execute` | `execute_workspace_skill` | ✅ | ❌ | ✅ | ✅ |
| POST | `/workspace/skills/{skill_id}/restore` | `restore_workspace_skill` | ✅ | ✅ | ❌ | ❌ |
| POST | `/workspace/skills/{skill_id}/versions/{version}/rollback` | `rollback_workspace_skill_version` | ❌ | ❌ | ❌ | ❌ |

## 初步发现（需要人工复核）

- 写操作端点总数：**179**
- 未检测到 `_rbac_guard` 的端点：**152**
- 未检测到 `add_audit_log` 的端点：**158**

### A) 可能缺少 RBAC 门控的端点（❌ _rbac_guard）

- POST `/adapters` (create_adapter)
- DELETE `/adapters/{adapter_id}` (delete_adapter)
- PUT `/adapters/{adapter_id}` (update_adapter)
- POST `/adapters/{adapter_id}/disable` (disable_adapter)
- POST `/adapters/{adapter_id}/enable` (enable_adapter)
- POST `/adapters/{adapter_id}/models` (add_adapter_model)
- DELETE `/adapters/{adapter_id}/models/{model_name}` (delete_adapter_model)
- PUT `/adapters/{adapter_id}/models/{model_name}` (update_adapter_model)
- POST `/adapters/{adapter_id}/test` (test_adapter)
- POST `/agents` (create_agent)
- POST `/agents/executions/{execution_id}/resume` (resume_agent_execution)
- DELETE `/agents/{agent_id}` (delete_agent)
- PUT `/agents/{agent_id}` (update_agent)
- POST `/agents/{agent_id}/skills` (bind_agent_skills)
- DELETE `/agents/{agent_id}/skills/{skill_id}` (unbind_agent_skill)
- POST `/agents/{agent_id}/start` (start_agent)
- POST `/agents/{agent_id}/stop` (stop_agent)
- POST `/agents/{agent_id}/tools` (bind_agent_tools)
- DELETE `/agents/{agent_id}/tools/{tool_id}` (unbind_agent_tool)
- POST `/agents/{agent_id}/versions` (create_agent_version)
- POST `/agents/{agent_id}/versions/{version}/rollback` (rollback_agent_version)
- POST `/approvals/{request_id}/replay` (replay_approval)
- POST `/autosmoke/run` (run_autosmoke)
- POST `/change-control/changes/{change_id}/autosmoke` (autosmoke_change_control)
- POST `/diagnostics/e2e/smoke` (run_e2e_smoke)
- POST `/diagnostics/prompt/assemble` (diagnostics_prompt_assemble)
- POST `/diagnostics/repo/changeset/preview` (diagnostics_repo_changeset_preview)
- POST `/diagnostics/repo/changeset/record` (diagnostics_repo_changeset_record)
- POST `/diagnostics/repo/git/branch` (diagnostics_repo_git_branch)
- POST `/diagnostics/repo/git/commit` (diagnostics_repo_git_commit)
- POST `/diagnostics/repo/staged/preview` (diagnostics_repo_staged_preview)
- POST `/diagnostics/repo/tests/run` (diagnostics_repo_tests_run)
- DELETE `/gateway/dlq/{dlq_id}` (delete_gateway_delivery_dlq)
- POST `/gateway/dlq/{dlq_id}/retry` (retry_gateway_delivery_dlq)
- DELETE `/gateway/pairings` (delete_gateway_pairing)
- POST `/gateway/pairings` (upsert_gateway_pairing)
- POST `/gateway/slack/command` (gateway_slack_command)
- POST `/gateway/slack/events` (gateway_slack_events)
- POST `/gateway/tokens` (create_gateway_token)
- DELETE `/gateway/tokens/{token_id}` (delete_gateway_token)
- POST `/gateway/webhook/message` (gateway_webhook_message)
- POST `/graphs/compiled/react/execute` (execute_compiled_react_graph)
- POST `/graphs/runs/{run_id}/resume` (resume_graph_run)
- POST `/graphs/runs/{run_id}/resume/execute` (resume_and_execute_compiled_graph)
- PUT `/harness/config` (update_harness_config)
- POST `/harness/coordinators` (create_coordinator)
- DELETE `/harness/coordinators/{coordinator_id}` (delete_coordinator)
- PUT `/harness/coordinators/{coordinator_id}` (update_coordinator)
- PUT `/harness/feedback/config` (update_feedback_config)
- POST `/harness/hooks` (create_hook)
- ... 其余 102 条略

### B) 可能缺少审计记录的端点（❌ add_audit_log）

> 注：有些端点可能仅靠 changeset/event 记录，仍需人工判断是否满足审计要求。

- POST `/adapters` (create_adapter)
- DELETE `/adapters/{adapter_id}` (delete_adapter)
- PUT `/adapters/{adapter_id}` (update_adapter)
- POST `/adapters/{adapter_id}/disable` (disable_adapter)
- POST `/adapters/{adapter_id}/enable` (enable_adapter)
- POST `/adapters/{adapter_id}/models` (add_adapter_model)
- DELETE `/adapters/{adapter_id}/models/{model_name}` (delete_adapter_model)
- PUT `/adapters/{adapter_id}/models/{model_name}` (update_adapter_model)
- POST `/adapters/{adapter_id}/test` (test_adapter)
- POST `/agents` (create_agent)
- POST `/agents/executions/{execution_id}/resume` (resume_agent_execution)
- DELETE `/agents/{agent_id}` (delete_agent)
- PUT `/agents/{agent_id}` (update_agent)
- POST `/agents/{agent_id}/execute` (execute_agent)
- POST `/agents/{agent_id}/skills` (bind_agent_skills)
- DELETE `/agents/{agent_id}/skills/{skill_id}` (unbind_agent_skill)
- POST `/agents/{agent_id}/start` (start_agent)
- POST `/agents/{agent_id}/stop` (stop_agent)
- POST `/agents/{agent_id}/tools` (bind_agent_tools)
- DELETE `/agents/{agent_id}/tools/{tool_id}` (unbind_agent_tool)
- POST `/agents/{agent_id}/versions` (create_agent_version)
- POST `/agents/{agent_id}/versions/{version}/rollback` (rollback_agent_version)
- POST `/approvals/{request_id}/replay` (replay_approval)
- POST `/autosmoke/run` (run_autosmoke)
- POST `/change-control/changes/{change_id}/autosmoke` (autosmoke_change_control)
- POST `/diagnostics/e2e/smoke` (run_e2e_smoke)
- POST `/diagnostics/prompt/assemble` (diagnostics_prompt_assemble)
- POST `/diagnostics/repo/changeset/preview` (diagnostics_repo_changeset_preview)
- POST `/diagnostics/repo/changeset/record` (diagnostics_repo_changeset_record)
- POST `/diagnostics/repo/git/branch` (diagnostics_repo_git_branch)
- POST `/diagnostics/repo/git/commit` (diagnostics_repo_git_commit)
- POST `/diagnostics/repo/staged/preview` (diagnostics_repo_staged_preview)
- POST `/diagnostics/repo/tests/run` (diagnostics_repo_tests_run)
- DELETE `/gateway/dlq/{dlq_id}` (delete_gateway_delivery_dlq)
- POST `/gateway/dlq/{dlq_id}/retry` (retry_gateway_delivery_dlq)
- DELETE `/gateway/pairings` (delete_gateway_pairing)
- POST `/gateway/pairings` (upsert_gateway_pairing)
- POST `/gateway/slack/command` (gateway_slack_command)
- POST `/gateway/slack/events` (gateway_slack_events)
- POST `/gateway/tokens` (create_gateway_token)
- DELETE `/gateway/tokens/{token_id}` (delete_gateway_token)
- POST `/gateway/webhook/message` (gateway_webhook_message)
- POST `/graphs/compiled/react/execute` (execute_compiled_react_graph)
- POST `/graphs/runs/{run_id}/resume` (resume_graph_run)
- POST `/graphs/runs/{run_id}/resume/execute` (resume_and_execute_compiled_graph)
- PUT `/harness/config` (update_harness_config)
- POST `/harness/coordinators` (create_coordinator)
- DELETE `/harness/coordinators/{coordinator_id}` (delete_coordinator)
- PUT `/harness/coordinators/{coordinator_id}` (update_coordinator)
- PUT `/harness/feedback/config` (update_feedback_config)
- ... 其余 108 条略

