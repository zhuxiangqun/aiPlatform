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
---
# 评测系统 v1.0 实施方案

> 依据：
> - `docs/standards/evaluation-system/v1.0/technical-whitepaper.md`
> - `docs/standards/evaluation-system/v1.0/normative-appendix.md`
>
> 本文是实施计划，不是标准正文，也不是当前实现状态声明。  
> 承接：`eval-v1-charter.md`、五产品 Evaluation 模块现状。

## 0. 结论先行

```text
先唯一入口 + 金标可复现 + 门禁指纹
再校准 / 评测中心
最后 A3 / 生产 authorize
```

套件绿 ≠ accuracy；preview UI ≠ certified。

### 0.1 代码证据基线（2026-11-26 · 刷新）

测量：`reports/products/evaluation-system/v1.0/core-gap-evidence.md`。

| Core | 测量 |
|---|---|
| E01–E06 | **exists** |
| 正式 core_ready | 待非作者复核附录 N |
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
| P4 | Gate 指纹绑定 | E06 | **exists（已收口）** → 待复核 core_ready |
| P5 | Judge 校准 / `/eval` / Tool·MCP | Extended E07–E09 | **exists（测量）** — 见 `extended-gap-evidence.md` |
| P6 | A3 / SLA / κ | Operational E10–E12 | **exists（门禁）**；authorized=false — 见 `operational-gap-evidence.md` |

## 4. 证据目录

`reports/products/evaluation-system/v1.0/`（测量，非符合声明）。

## 5. 与知识 / FDE / 外援互通关系

| 系统 | 关系 |
|---|---|
| 知识体系 | 评测可消费知识检索质量探针，但不把 Wiki 当事实源 |
| FDE | 评测挡工程回归；FDE 签收挡客户交付 |
| 外援互通 | Tool/MCP subject 对齐互通 L0–L2；导入可用 ≠ 评测通过 |
