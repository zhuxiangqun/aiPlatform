---
doc_type: Report
title: Phase 0 — 知识系统资产盘点（相对 v4.3.1）
status: active
authority: supporting
measured_at: 2026-11-15
pilot_domain: lock-service
plan_ref: docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md
---

# Phase 0：资产 / owner 清单

> 对照实施计划 §3 / §8.1。状态：`exists` / `partial` / `missing`。  
> 每条必须有路径证据；禁止凭文档推断「已符合」。

| # | 计划概念 | 状态 | 现码锚点（证据） | Owner（建议） |
|---|----------|:----:|------------------|---------------|
| 1 | Raw 不可变快照 | missing | `DataSourceConfig` 仅有 name/type/connection/mapping，无 content_hash/locator/snapshot（`aiPlat-core/core/harness/ontology_engine/data_source.py:30-35`） | 平台知识系统 |
| 2 | Source Registry（附录 A） | partial | `DataSourceRegistry` 存在（同文件 `:227`），可按 `source_id` 取源与映射（`:254-321`）；缺 hash/抓取时间/撤回策略 | 平台知识系统 |
| 3 | Ontology ObjectType / LinkType | partial | 域 YAML 类/状态机：`aiPlat-core/workspace_seeds/ontologies/lock-service.yaml`（`version: "1.2.0"` L4）；运行时 `DomainRouter.list_domains`（`domain_router.py:340`）；`GraphIndex.load`（`graph_index.py:1172`）。非附录 B JSON Schema 契约对象 | FDE/业务（语义）+ 平台 |
| 4 | Fact / Claim / Evidence Store（附录 D/L） | missing | 全仓无 `FactStore`/`FactRecord`/`ClaimRecord` 实现类（`rg` 无命中生产实现） | 平台知识系统 |
| 5 | 抽取侧 evidence 字符串 | partial | `EntityExtractor` 产出 `evidence` 字段（`extractor.py:136-149,449-464`）；`PendingExtractionStore` SQLite 待审（`:808-927`）— 非 Fact Store，无 review/lifecycle 分状态机 | 平台知识系统 |
| 6 | Object projection / GraphIndex | partial | `GraphIndex`（`graph_index.py:110`）；`write_extraction_to_graph_index`（extractor）；`GraphRAGRetriever`（`knowledge_pipeline/retriever.py:20`）。图为投影，但事实源仍混 Wiki/KB | 平台知识系统 |
| 7 | Wiki 读模型 | missing（相对目标） | `write_page`/`update_page` 可写（`wiki_engine.py:403,1110`）→ Wiki 仍是可写知识面，非「仅派生读模型」 | 平台知识系统 |
| 8 | Wiki 派生重建钩子 | partial | 写后 `rebuild_metrics` / `invalidate_graph_cache` / DomainRouter 重建（`wiki_engine.py:631-646,1240-1257`）；无「有条件重建分类：精确重放/语义重建/不可重建」契约 | 平台知识系统 |
| 9 | 向量 / SQLite KB | partial | `SqliteEmbeddingRetriever` 按 tenant 分库与 SQL 过滤（`sqlite_retriever.py:80-84,131-133,325-327`） | 平台知识系统 |
| 10 | 查询租户前置 | partial | `KnowledgeQuery.tenant_id`（`types.py:110`）；Wiki retriever mismatch 阻断（`wiki_retriever.py:326-331`）。字段级 ACL / 全入口统一 Gateway 契约（附录 M）未齐 | 平台安全 + 知识 |
| 11 | Action / Policy / Approval | partial | `ActionContractModel.require_approval` / `rollback_action_id`（`action_contract.py:111-116`）；`AsyncActionRegistry` 审批门（`action_registry.py:341-359`）。非全知识写入路径；`idempotency`/`kill_switch` 未在 registry 主路径完整落地 | 平台治理 |
| 12 | ObjectSet / SDK | missing | `rg ObjectSet\|object_set` 于 `aiPlat-core/core` 无生产实现 | 平台知识系统 |
| 13 | Scenario / Package 隔离 | missing | 标准附录有示例；实现无 Scenario 主事实隔离 / Package 签名 | 平台知识系统 |
| 14 | Confidence 校准 / OCS | missing | ECE/Brier/OCS 仅出现在标准与归档叙事；无实现校准报告产物 | 平台评测 + 知识 |
| 15 | 标准包 schemas | exists | `docs/standards/knowledge-system/v4.3.1/schemas/`；Phase 0 校验 22+30 通过（见 `phase0-standard-pack-baseline.md`） | 标准 owner |

## 迁移映射（指向计划 §8，不重写）

```text
现有 Wiki        → 目标：读模型（当前仍可写 → 差距）
GraphIndex       → 对象投影（已有，待挂 Fact Store）
向量 KB          → Raw/检索索引（有租户分片，缺 Raw hash）
业务库 / DataSource → Source 绑定（有 registry 雏形，缺附录 A）
PendingExtraction → 应汇入 Claim/Evidence + 人审，而非长期第二事实源
```

权威步骤仍见：`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md` §8。
