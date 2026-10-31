# Ontology API v0（草案）

> Capability: **ontology** · Central · **A1 wired**  
> Schema: `contracts/schemas/ontology_api.schema.json` + `healthz.schema.json`  
> Adapter: `core.harness.knowledge.ontology_api` · Facade: `wiki_structured_query_api` 等

## 目标

冻结对外交换面：**entity / relation / graph / wiki / asset**，消费者只经 CoreFacade / 平台路由，禁止跨模块读表。

## v0 信封

| 字段 | 含义 |
|------|------|
| `schema_version` | 固定 `ontology.api.v0` |
| `kind` | entity \| relation \| graph \| wiki \| asset \| query_result |
| `payload` | kind 对应正文（结构后续分 schema 细化） |
| `domain_id` | 域（可选） |
| `refs` | 外部引用（Wiki 页、资产 URI 等） |

## 首版边界

- **只读盘点**优先（文档 + Wiki）；不承诺全资产类型  
- 不承担 Agent 生命周期 / FDE 项目事实 / Eval 评分  
- 写路径（抽取确认、跨域边）仍走既有 governance 门，不另开平行 API  

## Healthz

`product_id=ontology` · `deploy_unit=central` · `mode=read_only|read_write`

## 接线

| Path | Behavior |
|------|----------|
| `…/wiki/query-structured` | 响应含 `ontology_api` |
| `…/wiki/pages` | 响应含 `ontology_api` |
| `…/wiki/engine/graph-stats/{domain_id}` | 响应含 `ontology_api` |
| `CoreFacade.wiki_*_api` / `get_graph_health_api` | 信封 helper |

## 验证

```bash
python3 reports/five-products/modules/ontology/contracts/validate_sample.py
python3 -m pytest aiPlat-core/core/tests/unit/test_ontology_api_v0.py -q
```
