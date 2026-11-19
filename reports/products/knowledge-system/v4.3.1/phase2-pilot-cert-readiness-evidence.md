---
doc_type: Report
title: Phase 2 — 试点认证就绪包证据（Batch E4）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / 试点认证就绪（Batch E4）证据

> 实施权威：选项 1+2 — N01/N06/N09 加深后的试点就绪汇总。  
> 本包结构门仍不自动徽章；等级/全量徽章见 `phase2-*-cert-path-evidence.md`（2026-11-19 已闭合）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| N01/N06/N09 门槛均 ok | pass | `item_gates` |
| catalog 焦点项证据路径齐 | pass | `focus_evidence_ok` |
| 就绪门 pass ≠ certified | pass | honesty 断言 |
| 本包不自动置徽章 | pass | pack / gate 字段（徽章另走批准） |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_pilot_cert_readiness_phase2.py -v
# 预期：2 passed
```

实测（2026-11-16）：`2 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `build_pilot_cert_readiness_pack` / `evaluate_pilot_cert_readiness_gate` |
| Facade | 同名 CoreFacade 包装 |

## 明确未做

- 将 catalog 任一项改为 exists/certified
- 试点域正式认证签字流程
- 附录 N 全量 / Core 认证
