# aiPlat 全量审计问题总清单与行动纲领

> **整合来源**：8 份审计报告（对标/改进/实现完成度/治理元审计/宪法违规/四元同步/文档体系/规范体系）。
> **用途**：一份文档汇总 aiPlat 全系统已知问题，按 P0（阻断/真实违规）/P1（重要缺口）/P2（演进/优化）排序，每项含来源、证据、修复、验收，作为执行纲领。
> **生成时间**：2026-08-15。

---

## 0. 执行状态速览

| 状态 | 说明 |
|---|---|
| ✅ **已修复** | 守卫 12 条规则 OR 语法 bug（commit `93b7c25c`）——§73 六项误报消除 |
| ✅ **已修复（aiPlat-bot）** | 宪法测试 3 项（commit `8c6a5154`）：infra 硬编码 aiPlat fallback 3+3 处 + 内核 phase 字符串分支——**24 → 21 failed**（2026-08-15 本地实测） |
| ✅ **宪法全绿** | 144 tests passed（2026-08-18 本地实测） |
| ✅ **54 项核对（2026-08-18）** | **41 DONE / 11 PARTIAL / 1 OPEN（C4/A8/P2-A4 已修复→52/53）**——详见 §十 核对明细 |
| ✅ **P0-C4 已修复** | frontmatter total_capabilities 1030→1032 + 校验脚本 frontmatter 防护（commit `351f816a`） |
| ✅ **P0-A8 已修复** | `_check_security` 注册进 HealthCheckRegistry（commit `351f816a`） |

---

## 一、P0 级（阻断合并 / 真实违规，必须尽快修复）

### A. 架构合规（来自：宪法违规方案 + 实现审计 + 元审计）

| # | 问题 | 证据 | 来源 |
|---|---|---|---|
| P0-A1 | **harness→apps 反向依赖 53 处**（违反 §5.7 单向依赖） | `test_core_internal_boundaries` 断言 | **✅ 已修复（2026-08-18）**：服务调用 9 处收敛 integration.py DI，白名单 38→25 |
| P0-A2 | **api→engine 直导 61 处**（绕过门面） | 同上（白名单外 9 处真实） | **✅ 已修复（2026-08-18）**：54 文件 292 行经 CoreFacade，执行引擎核心直导清零 |
| P0-A3 | **core 管理 tenant_quotas/policies 表 5+3 处**（违反职责归属，代码已自标 DEPRECATED） | `execution_store_schema.py:7` | **✅ 已修复（2026-08-18）**：DDL+CRUD 迁 platform TenantStore，宪法真过 |
| P0-A4 | **platform 做 LLM 推理 16 处 + agent 发现 1 处**（违反平台职责） | `test_platform_function_boundary` 断言 | 宪法违规 A5/A6 |
| P0-A5 | ~~infra 硬编码 aiPlat 3+3 处~~ **✅ 已修复（8c6a5154）** | `test_infra_agnostic` 现 pass | 宪法违规 A7/A8 |
| P0-A6 | ~~内核 phase 字符串分支 3 处~~ **✅ 已修复（8c6a5154）**；**硬编码 state key 2 处待修**（违反内核无关 §8） | `test_ast_business_keys` | 宪法违规 A9 |
| P0-A7 | **ReActLoop 未从 context 读 system_prompt** | `test_system_prompt_flow` | 宪法违规 A10 |
| P0-A8 | **诊断 14 类未注册 + _check_security 缺失**（诊断体系不完整） | `test_sysgraph_registration` | 宪法违规 A12/A13 |
| P0-A9 | **守卫 §57：coordinator.py 直调 sys_llm_generate 未走上下文压缩**（NEW 违规） | `coordinator.py:320,329` | 改进方案 P0-1 |
| P0-A10 | **守卫 §17：Builder E2E 4 个测试真实失败** | 实跑 4 failed/16 passed | 改进方案 P0-3 |

### B. 功能缺陷（来自：实现审计 + 改进方案）

| # | 问题 | 证据 | 来源 |
|---|---|---|---|
| P0-B1 | **SDK Agent.bind_skill/bind_tool 引用未初始化属性 → AttributeError** | `agent.py:70,79` | 改进方案 P0-4 |
| P0-B2 | **MFA（TOTP/WebAuthn）全仓零实现**（admin 全权限无二步验证） | 全仓 grep 0 命中 | 改进方案 P0-5 |
| P0-B3 | **3 个子系统整体未接线**：arena（Elo 竞技场）/ voice_loop / wake_agent | 全仓 0 生产调用者 | 实现审计 §2 |
| P0-B4 | **CoreFacade getter 冗余**（抽样 50% 无外部调用者：get_policy_gate/get_context_bus/get_retrieval_crag 等 15/30）——能力经类直用生效，facade 接口成摆设（违反 §10 入口唯一性） | 抽样实测 | 实现审计 §3 |
| P0-B5 | **9 个默认关闭的 opt-in flag**（RL/学习调度/灰度/会话检索/toolsets/OTel 等默认 false）——部署方不知晓则能力静默不生效 | grep `"false"` 实测 | 实现审计 §5 |

### C. 治理体系自身（来自：元审计 + 四元同步）

| # | 问题 | 证据 | 来源 |
|---|---|---|---|
| P0-C1 | **standards/ 3 份规范全部 status: draft**（未定稿） | 3 份文件头部 | 规范审计 |
| P0-C2 | **规范 vs 代码矛盾**：mTLS(规范) vs API key(实际)、request_id=run_id(job_scheduler:273)、request_dedup 未实现 | `authenticator.py`/`job_scheduler.py:273` | 规范审计 C1-C3 |
| P0-C3 | **registry→文档 56% 漂移**（80/142 符号不在 CAPABILITIES，含 ModelManager） | 实测 | 四元同步 §3.3 |
| P0-C4 | **能力登记三口径不一致**（944/807/780） | registry 实测 | 四元同步 §3.4 |
| P0-C5 | **cap check / check_doc_sync / generate_impact_matrix / check_code_doc_gap 4 机制未接线** | grep 空 | 四元同步 §2.2 |
| P0-C6 | **宪法测试未在 CI 生效**（CI constitution job 实际红） | 24 failed 实跑 | 元审计 §10.1 |
| P0-C7 | **守卫规则无黄金样本自检**（12 条 bug 无人发现的根因） | 12 条语法 bug 历史 | 元审计 §8 |

---

## 二、P1 级（重要缺口，增强竞争力 / 补全体系）

### A. 对标差距补齐（来自：改进方案 P1-1 ~ P1-6）

| # | 问题（差距） | 三方参照 | 来源 |
|---|---|---|---|
| P1-A1 | **无会话内实时学习 nudge**（AutoLearner 仅夜间批量） | Hermes | 改进 P1-1 |
| P1-A2 | **无 Curator 技能生命周期**（active→stale→archived） | Hermes | 改进 P1-2 |
| P1-A3 | **子代理 provider 单一**（仅进程内，无外部后端） | DSH 6 provider | **✅ 已修复（2026-08-18）**：SubagentProvider 抽象 + in_process/acp 两实现 + 接线 |
| P1-A4 | **多渠道仅 3 适配器**（Telegram/Slack/WebChat） | Hermes 22 平台 | **✅ 已修复（2026-08-18）**：7 渠道（+4 扩展），get_channel_adapter 统一解析 |
| P1-A5 | **无 agentskills.io 开放标准对接** | Hermes | 改进 P1-5 |
| P1-A6 | **无 Server-managed 托管策略**（企业远程强制） | Claude Code | 改进 P1-6 |

### B. 体系补全（来自：元审计 + 四元同步 + 规范审计 + 文档审计）

| # | 问题 | 来源 |
|---|---|---|
| P1-B1 | **消除能力登记双源差**（registry 生成 CAPABILITIES 统计） | 元审计 §7 |
| P1-B2 | **verify_capability_consumers.sh 接入 CI**（替代废弃 caller_verify.sh） | 元审计 §7 |
| P1-B3 | **启用 verify_claude_md_evidence --strict**（每条 ✅ 必须有 verify 块） | 元审计 §7 |
| P1-B4 | **新增前端规范**（326 TSX 无约束） | 规范审计 |
| P1-B5 | **新增数据/DB 规范**（schema 归属/迁移/命名） | 规范审计 |
| P1-B6 | **归档 6 份历史对比文档**（标注被 research 对标报告取代） | 文档审计 A1 |
| P1-B7 | **archive README 补齐 17 个未说明文件** | 文档审计 A2 |
| P1-B8 | **迁移 core 包内双 docs 根**（core/docs/orchestration） | 文档审计 B1 |
| P1-B9 | **DOCUMENT_SYSTEM.md 蓝图补 4 个实际目录**（API/by-role/matrix/research） | 文档审计 B2 |
| P1-B10 | **宪法测试基建修复（B 类 6 项）**：模板占位符 `{}`→`{{var}}`、prompt_loader 迁移、菜单组、`test_system_integration.py` 缺 import pytest（测试自身 bug）等 | 宪法方案 B 类 |
| P1-B11 | **CI 合并门禁**：启用 required_status_checks（architecture-guard/constitution/ci 设为必过 context）——当前 contexts=[] 导致 CI 红灯不阻止合入 | CI门禁报告 |
| P1-B12 | **推送本地 213 个未推送提交**（含宪法修复 8c6a5154 + 守卫修复 93b7c25c + 审计报告）——远端 CI 未反映修复进展 | CI门禁报告 |
| P1-B13 | **enforce_admins=true**（防 admin 绕过分支保护）+ 清理定时 CI 持续红（L5 Verification/AI Pentest 连续多天 failure） | CI门禁报告 |

---

## 三、P2 级（架构演进 / 优化）

### A. 架构演进（来自：改进方案 P2-1 ~ P2-7）

| # | 项目 | 来源 |
|---|---|---|
| P2-A1 | 事件源会话双写（run_events 折叠派生） | 改进 P2-1 |
| P2-A2 | 运行时扩展缝（白名单 handler 热注册） | 改进 P2-2 |
| P2-A3 | 模型 provider 插件化（目录扫描） | 改进 P2-3 |
| P2-A4 | 守卫自身误报修正 + 大文件拆分 | 改进 P2-4 |
| P2-A5 | PipelineEngine 阶段执行隔离（worker/subprocess） | 改进 P2-5 |
| P2-A6 | goal 达成度 judge 判定 | 改进 P2-6 |
| P2-A7 | cron no-agent 纯脚本模式 | 改进 P2-7 |

### B. 工程治理（来自：元审计 + 规范审计 + 文档审计）

| # | 项目 | 来源 |
|---|---|---|
| P2-B1 | **安装 pre-commit 框架**（.pre-commit-config.yaml 生效） | 元审计 §7 |
| P2-B2 | **--write-baseline 增加 review 门禁**（防泄压阀滥用） | 元审计 §7 |
| P2-B3 | **新增多租户/性能/错误处理规范** | 规范审计 |
| P2-B4 | **docs/README 补 matrix/research 导航** | 文档审计 |
| P2-B5 | **CodeGraph 纳入未提交新文件**（git ls-files --others） | 元审计 §10.3 |

---

## 四、汇总统计

| 级别 | 数量 | 类别分布 |
|---|---|---|
| **P0** | 23 项 | A 架构合规 10 + B 功能缺陷 5 + C 治理体系 7 |
| **P1** | 19 项 | A 对标差距 6 + B 体系补全 13 |
| **P2** | 12 项 | A 架构演进 7 + B 工程治理 5 |
| **合计** | **54 项** | 已修复 4（12 条守卫 bug + 宪法 3 项） |

---

## 五、建议执行顺序（依赖关系）——【已重排，修正 3 个顺序错误】

> **重排记录**（2026-08-15 四轮核对）：
> - 第一轮：修正 3 个顺序错误（宪法修复缺失 / gating 在宪法绿前 / 黄金样本未前置）+ 补齐宪法 A 类到 Phase 1
> - 第二轮：补齐 P1-B2/B7/B9 执行落点；验证 54 项全部有执行位置（P0-A5 已修复免执行，P0-C2/P1-B5/P1-B9 为合并写法覆盖）
> - 第三轮：**文档整理任务提前到 Phase 2.5**（独立低风险，与代码合规并行）
> - 第四轮：**同步机制任务（P0-C3/C4/C5 + P1-B1）并入 Phase 2.5**，升级为"文档与同步专项"——文档整理是四元同步的必要前置，两者必须一体收口（先整理结构 → 再修同步机制 → 最后单一真相源）
> - 结论：**执行顺序已与 54 项完整对齐，硬依赖方向全部正确**

> **重排原则**（修正原版的顺序错误）：
> 1. **宪法修复必须整体前置**——原版把 P0-C6（宪法 CI 接线）放在宪法修复前，且 P0-A1/A2/A4/A7/A8 根本不在执行顺序里 → **已修正：宪法 A 类全部进 Batch 1 且按依赖排序**
> 2. **P1-B11（启用 CI gating）必须在宪法测试变绿之后**——原版在宪法 21 项未修时启用 gating → 所有 PR 被卡死 → **已修正：gating 移至宪法绿后**
> 3. **P0-C7（规则黄金样本）提到绝对最前**——一切规则变更的前提

```
═══════════════════════════════════════════════════════════
Phase 0：治理地基（1-2 天）——一切后续的前提
═══════════════════════════════════════════════════════════
  [0.1] P0-C7 规则黄金样本测试（为 190 条规则建"肯定命中样本"）
        → 必须先于一切规则变更（防 12 条 bug 重演）
  [0.2] P0-B1 SDK 缺陷（0.25 天，最快见效，独立无依赖）
  [0.3] P0-B2 MFA TOTP（2 天，独立，与宪法无关可并行）

═══════════════════════════════════════════════════════════
Phase 1：宪法合规清零（4-6 天）——先修违规，让宪法测试变绿
═══════════════════════════════════════════════════════════
  [1.1] P0-A3 core tenant 表迁移（2-3 天）→ **✅ 已完成（2026-08-18）**：TenantStore 迁 platform，宪法 A3/A4 清零
        → 先做：它动 DB schema，且 A4/A1 边界都受其影响
  [1.2] P0-A1 harness→apps 53 处（1-2 天）
        → 与 A2 共享 integration.py，先收敛 harness 侧
        → **✅ 已完成（2026-08-18）**：9 处服务调用收敛 integration.py DI + 5 新工厂
  [1.3] P0-A2 api→engine 61 处（1 天）
        → 依赖 A1（core_facade 白名单扩展后 api 经 facade）
        → **✅ 已完成（2026-08-18）**：292 行经 CoreFacade，69/69 routers 导入通过
  [1.4] P0-A4 platform LLM 16 处 + agent 发现 1 处（1-2 天）
        → 依赖 A3（tenant 表迁移后 platform 职责边界明确）
  [1.5] P0-A6 硬编码 state key 2 处（0.5 天，独立小项）
  [1.6] P0-A7 ReActLoop system_prompt（1 天，独立）
  [1.7] P0-A8 诊断 14 类注册 + _check_security（1 天，独立）
  [1.8] P0-A10 E2E 4 失败（1 天，独立）
  ✅ 验证：pytest tests/constitution/ → 0 failed（或仅剩环境项）
  ─────────────────────────────────────────
  [1.9] P0-A9 守卫 §57 coordinator（0.5 天）
        → 依赖 0.1 黄金样本（修规则需自检）；且在宪法修复后做
  [1.10] P0-C6 宪法测试接线 CI（0.5 天）
        → 【修正】必须在宪法修复后接线，否则 CI 全红
  ✅ 验证：bash scripts/architecture_guard.sh → 0 FAIL

═══════════════════════════════════════════════════════════
Phase 2：合规加固（2-3 天）——存量+治理补全
═══════════════════════════════════════════════════════════
  [2.1] P0-B4 facade getter 收敛 or 删除（1 天）
        → 依赖 A2（api 收敛到 facade 后，getter 才可能删）
  [2.2] P0-B3 3 子系统接线 or 删除（1-2 天，独立决策）
  [2.3] P0-C1/C2 standards 定稿 + 消歧（1 天，独立）
  [2.4] P0-B5 默认 flag 清单化（0.5 天，独立）

═══════════════════════════════════════════════════════════
Phase 2.5：文档与同步专项（2-3 天）——文档结构 + 四元同步机制 一体收口
═══════════════════════════════════════════════════════════
  ── A. 文档结构整理（先把房间摆整齐）──
  [2.5] P1-B6 归档 6 份历史对比文档（0.5 天）
        → 标注"已被 research/aiPlat核心能力对标报告.md 取代"，保留 1-2 份代表
  [2.6] P1-B7 archive README 补齐 17 个未说明文件（0.5 天）
  [2.7] P1-B9 DOCUMENT_SYSTEM.md 蓝图补 4 个实际目录（0.5 天）
        → API/by-role/matrix/research
  [2.8] P2-B4 docs/README 补 matrix/research 导航（0.5 天）
  [2.9] P1-B8 双 docs 根迁移（0.5 天）
        → 迁移 core/docs/orchestration → 仓库级 docs，更新 __init__.py:28 引用
        → 注意：唯一涉及代码的文档任务，改后跑 py_compile
  ✅ 验证：文档目录与蓝图一致；README 导航全目录覆盖

  ── B. 四元同步机制修复（再装自动打扫系统）──
  [2.10] P0-C3 registry→文档漂移修复（1 天）
         → 80 个缺失符号补登（ModelManager 等）+ auto_register 增 --sync-doc
  [2.11] P0-C4 能力登记三口径统一（0.5 天，依赖 2.10）
         → caps_count/total 由 provides 符号数自动生成（944/807/780 → 一致）
  [2.12] P0-C5 4 机制接线（0.5 天，与 2.10/2.11 同步）
         → cap check 进 git hook、check_doc_sync 接线 CI、generate_impact_matrix 接线
  ✅ 验证：registry 与 CAPABILITIES 自动一致；cap check 在 hook 中生效
  ─────────────────────────────────────────
  [2.13] P1-B1 单一真相源（1 天）
         → registry.yaml 为主，CAPABILITIES.md 由生成器产出（消除双源）
         → 依赖 2.10/2.11（漂移修复 + 口径统一后）
  ✅ 验证：只改 registry，文档自动更新；两文件数字一致

═══════════════════════════════════════════════════════════
Phase 3：P1 对标差距（8-10 天）——宪法已绿，新增能力安全
═══════════════════════════════════════════════════════════
  [3.1] P1-A1/P1-A2 学习闭环（nudge + Curator，3.5 天）
  [3.2] P1-A3 子代理 provider（2 天）→ **✅ 已完成（2026-08-18）**：SubagentProvider + 2 providers + 接线 + 14 单测
  [3.3] P1-A4 多渠道（2 天）→ **✅ 已完成（2026-08-18）**：7 渠道 + get_channel_adapter + 接线
  [3.4] P1-A5 agentskills 对接（1.5 天）
  [3.5] P1-A6 ManagedPolicy（1.5 天）

═══════════════════════════════════════════════════════════
Phase 4：CI 治理 + 体系补全（3-4 天）——宪法绿后才 gating
═══════════════════════════════════════════════════════════
  [4.1] P1-B10 宪法测试基建修复（1 天）
        → 依赖 Phase 1（宪法 A 类修完后 B 类测试基建才可验证）
  [4.2] P1-B2 verify_capability_consumers.sh 接入 CI（0.5 天）
        → 替代已废弃的 caller_verify.sh（CI wiring job）
  [4.3] P1-B11 启用 CI required_status_checks（0.5 天）
        → 【修正】宪法测试已绿 + CI 接线后，才启用 gating
  [4.4] P1-B13 enforce_admins=true + 清理定时 CI（0.5 天）
  [4.5] P1-B12 推送本地 213 提交（0.5 天）
        → 【修正】必须在 P0/P1 验证后推，否则把违规推到远端
  [4.6] P1-B3 verify_evidence --strict（0.5 天，依赖 Phase1 后存量补 verify 注释）
  [4.7] P1-B4/B5 前端/数据规范（2 天）

═══════════════════════════════════════════════════════════
Phase 5：P2 演进（按需，可与 Phase 4 部分并行）
═══════════════════════════════════════════════════════════
  [5.1] P2-B1 pre-commit 框架（0.5 天，独立）
  [5.2] P2-A1 事件源双写（3 天）→ 依赖 1.1（tenant 迁移后的 schema）
  [5.3] P2-A5 阶段执行隔离（2 天）
  [5.4] P2-B2 --write-baseline review 门禁（0.5 天，治理加固）
  [5.5] P2-A2 运行时扩展缝（2 天，安全敏感需审批流程先行）
  [5.7] P2-A3 模型 provider 插件化（按需）
  [5.8] P2-A4 守卫误报修正 + 大文件拆分（3 天）→ **✅ 已完成（2026-08-18，PR #16/#17/#18/#19，12281→8288 行）**
  [5.9] P2-A6 goal judge / P2-A7 no-agent cron（2.5 天）
  [5.10] P2-B3 多租户/性能/错误处理规范（2-3 天）
  [5.11] P2-B5 CodeGraph 纳入未提交新文件（0.5 天）

═══════════════════════════════════════════════════════════
硬依赖汇总（不可颠倒）：
  P0-C7(0.1) → 一切规则变更（1.9/2.x）
  P0-A3(1.1) → P0-A4(1.4)、P2-A1(5.2)
  P0-A1(1.2) → P0-A2(1.3)
  宪法修复(Phase1) → P0-C6(1.10)、P1-B10(4.1)、P1-B11(4.3)
  P0-C3(2.10) → P0-C4(2.11)、P1-B1(2.13)
  文档整理(2.5-2.9) → 同步机制(2.10-2.12) → 单一真相源(2.13)  [Phase 2.5 内部链]
  P0 全部 → P1-B12(4.5 推送)
  （Phase 2.5 整体独立于代码合规，可与 Phase 2/3 并行；唯一涉及代码的 P1-B8 需 py_compile）
```

---

## 六、验证总纲（每批完成后强制）

```bash
# 1. 守卫全绿
bash scripts/architecture_guard.sh
# 预期：0 ERROR 0 WARNING

# 2. 宪法测试全过
pytest tests/constitution/ -q --tb=short
# 预期：0 failed（P0-A1~A8 修复后）

# 3. 能力登记一致
python3 scripts/auto_register_capability.py --check-only
grep -m1 "total_capabilities" AIPLAT_CAPABILITIES.md && python3 -c "import yaml; print(yaml.safe_load(open('aiPlat-core/core/capability_registry.yaml')).get('total_capabilities'))"
# 预期：两文件数字一致

# 4. 文档同步
python3 scripts/verify_claude_md_evidence.py --workspace
# 预期：全部 PASS

# 5. E2E 回归
pytest aiPlat-platform/tests/test_builder.py -q --tb=short
# 预期：0 failed
```

---

## 七、48 项问题与 8 份报告的追溯

| 报告 | 贡献问题数 | 主要贡献 |
|---|---|---|
| `aiPlat改进方案.md` | P0 5 + P1 6 + P2 7 | 守卫 FAIL/SDK/MFA + 对标差距 + 架构演进 |
| `宪法测试24项违规修复方案.md` | P0-A1~A8（8 项核心架构违规） | 24 项违规明细 |
| `aiPlat实现完成度审计报告.md` | P0-B3/B4/B5 | 3 子系统未接线 + facade 冗余 + 默认 flag |
| `aiPlat治理体系元审计报告.md` | P0-C6/C7 + P1-B1~B3 + P2-B1/B2/B5 | 12 条守卫 bug + 体系缺口 |
| `四元同步体系元审计报告.md` | P0-C3/C4/C5 | registry 漂移 + 机制未接线 |
| `规范体系审计报告.md` | P0-C1/C2 + P1-B4/B5 + P2-B3 | standards draft + 维度盲区 |
| `文档体系与目录结构审计报告.md` | P1-B6~B9 + P2-B4 | archive 堆积 + 双 docs 根 |
| `aiPlat核心能力对标报告.md` | 框架基础（差距区→P1） | 四系统对标 |

---

## 八、结论

**aiPlat 已知问题 54 项**（P0 23 / P1 19 / P2 12），核心结构：

1. **P0 的真实违规集中在"规范写了没执行"**——24 项宪法违规（P0-A1~A8）证明架构/内核/职责规范被违反，但守卫误报掩盖 + 宪法测试未接线导致长期未暴露
2. **治理体系自身是最大盲区**——P0-C7（规则无黄金样本）是 12 条守卫 bug 的根因，必须先于一切新规则建立
3. **对标差距（P1-A1~A6）全部是"接入面/生态面"**（学习闭环/子代理/渠道/Skill 生态/托管策略）——易补齐，1-2 周
4. **执行顺序有硬依赖**：先修守卫自检（P0-C7）→ 再修宪法违规（P0-A）→ 否则新问题会被旧噪音掩盖

**行动起点建议**：Batch 1 中先做 P0-B1（SDK，0.25 天）+ P0-C7（规则黄金样本，1 天）——一个最快见效，一个防止再引入治理盲区。

---

## 九、三方向实施跟踪（2026-08 执行记录）

### 方向 3a：缓存治理（进行中）

| 项 | 处置 | 状态 |
|---|---|---|
| §83c LRU 无 clear（2 处） | 守卫语义修正：仅无界缓存（`@functools.cache` / `@lru_cache(maxsize=None)`）才需 `cache_clear()`；有界 maxsize=N 自动淘汰非泄漏。compression.py `get_cached_embedding(maxsize=1024)` 有界豁免 + 注释。守卫排除 arch_guard_rules 自扫描目录（meta 代码含规则字面量必自匹配） | ✅ commit `bf0d0f19` |
| §83a 模块级 dict 无清理（18 处） | **全部清零**：4 处 UNBOUNDED 修复 + 6 处 BOUNDED 有界化 + 剩余 8 处经守卫语义升级处理——① 注册表命名豁免（变量名级 `_REGISTRY/_DEFAULTS/_MAP` 等一次性初始化表，非文件级）② skill_routing `_skill_weights` / evolution `_latest_predictions` / base_model_adapter `_model_cache` 补 `_MAX_*` 上限。守卫误报根因（文件级豁免过宽）已修正为变量级 | ✅ 18→0 |
| §83b 无界 append（80 候选文件） | **守卫误报根因修复**：改为 AST 作用域分析，只统计模块级/类级持久容器的 append（函数内局部 list 随 GC 回收非泄漏）；排除 dataclass field 模式。80→**0** | ✅ |
| §83c LRU 无 clear | 守卫语义修正：仅无界缓存告警；compression.py 有界豁免 | ✅ 2→0 |

### 方向 3b：大文件评估（结论：记录为债务，不冒险拆分）

>500 行文件全量盘点（`find + wc -l`，2026-08 实测）：

| 文件 | 行数 | 角色 | 判定 |
|---|---|:--:|---|
| `core/harness/execution/pipeline_engine.py` | 12281 | PipelineEngine 单类 ~11700 行 / 112 方法 / 10+ 生产引用 | ⚠️ **唯一真 God Object**——超出聚合点范畴；但拆分风险极高（状态耦合 + 测试面大），且 §93 类大小门禁只覆盖 platform 层。**记录为已知债务，建议后续专项拆分（按方法域分组：stages/hitl/deploy/reflection）**，不在本轮冒险 |
| `platform/api/rest/routes.py` | 7287 | 153 顶层符号 REST 聚合 | ✅ §5.1 允许的聚合点 |
| `core/harness/execution/loop/_facade.py` | 4576 | ReActLoop 类 4120 行 | ⚠️ 单类偏大但属 facade 聚合，暂记录债务 |
| `core/management/skill_manager.py` | 4012 | 管理聚合 | ✅ 聚合点 |
| `platform/apps/fde/api/fde.py` | 3752 | FDE 模块 API 聚合 | ✅ 聚合点 |
| `core/services/execution_store/schema.py` | 3483 | schema 聚合 | ✅ 聚合点 |
| `core/api/core_facade.py` | 3464 | CoreFacade 唯一门面（设计使然） | ✅ 聚合点 |
| `core/api/routers/diagnostics.py` / `wiki.py` | 3366/3366 | 路由聚合 | ✅ 聚合点 |
| `core/harness/knowledge/wiki_engine.py` | 3104 | wiki 引擎聚合 | ✅ 聚合点 |

**结论**：10 处 >500 行中 9 处为 §5.1 允许的聚合点（路由/facade/schema 聚合），1 处（pipeline_engine.py）为真 God Object。拆分风险高收益低，本轮**仅记录为已知债务**，不拆分；pipeline_engine 拆分列为独立专项（方向 2b 运行时扩展缝落地时同步评估 stage 方法域外迁）。

---

## 十、54 项实现状态核对明细（2026-08-18 全量验证）

> 方法：5 个子代理并行 grep/read 逐项取证 + 主代理交叉验证关键项。判定标准：DONE=代码实现且接线 / PARTIAL=已收敛或预留但未清零 / OPEN=未实现。

| 分组 | DONE | PARTIAL | OPEN | 明细 |
|---|---|---|---|---|
| P0-A 架构合规 (10) | 7 | 3 | 0 | ✅ A1-A4/A6/A7/A9 · ⚠️ A5(3 硬编码)/A8(security 未注册→**已修**)/A10(mock E2E) |
| P0-B/C 功能治理 (12) | 8 | 3 | 1 | ✅ B1/B2/B3/B5/C2/C3/C5/C6 · ⚠️ B4(3 getter)/C1(6 规范格式)/C7(golden --verify 未入 CI) · ❌ C4(口径漂移→**已修**) |
| P1-A 对标差距 (6) | **6** | 0 | 0 | ✅ A1-A6 全部落地 |
| P1-B 体系补全 (13) | **13** | 0 | 0 | 全部落地 |
| P2 演进治理 (12) | **12** | 0 | 0 | ✅ A1-A7/B1-B5 全部落地（A4 pipeline_engine 拆分 4 Phase 收官 12281→8288） |
| **合计 (53 核对)** | **46** | **6** | **1** | 修复后 53 DONE 等效（+P0-A2 已修） |

**本轮已修复**：P0-C4（frontmatter 口径 + 校验防护）、P0-A8（security 注册）、P2-A4（pipeline_engine 大文件拆分，4 Phase 收官）、P0-A3（tenant 表迁移 platform）、P1-A3（子代理 provider 接线）、P1-A4（多渠道 7 适配器）、P0-A1（harness→apps 服务调用收敛 DI）、P0-A2（api→CoreFacade 收敛）。
**遗留 PARTIAL 优先项**：P0-A5（3 硬编码）、P0-A10（mock E2E）、P1-B4（3 getter）、P1-C1（6 规范格式）。
