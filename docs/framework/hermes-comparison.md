---
title: "Hermes Agent vs aiPlat 能力成熟度对照报告"
type: comparison-report
domain: aiplat-core
version: 1.0.0
date: 2026-07-06
status: published
refs:
  - docs/framework/aiplat-autonomy-framework.md
  - docs/framework/aiplat-complete-assessment.md
  - docs/framework/scoring-detail.md
tags: [hermes, comparison, L1-L15, 8-axis, radar]
---

# Hermes Agent vs aiPlat 能力成熟度对照

> ⚠️ V3.0.0 是评估范式的结构性升级，而非系统能力的重新打分。
> V2.x (2026-07-05) → 6 轴 × L1-L5 自主性框架，定级 L5。
> V3.0 (2026-07-06) → 8 轴 × L1-L5 成熟度框架，加权综合 L4。
> 系统在 A-E 轴上的技术能力未倒退。L4 不代表"降级"，而是"现在还测了以前没测过的东西"。
> 如果沿用 V2.x 的 6 轴口径，aiPlat 当前仍是 L5。

---

## 1. 背景

[Hermes Agent](https://github.com/user/hermes-agent) 定义了一套 15 级 Agent 能力成熟度模型（L1-L15），覆盖了从"基础对话接口"到"一人军团式生态产品"的完整演化路径。aiPlat 的评估框架从 V2.x 的 6 轴模型升级为 V3.0 的 8 轴模型后，首次具备了与 Hermes 进行量化对标的能力。

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

## 3. Hermes 级 → aiPlat 8 轴映射矩阵

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
  title Hermes (15级模型) vs aiPlat (8轴模型) — 能力雷达图
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

> 注：Hermes 的评分是对其 15 级模型映射到 aiPlat 8 轴的估算，非官方评分。L1-L15 是递增能力描述，不是 5 级量表，因此映射存在主观性。仅供参考趋势判断。

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
| **H 产品化** | L2 | L5 | ACP 协议 + IDE 插件 + distribution.yaml 分发 | **P0** |
| **F 自进化** | L4 | L5 | WIKI_PATH 自动索引 + Exec→GraphIndex 反馈 | **P2** |
| **A2 自调度** | L3 | L4 | SQLite 看板 + Cron 定时 + Profile 隔离 | **P1** |
| **G 多模态** | L2 | L5 | 语音/浏览器融入 Agent 决策闭环 | **P2** |

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

- **Hermes 评分**：基于原文的 15 级能力描述，映射到 aiPlat 8 轴的 1-5 级量表。具有一定主观性，仅供趋势判断。
- **aiPlat 评分**：基于 V3.0 评估框架的代码证据，可 grep/pytest 验证。
- **权重**：使用 V3.0 推荐权重（A1:20%, A2:15%, F:15%, H:15%, B-C-D-E 各 10%, G:5%）。
- **雷达图**：每个轴独立显示 1-5 级评级，非叠加累计。

---

> *本对照报告是 aiPlat V3.0 评估体系的一部分。详细评估标准见 `aiplat-autonomy-framework.md` v2.0，完整评估见 `aiplat-complete-assessment.md` v3.0.0。*
