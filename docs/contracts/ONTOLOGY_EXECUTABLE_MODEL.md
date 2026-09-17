# 可执行本体模型（Palantir 式 OS 内核）

| 字段 | 值 |
|------|-----|
| 文档 ID | `ONTOLOGY-EXECUTABLE-MODEL-2026-09` |
| 版本 | v1.1 |
| 状态 | **已决议**（Phase 0 决策记录） |
| 关联 | [`ONTOLOGY_RUNTIME_AUTHORITY.md`](./ONTOLOGY_RUNTIME_AUTHORITY.md) · [`ONTOLOGY_NARRATIVE.md`](./ONTOLOGY_NARRATIVE.md) · [`ONTOLOGY_XINGYE_PPT_ANALYSIS.md`](./ONTOLOGY_XINGYE_PPT_ANALYSIS.md) · [`ONTOLOGY_OUTCOME_GOALS.md`](./ONTOLOGY_OUTCOME_GOALS.md) · [`ONTOLOGY_OWL_CONCEPT_MAP.md`](./ONTOLOGY_OWL_CONCEPT_MAP.md) |
| 维护人 | Oliver Zhu |

---

## 0. 决策记录（书面确认）

| 项 | 决议 |
|----|------|
| **运行时权威** | 域 YAML（TBox）+ GraphIndex（ABox）+ ActionRegistry L1 |
| **运行时 OWL / HermiT / Pellet / ELK / SPARQL 级推理** | **非目标**；除非另开 RFC 且明确「仅离线、非审计权威」 |
| **产品定位** | Palantir 式「企业操作系统内核」意义上的可执行本体，不是 OWL 推理机产品 |
| **Evolve vs 本体提案** | 配置 Evolve ≠ 说明书变更；`touches_abox\|touches_ontology` 禁止走 Evolve apply |
| **日期** | 2026-09-16 |

---

## 1. 战略一句话

把 aiPlat 建成 **说明书定义世界与可行动边界、真实层承载实例与状态、Action 硬门驱动「该做什么」并写回现实** 的平台；**不以 OWL 推理机作运行时权威**。

---

## 2. OWL vs Palantir（纠偏版）

| | OWL 路线 | Palantir / 本平台路线 |
|--|----------|------------------------|
| 本质 | W3C 知识表示标准 | 运营层平台能力 |
| 核心问题 | 什么是真的（推理） | 该做什么、做了怎样（执行） |
| 一等公民 | 公理 + Reasoner | 对象 + Link + **Action** |
| TBox/ABox | **两者皆有**；卖点在 TBox 可推理性 | **两者皆有**；卖点在 ABox 状态变化 + Kinetic |
| 与 aiPlat | 可选：离线一致性 / 导入导出 | **默认运行时权威路径** |

### 禁止过冲（对外）

| ❌ 禁止说 | ✅ 应说 |
|----------|--------|
| 「OWL 只有 TBox」 | OWL 也有 ABox；差别在卖点 |
| 「Palantir / 我们不要逻辑」 | 我们要工程约束（类/状态/ACL/硬门），不追求 DL 完备推理 |
| 「OWL 已上线推理」 | 运行时权威在 YAML + 图 + Action |
| 「我们融合了 HermiT」 | 可选离线校验另开 RFC；当前非目标 |

概念级对照（Class / Property / Individual / Axiom / OWA ↔ YAML·GraphIndex·Action）：见 [`ONTOLOGY_OWL_CONCEPT_MAP.md`](./ONTOLOGY_OWL_CONCEPT_MAP.md)。

### 2.1 建议层边界（可验证）

推理输出**仅建议层**：任何落图或改状态必须经显式 Action（`platform_action:graph:assert_inferred_*`）或本体提案，并带审批与快照。  
`GraphInference.apply_to_graph` 默认拒绝直写；引擎管道只收集 `inferred_suggestions`。

---

## 3. 目标分层（对外一页图）

```text
适配层     监控/API/DB/文档/管理端/FDE
    ↓ 路径 A/B/C 入轨
可执行内核  域YAML(TBox) · GraphIndex(ABox) · Action L1 · 提案门 · ABox ACL
    ↓ 硬门内调用
智能体层   Pipeline / Skill / Syscall（禁止平行写图）
    ↓
场景交付   故障诊断 · 数据治理 · 工厂生成应用
```

### 权威不变式

1. **TBox**：`~/.aiplat/ontologies/{domain}.yaml`；变更仅经提案 apply。  
2. **ABox**：GraphIndex；路径 A 不直接产实例；B/C/Action/confirm 写实例。  
3. **L1 > L2 > L3**：硬门否决 > 公理/prompt 软约束 > 审计。  
4. **Wiki / OWL** 不得进入业务 Action / 审计快照权威链。

---

## 4. 路径 A / B / C

| 路径 | 行为 | 生产入口 |
|------|------|----------|
| A | 数据源→说明书（抽取→confirm→提案 apply） | 知识工厂 |
| B | 数据源→真实层 | `POST .../graph/import` · `POST .../graph/webhook/{source_id}` |
| C | 已有说明书→模板种图 | AcceptTab 演示种子 |

---

## 5. 实施后仍不宣称

- 运行时 HermiT / Pellet / ELK / SPARQL 级推理已上线  
- 星邺宣传人天 / 准确率已复现  
- 企业全域统一 TBox / 全域 CBAC 产品完成  
- 生产监控 / DB 已全量自动建成全域本体  

---

## 6. 验收目的（G1–G7）

见完整方案 Phase 门禁；工程度量锚定 [`ONTOLOGY_OUTCOME_GOALS.md`](./ONTOLOGY_OUTCOME_GOALS.md) 与本文件 §0 决议。
