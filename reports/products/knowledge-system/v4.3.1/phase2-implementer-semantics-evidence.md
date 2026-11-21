---
doc_type: Report
title: Phase 2/4 — Implementer Semantics 最小切片证据（W10 / N18）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# W10 / N18 实现方语义测试（最小切片）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W10。  
> 标准：`docs/standards/knowledge-system/v4.3.1/schemas/conformance/README.md`（Real implementation tests）。  
> **未宣称** N18 全量认证 / 生产 RBAC 策略源替换 / 24/24。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 必跑 5 用例齐全 | pass | `REQUIRED_CASES` + `test_suite_passes_and_gate_never_certifies` |
| Raw 不可变 | pass | `raw_immutable` → FactLedger.register_source |
| published 拒空 evidence | pass | `published_requires_evidence` |
| citation 可解析 + 跨租户不泄 | pass | `citation_resolves` / `cross_tenant_isolation` |
| customer_action 快照+幂等 | pass | `customer_action_audit` → ActionExecution |
| 门槛门 pass ≠ certified | pass | `certified`/`n18_full_conformance` 恒 false |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_implementer_semantics_phase2.py -q
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `implementer_semantics.run_implementer_semantics_suite` / `evaluate_implementer_semantics_gate` |
| Facade | 同名 |
| HTTP | `POST …/fde/implementer-semantics/run` · `POST …/fde/implementer-semantics/gate` |

## 明确未做（后续）

- 部署侧 RBAC 真源 deepen 见 `phase2-deployed-rbac-evidence.md`（本文件不重复宣称）
- 外部对账 adapter 全路径（unknown→succeeded/failed）
- `semantic_cases.json` 全量状态机序列对真实 Fact Store
- 召回/聚合/导出/缓存全路径强制经部署源；宣称 N18 全量 / Core 符合
