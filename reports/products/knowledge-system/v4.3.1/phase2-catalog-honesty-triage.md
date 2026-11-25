---
doc_type: Report
title: Phase 2 — catalog exists 诚实锁盘点（非 ADR 表项）
status: active
authority: supporting
measured_at: 2026-11-24
pilot_domain: lock-service
catalog: reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml
exception_adr: reports/products/knowledge-system/v4.3.1/phase2-exception-adr.md
---

# Phase 2 / catalog 诚实锁盘点

> 范围：`n24-conformance-catalog.yaml` 中 `status: exists` 且 note 仍含深度缺口，但 **未** 单独列入 [`phase2-exception-adr.md`](./phase2-exception-adr.md) 例外表的项。  
> 判定三选一：**仍开放** / **已过时** / **并入既有刀**。  
> **禁止**：本盘点冒充附录 N certified / 关闭 ADR 例外 / 风险已接受签字。
>
> 2026-11-23：剩余 ADR 例外面已批量冻结（`phase2-remaining-adr-freeze-evidence.md`）；本表 residual 列仍开放，不因 freeze 关闭。
> 2026-11-23：Phase 2 sufficient-freeze 程序收口（`phase2-sufficient-freeze-closeout-evidence.md`）；仍不关闭 residual / certified。
> 2026-11-24：产品完备面显式 residual 已合入（N02 bulk / N24 ops console 薄壳 / N08 有界 Lv4 auto-close / N02 published-over-seed / N24 ops console 有界导出）；N24 运维台**产品面**已落地（默认可用 + schema JSON + **表单字段编辑器** + 浏览器导出；`full_ops_console=true` / `schema_form_editor=true`）；N02 **种子权威产品面第一刀**已落地（workspace_seeds 目录 + published-over-seed；`seed_product_surface=true`；不改写 seeds）；N08 **有界 Lv4 auto-close 产品面第一刀**已落地（默认可用；`lv4_product_surface=true`；仍仅 low）；N11/N14 **生产切写就绪产品面第一刀**已落地（默认可用；`prod_attest_product_surface=true`）；N10 **LLM judge 产品面第一刀**已落地（默认可用；`llm_judge_product_surface=true`）；**未**宣称 certified / seed_replacement_complete / full_action_lv4 / production_cutover_certified / accuracy_claim / 自由布局可视化设计器；freeze 仍 true。
> 2026-11-25：N24 运维台**产品面第二刀**已落地（四面板 + 通用 ops bundle；`ops_console_general_export=true`；audit_sample≤20；非 export_complete）；**未**宣称 certified / export_complete / 自由布局可视化设计器；freeze 仍 true。
> 2026-11-25：N02 种子权威**产品面第二刀**已落地（allowlist backup/write/restore；`seed_migrate_rollback=true`；不改写 workspace_seeds）；**未**宣称 seed_replacement_complete / certified；freeze 仍 true。
> 2026-11-25：N02 种子权威**产品面第二刀**已落地（allowlist backup/write/restore；`seed_migrate_rollback=true`；不改写 workspace_seeds）；**未**宣称 seed_replacement_complete / certified；freeze 仍 true。

## 本切片修复

| 项 | 判定 | 说明 |
|----|------|------|
| N09 catalog YAML | **已过时（结构债）** | `note` 误嵌进 evidence 列表导致 `ScannerError`，conformance pack 无法加载；已回顶层 item `note` |
| N11 note「切写未授权」 | **已过时** | 作业级切写授权已接线（`phase2-migration-cutover-auth-evidence.md`）；note 改为「非生产切写认证」 |
| N02 多域批量 | **已过时（residual + 产品面第一刀已落地）** | residual：`bulk_transition_object_types`；产品面：`bulk_transition_object_types_product`（`phase2-n02-bulk-portal-product-evidence.md`）；剩 certified / seed_replacement |
| N02 种子权威覆盖 | **已过时（residual + 产品面 slice-1/2 已落地）** | residual：`apply_published_seed_authority`；产品面：catalog/apply + allowlist migrate/rollback（`phase2-n02-seed-authority-product-evidence.md` + `phase2-n02-seed-authority-product-slice2-evidence.md`）；剩 in-tree seed_replacement_complete / certified |

## 未进 ADR 例外表的 exists 项

| ID | catalog note 摘要 | 判定 | 后续 |
|----|-------------------|------|------|
| N02 | ObjectType 人审发布 deepen + 管理端薄门户 + 多租户有界 bulk residual/**产品面** + published-over-seed residual + **种子权威产品面**（含 migrate/rollback slice-2）已接线；seed_replacement_complete / certified 仍缺 | **并入既有刀**（deepen+薄门户+bulk residual/产品面+seed residual/产品面 slice-1/2）+ **仍开放**（in-tree complete/certified） | deepen/门户见 ADR N02 + `phase2-object-type-publish-evidence.md` + `phase2-n02-object-type-publish-portal-evidence.md`；bulk residual 见 `phase2-n02-bulk-portal-residual-evidence.md`；bulk 产品面见 `phase2-n02-bulk-portal-product-evidence.md`；seed residual 见 `phase2-n02-seed-replace-residual-evidence.md`；种子产品面见 `phase2-n02-seed-authority-product-evidence.md` + `phase2-n02-seed-authority-product-slice2-evidence.md`；complete/certified 仍开放 |
| N05 | Wiki 有条件重建 deepen 已接线；wiki_engine/FTS 全量仍缺 | **并入既有刀**（deepen）+ **仍开放**（全量引擎） | deepen 见 ADR N05 + `phase2-wiki-rebuild-evidence.md`；全量仍开放 |
| N10 | Exact-match gold 流水线已接线；LLM judge opt-in residual + **产品面第一刀**已落地；准确率宣称仍缺 | **并入既有刀**（deepen + residual + 产品面）+ **仍开放**（准确率/certified） | deepen 见 ADR N10 + `phase2-knowledge-gold-eval-evidence.md`；residual 见 `phase2-n10-llm-judge-residual-evidence.md`；产品面见 `phase2-n10-llm-judge-product-evidence.md`；准确率宣称仍开放 |
| N15 | 标准包 schema 已发布 | **已过时**（无 deepen 债） | 保持 exists；无单独 deepen todo |
| N16 | phase0 schema validate | **已过时**（无 deepen 债） | 同上 |
| N17 | 记录级语义运行时权威 deepen 已接线；非 RBAC 真源 / 非全量 cases | **并入既有刀**（deepen）+ **仍开放**（全量） | deepen 见 ADR N17 + `phase2-record-semantics-evidence.md`；全量仍开放 |
| N18 | 部署侧 RBAC 真源 deepen 已接线；非召回全路径 / 非 certified | **并入既有刀**（deepen）+ **仍开放**（全路径） | deepen 见 ADR N18 + `phase2-deployed-rbac-evidence.md`；全路径仍开放 |
| N19 | Fact/Query 统一审计 + put_fact/unified/query_facts(_gateway)/MaterialsChat/GraphRAG/Wiki-KB/裸 list/KB Q&A·CRAG/统一 knowledge_retrieve/wiki_context/wiki_structured/wiki_search_pages_api/ontology_context(域)/URN+HTTP/`sys_graph_neighbors`/`sys_graph_query`/裸 `wiki_search_pages`/FDE clarify tenant/wiki_engine.search_pages(opt-in) 热路径 deepen 已接线；非全部旁路强制 / 非 certified | **并入既有刀**（deepen）+ **仍开放**（旁路全量） | deepen 见 ADR N19 + `phase2-fact-query-wiki-engine-search-pages-hotpath-evidence.md`；旁路全量仍开放 |
| N20 | 知识面 L1>L2>L3 + Gateway/put_fact/query_facts_gateway/MaterialsChat/GraphRAG/Wiki-KB/裸 list/`query_facts` list 热路径 deepen 已接线；非 list→dict 改写 / 非 certified | **并入既有刀**（deepen）+ **仍开放**（list→dict / certified） | deepen 见 ADR N20 + `phase2-constraint-layers-evidence.md`；list→dict 仍开放 |
| N21 | Fact/object_set + Wiki/KB + Materials RAG/trivial/cache_hit + GraphRAG + list n21_query 信封 deepen 已接线；非改写 list 主返回类型 / 非 certified | **并入既有刀**（deepen）+ **仍开放**（主返回类型改写） | deepen 见 ADR N21 + `phase2-query-abstain-citations-evidence.md`；list 主类型仍开放 |
| N14 生产对账 | Raw↔Fact↔Index 全链路 deepen 已接线；生产就绪 residual + **产品面第一刀**已落地；非生产切写认证 / 非 certified | **并入既有刀**（deepen + residual + 产品面）+ **仍开放**（生产认证/certified） | deepen 见 ADR N14 + `phase2-raw-fact-index-reconcile-evidence.md`；residual 见 `phase2-n11-production-attest-residual-evidence.md`；产品面见 `phase2-n11-production-attest-product-evidence.md`；生产认证仍开放 |

## 已在 ADR 例外表（本盘点不重复开刀）

N01 · N03 · N04/N12 · N06 · N07/N22 · N08 · N09 · N11/N14 · N13/校准 · N23/OCS · N24 · SLO

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| catalog YAML 可解析 | pass | `yaml.safe_load` + `build_conformance_pack` |
| 未宣称任何 Nxx certified | pass | 本文件 honesty |
| 未关闭 ADR 例外行 | pass | `phase2-exception-adr.md` 仍 active |

## 命令

```bash
python3 -c "import yaml; yaml.safe_load(open('reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml')); print('ok')"
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 -c \
  "from core.harness.knowledge_pipeline.conformance_pack import build_conformance_pack; p=build_conformance_pack(); print('items', len((p.get('catalog') or {}).get('items') or p.get('items') or []))"
```

## 明确未做

- 关闭任何 ADR 例外 / 置 `certified=true`
- ObjectType seed_replacement_complete / 原地改写 workspace_seeds、Wiki 全量引擎、gold 准确率宣称、N17 semantic_cases 全量对 Fact Store、N18 召回/聚合/导出全路径、N19 全部旁路强制落快照、N20 list→dict 改写/certified、N21 Wiki/KB list 主返回类型改写、N14 生产切写认证/自动修复写回、N08 full_action_lv4 / 中高风险放行 / certified、N24 自由布局可视化设计器 / certified
