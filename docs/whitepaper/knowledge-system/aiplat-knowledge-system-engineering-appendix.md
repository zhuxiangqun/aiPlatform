# aiPlat 知识体系工程附录

> **版本**：v1.0 · 2026-11-11  
> **性质**：工程示例 / 字段字典 / API 参考  
> **状态**：非规范性（Non-normative）  
> **配套**：《aiPlat 知识体系技术白皮书（可读版）》（同目录）  
> **重要说明**：本附录中的 JSON、表结构、API 仅为**示例**，不是实现规范；规范以白皮书正文的 MUST/SHOULD 为准。

---

## 阅读方法

每个代码块按三行读：

1. **这段说明什么**：它在解释哪个概念；
2. **关键字段**：哪些字段是必须理解的；
3. **不是什么**：避免把示例当规范。

---

## A. Source Registry

### A.1 一段说明

Source Registry 记录“这份资料从哪里来、哪一刻的快照、内容 hash、谁能访问”。

**关键字段：**

- `source_id`：资料实体 ID；
- `snapshot_uri`：不可变快照位置；
- `sha256`：内容 hash，用于幂等/去重；
- `revision`：第几版；
- `status`：active/tombstone。

**不是什么：**

- 不是原始文件本身；
- 不是“活 URL”；
- 不是 Wiki 页面。

```json
{
  "source_id": "src-2026-11-11-001",
  "tenant_id": "tenant-a",
  "collection_id": "support-kb",
  "kind": "web",
  "uri": "https://example.com/docs/refund",
  "snapshot_uri": "s3://aiplat-raw/tenant-a/src-2026-11-11-001.html",
  "sha256": "9f2c...",
  "fetched_at": "2026-11-11T08:00:00Z",
  "revision": 3,
  "license": "company-internal",
  "acl": ["group:support"],
  "connector": "web_clipper",
  "status": "active",
  "immutable": true
}
```

### A.2 字段字典

| 字段 | 类型 | 必填 | 说明 |
|---|---|:---:|---|
| source_id | string | 是 | 全局唯一 |
| tenant_id | string | 是 | 隔离边界 |
| collection_id | string | 是 | 集合 |
| kind | enum | 是 | web/file/obsidian/repo/saas/db/media/human/dataset |
| uri | string | 是 | 来源地址 |
| snapshot_uri | string | 是 | 不可变快照 |
| sha256 | string | 是 | 内容 hash |
| fetched_at | ISO8601 | 是 | 抓取/接收时间 |
| revision | int | 是 | 从 1 开始 |
| license | string | 否 | 许可 |
| acl | array | 是 | 访问控制 |
| connector | string | 是 | 适配器 |
| status | enum | 是 | active/tombstone |
| immutable | bool | 是 | 必须 true |

---

## B. Ontology（TBox）

### B.1 一段说明

本体只定义 schema，不存具体事实。

**关键字段：**

- `classes`：类；
- `relations`：关系；
- `axioms`：公理/约束；
- `version`：版本。

**不是什么：**

- 不是实体数据；
- 不是 Wiki；
- 不是图谱。

```json
{
  "ontology_id": "customer-support",
  "version": "1.2.0",
  "classes": [
    {
      "id": "Ticket",
      "label": "工单",
      "properties": [
        {"id": "status", "type": "enum", "values": ["open", "closed"]}
      ]
    }
  ],
  "relations": [
    {"id": "assigned_to", "from": "Ticket", "to": "Person", "cardinality": "many-to-one"}
  ],
  "axioms": [
    {"id": "ticket_has_owner", "rule": "Ticket -> assigned_to exactly 1 Person"}
  ],
  "states": [
    {"id": "ticket_lifecycle", "initial": "open", "transitions": [{"from": "open", "to": "closed"}]}
  ]
}
```

### B.2 字段字典

| 字段 | 类型 | 必填 | 说明 |
|---|---|:---:|---|
| ontology_id | string | 是 | 域 ID |
| version | semver | 是 | 版本 |
| classes[].id | string | 是 | 类 ID |
| classes[].properties | array | 否 | 属性 |
| relations[].from/to | string | 是 | 域/值域 |
| relations[].cardinality | enum | 否 | 基数 |
| axioms[].rule | string | 是 | 约束 |
| states[] | array | 否 | 状态机 |

---

## C. Entity / Relation / Claim

### C.1 Entity

**说明：** 一个本体类的实例。

**关键字段：** `entity_id`、`class_id`、`source_refs`、`confidence`、`review_status`。

**不是什么：** 不是 Wiki 页；不是向量。

```json
{
  "entity_id": "ent-ticket-123",
  "tenant_id": "tenant-a",
  "class_id": "Ticket",
  "properties": {"status": "open", "priority": "high"},
  "source_refs": ["src-2026-11-11-001"],
  "confidence": 0.92,
  "review_status": "reviewed",
  "valid_from": "2026-11-11T08:00:00Z",
  "valid_to": null
}
```

### C.2 Relation

**说明：** 两个实体之间的关系。

**关键字段：** `from`、`type`、`to`、`source_refs`、`valid_from/to`。

```json
{
  "relation_id": "rel-123",
  "tenant_id": "tenant-a",
  "from": "ent-ticket-123",
  "type": "assigned_to",
  "to": "ent-person-456",
  "source_refs": ["src-2026-11-11-001"],
  "confidence": 0.9,
  "valid_from": "2026-11-11T08:00:00Z",
  "valid_to": null
}
```

### C.3 Claim

**说明：** 一条可引用断言，必须有 evidence。

**关键字段：** `claim_id`、`text`、`evidence`、`confidence`、`review_status`。

```json
{
  "claim_id": "cl-001",
  "tenant_id": "tenant-a",
  "text": "退款需在购买后 30 天内申请",
  "evidence": [
    {"source_id": "src-2026-11-11-001", "locator": "p.3", "quote": "30 days"}
  ],
  "confidence": "high",
  "review_status": "published"
}
```

### C.4 Evidence

**说明：** 证据是 source + locator + quote，不是 Wiki 链接。

```json
{
  "source_id": "src-2026-11-11-001",
  "locator": "page=3|offset=120",
  "quote": "Refunds are available within 30 days.",
  "sha256": "9f2c..."
}
```

---

## D. WikiPage

### D.1 一段说明

Wiki 是可读视图，不是事实源；每个关键断言必须有 citation。

**关键字段：** `status`、`sources`、`claims`、`revision`、`reviewer`。

**不是什么：** 不是 Fact Store；不是索引。

```json
{
  "page_id": "wiki-refund-policy",
  "tenant_id": "tenant-a",
  "collection_id": "support-kb",
  "title": "退款政策",
  "type": "concept",
  "status": "published",
  "sources": ["src-2026-11-11-001"],
  "claims": ["cl-001"],
  "body_md": "...",
  "revision": 3,
  "reviewer": "alice",
  "last_reviewed": "2026-11-11T10:00:00Z"
}
```

### D.2 页面状态

| 状态 | 含义 |
|---|---|
| draft | LLM 生成，未审 |
| reviewed | 人审通过 |
| published | 可默认检索 |
| stale | 过期 |
| deprecated | 被取代 |

### D.3 页面示例（Markdown）

```markdown
---
page_id: wiki-refund-policy
type: concept
status: published
sources: [src-2026-11-11-001]
claims: [cl-001]
reviewer: alice
last_reviewed: 2026-11-11
---

# 退款政策

## 摘要

退款需在购买后 30 天内申请。[src-2026-11-11-001 p.3]

## 例外

- 数字商品不支持退款。[src-2026-11-11-002 p.1]
```

---

## E. Index

### E.1 一段说明

索引是检索结构，不是事实源；必须可重建。

**关键字段：** `type`、`model`、`version`、`source_revision`、`rebuildable`。

```json
{
  "index_id": "idx-wiki-vector-v1",
  "type": "vector",
  "model": "embedding-model-x",
  "version": "1.0.0",
  "source_revision": "2026-11-11T10:00:00Z",
  "rebuildable": true
}
```

### E.2 类型

| 类型 | 用途 |
|---|---|
| fts | 关键词/编号 |
| vector | 语义召回 |
| graph | 关系/多跳 |

---

## F. Gateway 请求/响应

### F.1 请求

**说明：** 所有入口统一调这个接口。

**关键字段：** `tenant_id`、`collection_id`、`query`、`mode`、`require_citations`。

```json
{
  "tenant_id": "tenant-a",
  "collection_id": "support-kb",
  "query": "退款多久内可以申请？",
  "mode": "auto",
  "top_k": 8,
  "require_citations": true
}
```

### F.2 响应

**说明：** 返回答案、引用、路由、冲突、是否 abstain。

```json
{
  "answer": "购买后 30 天内可申请退款。",
  "citations": [
    {"claim_id": "cl-001", "source_id": "src-2026-11-11-001", "locator": "p.3"}
  ],
  "route": ["fact", "wiki"],
  "conflicts": [],
  "confidence": "high",
  "abstained": false,
  "degraded": false
}
```

### F.3 字段字典

| 字段 | 类型 | 说明 |
|---|---|---|
| answer | string | 回答；abstain 时为空/说明 |
| citations | array | 证据 |
| route | array | 实际使用的层 |
| conflicts | array | 冲突 |
| confidence | enum | high/medium/low |
| abstained | bool | 是否拒答 |
| degraded | bool | 是否降级 |

---

## G. 更新任务与影响分析

### G.1 更新任务

**说明：** Raw 变化后生成的任务，不是直接改事实。

```json
{
  "job_id": "job-2026-11-11-001",
  "tenant_id": "tenant-a",
  "source_id": "src-2026-11-11-001",
  "from_revision": 2,
  "to_revision": 3,
  "change_type": "content_changed",
  "status": "queued",
  "attempts": 0,
  "max_attempts": 3
}
```

### G.2 影响报告

```json
{
  "source_id": "src-2026-11-11-001",
  "affected_claims": ["cl-001"],
  "affected_pages": ["wiki-refund-policy"],
  "affected_indexes": ["idx-wiki-vector-v1"],
  "requires_review": true,
  "reason": "claim changed; citation stale"
}
```

---

## H. 错误与拒答

### H.1 错误码

| 码 | 含义 |
|---|---|
| `tenant_required` | 缺租户 |
| `collection_required` | 缺集合 |
| `acl_denied` | 无权限 |
| `source_unavailable` | 源不可达 |
| `evidence_missing` | 无证据 |
| `conflict_unresolved` | 冲突未裁决 |
| `index_stale` | 索引滞后 |
| `abstain` | 证据不足拒答 |

### H.2 拒答示例

```json
{
  "answer": "现有资料不足以回答该问题。",
  "citations": [],
  "abstained": true,
  "reason": "no_supporting_evidence"
}
```

---

## I. 校验规则

### I.1 Source

- `immutable=true`；
- `sha256` 与快照一致；
- `tenant_id/collection_id` 非空；
- tombstone 不得物理删除。

### I.2 Fact/Claim

- evidence 非空；
- evidence.source_id 存在；
- locator 可定位；
- confidence 在许可枚举；
- review_status 合法；
- 冲突未裁决不得 published。

### I.3 Wiki

- 每个关键断言有 citation；
- published 必须 reviewer；
- stale 不得默认检索；
- 不得写回 Fact Store。

### I.4 Index

- 可重建；
- model/version 记录；
- tenant 隔离；
- 与 source_revision 对齐。

---

## J. API 端点示例

> 以下是**逻辑 API**，不是当前实现绑定；实际路径由 Gateway/适配层决定。

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | /knowledge/sources | 登记 source |
| POST | /knowledge/ingest | 触发摄入 |
| POST | /knowledge/query | 查询 |
| GET | /knowledge/wiki/{page_id} | 读 Wiki |
| PUT | /knowledge/wiki/{page_id} | 更新 Wiki |
| POST | /knowledge/wiki/{page_id}/review | 审核 |
| POST | /knowledge/lint | 健康检查 |
| GET | /knowledge/coverage | 覆盖报告 |
| GET | /knowledge/graph/{entity_id} | 图投影 |
| GET | /knowledge/jobs/{job_id} | 更新任务 |

---

## K. 端到端示例

### K.1 输入

- Source：退款政策网页；
- Snapshot：HTML；
- Ontology：Policy/RefundRule；
- Claim：“30 天内退款”；
- Wiki：退款政策页。

### K.2 流程

1. 登记 source；
2. 生成 snapshot；
3. 解析；
4. 抽取 claim；
5. 绑定 evidence；
6. 人审；
7. 写入 Fact Store；
8. 编译 Wiki；
9. 建索引；
10. Gateway 查询返回 citation。

### K.3 更新

1. 网页变化；
2. 新 snapshot/revision；
3. 影响分析：claim cl-001、wiki-refund-policy；
4. 重抽取；
5. 冲突/人审；
6. 更新 Fact Store；
7. 重编译 Wiki；
8. 重建索引。

---

## L. 术语速查

| 术语 | 含义 |
|---|---|
| Source | 资料实体 |
| Snapshot | 不可变内容 |
| Revision | 新快照 |
| TBox | schema |
| ABox | 实例 |
| Fact | 可验证事实 |
| Claim | 可引用断言 |
| Evidence | 来源+定位 |
| Wiki | 可读视图 |
| Index | 检索结构 |
| Gateway | 统一查询入口 |
| KG | Fact Store 的图投影 |
| Graph DB | 图存储技术，不等于 KG |

---

## M. 使用边界

- 本附录不是规范；
- 字段可随 ADR 演进；
- 示例数据是虚构的；
- 不要复制示例中的密钥/租户/路径到生产；
- 真实实现须满足白皮书正文的 MUST/SHOULD。
