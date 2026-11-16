---
doc_type: Report
title: Phase 2 — Ontology Package 最小切片证据（W9 / H.3）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# Phase 2 / Ontology Package（W9）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W9。  
> 标准形状：`docs/standards/knowledge-system/v4.3.1/normative-appendix.md` §H.3。  
> **未宣称**附录 N 全量符合；仅证明包可验证 + 版本兼容 + 依赖锁定 + 回滚。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 发布后 content_hash 可重算一致 | pass | `test_publish_validate_hash` |
| 篡改 payload → hash mismatch | pass | 同上 |
| 兼容矩阵 forward/backward | pass | `test_compatibility_matrix` |
| 依赖锁定 `>=` 满足 | pass | `test_dependency_lock_and_rollback` |
| 回滚切换 active | pass | 同上 |
| 跨租户读隐藏 | pass | `test_cross_tenant_hidden` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_ontology_package_phase2.py -v
# 预期：4 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `ontology_package.publish_package` / `validate_package` / `check_compatibility` / `check_dependency_lock` / `rollback_package` |
| Facade | `publish_ontology_package` 等 |
| HTTP | `POST/GET …/fde/ontology-packages*` |

## 明确未做（后续）

- PKI / 密钥管理签名（本切片仅 content_hash）
- 自动执行 `migrations` SQL
- 附录 N 全量符合
