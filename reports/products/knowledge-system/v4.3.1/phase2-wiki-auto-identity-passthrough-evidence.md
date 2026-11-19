---
doc_type: Report
title: Phase 2 — platform wiki_auto_update 身份透传（N07/N22 residual deepen）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / Wiki auto 身份透传（N07/N22 deepen）

> 实施权威：附录 H.1 / N07/N22；叠在 EvolutionRunner ACL 之上。  
> **未宣称** N07/N22 certified / 字段 ACL 管理 UI / 无启动身份时伪造 cron 角色。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| `_auto_wiki_update` 含 actor | pass | `test_auto_wiki_update_signature_has_actor` |
| ingest 透传 identity | pass | `test_documents_ingest_wires_identity_to_auto_wiki` |
| watch 启动捕获 + 轮询透传 | pass | `test_watch_directory_signature_and_wiki_call_wires_actor` |
| watch HTTP 接线 | pass | `test_kb_watch_route_passes_identity` |
| vault_to_wiki 透传 | pass | `test_vault_to_wiki_signature_wires_actor` |
| vault/wiki HTTP 接线 | pass | `test_vault_send_to_wiki_resolves_identity` |
| vault indexer 闭包 | pass | `test_vault_start_indexer_wires_actor` |
| vault index HTTP | pass | `test_vault_index_start_route_passes_identity` |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-platform/tests/test_wiki_auto_identity_passthrough_phase2.py -v
# 实测 2026-11-19：8 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Ingest | `documents_ingest` identity → `_auto_wiki_update` → `wiki_auto_update` |
| Watch | `kb_watch_directory` identity → `watch_directory` 闭包 → `wiki_auto_update` |
| Vault wiki | `vault_send_to_wiki` identity/body → `vault_to_wiki` → `wiki_auto_update` |
| Vault indexer | `vault_index_start` identity → `vault_start_indexer` 闭包 → `vault_to_wiki` |

## 明确未做

- N07/N22 certified 或关闭 ADR 例外
- 字段 ACL 管理 UI 大改
- 无调用方 / 无启动身份时的伪造 service 角色（空身份保持空，不做自动推断）
