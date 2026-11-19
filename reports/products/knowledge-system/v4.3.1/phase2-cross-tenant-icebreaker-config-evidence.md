---
doc_type: Report
title: Phase 2 — icebreaker 业务域键配置外置证据（N09 Batch K48）
status: active
authority: supporting
measured_at: 2026-11-18
pilot_domain: lock-service
---

# Phase 2 / icebreaker config-driven（Batch K48）证据

> 实施权威：附录 N N09 partial 加深（`generate_icebreaker_questions` 内联业务域键 → `workspace_seeds/fde/icebreaker_questions.yaml`）。  
> **未宣称** N09 certified。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| YAML seed 存在 | pass | `test_yaml_seed_exists_and_has_domains` |
| Python 无内联 icebreaker_map 业务域键 | pass | `test_service_has_no_inline_business_domain_icebreaker_map` |
| 加载 + 生成可用 | pass | `test_load_and_generate_from_yaml` |
| certified 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_apps/test_fde/test_icebreaker_config_k48.py -v
# 预期：3 passed
```

## 接线

| 入口 | 路径 |
|------|------|
| Seed | `aiPlat-core/workspace_seeds/fde/icebreaker_questions.yaml` |
| Loader | `_load_icebreaker_map()` / `AIPLAT_ICEBREAKER_QUESTIONS_PATH` |
| API | `generate_icebreaker_questions` |

## 明确未做

- `tenant_id` knowledge 层 SSOT → 见 Batch K49；其它层签名默认仍开放
- wiki collection 字面量（consultant_knowledge）
- N09 / 附录 N 全量认证（certified 仍 false）
