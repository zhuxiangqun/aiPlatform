# ABox Connector 模板（路径 B 生产入轨）

| 字段 | 值 |
|------|-----|
| 文档 ID | `ONTOLOGY-CONNECTOR-TEMPLATES-2026-09` |
| 版本 | v1.1 |
| 关联 | [`ONTOLOGY_EXECUTABLE_MODEL.md`](./ONTOLOGY_EXECUTABLE_MODEL.md) · [`ONTOLOGY_DEMO_PLAYBOOK.md`](./ONTOLOGY_DEMO_PLAYBOOK.md) |
| 原则 | 域可配置 allowlist；**禁止**在 harness 硬编码 `domain_id` |

---

## 契约

```text
source_id → connector.json → import_abox_payload(GraphIndex) → receipt
```

| 字段 | 说明 |
|------|------|
| `source_id` | Webhook 路径段：`POST /api/platform/apps/fde/graph/webhook/{source_id}` |
| `domain_id` | 目标域 |
| `allowed_classes` / `allowed_relations` | 白名单；空类列表 → 拒绝导入 |
| `primary_class` | 回执 `primary_id` 优先匹配的类 |
| `auth` | `shared_secret_env` → `AIPLAT_ABOX_WEBHOOK_SECRET`（未设置则开发放行） |

回执统一：`created_entities` / `relations` / `skipped` / `primary_id`（兼 `primary_alert_id`）。

配置落点：`~/.aiplat/ontologies/{domain}/connector.json`（种子：`aiPlat-core/workspace_seeds/connectors/`）。

---

## 模板 1 — 监控 Webhook（已实现）

| 项 | 值 |
|----|-----|
| 种子 | `connectors/it-ops.json` · `retail-ops.json` |
| 入口 | `POST .../graph/webhook/monitor-alerts` |
| Header | `X-AIPLAT-WEBHOOK-SECRET`（可选） |
| Body | 与 `fixtures/it_ops_alert_import_sample.json` 同构 |

```bash
curl -sS -X POST "$BASE/api/platform/apps/fde/graph/webhook/monitor-alerts" \
  -H 'Content-Type: application/json' \
  -d @aiPlat-core/core/apps/fde/service/fixtures/it_ops_alert_import_sample.json
```

---

## 模板 2 — 工单 / 业务表 CSV→JSON（**已实现**）

| 项 | 值 |
|----|-----|
| 入口 | `POST .../graph/import` + `source_type=table_map` |
| 映射 | `connector.json` → `table_map`：列→实体字段；`relation_rows` 可选 |
| 样例 | `use_sample=true`（it-ops）或 body.`rows` / `csv_text` |

```http
POST /api/platform/apps/fde/graph/import
{
  "domain_id": "it-ops",
  "source_type": "table_map",
  "rows": [
    {"id": "SVC-T1", "name": "api", "class": "服务"},
    {"id": "ALT-T1", "name": "timeout", "class": "告警", "state": "open"}
  ],
  "relation_rows": [
    {"from": "ALT-T1", "to": "SVC-T1", "rel": "suspects"}
  ]
}
```

1. ETL 将表行映射为 entities（`class` ∈ 域 allowlist）。  
2. 关系列映射为 relations。  
3. **不**在 core/harness 写表名/列名硬编码。

---

## 模板 3 — 文档目录 / 代码建议（Path A 草稿）

路径 A：知识工厂抽取→confirm→提案。  
代码路径建议：`POST .../ontology/code-suggestions` 仅产提案草稿，**禁止**自动 apply。  
本模板不替代提案门。

---

## 权限矩阵（T9）

见 `GET /api/platform/apps/fde/graph/acl/{domain_id}` → `crud_matrix`。  
角色桥：`X-AIPLAT-ACTOR-ROLE` / `X-AIPLAT-SCOPES` → `viewer|analyst|admin`。

管理：

```http
PUT /api/platform/apps/fde/graph/acl/{domain}/entities/{id}
PUT /api/platform/apps/fde/graph/acl/{domain}/fields/{id}/{field}
```

---

## 非目标

- 运行时 OWL 校验阻断 L1  
- 宣称「监控已全量自动建成全域本体」  
- 全域 CBAC 产品（仅域级 ABox ACL）
