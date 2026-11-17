---
doc_type: Report
title: Phase 2 — Revision Restore 程序化恢复证据（N24 Batch I1）
status: active
authority: supporting
measured_at: 2026-11-17
pilot_domain: lock-service
---

# Phase 2 / Revision Restore（Batch I1）证据

> 实施权威：附录 N N24 partial 加深（Fact/Claim/Source 抬号归档后的程序化 restore）。  
> **未宣称** 一键回滚 UI / 审批式 revert / Package+Action 统一审计总线 / N24 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 缺 actor/reason 拒绝 | pass | `test_restore_requires_actor_reason` / suite |
| 缺失 revision 拒绝 | pass | `test_restore_missing_revision_rejected` |
| Fact/Claim/Source 恢复抬号 | pass | `test_restore_fact_claim_source` |
| 同内容幂等 | pass | `test_restore_idempotent` |
| suite/gate certified 恒 false | pass | `test_suite_and_gate_honesty` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_revision_restore_phase2.py -v
# 预期：5 passed
```

实测（2026-11-17）：`5 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `restore_fact_at_revision` / `restore_claim_at_revision` / `restore_source_at_revision` |
| 语义 | 内容取自目标 revision；`review_status`/`status` 保留当前头；抬号归档 |
| 套件 | `run_revision_restore_suite` / `evaluate_revision_restore_gate` |
| Facade | `fact_ledger_restore_*` + suite/gate |

## 明确未做

- 管理端一键回滚 UI
- 审批式 revert 工作流
- Package+Action 统一审计总线合并
- N24 / 附录 N 全量认证
