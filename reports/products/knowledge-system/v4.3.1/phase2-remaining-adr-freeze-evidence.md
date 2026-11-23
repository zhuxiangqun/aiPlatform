---
doc_type: Report
title: Phase 2 — 剩余 ADR 例外面批量冻结（sufficient / 非 certified）
status: active
authority: supporting
measured_at: 2026-11-23
pilot_domain: lock-service
---

# Phase 2 / 剩余 ADR 例外面批量冻结

> 实施权威：附录 N；仿 N09 / N01 / N02 freeze。  
> 范围：ADR 表中此前仍写「至全量/签字」、且 deepen 证据已接线的剩余项。  
> **未宣称** 任一 Nxx certified / 关闭 ADR 例外行 / 生产达标 / 准确率。

## 冻结清单

| Catalog flag | 等级 | ADR | Residual（仍开放） | Deepen 证据 |
|--------------|------|-----|-------------------|-------------|
| `n03_claim_freeze` | Core | N03 | 全量 Claim 生命周期 / certified | `phase2-claim-status-write-evidence.md` |
| `n04_n12_write_rbac_freeze` | Core | N04/N12 | 部署 RBAC 真源 / certified | `phase2-reviewer-rbac-evidence.md` |
| `n05_wiki_rebuild_freeze` | Extended | N05 | wiki_engine/FTS 全量 / certified | `phase2-wiki-rebuild-evidence.md` |
| `n06_query_gateway_freeze` | Core | N06 | 全部其它应用入口 / certified | `phase2-unified-query-gateway-evidence.md` |
| `n10_gold_eval_freeze` | Operational | N10 | 准确率宣称 / certified（LLM judge opt-in residual 已落地，见 `phase2-n10-llm-judge-residual-evidence.md`） | `phase2-knowledge-gold-eval-evidence.md` |
| `n11_n14_migration_freeze` | Operational | N11/N14 | 生产切写认证 / certified | `phase2-raw-fact-index-reconcile-evidence.md` |
| `n13_calibration_freeze` | Operational | N13/校准 | 真实 ECE 训练 / 准确率宣称 / certified | `phase2-calibration-pipeline-evidence.md` |
| `n17_record_semantics_freeze` | Core | N17 | semantic_cases 全量 / certified | `phase2-record-semantics-evidence.md` |
| `n18_deployed_rbac_freeze` | Core | N18 | 召回/聚合/导出/缓存全路径 / certified | `phase2-deployed-rbac-evidence.md` |
| `n19_fact_query_audit_freeze` | Extended | N19 | 全部旁路强制 / certified | `phase2-fact-query-wiki-engine-search-pages-hotpath-evidence.md` |
| `n20_constraint_layers_freeze` | Extended | N20 | list→dict 改写 / Lv4 / certified | `phase2-constraint-layers-evidence.md` |
| `n21_query_abstain_freeze` | Core | N21 | list 主返回类型改写 / certified | `phase2-query-abstain-citations-evidence.md` |
| `n23_ocs_freeze` | Operational | N23/OCS | 企业全域完整 / certified | `phase2-ocs-enterprise-scan-evidence.md` |

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| catalog 上述 flag 均为 true | pass | `n24-conformance-catalog.yaml` |
| conformance pack / core_ready 透传 | pass | `build_conformance_pack` / `evaluate_core_ready_gate` |
| 测试断言 freeze | pass | `test_core_cert_path_phase2` |
| ADR 期限改为「面足够」 | pass | `phase2-exception-adr.md` |
| `certified` 恒 false | pass | honesty（gate + pack） |

## 命令

```bash
python3 -c "import yaml; c=yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); assert c['n03_claim_freeze'] is True && c['n04_n12_write_rbac_freeze'] is True && c['n05_wiki_rebuild_freeze'] is True && c['n06_query_gateway_freeze'] is True && c['n10_gold_eval_freeze'] is True && c['n11_n14_migration_freeze'] is True && c['n13_calibration_freeze'] is True && c['n17_record_semantics_freeze'] is True && c['n18_deployed_rbac_freeze'] is True && c['n19_fact_query_audit_freeze'] is True && c['n20_constraint_layers_freeze'] is True && c['n21_query_abstain_freeze'] is True && c['n23_ocs_freeze'] is True"
PYTHONPATH=aiPlat-platform:aiPlat-core:aiPlat-infra .venv/bin/python -m pytest \
  aiPlat-core/core/tests/unit/test_harness/test_knowledge/test_core_cert_path_phase2.py -v
```

## 明确未做

- 任一 Nxx certified 或删除 ADR 例外行
- 恢复上述面的默认 deepen mop
- 生产切写认证 / 准确率宣称 / 企业全域 OCS 完整 / 全量门户与引擎
