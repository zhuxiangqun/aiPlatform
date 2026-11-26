---
doc_type: Architecture
title: 评测系统 v1.0 实施方案
status: draft
authority: supporting
language: zh-CN
created: 2026-11-26
doc_id: EVAL_SYS_V10_IMPL_PLAN
last_reviewed: 2026-11-26
purpose: 将评测系统 v1.0 标准落到可认证路径（非标准正文）
clause_sync: "2026-11-26 · 对齐非作者 Core/Extended/Operational 批准记录"
---
# 评测系统 v1.0 实施方案

> 依据：
> - `docs/standards/evaluation-system/v1.0/technical-whitepaper.md`
> - `docs/standards/evaluation-system/v1.0/normative-appendix.md`
>
> 本文是实施计划，不是标准正文。  
> **实现徽章以** `reports/products/evaluation-system/v1.0/*-approval-record.approved.json` **与 gap 证据为准**（clause-sync）。  
> 承接：`eval-v1-charter.md`、五产品 Evaluation 模块现状。

## 0. 结论先行

```text
先唯一入口 + 金标可复现 + 门禁指纹
再校准 / 评测中心
最后 A3 / 生产 authorize
```

套件绿 ≠ accuracy；preview UI ≠ certified。

### 0.1 代码证据基线（2026-11-26 · clause-sync）

测量与批准：`reports/products/evaluation-system/v1.0/`。

| 层 | 状态 |
|---|---|
| E01–E06 | **exists** + **conditional core_ready**（朱鸿林 / `core-approval-record.approved.json`） |
| E07–E09 | **exists** + **conditional extended_ready**（朱莹 / `extended-approval-record.approved.json`） |
| E10–E11 | **authorized=true**（朱莹 / `operational-approval-record.approved.json`；pilot SLA） |
| E12 | κ 报告 exists；`accuracy_claim=false` |
| certified | **否** |

已收口：`normalize_evidence_refs`；claims_gate / attach_plan 三指纹绑定。

## 1. 目标

1. **近端（MUST）**：附录 N Core（E01–E06）全部 `exists` + 证据槽位；
2. Extended：E07–E09；
3. Operational：E10–E12（另批授权）。

## 2. 非目标

- 一次宣称通用 accuracy；
- 用 FDE 签收代替评测；
- 未 ADR 强行 A3 拆分。

## 3. 阶段

| Phase | 内容 | Gate | 相对基线 |
|---|---|---|---|
| P0 | 入口盘点 / 并行路径表 / 金标资产表 | 差距表 | **已完成** |
| P1 | Canonical API 收敛 + shim | E01–E02 | **exists** |
| P2 | Case Pack + live hash | E03 | **exists** |
| P3 | 归因报告 + 默认 claim_eligible=false | E04–E05 | **exists（已收口 E04）** |
| P4 | Gate 指纹绑定 | E06 | **exists** → **core_ready conditional** |
| P5 | Judge 校准 / `/eval` / Tool·MCP | Extended E07–E09 | **exists** → **extended_ready conditional** |
| P6 | A3 / SLA / κ | Operational E10–E12 | **E10–E11 authorized**；E12 κ≠accuracy — 见 `operational-gap-evidence.md` |

## 4. 证据目录

`reports/products/evaluation-system/v1.0/`（测量，非符合声明）。

## 5. 与知识 / FDE / 外援互通关系

| 系统 | 关系 |
|---|---|
| 知识体系 | 评测可消费知识检索质量探针，但不把 Wiki 当事实源 |
| FDE | 评测挡工程回归；FDE 签收挡客户交付 |
| 外援互通 | Tool/MCP subject 对齐互通 L0–L2；导入可用 ≠ 评测通过 |
