---
doc_type: Report
title: Phase 2 — catalog exists 诚实锁盘点（非 ADR 表项）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
catalog: reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml
exception_adr: reports/products/knowledge-system/v4.3.1/phase2-exception-adr.md
---

# Phase 2 / catalog 诚实锁盘点

> 范围：`n24-conformance-catalog.yaml` 中 `status: exists` 且 note 仍含深度缺口，但 **未** 单独列入 [`phase2-exception-adr.md`](./phase2-exception-adr.md) 例外表的项。  
> 判定三选一：**仍开放** / **已过时** / **并入既有刀**。  
> **禁止**：本盘点冒充附录 N certified / 关闭 ADR 例外 / 风险已接受签字。

## 本切片修复

| 项 | 判定 | 说明 |
|----|------|------|
| N09 catalog YAML | **已过时（结构债）** | `note` 误嵌进 evidence 列表导致 `ScannerError`，conformance pack 无法加载；已回顶层 item `note` |
| N11 note「切写未授权」 | **已过时** | 作业级切写授权已接线（`phase2-migration-cutover-auth-evidence.md`）；note 改为「非生产切写认证」 |

## 未进 ADR 例外表的 exists 项

| ID | catalog note 摘要 | 判定 | 后续 |
|----|-------------------|------|------|
| N02 | ObjectType 人审发布 deepen 已接线；全量门户/种子替换仍缺 | **并入既有刀**（deepen）+ **仍开放**（全量门户） | deepen 见 ADR N02 + `phase2-object-type-publish-evidence.md`；全量门户仍开放 |
| N05 | Wiki 有条件重建 deepen 已接线；wiki_engine/FTS 全量仍缺 | **并入既有刀**（deepen）+ **仍开放**（全量引擎） | deepen 见 ADR N05 + `phase2-wiki-rebuild-evidence.md`；全量仍开放 |
| N10 | Exact-match gold 流水线已接线；LLM judge/准确率宣称仍缺 | **并入既有刀**（deepen）+ **仍开放**（准确率） | deepen 见 ADR N10 + `phase2-knowledge-gold-eval-evidence.md`；准确率宣称仍开放 |
| N15 | 标准包 schema 已发布 | **已过时**（无 deepen 债） | 保持 exists；无单独 deepen todo |
| N16 | phase0 schema validate | **已过时**（无 deepen 债） | 同上 |
| N17 | 记录级语义运行时权威 deepen 已接线；非 RBAC 真源 / 非全量 cases | **并入既有刀**（deepen）+ **仍开放**（全量） | deepen 见 ADR N17 + `phase2-record-semantics-evidence.md`；全量仍开放 |
| N18 | 部署侧 RBAC 真源 deepen 已接线；非召回全路径 / 非 certified | **并入既有刀**（deepen）+ **仍开放**（全路径） | deepen 见 ADR N18 + `phase2-deployed-rbac-evidence.md`；全路径仍开放 |
| N19 | Fact/Query 统一审计 + put_fact/Gateway 热路径 deepen 已接线；非全部旁路强制 / 非 certified | **并入既有刀**（deepen）+ **仍开放**（旁路全量） | deepen 见 ADR N19 + `phase2-fact-query-audit-evidence.md`；旁路全量仍开放 |
| N20 | 知识面 L1>L2>L3 栈 deepen 已接线；非全域强制 / 非 certified | **并入既有刀**（deepen）+ **仍开放**（全域） | deepen 见 ADR N20 + `phase2-constraint-layers-evidence.md`；全域仍开放 |
| N21 | Fact/object_set + Wiki/KB + Materials RAG/trivial/cache_hit + GraphRAG + list n21_query 信封 deepen 已接线；非改写 list 主返回类型 / 非 certified | **并入既有刀**（deepen）+ **仍开放**（主返回类型改写） | deepen 见 ADR N21 + `phase2-query-abstain-citations-evidence.md`；list 主类型仍开放 |
| N14 生产对账 | Raw↔Fact↔Index 全链路 deepen 已接线；非生产切写认证 / 非 certified | **并入既有刀**（deepen）+ **仍开放**（生产认证） | deepen 见 ADR N14 + `phase2-raw-fact-index-reconcile-evidence.md`；生产认证仍开放 |

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
- 全量 ObjectType 人审、Wiki 全量、gold 准确率宣称、N17 semantic_cases 全量对 Fact Store、N18 召回/聚合/导出全路径、N19 全部旁路强制落快照、N20 全域强制分层、N21 Wiki/KB list 主返回类型改写、N14 生产切写认证/自动修复写回
