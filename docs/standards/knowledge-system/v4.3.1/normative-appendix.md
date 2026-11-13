---
doc_type: Standard
---

# aiPlat 知识体系规范性附录 v4.3.1

> **版本**：v4.3.1 · 2026-11-11
> **性质**：规范性附录（Normative Annex）
> **状态**：Approved Standard Annex（与正文同时批准）
> **配套**：《aiPlat 知识体系技术白皮书 v4.3.1（已批准）》
> **勘误**：2026-11-13 修正附录 P 的批准状态；不改变规范要求。
> **效力**：本附录与正文具有同等效力。字段名、必填规则、类型、错误码、版本兼容和符合性清单为 MUST/SHOULD；示例值仅作说明。
> **说明**：本附录不是“仅供参考”；实现必须满足本附录的规范性要求。

## 附录地图

| 小节 | 内容 | 对应正文 |
|---|---|---|
| 0 | 规范性约定 | 全文 |
| A | Source Registry | 3、5、11 |
| B | ObjectType / LinkType | 4、6.1、7 |
| C | Action / Function / Interface | 6.2–6.4、8 |
| D | Fact / Object / Evidence | 4、7 |
| E | ObjectSet / SDK | 9.2–9.3 |
| F | Gateway / Agent Tool Surface + VerificationResult | 9.1、9.4、9.6、10 |
| G | Execution / SQL 边界 | 6.7、8 |
| H | Security / Scenario / Package | 7.4、12 |
| I | 校验与错误 | 11、12 |
| J | 术语速查 | 全文 |
| K | Source Policy / Conflict | 7.6 |
| L | Fact Store Record | 7.5 |
| M | Query Contract | 9.6 |
| N | Conformance Checklist | 16 |
| O | Confidence Calibration Report | 9.6.7 |
| P | Approval Record | 标准声明 |
| Q | 使用边界 | — |

---

## 0. 规范性约定

### 0.1 用语

- **MUST**：强制；
- **MUST NOT**：禁止；
- **SHOULD**：建议；例外需记录；
- **MAY**：可选。

### 0.2 JSON 规则

- 字段名区分大小写；
- 必填字段缺失 = 不合规；
- 未定义字段不得写入；扩展字段必须使用 `x-` 前缀；
- 时间使用 RFC3339 UTC；
- ID 在租户内稳定；
- 金额/精确数值使用十进制字符串或明确单位；`confidence`/`coverage` 等比例值可用 0–1 number。

### 0.3 版本兼容

- Patch：编辑性修正；
- Minor：向后兼容新增；
- Major：破坏性变更；
- 删除/重命名字段必须走 Major，并提供迁移；
- 读取方必须忽略未知 `x-` 扩展字段。

### 0.4 验证

实现必须同时通过：

1. 语法/schema 校验；
2. 语义校验（引用存在、权限、状态转换）；
3. 负向测试（缺字段、越权、冲突、过期）。

### 0.5 机器可读 Schema

每个对象/动作/函数/接口必须提供 JSON Schema（Draft 2020-12 或更高），并与本附录字段一致：

- Schema 版本与本附录版本绑定；
- Schema 必须声明 `required`、类型、枚举、格式；
- 示例必须通过 Schema 校验；
- Schema 变更走版本兼容规则。

### 0.5.1 交付责任

本标准以**标准包**形式发布：

- 正文；
- 本规范性附录；
- `schemas/` 目录（JSON Schema + 校验器/用例 + conformance 参考策略，规范性工具）。

责任：

- **标准 owner** 负责发布与版本绑定的 schema；
- **实现方** 负责按 schema 校验并提交符合性证据；
- **未附 schema 的标准包不完整，不得宣称符合本标准**；
- 本版本 schema 入口：`schemas/knowledge-system.v4.3.1.schema.json`；清单：`schemas/manifest-v4.3.1.json`；
- 实现方扩展字段只允许 `x-` 前缀，且不得改变必填/语义。

### 0.6 本版验证记录

- Schema：`schemas/knowledge-system.v4.3.1.schema.json`；
- 结构验证器：`jsonschema` Draft202012Validator；
- 结构验证脚本：`schemas/validate_examples_v4.3.1.py`；
- 结构验证范围：A/B/C/D/E/F/H/I/K/L/M 的 22 个 JSON 示例；
- 结构验证结果：**22/22 通过，0 失败**（含 date/date-time format 与 sha256 64-hex pattern）；
- 批准记录：`approval-record-v4.3.1.pending.json` **1/1 通过**；`approval-record-v4.3.1.approved.json` **1/1 通过**；
- 语义验证脚本：`schemas/validate_semantics_v4.3.1.py`；
- 语义示例：**22/22 通过，0 失败**；
- 语义用例：**30/30 通过，0 失败**；
- 覆盖：单步/多步状态转换、冲突裁决、参考权限策略、外部对账 mock；
- 参考策略：`schemas/conformance/reference_policy.json`；
- conformance 说明：`schemas/conformance/README.md`；
- 日期：2026-11-11；
- 说明：参考策略/mock 只能证明标准规则；真实权限/真实外部系统由实现方 conformance 测试证明。

### 0.7 语义校验

JSON Schema 只能校验结构。本版提供标准级语义校验器：

- `schemas/validate_semantics_v4.3.1.py`；
- `schemas/semantic_cases.json`；
- 覆盖：22 个附录示例、Fact/Claim 状态转换、多步序列、高风险 Action 回滚、ActionExecution result/error、Query abstain/citations/partial、VerificationResult valid/skipped、冲突裁决、参考权限策略、外部对账 mock。

仍由实现方 conformance 测试覆盖：

- 真实 RBAC/ACL 与租户过滤；
- 引用是否真实存在；
- 真实冲突裁决与人工审批；
- 并发/多步状态下的实现行为；
- 真实外部系统对账/补偿；
- 真实 implementation 的 conformance 证据见 `schemas/conformance/README.md`。

**符合性认证要求：结构校验 + 记录级语义校验 + 实现方语义测试同时通过。**

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
  "sha256": "9f2c4e7a1b8d3f6c0a5e9d2b7c4f1a8e6d3b0c9f2a7e4d1b8c5f0a3e6d9b2c7f",
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

**必填字段：**

| 字段 | 类型 | 必填 |
|---|---|:---:|
| source_id | string | 是 |
| tenant_id | string | 是 |
| collection_id | string | 是 |
| kind | enum | 是 |
| uri / snapshot_uri | string | 是 |
| sha256 | string（64 位十六进制） | 是 |
| fetched_at | RFC3339 | 是 |
| revision | int | 是 |
| acl | array | 是 |
| connector | string | 是 |
| status | enum | 是 |
| immutable | bool=true | 是 |

---

## B. ObjectType / LinkType

**说明：** ObjectType 是语义 schema + 数据绑定；ObjectInstance 才是 Fact Store 的对象投影。

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

**必填字段：**

| 字段 | 类型 | 必填 |
|---|---|:---:|
| object_type_id | string | 是 |
| label | string | 是 |
| primary_key | string | 是 |
| source_binding | object | 是 |
| properties | array | 是 |
| links | array | 否 |
| index | object | 否 |
| sync | object | 是 |

---

## C. Action / Function / Interface

### C.1 ActionContract

**说明：** 动作是语义操作，不是任意 API/SQL。

```json
{
  "action_id": "ticket.close",
  "label": "关闭工单",
  "version": "1.0.0",
  "namespace": "customer_action",
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

**必填字段：**

| 字段 | 类型 | 必填 |
|---|---|:---:|
| action_id | string | 是 |
| label | string | 是 |
| version | string | 是 |
| namespace | enum（customer_action/platform_action/internal） | 是 |
| scope / target_class | string | 是 |
| input_schema / output_schema | object | 是 |
| preconditions / effects | array | 是 |
| required_permissions | array | 是 |
| require_approval / risk_level | bool/enum | 是 |
| handler | string | 是 |
| rollback_action_id | string | 高风险动作必填 |
| action_level | enum | 是 |
| audit | bool=true | 是 |

### C.2 ActionExecution

```json
{
  "execution_id": "exec-2026-11-11-001",
  "action_id": "ticket.close",
  "action_namespace": "customer_action",
  "tenant_id": "tenant-a",
  "actor": "user-42",
  "target": "ent-ticket-123",
  "input_hash": "sha256:...",
  "idempotency_key": "idem-2026-11-11-001",
  "status": "succeeded",
  "policy_decision": "allow",
  "approval_id": "apr-001",
  "before_snapshot": {"status": "open"},
  "after_snapshot": {"status": "closed"},
  "run_id": "run-2026-11-11-001",
  "evidence_ref": "ev-2026-11-11-001",
  "result": {"status": "closed"},
  "audit_hash": "sha256:...",
  "started_at": "2026-11-11T10:00:00Z",
  "completed_at": "2026-11-11T10:00:01Z"
}
```

关键：ActionExecution 是事实；追加不改历史。

**必填字段：**

| 字段 | 类型 | 必填 |
|---|---|:---:|
| execution_id | string | 是 |
| action_id / tenant_id / actor / target | string | 是 |
| action_namespace | enum（customer_action/platform_action/internal） | 是 |
| idempotency_key | string | 是 |
| approval_id | string | 需要审批时必填 |
| before_snapshot / after_snapshot | object | 客户动作必填 |
| run_id / evidence_ref | string | 客户动作必填 |
| input_hash | string | 是 |
| status / policy_decision | enum | 是 |
| result / error | object | 是（二选一） |
| audit_hash | string | 是 |
| started_at | RFC3339 | 是 |
| completed_at | RFC3339 | 成功/失败时必填 |

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

**必填字段：**

| 字段 | 类型 | 必填 |
|---|---|:---:|
| function_id / version | string/semver | 是 |
| input_schema / output_schema | object | 是 |
| deterministic / side_effects | bool | 是 |
| required_permissions | array | 是 |
| timeout_ms | int | 是 |
| handler | string | 是 |

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

**必填字段：**

| 字段 | 类型 | 必填 |
|---|---|:---:|
| interface_id | string | 是 |
| properties / links | array | 是 |
| actions | array | 否 |
| implementers | array | 是 |

---

## D. Fact / Object / Evidence

### D.1 Fact（完整合规样例）

```json
{
  "fact_id": "fact-001",
  "tenant_id": "tenant-a",
  "collection_id": "support-kb",
  "subject": "ent-ticket-123",
  "predicate": "status",
  "object": "open",
  "evidence": [
    {"source_id": "src-2026-11-11-001", "locator": "p.1", "quote": "status: open", "fetched_at": "2026-11-11T08:00:00Z"}
  ],
  "source_policy": "primary_2026",
  "extractor_version": "extractor-1.4.0",
  "review_status": "published",
  "confidence": 0.92,
  "valid_from": "2026-11-11T08:00:00Z",
  "recorded_at": "2026-11-11T08:01:00Z",
  "valid_to": null,
  "revision": 3,
  "status": "active",
  "inferred": false
}
```

### D.2 Claim（完整合规样例）

```json
{
  "claim_id": "cl-001",
  "tenant_id": "tenant-a",
  "collection_id": "support-kb",
  "text": "退款需在购买后 30 天内申请",
  "evidence": [
    {"source_id": "src-2026-11-11-001", "locator": "p.3", "quote": "30 days", "fetched_at": "2026-11-11T08:00:00Z"}
  ],
  "source_policy": "primary_2026",
  "extractor_version": "extractor-1.4.0",
  "review_status": "published",
  "confidence": 0.92,
  "valid_from": "2026-11-11T08:00:00Z",
  "recorded_at": "2026-11-11T08:01:00Z",
  "valid_to": null,
  "revision": 2,
  "status": "accepted"
}
```

### D.3 必填字段

| 字段 | Fact | Claim |
|---|:---:|:---:|
| fact_id / claim_id | 是 | 是 |
| tenant_id / collection_id | 是 | 是 |
| subject / predicate / object | 是 | 否 |
| text | 否 | 是 |
| evidence[] | 是 | 是 |
| source_policy | 是 | 是 |
| extractor_version | 是 | 是 |
| review_status | 是 | 是 |
| confidence | 是 | 是 |
| valid_from / valid_to | 是 | 是 |
| recorded_at | 是 | 是 |
| revision | 是 | 是 |
| status | 是 | 是 |
| inferred | 是 | 否 |

**规则：** 无 evidence 不得 published；旧事实 supersede/retire，不覆盖历史；推断关系标 `inferred=true`。

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
  "route_plan": ["fact", "wiki"],
  "route_reason": "fact hit; wiki used for explanation",
  "confidence": "high",
  "confidence_factors": {
    "evidence_coverage": 1.0,
    "source_authority": "high",
    "conflict": false,
    "coverage": 0.9,
    "freshness": "valid"
  },
  "partial": false,
  "degraded": false,
  "abstained": false,
  "conflicts": []
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

### F.3 VerificationResult

```json
{
  "status": "degraded",
  "valid": false,
  "checks_run": ["citation_exists", "tenant_filter"],
  "skipped_checks": ["freshness"],
  "reason": "freshness check skipped"
}
```

规则：

- `valid=true` 只能在 `status=ok`、`checks_run` 非空且 `skipped_checks` 为空时返回；
- 未执行检查 → `status=unchecked`，`valid=false`；
- 部分失败/跳过 → `status=error/degraded`，列出 `skipped_checks[]`；
- `verification` 可作为 QueryResponse 的可选字段返回。

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

规则：对象/属性/链接/动作/函数/接口全覆盖；实例级通过 `condition` 选择实例，字段级通过 `masked_properties` 脱敏；聚合不泄漏；导出同权限；前端过滤不算安全。

### H.2 Scenario

```json
{
  "scenario_id": "scn-2026-11-11-001",
  "base_snapshot_at": "2026-11-11T10:00:00Z",
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
  "dependencies": [{"package": "core-ontology", "version": ">=1.0"}],
  "compatibility": {"backward": ["1.1.0"], "forward": ["1.3.0"]},
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
| `entity_missing` | 实体不存在或不在 Fact Store |
| `abstain` | 证据不足拒答 |

租户不匹配统一返回 `acl_denied`；需要审批统一返回 `action_rejected`；不得通过错误码暴露租户是否存在。

### I.1 错误响应

```json
{
  "error": {
    "code": "evidence_missing",
    "message": "关键断言缺少证据",
    "request_id": "req-2026-11-11-001",
    "details": {"claim_id": "cl-001"},
    "retryable": false
  }
}
```

### I.2 HTTP 映射

| 情况 | HTTP |
|---|---|
| schema 不合法 | 400 |
| 未认证 | 401 |
| 无权限 | 403 |
| 冲突未裁决 | 409 |
| 语义校验失败 | 422 |
| 依赖未满足 | 424 |
| 暂时不可用/降级 | 503 |

**规则：** 错误响应不得包含跨租户信息；`request_id` 必须可审计；`retryable` 必须准确。

---

## J. 术语速查

| 术语 | 含义 |
|---|---|
| Source | 资料实体 |
| Snapshot | 不可变内容 |
| Revision | 新快照 |
| Ontology | 语义模型（TBox + ABox）；行为契约绑定到本体，但不属于 TBox |
| TBox | 类型、属性、关系、公理、约束 |
| ABox | 实例、事实、关系实例 |
| Fact Store | 规范事实层；GraphIndex 是其图投影 |
| ObjectType | 语义 schema + 数据绑定 |
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
| Package | 语义模型发布包 |
| PolicyGate | 权限/审批/审计的唯一策略执行点 |
| ApprovalGate | 高风险动作的人工审批门 |
| Tenant | 租户隔离边界 |
| Conflict | 来源/事实/断言的冲突记录 |
| Calibration | 置信度校准报告 |

---

## K. Source Policy / Conflict

```json
{
  "source_id": "src-2026-11-11-001",
  "authority": "primary",
  "freshness": {"valid_days": 365},
  "scope": ["refund_policy"],
  "license": "company-internal",
  "trust": "high",
  "conflict_rule": "prefer_newer_primary_then_human_review"
}
```

```json
{
  "claim_id": "cl-001",
  "status": "accepted",
  "source_policy": "primary_2026",
  "conflict_ids": [],
  "decision": {"by": "reviewer-1", "reason": "latest official policy"}
}
```

**规则：** Raw 是证据，不是自动真理；冲突由来源策略 + 人审裁决；不允许固定 `Raw > KG > Wiki`。

---

## L. Fact Store Record

> 这是**完整合规样例**，不是字段节选。

```json
{
  "fact_id": "fact-001",
  "tenant_id": "tenant-a",
  "collection_id": "support-kb",
  "subject": "ent-ticket-123",
  "predicate": "status",
  "object": "open",
  "evidence": [
    {"source_id": "src-2026-11-11-001", "locator": "p.1", "quote": "status: open", "fetched_at": "2026-11-11T08:00:00Z"}
  ],
  "source_policy": "primary_2026",
  "extractor_version": "extractor-1.4.0",
  "review_status": "published",
  "confidence": 0.92,
  "valid_from": "2026-11-11T08:00:00Z",
  "recorded_at": "2026-11-11T08:01:00Z",
  "valid_to": null,
  "revision": 3,
  "status": "active",
  "inferred": false
}
```

**规则：** 无 evidence 不得 published；旧事实 superseded/retired；推断关系标 `inferred=true`；查询层/Wiki/SDK 不得直接写 Fact Store。

---

## M. Query Contract

```json
{
  "tenant_id": "tenant-a",
  "collection_id": "support-kb",
  "query": "退款多久内可以申请？",
  "time_range": {"from": "2026-01-01T00:00:00Z", "to": "2026-11-11T23:59:59Z"},
  "query_type": "fact",
  "mode": "auto",
  "filters": {"status": "active"},
  "top_k": 8,
  "budget_ms": 3000,
  "require_citations": true
}
```

```json
{
  "answer": "购买后 30 天内可申请退款。",
  "citations": [
    {"claim_id": "cl-001", "source_id": "src-2026-11-11-001", "locator": "p.3"}
  ],
  "route_plan": ["fact", "wiki"],
  "route_reason": "fact hit; wiki used for explanation",
  "confidence": "high",
  "confidence_factors": {
    "evidence_coverage": 1.0,
    "source_authority": "high",
    "conflict": false,
    "coverage": 0.9,
    "freshness": "valid"
  },
  "partial": false,
  "degraded": false,
  "abstained": false,
  "conflicts": []
}
```

**规则：** 权限召回前过滤；引用可定位；无证据 abstain；`confidence` 由多因子组成，不是字符串魔法。

---

## N. Conformance Checklist

- [ ] Raw 不可变；
- [ ] 语义模型版本化；
- [ ] Fact/Claim 有 evidence；
- [ ] 来源策略与冲突裁决；
- [ ] Wiki/索引有条件重建；
- [ ] Gateway 查询契约；
- [ ] 权限召回前过滤；
- [ ] 动作执行走 Policy/Approval/Audit；
- [ ] 跨租户 0 泄漏；
- [ ] 评测有定义/数据集/门槛；
- [ ] 迁移/回滚方案；
- [ ] Fact 状态机；
- [ ] confidence 校准规则；
- [ ] 跨存储失败恢复/对账；
- [ ] JSON Schema 与附录一致；
- [ ] 附录示例通过 Schema 校验；
- [ ] 记录级语义校验通过；
- [ ] 实现方语义测试通过；
- [ ] 运行时权威与审计快照；
- [ ] L1/L2/L3 约束分层；
- [ ] 防假绿；
- [ ] 实例/字段级 ACL；
- [ ] OCS 完整度；
- [ ] 版本/变更/审计。

---

## O. Confidence Calibration Report

校准报告必须至少包含：

| 字段 | 类型 | 必填 |
|---|---|:---:|
| calibration_id | string | 是 |
| domain / query_type | string | 是 |
| dataset_version | string | 是 |
| sample_size | int | 是 |
| label_protocol / inter_annotator_agreement | string/number | 是 |
| weights | object | 是 |
| calibration_version | string | 是 |
| ece / brier | number | 是 |
| high_precision / coverage | number | 是 |
| approved_by / valid_until | string/date | 是 |

**最低门槛：**

- 每个域/query_type 至少 100 条 gold；不足需统计论证；
- 至少 20% 双人标注；
- ECE ≤ 0.05；
- high 精度 ≥ 0.90；
- 样本不足/ECE 超标/分布漂移 → confidence 最高只能 `medium`；
- 报告必须可复现，并绑定模型/索引/来源策略版本。

---

## P. Approval Record

批准记录必须由批准人填写；没有记录 = 未批准。

- 默认要求非作者批准；
- 作者担任 Architecture Review 或 Product 时，必须披露作者身份、记录 `conflict_waiver`，且 Security/Data Governance 必须由非作者担任；
- 至少一名非作者批准人；
- 作者不得单独批准。

| 字段 | 类型 | 必填 |
|---|---|:---:|
| standard_version | string | 是 |
| scope | string | 是 |
| status | enum（pending/approved/rejected） | 是 |
| approvers | array | approved/rejected 时必填 |
| approval_date | date | approved/rejected 时必填 |
| effective_date | date | approved 时必填 |
| exceptions | array | 是 |
| conflict_waiver | object | 作者担任批准人时必填 |
| decision | enum（approved/rejected/conditional） | approved/rejected 时必填；conditional 仅与 approved 且非空 exceptions 一起使用 |
| record_id | string | 是 |

**状态：Approved。** 本版已批准；批准记录见 `schemas/conformance/approval-record-v4.3.1.approved.json`（approval_date 2026-11-11；effective_date 2027-01-01）。

---

## Q. 使用边界

- 本附录是**规范性附录**，与正文同等效力；
- 字段、必填、错误码、版本兼容和符合性清单为 MUST/SHOULD；
- 示例值可虚构；不得复制示例中的密钥/租户/路径到生产；
- 真实实现须**同时**满足正文和本附录；
- 例外走 ADR，记录范围、期限、补偿。
