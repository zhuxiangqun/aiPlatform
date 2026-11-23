---
doc_type: Report
title: Phase 2 — N01 Raw/连接器面冻结（Core-sufficient）
status: active
authority: supporting
measured_at: 2026-11-23
pilot_domain: lock-service
---

# Phase 2 / N01 Raw 完整性面冻结

> 实施权威：附录 N.2 N01；仿 N09 / N07 / N08 / N24 / SLO freeze。  
> **未宣称** N01 certified / vendor 驱动全量矩阵 / 关闭 ADR 例外行。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| catalog `n01_raw_integrity_freeze: true` | pass | `n24-conformance-catalog.yaml` |
| conformance pack / core_ready 透传 | pass | `build_conformance_pack` / `evaluate_core_ready_gate` |
| 测试断言 freeze | pass | `test_core_cert_path_phase2` |
| ADR 期限「Raw 面足够」 | pass | `phase2-exception-adr.md` N01 |
| `certified` 恒 false | pass | honesty（gate + pack） |

## 命令

```bash
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n01_raw_integrity_freeze'] is True"
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_core_cert_path_phase2.py -v
```

## 接线

| 入口 | 路径 |
|------|------|
| Catalog | `n01_raw_integrity_freeze` / `n01_raw_integrity_note` |
| Pack/Gate | `conformance_pack.py` 透传布尔旗 |

## 明确未做

- N01 certified 或删除 ADR 例外行
- PG/MySQL/Oracle 等 vendor 驱动全量矩阵
- 取消 process Raw opt-out 逃生舱
- 恢复默认 N01 deepen mop
