# 故障诊断 + 治理可交付演示剧本

| 字段 | 值 |
|------|-----|
| 文档 ID | `ONTOLOGY-DEMO-PLAYBOOK-2026-09` |
| 版本 | v1.2 |
| 关联 | [`ONTOLOGY_OUTCOME_GOALS.md`](./ONTOLOGY_OUTCOME_GOALS.md) · [`ONTOLOGY_PPT_SCENARIOS.md`](./ONTOLOGY_PPT_SCENARIOS.md) B3/B4 · [`ONTOLOGY_EXECUTABLE_MODEL.md`](./ONTOLOGY_EXECUTABLE_MODEL.md) · [`ONTOLOGY_CONNECTOR_TEMPLATES.md`](./ONTOLOGY_CONNECTOR_TEMPLATES.md) |
| 时长 | 故障约 15 分钟；治理约 10 分钟；权限+webhook 约 5 分钟 |

### 对外三句话（开场必说）

1. **底座**：域说明书（YAML）定义类/关系/状态/动作。  
2. **执行**：动作硬门可否决、可审计（非 OWL 推理机权威）。  
3. **权威**：真实层在 GraphIndex；说明书变更走**本体提案**（≠ 配置 Evolve）。

---

## §故障（P1）— AcceptTab

| 分钟 | 操作 | 口述 |
|:----:|------|------|
| 0–2 | 念三句话；勾选 T6 | 告警进图→调用链→硬门落根因 |
| 2–4 | **创建教学复杂拓扑** | 路径 C：模板写入 |
| 4–7 | 对照 B3.2 镜 | 主告警、calls、旁路 Redis 从 |
| 7–11 | 分诊 → 挂疑似 → 确认根因 | 写回 GraphIndex |
| 11–12 | 对 `open` 直接确认根因 | 应 **blocked** |
| 12–14 | 可选：**导入样例告警JSON** 或 **webhook** | 路径 B 生产入口 |
| 14–15 | 对比 minimal 种子 | complex ⊃ minimal |

```http
POST /api/platform/apps/fde/graph/import
{ "domain_id": "it-ops", "use_sample": true }

POST /api/platform/apps/fde/graph/webhook/monitor-alerts
Content-Type: application/json
（body = 样例 JSON；可选 Header X-AIPLAT-WEBHOOK-SECRET）
```

---

## §第二域同构（Phase 2）— retail-ops

| 分钟 | 操作 | 口述 |
|:----:|------|------|
| 0–2 | 种图：`seed_retail_ops_demo_graph` / 装 `retail-ops.yaml` | **零改 harness** 复制 it-ops |
| 2–5 | `triage_alert` → `mark_root_cause` | 同构硬门 |
| 5–6 | 对 `open` 直接确认根因 | 应 **blocked** |
| 6–8 | webhook `pos-monitor-alerts` | 路径 B 第二 source |

---

## §权限 30 秒（T9）

| 操作 | 口述 |
|------|------|
| `GET .../graph/entities?domain=data-gov&actor_role=viewer` 或 Header `X-AIPLAT-ACTOR-ROLE: guest` | guest→viewer；看不见幽灵表 |
| `POST .../actions/execute` + `role=viewer` 丢弃幽灵 | `constraint_type=abox_acl` |
| `GET .../graph/acl/data-gov` | CRUD 矩阵 + 当前 ACL |
---

## §治理（P3）— 知识工厂

入口：侧边栏 **知识工厂**（域默认 `lock-service`）

| 分钟 | 操作 | 口述 |
|:----:|------|------|
| 0–2 | 粘贴一段含新业务对象的文本 → 抽取 | 路径 A 草稿；非静默改 YAML |
| 2–4 | 待审列表点 **确认** | 写 GraphIndex（路径 B）+ **入队本体提案** |
| 4–7 | ③ 本体提案：草稿点 **批准** | tier 门（edge 可 analyst） |
| 7–9 | 已批准点 **应用** | toast：`vN→vN+1` + 新增类；live `{domain}.yaml` 可查 |
| 9–10 | 打开 `~/.aiplat/ontologies/lock-service.yaml` | 新类 label 可见；≠ Evolve |

```http
POST /api/platform/apps/fde/extractions/{id}/confirm
POST /api/platform/apps/fde/ontology/proposals/{id}/approve
{ "approver_role": "analyst" }
POST /api/platform/apps/fde/ontology/proposals/{id}/apply
```

## §治理洪水（P4）— AcceptTab data-gov

| 分钟 | 操作 | 口述 |
|:----:|------|------|
| 0–2 | **创建治理教学图** | B4.3 子集：主线资产 + 幽灵表 + 错挂目录 |
| 2–4 | 看 ACL / 字段提示 | viewer 看不到幽灵表；`owner_contact` 对 viewer 脱敏 |
| 4–5 | 点 **viewer试丢弃（应拦截）** | 紫色 ACL 拦截（写路径） |
| 5–8 | 对幽灵表 **丢弃幽灵表**（analyst） | 洪水筛选；state→discarded |
| 8–10 | 对 DA-积分流水点 **挂载目录→执行**（catalog_id 已默认 `CAT-积分流水`） | 闸2 一键：meta_ready→cataloged + mounts |

```http
POST /api/platform/apps/fde/graph/entities
{ "scenario": "data-gov-assets" }
GET /api/platform/apps/fde/graph/entities?domain=data-gov&class=物理表&actor_role=viewer
```

### 禁止口述

- 「OWL / HermiT 已在运行时推理」或「建模已内置 OWL 完备推理」  
- 「星邺 8000 人天已在本系统复现」  
- 「企业全域属性 RBAC 已产品化」（仅 GraphIndex ABox ACL 竖切）  
- 「确认即静默改域 YAML」（须批准→应用）  
- 「推理建议 = 已确认业务事实」（须 Action / 提案）

---

## §表映射入轨（Path B）— 非监控

| 分钟 | 操作 | 口述 |
|:----:|------|------|
| 0–2 | `POST .../graph/import` + `source_type=table_map` + CSV/行数组 | 适配层：表→真实层 |
| 2–4 | 看回执 `created_entities` / `skipped` | 类/边须 ∈ connector allowlist |
| 4–6 | 对主实体跑一动作（若域有 Action） | 入轨后仍过硬门 |

```http
POST /api/platform/apps/fde/graph/import
{
  "domain_id": "it-ops",
  "source_type": "table_map",
  "use_sample": true
}
```

---

## §三柱速览

```http
GET /api/platform/apps/fde/ontology/pillars/{domain_id}
```

口述：数据=图实体计数；逻辑=axioms/inference_rules；行动=customer_action 列表；建议≠权威。
