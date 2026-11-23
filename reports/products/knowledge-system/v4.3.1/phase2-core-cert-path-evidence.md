---
doc_type: Report
title: Phase 2 — Core 可认证路径闭合（等级映射 + core_ready + 人工徽章）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
---

# Phase 2 / Core cert path 证据

> 实施权威：白皮书 §16.1 / 附录 N.1–N.2 / 实施方案 §1.1·§14.1。  
> 试点 Core：`pilot_certified=true`（非作者 **朱鸿林** 已复核确认，`pilot-core-approval-record.approved.json`）。  
> 后续：Extended/Operational/全量见各自证据；全量 `certified` 由独立全量批准置真（朱向群，conditional）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| 三份文档等级映射 | pass | 白皮书 §16.1 / 附录 N / 实施方案 DoD |
| catalog `level` + `core_minimum_ids` | pass | `n24-conformance-catalog.yaml` |
| Core 12 项 exists（Core-scoped） | pass | catalog status |
| N09 探针冻结 | pass | `n09_core_probe_freeze: true` |
| N07/N22 H.1 条件面冻结（Extended） | pass | `n07_n22_h1_condition_freeze: true`（非 Core 最小集冒充） |
| N08 Action Policy 面冻结（Extended） | pass | `n08_action_policy_freeze: true`（非 Core 最小集冒充） |
| N24 统一审计面冻结（Operational） | pass | `n24_unified_audit_freeze: true`（非 Core 最小集冒充） |
| SLO 遥测面冻结（Operational） | pass | `slo_telemetry_freeze: true`（wiring≠attainment） |
| N01 Raw/连接器面冻结（Core） | pass | `n01_raw_integrity_freeze: true` |
| N02 ObjectType 发布面冻结（Core） | pass | `n02_object_type_freeze: true` |
| N03 面冻结（Core） | pass | `n03_claim_freeze: true` |
| N04/N12 面冻结（Core） | pass | `n04_n12_write_rbac_freeze: true` |
| N05 面冻结（Extended） | pass | `n05_wiki_rebuild_freeze: true` |
| N06 面冻结（Core） | pass | `n06_query_gateway_freeze: true` |
| N10 面冻结（Operational） | pass | `n10_gold_eval_freeze: true` |
| N11/N14 面冻结（Operational） | pass | `n11_n14_migration_freeze: true` |
| N13/校准 面冻结（Operational） | pass | `n13_calibration_freeze: true` |
| N17 面冻结（Core） | pass | `n17_record_semantics_freeze: true` |
| N18 面冻结（Core） | pass | `n18_deployed_rbac_freeze: true` |
| N19 面冻结（Extended） | pass | `n19_fact_query_audit_freeze: true` |
| N20 面冻结（Extended） | pass | `n20_constraint_layers_freeze: true` |
| N21 面冻结（Core） | pass | `n21_query_abstain_freeze: true` |
| N23/OCS 面冻结（Operational） | pass | `n23_ocs_freeze: true` |
| Phase 2 sufficient-freeze 程序收口 | pass | `phase2_sufficient_freeze_complete: true` |
| `core_ready` 门 | pass | `evaluate_core_ready_gate` |
| FDE HTTP 接线 | pass | `GET …/conformance-pack/core-ready` / `pilot-core-cert` |
| 无批准时 pilot_certified 恒 false | pass | 缺路径 / superseded pending + honesty 测 |
| 有非作者批准时 pilot_certified | pass | `pilot-core-approval-record.approved.json`（朱鸿林） |
| 本门不自动置全量 certified | pass | honesty（全量须独立批准） |

## 命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform:. .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_conformance_pack_phase2.py \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_core_cert_path_phase2.py -v
```

## 明确未做

- Extended / Operational 全量 / 附录 N 24/24
- 自动 `certified=true`（全量徽章仍禁止无独立全量批准）
