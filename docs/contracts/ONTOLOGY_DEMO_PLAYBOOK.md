# 故障诊断 + 治理可交付演示剧本

| 字段 | 值 |
|------|-----|
| 文档 ID | `ONTOLOGY-DEMO-PLAYBOOK-2026-09` |
| 版本 | v1.3 |
| 关联 | [`ONTOLOGY_OUTCOME_GOALS.md`](./ONTOLOGY_OUTCOME_GOALS.md) · [`ONTOLOGY_PPT_SCENARIOS.md`](./ONTOLOGY_PPT_SCENARIOS.md) B3/B4（含口述 B3.6/B4.6） · [`ONTOLOGY_EXECUTABLE_MODEL.md`](./ONTOLOGY_EXECUTABLE_MODEL.md) · [`ONTOLOGY_CONNECTOR_TEMPLATES.md`](./ONTOLOGY_CONNECTOR_TEMPLATES.md) |
| 时长 | 故障约 15 分钟；治理约 10 分钟；权限+webhook+表映射约 8 分钟 |

### 对外三句话（开场必说）

1. **底座**：域说明书（YAML）定义类/关系/状态/动作。  
2. **执行**：动作硬门可否决、可审计（非 OWL 推理机权威）。  
3. **权威**：真实层在 GraphIndex；说明书变更走**本体提案**（≠ 配置 Evolve）。

---

## §故障（P1）— AcceptTab

| 分钟 | 操作 | 口述 |
|:----:|------|------|
| 0–2 | 念三句话；勾选 T6；可选先念 PPT **B3.6 30s** | 告警进图→调用链→硬门落根因 |
| 2–4 | **创建教学复杂拓扑** | 路径 C：模板写入；对照 B3.2 图说 |
| 4–7 | 对照 B3 镜1–4（含镜4 判定表） | 主告警、calls、旁路 Redis 从 |
| 7–11 | 分诊 → 挂疑似 → 确认根因 | 写回 GraphIndex（B3.6 90s 可并行） |
| 11–12 | 对 `open` 直接确认根因 | 应 **blocked** |
| 12–14 | **导入样例告警JSON** 或 **导入表/CSV样例** 或 webhook | 路径 B（非路径 C） |
| 14–15 | 可选：加载 **本体三柱速览** | 数据/逻辑软/行动硬 |

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

---

## §在线学习 / 受控进化（P0–P2.5）— AcceptTab

| 步 | 操作 | 期望 |
|----|------|------|
| 0 | **刷新学习状态** | 见 UCB / EDGE_AUTO / serves 计数 |
| 1 | **写入演示案例**（域 `it-ops`） | 返回 `case_id`；**不**改 live YAML |
| 2 | **加权检索**（词含 ServiceEndpoint / triage） | 高 `reward_ema` 靠前；`serve_count`+1；可能带 `ucb_bonus` |
| 3 | **高分反馈**（rating≈0.95） | `reward_ema` 上升；可能 `evolve.status=draft` + `proposal_id` |
| 4 | **强制入队提案** | 默认 `auto_apply=false`；开 `AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY` 时 edge 可自动 apply |
| 5 | **回滚提案**（若已 apply） | 恢复 apply 前快照；status=`rolled_back` |
| 6 | （可选）再执行一次告警分诊 Action | ActionRegistry 自动写回案例（best-effort） |

```http
GET  /api/platform/apps/fde/ontology/cases/meta?domain_id=it-ops
POST /api/platform/apps/fde/ontology/cases
GET  /api/platform/apps/fde/ontology/cases/search?domain_id=it-ops&q=ServiceEndpoint
POST /api/platform/apps/fde/ontology/cases/{case_id}/feedback
POST /api/platform/apps/fde/ontology/cases/{case_id}/evolve
POST /api/platform/apps/fde/ontology/cases/{case_id}/rollback
```

口述红线：学习改的是**案例排序**；默认进化出口是**提案门**；edge 自动 apply 是 opt-in，且可回滚、禁升格。  
入队后点 **打开知识工厂批准此提案** → `/knowledge/business?tab=factory&domain=…&proposal=…`。

---

## §治理洪水（P4）— AcceptTab data-gov

| 步 | 操作 | 期望 |
|----|------|------|
| 0 | 看 **数据治理场景 · 8 步对照** | 每步有状态标签 + 深链；无材料 KPI |
| 1–3 | 创建治理教学图 → 丢幽灵 / 挂目录 | 闸2 写 ABox；viewer 丢弃应拦截 |
| — | （可选）工厂①b 表头/CSV → 见 AI补齐启发式 → 入队提案 | Path A；≠写图 |

---

## §工厂 ①b 代码建议 / 表头→提案

业务本体 → 工厂流水线 → **①b**：

| Tab | 作用 | API |
|-----|------|-----|
| 表头/CSV | 表名+CSV → edge 类提案草稿（≠写图） | `POST …/ontology/schema-suggestions` |
| 代码片段 | 代码/ER → 类提案草稿 | `POST …/ontology/code-suggestions` |

须 ③ 批准→apply。写实例仍走 FDE⑦ `source_type=table_map`。
