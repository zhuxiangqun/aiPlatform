---
doc_type: Report
title: Phase 2/3 — Source Policy / Conflict 最小切片证据（W3 / N04）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# W3 / N04 来源策略与冲突裁决（最小切片）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W3。  
> 标准：`docs/standards/knowledge-system/v4.3.1/normative-appendix.md` §K；白皮书 §7.6。  
> **未宣称** N04 全量 / 附录 N 认证 / 全写入路径强制替换。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| Source Policy 必填字段可登记 | pass | `register_source_policy` + `test_policy_register_and_forbid_fixed_layer` |
| 禁止固定 Raw>KG>Wiki 层序 | pass | `FORBIDDEN_LAYER_ORDER_RULES` 拒绝 |
| 冲突显式检测且不自动选边 | pass | `detect_object_conflicts` → `auto_winner=None` |
| 人审裁决含 actor/reason | pass | `adjudicate_conflict` + `test_adjudicate_and_publish_gate` |
| 未裁决冲突阻止 published | pass | `assert_publish_allowed` / transition + `put_fact` 硬门 |
| 裸 put_fact 强制策略登记 | pass | `test_put_fact_rejects_unknown_policy` |
| published 须经 transition（actor/reason） | pass | `put_fact_with_source_policy` → `transition_fact_review` |
| 门槛门 pass ≠ certified | pass | `evaluate_source_policy_gate` 恒 `certified=false` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_source_policy_phase2.py -q
```

实测（2026-11-16 加深）：`test_source_policy_phase2` + `test_fact_write_gates_phase2` 合跑通过。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `source_policy.register_source_policy` / `scan_and_record_conflicts` / `adjudicate_conflict` / `put_fact_with_source_policy` / `evaluate_source_policy_gate` |
| Facade | 同名 |
| HTTP | `POST …/fde/source-policies` · `GET …/fde/source-policies/{id}` · `GET …/fde/conflicts` · `POST …/fde/conflicts/scan` · `POST …/fde/conflicts/{id}/adjudicate` · `POST …/fde/source-policies/gate` |

## 明确未做（后续）

- conflict_rule 自动选边并发布（标准禁止；仅可建议）
- Claim 全量 `conflict_ids` / `decision` 字段投影
- 宣称 N04 全量 / Core 符合（`allow_bootstrap_published` 仅测试种子）
