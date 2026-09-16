# 星邺目标 → aiPlat 能力结果（成功标准）

| 字段 | 值 |
|------|-----|
| 文档 ID | `ONTOLOGY-OUTCOME-GOALS-2026-09` |
| 版本 | v1.6 |
| 关联 | [`ONTOLOGY_EXECUTABLE_MODEL.md`](./ONTOLOGY_EXECUTABLE_MODEL.md) · [`ONTOLOGY_XINGYE_PPT_ANALYSIS.md`](./ONTOLOGY_XINGYE_PPT_ANALYSIS.md) · [`ONTOLOGY_NARRATIVE.md`](./ONTOLOGY_NARRATIVE.md) · [`ONTOLOGY_PPT_SCENARIOS.md`](./ONTOLOGY_PPT_SCENARIOS.md) · [`ONTOLOGY_DEMO_PLAYBOOK.md`](./ONTOLOGY_DEMO_PLAYBOOK.md) · [`ONTOLOGY_RUNTIME_AUTHORITY.md`](./ONTOLOGY_RUNTIME_AUTHORITY.md) · [`ONTOLOGY_CONNECTOR_TEMPLATES.md`](./ONTOLOGY_CONNECTOR_TEMPLATES.md) |
| 原则 | **能力结果**才算达成；仅叙事/分析文档不算。运行时 OWL 全家桶为非目标（见 NARRATIVE / EXECUTABLE_MODEL） |

---

## T1–T9 成功标准

| ID | 星邺描述的目标 | aiPlat「达成」定义 | P0 | P1 | P2 | P3 | P4 |
|----|----------------|-------------------|:--:|:--:|:--:|:--:|:--:|
| T1 | 本体是 AI 语义底座 | it-ops / data-gov YAML + 动作硬门 | ✅ | ✅ | ✅ | ✅ | ✅ |
| T2 | 数据层对象属性关系 | GraphIndex 实例与边（B/C） | — | ✅ | ✅ | ✅ | ✅ |
| T3 | 逻辑层流程/规则 | 状态机 + 提案 apply | 部分 | ✅ | ✅ | ✅ | ✅ |
| T4 | 行动层对象行为 | triage / mount_catalog 等写回 | ✅ | ✅ | ✅ | ✅ | ✅ |
| T5 | 多源建模 | C 种图；B JSON/confirm；A apply | C✅ | B✅ | B✅ | A✅ | ✅ |
| T6 | 故障诊断根因 | 多告警 + 硬门 + AcceptTab | — | ✅ | ✅ | ✅ | ✅ |
| T7 | 数据治理资产化 | 抽取→图/提案 + **治理教学图闸2** | — | — | 部分 | ✅ | ✅ |
| T8 | 智能体/工作台形态 | AcceptTab 故障+治理；知识工厂 | — | ✅ | ✅ | ✅ | ✅ |
| T9 | 权限细控 | 域动作级 + **实例/属性 ABox ACL** | 部分 | 部分 | 部分 | 部分 | ✅ |

**P4 勾选**：`graph_abox_acl` 可测 + data-gov 种图/挂目录/丢幽灵 + AcceptTab。

---

## P1–P3 证据（摘要）

见历史版本清单；故障 PLAYBOOK §故障；confirm/apply 见 P2/P3 节（v1.1–v1.2）。

---

## P4 证据清单（ACL + 治理闸2）

| 项 | 证据 |
|----|------|
| 实例 ACL | `core/policy/graph_abox_acl.py`；viewer 拒读 `TBL-tmp_export` |
| 属性脱敏 | `set_field_acl` / `redact_entity_fields`；`owner_contact` admin-only |
| API | `GET /graph/entities?actor_role=`；execute 前 `state_change` ACL |
| 治理种图 | `scenario=data-gov-assets`；AcceptTab「创建治理教学图」 |
| 闸2 | `mount_catalog` / `discard_ghost`；`test_data_gov_p4.py` |
| 剧本 | [`ONTOLOGY_DEMO_PLAYBOOK.md`](./ONTOLOGY_DEMO_PLAYBOOK.md) §治理洪水 |

### P5 打磨（闸2 一键可点 + ACL 演示）

| 项 | 证据 |
|----|------|
| `catalog_id` 默认 | ActionCards `defaultParams` / `fieldDefault('catalog_id')` |
| CoreFacade | `check_graph_entity_acl` / `redact_graph_entity_fields` |
| viewer 写拦截 | AcceptTab「viewer试丢弃（应拦截）」；`test_viewer_acl_blocks_state_change_check` |
| 属性脱敏可见 | 刷新后展示 `owner_contact：viewer=… / admin=…` |
| 诚实性 | B4.4：AcceptTab 种 B4.3 **子集**（非全图） |

---

## 轨道收尾（P0–P5）

星邺「能力结果」竖切在本仓库已可演示闭环：

| 轨 | 入口 |
|----|------|
| 故障 | AcceptTab it-ops：种图/导入 → 三动作 |
| 治理说明书 | 知识工厂：confirm → 批准 → apply |
| 治理实例 | AcceptTab data-gov：种图 → 丢幽灵 / 挂目录 + ACL |

**全量回归（本地）**：

```bash
cd aiPlat-core && PYTHONPATH=..:.:../.venv/lib/python*/site-packages \
  ../.venv/bin/python -m pytest \
  core/tests/unit/test_harness/test_knowledge/test_it_ops_alert_lifecycle.py \
  core/tests/unit/test_harness/test_knowledge/test_data_gov_p4.py \
  core/tests/unit/test_harness/test_knowledge/test_lock_service_ontology_loop.py \
  core/tests/unit/test_harness/test_knowledge/test_ontology_completeness_ocs.py \
  core/tests/unit/test_harness/test_knowledge/test_executable_ontology_phase12.py \
  -q
```

---

## 可执行本体产品化（Phase 0–3 lite，2026-09）

| 阶段 | 交付 | 证据 |
|------|------|------|
| 0 | 战略契约 | `ONTOLOGY_EXECUTABLE_MODEL.md`；NARRATIVE v1.16；OWL 非目标书面决议 |
| 1.1 | 路径 B webhook | `abox_connector.py`；`POST .../graph/webhook/{source_id}`；connector.json |
| 1.2 | ACL↔身份 | `resolve_abox_actor_role`；Header `X-AIPLAT-ACTOR-ROLE` / scopes |
| 1.3 | 域脚手架 | `scripts/new_domain_scaffold.py`（YAML+action+test+connector+PLAYBOOK） |
| 2 | 第二域 | `retail-ops` YAML/actions/种子；同构 triage 测试 |
| 3 lite | 模板+ACL API | `ONTOLOGY_CONNECTOR_TEMPLATES.md`；`GET/PUT .../graph/acl/...` |

**非目标（仍不算达成）**：企业全域 CBAC 产品化、运行时 OWL、建模期内置 OWL 完备推理、生产监控全量接入。

---

## 完整改善方案进度（A–E，2026-09）

| 阶段 | 交付 | 状态 |
|------|------|------|
| A | 五层对照 + 建模 OWL 诚实句 + PLAYBOOK 表映射/三柱 | ✅ |
| B2 | 表/CSV → GraphIndex（`source_type=table_map`） | ✅ 本轮 |
| B3 | 代码路径建议 → 提案草稿（不自动 apply） | ✅ 本轮 |
| C | `GET .../ontology/pillars/{domain}` 三柱 API + AcceptTab 速览 | ✅ 本轮 |
| D | 离线 OWL 审稿门：`status=unchecked` 禁假绿（无推理机依赖） | ✅ 本轮 |
| E | 脚手架回归 + CAPABILITIES | ✅ 本轮 |
