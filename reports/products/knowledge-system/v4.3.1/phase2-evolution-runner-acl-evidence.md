---
doc_type: Report
title: Phase 2 — EvolutionRunner suggestions OWL 落盘身份透传（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / EvolutionRunner 字段 ACL（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 suggestions/offline OWL ACL 之上。  
> **未宣称** N07/N22 certified / 字段 ACL 管理 UI / 全量后台任务身份注入。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| ctor 含 actor | pass | `test_evolution_runner_ctor_has_actor` |
| 持有身份 | pass | `test_evolution_runner_stores_actor` |
| 落盘透传 | pass | `test_evolution_runner_write_suggestions_call_wires_actor` |
| HTTP `/evolve` | pass | `test_wiki_evolve_route_wires_actor` |
| wiki_auto_update | pass | `test_wiki_auto_update_signature_has_actor` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_evolution_runner_acl_phase2.py -v
# 实测 2026-11-19：5 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Runner | `EvolutionRunner(..., actor_role=, actor_scopes=)` → `write_suggestions_owl_file` |
| HTTP | `POST …/wiki/evolve?actor_role=&actor_scopes=` |
| Facade | `wiki_auto_update(..., actor_role=, actor_scopes=)` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 字段 ACL 管理 UI 大改
- 无调用方身份时的后台 cron 自动推断身份（见 `phase2-wiki-auto-identity-passthrough-evidence.md`：有启动身份已透传；无身份不伪造）
