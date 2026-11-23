---
doc_type: Report
title: Phase 2 — sufficient-freeze 程序收口（非 certified）
status: active
authority: supporting
measured_at: 2026-11-23
pilot_domain: lock-service
---

# Phase 2 / sufficient-freeze 程序收口

> 实施权威：附录 N 各面 deepen 已接线后，以 `*_freeze` 停止默认 deepen。  
> **未宣称** 任一 Nxx certified / Full unconditional / 关闭 ADR 例外行 / 生产达标。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| catalog `phase2_sufficient_freeze_complete: true` | pass | `n24-conformance-catalog.yaml` |
| 20 个 sufficient freeze 旗均为 true | pass | `SUFFICIENT_FREEZE_FLAGS` / `sufficient_freeze_missing==[]` |
| pack / core_ready 透传 complete | pass | `build_conformance_pack` / `evaluate_core_ready_gate` |
| `certified` 恒 false | pass | honesty |

## 命令

```bash
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -c "from core.harness.knowledge_pipeline.conformance_pack import load_conformance_catalog, sufficient_freeze_missing, evaluate_core_ready_gate; c=load_conformance_catalog(); assert c.get('phase2_sufficient_freeze_complete') is True; assert sufficient_freeze_missing(c)==[]; g=evaluate_core_ready_gate(); assert g['phase2_sufficient_freeze_complete'] is True; assert g['certified'] is False; print('ok')"
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_core_cert_path_phase2.py -v
```

## 明确未做

- 置 `certified` / 删除 ADR 例外
- 消费 residual（多域批量门户 / 生产 vendor 连库验收 / `$where` / 生产切写 / 准确率等；vendor 软依赖探测见 `phase2-n01-vendor-driver-matrix-evidence.md`；N02 薄门户见 `phase2-n02-object-type-publish-portal-evidence.md`）
- 恢复默认 deepen mop
