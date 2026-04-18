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

**当前状态**：⚠️（已基本闭环，但字段命名仍存在“error_detail vs error{code,message}”差异）

**Evidence**
- 统一执行入口：`aiPlat-core/core/harness/integration.py: HarnessIntegration.execute()`
- Gateway 入口：`aiPlat-core/core/server.py: POST /api/core/gateway/execute`
- Tool 执行返回携带 execution_id/trace_id：`aiPlat-core/core/harness/integration.py: _execute_tool()`
- 错误归一化：`aiPlat-core/core/harness/integration.py: _normalize_error()`（返回 `error_detail`）
- ExecutionStore 持久化 error_code：`aiPlat-core/core/services/execution_store.py`（schema v17，agent/skill executions error_code）
- UI 展示：`aiPlat-management/frontend/src/pages/Diagnostics/Links/Links.tsx`、各 Execute*Modal

**自动化验证**
- `aiPlat-core/.github/workflows/kernel-static-scan.yml`（CI）
- `pytest -q aiPlat-core/core/tests/integration/test_gateway_execute_api.py`

**主要 Gap（要达成“全量目标”仍需）**
1. **字段完全对齐文档**：将对外返回统一为 `error: {code,message}`（或提供稳定别名），逐步废弃 `error_detail`（或反之更新文档并冻结）。
2. **统一所有执行返回**：确保 workspace/core 的 agent/skill/tool 执行 API 在失败/成功都包含同一套字段（execution_id/status/output/error/trace_id/run_id）。
3. **补齐 Tool Modal 的契约一致性**：management 的 Tool 执行弹窗/列表与 Links 对齐（同样展示 error code + message + trace 链接）。

---

## PR-R0-2：syscalls 事件模型规范化 + 可搜索
**目标（文档）**：tool/llm/skill syscall 统一事件 schema，落盘+索引，可检索/统计。

**当前状态**：⚠️（已可检索；“可统计/聚合”仍欠缺标准接口）

**Evidence**
- syscall_events 表与索引：`aiPlat-core/core/services/execution_store.py`（Migration v6/v10 + indexes）
- 查询 API（core）：`aiPlat-core/core/server.py: GET /api/core/syscalls/events`
- management 代理：`aiPlat-management/management/api/diagnostics.py: GET /api/diagnostics/syscalls/core`
- 前端 Syscalls 页：`aiPlat-management/frontend/src/pages/Diagnostics/Syscalls/Syscalls.tsx`

**自动化验证**
- `pytest -q aiPlat-management/tests/test_diagnostics_syscalls.py`

**主要 Gap**
1. **聚合/统计接口缺失**：缺少按 `tool_name/kind/status/error_code` 的 TopN、趋势、分布等（建议新增 `/api/core/syscalls/stats`）。
2. **维度不全**：文档提到 `agent_id` 等维度；当前 syscall_events 已有 run_id/trace_id/span_id，但对“关联到 agent/skill/tool 的一跳聚合”仍需明确字段与索引策略。

---

# Roadmap-1：Prompt/Context 子系统

## PR-R1-1：PromptAssembler 完整化（稳定层缓存 + 临时层 overlay）
**目标（文档）**：
- `PromptAssembler.build()` 输出 `stable_system_prompt` + `ephemeral_overlay`
- stable prompt 有缓存 key（agent_id + prompt_version + workspace_context_hash）

**当前状态**：🔧（已有最小 PromptAssembler，但未达到稳定层/overlay/缓存的目标形态）

**Evidence**
- PromptAssembler（最小）：`aiPlat-core/core/harness/assembly/prompt_assembler.py`
  - 目前输出：messages + prompt_version（sha256）
  - 未实现：stable_system_prompt / ephemeral_overlay / 缓存 key

**主要 Gap**
1. 设计并实现 `PromptAssembler.build()` 的稳定输出结构（并接到 loop/langgraph 的唯一入口）。
2. 引入稳定层缓存：repo_root + project_context_sha256 + agent_id + toolset 等形成 hash。
3. 自动化测试：同一输入应生成同一 prompt_version；上下文文件变化应导致缓存失效。

---

## PR-R1-2：项目上下文文件（AGENTS.md/AIPLAT.md）支持 + 注入扫描
**目标（文档）**：支持上下文文件查找策略 + 注入扫描；命中高危时阻断或降级（可配置）。

**当前状态**：⚠️（已支持 + 有最小注入扫描；“可配置策略/更全风险规则/审计展示”仍需增强）

**Evidence**
- ContextEngine：`aiPlat-core/core/harness/context/engine.py`
  - 查找：`AGENTS.md / AIPLAT.md / .aiplat.md`
  - 注入扫描：invisible unicode + 3 类 injection pattern（阻断并写入 metadata）

**主要 Gap**
1. 扩充风险模式：exfiltration、编码/混淆、URL/secret 诱导等。
2. 策略化：block / warn-only / truncate / require-approval 的可配置开关。
3. 审计：将 blocked_reason 以更结构化方式落到 trace/syscall_event 或专门的 context_event。

---

## PR-R1-3：ContextEngine 插拔（压缩/检索/RAG 抽象层）
**目标（文档）**：should_compact/compact/get_status；默认压缩；可选 RAG/LCM。

**当前状态**：🔧（接口存在，但当前仅做“项目上下文文件注入”；未实现压缩/检索）

**Evidence**
- `aiPlat-core/core/harness/context/engine.py: ContextEngine / DefaultContextEngine`

**主要 Gap**
1. ContextEngine 接口扩展到文档要求（should_compact/compact/get_status）。
2. 默认压缩器：清理旧 tool 输出、结构化总结（并记录到 trace）。
3. RAG 插拔：接 aiPlat-core 的 knowledge/memory（已有基础模块，但需形成统一注入策略）。

---

# Roadmap-2：Tool Runtime 治理

## PR-R2-1：Tool Registry 收敛 + Toolset（能力包）体系化
**当前状态**：⚠️

**Evidence**
- ToolRegistry：`aiPlat-core/core/apps/tools/base.py: ToolRegistry`
- Toolsets：`aiPlat-core/core/harness/tools/toolsets.py`
- syscalls 强制治理入口：`aiPlat-core/core/harness/syscalls/tool.py`

**主要 Gap**
1. **check_fn/可用性剔除**：依赖/鉴权缺失时自动从可用工具集合剔除并返回原因（目前更多是运行时报错）。
2. toolset 覆盖更全：`write_repo/web/browser/mcp-*` 等能力包的标准化定义与 UI 引导。

---

## PR-R2-2：MCP 风险分级与强制最小权限
**当前状态**：✅（核心能力已落地）

**Evidence**
- MCP policy 元数据：`aiPlat-core/core/management/mcp_manager.py`（allowed_tools + risk_level/tool_risk/approval_required/prod_allowed）
- prod stdio 限制：`aiPlat-core/core/apps/mcp/runtime.py`（prod 下 stdio 需要 prod_allowed）
- tool 风险/审批：`aiPlat-core/core/apps/mcp/adapter.py` + `aiPlat-core/core/harness/syscalls/tool.py`

**自动化验证**
- （建议后补）增加 1 个 integration test：prod 环境下 stdio 未允许时必须拒绝 + 记录 syscall_event。

---

## PR-R2-3：文件工具工程化（去重/限额/一致性检测）
**当前状态**：⚠️（已有根目录 allowlist、max_bytes、写删开关；缺少去重/mtime 校验/更多防护）

**Evidence**
- `aiPlat-core/core/apps/tools/base.py: FileOperationsTool`

**主要 Gap**
1. 读取去重（path+offset+limit+mtime）缓存与统计；
2. 写入前 mtime 校验（外部改动提示/拒绝）；
3. 更严格的敏感路径/设备文件/二进制文件处理策略；
4. 自动化测试：覆盖 allow roots、max_bytes、write/delete policy、mtime 校验。

---

# Roadmap-3：多入口与长期运行

## PR-R3-1：Jobs/Cron 成为一等公民
**当前状态**：⚠️（执行与落库闭环已完成；死信/更强审计仍需补齐）

**Evidence**
- Scheduler：`aiPlat-core/core/management/job_scheduler.py`
  - 通过 HarnessIntegration 执行
  - job/job_runs 落库：`aiPlat-core/core/services/execution_store.py`（Migration v12+）
  - webhook delivery + retry/backoff（best-effort）

**主要 Gap**
1. 死信/DLQ（多次失败后的归档与可视化）；
2. delivery 类型扩展：Slack/飞书等渠道（与 PR-R3-2 合并实现）；
3. 自动化测试：job run 落库 + delivery retry 行为。

---

## PR-R3-2：Gateway（IM/机器人）入口适配层
**当前状态**：⚠️（已有统一 gateway/execute，但缺少 pairing/tenant/auth、消息→session 的完整适配）

**Evidence**
- `aiPlat-core/core/server.py: POST /api/core/gateway/execute`
- 测试：`pytest -q aiPlat-core/core/tests/integration/test_gateway_execute_api.py`

**主要 Gap**
1. pairing（用户绑定/权限映射）；
2. 多租户/鉴权接线；
3. 渠道侧消息模型（event → session_id → ExecutionRequest）与投递执行过程/最终结果。

---

# Roadmap-4：学习闭环

## PR-R4-1：Skill 生态升级为“技能包”（渐进披露 + 自修复）
**当前状态**：⚠️（Skill Packs 已完成；“自修复/自动沉淀”需要与学习闭环更深接线）

**Evidence**
- Skill Packs：`aiPlat-core/core/services/execution_store.py`（skill_packs/versions/installs）
- API 与 materialize：`aiPlat-core/core/server.py`（/skill-packs/* + install->workspace）
- SKILL.md 预览：`GET /api/core/workspace/skills/{id}/skill-md`
- 测试：`pytest -q aiPlat-core/core/tests/integration/test_skill_packs_api.py`

**主要 Gap**
1. skill index/view/reference files 的体系化（目前以 SKILL.md 为主，缺少“引用文件”与索引页标准）；
2. patch/edit 版本化与审计（部分已有 versions，但需补齐“引用/变更记录/回放”闭环）；
3. 自动化生成建议沉淀 skill（学习闭环触发器 → skill pack/skill 更新）。

---

## PR-R4-2：Memory（长期记忆）与 Session Search（跨会话检索）
**当前状态**：⚠️（长期记忆已完成；Session Search 未实现）

**Evidence**
- long-term memory：`aiPlat-core/core/services/execution_store.py`（long_term_memories + FTS）
- API：`aiPlat-core/core/server.py`（/memory/longterm + search）
- 测试：`pytest -q aiPlat-core/core/tests/integration/test_long_term_memory_api.py`

**主要 Gap**
1. Session Search（跨会话检索）数据模型与索引；
2. 注入策略：冻结快照 + 下次会话生效（保证缓存稳定）；
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

