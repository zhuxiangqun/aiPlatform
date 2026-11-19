---
doc_type: Report
title: Phase 2 — Knowledge SDK Python 写盘安装（W6 deepen）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / Knowledge SDK 写盘安装（W6 deepen）

> 实施权威：附录 E.3；在最小 SDK 切片之上，将 Python 源码落到 allowlist  
> ``aiplat-sdk/aiplat/knowledge/``。  
> **未宣称** 多语言包发布 / PyPI 发布 / 字段 ACL / N24。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 非 allowlist 根拒绝 | pass | `test_resolve_rejects_non_allowlisted_root` |
| allowlist 写盘成功 | pass | `test_install_writes_under_allowlist` |
| 缺 `kb:read` 拒绝且不写盘 | pass | `test_install_policy_denied` |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_sdk_write_install_phase2.py -v
# 预期：3 passed
```

实测（2026-11-19，`.venv` Python 3.11）：`3 passed`。

## 接线

| 入口 | 路径 |
|------|------|
| 核心 | `sdk_generator.install_sdk_python` / `resolve_sdk_install_root` |
| Facade | `install_knowledge_sdk` |
| HTTP | `POST …/fde/sdk/install/{object_type}` |

## 明确未做

- TypeScript / 其他语言包或商店发布
- 自动改写 `aiplat-sdk/aiplat/__init__.py` 公开 API
- 字段级 ACL / 附录 N 全量
