---
doc_type: Report
title: Phase 2 — ABox ACL H.1 有界条件面冻结（N07/N22 Extended-sufficient）
status: active
authority: supporting
measured_at: 2026-11-23
pilot_domain: lock-service
---

# Phase 2 / ABox ACL H.1 有界条件面冻结（N07/N22）

> 实施权威：附录 H.1 / N07/N22；仿 N09 `n09_core_probe_freeze`。  
> **未宣称** N07/N22 certified / `$where`/`$expr` / 任意 RBAC / 关闭 ADR 例外行。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| catalog `n07_n22_h1_condition_freeze: true` | pass | `n24-conformance-catalog.yaml` |
| conformance pack / core_ready 透传 | pass | `build_conformance_pack` / `evaluate_core_ready_gate` |
| 测试断言 freeze | pass | `test_core_cert_path_phase2` |
| ADR 期限「有界 H.1 足够」 | pass | `phase2-exception-adr.md` N07/N22 |
| `certified` 恒 false | pass | honesty（gate + pack） |

## 命令

```bash
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n07_n22_h1_condition_freeze'] is True"
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_core_cert_path_phase2.py -v
# 实测 2026-11-23：pass
```

## 接线

| 入口 | 路径 |
|------|------|
| Catalog | `n07_n22_h1_condition_freeze` / `n07_n22_h1_condition_note` |
| Pack/Gate | `conformance_pack.py` 透传布尔旗 |

## 明确未做

- N07/N22 certified 或删除 ADR 例外行
- `$where` / `$expr` / 任意自由 RBAC 轴
- 恢复默认 condition-op deepen（bool-depth +1 / nest≥3）
