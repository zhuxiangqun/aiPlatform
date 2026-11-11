---
doc_type: Archive
---

# aiPlat 知识体系工程附录 v4.1

> **版本**：v4.1 · 2026-11-11  
> **性质**：工程示例 / 字段字典 / API 参考  
> **状态**：非规范性（Non-normative）  
> **配套**：《aiPlat 知识体系技术白皮书 v4.1》  
> **说明**：以下 JSON/API 仅为示例，不是实现规范；规范以白皮书正文的 MUST/SHOULD 为准。

## 附录地图

| 小节 | 内容 | 对应正文 |
|---|---|---|
| A | Source Registry | 3、5、11 |
| B | ObjectType / LinkType | 4、6.1、7 |
| C | Action / Function / Interface | 6.2–6.4、8 |
| D | Fact / Object / Evidence | 4、7 |
| E | ObjectSet / SDK | 9.2–9.3 |
| F | Gateway / Agent Tool Surface | 9.1、9.4、10 |
| G | Execution / SQL 边界 | 6.7、8 |
| H | Security / Scenario / Package | 7.4、12 |
| I | 校验与错误 | 11、12 |
| J | 术语速查 | 全文 |
| K | 使用边界 | — |

---

## A. Source Registry

**说明：** 记录资料从哪来、哪一刻的快照、内容 hash、谁能访问。

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

关键字段：`source_id`、`snapshot_uri`、`sha256`、`revision`、`status`。  
不是什么：不是原始文件本身；不是活 URL；不是 Wiki。

---

## B. ObjectType / LinkType

**说明：** ObjectType 是 Fact Store 的对象视图，不是第二套事实。

```json
{
  "object_type_id": "Ticket",
  "label": "工单",
  "primary_key": "ticket_id",
  "source_binding": {
    "kind": "dataset",
    "dataset_id": "ds_ticket_current",
    "watermark": "updated_at"
  },
  "properties": [
    {"id": "status", "type": "enum", "indexed": true},
    {"id": "priority", "type": "enum", "indexed": true}
  ],
  "links": [
    {"link_type": "assigned_to", "target": "Person", "cardinality": "many-to-one"}
  ],
  "index": {"search": ["status", "priority"], "aggregate": ["status"]},
  "sync": {"mode": "incremental", "schedule": "5m", "health": "required"}
}
```

```json
{
  "link_type": "assigned_to",
  "from": "Ticket",
  "to": "Person",
  "cardinality": "many-to-one"
}
```

关键字段：`object_type_id`、`primary_key`、`source_binding`、`properties`、`links`。  
不是什么：不是数据集本身；不是第二套事实库。

---

## C. Action / Function / Interface

### C.1 ActionContract

**说明：** 动作是语义操作，不是任意 API/SQL。

```json
{
  "action_id": "ticket.close",
  "label": "关闭工单",
  "scope": "domain",
  "domain_id": "customer-support",
  "target_class": "Ticket",
  "required_state": "open",
  "input_schema": {"ticket_id": "string", "reason": "string"},
  "output_schema": {"ticket_id": "string", "status": "string"},
  "preconditions": [{"type": "state", "value": "open"}],
  "effects": ["Ticket.status = closed"],
  "required_permissions": ["ticket.close"],
  "require_approval": true,
  "risk_level": "high",
  "handler": "custom_handlers.ticket:close",
  "rollback_action_id": "ticket.reopen",
  "action_level": "lv2_confirmed",
  "audit": true
}
```

关键字段：`action_id`、`target_class`、`preconditions`、`effects`、`required_permissions`、`handler`、`rollback_action_id`。  
不是什么：不是 API endpoint 别名；不是 Wiki；不是绕过 PolicyGate 的脚本。

### C.2 ActionExecution

```json
{
  "execution_id": "exec-2026-11-11-001",
  "action_id": "ticket.close",
  "tenant_id": "tenant-a",
  "actor": "user-42",
  "target": "ent-ticket-123",
  "input_hash": "sha256:...",
  "status": "succeeded",
  "policy_decision": "allow",
  "approval_id": "apr-001",
  "result": {"status": "closed"},
  "audit_hash": "sha256:...",
  "started_at": "2026-11-11T10:00:00Z",
  "completed_at": "2026-11-11T10:00:01Z"
}
```

关键：ActionExecution 是事实；追加不改历史。

### C.3 FunctionContract

```json
{
  "function_id": "ticket.priority_score",
  "version": "1.0.0",
  "input_schema": {"ticket_id": "string"},
  "output_schema": {"score": "number", "reason": "string"},
  "deterministic": true,
  "side_effects": false,
  "required_permissions": ["ticket.read"],
  "timeout_ms": 2000,
  "handler": "functions.ticket:priority_score"
}
```

不是什么：不是 Action；不是任意代码；不是 SQL 控制台。

### C.4 Interface

```json
{
  "interface_id": "Assignable",
  "properties": [{"id": "assignee_id", "type": "string"}],
  "links": [{"link_type": "assigned_to", "target": "Person"}],
  "actions": ["ticket.assign"],
  "implementers": ["Ticket", "WorkOrder", "Incident"]
}
```

不是什么：不是父类替代；不是 Wiki 模板。

---

## D. Fact / Object / Evidence

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

关键：每个 fact/claim 必须有 evidence；旧事实标 superseded/retired，不覆盖历史。

---

## E. ObjectSet / SDK

### E.1 ObjectSet 请求

```json
{
  "object_type": "Ticket",
  "filter": {"status": "open", "priority": "high"},
  "sort": [{"field": "created_at", "direction": "desc"}],
  "limit": 50,
  "aggregate": [{"type": "count", "group_by": ["status"]}]
}
```

### E.2 ObjectSet 响应

```json
{
  "object_type": "Ticket",
  "total": 12,
  "items": [{"ticket_id": "T-1", "status": "open"}],
  "aggregates": [{"status": "open", "count": 12}],
  "next_cursor": null
}
```

### E.3 SDK

```text
ObjectType Ticket -> TicketClient
  .get(id)
  .query(filter).fetch()
  .link("assigned_to").fetch()

ActionType ticket.close -> ticket.close({ticket_id, reason})
Function ticket.priority_score -> ticket.priorityScore({ticket_id})
```

不是什么：不是内部 API 的简单包装；不能绕过权限/审批。

---

## F. Gateway / Agent Tool Surface

### F.1 查询响应

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

### F.2 Agent 工具

| 工具 | 用途 |
|---|---|
| object.query | 查对象 |
| link.traverse | 多跳关系 |
| function.call | 计算/校验 |
| action.execute | 执行动作 |
| object_set.aggregate | 聚合 |

规则：入参 schema；权限/租户/审批；结果 citation；不允许通用 SQL 工具。

---

## G. Execution / SQL 边界

执行顺序：

1. 校验 ActionContract；
2. PolicyGate；
3. ApprovalGate；
4. EntityLock；
5. Handler/Function；
6. ActionStore/审计；
7. 更新 Fact Store/对象状态；
8. 事件；
9. 投影。

| 场景 | 建议 |
|---|---|
| 生成 SQL 文本 | 不是 Action |
| 只读 SELECT | Lv1 工具；只读账号、参数化、tenant 过滤、limit/timeout |
| DML | Action；审批、dry-run、行数上限、回滚、审计 |
| DDL | 高风险变更单；备份、审批、回滚 |

---

## H. Security / Scenario / Package

### H.1 对象级策略

```json
{
  "resource": "Ticket",
  "effect": "allow",
  "principals": ["role:support_agent"],
  "condition": {"tenant_id": "tenant-a", "status": "open"},
  "masked_properties": ["customer_phone"],
  "actions": ["ticket.close"]
}
```

规则：对象/属性/链接/动作/函数/接口全覆盖；聚合不泄漏；导出同权限；前端过滤不算安全。

### H.2 Scenario

```json
{
  "scenario_id": "scn-2026-11-11-001",
  "base_revision": "2026-11-11T10:00:00Z",
  "branch": "what-if-close-100-tickets",
  "dry_run": true,
  "changes": [{"action": "ticket.close", "target": "T-1"}],
  "status": "simulated"
}
```

规则：模拟不写主事实；合并必须人审。

### H.3 Ontology Package

```json
{
  "package_id": "customer-support-ontology",
  "version": "1.2.0",
  "schema": ["Ticket", "Person", "assigned_to"],
  "actions": ["ticket.close"],
  "functions": ["ticket.priority_score"],
  "interfaces": ["Assignable"],
  "migrations": ["001_add_priority.sql"]
}
```

规则：包版本化；依赖锁定；兼容矩阵；发布/回滚。

---

## I. 校验与错误

校验：

- Source：immutable、hash、tenant/collection；
- ObjectType：主键唯一、source_binding 存在；
- Fact/Claim：evidence 非空、source 存在、locator 可定位；
- Wiki：关键断言有 citation；published 必须 reviewer；
- Index：可重建、model/version、租户隔离。

错误码：

| 码 | 含义 |
|---|---|
| `acl_denied` | 无权限 |
| `evidence_missing` | 无证据 |
| `conflict_unresolved` | 冲突未裁决 |
| `object_sync_stale` | 对象不同步 |
| `action_rejected` | 动作被策略拒绝 |
| `abstain` | 证据不足拒答 |

---

## J. 术语速查

| 术语 | 含义 |
|---|---|
| Source | 资料实体 |
| Snapshot | 不可变内容 |
| Revision | 新快照 |
| ObjectType | Fact Store 的对象视图 |
| LinkType | 对象关系 |
| ActionType | 语义动作契约 |
| ActionExecution | 一次执行事实 |
| Function | 计算单元 |
| Interface | 多态契约 |
| ObjectSet | 对象集合查询 |
| SDK | 生成的 typed client |
| Fact | 可验证事实 |
| Claim | 可引用断言 |
| Evidence | 来源+定位 |
| Wiki | 可读视图 |
| Index | 检索结构 |
| Gateway | 查询内核 |
| Scenario | 隔离假设分支 |
| Package | 本体发布包 |

---

## K. 使用边界

- 本附录不是规范；
- 字段可随 ADR 演进；
- 示例数据是虚构的；
- 不要复制示例中的密钥/租户/路径到生产；
- 真实实现须满足白皮书正文的 MUST/SHOULD。
