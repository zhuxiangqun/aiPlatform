---
doc_type: Report
title: Phase 2/4 — Conformance / 认证证据包最小切片（W10 / 附录 N）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
---

# W10 / Conformance Pack（附录 N + §9.4）证据

> 实施权威：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §W10 / §9.4。  
> 标准：`docs/standards/knowledge-system/v4.3.1/normative-appendix.md` §N。  
> **未宣称** Core 符合 / 24/24 认证 / 生产 SLO；仅证明目录可机读 + 证据路径可解析 + 结构门槛门。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 目录恰 24 项 | pass | `test_repo_catalog_has_exactly_24_and_gate_passes` |
| claimed 证据路径存在 | pass | 同测 + `test_gate_fails_when_claimed_evidence_missing` |
| 结构门 pass ≠ certified | pass | `test_honesty_flags_never_auto_certify` |
| §9.4 槽位齐全（含显式缺失） | pass | catalog `certification_slots` 7 槽 |
| N24 刷新非过期基线 | pass | partial≥10、missing≤6 |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_conformance_pack_phase2.py -q
```

## 接线

| 入口 | 路径 |
|------|------|
| 目录 SSOT | `reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml` |
| 核心 | `conformance_pack.build_conformance_pack` / `evaluate_conformance_gate` |
| Facade | 同名 |
| HTTP | `GET …/fde/conformance-pack` · `GET …/fde/conformance-pack/gate` |

## 明确未做（后续）

- 人工认证流程 / 非作者批准记录绑定
- 生产 SLO 遥测采集（目标登记见 Batch F1 `phase2-slo-target-evidence.md`；例外见 `phase2-exception-adr.md`）
- N04 / N12 全量认证（N18 见 `phase2-implementer-semantics-evidence.md` 最小切片）
- 宣称 24/24 或 Core 符合
