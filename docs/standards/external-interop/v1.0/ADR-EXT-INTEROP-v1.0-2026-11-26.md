---
doc_type: Standard
status: active
authority: supporting
doc_id: ADR_EXT_INTEROP_V10_2026_11_26
last_reviewed: 2026-11-26
purpose: 批准外援互通标准包 v1.0
---
# ADR-EXT-INTEROP-v1.0-2026-11-26：批准外援互通标准 v1.0

## 状态

Accepted

## 日期

- 批准日期：2026-11-26
- 生效日期：2026-12-01

## 背景

外援资产（Agent/Skill/Tool/MCP）需分层诚实的互通契约。标准包已对照 `asset_compat` 完成 Core（X01–X06）测量，并补 §C.1 实现 tier 映射。

## 决定

1. 批准 `docs/standards/external-interop/v1.0/` 为外援互通标准 v1.0；
2. 自 2026-12-01 起，新外援导入/适配 MUST 符合本标准附录；
3. **标准批准 ≠ 实现 certified**；L2 / 生产 authorize 仍属 Extended/Operational；
4. 作者披露与职责分离豁免适用（同 KS v4.3.1 模式）。

## 批准人

- Architecture Review：朱向群（作者）
- Security：朱鸿林
- Data Governance：朱莹
- Product：朱向群（作者）

## 记录

- 批准记录：`schemas/conformance/approval-record-v1.0.approved.json`
- Schema 清单：`schemas/manifest-v1.0.json`
- Core 测量：`reports/products/external-interop/v1.0/core-gap-evidence.md`
