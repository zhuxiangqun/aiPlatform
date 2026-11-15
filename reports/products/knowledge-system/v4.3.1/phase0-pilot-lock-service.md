---
doc_type: Report
title: Phase 0 — 试点域 lock-service 边界
status: active
authority: supporting
measured_at: 2026-11-15
pilot_domain: lock-service
target_level: Core
---

# Phase 0：试点域 `lock-service`

## 批准记录（试点边界）

| 字段 | 值 |
|------|-----|
| 试点域 | `lock-service` |
| 种子本体 | `aiPlat-core/workspace_seeds/ontologies/lock-service.yaml`（version 1.2.0） |
| 运行时路径 | `~/.aiplat/ontologies/lock-service.yaml`（若已安装种子） |
| 目标等级 | **Core**（Phase 0 仅记录；未宣称符合） |
| 状态 | **试点边界批准（Phase 0 / G0）** — 允许进入 Phase 1 设计与实现 |
| 测量日 | 2026-11-15 |

## Owner

| 角色 | 职责 |
|------|------|
| 平台知识系统 | Raw/Source/Fact Store/查询/投影实现与证据 |
| FDE / 业务（锁安域） | 语义验收、ObjectType 字段与动作语义、现场签收口径 |
| 平台安全 / 治理 | 租户隔离、PolicyGate、跨租户负向测试验收 |
| 标准 owner | v4.3.1 标准包；不替代实现符合性 |

## 域内（本试点）

- `lock-service` ontology（DeviceModel / InstallOrder 等类与状态机）
- 该域文档 ingest / 实体抽取（`PendingExtractionStore` → 未来 Fact/Claim）
- 该域 GraphIndex / GraphRAG 查询（租户前置）
- 后续 Phase 1：该域 Raw/Source Registry + Fact/Claim/Evidence 最小表
- 与该域相关的 ActionContract（若已注册）走 L1 门禁

## 域外（明确非本试点）

- 其他业务域（`ai-knowledge` / `retail-ops` / `it-ops` 等）规模化迁移
- 管理端全量 Wiki UX 改造（对象浏览器/动作台/审核台规模化 → Phase 3）
- ObjectSet SDK 生成、Scenario Package 签名（Extended / Phase 2–3）
- 附录 N 24/24 认证证据包与校准报告（Phase 4）
- 宣称「已符合 v4.3.1 Core」

## 非目标（重申计划 §1.3）

```text
一次性替换所有现有系统
让 LLM 自动批准本体/动作
允许任意 SQL 执行
把 Wiki 当事实源
没有证据就宣称符合
把认证当安全认证/合规认证
```

## Gate G0 自检

| 条件 | 证据 |
|------|------|
| 差距有证据 | [`phase0-conformance-gap-n24.md`](./phase0-conformance-gap-n24.md) |
| owner 明确 | 本文件 Owner 表 |
| 试点边界批准 | 本文件「批准记录」+ 域内/域外划分 |

**G0**：通过（测量完成，可进入 Phase 1）。  
**Core 符合**：未通过（见 24 项表）。
