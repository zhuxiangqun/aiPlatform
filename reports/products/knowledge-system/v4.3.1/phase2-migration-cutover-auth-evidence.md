---
doc_type: Report
title: Phase 2 — 迁移切写授权证据（N11/N14 deepen）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
---

# Phase 2 / N11/N14 切写授权证据

> 实施权威：附录 N N11/N14 partial 加深。  
> **未宣称** 生产切写认证 / Raw↔Fact↔Index 全链路 / N11·N14 certified。  
> 作业级授权：`AIPLAT_KNOWLEDGE_CUTOVER_TOKEN` + actor/reason + 对账干净。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 错/缺 token 拒绝 | pass | suite `bad_token_denied` |
| 未授权切写拒绝 | pass | suite `unauthorized_cutover_denied` |
| 正确授权 | pass | suite `authorize_ok` |
| 授权后 phase=cutover | pass | suite `cutover_phase_ok` |
| 生产认证恒 false | pass | suite honesty_* |
| 可撤销 | pass | suite `revoke_ok` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_migration_cutover_auth_phase2.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `authorize_migration_cutover` / `request_write_cutover` / suite/gate |
| Facade | `authorize_knowledge_migration_cutover` / `request_knowledge_migration_write_cutover` / suite/gate |

## 明确未做

- 生产环境自动切写 / 生产 certified
- Raw↔Fact↔Index 全链路对账（N14 prod）
- N11/N14 certified / 关闭 ADR 例外
