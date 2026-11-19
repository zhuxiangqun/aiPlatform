---
doc_type: Report
title: Phase 2 — agents/jobs/pipeline session 运行时回退 SSOT（N09 Batch K60）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / agents+pipeline session runtime fallbacks（Batch K60）证据

> 实施权威：附录 N N09 partial 加深（agents/jobs/plugins/pipeline/compressor/langgraph/tool/skill/policy_gate 运行时 `session_id or "default"` → `DomainRouter.default_session()`）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| helper 稳定 | pass | `test_helper_stable` |
| 目标文件走 SSOT | pass | `test_targets_use_session_ssot` |
| 目标文件无运行时字面量回退 | pass | `test_target_runtime_session_fallbacks_empty` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_agents_pipeline_session_fallbacks_k60.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| agents base / materials_chat / routers agents·jobs·plugins | session 回退 |
| pipeline_engine / compressor / langgraph react | memory/namespace session |
| integration tool/skill + policy_gate | sess_id 回退 |

## 明确未做

- `harness/integration.py` / `integration/__init__.py` / `server.py` / platform approvals·gateway / memory manager·profile_builder / seci_engine 残留 → 见 K61
- N09 / 附录 N 全量认证（certified 仍 false）
