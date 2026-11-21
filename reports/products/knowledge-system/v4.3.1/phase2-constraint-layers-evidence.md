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
| put_fact 热路径入口 | pass | suite `put_fact_hotpath_entry` |
| query_facts_gateway 热路径入口 | pass | suite `query_facts_gateway_hotpath_entry` |
| MaterialsChat 热路径入口 | pass | suite `materials_chat_hotpath_entry` |
| GraphRAG 热路径入口 | pass | suite `graphrag_hotpath_entry` |
| Wiki/KB 热路径入口 | pass | suite `wiki_kb_hotpath_entry` |
| 裸 list syscall 热路径入口 | pass | suite `bare_list_hotpath_entry` |
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
| 核心 | `evaluate_constraint_stack` / `maybe_attach_*_constraint_hotpath` / suite/gate |
| 热路径 | `unified_query_gateway` + `put_fact` + `query_facts_gateway` + MaterialsChat 直出 + GraphRAG + Wiki/KB（list 信封 + query_wiki/kb_with_abstain）+ 裸 `sys_wiki_retrieve`/`sys_kb_retrieve`（`ConstraintAwareHitList.n20_constraint`）→ 挂 `n20_constraint`（`AIPLAT_CONSTRAINT_LAYERS_HOTPATH`；不阻断/不回滚；裸 list 主返回仍为 list） |
| Facade / HTTP | 同名 + `/fde/constraint-layers*` |

## 明确未做

- 重写 ActionRegistry / PolicyGate 全路径为唯一栈
- 把裸 list 主返回改写为 dict 信封（刻意保持 list；观测挂子类属性）
- 热路径 `blocked` 写回 F.1 `abstained` 或回滚 `put_fact`（刻意仅观测信封）
- N08 Lv4 误报门重设计；N20 certified
