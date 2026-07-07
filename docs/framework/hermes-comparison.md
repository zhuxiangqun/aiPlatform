---
title: "Hermes Agent vs aiPlat 能力成熟度对照报告"
type: comparison-report
domain: aiplat-core
version: 2.0.0
date: 2026-07-06
status: published
refs:
  - docs/framework/aiplat-autonomy-framework.md
  - docs/framework/aiplat-complete-assessment.md
  - docs/framework/scoring-detail.md
tags: [hermes, comparison, L1-L15, 8-axis, radar, resilience]
---

# Hermes Agent vs aiPlat 能力成熟度对照

> ⚠️ V3.0.0 是评估范式的结构性升级，而非系统能力的重新打分。
> V2.x (2026-07-05) → 6 轴 × L1-L5 自主性框架，定级 L5。
> V3.0 (2026-07-06) → 9 轴 × L1-L5 成熟度框架，加权综合 L4。
> 系统在 A-E 轴上的技术能力未倒退。L4 不代表"降级"，而是"现在还测了以前没测过的东西"。
> 如果沿用 V2.x 的 6 轴口径，aiPlat 当前仍是 L5。

> 📌 报告 v2.0（2026-07-06）新增 §5.4「容错四层对标（R 轴）」。
> Hermes 容错文章提出的四层纵深防御（Checkpoint → 自愈 → 凭证轮换 → 上下文压缩）
> 是一条**横向能力**，横跨 aiPlat 的 A1/B/C/F 四轴，无法被任一正向能力轴覆盖。
> 对标结论以**接线深度 D0-D4** 而非 "模块是否存在" 为标尺（详见 `aiplat-complete-assessment.md` §2.4）。

---

## 1. 背景

[Hermes Agent](https://github.com/user/hermes-agent) 定义了一套 15 级 Agent 能力成熟度模型（L1-L15），覆盖了从"基础对话接口"到"一人军团式生态产品"的完整演化路径。aiPlat 的评估框架从 V2.x 的 6 轴模型升级为 V3.0 的 9 轴模型后，首次具备了与 Hermes 进行量化对标的能力。

本报告建立两套体系之间的映射关系，识别领先、持平、落后的能力维度，为路线图规划提供数据支撑。

---

## 2. Hermes 15 级能力提炼

| 级 | 名称 | 核心系统能力 | 关键技术特征 |
|:--:|------|------|------|
| L1 | 尝鲜者 | 基础交互引擎 | LLM API 接入、文件读写、本地终端执行 |
| L2 | 对话者 | 持久化记忆系统 | 三文档架构（SOUL/MEMORY/USER.MD）、原子记忆操作 |
| L3 | 驯化师 | 初级任务调度器 | 会话内多任务并发（/background、/queue、/steer）、热切换模型 |
| L4 | 越境者 | 技能扩展框架 | 按需加载的专家知识包、渐进式披露、多技能中心连接 |
| L5 | 连接者 | MCP 协议网关 | 模型上下文协议服务端/客户端、工具搜索优化 |
| L6 | 召唤师 | 并行子 Agent 引擎 | 动态子 Agent 生成、独立上下文+工具集、并发数限制 |
| L7 | 自由人 | 自主循环 + 定时任务 | Goal 循环引擎、Cron 驱动、wakeAgent 零 Token 变更检测、检查点回滚 |
| L8 | 编队指挥 | 多 Profile 管理 | 独立 Profile（身份/模型/技能/MCP）、并行运行 |
| L9 | 造物主 | 自进化学习引擎 | /learn 指令、操作历史→SKILL.md、WIKI_PATH 知识库索引 |
| L10 | 调度者 | 看板工作流引擎 | SQLite 任务看板、状态流转、依赖链、定时调度 |
| L11 | 声控师 | 多模态语音网关 | STT/TTS 抽象层、27+ 消息通道 |
| L12 | 潜行者 | 浏览器自动化引擎 | Headless 浏览器控制（Playwright/CDP） |
| L13 | 架构师 | OpenAI 兼容 API | HTTP 端点暴露 Agent 能力、OAuth 网关 |
| L14 | 嵌入者 | ACP 协议服务器 | IDE 嵌入（VS Code/JetBrains）、聊天/diff/终端渲染 |
| L15 | 一人军团 | 配置分发与打包 | distribution.yaml + Git 一键安装/分发 |

---

## 3. Hermes 级 → aiPlat 9 轴映射矩阵

| Hermes 级 | 能力域 | 映射 aiPlat 轴 | aiPlat 当前评级 | 状态 |
|:--:|------|:--:|:--:|:--:|
| L1 | 基础交互 | A1, C | A1:L4, C:L4 | ✅ **超越** |
| L2 | 持久记忆 | D | D:L5 | ✅ **超越** (GossipProtocol 超出 Hermes L2 范围) |
| L3 | 多任务调度 | A1, A2 | A1:L4, A2:L3 | ✅ **持平** (aiPlat Pipeline 强于此级) |
| L4 | Skills 框架 | C | C:L4 | ✅ **持平** (32 Skill + handler.py 代码生成) |
| L5 | MCP 协议 | C, E | C:L4, E:L5 | ✅ **持平** (MCPServer + 动态发现) |
| L6 | 子 Agent 引擎 | E | E:L5 | ✅ **超越** (SwarmBroker 合同网 > 简单 delegate) |
| L7 | 自主循环 | A1 | A1:L4 | ⚠️ **接近** (差 wakeAgent + no_agent 模式) |
| L8 | 多 Profile | A2 | A2:L3 | ⚠️ **落后** (多租户 vs 真 Profile 隔离) |
| L9 | 自进化 /learn | F | F:L4 | ✅ **持平** (AutoLearner + EvolutionEngine + ActiveSynthesis 已构建闭环) |
| L10 | 看板工作流 | A2 | A2:L3 | ⚠️ **落后** (缺 SQLite 看板+定时调度) |
| L11 | 语音网关 | G | G:L2 | ❌ **显著落后** (模块存在但未闭环) |
| L12 | 浏览器引擎 | G | G:L2 | ❌ **显著落后** (模块存在但未闭环) |
| L13 | API 服务端 | H | H:L2 | ❌ **显著落后** (有 API 但未达到"Agent 能力全暴露"标准) |
| L14 | IDE 嵌入(ACP) | H | H:L2 | ❌ **显著落后** (无 ACP 协议) |
| L15 | 配置分发 | H | H:L2 | ❌ **显著落后** (无 distribution.yaml) |

---

## 4. 双系统雷达图

```mermaid
%%{init: {"theme": "dark"}}%%
radar
  title Hermes (15级模型) vs aiPlat (9轴模型) — 能力雷达图
  axis A1("A1 自执行 [20%]")
  axis A2("A2 自调度 [15%]")
  axis B("B 上下文感知 [10%]")
  axis C("C 工具掌握 [10%]")
  axis D("D 记忆系统 [10%]")
  axis E("E 协作能力 [10%]")
  axis F("F 自进化 [15%]")
  axis G("G 多模态 [5%]")
  axis H("H 产品化 [15%]")

  "aiPlat V3.0": 4, 3, 5, 4, 5, 5, 4, 2, 2
  "Hermes (映射估算)": 5, 4, 3, 4, 3, 3, 5, 5, 5
```

> 注：Hermes 的评分是对其 15 级模型映射到 aiPlat 9 轴的估算，非官方评分。L1-L15 是递增能力描述，不是 5 级量表，因此映射存在主观性。仅供参考趋势判断。

---

## 5. 差异分析

### 5.1 aiPlat 领先维度

| 轴 | aiPlat | Hermes (估) | 原因 |
|:--|:--:|:--:|------|
| **D 记忆系统** | L5 | L3 | GossipProtocol 推拉对等同步 + 四层记忆(WAL/Semantic/Episodic/Procedural) + 冲突检测——超出 Hermes L2 的三文档架构范围 |
| **E 协作能力** | L5 | L3 | SwarmBroker 实现合同网协议(announce→bid→award) + 能力自评 + DynamicOrchestrator——Hermes L6 delegate_task 是简单子任务派发，不等同于对等协商 |

### 5.2 水平相当维度

| 轴 | aiPlat | Hermes (估) | 说明 |
|:--|:--:|:--:|------|
| **A1 自执行** | L4 | L5 | aiPlat 有 GoalExecutor + 检查点回滚，差 wakeAgent（零 Token 变更检测）。Hermes 的 /goal 和 /rollback 等价 |
| **B 上下文** | L5 | L3 | aiPlat AdaptiveContextRouter + CRAG 3 级回退 + 26 本体模块；Hermes 上下文管理相对基础 |
| **C 工具掌握** | L4 | L4 | aiPlat ToolBootstrap handler.py 代码生成 + MCP 动态发现；Hermes Skills + MCP 相当 |

### 5.3 aiPlat 落后维度

| 轴 | aiPlat | Hermes (估) | 差距 | 优先级 |
|:--|:--:|:--:|------|:--:|
| **H 产品化 | **L3** | `aiPlat-core/core/acp/server.py` — FastAPI WebSocket ACP server + VS Code extension | 缺 distribution.yaml 配置分发 (L4) | L5 | ACP 协议 + IDE 插件 + distribution.yaml 分发 | **P0** |
| **F 自进化** | L4 | L5 | WIKI_PATH 自动索引 + Exec→GraphIndex 反馈 | **P2** |
| **A2 自调度** | L3 | L4 | SQLite 看板 + Cron 定时 + Profile 隔离 | **P1** |
| **G 多模态** | L2 | L5 | 语音/浏览器融入 Agent 决策闭环 | **P2** |

### 5.4 容错四层对标（R 轴 — V2.0 新增）

> Hermes 容错文章提出四层纵深防御架构，是 Hermes 15 级模型中"自主性得以落地的底层基础设施"。
> 以下是对 aiPlat 容错四层以**接线深度 D0-D4** 为标尺的对标（详见 `aiplat-complete-assessment.md` §2.4 完整证据链）。

| 层级 | Hermes 设计目标 | Hermes | aiPlat | 接线深度 | 关键证据 |
|------|------|:--:|:--:|:--:|------|
| Layer 1 Checkpoint | 文件快照 + 用户自助恢复 | ✅ 原生 | ✅ | D4 全量接线 | 快照机制完整；**2026-07-06 补齐**：执行态自助恢复 API + `file_checkpoint.py` 文件系统级物理安全网（写/编辑前自动备份 + `/file-checkpoints/*` 恢复）|
| Layer 2 自愈循环 | LLM 推理驱动修复 | ✅ 核心 | ✅ | D3+ 核心接线 | 19类分类 + 5策略 + UCB1 + LLM兜底 (`pipeline_engine.py:4416-4685`)；**2026-07-06 补齐**：ToolResult 结构化错误 (`error_type/exit_code/stderr/recovery_hint`) 注入 observation |
| Layer 3 凭证轮换 | 多key透明轮换 + 自动冷却 | ✅ 内置 | ✅ | D3+ 核心接线 | **2026-07-06 全路径接线**：`CredentialPool` 接入 chat + stream 热路径（429/403/timeout 轮换 + 冷却 + 脱敏观测），原 141 行死代码激活 |
| Layer 4 上下文压缩 | Token 溢出时 LLM 语义摘要 | ✅ 自动 | ✅ | D3+ 核心接线 | 6 级压缩 + 工具输出 JSON 摘要；**2026-07-06 补齐**：`_aggressive/_emergency_compress` 接入 `_llm_summarize_conversation`(4类结构化) |

**核心发现**：aiPlat 在容错四层的"骨架"全部存在，但有三类病症：
- **接线断裂**（Layer 3 凭证池 — 原 141 行死代码，2026-07-06 已接线修复）
- **能力错位**（Layer 1 Checkpoint — 2026-07-06 已补齐自助恢复 API + 文件系统级检查点，物理安全网完整）
- **深度不足**（Layer 2 无结构化错误 → 2026-07-06 已修复；Layer 4 对话级无语义摘要 → 2026-07-06 已修复）

**与 Hermes 15 级模型的内在关系**：

| Hermes | 机制 | 依赖的容错层 | aiPlat 缺口 |
|:--:|------|:--:|------|
| L7 /goal | 自主执行到完成 | Layer 2 自愈（不因单一错误中断） | ✅ 已接线 (2026-07-06) — ToolResult 结构化错误 (error_type/exit_code/stderr/recovery_hint) 注入 observation |
| L7 /rollback | 检查点回滚 | Layer 1 Checkpoint（文件可恢复） | ✅ 已接线 (2026-07-06) — 全量 state + 文件系统级文件内容均可自助恢复 |
| L9 /learn | 自进化学习 | Layer 4 上下文压缩（长任务认知续航） | ✅ 已接线 (2026-07-06) — 长任务 LLM 语义摘要保障产物完整 |
| L10 看板调度 | 跨 Profile 编排 | Layer 3 凭证池（多 key 不因限卡住） | ✅ 已接线 (2026-07-06) — 多 key 模式下 429/403/timeout 自动轮换；单 key 行为不变 |

> **优先级**（技术层面，非路线图承诺）：
> 1. ~~P0~~ → **✅ 已修复** Layer 3 凭证池接线 — `openai_compatible.py` chat 重试循环 + `mark_rate_limited`/`mark_success` liveness + `test_credential_rotation.py` 6 passed (2026-07-06)
> 2. ~~P0~~ → **✅ 已修复** Layer 2 ToolResult 结构化错误字段 — `sys_tool_call:_enrich_tool_error` 接入 ErrorTranslator 分类 + observation `[DIAGNOSTICS]` + `test_tool_error_enrichment.py` 12 passed (2026-07-06)
> 3. ~~P1~~ → **✅ 已修复** Layer 4 对话级 LLM 语义摘要 — `_llm_summarize_conversation` 接入 AGGRESSIVE/EMERGENCY（4类结构化）+ `test_conversation_summary.py` 10 passed (2026-07-06)
> 4. ~~P2~~ → **✅ 已修复** Layer 1 文件系统级快照回滚 — `file_checkpoint.py` 写/编辑前自动备份 + 自助恢复端点 + `test_file_checkpoint.py` 12 passed (2026-07-06)

---

## 6. 路线图建议

| 优先级 | 目标 | 关联轴 | 关键交付物 | 估算工作量 |
|:--:|------|:--:|------|:--:|
| **P0** | ACP 协议服务端 + VS Code 插件 | H | `acp_server.py` + VS Code extension | 2-3 周 |
| **P0** | distribution.yaml 配置打包 + Git 安装 | H | `scripts/hermes-profile-install.sh` + 模板 | 1-2 周 |
| **P1** | SQLite 看板引擎 | A2 | `harness/coordination/kanban_engine.py` + Cron 调度器 + 依赖链 | 2-3 周 |
| **P1** | 真正 Profile 隔离 | A2 | memory/skills/mcp 按 Profile 命名空间隔离 | 1-2 周 |
| **P2** | 语音 + 浏览器的 Agent 决策闭环 | G | 语音触发 → Goal 循环 → Browser 操作 → TTS 反馈 全链路 | 4-8 周 |

---

## 7. 方法说明

- **Hermes 评分**：基于原文的 15 级能力描述，映射到 aiPlat 9 轴的 1-5 级量表。具有一定主观性，仅供趋势判断。
- **aiPlat 评分**：基于 V3.0 评估框架的代码证据，可 grep/pytest 验证。
- **权重**：使用 V3.0 推荐权重（A1:20%, A2:15%, F:15%, H:15%, B-C-D-E 各 10%, G:5%）。
- **雷达图**：每个轴独立显示 1-5 级评级，非叠加累计。
- **R 轴（容错四层）方法论**（V2.0 新增）：R 轴是横向诊断轴，不并入 A-H headline。评分标尺是**接线深度 D0-D4** 而非 "模块是否存在"。两条强制升级：① 接线判据从 "≥1 caller" 升级为 "热路径接线"——追问 caller 是否真的在生产热路径行使核心机制（`CredentialPool` 有 1 caller 却空转 = D1 而非 D3）；② 引入 "故障注入" 视角——问 "触发条件成立时走哪条分支" 而非 "能力在不在"。完整方法见 `aiplat-complete-assessment.md` §6.3。

---

> *本对照报告是 aiPlat V3.0 评估体系的一部分。详细评估标准见 `aiplat-autonomy-framework.md` v2.0，完整评估见 `aiplat-complete-assessment.md` v3.0.0。*
