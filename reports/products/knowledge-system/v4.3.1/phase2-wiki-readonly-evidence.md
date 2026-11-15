---
doc_type: Report
title: Phase 2 — Wiki 读模型硬门（lock-service 试点）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / Wiki 只读最小切片证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §3（有 Wiki 无事实源 → 改为读模型）。  
> **未宣称**附录 N #5 全量符合 / 重建条件分类契约 / 全局禁写 / ObjectSet。

## 检查表

| 条件 | 状态 | 证据 |
|------|:----:|------|
| 配置名单内 collection 人工 POST/DELETE 被拦 | pass | `AIPLAT_WIKI_READ_MODEL_COLLECTIONS=lock-service,lock-kb`；`wiki.py` create/delete/delete-all → 403 `wiki_is_read_model` |
| 未配置 / 名单外仍可人工写 | pass | 默认空名单；`test_unconfigured_means_no_read_model` / `test_manual_write_allowed_on_non_configured` |
| 破窗显式且可观测 | pass | `AIPLAT_WIKI_ALLOW_MANUAL_WRITE=1` → WARNING 后放行；`test_break_glass_allows_manual_write` |
| 编译器 `write_page` 不受影响 | pass | `test_compiler_write_page_unaffected` 直调 `write_page(..., collection_id=lock-kb)` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-platform:. python3 -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_wiki_read_model_gate.py -v
```

## 接线

| 入口 | 路径 |
|------|------|
| 策略模块 | `harness/knowledge/wiki_read_model.py` |
| HTTP 人工写 | `api/routers/wiki.py` `POST /pages`、`DELETE /pages/{title}`、`DELETE /pages-all` |
| 配置 | `AIPLAT_WIKI_READ_MODEL_COLLECTIONS`（必填试点名单，默认空）；`AIPLAT_WIKI_ALLOW_MANUAL_WRITE`（破窗） |

## 明确未做（后续）

- 重建条件分类契约（exact_replay / semantic / non-rebuildable）
- ObjectSet SDK / Interface
- FunctionContract → 见 `phase2-function-contract-evidence.md`（本批另切片）
- 字段级 ACL；管理端 Wiki UX 规模化禁写提示
- 全局所有 collection 默认读模型
