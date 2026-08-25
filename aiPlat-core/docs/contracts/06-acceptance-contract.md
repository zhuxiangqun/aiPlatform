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

### 1.18 消息渠道适配器（P1-A4, 2026-08-18）
- MUST：`aiPlat-app/channels/adapter.py::get_channel_adapter(name)` 存在，7 渠道（telegram/slack/webchat/discord/wecom/email/dingtalk）均可解析，`wecom` 映射 `WeComAdapter`；未知渠道 raise ValueError
- MUST：扩展适配器（Discord/WeCom/Email/DingTalk）注册进 `ChannelDispatcher`（3 内置 + 4 扩展 = 7）
- MUST：`POST /platform/channels/{id}/test` 校验适配器（未知通道 422）
- 自动化验收：
  - `python3 -c "import sys; sys.path.insert(0,'aiPlat-app'); from channels.adapter import get_channel_adapter; [get_channel_adapter(n) for n in ['telegram','slack','webchat','discord','wecom','email','dingtalk']]; print('OK')"`
  - `cd aiPlat-app && pytest tests/test_cli_and_channels.py -q`（6 passed）

### 1.18b 渠道广度延伸（WhatsApp/Lark/Teams, 2026-08-23）
- MUST：`get_channel_adapter` 可解析 10 渠道（3 内置 + 7 扩展 = telegram/slack/webchat/discord/wecom/email/dingtalk/whatsapp/lark/teams）
- MUST：`whatsapp`/`lark`/`teams` 适配器实现 `parse_message`（统一 `ChannelMessage` 格式）+ `format_response`（渠道原生响应），注册进 `ADAPTERS`
- 自动化验收：
  - `python3 -c "import sys; sys.path.insert(0,'aiPlat-app'); from channels.adapter import get_channel_adapter; [get_channel_adapter(n) for n in ['whatsapp','lark','teams']]; print('OK')"`
  - `cd aiPlat-app && pytest tests/test_cli_and_channels.py -q`（≥9 passed）

### 1.18c 渠道广度延伸二批（Signal/Matrix/Mattermost/Line, 2026-08-24）
- MUST：`signal`/`matrix`/`mattermost`/`line` 适配器实现 `parse_message`（统一 `ChannelMessage`）+ `format_response`（渠道原生响应），注册进 `ADAPTERS`
- MUST：`get_channel_adapter` 可解析 **14 渠道**（3 内置 + 11 扩展 = telegram/slack/webchat/discord/wecom/email/dingtalk/whatsapp/lark/teams/signal/matrix/mattermost/line）
- 自动化验收：
  - `python3 -c "import sys; sys.path.insert(0,'aiPlat-app'); from channels.adapter import get_channel_adapter; [get_channel_adapter(n) for n in ['signal','matrix','mattermost','line']]; print('OK')"`
  - `cd aiPlat-app && pytest tests/test_cli_and_channels.py -q`（15 passed）

### 1.18d 渠道广度延伸三批（QQ/Reddit/GitHub/SMS, 2026-08-24）
- MUST：`qq`/`reddit`/`github`/`sms` 适配器实现 `parse_message`（统一 `ChannelMessage`）+ `format_response`（渠道原生响应），注册进 `ADAPTERS`
- MUST：`get_channel_adapter` 可解析 **18 渠道**（3 内置 + 15 扩展）
- 自动化验收：
  - `python3 -c "import sys; sys.path.insert(0,'aiPlat-app'); from channels.adapter import get_channel_adapter; [get_channel_adapter(n) for n in ['qq','reddit','github','sms']]; print('OK')"`
  - `cd aiPlat-app && pytest tests/test_cli_and_channels.py -q`（20 passed）

### 1.19 harness→apps 收敛（P0-A1, 2026-08-18）
- MUST：integration.py 含 5 个新工厂（`get_mcp_client_manager`/`get_skill_discovery`/`get_job_manager`/`get_dataset_manager`/`get_result_verifier`），DI-first fallback direct import
- MUST：9 个 harness 文件不再直导 apps 服务（dynamic_orchestrator/delegate_tool/voice_pipeline/profile/learning/training×3/pipeline_engine-quality）
- MUST：宪法 `test_core_internal_boundaries.py` 白名单 ≤ 26 条（38→25）
- 自动化验收：
  - `pytest tests/constitution/test_core_internal_boundaries.py -q`（3 passed）
  - `python3 -c "from core.harness.integration import get_mcp_client_manager, get_skill_discovery, get_job_manager, get_dataset_manager, get_result_verifier; assert all(callable(f) for f in [get_mcp_client_manager, get_skill_discovery, get_job_manager, get_dataset_manager, get_result_verifier])"`

### 1.20 api→CoreFacade 收敛（P0-A2, 2026-08-18）
- MUST：api/routers 不再直导执行引擎核心模块（kernel.runtime/integration/model_injection 公共符号/syscalls.llm/approval）
- MUST：CoreFacade 模块级含 `sys_llm_generate` re-export
- MUST：api 全部 routers 可导入（69/69）
- 自动化验收：
  - `python3 -c "import sys; sys.path.insert(0,'aiPlat-core'); import core.api.routers.plugins, core.api.routers.runs, core.api.routers.diagnostics, core.api.routers.memory, core.api.routers.workspace_agents; print('OK')"`
  - `pytest tests/constitution/test_core_internal_boundaries.py tests/constitution/test_kernel_agnostic.py -q`（14 passed）

### 1.21 Builder E2E 修复（P0-A10, 2026-08-18）
- MUST：`aiPlat-platform/tests/test_builder.py` + `aiPlat-core/core/tests/unit/test_builder_pipeline_e2e.py` 20/20 passed（守卫 §17 放行）
- MUST：测试不依赖本地硬件模型加载（mock create_selected_adapter/best_model_for_purpose）
- 自动化验收：
  - `pytest aiPlat-platform/tests/test_builder.py aiPlat-core/core/tests/unit/test_builder_pipeline_e2e.py -q`（20 passed）

### 1.22 MFA 强制策略（P0-5 阶段 3, 2026-08-18）
- MUST：`POST /tenant/api-keys` 对 admin 角色（`actor_role == admin`）未启用 MFA 的用户返回 422 `mfa_required`
- MUST：CLAUDE.md §11b 升级为强制（含 verify 块）
- 自动化验收：
  - `pytest aiPlat-platform/tests/test_mfa.py -q`（9 passed）
  - `python3 -c "from auth.mfa import require_mfa_for_role; assert require_mfa_for_role('admin') and not require_mfa_for_role('developer')"`

### 1.23 部分项闭环（P0-B4/B5/C3, 2026-08-19）
- MUST：CoreFacade `get_*` 符号 0 调用者清零（`get_agent_registry_facade` 已删，统一 `get_agent_registry`）
- MUST：`docs/standards/规范-功能开关与配置.md` 存在，登记 ≥40 个默认 false 的 AIPLAT_* 开关（分组 + 用途 + 位置 + 登记义务）
- MUST：`sync_registry_to_docs.py` 无漂移（190 符号全同步）；pre-commit Step 2.7 自动补登
- 自动化验收：
  - `python3 scripts/sync_registry_to_docs.py`（✅ 190 符号全同步）
  - `grep -c 'AIPLAT_' docs/standards/规范-功能开关与配置.md`（≥40）
  - `python3 -c "import ast; ast.parse(open('aiPlat-core/core/api/core_facade.py').read()); print('OK')"`

### 1.24 P0-A2 收敛回归修复（2026-08-19）
- MUST：全仓 `from core.api.core_facade import X` 的 X 均在 CoreFacade 模块级（缺失符号 = 0）
- MUST：`GET /api/core/knowledge-graph/stats` 端点核心逻辑 `_get_stats_sync` 可运行（无 ImportError）
- 自动化验收：
  - `python3 -c "from core.api.routers.knowledge_graph import _get_stats_sync; r=_get_stats_sync(); assert r.get('total_files',0)>0"`
  - `grep -rn 'from core.api.core_facade import' aiPlat-core/core/ aiPlat-platform/ --include='*.py' | grep -v __pycache__ | wc -l`（AST 校验缺失=0）

### 1.25 P0-A1 DI 工厂 fallback 修复（2026-08-19）
- MUST：integration.py 全部 `_resolve_or_import` fallback（13 个）的 `module:attr` 均真实存在
- MUST：`get_mcp_client_manager()` 返回 `MCPClientManager`（有 list_servers）；`get_agent_registry()` 返回 `AgentRegistry`
- 自动化验收：
  - `python3 -c "from core.harness.integration import get_mcp_client_manager, get_agent_registry; assert hasattr(get_mcp_client_manager(), 'list_servers'); assert get_agent_registry() is not None"`

### 1.26 应用工厂 rebuild 修复（2026-08-19）
- MUST：pipeline_execution.py 含 `PipelineConfig` import（3 处用法可解析）；`rebuild_from_state` 经 `create_pipeline_engine`（宪法 A2：api 不直导 pipeline_engine）
- MUST：无 api/routers → core.harness.execution.pipeline_engine 直导（宪法 test_api_routers_use_facade_not_engine 通过）
- 自动化验收：
  - `python3 -c "from core.schemas_builder import PipelineConfig, PipelineStageConfig; c=PipelineConfig(stages=[PipelineStageConfig(id='s1', agent_id='a', prompt='p')], max_tokens_per_run=1000); assert len(c.stages)==1"`
  - `pytest tests/constitution/test_core_internal_boundaries.py -q`（3 passed）

### 1.27 守卫盲区修复（2026-08-19）
- MUST：scripts/guard_undefined_names.py 存在且接入 architecture_guard.sh（AST 级未定义符号检查）
- MUST：pipeline_execution.py 无 PipelineEngine 直构/直导（全部经 create_pipeline_engine）
- 自动化验收：
  - python3 scripts/guard_undefined_names.py（0 new）
  - pytest tests/unit/test_pipeline_execution_undefined_names.py -q（4 passed）

### 1.28 模型选择去除 env 干预（2026-08-19）
- MUST：`core.harness.utils.model_injection` 无 `create_adapter_with_fallback`（死代码已删）
- MUST：`generate_with_fallback` 候选来自 `select_by_purpose_list`（infra 评分），无 `AIPLAT_{purpose}_MODEL` env 覆盖
- MUST：`_build_preferences` 不读 `AIPLAT_*_MODEL` env（仅 YAML model_overrides）
- MUST：`pipeline_state.py` 含 `import logging`（checkpoint OSError 路径不崩溃）
- 自动化验收：
  - `python3 -c "import core.harness.utils.model_injection as mi; assert not hasattr(mi, 'create_adapter_with_fallback'); assert callable(mi.generate_with_fallback)"`
  - `pytest core/tests/unit/test_builder_pipeline_e2e.py -q`（5 passed）

### 1.29 本体学习输出 + P1-2 页面感知优化（2026-08-19）
- MUST：`export_suggestions_to_owl` 将 pending new_class/new_property 建议序列化为含 `owl:Class`/`rdfs:subClassOf` 的 OWL/Turtle
- MUST：`write_suggestions_owl_file` 落盘 `~/.aiplat/ontologies/{collection_id}.learned.ttl`
- MUST：`GET /export/learned` 端点返回学习本体（`classes`/`properties`/`persisted`/`ttl`）
- MUST：materials_chat 页面感知检索不再硬编码 `manuals / management-ui-operation-manual`（改 `search_pages(page_label)`）
- 自动化验收：
  - `pytest core/tests/unit/test_harness/test_knowledge/test_ontology_learning.py -q`（5 passed）
  - `grep -c "manuals / management-ui-operation-manual" aiPlat-core/core/apps/agents/materials_chat.py`（注释命中 1，无代码硬编码）

### 1.30 本体学习管理面板（2026-08-19）
- MUST：`GET /ontology/suggestions` 返回 pending 建议列表（new_class/new_property/new_subclass/merge_classes）
- MUST：前端 `OntologyLearningPanel` 挂载于本体模型管理页（建议展示 + OWL 导出按钮调 `GET /ontology/export/learned`）
- 自动化验收：
  - 后端端点注册：`grep -c "suggestions" aiPlat-core/core/api/routers/wiki_semantic_suggestions.py`（GET 端点存在）
  - 前端 tsc：`cd aiPlat-management/frontend && npx tsc --noEmit`（exit 0）

### 1.31 数字人管线（2026-08-21）
- MUST：`integration.get_agent_registry()` 与 `core.apps.agents.get_agent_registry()` 返回同一 discovery 单例实例（P0-1 修复）
- MUST：`voice_pipeline.transcribe` 对 `List[Dict]`（segment 列表）按顺序拼接文本，不产生 `str(list)` 垃圾
- MUST：`voice_pipeline.generate_answer` 支持 `page_data` 参数并注入 `run_ctx['page_data']`；无 page_data 时不注入该字段
- MUST：`trajectory_collector.export_sharegpt_dataset` 聚合轨迹为 ShareGPT JSONL（`conversations: [{from: human/gpt, value}]`）
- MUST：WS `/ws/voice-chat` 在配置 `AIPLAT_VOICE_WS_TOKEN` 后校验 `?token=`（未配置保持开放）
- MUST：前端 `lib/pageDataBridge.ts` 提供 `reportPageData/getPageData/pageDataToText`；页面上报数据随 context 发送（`data` 字段）
- 自动化验收：
  - `pytest aiPlat-core/core/tests/unit/test_harness/test_digital_human/test_voice_pipeline_fixes.py -q`（12 passed）
  - `python3 -c "from core.harness.integration import get_agent_registry as a; from core.apps.agents import get_agent_registry as b; assert a() is b()"`（单例同源）
  - 前端 tsc + build：`cd aiPlat-management/frontend && npx tsc --noEmit && npm run build`（exit 0）

### 1.32 文档新鲜度守卫 Rule 6（2026-08-22）
- MUST：`scripts/check_research_docs_freshness.py` 存在且可运行（`python3 scripts/check_research_docs_freshness.py <workspace>` 返回 0）
- MUST：`verify_doc_sync.sh` 含 Rule 6 调用（`check_research_docs_freshness`），`--ci` 模式下 research 文档违规计入阻断
- MUST：审计报告头部支持 `> **最后验证：YYYY-MM-DD**` 自校验字段
- 自动化验收：
  - `python3 -m pytest tests/tool_correctness/test_research_docs_freshness.py -q`（8 passed）
  - `grep -c "check_research_docs_freshness" scripts/verify_doc_sync.sh`（≥2：定义 + 调用）

### 1.33 应用工厂页面感知（2026-08-22）
- MUST：`frontend/src/pages/App/Factory/index.tsx` 含 `reportPageData('/app/factory', ...)`（项目数/阶段/通过率/选中项目）
- MUST：`/app/factory`（AIFactory 3 模式）与 `/app/builder/projects`（ProjectsPage）共用后端 `/platform/builder/projects`
- MUST：应用工厂生命周期端点完整（chat/confirm/recommend-team/start/approve/reject/fix/rollback/deploy）
- 自动化验收：
  - `grep -c "reportPageData('/app/factory'" aiPlat-management/frontend/src/pages/App/Factory/index.tsx`（≥1）
  - `grep -c "start_pipeline\|deploy_to_app" aiPlat-platform/builder/builder_project_service.py`（≥2）
  - 前端 tsc + build：`cd aiPlat-management/frontend && npx tsc --noEmit && npm run build`（exit 0）

### 1.34 应用工厂双模式 + pass_rate 标注（2026-08-22）
- MUST：`team_planner` 的 mode 判断存在（prompt 含 `agent`/`code` 两种模式说明），`mode ∈ (agent, code)` 才接受
- MUST：`deploy_to_app` 写入 `pass_rate_source`（`real_pytest` / `estimated`），estimated 时附 `pass_rate_estimate_reason`
- MUST：`~/.aiplat/teams/default.yaml`（agent 模式）与 `code.yaml`（code 模式）存在，code 模式含 `uses_file_output`/`deploy_files_to_disk`
- 自动化验收：
  - `grep -c "mode" aiPlat-core/core/harness/execution/team_planner.py`（≥5，mode 判断 + 输出）
  - `grep -c "pass_rate_source" aiPlat-platform/builder/builder_project_service.py`（≥1）
  - `ls ~/.aiplat/teams/`（含 default.yaml + code.yaml）

### 1.35 应用工厂分析报告（2026-08-22）
- MUST：`docs/research/应用工厂分析报告.md` 存在且含双模式自动路由说明（mode: agent/code）
- MUST：报告中的代码引用可通过 Rule 6 校验（`python3 scripts/check_research_docs_freshness.py <workspace>` 返回 0）
- 自动化验收：
  - `ls docs/research/应用工厂分析报告.md`（存在）
  - `grep -c "planning_agent" docs/research/应用工厂分析报告.md`（≥1）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.36 SystemGraph 路径修复 + guard 冲突修复（2026-08-22）
- MUST：`SystemGraph/index.tsx` 的 code-intel API 用 `/api/platform/apps/diagnostics/code-intel/*`（匹配 platform misc 挂载）
- MUST：`guard_frontend.py` 支持跨层同名文件（core/api/routers/code_intel.py vs platform/apps/misc/api/code_intel.py）——完整相对路径优先于 basename
- 自动化验收：
  - `grep -c "api/platform/apps/diagnostics/code-intel" aiPlat-management/frontend/src/pages/SystemGraph/index.tsx`（≥5）
  - `python3 scripts/guard_frontend.py`（exit 0，无 path_mismatch ERROR）
  - `grep -c "rel_path" scripts/guard_frontend.py`（≥1，完整路径优先逻辑）

### 1.37 L2 导入既有代码设计 + Rule 6 plan 豁免（2026-08-22）
- MUST：`docs/research/plan-app-factory-l2-import-repo.md` 存在（L2 设计：import-repo API/prompt 注入/安全/回滚/验收）
- MUST：`check_research_docs_freshness.py` 对 `plan-` 前缀设计文档跳过引用对账（`is_plan` 逻辑）
- 自动化验收：
  - `ls docs/research/plan-app-factory-l2-import-repo.md`（存在）
  - `grep -c "is_plan" scripts/check_research_docs_freshness.py`（≥2：定义 + 使用）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.38 L2 评审意见并入（重写契约 + 意图绑定 + 测试门禁/依赖预检）（2026-08-22）
- MUST：设计文档明确"重写而非合并"行为契约（§3.4 行为契约 + 前端红字警告 + prompt 行为指令）
- MUST：modify_files 升级为 {path, intent} 意图绑定（§3.2/§3.5/§4），空意图不能提交
- MUST：测试门禁逃生（§3.8）：tests/ 检测 + `skip_pytest_gate` 字段 + pre-check-import 依赖预检
- 自动化验收：
  - `grep -c "重写而非合并" docs/research/plan-app-factory-l2-import-repo.md`（≥2：§3.4 标题 + §3.4 正文）
  - `grep -c "intent" docs/research/plan-app-factory-l2-import-repo.md`（≥4：API/注入/验收/前端）
  - `grep -c "skip_pytest_gate" docs/research/plan-app-factory-l2-import-repo.md`（≥2：§3.8 + §4）
  - `grep -c "pre-check-import" docs/research/plan-app-factory-l2-import-repo.md`（≥2：§3.2 + §3.8）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.39 L2 终审条件并入（手册 + Build Log 警告 + 埋点 + missing_deps）（2026-08-22）
- MUST：`docs/research/plan-app-factory-l2-expected-behavior-manual.md` 存在（《L2 模式预期管理手册》交付物：重写≠合并/风格玄学/门禁失效三硬边界 + Checklist + 后悔路径）
- MUST：设计文档含 §3.9 交付条件（手册引用 + Build Log regenerated 警告 + skip_pytest_gate 埋点 >40% 触发 L3 优先级告警）
- MUST：依赖预检并入 import_repo 响应（missing_deps 字段，pre-check-import 独立接口降级，保留决策痕迹 ≥2 处）
- 自动化验收：
  - `ls docs/research/plan-app-factory-l2-expected-behavior-manual.md`（存在）
  - `grep -c "missing_deps" docs/research/plan-app-factory-l2-import-repo.md`（≥3：§3.2 响应 + §3.8 表格 + §6 工作量）
  - `grep -c "has been regenerated" docs/research/plan-app-factory-l2-import-repo.md`（≥1：§3.9 条件 2）
  - `grep -c "埋点" docs/research/plan-app-factory-l2-import-repo.md`（≥2：§3.8 表格 + §3.9 条件 3）
  - `grep -c "pre-check-import" docs/research/plan-app-factory-l2-import-repo.md`（≥2：决策痕迹，兼容 1.38）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.40 L2 实施（import-repo + prompt 注入 + 门禁逃生 + 警告/埋点）（2026-08-22）
- MUST：`POST /projects/{id}/import-repo`（zip/路径→manifest，zip-slip 防护/密钥过滤/限额）+ `GET /projects/{id}/imported-files` + `GET /import-stats` 端点存在（builder.py）
- MUST：modify_files {path, intent} 校验（空 intent 拒绝）+ rebuild config 传递 `imported_repo`（含 behavior_prompt/intent_anchor_block）+ `skip_pytest_gate`
- MUST：core 侧 `PipelineStageConfig.inject_imported_context` 字段 + `_run_stage_skill` 注入（行为契约/意图锚点/被引用文件全文/清单）+ skip gate（test_execution_mode=pytest 短路，APPROVED_SKIPPED）
- MUST：deploy_to_app 对 skip 场景 reason 标注 + `regenerated_warnings`（Build Log 刷屏警告，§3.9 条件 2）
- MUST：前端 Factory 页含导入入口/文件勾选+意图输入/红字重写警告/门禁开关/手册弹窗/regenerated 警告展示
- 自动化验收：
  - `grep -c "import-repo" aiPlat-platform/api/routers/builder.py`（≥1）
  - `grep -c "_safe_extract_zip" aiPlat-platform/builder/builder_project_service.py`（≥2：定义 + 调用）
  - `grep -c "inject_imported_context" aiPlat-core/core/schemas_builder.py aiPlat-core/core/harness/execution/pipeline_engine.py`（≥2）
  - `grep -c "APPROVED_SKIPPED" aiPlat-core/core/harness/execution/pipeline_engine.py aiPlat-core/core/harness/execution/pipeline_eval.py`（≥2）
  - `grep -c "regenerated_warnings" aiPlat-platform/builder/builder_project_service.py`（≥1）
  - `grep -c "导入既有代码（L2）" aiPlat-management/frontend/src/pages/App/Factory/index.tsx`（≥1）
  - `python3 -m pytest aiPlat-platform/tests/test_l2_import_repo.py aiPlat-platform/tests/test_l2_import_helpers.py aiPlat-core/core/tests/unit/test_harness/test_l2_import_context.py -q`（≥34 passed）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.41 L3 增量合并引擎设计文档（2026-08-22）
- MUST：`docs/research/plan-app-factory-l3-incremental-engine.md` 存在（L3 设计：ImpactAnalyzer/DiffMerger/incremental_merge 策略/审批门禁/验收 10 项/约 3.25 天）
- MUST：设计文档含 `merge_strategy` 字段设计（full_rewrite 默认 / incremental_merge）+ 与 L2 衔接清单（§9）
- 自动化验收：
  - `ls docs/research/plan-app-factory-l3-incremental-engine.md`（存在）
  - `grep -c "merge_strategy" docs/research/plan-app-factory-l3-incremental-engine.md`（≥3：§3.2 字段 + §5 验收 + §9 衔接）
  - `grep -c "ImpactAnalyzer" docs/research/plan-app-factory-l3-incremental-engine.md`（≥3：§3.3 + §5 + §6）
  - `grep -c "DiffMerger" docs/research/plan-app-factory-l3-incremental-engine.md`（≥3：§3.5 + §5 + §6）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.42 L3 增量合并引擎实施（2026-08-22）
- MUST：`aiPlat-platform/builder/merge_engine.py` 存在（ImpactAnalyzer 影响面分析 + DiffMerger diff 预览/语法/接口验证/apply_merge 快照）
- MUST：`PipelineStageConfig` 含 `merge_strategy`（full_rewrite 默认 / incremental_merge）+ `merge_review_required`
- MUST：merge 端点（merge-preview/merge-previews/merge-apply）+ `_L3_INCREMENT_PROMPT`（增量行为契约：逐字节一致/UNCHANGED）+ rebuild 按 merge_strategy 选 prompt
- MUST：引擎 `_deploy_file_blocks` 剔除 `## UNCHANGED:` 标记（通用输出约定）
- MUST：前端 Factory 含修改模式单选 + 合并审批界面（逐文件 diff/通过/驳回）
- 自动化验收：
  - `grep -c "merge_strategy" aiPlat-core/core/schemas_builder.py`（≥2：字段定义 + 注释）
  - `grep -c "analyze_impact\|build_merge_preview\|apply_merge" aiPlat-platform/builder/merge_engine.py`（≥3）
  - `grep -c "merge-preview" aiPlat-platform/api/routers/builder.py`（≥1）
  - `grep -c "_L3_INCREMENT_PROMPT" aiPlat-platform/builder/builder_project_service.py`（≥2：定义 + 使用）
  - `grep -c "UNCHANGED" aiPlat-core/core/harness/execution/pipeline_engine.py`（≥1）
  - `grep -c "合并审批（L3" aiPlat-management/frontend/src/pages/App/Factory/index.tsx`（≥1）
  - `python3 -m pytest aiPlat-platform/tests/test_l3_merge_engine.py aiPlat-platform/tests/test_l3_merge_static.py -q`（17 passed）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.43 L3 评审 P0 暗坑补丁（2026-08-23）
- MUST：merge_apply 原子化（全部受影响文件 approved 才应用，缺失/驳回 → error code atomic_approval_required）
- MUST：哈希快照锁（rebuild 时对 imported/ 受影响文件 sha256 快照存 pre_gen_snapshot，merge_apply 前 verify_snapshot 不一致 → error code concurrent_modification）
- MUST：前端应用按钮常灰（全部通过才可点）+ 驳回 → 重新生成（handleRegenerateAfterReject）+ 确定性门禁红横幅（P0-03）
- MUST：P1-04 diff 噪音过滤（_categorize_hunk formatting/logic）+ P1-05 analyze-impact 端点 + 影响面取消二次确认
- 自动化验收：
  - `grep -c "atomic_approval_required" aiPlat-platform/builder/builder_project_service.py`（≥1）
  - `grep -c "pre_gen_snapshot" aiPlat-platform/builder/builder_project_service.py`（≥2：rebuild 写 + merge_apply 读）
  - `grep -c "def snapshot_affected_files\|def verify_snapshot" aiPlat-platform/builder/merge_engine.py`（≥2）
  - `grep -c "def _categorize_hunk" aiPlat-platform/builder/merge_engine.py`（≥1）
  - `grep -c "analyze-impact" aiPlat-platform/api/routers/builder.py`（≥1）
  - `grep -c "驳回文件需重新生成\|确定性门禁阻断" aiPlat-management/frontend/src/pages/App/Factory/index.tsx`（≥1）
  - `python3 -m pytest aiPlat-platform/tests/test_l3_merge_engine.py aiPlat-platform/tests/test_l3_merge_static.py -q`（25 passed）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.44 L4 多模块编排设计文档（2026-08-23）
- MUST：`docs/research/plan-app-factory-l4-multi-module.md` 存在（L4 设计：modules.json/CrossModuleAnalyzer/ModuleOrchestrator/契约门禁/验收 12 项/约 4.5 天）
- MUST：设计文档含模块级项目结构（modules.json 数据模型）+ 单模块隐式兼容（module_id=default）+ 与 L2/L3 衔接清单（§9）
- 自动化验收：
  - `ls docs/research/plan-app-factory-l4-multi-module.md`（存在）
  - `grep -c "modules.json" docs/research/plan-app-factory-l4-multi-module.md`（≥4：§1/§3.1 结构/§3.2/§5 验收）
  - `grep -c "CrossModuleAnalyzer" docs/research/plan-app-factory-l4-multi-module.md`（≥3：§3.3 + §5 + §6）
  - `grep -c "ModuleOrchestrator" docs/research/plan-app-factory-l4-multi-module.md`（≥3：§3.4 + §5 + §6）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.45 L4 多模块后端实施（2026-08-23）
- MUST：`aiPlat-platform/builder/cross_module.py` 存在（scan_module_contracts/analyze_cross_module/impact_closure/topological_order）
- MUST：模块 CRUD（create_modules/list_modules）+ import-repo 支持 module_id（default → legacy 布局，多模块 → module_repos）+ rebuild 支持 module_id
- MUST：cross-module-impact / module-orchestrate 端点（依赖顺序编排 + 未受影响模块不重跑）
- 自动化验收：
  - `grep -c "def scan_module_contracts\|def analyze_cross_module\|def impact_closure\|def topological_order" aiPlat-platform/builder/cross_module.py`（≥4）
  - `grep -c "async def create_modules\|async def module_orchestrate\|async def cross_module_impact" aiPlat-platform/builder/builder_project_service.py`（≥3）
  - `grep -c "module_id: str = \"default\"" aiPlat-platform/builder/builder_project_service.py`（≥2：import_repo + rebuild）
  - `grep -c "module-orchestrate" aiPlat-platform/api/routers/builder.py`（≥1）
  - `python3 -m pytest aiPlat-platform/tests/test_l4_cross_module.py aiPlat-platform/tests/test_l4_module_static.py -q`（17 passed）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.46 L4 前端 + 文档同步（2026-08-23）
- MUST：前端 Factory 含模块面板（声明/列表/导入/影响展示/编排结果）+ builderTeamApi 模块 API
- MUST：L4 设计文档状态 ✅ 已实施 + §10 实施记录（差异标注）
- MUST：操作手册含多模块编排（L4）章节
- 自动化验收：
  - `grep -c "多模块编排（L4）" aiPlat-management/frontend/src/pages/App/Factory/index.tsx`（≥1）
  - `grep -c "createModules\|listModules\|importModuleRepo\|crossModuleImpact\|moduleOrchestrate" aiPlat-management/frontend/src/services/builderTeamApi.ts`（≥5）
  - `grep -c "✅ \*\*已实施\*\*" docs/research/plan-app-factory-l4-multi-module.md`（≥1）
  - `grep -c "多模块编排（L4" docs/manuals/management-ui-operation-manual.md`（≥1）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.47 L4 v1.5 跨模块 merge 契约门禁（2026-08-23）
- MUST：`verify_changed_module_contracts`（cross_module.py）——依赖方（depended_by）引用的端点/实体在变更模块新版本中缺失 → broken 列表
- MUST：merge_preview 支持 module_id（记录 merge_module）+ 多模块时附加 cross_contracts；merge_apply 前 broken → error contract_gate_failed 阻断
- MUST：前端 mergePreview 带 module_id + 审批界面显示跨模块契约状态（断裂红横幅/通过绿条）
- 自动化验收：
  - `grep -c "def verify_changed_module_contracts" aiPlat-platform/builder/cross_module.py`（≥1）
  - `grep -c "contract_gate_failed" aiPlat-platform/builder/builder_project_service.py`（≥1）
  - `grep -c "merge_module" aiPlat-platform/builder/builder_project_service.py`（≥2：merge_preview 写 + merge_apply 读）
  - `grep -c "cross_contracts" aiPlat-management/frontend/src/pages/App/Factory/index.tsx`（≥2）
  - `python3 -m pytest aiPlat-platform/tests/test_l4_cross_module.py -q`（14 passed，含 TestContractGate 4 例）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.48 L4.5 数据库迁移编排设计文档（2026-08-23）
- MUST：`docs/research/plan-app-factory-l45-db-migration.md` 存在（L4.5 设计：SchemaExtractor/SchemaDiffAnalyzer/MigrationGenerator/破坏性门禁/验收 12 项/约 4.25 天）
- MUST：设计文档含迁移编排数据流（merge_apply → schema diff → 迁移预览审批）+ 破坏性变更定义（§3.4）+ 与 L2/L3/L4 衔接清单（§9）
- 自动化验收：
  - `ls docs/research/plan-app-factory-l45-db-migration.md`（存在）
  - `grep -c "SchemaExtractor" docs/research/plan-app-factory-l45-db-migration.md`（≥3：§3.3 + §5 + §6）
  - `grep -c "SchemaDiffAnalyzer" docs/research/plan-app-factory-l45-db-migration.md`（≥3：§3.4 + §5 + §6）
  - `grep -c "MigrationGenerator" docs/research/plan-app-factory-l45-db-migration.md`（≥3：§3.5 + §5 + §6）
  - `grep -c "destructive" docs/research/plan-app-factory-l45-db-migration.md`（≥4：§3.4 定义 + §3.5 + §3.8 + §5）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.49 L4.5 数据库迁移编排实施（2026-08-23）
- MUST：`aiPlat-platform/builder/schema_migration.py` 存在（extract_schema/diff_schema/generate_migration）
- MUST：迁移端点（migration-preview/migrations/apply/rollback）+ 破坏性迁移需显式确认（destructive_migration_requires_confirmation）+ 跨模块字段引用（_check_cross_module_fields）
- MUST：前端迁移面板（生成预览/up-down SQL/destructive 横幅/确认勾选/历史/回滚）
- 自动化验收：
  - `grep -c "def extract_schema\|def diff_schema\|def generate_migration" aiPlat-platform/builder/schema_migration.py`（≥3）
  - `grep -c "destructive_migration_requires_confirmation" aiPlat-platform/builder/builder_project_service.py`（≥1）
  - `grep -c "migration-preview" aiPlat-platform/api/routers/builder.py`（≥1）
  - `grep -c "数据库迁移（L4.5）" aiPlat-management/frontend/src/pages/App/Factory/index.tsx`（≥1）
  - `python3 -m pytest aiPlat-platform/tests/test_l45_migration.py aiPlat-platform/tests/test_l45_migration_static.py -q`（18 passed）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.50 L5 模块级 CI/CD 与灰度发布设计文档（2026-08-23）
- MUST：`docs/research/plan-app-factory-l5-cicd.md` 存在（L5 设计：版本化产物/发布状态机（building/ready/canary/full/rolled_back）/金丝雀灰度/回滚/验收 8 项/约 3 天）
- MUST：设计文档含发布状态机定义（§3.2）+ 与 infra deploy_service 衔接（§3.6）+ 与 L2/L3/L4/L4.5 衔接清单（§9）
- 自动化验收：
  - `ls docs/research/plan-app-factory-l5-cicd.md`（存在）
  - `grep -c "canary" docs/research/plan-app-factory-l5-cicd.md`（≥5：§3.2 状态机 + §3.5 + §5 + §7 + §9）
  - `grep -c "rolled_back" docs/research/plan-app-factory-l5-cicd.md`（≥3：§3.2 + §3.5 + §5）
  - `grep -c "releases/v" docs/research/plan-app-factory-l5-cicd.md`（≥2：§3.1 + §3.4）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.51 L5 发布流水线实施（2026-08-23）
- MUST：`aiPlat-platform/builder/release_engine.py` 存在（create_release/set_release_status/current 指针/状态机 building→ready→canary→full→rolled_back）
- MUST：发布端点（release/releases/canary/full/rollback）+ 迁移先行门禁（pending_migrations）+ infra 可选集成（AIPLAT_L5_INFRA_DEPLOY）
- MUST：前端发布区（版本徽标/金丝雀控制/回滚/estimated 提示）
- 自动化验收：
  - `grep -c "def create_release\|def set_release_status\|def _write_pointer" aiPlat-platform/builder/release_engine.py`（≥3）
  - `grep -c "_VALID_TRANSITIONS" aiPlat-platform/builder/release_engine.py`（≥1）
  - `grep -c "releases/{version}/canary" aiPlat-platform/api/routers/builder.py`（≥1）
  - `grep -c "pending_migrations" aiPlat-platform/builder/builder_project_service.py`（≥2：迁移门禁）
  - `grep -c "发布流水线（L5）" aiPlat-management/frontend/src/pages/App/Factory/index.tsx`（≥1）
  - `python3 -m pytest aiPlat-platform/tests/test_l5_release.py aiPlat-platform/tests/test_l5_release_static.py -q`（14 passed）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.52 L5 v2 infra 集成 + 金丝雀权重（2026-08-23）
- MUST：`infra_bridge.deploy_app_service`（core 桥接，standalone-safe no-op）+ `CoreFacade.deploy_app_service` re-export + platform 经 facade 调用（无 infra 直导）
- MUST：发布记录含 `canary_weight`（0/10/50/100；canary 设权重，full 强制 100，rollback 置 0）+ canary 端点支持 canary_weight
- 自动化验收：
  - `grep -c "def deploy_app_service" aiPlat-core/core/harness/infrastructure/infra_bridge.py aiPlat-core/core/api/core_facade.py`（≥2）
  - `grep -c "from core.api.core_facade import deploy_app_service" aiPlat-platform/builder/builder_project_service.py`（≥1）
  - `grep -c "from infra" aiPlat-platform/builder/builder_project_service.py`（=0，无直导）
  - `grep -c "canary_weight" aiPlat-platform/builder/release_engine.py`（≥4：create_release + canary/full/rollback）
  - `python3 -m pytest aiPlat-platform/tests/test_l5_release.py aiPlat-platform/tests/test_l5_release_static.py -q`（23 passed）
  - `python3 scripts/check_research_docs_freshness.py .`（exit 0）

### 1.53 安全降级审计事件（方案 B, 2026-08-23）
- MUST：`policy_gate` skill_load 权限规则 except 路径（权限解析器降级 fail-open）记录 `security_degraded` 审计事件——`execution_store.add_audit_log(action="security_degraded", kind="skill_permission_resolver_unavailable", status="warn", ...)` 含 tenant/actor/tool/skill/error 上下文
- MUST：审计为 best-effort（store 不可用静默跳过，`# noqa: cleanup-best-effort`），fail-open 行为不变（决策不受审计失败影响）
- 契约登记：边界契约 `01-architecture-contract.md` 附录 B + 治理契约 `05-governance-release-contract.md` §6 + run spec 五十二轮
- 自动化验收：
  - `grep -c "security_degraded" aiPlat-core/core/harness/infrastructure/gates/policy_gate.py`（≥2：action + kind）
  - `grep -c "security_degraded" aiPlat-core/docs/contracts/05-governance-release-contract.md`（≥1：§6）
  - `grep -c "安全降级审计事件" aiPlat-core/docs/contracts/01-architecture-contract.md`（≥1：附录 B 登记）
  - `grep -c "security_degraded" aiPlat-core/core/tests/unit/test_gates/test_policy_gate_skill_load_permissions.py`（≥1：test_security_degraded_audit_wired）
  - `python3 -m pytest aiPlat-core/core/tests/unit/test_gates/test_policy_gate_skill_load_permissions.py -q`（3 passed，需可写 AIPLAT_HOME）

### 1.54 G6 CC/Codex hooks 协议桥（2026-08-23）
- MUST：`cc_bridge.py` 存在——`load_hooks_json`（CC 嵌套 `{"hooks":{Event:[...]}}` + Codex 数组 `[{hook_event_name, command}]` 双格式解析，非 command handler 跳过）+ `CCHookBridge`（command handler 执行器：shell=False shlex 拆词、超时、stdout/stderr 捕获、结构化结果）+ `register_cc_hooks`/`load_cc_hooks_if_configured`
- MUST：`cc_bridge_rules.py` 数据驱动映射表（CC 7/30 + Codex 4/10 事件→HookPhase）；unmapped 事件 fail-open 不静默执行
- MUST：`HookManager.__init__` 配置存在时装载（`~/.aiplat/hooks.json` / `AIPLAT_CC_HOOKS_PATH`，默认关）；command not found/timeout 不抛（fail-open）
- 契约登记：边界契约 `01-architecture-contract.md` 附录 B（G6 条目）+ run spec 五十三轮
- 自动化验收：
  - `grep -c "def load_hooks_json\|def register_cc_hooks\|def load_cc_hooks_if_configured\|class CCHookBridge" aiPlat-core/core/harness/infrastructure/hooks/cc_bridge.py`（≥4）
  - `grep -c "load_cc_hooks_if_configured" aiPlat-core/core/harness/infrastructure/hooks/hook_manager.py`（≥1：生产接线）
  - `grep -c "SessionStart\|PreToolUse\|PostToolUse\|SessionEnd" aiPlat-core/core/harness/infrastructure/hooks/cc_bridge_rules.py`（≥4：映射表）
  - `grep -c "G6 CC/Codex hooks 协议桥" aiPlat-core/docs/contracts/01-architecture-contract.md`（≥1：附录 B 登记）
  - `python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_cc_hooks_bridge.py -q`（15 passed）

### 1.55 stdio JSON-RPC 持久内核（P0-a, 2026-08-24）
- MUST：`core/acp/stdio_server.py` 存在——`StdioKernel`（JSON-RPC 2.0 over stdio JSONL）+ `handle_request` 分发 + `_event_loop` 主循环；方法：initialize/shutdown/thread/start/status/events/resume/approve/reject/rollback/cancel
- MUST：Thread 映射到已有能力——`thread/start`→`create_pipeline_session().start`、`thread/approve|reject`→`session.approve|reject`（HITL）、`thread/events`→`PipelineRunStore.list_run_events`、`thread/cancel`→`cancel_pipeline`
- MUST：JSON-RPC 2.0 错误信封（-32700 parse/-32601 method not found/-32602 invalid params/-32603 internal）；背压 `-32001`（并发超限建议指数退避，对齐 codex）
- MUST：独立进程入口 `python -m core.acp.stdio_server`（外部程序/CI spawn 驱动）；`CoreFacade.start_stdio_kernel` + server 启动 env 门控（`AIPLAT_STDIO_KERNEL=1`）
- 契约登记：边界契约 `01-architecture-contract.md` 附录 B（P0-a 条目）+ run spec 五十五轮
- 自动化验收：
  - `grep -c "class StdioKernel\|def handle_request\|def _event_loop\|thread_start\|thread_approve" aiPlat-core/core/acp/stdio_server.py`（≥6）
  - `grep -c "def start_stdio_kernel" aiPlat-core/core/api/core_facade.py`（≥1）
  - `grep -c "start_stdio_kernel" aiPlat-core/core/server.py`（≥1：生产接线）
  - `grep -c "P0-a" aiPlat-core/docs/contracts/01-architecture-contract.md`（≥1：附录 B 登记）
  - `python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_stdio_kernel.py -q`（13 passed）
  - `python3 -c "import subprocess,sys; p=subprocess.run([sys.executable,'-m','core.acp.stdio_server'],input='{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{}}\\n{\"jsonrpc\":\"2.0\",\"id\":99,\"method\":\"shutdown\",\"params\":{}}\\n',capture_output=True,text=True,timeout=30,cwd='aiPlat-core'); assert p.returncode==0 and 'protocol_version' in p.stdout and 'shutdown' in p.stdout"`（进程级 smoke：initialize+shutdown 往返）

### 1.56 竞品会话/记忆导入（P0-b, 2026-08-24）
- MUST：`core/harness/memory/import_claude_sessions.py` 存在——`parse_claude_session`（Claude JSONL user/assistant 配对、system-reminder 跳过、text/block-list content 提取）+ `find_claude_sessions`（~/.claude/projects|transcripts 递归查找）+ `import_claude_sessions`（→ MemoryManager.save_interaction，source_tag=claude_import + provenance 溯源）
- MUST：`CoreFacade.import_claude_memories` facade + platform `POST /platform/memory/import` + `GET /platform/memory/import/status`（经 CoreFacade 调用，require_auth）
- 契约登记：边界契约 `01-architecture-contract.md` 附录 B（P0-b 条目）+ run spec 五十六轮
- 自动化验收：
  - `grep -c "def parse_claude_session\|def find_claude_sessions\|def import_claude_sessions" aiPlat-core/core/harness/memory/import_claude_sessions.py`（≥3）
  - `grep -c "def import_claude_memories" aiPlat-core/core/api/core_facade.py`（≥1）
  - `grep -c "memory/import" aiPlat-platform/api/routers/memory_import.py aiPlat-platform/api/rest/routes.py`（≥2：端点 + 注册）
  - `grep -c "P0-b" aiPlat-core/docs/contracts/01-architecture-contract.md`（≥1：附录 B 登记）
  - `python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_import_claude_sessions.py -q`（10 passed）

### 1.57 SDK stdio 内核客户端（P1, 2026-08-24）
- MUST：`aiplat-sdk/aiplat/stdio.py` 存在——`StdioKernelClient`（spawn `python -m core.acp.stdio_server` + JSON-RPC over stdio：thread/start|status|events|resume|approve|reject|rollback|cancel + stream_events 流式监听 + 错误信封）+ 可注入 transport（测试用）
- MUST：`StdioKernelClient`/`StdioKernelError` 从 `aiplat.__init__` 导出；README 示例含 stdio 用法
- 契约登记：边界契约 `01-architecture-contract.md` 附录 B（P1 SDK 条目）+ run spec 五十七轮
- 自动化验收：
  - `grep -c "class StdioKernelClient\|async def thread_start\|async def thread_approve\|async def stream_events" aiplat-sdk/aiplat/stdio.py`（≥4）
  - `grep -c "StdioKernelClient" aiplat-sdk/aiplat/__init__.py`（≥1：导出）
  - `cd aiplat-sdk && python3 -m pytest tests/test_stdio_client.py -q`（8 passed，含真实内核集成）
  - `grep -c "P1 SDK" aiPlat-core/docs/contracts/01-architecture-contract.md`（≥1：附录 B 登记）

### 1.58 OS 原生沙箱执行器（P1, 2026-08-24）
- MUST：`core/harness/infrastructure/os_sandbox.py` 存在——`detect_sandbox_mode`（bwrap/seatbelt/无探测 + AIPLAT_SANDBOX 开关）+ `build_os_sandbox_cmd`（bwrap：--ro-bind 系统路径 + --bind 工作区/tmp + --unshare-net 可选；seatbelt：sandbox-exec deny-default profile）+ fail-open fallback（无沙箱返回原命令）
- MUST：接线——`StageSandbox.run` 包装 worker 子进程（`sandbox.py`）+ `CoreFacade.get_os_sandbox_status`（诊断）
- 契约登记：边界契约 `01-architecture-contract.md` 附录 B（P1 OS 沙箱条目）+ run spec 五十八轮
- 自动化验收：
  - `grep -c "def detect_sandbox_mode\|def build_os_sandbox_cmd\|def sandbox_env_ready" aiPlat-core/core/harness/infrastructure/os_sandbox.py`（≥3）
  - `grep -c "build_os_sandbox_cmd" aiPlat-core/core/harness/execution/sandbox.py`（≥1：StageSandbox 接线）
  - `grep -c "def get_os_sandbox_status" aiPlat-core/core/api/core_facade.py`（≥1）
  - `grep -c "P1 OS 沙箱" aiPlat-core/docs/contracts/01-architecture-contract.md`（≥1：附录 B 登记）
  - `python3 -m pytest aiPlat-core/core/tests/unit/test_harness/test_os_sandbox.py -q`（10 passed）

### 1.59 前端 coding 场景：文件 Checkpoint UI（2026-08-24，对标报告 §16.3 ⚠️未变项闭环）
- MUST：`FileCheckpoints.tsx` 存在——checkpoint 列表（session/路径过滤 + 刷新）+ 查看内容（Modal + 代码块渲染）+ 恢复（confirm + restore 调用），经 `checkpointApi`（services 统一出口）调 `/platform/execution/file-checkpoints`
- MUST：路由注册（`App.tsx` `core/checkpoints`）+ 侧边栏菜单（`pageManifest.ts`）
- 契约登记：run spec 六十轮（前端 UI 属展示层，无 backend 契约变更）
- 自动化验收：
  - `grep -c "checkpointApi" aiPlat-management/frontend/src/services/coreApi.ts aiPlat-management/frontend/src/services/index.ts`（≥2：API 定义 + 统一出口）
  - `grep -c "core/checkpoints" aiPlat-management/frontend/src/App.tsx aiPlat-management/frontend/src/pageManifest.ts`（≥2：路由 + 菜单）
  - `cd aiPlat-management/frontend && npx tsc --noEmit`（0 error）+ `npm run build`（exit 0）

### 1.60 continuable 子代理编排（2026-08-24，对标报告 §21.1 "continuable 编排仍缺"闭环）
- MUST：`coordinator.continue_execution(instance_id, message)` 存在——复用 `execute_single` 创建的 agent（`SubagentInstance.agent_ref`），向同一会话追加消息重执行（conversational agent `_conversation_history` 天然多轮）；fail-loud（未知 instance / 无 agent_ref → 明确错误）
- MUST：`execute_single` 返回真实 instance key（`SubagentResult.instance_id`，格式 `{session_id}:{name}`，非 `inproc:{name}` 占位）
- MUST：`InProcessProvider.continuation` 委托 coordinator（`capabilities.continuation=True` 名实相符）；`coordinator.send_message` → in_process continuation 成功
- 契约登记：边界契约 `01-architecture-contract.md` 附录 B（continuable 条目）+ run spec 六十一轮
- 自动化验收：
  - `grep -c "async def continue_execution" aiPlat-core/core/apps/agents/subagent/coordinator.py`（≥1）
  - `grep -c "agent_ref" aiPlat-core/core/apps/agents/subagent/config.py`（≥1：SubagentInstance 保留 agent）
  - `grep -c "instance_id=_inst_key\|instance_id=getattr" aiPlat-core/core/apps/agents/subagent/coordinator.py aiPlat-core/core/apps/agents/subagent/providers.py`（≥2：真实 key 返回 + provider 使用）
  - `grep -c "continuable 编排" aiPlat-core/docs/contracts/01-architecture-contract.md`（≥1：附录 B 登记）
  - `python3 -m pytest aiPlat-core/core/tests/unit/test_agents/test_subagent_providers.py -q`（24 passed）

### 1.61 模型 provider 生态广度（2026-08-24，对标报告 §21.1 "家族数远少于 38"收窄）
- MUST：`aiPlat-infra/config/providers.yaml` 含 **≥14 provider**（基础 6 + 新增 qwen/groq/mistral/cohere/cerebras/together/xai/novita 8 家族）——全部 OpenAI 兼容端点（复用 openai_compatible.py，零代码）
- MUST：所有 external + requires_api_key 的 provider 带 `env_key`（API key 契约）；`base_url_env` 缺省走 openai_compatible 默认 /v1（自动补全）
- MUST：`ModelManager._api_provider_ids()` 可发现 ≥12 外部 API provider（YAML 驱动，非 fallback 硬编码集）
- 契约登记：run spec 六十二轮（infra 配置驱动，无 harness 契约变更）
- 自动化验收：
  - `python3 -c "import yaml; d=yaml.safe_load(open('aiPlat-infra/config/providers.yaml')); assert len(d['providers'])>=14; print('OK')"`
  - `python3 -c "import sys; sys.path.insert(0,'aiPlat-infra'); from infra.management.model.manager import _api_provider_ids; ids=_api_provider_ids(); assert all(x in ids for x in ['qwen','groq','mistral','cohere','cerebras','together','xai','novita']); print('OK')"`
  - `cd aiPlat-infra && python3 -m pytest infra/tests/unit/test_model_selection.py -q`（16 passed，含 2 新增生态广度防回归）

### 1.62 aiplat exec 单次执行 CLI（2026-08-25，Codex-Harness 借鉴 P2 "codex exec 对齐"）
- MUST：`aiplat-sdk/aiplat/exec.py` 存在——`exec_script`（--script 零 LLM subprocess：入口白名单 {bash,sh,python3,python}，白名单外 exit_code=125 fail-closed）+ `exec_pipeline`（经 `StdioKernelClient` spawn stdio 内核 → thread/start → 轮询 thread/status 直到 done/failed/cancelled/paused，超时 best-effort thread/cancel）+ `main`（argparse，requirement 或 --script 至少其一，--json 输出）
- MUST：pyproject `[project.scripts] aiplat = aiplat.exec:main`；`aiplat.__init__` 导出 `exec_script`/`exec_pipeline`/`exec_main`
- 契约登记：边界契约 `01-architecture-contract.md` 附录 B（exec CLI 条目）+ run spec 六十六轮
- 自动化验收：
  - `grep -c "def exec_script" aiplat-sdk/aiplat/exec.py`（≥1）
  - `grep -c "def exec_pipeline" aiplat-sdk/aiplat/exec.py`（≥1）
  - `grep -c "aiplat = \"aiplat.exec:main\"" aiplat-sdk/pyproject.toml`（≥1：console script 注册）
  - `grep -c "exec_script" aiplat-sdk/aiplat/__init__.py`（≥1：SDK 导出）
  - `cd aiplat-sdk && python3 -m pytest tests/test_exec_cli.py -q`（8 passed）
  - `python3 -m aiplat.exec --script "python3 -c 'print(42)'" --json`（exit 0 + status ok）


### 1.64 渠道广度延伸四批（2026-08-25，渠道 18→22 对齐 Hermes 22 收官）
- MUST：`aiPlat-app/channels/adapters/` 含 **22 渠道**（3 内置 + 19 扩展）——新增 google_chat/homeassistant/irc/ntfy 4 适配器（Google Chat event / Home Assistant 事件 / IRC PRIVMSG / ntfy.sh publish）
- MUST：`ChannelType` 补 GOOGLE_CHAT/HOMEASSISTANT/IRC/NTFY 枚举 + `ADAPTERS` 注册；`get_channel_adapter(name)` 动态解析 22 渠道（未知渠道 ValueError）
- 契约登记：边界契约 `01-architecture-contract.md` 附录 B（渠道四批收官）+ run spec 六十七轮
- 自动化验收：
  - `python3 -c "import sys; sys.path.insert(0,'aiPlat-app'); from channels.adapter import ChannelType; assert len(ChannelType)==22; print('OK')"`
  - `python3 -c "import sys; sys.path.insert(0,'aiPlat-app'); from channels.adapters import ADAPTERS; assert len(ADAPTERS)==19; print('OK')"`
  - `cd aiPlat-app && python3 -m pytest tests/test_cli_and_channels.py -q`（25 passed）


### 1.63 模型 provider 生态广度二批（2026-08-25，向 Hermes 38 方向继续收窄）
- MUST：`aiPlat-infra/config/providers.yaml` 含 **≥22 provider**（基础 6 + 2026-08-24 首批 8 + 2026-08-25 二批 8：siliconflow/moonshot/minimax/zhipu/baichuan/stepfun/deepinfra/fireworks）——全部 OpenAI 兼容端点（复用 openai_compatible.py，零代码）
- MUST：所有 external + requires_api_key 的 provider 带 `env_key`（API key 契约）；`base_url_env` 缺省走 openai_compatible 默认 /v1
- MUST：`ModelManager._api_provider_ids()` 可发现 ≥20 外部 API provider（YAML 驱动，非 fallback 硬编码集）
- 契约登记：run spec 六十八轮（infra 配置驱动，无 harness 契约变更）
- 自动化验收：
  - `python3 -c "import yaml; d=yaml.safe_load(open('aiPlat-infra/config/providers.yaml')); assert len(d['providers'])>=22; print('OK')"`
  - `python3 -c "import sys; sys.path.insert(0,'aiPlat-infra'); from infra.management.model.manager import _api_provider_ids; ids=_api_provider_ids(); assert all(x in ids for x in ['siliconflow','moonshot','minimax','zhipu','baichuan','stepfun','deepinfra','fireworks']); print('OK')"`
  - `cd aiPlat-infra && python3 -m pytest infra/tests/unit/test_model_selection.py -q`（16 passed，含生态广度防回归升级 22 家族）


### 1.65 Skill 开放生态收尾（2026-08-25，G8 agentskills.io 对接完善）
- MUST：`GET /skills/marketplace/external` 端点存在（`aiPlat-platform/api/routers/skill_marketplace.py`）——接线 `SkillMarketplace.discover_external`（P1-A5 已有，此前 0 生产 caller）；`source=agentskills.io` 支持、`limit` 参数；unsupported source → 400
- MUST：外部源不可达返回 error 列表（best-effort，不抛异常、不阻断本地 marketplace）；`supports_external_source("agentskills.io")` 为 True
- 契约登记：边界契约 `01-architecture-contract.md` 附录 B（Skill 生态收尾）+ run spec 六十九轮
- 自动化验收：
  - `grep -c "marketplace/external" aiPlat-platform/api/routers/skill_marketplace.py`（≥1：端点注册）
  - `grep -c "discover_external" aiPlat-platform/api/routers/skill_marketplace.py`（≥1：接线）
  - `cd aiPlat-platform && python3 -m pytest tests/test_skill_marketplace_external.py -q`（5 passed）

### 1.66 模型 provider 生态广度三批（2026-08-25，向 Hermes 38 方向继续收窄）
- MUST：`aiPlat-infra/config/providers.yaml` 含 **≥30 provider**（基础 6 + 一批 8 + 二批 8 + 三批 8：gemini/nvidia/huggingface/upstage/arcee/zai/xiaomi/nous）——全部 OpenAI 兼容端点（复用 openai_compatible.py，零代码）
- MUST：所有 external + requires_api_key 的 provider 带 `env_key`（API key 契约）
- MUST：`ModelManager._api_provider_ids()` 可发现 ≥28 外部 API provider（YAML 驱动，非 fallback 硬编码集）
- 契约登记：run spec 七十轮（infra 配置驱动，无 harness 契约变更）
- 自动化验收：
  - `python3 -c "import yaml; d=yaml.safe_load(open('aiPlat-infra/config/providers.yaml')); assert len(d['providers'])>=30; print('OK')"`
  - `python3 -c "import sys; sys.path.insert(0,'aiPlat-infra'); from infra.management.model.manager import _api_provider_ids; ids=_api_provider_ids(); assert all(x in ids for x in ['gemini','nvidia','huggingface','upstage','arcee','zai','xiaomi','nous']); print('OK')"`
  - `cd aiPlat-infra && python3 -m pytest infra/tests/unit/test_model_selection.py -q`（16 passed，含生态广度防回归升级 30 家族）

### 1.67 知识管理审计 REAL 项修复（2026-08-25，P2-1/P2-3/P2-4/Q3）
- MUST：quality gate 真正降级——`retriever.py` gate 块在策略分支前执行；gate 失败 + `AIPLAT_DEEP_RESEARCH_ENABLED` → `_ddg_search` web 结果并入（source_category=web_fallback），否则仅打标记
- MUST：`knowledge-extraction` 模板注册 prompt_loader（`_sync_resolve` 可解析 + ${chunk_text} 变量替换）；`EntityExtractor._effective_class_types` 域本体配置驱动（无域回退默认集）
- MUST：`DomainRouter._t1_label_match`/`_t2_embed_score` 共享助手存在（classify/suggest/per_domain_cost 复用）
- MUST：`knowledge_abox_builder._map_to_domain_class`（wiki category→域 TBox 类）+ `_add_data_validated`（prop 域 TBox 校验）
- 契约登记：边界契约 `01-architecture-contract.md` 附录 B（知识管理修复）+ run spec 七十一轮
- 自动化验收：
  - `grep -c "_add_data_validated" aiPlat-core/core/harness/knowledge/knowledge_abox_builder.py`（≥6）
  - `grep -c "_t1_label_match\|_t2_embed_score" aiPlat-core/core/harness/knowledge/domain_router.py`（≥4）
  - `grep -c "knowledge-extraction" aiPlat-core/core/harness/knowledge_pipeline/extractor.py`（≥1）
  - `cd aiPlat-core && python3 -m pytest core/tests/unit/test_harness/test_knowledge/test_knowledge_audit_p2.py -q`（10 passed）

### 1.68 治理/架构路线图 REAL 项修复（2026-08-25，P3 图索引 + roadmap §0.2/§0.3）
- MUST：`code_graph.py` 增量同步含新文件发现（未索引 .py 文件浅层入图，≤100 上限）
- MUST：`scripts/coupling_metrics.py` 存在（AST import-degree：avg_degree/max_degree(non-agg)/top-20 + `--baseline` ratchet + `--write-baseline`）；`scripts/baselines/coupling_baseline.json` 已生成
- MUST：`core/harness` 一级子目录全量 BOUNDARY.yaml（48/48）；架构守卫 §94b 检查缺 BOUNDARY 目录 FAIL
- MUST：记忆测试 6 文件导入路径迁移 `harness.memory.*` → `core.harness.memory.*`（可收集）
- 契约登记：边界契约 `01-architecture-contract.md` 附录 B（治理修复）+ run spec 七十二轮
- 自动化验收：
  - `grep -c "new_files" aiPlat-core/core/harness/knowledge/code_graph.py`（≥2：发现 + 上限）
  - `grep -c "avg_degree" scripts/coupling_metrics.py`（≥2）
  - `find aiPlat-core/core/harness -maxdepth 1 -name BOUNDARY.yaml | grep -v __pycache__ | wc -l` 与 `ls -d aiPlat-core/core/harness/*/ | grep -v __pycache__ | wc -l` 相等
  - `grep -c "harness.memory" aiPlat-core/core/tests/unit/test_harness/test_memory/*.py` → 0
  - `python3 scripts/coupling_metrics.py --baseline scripts/baselines/coupling_baseline.json` → baseline OK
