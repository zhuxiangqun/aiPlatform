---
doc_type: Report
title: Phase 0 — v4.3.1 标准包基线校验
status: active
authority: supporting
measured_at: 2026-11-15
pilot_domain: lock-service
---

# Phase 0：标准包基线校验

> **诚实边界**：本报告只证明标准包（schema + 语义用例）可复现通过。  
> **不等于**实现符合性，也不得据此勾选附录 N。

## 命令与结果

| 脚本 | 退出码 | 摘要 |
|------|:------:|------|
| `docs/standards/knowledge-system/v4.3.1/schemas/validate_examples_v4.3.1.py` | 0 | `validated=22 failed=0`（含 2 份 approval-record） |
| `docs/standards/knowledge-system/v4.3.1/schemas/validate_semantics_v4.3.1.py` | 0 | `semantic_examples=22 failed=0`；`cases=30 failed=0` |

原始日志：

- [`phase0-schema-validate.log`](./phase0-schema-validate.log)
- [`phase0-semantics-validate.log`](./phase0-semantics-validate.log)

## 说明

标准包入口：`schemas/knowledge-system.v4.3.1.schema.json`。  
实现方 conformance（真实 RBAC、真实 Fact Store、真实外部对账）见  
`docs/standards/knowledge-system/v4.3.1/schemas/conformance/README.md`，**尚未**对本仓库实现跑通。
