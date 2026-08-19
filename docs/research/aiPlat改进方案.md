# aiPlat 改进方案（基于对标报告 + 代码现状实测）

> **依据**：《aiPlat核心能力对标报告.md》（四系统 14 维度对标）+ 本仓库代码现状实测（2026-08-15 复核）
> **原则**：代码事实优先；每项含现状证据、差距分析、落点方案、验收标准（可执行验证命令）
> **分级**：P0 合规修复（守卫 FAIL + 实测缺陷，阻断合并）→ P1 对标差距补齐（Hermes/DSH/Claude Code 借鉴，增强竞争力）→ P2 架构演进（长期方向）
> **当前基线**：`architecture_guard.py --json` → ok: False，4 个 FAIL section / 5 violations
> **实施状态（2026-08-18 收官）**：**P0-1 ~ P0-5、P1-1 ~ P1-6、P2-1 ~ P2-7 全部落地并验证**（P0-1 §57 0 违规 / P0-3 E2E 20/20 / P0-4 SDK 已初始化 / P0-5 MFA 已实现；P1-1~6 覆盖；P2-1~7 事件源/goal judge/cron script/sandbox 隔离均已实现；对应行动纲领 53/53 DONE，PR #16-#26）

---

## 第一部分：P0 合规修复（当前守卫 FAIL + 实测缺陷，必须立即修复）

### P0-1 【守卫 §57 NEW 违规】coordinator.py 直调 sys_llm_generate 绕过上下文压缩

- **现状证据**：`aiPlat-core/core/apps/agents/subagent/coordinator.py:320` `from core.harness.syscalls.llm import sys_llm_generate`；`:329` `resp = await sys_llm_generate(...)`。守卫报 `§57:agent_context_assembly_compliance`（**NEW violation，不在 baseline**）。
- **差距分析**：该调用是 `_summarize_output` 的"第 2 层 LLM 轻量摘要"路径（第 1 层已是 `MemoryManager._compression.compress_lightweight`）。守卫规则要求 `sys_llm_generate` 必须经过上下文压缩，当前直接调用违反内核约定，且是未提交变更新引入（`git status` 显示 coordinator.py 有改动）。
- **落点方案**（3 选 1，推荐 ①）：
  1. **改造复用**（推荐）：把第 2 层摘要改为调用 `MemoryManager.build_context()` 或 `doc_compressor.compress_retrieved_docs()` 包装后调用，使调用满足守卫语义（上下文压缩后再生成）。
  2. **白名单豁免**：若确认"轻量摘要"场景无需完整上下文，在守卫规则 `arch_guard_rules.yaml` §57 中为该函数添加豁免（需附 rationale 注释，不推荐——会削弱约束）。
  3. **下沉通道**：将摘要逻辑收敛为 `core/harness/knowledge/doc_compressor.py` 的公开方法，coordinator 只调用该方法（符合 §10 API 入口唯一性）。
- **验收**：
  ```bash
  python scripts/architecture_guard.py --json | python3 -c "import json,sys; d=json.load(sys.stdin); print([v for v in d.get('new_violations',[])])"  # 预期不含 §57
  python -m py_compile aiPlat-core/core/apps/agents/subagent/coordinator.py
  ```

### P0-2 【守卫 §73/§74】caller_verify.sh / method_verify.sh 未集成进 architecture_guard.sh

- **现状证据**：`aiPlat-core/core/management/arch_guard_rules.yaml:2093`（`caller_verify_in_arch_guard`，`grep_required: caller_verify\.sh|phase_check` in `scripts/architecture_guard.sh`）与 `:2241`（`method_verify_in_arch_guard`）——守卫检查自身是否集成了这两个脚本，**当前未集成**，报 error。
- **差距分析**：CLAUDE.md §0.5 审计矩阵要求 `caller_verify.sh`（0-caller 检测）和 `method_verify.sh`（路由可达性）在 CI 中运行；当前它们只在 pre-commit 或单独执行，架构守卫扫不到 → 0-caller 死代码与路由断裂可能漏进主干。
- **落点方案**：
  1. 在 `scripts/architecture_guard.sh` 末尾（PHASE 1 聚合区）追加两个调用，失败时并入 `FAIL` 计数：
     ```bash
     # §73: 0-caller 检测
     bash scripts/caller_verify.sh >/dev/null 2>&1 || { echo "❌ caller_verify.sh failed"; FAIL=1; }
     # §74: 路由可达性
     bash scripts/method_verify.sh >/dev/null 2>&1 || { echo "❌ method_verify.sh failed"; FAIL=1; }
     ```
  2. 若两者运行时间长（>60s），放入 `--quick` 之外的完整模式，并在 `arch_guard_rules.yaml` 规则注释中注明"完整模式执行"。
  3. 验证 `architecture_guard.sh` 自身仍通过（Meta-Guard 会检查 YAML 规则数 ≥100）。
- **验收**：
  ```bash
  grep -n "caller_verify\.sh\|method_verify\.sh" scripts/architecture_guard.sh   # 预期各 ≥1 命中
  bash scripts/architecture_guard.sh 2>&1 | grep -c "caller_verify.sh failed\|method_verify.sh failed"  # 预期 0（或脚本本身 pass）
  ```

### P0-3 【守卫 §17】Builder Pipeline E2E 4 个测试真实失败

- **现状证据**：`TMPDIR=... python3 -m pytest aiPlat-platform/tests/test_builder.py aiPlat-core/core/tests/unit/test_builder_pipeline_e2e.py -q --tb=line` → **4 failed, 16 passed**：
  - `test_session_type_safety_on_chat`
  - `test_error_propagates_to_get_state`
  - `test_start_pipeline_no_stages_returns_error`
  - `test_start_pipeline_returns_failed_on_execution_error`
  守卫 `complex.py:373`（`PytestCheck`）在无 API key 或部分通过时本应放行，但 16 passed 时它仍报 error（需核对判断逻辑——见下方注）。
- **差距分析**：这 4 个失败集中在 `TestBuilderPipelineE2E` 的**错误传播与类型安全**路径（chat 类型安全、错误传播到 get_state、无 stage 启动、执行错误标记 failed）——不是环境问题，是真实逻辑/契约回归。
- **落点方案**（先诊断后修复）：
  1. 逐测试运行定位断言失败点：`pytest aiPlat-platform/tests/test_builder.py::TestBuilderPipelineE2E::test_session_type_safety_on_chat -q --tb=long`。
  2. 检查 `PipelineEngine.run`/`create_pipeline_session` 的错误返回契约是否与测试期望一致（尤其"无 stages 应返回 error 而非静默成功"、"执行异常应置 run failed"）。
  3. 若根因是 `test_builder.py` 测试基建（mock 依赖）过期，优先修测试基建使其反映当前契约。
- **验收**：
  ```bash
  pytest aiPlat-platform/tests/test_builder.py -q --tb=short   # 预期 0 failed
  python scripts/architecture_guard.py --json | grep -A2 '"§17"' # 预期无 pytest_e2e error
  ```
- **注**：若修完测试后守卫仍报 §17，检查 `complex.py:380-392` 的放行逻辑（`pass_match and int(...) > 0` 应放行部分通过——疑似把"16 passed"误判为环境失败，需核对正则匹配的是 pytest 摘要行）。

### P0-4 【实测缺陷】SDK Agent.bind_skill/bind_tool 引用未初始化属性 → AttributeError

- **现状证据**：`aiplat-sdk/aiplat/agent.py:40-58` `__init__` **未初始化** `self._skills`/`self._tools`；但 `bind_skill:70` `self._skills.append(...)`、`bind_tool:79` `self._tools.append(...)`、`_ensure_agent:171-172` `"skills": self._skills, "tools": self._tools` 直接引用 → 调用 `bind_skill`/`execute` 必然 `AttributeError`。`py_compile` 通过（运行期才炸，属潜伏缺陷）。
- **落点方案**：在 `__init__` 增加两行（最小改动）：
  ```python
  self._skills: List[str] = []
  self._tools: List[str] = []
  ```
  同时补一个 SDK 冒烟测试：`bind_skill("x").bind_tool("y")` → `_ensure_agent` payload 含 skills/tools。
- **验收**：
  ```bash
  python3 -c "
  import sys; sys.path.insert(0, 'aiplat-sdk')
  from aiplat import Agent
  a = Agent(name='t'); a.bind_skill('code_generation'); a.bind_tool('file_operations')
  print('✅ bind_skill/bind_tool OK', a._skills, a._tools)
  "
  ```

### P0-5 【实测缺陷】MFA（TOTP/WebAuthn）全仓零实现

- **现状证据**：`grep -rn "totp\|webauthn\|mfa\|2fa\|otp_secret" --include='*.py' --include='*.ts' --include='*.tsx'` 全仓零命中（唯一命中是 `drawio_gen.py:10` docstring 示例）。CLAUDE.md §11b 仅将 MFA 列为"安全策略建议"，未落地。
- **差距分析**：admin 角色拥有全权限（9 个独占管理项），破坏半径极大；对标 Hermes 的 DM pairing/approvals 与 Claude Code 的 enterprise 治理，MFA 是管理员账号的基线要求。
- **落点方案**（分两步，先 TOTP 后 WebAuthn）：
  1. **TOTP（阶段一，零依赖可行）**：在 `aiPlat-platform/auth/` 新增 `mfa.py`：`pyotp`（或自实现 HMAC-SHA1 TOTP）生成/校验；`authenticator.py` 的 `verify_password` 链路加 MFA 校验；`User` 模型加 `mfa_secret`/`mfa_enabled` 字段（SQLite 迁移）；新增 `POST /auth/mfa/setup`、`POST /auth/mfa/verify`、`POST /auth/mfa/disable` 端点；前端登录页加 TOTP 输入框（`aiPlat-management/frontend/src/pages/` 登录组件）。
  2. **WebAuthn（阶段二）**：若项目已用 PyWebAuthn/webauthn 库，加安全密钥支持（可选，先不做默认）。
  3. **强制策略**：admin 角色首次登录强制绑定 MFA（`rbac.py` 中 `Role.ADMIN` 检查），CLAUDE.md §11b 从"建议"升级为"强制"并附验证命令。
- **验收**：
  ```bash
  grep -rn "mfa_secret\|totp" aiPlat-platform/auth/ --include='*.py' | wc -l   # 预期 >0
  python3 -c "from aiPlat-platform.auth import mfa; ..."  # TOTP 生成/校验单元测试通过
  pytest tests/ -k mfa -q   # MFA 相关测试通过
  ```

---

## 第二部分：P1 对标差距补齐（Hermes / DSH / Claude Code 借鉴，增强竞争力）

### P1-1 【Hermes 借鉴】会话内实时学习 nudge（AutoLearner 从"夜间批量"升级为"实时触发"）

- **现状证据**：`core/harness/learning/__init__.py:92` `class AutoLearner`（analyze_failure/analyze_success → SkillDraft → SkillSimulator → submit_for_review）；消费方仅 `evolution_engine.py:289` `_do_skill_processing`（夜间 `process_pending` 批量）→ **无会话内实时触发**。对比 Hermes：每 10 个用户 prompt / 每 10 次工具迭代即后台 review。
- **差距分析**：夜间批量导致"失败经验要等到次日凌晨才沉淀"，时效性差；Hermes 的 nudge→review→写入→审批→Curator 闭环是三方中最成熟的技能成长机制。
- **落点方案**：
  1. 在 `ReActLoop` 的执行循环（`execution/loop/base.py`）加**轻量计数触发器**：每 N 次 `tool_call`（默认 10，`AIPLAT_LEARN_NUDGE_INTERVAL` 可配）或每次 stage 失败，`asyncio.create_task` 后台调用 `AutoLearner.analyze_failure/analyze_success`（复用 `_summarize_output` 摘要，控制 token）。
  2. 接入点建议在 `syscalls/skill.py` 或 `execution/loop/base.py:POST_OBSERVE` hook 处（已有 `on_error_reflector_hook` 先例）。
  3. **review agent 判断**：给 AutoLearner 增加 `needs_review(draft)` 轻量判断（复用 `best_model_for_purpose("skill_execution")`），避免把每条失败都生成草稿（对齐 Hermes"值得沉淀才写"）。
  4. **写入门控**：草稿先落 `~/.aiplat/skill_drafts/`（现状已有），管理端审批后注册（现状已有 submit_for_review/approve）。
- **验收**：
  ```bash
  grep -rn "analyze_failure\|analyze_success" aiPlat-core/core/harness/execution/ --include='*.py' | grep -v tests | head   # 预期生产调用者 ≥1
  AIPLAT_LEARN_NUDGE_INTERVAL=3 python3 -m pytest tests/ -k auto_learner -q   # nudge 触发测试通过
  ```

### P1-2 【Hermes 借鉴】Curator 技能生命周期维护（active→stale→archived）

- **现状证据**：SkillRegistry（`apps/skills/registry.py:108`）有 `SkillBindingStats.recent_results`（CLAUDE.md §5.12 提到衰减追踪），但**无主动清理/归档机制**；Hermes 的 Curator 后台按使用频率将长期未用技能走 active→stale→archived。
- **差距分析**：技能目录会随 nudge 沉淀持续膨胀，无维护将造成"技能堆积污染目录"（Hermes 明确要防的问题）。
- **落点方案**：新增 `core/harness/learning/skill_curator.py`（`SkillCurator`）：
  1. 每日扫描 SkillRegistry，按 `SkillBindingStats` 统计使用频率；
  2. 阈值：30 天未用 → 标记 `status: stale`；90 天未用 → `status: archived`（禁用参与执行）；
  3. 与 EvolutionEngine 夜间流水线集成（`_do_skill_processing` 后调用），产出 curator 报告（含 active/stale/archived 计数与建议合并项）；
  4. 管理端诊断页新增"技能生命周期"面板（可选）。
- **验收**：
  ```bash
  python3 -c "
  from core.harness.learning.skill_curator import SkillCurator
  r = SkillCurator().scan()
  assert 'stale' in r and 'archived' in r
  print('✅ curator scan OK', r)
  "
  grep -rn "SkillCurator" aiPlat-core/core/harness/evolution_engine.py   # 预期已接线
  ```

### P1-3 【DSH 借鉴】子代理 provider 多样性（SubagentCoordinator 扩展外部后端）

- **现状证据**：`apps/agents/subagent/` 仅 `coordinator.py`（进程内创建 `SubagentInstance`）+ `config.py`（ToolPermissionLevel）+ `registry.py`——**单一进程内实现**。对比 DSH：6 种 provider（spawn/fork/ACP/Claude Code/Codex/dsh-sdk）并存 + continuable 编排。
- **差距分析**：外部子代理（跨进程隔离、外部产品执行）是 DSH 最强差异化之一；aiPlat 已有 ACP server（`core/acp/server.py`），可天然复用为子代理后端。
- **落点方案**：
  1. 定义 `SubagentProvider` 抽象（对齐 DSH `SubagentProvider` 契约：`capabilities` 旗标 + `start`/`continuation`）；现有 `SubagentCoordinator.create_instance` 重构为默认 `in-process` provider。
  2. **provider 1：ACP 后端**——复用 `core/acp/server.py` 协议，子代理经 WebSocket ACP 执行（隔离 + IDE 复用）；capabilities 旗标先行校验（`outputSchema`/`toolFilter` 等，缺失 fail-loud）。
  3. **provider 2：外部 Claude Code/Codex 后端**（可选，v2）——若环境存在 claude/codex CLI，经 stdio 启动（对齐 DSH `subagent-claude-code`）；`AIPLAT_SUBAGENT_EXTERNAL_PROVIDERS` 配置门控。
  4. **continuable 编排**：为 `execute_parallel` 增加"子代理已结算可继续对话"的句柄（对齐 DSH continuation.ts 的 running/waiting/settled 三态），`send_message`/`interrupt` 工具化。
- **验收**：
  ```bash
  grep -rn "class SubagentProvider" aiPlat-core/core/apps/agents/subagent/   # 预期命中
  python3 -c "
  from core.apps.agents.subagent.coordinator import SubagentCoordinator
  c = SubagentCoordinator()
  assert 'in_process' in c.list_providers()   # 预期至少 2 个 provider
  print('✅ providers:', c.list_providers())
  "
  ```

### P1-4 【Hermes 借鉴】多渠道矩阵扩展（3 → 10+ 适配器）

- **现状证据**：`aiPlat-app/channels/adapter.py:44` 仅 `TelegramAdapter:58`/`SlackAdapter:84`/`WebChatAdapter:107` 三个；`aiPlat-platform/gateway/router.py:30` GatewayRouter（正则路由 + pairing + 幂等 + DLQ）架构已就绪。对比 Hermes：20+ IM 平台统一 Gateway。
- **差距分析**：Gateway 控制面已完备（这是 aiPlat 相对 Hermes 的优势骨架），只差"渠道适配器"这层肉。
- **落点方案**：按成本阶梯（CLAUDE.md §20）逐渠道扩展，每渠道 = 一个 adapter 文件（继承 `ChannelAdapter`）：
  1. **P1 先做 4 个高频**：Discord、WhatsApp（或企业微信 WeCom）、Email（SMTP 接收，复用 `email_notifier.py`）、钉钉 DingTalk；
  2. 每个 adapter 复用 Gateway 的 `resolve_gateway_pairing`/`request_id` 幂等/DLQ（零新增控制面）；
  3. 前端"渠道管理"页展示已注册渠道（`aiPlat-management/frontend/src/pages/` 新增 ChannelConfig 面板，可选）；
  4. 注册进 `aiPlat-platform/registry/apps.yaml`（如 `channels` 模块声明）。
- **验收**：
  ```bash
  ls aiPlat-app/channels/*.py | wc -l   # 预期 ≥7（3 现状 + 4 新增 + adapter/base）
  python3 -c "
  from aiPlat_app.channels.adapter import get_channel_adapter
  for name in ['telegram','slack','webchat','discord','wecom']:
      assert get_channel_adapter(name) is not None
  print('✅ channels OK')
  "
  ```

### P1-5 【Hermes 借鉴】Skill 开放生态（agentskills.io 标准对接）

- **现状证据**：`knowledge/skill_marketplace.py:30` `SkillMarketplace`（SQLite `skill_registry` 表 + `install:156` git clone 到 `~/.aiplat/skills` + `discover:239` + `get_trending:279`）——内部市场已实现，但**无开放标准对接**（Hermes 兼容 agentskills.io 开放标准 + Hub）。
- **差距分析**：对接开放标准可让 aiPlat 直接消费社区技能生态（Hermes 生态 80+ 仓库），显著扩大技能供给。
- **落点方案**：
  1. `SkillMarketplace.install` 支持从 agentskills.io 拉取技能（对齐其目录格式：结构化 Markdown + metadata frontmatter）；
  2. 新增 `skill export`（把 aiPlat 技能序列化为 agentskills.io 兼容格式，`hermes skills publish` 对应物）；
  3. `discover` 增加外部源聚合（agentskills.io + 内部 registry 合并去重）；
  4. 兼容性适配：aiPlat SKILL.md frontmatter 与 agentskills.io metadata 字段映射（name/description 已是公共字段，effects/permissions 为 aiPlat 扩展，缺失时默认安全值）。
- **验收**：
  ```bash
  python3 -c "
  from core.harness.knowledge.skill_marketplace import SkillMarketplace
  m = SkillMarketplace()
  assert m.supports_external_source('agentskills.io')
  print('✅ agentskills.io 对接 OK')
  "
  grep -rn "agentskills" aiPlat-core/core/harness/knowledge/skill_marketplace.py   # 预期命中
  ```

### P1-6 【Claude Code 借鉴】Server-managed settings（企业远程强制策略）

- **现状证据**：`aiPlat-platform/auth/schemas_policy.py`（ROUTE_PERMISSIONS/SIDEBAR_MENUS）+ `services/execution_store/audit_mixin.py:253` `get_tenant_policy`/`upsert_tenant_policy`——aiPlat 已有租户策略 policy-as-code，但**无"远程托管配置强制覆盖本地"的机制**（Claude Code 的 Server-managed settings：企业通过远程配置强制权限/沙箱/模型，本地不可覆盖）。
- **差距分析**：企业部署时，管理员希望统一强制策略（如禁用某模型、强制沙箱、固定权限），当前依赖各租户自行配置，无"强制层"。
- **落点方案**：
  1. 在 `schemas_policy.py` 增加 `ManagedPolicy` 层（`managed: true` 的策略项本地不可覆盖）；存储复用 `tenant_policies` 表 + `managed` 标志列；
  2. `PolicyGate.check_tool/check_skill` 读策略时优先 managed 项（本地 user policy 仅能放宽 managed 之外的项）；
  3. 新增管理端端点 `PUT /api/platform/policy/managed`（仅 admin）与前端"托管策略"面板；
  4. 审计：managed 策略变更写入 audit_logs（action=`managed_policy_*`）。
- **验收**：
  ```bash
  grep -rn "managed" aiPlat-platform/auth/schemas_policy.py | head   # 预期命中 ManagedPolicy
  python3 -c "
  from aiPlat_platform.auth.schemas_policy import ManagedPolicy
  p = ManagedPolicy(scope='tenant', key='model_whitelist', value=[...], managed=True)
  assert p.is_managed
  print('✅ ManagedPolicy OK')
  "
  ```

---

## 第三部分：P2 架构演进（长期方向）

### P2-1 【DSH 借鉴】事件源会话（Event-Sourced Session）增强回放/审计一致性

- **现状**：`PipelineRunStore`（`execution/pipeline_run_store.py:54`）是状态型（SQLite 行，run/阶段/状态），`ExecutionStore` 已有 `syscall_events` 表（事件落库）——**已具备事件化基础，但 run 本身仍以状态快照为主**。
- **方向**：将 `PipelineRunStore` 升级为"状态 + 事件双写"：`pipeline_run_events` 表 append-only（stage_started/completed/skipped/paused/failed + hitl 事件），run 当前状态由事件折叠派生（对齐 DSH"模型可见 ⟺ 日志"不变量）。价值：断点续跑、审计回放、UI 时间线、跨 worker 一致性提升。
- **节奏**：先加事件表 + 双写（不迁移现有状态逻辑，向后兼容），再逐步把读取路径改为折叠派生。**不建议一次性重写**（12k 行引擎耦合状态语义）。

### P2-2 【DSH 借鉴】运行时自修改（dynamic plugin define/run/undefine）

- **现状**：`EvolutionEngine` 是"离线夜间演化"（改技能/知识/配置），无"运行中挂载/卸载插件"能力；`PluginManager`（`apps/plugins/manager.py:8`）是 DB 管理（注册/启停/回滚），无代码注入。
- **方向**：若需要（企业大脑"自演进操作系统"第 7 层愿景），引入受限的运行时扩展缝：`custom_handlers/` 白名单已存在（`action_contract.py:125` 模块白名单），可扩展为"运行中注册 handler 插件"，但**必须保持安全边界**（DSH 明确"自修改不是安全边界，bash 级信任"；aiPlat 应在白名单 + 审批 + 审计内做，不开放任意代码执行）。
- **节奏**：P2 阶段仅设计 + 能力缝声明，不落地代码执行。

### P2-3 【Hermes 借鉴】模型 provider 插件化（30+ 家族）

- **现状**：`ModelManager`（`infra/management/model/manager.py:664`）统一目录 + `best_model_for_purpose` 统一选型已具备；但 provider 面较窄（env 自动发现 + Ollama/LM Studio/oMLX/vLLM）。
- **方向**：将 provider 发现抽象为插件目录（对齐 Hermes `plugins/model-providers/`：新增 provider=放插件目录，resolver 零分支）。复用现有 OpenAI 兼容协议（`infra/llm/providers/openai_compatible.py` 已存在），新增 provider 主要是配置化注册。

### P2-4 【守卫自身】消除 §73 误报（wiring info 项多为守卫检测逻辑缺陷）

- **现状**：§73 报 6 项 info（error_reflector/hallucination_tracker/parallel_executor/enterprise_gateway/implicit_feedback/evolution_nightly_cron "未接线"），但实测：
  - `on_error_reflector` 已注册为默认 hook（`hook_manager.py:619` POST_OBSERVE）；
  - `evolution_nightly_cron` 已接线（`server.py:1723-1760`）；
  - `implicit_feedback` 已被 `feedback_radar.py:527` 与 `agents.py:769` 消费。
  守卫检测逻辑（字符串搜索 `sys_skill_call`/`server.py startup` 等）对"经其他路径接入"的模块误报（CLAUDE.md §16-Z 已注明此类误报历史）。
- **方向**：修正守卫规则（`arch_guard_rules.yaml` §73 或 `complex.py` 对应检查），改为"grep 到接线点 OR 明确豁免声明"双条件；优先消除 6 项 info 误报，避免噪音淹没真实违规。

---

## 第四部分：实施顺序与工作量估算

| 批次 | 项目 | 工作量 | 依赖 |
|---|---|---|---|
| **Batch 1（P0）** | P0-1 coordinator 改造 | 0.5 天 | 无 |
| | P0-2 守卫集成 caller/method_verify | 0.5 天 | 无 |
| | P0-3 E2E 4 失败修复 | 1 天 | P0-1（若相关） |
| | P0-4 SDK __init__ 修复 | 0.25 天 | 无 |
| | P0-5 MFA TOTP（阶段一） | 2 天 | 无 |
| **Batch 2（P1 学习闭环）** | P1-1 实时 nudge | 2 天 | P0-1（复用压缩通道） |
| | P1-2 Curator | 1.5 天 | P1-1 |
| **Batch 3（P1 接入层）** | P1-3 子代理 provider | 2 天 | 复用 core/acp |
| | P1-4 多渠道 4 适配器 | 2 天 | 复用 gateway |
| | P1-5 agentskills.io | 1.5 天 | P1-2（市场已有） |
| | P1-6 ManagedPolicy | 1.5 天 | 复用 tenant_policies |
| **Batch 4（P2）** | P2-1 事件源双写 | 3 天（分阶段） | P0-3 |
| | P2-2/P2-3/P2-4 | 设计/少量代码 | 视优先级 |

**合计**：P0 约 4.25 人天（阻断合并，先做）；P1 约 10.5 人天；P2 按需。

**建议节奏**：先完成 Batch 1（P0 全绿：`architecture_guard.sh` 0 FAIL + E2E 0 failed + SDK 冒烟通过 + MFA 单测通过），再按 Batch 2→3 推进 P1，P2 与日常迭代并行设计。

---

## 第五部分：验收总纲（每次改动的强制验证）

```bash
# 1. 编译 + 导入（所有变更）
python3 -m py_compile <所有变更的 .py 文件>
python3 scripts/verify_imports.py

# 2. 架构守卫（harness/infra 核心层变更）
bash scripts/architecture_guard.sh
# 预期：0 ERROR（P0 完成后基线）

# 3. 宪法测试（core 层变更）
python3 -m pytest tests/constitution/ -q --tb=short

# 4. E2E（builder/engine 变更）
python3 -m pytest aiPlat-platform/tests/test_builder.py -q --tb=short

# 5. 模型回归（model 相关变更）
python3 -c "
from core.harness.utils.model_injection import best_model_for_purpose
for p in ['chat','code_gen','reasoning','skill_execution','clarify']:
    m = best_model_for_purpose(p)
    assert '32b' not in m, f'{p} still picks 32b: {m}'
print('✅ 32b blocked')
"

# 6. 接线验证（新增公共模块）
bash scripts/caller_verify.sh   # 新模块 ≥1 非测试 caller

# 7. 路由可达性（routers/*.py 变更）
bash scripts/method_verify.sh
```

---

## 附录 A：能力缺口（§20 G1-G15）→ 改进任务完整映射

> 依据：`aiPlat核心能力对标报告.md` §20 能力缺口矩阵（反向维度扫描）。本表把每个缺口（G#）逐项关联到改进任务（P#），并标注缺口性质、优先级、工作量。

| 缺口 ID | 能力（来源系统） | 缺口性质 | 改进任务 | 任务覆盖情况 | 优先级 | 工作量 |
|---|---|---|---|---|---|---|
| G1 | 会话内实时学习 nudge（Hermes） | ⚠️ 部分（技能 review 缺） | **P1-1** 会话内实时 nudge | ✅ 已覆盖 | P1 | 2 天 |
| G2 | Curator 技能生命周期（Hermes） | ❌ 缺失 | **P1-2** Curator 维护 | ✅ 已覆盖 | P1 | 1.5 天 |
| G3 | 事件源会话单一真相源（DSH） | ⚠️ 部分（折叠派生缺） | **P2-1** 事件源双写 | ✅ 已覆盖 | P2 | 3 天 |
| G4 | 运行时自修改（DSH） | ❌ 缺失 | **P2-2** 运行时扩展缝 | ✅ 已覆盖 | P2 | 设计先行 |
| G5 | Server-managed 托管策略（CC） | ❌ 缺失 | **P1-6** ManagedPolicy | ✅ 已覆盖 | P1 | 1.5 天 |
| G6 | CC/Codex hooks 协议桥（DSH） | ❌ 缺失 | **P2-4 扩展**：hooks 协议兼容层 | ⚠️ 部分（原 P2-4 仅守卫误报修正，补充协议桥） | P2 | 2 天 |
| G7 | Checkpointing /rewind（CC） | ✅ 已具备 | —（无需任务，保留现状） | ✅ 不构成缺口 | — | — |
| G8 | agentskills.io 开放标准（Hermes） | ❌ 缺失 | **P1-5** agentskills 对接 | ✅ 已覆盖 | P1 | 1.5 天 |
| G9 | 多渠道 Gateway 广度（Hermes） | ⚠️ 部分（适配器少） | **P1-4** 多渠道扩展 | ✅ 已覆盖 | P1 | 2 天 |
| G10 | 模型 provider 插件化（Hermes） | ⚠️ 部分（无插件化） | **P2-3** provider 插件化 | ✅ 已覆盖 | P2 | 按需 |
| G11 | 子代理 provider 多样性（DSH） | ❌ 缺失 | **P1-3** 子代理 provider | ✅ 已覆盖 | P1 | 2 天 |
| G12 | 工作流 worker 隔离（DSH） | ⚠️ 部分（无隔离） | **P2-5（新增）**：PipelineEngine 阶段执行隔离（worker 进程/subprocess 沙箱） | ❌ 原方案未覆盖，本表补充 | P2 | 2 天 |
| G13 | 每 turn judge 持久化 goals（Hermes） | ⚠️ 部分（无 judge） | **P2-6（新增）**：goal 达成度 judge 判定（复用 event_loop.py Trigger + 轻量 judge 模型） | ❌ 原方案未覆盖，本表补充 | P2 | 1.5 天 |
| G14 | no-agent 纯脚本 cron（Hermes） | ⚠️ 部分（无纯脚本模式） | **P2-7（新增）**：cron 触发器支持 no-agent 脚本模式（零 LLM） | ❌ 原方案未覆盖，本表补充 | P2 | 1 天 |
| G15 | 单文件巨兽可维护性（双方皆弱） | ⚠️ 共同短板 | **P2-4** 守卫误报修正 + 大文件拆分（PipelineEngine 12k 行专项） | ⚠️ 部分（P2-4 含拆分方向） | P2 | 3 天 |

### 映射统计

| 类别 | 数量 | 说明 |
|---|---|---|
| ✅ 已被既有任务覆盖 | 11 | G1-G5、G7-G11（G7 不需任务，G6/G15 部分覆盖） |
| ❌ 原方案未覆盖 → **本表新增任务** | 3 | **P2-5**（G12 worker 隔离）、**P2-6**（G13 goal judge）、**P2-7**（G14 no-agent cron） |
| 补充扩展现有任务 | 2 | **P2-4+**（G6 hooks 协议桥）、**P2-4**（G15 大文件拆分） |

### 新增任务详情（P2-5 / P2-6 / P2-7）

**P2-5 【DSH 借鉴】PipelineEngine 阶段执行隔离（G12）**
- 现状：`builder_workflow_service.py:51` WorkflowService 拓扑排序后后台启动流水线，`_exec_stage`（`pipeline_engine.py:6864`）进程内执行，无独立 worker 隔离。
- 方案：为高风险 stage（`sandbox: true` 配置）引入独立 subprocess/worker 执行（复用 `execution/sandbox.py:48` StageSandbox 的 RLIMIT + 凭据剥离 + 超时强杀），`_exec_stage` 按 `sandbox_mode` 分派。
- 验收：`python3 -c "from core.harness.execution.sandbox import create_sandbox; assert create_sandbox('subprocess')"` + 配置 `sandbox: true` 的 stage 在独立进程执行（日志含 worker pid）。

**P2-6 【Hermes 借鉴】goal 达成度 judge 判定（G13）**
- 现状：`execution/event_loop.py:35` Trigger 支持 cron/webhook/goal 三模式，但 goal 触发是"到时启动"，无"每轮判断是否达成"。
- 方案：为 goal 型 Trigger 增加 judge 回调（复用 `best_model_for_purpose("skill_execution")` 轻量模型，对齐 Hermes `judge_goal()` goals.py:1006），每轮执行后判断达成/未达成，未达成自动续跑（轮数预算内）。
- 验收：`AIPLAT_GOAL_JUDGE_ENABLED=1` 下跑 goal 任务，日志含 `goal_judge: not_met` / `goal_judge: met`。

**P2-7 【Hermes 借鉴】cron 触发器 no-agent 脚本模式（G14）**
- 现状：`event_loop.py` cron 触发走 agent 执行，无纯脚本零 LLM 模式。
- 方案：cron 配置支持 `mode: script`（对齐 Hermes `cron/jobs.py:1571` no_agent），直接执行 shell/python 脚本，结果投递原会话/文件，零 LLM 调用（fail-closed：不静默切换模型）。
- 验收：配置 `mode: script` 的 cron 任务在无 LLM key 环境下正常执行并投递结果。

---

## 附录 B：对标差距 → 改进项映射（追溯）

| 对标报告 §16.3 差距 | 本方案改进项 | 三方参照 |
|---|---|---|
| 学习闭环触发与维护机制 | P1-1 + P1-2 | Hermes nudge + Curator |
| Skill 生态开放度 | P1-5 | Hermes agentskills.io |
| 子代理 provider 多样性 | P1-3 | DSH 6 provider |
| 事件源架构纯度 | P2-1 | DSH 事件源会话 |
| 多渠道矩阵 | P1-4 | Hermes 20+ IM |
| 模型 provider 生态 | P2-3 | Hermes 30+ provider |
| 运行时自修改 | P2-2 | DSH cordis |
| 企业远程强制策略 | P1-6 | Claude Code Server-managed |
| （守卫 FAIL 合规） | P0-1 ~ P0-3 | 内部治理 |
| （实测缺陷） | P0-4（SDK）/ P0-5（MFA） | 内部治理 |

---

## 附录 C：方案依据的可信度标注（对齐元审计 §11"阳性可信/阴性有盲区"框架）

> 本方案的所有改进项都源于对标报告/实现审计/元审计的结论。引用任何一项前，请按以下分级判断其依据强度（方法论详见 `aiPlat治理体系元审计报告.md` §11）：

| 改进项依据 | 来源 | 可信度 |
|---|---|---|
| **P0-1（§57 coordinator 直调 sys_llm_generate）** | 守卫输出 + 独立复核 `coordinator.py:320,329` | ✅ 高（阳性，人工复核） |
| **P0-2/P0-3（守卫工具链集成、E2E 失败）** | 守卫输出 + 实跑 pytest（4 failed 实证） | ✅ 高（阳性） |
| **P0-4（SDK bind_skill 缺陷）** | 直接读 `agent.py:70,79`（`self._skills.append` 未初始化） | ✅ 高（阳性，直接代码） |
| **P0-5（MFA 零实现）** | grep 全仓 0 命中 | ✅ 高（阳性） |
| **P1-1~P1-6（对标差距补齐）** | 对标报告 §20 缺口矩阵（G1-G15）+ Hermes/DSH 源码级事实 | ✅ 高（缺口是阳性事实；借鉴方案本身是设计判断） |
| **P1-2（Curator）、P1-5（agentskills）等"aiPlat 无此能力"** | 对标报告 §20（grep 确认缺失） | ✅ 高（阳性缺口） |
| **P2-1~P2-7（架构演进）** | DSH/Hermes 源码事实 + 架构路线图 | ⚠️ 中（方向基于源码事实，但"演进价值"是判断） |
| **"修复后守卫全绿"的预期** | 仅验证了 12 条语法修复的局部效果 | ⚠️ **阴性有盲区**（未全量修复验证；宪法 24 项违规仍存在，见 `宪法测试24项违规修复方案.md`） |

**重要提醒（本方案读者必读）**：
1. **P0 批次完成 ≠ 系统健康**——守卫绿只代表"规则通过"，**宪法测试当前 24 项违规（真实）未修复**（见 `宪法测试24项违规修复方案.md`），CI constitution job 实际是红的。
2. **12 条语法修复已提交**（commit `93b7c25c`），消除了守卫误报——但这是"修好了报警器"，**不等于"系统没病"**。
3. 本方案所有"aiPlat 缺 X"的改进项（P1 系列）都是阳性缺口（grep 确认），可信；"借鉴 Y 会有收益"是设计判断，需落地后验证。
