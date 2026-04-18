---
title: Roadmap 全量目标 Gap 清单（按 aiPlat_arch_vs_hermes.md）
date: 2026-04-18
source_of_truth: /sessions/69df99acf22671cacf117ebb/workspace/aiPlat_arch_vs_hermes.md
acceptance: 必须有自动化测试（pytest/CI/前端 build）
---

> 说明：本文以 `aiPlat_arch_vs_hermes.md` 的 Roadmap-0~4（PR-R*-*）为唯一验收清单，对照当前仓库代码现状给出 ✅/⚠️/🔧/❌，并为每条补齐 Evidence（代码入口/测试或 CI）。

## 状态标记
- ✅ 已实现：代码存在且有验证方式（测试/CI/可运行命令）
- ⚠️ 部分实现：主链路可用，但缺少文档要求的关键子项或缺少自动化验收
- 🔧 结构存在：已有框架/占位，但未真正接通或功能缺失较大
- ❌ 未实现：未找到对应实现

---

# Roadmap-0：基础契约统一

## PR-R0-1：统一 ExecutionRequest/ExecutionResult 契约
**目标（文档）**：所有入口（Agent/Skill/Tool/cron/gateway）返回一致结构，失败原因规范化为 `error{code,message}`，tool 执行也带 `execution_id/trace_id`。

**当前状态**：✅

**Evidence**
- 统一执行入口：`aiPlat-core/core/harness/integration.py: HarnessIntegration.execute()`
- Gateway 入口：`aiPlat-core/core/server.py: POST /api/core/gateway/execute`
- Tool 执行返回携带 execution_id/trace_id：`aiPlat-core/core/harness/integration.py: _execute_tool()`
- 错误归一化：`aiPlat-core/core/harness/integration.py: _normalize_error()`（对外 `error={code,message}` + `error_message`，并保留 `error_detail` 兼容别名）
- ExecutionStore 持久化 error_code：`aiPlat-core/core/services/execution_store.py`（schema v17，agent/skill executions error_code）
- UI 展示：`aiPlat-management/frontend/src/pages/Diagnostics/Links/Links.tsx`、各 Execute*Modal
- Commit：`928bd50 feat: unify execution error contract (error object + error_message)`

**自动化验证**
- `aiPlat-core/.github/workflows/kernel-static-scan.yml`（CI）
- `pytest -q aiPlat-core/core/tests/integration/test_gateway_execute_api.py`

---

## PR-R0-2：syscalls 事件模型规范化 + 可搜索
**目标（文档）**：tool/llm/skill syscall 统一事件 schema，落盘+索引，可检索/统计。

**当前状态**：✅

**Evidence**
- syscall_events 表与索引：`aiPlat-core/core/services/execution_store.py`（Migration v6/v10 + v21 增强维度）
- 查询 API（core）：`aiPlat-core/core/server.py: GET /api/core/syscalls/events`（支持 error_code/target_type/target_id 过滤）
- 统计 API（core）：`aiPlat-core/core/server.py: GET /api/core/syscalls/stats`（TopN/分布/趋势 + error_code）
- management 代理：`aiPlat-management/management/api/diagnostics.py: GET /api/diagnostics/syscalls/core`
- 前端 Syscalls 页：`aiPlat-management/frontend/src/pages/Diagnostics/Syscalls/Syscalls.tsx`
- Commit：`e1d0e2e feat: add syscall dimensions and error_code stats`

**自动化验证**
- `pytest -q aiPlat-management/tests/test_diagnostics_syscalls.py`
- `pytest -q aiPlat-core/core/tests/integration/test_syscall_stats_error_codes.py`

---

# Roadmap-1：Prompt/Context 子系统

## PR-R1-1：PromptAssembler 完整化（稳定层缓存 + 临时层 overlay）
**目标（文档）**：
- `PromptAssembler.build()` 输出 `stable_system_prompt` + `ephemeral_overlay`
- stable prompt 有缓存 key（agent_id + prompt_version + workspace_context_hash）

**当前状态**：✅

**Evidence**
- PromptAssembler：`aiPlat-core/core/harness/assembly/prompt_assembler.py`
  - 输出：`stable_system_prompt` + `ephemeral_overlay` + `stable_cache_key` + `workspace_context_hash`
  - 缓存：内置 `_STABLE_PROMPT_CACHE`（基于 agent_id/prompt_version/workspace_context_hash）
- Commit：`7b6055b feat: P0 roadmap prompt/context/session search hardening`

**自动化验证**
- `pytest -q aiPlat-core/core/tests/integration/test_phaseR1_prompt_assembler_layers_cache.py`

---

## PR-R1-2：项目上下文文件（AGENTS.md/AIPLAT.md）支持 + 注入扫描
**目标（文档）**：支持上下文文件查找策略 + 注入扫描；命中高危时阻断或降级（可配置）。

**当前状态**：✅

**Evidence**
- ContextEngine：`aiPlat-core/core/harness/context/engine.py`
  - 查找：`AGENTS.md / AIPLAT.md / .aiplat.md`
  - 注入扫描：invisible unicode + 扩展 risk patterns（exfil/URL/编码/私钥等）
  - 策略：`AIPLAT_PROJECT_CONTEXT_POLICY`（block/warn/truncate/approval_required）
  - 审计：写入 `syscall_events(kind=context,name=project_context_scan)`
- Commit：`9978f51 feat: project context injection policy and audit`

**自动化验证**
- `pytest -q aiPlat-core/core/tests/unit/test_harness/test_context_engine_project_context_policy.py`

---

## PR-R1-3：ContextEngine 插拔（压缩/检索/RAG 抽象层）
**目标（文档）**：should_compact/compact/get_status；默认压缩；可选 RAG/LCM。

**当前状态**：✅

**Evidence**
- `aiPlat-core/core/harness/context/engine.py: ContextEngine / DefaultContextEngine`
- Commit：`7b6055b feat: P0 roadmap prompt/context/session search hardening`

**自动化验证**
- `pytest -q aiPlat-core/core/tests/unit/test_harness/test_context_engine_compaction.py`

---

# Roadmap-2：Tool Runtime 治理

## PR-R2-1：Tool Registry 收敛 + Toolset（能力包）体系化
**当前状态**：✅

**Evidence**
- ToolRegistry：`aiPlat-core/core/apps/tools/base.py: ToolRegistry`
- Toolsets：`aiPlat-core/core/harness/tools/toolsets.py`
- syscalls 强制治理入口：`aiPlat-core/core/harness/syscalls/tool.py`
- 可用性：`BaseTool.check_available()` + `ToolRegistry.get_availability()` + `/api/core/tools?available_only=true`
- toolset 覆盖：新增 `write_repo/web/browser/mcp_readonly` 并支持 prefix allow（mcp.*）
- Commit：`21a7bb2 feat: tool availability and richer toolsets`

**自动化验证**
- `pytest -q aiPlat-core/core/tests/integration/test_tools_availability_api.py`

---

## PR-R2-2：MCP 风险分级与强制最小权限
**当前状态**：✅

**Evidence**
- MCP policy 元数据：`aiPlat-core/core/management/mcp_manager.py`（allowed_tools + risk_level/tool_risk/approval_required/prod_allowed）
- prod stdio 限制：`aiPlat-core/core/apps/mcp/runtime.py`（prod 下 stdio 需要 prod_allowed）
- tool 风险/审批：`aiPlat-core/core/apps/mcp/adapter.py` + `aiPlat-core/core/harness/syscalls/tool.py`

**自动化验证**
- `pytest -q aiPlat-core/core/tests/integration/test_mcp_prod_stdio_denied_audit.py`（prod stdio deny + syscall_event）

---

## PR-R2-3：文件工具工程化（去重/限额/一致性检测）
**当前状态**：✅

**Evidence**
- `aiPlat-core/core/apps/tools/base.py: FileOperationsTool`
- Commit：`83b1bec feat: harden file_operations tool with cache and mtime guard`

**自动化验证**
- `pytest -q aiPlat-core/core/tests/unit/test_tools/test_file_operations_tool.py`

---

# Roadmap-3：多入口与长期运行

## PR-R3-1：Jobs/Cron 成为一等公民
**当前状态**：✅

**Evidence**
- Scheduler：`aiPlat-core/core/management/job_scheduler.py`
  - 通过 HarnessIntegration 执行
  - job/job_runs 落库：`aiPlat-core/core/services/execution_store.py`（Migration v12+）
  - webhook delivery + retry/backoff（best-effort）

**主要 Gap**
- 已补齐：delivery DLQ + API + management UI + tests

**自动化验证**
- `pytest -q aiPlat-core/core/tests/integration/test_jobs_delivery_dlq.py`

---

## PR-R3-2：Gateway（IM/机器人）入口适配层
**当前状态**：✅

**Evidence**
- `aiPlat-core/core/server.py: POST /api/core/gateway/execute`
- pairing/tokens：`/api/core/gateway/pairings`、`/api/core/gateway/tokens`
- slack adapters：`/api/core/gateway/slack/command`、`/api/core/gateway/slack/events`
- 测试：`pytest -q aiPlat-core/core/tests/integration/test_gateway_execute_api.py`
- Commit：`2a9afd5`（pairing/auth）、`3ec196e`（webhook adapter）、`9948972`（slack adapters）

**自动化验证**
- `pytest -q aiPlat-core/core/tests/integration/test_gateway_pairing_and_auth.py`
- `pytest -q aiPlat-core/core/tests/integration/test_gateway_slack_adapter.py`

---

# Roadmap-4：学习闭环

## PR-R4-1：Skill 生态升级为“技能包”（渐进披露 + 自修复）
**当前状态**：✅

**Evidence**
- Skill Packs：`aiPlat-core/core/services/execution_store.py`（skill_packs/versions/installs）
- API 与 materialize：`aiPlat-core/core/server.py`（/skill-packs/* + install->workspace）
- SKILL.md 预览：`GET /api/core/workspace/skills/{id}/skill-md`
- workspace 引用文件/索引：`GET /api/core/workspace/skills/{id}/files`、`GET /api/core/workspace/skills/{id}/revisions`
- 学习闭环建议：`POST /api/core/learning/autocapture/to_skill_evolution`
- 测试：`pytest -q aiPlat-core/core/tests/integration/test_skill_packs_api.py`
- Commit：`a10d967 feat: skill references/revisions and skill_evolution drafts`

**自动化验证**
- `pytest -q aiPlat-core/core/tests/integration/test_workspace_skill_files_and_revisions_api.py`
- `pytest -q aiPlat-core/core/tests/integration/test_learning_autocapture_to_skill_evolution.py`

---

## PR-R4-2：Memory（长期记忆）与 Session Search（跨会话检索）
**当前状态**：✅

**Evidence**
- long-term memory：`aiPlat-core/core/services/execution_store.py`（long_term_memories + FTS）
- API：`aiPlat-core/core/server.py`（/memory/longterm + search）
- 测试：`pytest -q aiPlat-core/core/tests/integration/test_long_term_memory_api.py`
- Session Search（跨会话检索）：`aiPlat-core/core/services/execution_store.py`（memory_messages + memory_messages_fts）
- API：`aiPlat-core/core/server.py`（POST /api/core/memory/search）
- 写入执行链路：`aiPlat-core/core/harness/integration.py`（执行完成后 add_memory_message）
- 测试：`pytest -q aiPlat-core/core/tests/integration/test_memory_sessions_persistent_api.py`

**主要 Gap**
- 无（已达到清单要求）
3. 权限/隐私：按 user/tenant 范围隔离与审计；
4. 自动化测试：跨 session 写入→检索→注入到 prompt 的可验证闭环。

---

# 建议的推进顺序（满足“全量目标 + 必须有自动化测试”）

## P0（最先做，能显著提升稳定性/可验收性）
1. R1-1 PromptAssembler 完整化（稳定层/overlay/缓存 key）+ tests
2. R1-3 ContextEngine 压缩最小实现（should_compact/compact/get_status）+ tests
3. R4-2 Session Search（数据模型 + API + 注入策略 + tests）

## P1（治理与可运维）
1. R0-2 syscall_events 统计/聚合接口 + UI（TopN/趋势）+ tests
2. R2-3 FileOperations 工程化（去重/mtime/二进制/设备文件）+ tests
3. R3-1 Jobs：DLQ/失败策略/审计 UI + tests

## P2（多入口与更完整生产化）
1. R3-2 Gateway：pairing/auth/tenant + 渠道适配（Slack/飞书/企业微信）+ tests
2. R4-1 自修复/自动沉淀（learning→skill pack/skill 更新）+ tests
