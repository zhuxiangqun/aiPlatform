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
