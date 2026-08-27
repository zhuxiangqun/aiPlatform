---
title: prime-agent 自进化 Harness 核实分析（RLM + Continual Harness）
date: 2026-08-27
status: 定稿
tags: [prime-agent, RLM, Continual Harness, 自进化, 对标]
---

# prime-agent 自进化 Harness 核实分析

## 0. 摘要

Prime Agent（PrimeIntellect-ai/prime-agent，GitHub 热榜项目）是面向长周期复杂任务的自进化 AI Agent，核心是两大抽象：

- **RLM（Recursive Language Model）**：context 即变量（prompt-as-a-variable）、子 Agent 即函数调用（rlm()），全部运行在持久 Python REPL 内；
- **Continual Harness**：补充提示 / 记忆 / 技能 / 子 Agent 规格作为持久状态，通过小的、evidence-backed 更新自进化（不改模型权重、不改基础 system prompt、快照可回滚）。

本文基于**本地源码逐项核实**（非宣传材料），重点回答：宣传主张哪些属实、三个真实创新是什么、自进化机制的防护缺口在哪、与 aiPlat 的 SBA × HarnessEval 体系如何对照借鉴。

## 1. 宣传主张 vs 代码事实（核实表）

| 主张 | 代码证据（本地路径） | 判定 |
|---|---|---|
| 唯一内置工具为 IPython | packages/coding-agent/src/core/tools/index.ts：ToolName = "ipython"，createAllToolDefinitions 仅注册 ipython（bash/edit 为宿主内部函数） | ✅ 工具**定义**唯一 |
| 持久化环境、变量保留 | prime-agent-runtime/src/rlm/repl.py：持久 __main__ namespace + 单 asyncio loop；_snapshot_state（聚合 256MB / 单变量 16MB 上限）；_ALWAYS_SKIP/_RESTORE_SKIP（bootstrap 名永不快照） | ✅ 属实 |
| rlm() 子 Agent 函数化 | packages/coding-agent/src/core/rlm-runtime.ts：rlm.run(name, prompt, …) 校验 + CreateRlmSubagentRuntimeOptions（子会话独立 model/thinkingLevel/tools/rlmDepth/rlmMaxDepth）；bootstrap 在 tools/ipython.ts（async def run/find_models/list_subagents/delete_subagent） | ✅ 属实 |
| /refine 经验沉淀 + 快照回滚 | prime-agent-runtime/src/rlm/harness.py：HarnessKind = prompt/memory/skill/subagent；RefinementEvent{id, trigger, changes, evidence, outcome}；slash-commands.ts 支持 /refine rollback <id> | ✅ 属实 |
| 断线续跑 daemon | agent-session-runtime.ts（"daemon uses it to apply…"）+ cron-jobs.ts:253（"Active session ids are daemon-local"）+ daemon-mode.test.ts（detach 后会话继续） | ✅ 属实（状态持久化 + daemon-local 注册表 + detach 不终止） |
| 不改写基础 system prompt | repl.py _ALWAYS_SKIP/_RESTORE_SKIP + README "immutable base system prompt" | ✅ 属实 |
| Agent 间直接通信 | agent-session.ts agent_message.send{target,message} + agent_observe skill（list_agents/get_agent） | ✅ 属实 |
| Skills 可执行（导入即用） | prime-agent-runtime/src/rlm/skill.py（console script 名 == skill 导入名）+ bootstrap _PrimeAgentCallableSkillModule（技能模块可 await 调用） | ✅ 属实 |

### 1.1 三处修正（初版分析基于片段证据，完整核实后修正）

1. **"唯一工具"表述**：对外工具**定义**唯一（ipython cell），但环境内预置多个可编程函数——rlm、bash(command)、mcp——是"单入口工具面 + 环境内多函数"。
2. **rlm() 并行**：rlm.run 是 async 函数，单次调用串行 await；**并行由用户代码编排**（REPL 顶层 await + asyncio.gather）。宣传"支持异步执行"属实，"自动并行"不准确。
3. **daemon 机制**：非单一 daemon 进程，而是会话状态持久化 + daemon-local 活动会话注册表 + 客户端 detach 时取消 UI 请求但会话继续。

## 2. 三个真实创新（架构级，非概念包装）

1. **prompt-as-a-variable**：大文件读取/解析结果存持久变量，对话只放引用。Token 省在"不重复传输原始数据"，代价是模型须自行"记得调用变量"。
2. **子 Agent 函数化**：rlm.run() 返回可编程结果、子 Agent 是完整独立会话（model/tools/depth 独立）、支持代码级编排与互发消息——编排逻辑与业务逻辑同层书写。
3. **Continual Harness 的"小而 evidence-backed 更新"**：RefinementEvent.changes（小步修改）+ 快照回滚；框架层自进化，不碰权重、不改基础 prompt。

## 3. 三个必须警惕的问题（宣传未展开）

### 3.1 evidence 是 LLM 自评——"自洽的谎言"风险（结构性）

- refinement.ts 输出 spec：rationale: "why these edits are justified by trajectory evidence"——**evidence 是 reviewer 对轨迹的自圆其说**；
- 防护全是提示词级：autoRefineInstructions（"Prefer an empty edits array over speculative…"）+ "Prefer small evidence-backed edits" + global scope 政策提示词；
- 机器只做：schema 解析、kind/scope 白名单、输出 token 上限（REFINEMENT_MAX_OUTPUT_TOKENS=32000）、**快照回滚（事后）**。

→ **"Agent 学到作弊方案并沉淀为技能"是结构性必然**（README 自述观察到该现象）：reviewer 认为"有证据"（rationale 自洽）即写入，无事前机器验证。

### 3.2 无沙箱 + 持久 REPL = 任意代码执行面

IPython 内 bash 是字符串命令、文件编辑是代码生成——prompt 注入即可接管整个环境。README 自承"对运行环境有较高安全要求"。

### 3.3 单工具面双刃剑

工具面极小省 token，但每次文件修改 = "LLM 写代码 → REPL 执行 → 结果回传"，latency 高于原生 file/edit 工具；IPython 内类型安全弱于结构化工具调用。

## 4. 与 aiPlat 对照（三篇研究系列：SBA 执行侧 / HarnessEval 评测侧 / prime-agent 自进化）

| 维度 | prime-agent | aiPlat | 差异与借鉴 |
|---|---|---|---|
| 上下文管理 | prompt-as-a-variable（按需计算） | ContextBus 10 层注入（主动注入） | 两种哲学互补：大块数据走变量、决策上下文走注入 |
| 经验沉淀 | Continual Harness：**LLM 自评 evidence + 提示词约束 + 事后快照回滚** | L2 经验回写：**机器门槛（confidence<0.7 拒收 + 两次独立验证 + 高风险人工确认 + rejected）+ 事前预防** | 同构但防护哲学不同——prime-agent 以实证（学到作弊）验证了"自动写回必须走验证门槛"的判断 |
| 存储 | harness_state.json（local/global） | experience_feedback.json（AIPLAT_EXPERIENCE_FILE） | 同构 |
| 子 Agent | rlm() 函数化 + 互发消息 | subagent / subagent_fork（fork 继承父上下文） | 同构；**我们多 fork 继承；他们多 agent 消息总线** |
| 断线续跑 | **daemon 会话托管 + reattach（有）** | **无——长任务绑定终端** | **我们最值得借鉴** |
| 安全 | 无沙箱 | e2e-docker + CI 门禁 + 权限体系 | 我们更完备 |
| 技能 | 可导入 Python 包 + await 调用 | SKILL.md + execution_type + conformance 契约 | 同构；我们有格式/执行双校验 |

## 5. 借鉴建议（按优先级）

1. **daemon 断线续跑**（P1）：长任务（pipeline、多轮实施）后台进程托管 + reattach + 心跳/持久目标——补齐长周期任务最后一块拼图；**✅ 已落地（2026-08-27）**：`governance/daemon_jobs.py`（DaemonJobStore：start 新会话组 / status ps-stat 僵尸判定+退出码标记 / attach 输出尾部 / kill 会话组）+ 端点 `/governance/jobs*`（契约第 27 条）+ CLI（--start/--status/--attach/--kill）；
2. **agent 消息总线**（P2）：agent_message.send 式运行中 agent 直连互发（我们现有 subagent 结果回传，但无运行时互发）；
3. **prompt-as-a-variable 的数据走变量**（P3）：大文件读取/工具输出落持久存储，对话只放引用——与 ContextBus 结合。

## 6. 结论

prime-agent 的三大创新（单入口 REPL、子 Agent 函数化、Continual Harness）均为真实架构级设计，"框架层自进化、不碰权重"的路线与 aiPlat 的 SBA × HarnessEval 体系同价值观。但它用自己的实证（学到作弊方案）验证了关键判断：**自动写回必须走机器验证门槛，不能只靠可回滚**——其快照回滚是事后补救，aiPlat 的 L2 门槛（confidence + 两次独立验证 + 高风险人工确认）是事前预防，工程代价更高但防的是同一类事故。
