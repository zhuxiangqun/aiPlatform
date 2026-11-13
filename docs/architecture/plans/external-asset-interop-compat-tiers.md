---
doc_type: Architecture
title: 外源资产互通完整改善方案（Agent / Skill / Tool / MCP）
status: proposed
authority: design-target
language: zh-CN
created: 2026-11-12
updated: 2026-11-13
---

# 外源资产互通完整改善方案（Agent / Skill / Tool / MCP）

> **设计目标态，不是实施 diff。** 先读 §0；实施读 §1 起。  
> 全文长稿曾因 physical-merge `max_net_lines=200` 拆为本文（契约口径）+ 后续 detail PR。

## 0. 白话版

### 0.1 一句话

外面的好技能，**导入后就要像 Cursor 一样马上能用**。审核管「正式上架 / 高权限」，**不挡第一次试用**。只有少数危险或缺关键依赖时才「还差几步 / 不能用」。

### 0.1b 产品默认承诺

| 承诺 | 说明 |
|------|------|
| **默认能用** | 说明书型 Skill → 导入成功 = 立刻可调用 |
| **审核不挡试用** | 审核挡上架，不挡工作区试用 |
| **少数才降级** | 安全失败或高危未映射 → 才不能用 / 还差几步 |
| **导入要有意义** | 主流结果若都是不能用 = 导入失败 |

### 0.2 四类资产

| 名字 | 类比 |
|------|------|
| Agent | 有人设的岗位员工 |
| Skill | SOP 手册（多数开源是说明书） |
| Tool | 真正动手的设备 |
| MCP | 外接工具箱的统一插头 |

### 0.3 界面三态（默认是绿）

| 文案 | 预期占比 | 含义 |
|------|:--------:|------|
| 现在就能用 | 大多数 | 立刻可调度 |
| 还差几步 | 少数 | 列出缺什么、怎么补 |
| 不能用 | 极少数 | 给原因 |

**确认（仅 handler 草稿）** = 管理台看权限/差异 →（可选试跑）→ 点「启用 handler」并审计；未点前草稿不可正式调度。

## 1. 问题与原则

**矛盾**：交换格式轻 vs 平台执行模型重；禁止用「安装成功」掩盖差距。

| # | 原则 |
|---|------|
| P0 | **导入默认可用**（不能用是例外） |
| P1 | 交换与执行分离 |
| P2 | 四类资产共用 L0→L1→L2 |
| P3 | 试用与上架分离；审核不挡第一次使用 |
| P4 | Tool 映射/MCP 优先；禁止默认热加载任意外源码 |
| P5 | 自动生成最多是草稿，默认不启用 |
| P6 | 跨资产依赖可解析 |
| P7 | 本地 Tool 与 MCP 投影一律 PolicyGate |
| P8 | 诚实展示三态，禁止只有「安装成功」 |

## 2. 三层模型（摘要）

- **L0 交换**：AGENT.md / SKILL.md / tool schema / MCP 连接描述  
- **L1 兼容**：写 `_compat`（tier 一等公民）；升格 mapped / handler / bound  
- **L2 运行时**：只调度 schedulable；唯一执行面 + 门禁  

## 3. Compat tiers（产品校正后）

### Skill

| Tier | 默认可调度 |
|------|:----------:|
| `prompt_ready` | ✅（无 handler.py 是常态） |
| `tool_mapped` | ✅ |
| `needs_handler` | ❌（可有草稿，未启用） |
| `blocked` | ❌ |

### Agent

| Tier | 默认可调度 |
|------|:----------:|
| `persona_ready` | ✅ 对话/试用立刻可用（导入默认） |
| `bound_ready` | ✅ 全功能 |
| `needs_binding` | ⚠️ **对话仍可用**；仅全功能受限 |
| `blocked` | ❌ |

### Tool

| Tier | 默认可调度 |
|------|:----------:|
| `mapped` / MCP 投影 | ✅ 立刻可调 |
| `schema_only` | ❌ 真实调用拒绝 |
| `needs_impl` | ❌；草稿须「启用」确认 |
| `blocked` | ❌ |

> 「立刻能用」= 映射或 MCP 连上后可调；**不是**任意 `.py` 热加载。

### MCP

| Tier | 默认可调度 |
|------|:----------:|
| `connectable` | ❌（应自动尝试连接） |
| `connected` | ✅ 默认立刻可用（最小权限） |
| `gated` | 部分（高风险个别确认） |
| `blocked` | ❌ |

## 4. `_compat`（必备语义）

`schema=aiplat.asset_compat.v1`；含 `tier`、`schedulable`、`issues`、`mappings`、`dependencies`、`upgrade.auto_generated_artifacts`（草稿默认 disabled）。  
`schedulable` 由 tier+策略计算，禁止手写撒谎。路由只返回 `schedulable=true`。

## 5. 导入管道与 handler 确认

管道：Ingest → Detect → SecureScan → L0Validate → Adapt → Persist → Register → **InstallReport(tier)** → Optional QA（上架）。

### 5.3 无 `handler.py`？

说明书型（prompt）**不要** handler → **自动即可用**。程序型才需要；无合格 handler 前不按 handler 调度。

### 5.4 「启用」流程（确认定义）

仅 needs_handler / 已有草稿时：

1. 提示：还差几步 · 草稿未启用  
2. 升格页：草稿做什么、权限清单、与 SOP 差异  
3. 可选试跑 / 改权限 / 丢弃草稿继续 prompt  
4. 点「启用」→ 转正 `handler.py` + 审计（谁/何时）  
5. 生产上架另走审核（不挡工作区试用）

工作区：导入人可点启用。团队/生产：有权限管理员或审核流。

## 6. 分资产口径（校正）

- **Skill**：无 handler 默认 `prompt_ready`；假绿自动 handler 禁止；启用走 §5.4  
- **Agent**：默认 `persona_ready` 能聊；缺依赖不关对话；全功能要 `bound_ready`  
- **Tool**：映射/MCP 后立刻能调；实现草稿要启用；高风险 effects 要确认  
- **MCP**：保存后自动连接；连上即用；高风险工具个别 gated；断连不假成功  

## 7. 交付切片（摘要）

- A：Skill `_compat` + InstallReport + 切断假绿 handler + UI 三态  
- B：Agent 依赖级联 + 对话/全功能分流  
- C：Tool 三路径 + MCP 生命周期  
- D：发现闭环 + 生产上架门禁 + 守卫  

## 8. 讨论修订记录

| 议题 | 结论 |
|------|------|
| 导入要像 Cursor 马上能用？ | 要；P0 默认能用 |
| 审核挡第一次用？ | 否；挡上架/高权限 |
| 无 handler.py？ | 能用；prompt 主路径 |
| 自动 handler？ | 可草稿，默认不启用；点启用才算确认 |
| Agent 缺依赖？ | 对话仍可用 |
| Tool 立刻能用？ | 映射或 MCP 投影后 |
| MCP 立刻能用？ | 自动连接成功后默认能用 |

## 9. 非目标

不保证任意生态比特级复刻；不默认执行任意下载代码；不把「多数待升格」当成默认体验。
