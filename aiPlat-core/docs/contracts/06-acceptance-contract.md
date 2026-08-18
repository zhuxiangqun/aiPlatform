# Acceptance Contract（验收/回归契约）

本文件将 Contracts 转成“可自动化验收点”，用于像 Claude Code 一样把系统行为锁死在 CI 里。

## 0. Definition of Done（MUST）

对核心能力/机制的变更，合入前必须满足：
1. 契约文档已更新（本目录）或明确说明“不影响契约”
2. 对应自动化用例已新增/更新并通过
3. 关键路径不引入循环依赖（import 结构可被单测覆盖）

## 1. 核心验收点清单

### 1.1 工具描述预算（Tools Desc Budgets）
- MUST：当总预算触发隐藏工具时，`tool_search` 仍可见
- MUST：per_tool 截断生效且 stats 正确
- 参考用例：
  - `core/tests/unit/test_harness/test_tools_desc_budget.py`

### 1.2 动态工具发现（tool_search）
- MUST：能按 query 搜索已注册工具并返回 items 列表
- SHOULD：能按 name 精确返回 schema（截断版）
- 参考用例：
  - `core/tests/unit/test_tool_search_tool.py`

### 1.3 Transcript Guard（LLM 输入保护）
- MUST：role 修复、相邻合并、长度限制、统计上报
- 参考用例：
  - `core/tests/unit/test_harness/test_llm_message_guard.py`

### 1.4 Context Compaction（摘要压缩）
- MUST：超过阈值生成 CONTEXT_SUMMARY，保留标识符
- 参考用例：
  - `core/tests/unit/test_harness/test_context_compaction.py`

### 1.5 Stable Prompt Cache Key
- MUST：stable cache key 仅依赖 stable system hash（不因每轮变化而变化）
- 参考用例：
  - `core/tests/integration/test_phaseR1_prompt_assembler_layers_cache.py`

### 1.6 Prompt Mode
- MUST：`none/minimal/full` 行为符合定义
- 参考用例：
  - `core/tests/integration/test_phaseR1_prompt_mode.py`

### 1.7 Policy Denied 体验（自动引导/可控重试）
- SHOULD：policy_denied 给出下一步指导，且不会立即把系统卡死在 pause
- 参考用例：
  - `core/tests/unit/test_harness/test_policy_denied_auto_retry.py`

### 1.8 内存缓存有界化（2026-08-18）
- MUST：harness 持久容器缓存有界——`file.py:_read_cache`（`_MAX_CACHE`）、`path_planner.py:_discovered_cache`（`_MAX_CACHE`+TTL）、`a2a/server.py:_tasks`（`_MAX_TASKS`）、`observation.py:_diag_buffers`（`_DIAG_TTL`+`_MAX_DIAG_RUNS`）、`plugins:_slot_archives`（`_MAX_ARCHIVES`）、`sql_ontology:_translators`（`_MAX_DOMAINS`）、`model_injection:_FAILURE_TRACKER`/`_model_overrides`（`_MAX_*`）、`credential_pool:_pools`（`_MAX_POOLS`）、`skill_routing:_skill_weights`（`_MAX_SKILL_WEIGHTS`）、`evolution:_latest_predictions`（`_MAX_PREDICTIONS`）、`base_model_adapter:_model_cache`（`_MAX_MODEL_CACHE`）
- MUST：守卫 §83 只告警无界缓存（`@functools.cache`/`@lru_cache(maxsize=None)`/无界持久容器），有界 maxsize=N 与模块级一次性注册表不告警；注册表豁免基于变量名（`_REGISTRY/_DEFAULTS/_MAP`），非文件级
- MUST：键空间来自客户端输入（HTTP 参数 / session_id / provider）的缓存必须校验或设上限
- 自动化验收：
  - `bash scripts/architecture_guard.sh`（§83 项：Dict 无清理 = 0、Unbounded append = 0、LRU 无 clear = 0）

### 1.9 运行时扩展缝门禁（P2-A2）
- MUST：`CoreFacade.register_handler` 拒绝危险模块（os/sys/subprocess/shutil/builtins）定义的 handler，未评估模块仅 warn
- MUST：dispatch 永不触发任意代码执行
- 参考用例：
  - `core/tests/integration/test_l5_verification.py`（register_handler/dispatch 正常路径）

### 1.10 Provider YAML 驱动（P2-A3）
- MUST：`ModelManager._api_provider_ids()` 从 `config/providers.yaml`（type=external）派生，新增 external provider 零代码；YAML 缺失回退硬编码集合
- 自动化验收：`python3 -c "from infra.management.model.manager import _api_provider_ids; assert 'ollama' not in _api_provider_ids()"`

### 1.8 Exec Backends（local/docker/ssh）
- MUST：health 输出结构包含 capabilities
- SHOULD：capabilities 能表达 supported_languages/isolation/config 关键信息
- 参考用例：
  - `core/tests/unit/test_exec_drivers/test_capabilities.py`
  - `core/tests/unit/test_exec_drivers/test_ssh_driver.py`

### 1.9 Skills：find/load（规则型技能按需加载）
- MUST：skills 列表仅暴露 name/description（受预算控制），不得默认注入 SOP 全文
- MUST：`skill_find` 返回摘要列表（不含正文）
- MUST：`skill_load` 按 name 加载正文并记录 skill_hash/version 到 meta / events
- MUST：权限三态 allow/ask/deny 对 load 生效（deny 不可见，ask 走审批）
- 参考用例：
  - `core/tests/unit/test_tools/test_skill_find_load_tools.py`
  - `core/tests/unit/test_gates/test_policy_gate_skill_load_permissions.py`
  - `core/tests/unit/test_harness/test_skills_desc_budget.py`

### 1.10 Skills：类型自动判别（rule vs executable）
- MUST：frontmatter 显式声明优先（`executable:true/false`）
- MUST：未声明时默认保守（倾向 rule），仅在满足明确入口/manifest 条件时判定 executable
- MUST：判定为 executable 时仍需通过安全门槛（permissions/provenance/integrity）否则降级或拒绝
- 参考用例：
  - `core/tests/unit/test_skills/test_skill_kind_detection.py`

### 1.11 Skills：安装器（git/path/zip）
- MUST：git 安装必须提供 ref（固定版本），禁止默认 main 漂移
- MUST：git host 必须命中 allowlist（默认 github.com），不允许 ssh 协议
- SHOULD：安装/更新/卸载在 workspace scope 下可用，并写入 SKILL.manifest.json（source/ref/commit）
- 参考用例：
  - `core/tests/unit/test_skills/test_skill_installer.py`

### 1.12 Skills：安装 plan_id（签名 + 防漂移）
- MUST：/installer/plan 返回 plan_id（当配置了 AIPLAT_SKILL_INSTALL_PLAN_SECRET 时）
- MUST：当启用 AIPLAT_SKILL_INSTALL_REQUIRE_PLAN_ID=true 时，/installer/install 必须携带 plan_id，且 payload 不得漂移（不一致则拒绝）
- MUST：plan_id 具有过期时间（TTL），过期拒绝
- SHOULD：plan_id 绑定“将安装的 skills 摘要 digest”，防止 plan/install 间技能集合变化
- 参考用例：
  - `core/tests/unit/test_skills/test_skill_install_plan_token.py`

## 2. 建议的“必跑测试集”（SHOULD）

在 CI 中建议至少包含：

```bash
pytest -q \
  core/tests/unit/test_harness/test_llm_message_guard.py \
  core/tests/unit/test_harness/test_context_compaction.py \
  core/tests/unit/test_harness/test_context_shaping_pipeline.py \
  core/tests/unit/test_harness/test_auto_eval_prompt_includes_browser_evidence.py \
  core/tests/unit/test_harness/test_evidence_diff.py \
  core/tests/unit/test_harness/test_coverage_gate.py \
  core/tests/unit/test_harness/test_canary_escalation.py \
  core/tests/unit/test_harness/test_canary_recommendation.py \
  core/tests/unit/test_skills/test_generic_skill_json_output.py \
  core/tests/unit/test_skills/test_skillmanager_bridge_schema_to_registry.py \
  core/tests/unit/test_skills/test_skill_linter.py \
  core/tests/unit/test_skill_fix_proposals.py \
  core/tests/unit/test_skill_lint_scan_job_kind.py \
  core/tests/unit/test_skill_lint_alert_contract.py \
  core/tests/unit/test_apply_lint_fix_workspace.py \
  core/tests/integration/test_canary_block_release_candidate.py \
  core/tests/unit/test_harness/test_regression_gate_required_tags.py \
  core/tests/unit/test_harness/test_tag_assertions.py \
  core/tests/unit/test_harness/test_evaluator_workbench.py \
  core/tests/unit/test_harness/test_evaluation_policy_parse.py \
  core/tests/unit/test_harness/test_evaluation_policy_merge.py \
  core/tests/unit/test_docs/test_auto_eval_docs_guard.py \
  core/tests/unit/test_docs/test_auto_eval_openapi_snapshot_guard.py \
  core/tests/unit/test_docs/test_auto_eval_doc_openapi_section_guard.py \
  core/tests/unit/test_harness/test_executable_skill_policy_gate.py \
  core/tests/unit/test_harness/test_run_state_format.py \
  core/tests/unit/test_harness/test_run_state_merge_generates_todo.py \
  core/tests/unit/test_harness/test_run_state_auto_next_step_from_todo.py \
  core/tests/unit/test_harness/test_policy_denied_auto_retry.py \
  core/tests/unit/test_harness/test_tools_desc_budget.py \
  core/tests/unit/test_harness/test_skills_desc_budget.py \
  core/tests/unit/test_tool_search_tool.py \
  core/tests/unit/test_tools/test_skill_find_load_tools.py \
  core/tests/unit/test_gates/test_policy_gate_skill_load_permissions.py \
  core/tests/unit/test_skills/test_skill_kind_detection.py \
  core/tests/unit/test_skills/test_skill_installer.py \
  core/tests/unit/test_skills/test_skill_install_plan_token.py \
  core/tests/unit/test_exec_drivers/test_capabilities.py \
  core/tests/integration/test_phaseR1_prompt_assembler_layers_cache.py \
  core/tests/integration/test_phaseR1_prompt_mode.py
```

## 3. 文档-测试绑定（SHOULD）

建议在 PR 模板或 CI 里加入检查：
- Contracts 目录变更时，必须包含至少 1 个对应用例变更；或在 PR 描述中解释原因

### 1.11 元认知 MetaAgent（P0-C7, 2026-08-18）
- MUST：`core.harness.meta.get_meta_agent()` 可导入且 `analyze(days)` 返回建议列表（EvolutionEngine meta_analysis step 不再静默 error）
- MUST：守卫规则黄金样本验证（`rule_golden_sample.py --verify`）在 CI 中执行，规则必须有真实命中
- 自动化验收：
  - `python3 scripts/rule_golden_sample.py --verify`（0 问题）
  - `core/tests/wiring/test_meta_agent_wired.py`（接线断言 2 passed）

### 1.12 PipelineEngine Mixin 拆分（P2-A4, 2026-08-18）
- MUST：`core.harness.execution.pipeline_healing.PipelineHealingMixin` 存在，`PipelineEngine` MRO 含该 Mixin，13 个自愈方法经继承可用
- MUST：`PipelineEngine` 类文件 ≤ 12000 行（Phase 1 后 11734）
- 自动化验收：
  - `python3 -c "from core.harness.execution.pipeline_engine import PipelineEngine; assert PipelineHealingMixin in PipelineEngine.__mro__"`
  - `bash scripts/verify-l4-claims.sh`（31/31 PASS）

### 1.13 PipelineEngine Phase 2 state Mixin（P2-A4, 2026-08-18）
- MUST：`core.harness.execution.pipeline_state.PipelineStateMixin` 存在，`PipelineEngine` MRO 含 `PipelineStateMixin`（在 `PipelineHealingMixin` 前）
- MUST：6 个状态持久化方法（`_snapshot`/`_merge_state`/`_load_checkpoints_from_disk`/`_output_root`/`_persist_files`/`_summarize_artifact`）经继承可用
- 自动化验收：
  - `python3 -c "from core.harness.execution.pipeline_engine import PipelineEngine; from core.harness.execution.pipeline_state import PipelineStateMixin; from core.harness.execution.pipeline_healing import PipelineHealingMixin; assert PipelineEngine.__mro__.index(PipelineStateMixin) < PipelineEngine.__mro__.index(PipelineHealingMixin)"`

### 1.14 PipelineEngine Phase 3 prompt/eval Mixin（P2-A4, 2026-08-18）
- MUST：`core.harness.execution.pipeline_prompt.PipelinePromptMixin` + `pipeline_eval.PipelineEvalMixin` 存在，`PipelineEngine` MRO 含两者（顺序 EvalMixin → PromptMixin → StateMixin → HealingMixin）
- MUST：14 个 prompt/eval 方法（`_build_prompt`/`_tri_evaluate`/`_retry_loop` 等）经继承可用
- MUST：主类 ≤ 10000 行（Phase 3 后 9406）
- 自动化验收：
  - `python3 -c "from core.harness.execution.pipeline_engine import PipelineEngine; from core.harness.execution.pipeline_eval import PipelineEvalMixin; from core.harness.execution.pipeline_prompt import PipelinePromptMixin; assert PipelineEngine.__mro__.index(PipelineEvalMixin) < PipelineEngine.__mro__.index(PipelinePromptMixin)"`

### 1.15 PipelineEngine Phase 4 stage Mixin（P2-A4, 2026-08-18，收官）
- MUST：`core.harness.execution.pipeline_stage.PipelineStageMixin` 存在，`PipelineEngine` MRO 首位 Mixin（顺序 StageMixin → EvalMixin → PromptMixin → StateMixin → HealingMixin）
- MUST：8 个 stage 方法（`_dispatch_execute`/`_exec_stage`/`_evaluate_stage_health`/`_infer_profile_from_stage`/`_calibrate_profile_from_history`/`_apply_capability_profile`/`_build_handler_params`/`_exec_isolated_stage`）经继承可用且不在主类重复定义
- MUST：`_run_stages_from` 保留在主类（核心调度枢纽，9 处引用不变）
- MUST：主类 ≤ 9000 行（Phase 4 后 8288），拆分累计 -3993 行，零公共 API 破坏
- 自动化验收：
  - `python3 -c "from core.harness.execution.pipeline_engine import PipelineEngine; from core.harness.execution.pipeline_stage import PipelineStageMixin; assert PipelineEngine.__mro__[1] is PipelineStageMixin; assert '_exec_stage' in PipelineStageMixin.__dict__; assert '_exec_stage' not in PipelineEngine.__dict__"`

### 1.16 Tenant 表迁移（P0-A3, 2026-08-18）
- MUST：`core.services.tenant_store_protocol.TenantStoreProtocol` 存在，含 8 个 tenant 方法签名（get/upsert_tenant_quota、add/get/list_tenant_usage、get/upsert/list_tenant_policies）
- MUST：`aiPlat-platform.tenants.tenant_store.TenantStore` 存在，实现 TenantStoreProtocol；`set_tenant_store()` 经 CoreFacade 可达；挂载 `apps.fde` 后 `get_tenant_store()` 非 None
- MUST：core ExecutionStore 不再定义 tenant_quotas/tenant_usage_ledger/tenant_policies 的 DDL 或 CRUD（宪法 `TestNoQuotaEnforcementInCore`/`TestPlatformResponsibilitiesNotInCore` 真过，无 DEPRECATED 豁免依赖）
- MUST：同库零数据迁移（TenantStore 与 ExecutionStore 同一 db_path，IF NOT EXISTS 幂等）
- MUST：消费方注入优先 fallback（core 9 处 + platform 6 处调用点 `get_tenant_store() or store`）
- 自动化验收：
  - `python3 -c "from core.services.tenant_store_protocol import TenantStoreProtocol, set_tenant_store, get_tenant_store; set_tenant_store(None); assert get_tenant_store() is None"`
  - `AIPLAT_HOME=tmp/guard_home pytest tests/constitution/test_kernel_agnostic.py::TestNoQuotaEnforcementInCore tests/constitution/test_layer_ownership.py -q`（5 passed，无豁免依赖）
  - `pytest tests/constitution/test_kernel_agnostic.py::TestNoQuotaEnforcementInCore tests/constitution/test_layer_ownership.py::TestPlatformResponsibilitiesNotInCore -q`（5 passed）

### 1.17 子代理 provider（P1-A3, 2026-08-18）
- MUST：`core.apps.agents.subagent.providers.SubagentProvider` 抽象存在（capabilities 旗标 + `start`/`continuation`/`interrupt`），`InProcessProvider` + `ACPProvider` 两实现，工厂 `get_provider_factories()` 返回 `{in_process, acp}`
- MUST：`SubagentCoordinator.list_providers()` ≥2；`execute_parallel(provider=...)` 走 `execute_with_provider`；`send_message`/`get_instance_status`（running/waiting/settled 三态）可用
- MUST：生产接线——`dynamic_orchestrator` 按 `AIPLAT_SUBAGENT_PROVIDER`（默认 in_process）选择 provider 路径
- MUST：fail-loud——provider 不支持的能力（continuation/start）返回明确错误，无假成功
- 自动化验收：
  - `python3 -c "from core.apps.agents.subagent.coordinator import SubagentCoordinator; c=SubagentCoordinator(); assert 'in_process' in c.list_providers() and len(c.list_providers())>=2"`
  - `pytest aiPlat-core/core/tests/unit/test_agents/test_subagent_providers.py -q`（14 passed）
