---
doc_type: Standard
status: active
authority: supporting
doc_id: ADR_EVAL_SYS_V10_2026_11_26
last_reviewed: 2026-11-26
purpose: 批准评测系统标准包 v1.0
---
# ADR-EVAL-SYS-v1.0-2026-11-26：批准评测系统标准 v1.0

## 状态

Accepted

## 日期

- 批准日期：2026-11-26
- 生效日期：2026-12-01

## 背景

评测系统需与知识体系 v4.3.1 同构的标准包（白皮书 + 规范性附录 + schemas + 实施计划）。草案已对照代码完成 Core（E01–E06）测量；现批准**标准包**为权威需求契约。

## 决定

1. 批准 `docs/standards/evaluation-system/v1.0/` 为评测系统标准 v1.0；
2. 自 2026-12-01 起，新评测能力 MUST 符合本标准附录；
3. **标准批准 ≠ 实现 certified**：`exists` 测量与正式 `core_ready` / `certified` 仍须按附录 N 单独认证；
4. 作者披露与职责分离豁免适用（同 KS v4.3.1 模式）。

## 批准人

- Architecture Review：朱向群（作者）
- Security：朱鸿林
- Data Governance：朱莹
- Product：朱向群（作者）

## 记录

- 批准记录：`schemas/conformance/approval-record-v1.0.approved.json`
- Schema 清单：`schemas/manifest-v1.0.json`
- Core 测量：`reports/products/evaluation-system/v1.0/core-gap-evidence.md`
