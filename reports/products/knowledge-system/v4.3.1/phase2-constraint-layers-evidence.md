---
doc_type: Report
title: Phase 2 — 知识面 L1/L2/L3 约束分层证据（N20 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N20 约束分层证据

> 实施权威：附录 N N20 deepen（白皮书 §8.4 L1>L2>L3 + Gateway 热路径信封）。  
> **未宣称** N20 certified / 知识面全域完整强制分层 / N08 Lv4 重设计。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| L1 缺权限阻塞 | pass | suite `l1_blocks_missing_permission` |
| L2 警告不阻塞 | pass | suite `l2_warn_not_block` |
| 高风险仅 L2 拒绝 | pass | suite `l2_alone_high_risk_denied` |
| L3 审计标记 | pass | suite `l3_audit_required_flag` |
| 层序 L1→L2→L3 | pass | suite `layer_order_l1_gt_l2_gt_l3` |
| 热路径 helper | pass | suite `hotpath_helper_attaches` |
| Gateway 热路径入口 | pass | suite `gateway_hotpath_entry` |
| certified 恒 false | pass | suite / gate honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_constraint_layers_phase2.py -v
# 预期：5 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `evaluate_constraint_stack` / `maybe_attach_constraint_stack_hotpath` / suite/gate |
| 热路径 | `unified_query_gateway` → 挂 `n20_constraint`（`AIPLAT_CONSTRAINT_LAYERS_HOTPATH` 默开，`0` 关；不阻断 F.1） |
| Facade / HTTP | 同名 + `/fde/constraint-layers*` |

## 明确未做

- 重写 ActionRegistry / PolicyGate 全路径为唯一栈
- 知识面全域（Wiki/KB/GraphRAG 全入口）完整强制分层
- 热路径 `blocked` 写回 F.1 `abstained`（刻意仅观测信封）
- N08 Lv4 误报门重设计；N20 certified
