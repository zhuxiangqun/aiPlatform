# OWL 概念 ↔ aiPlat 映射

| 字段 | 值 |
|------|-----|
| 文档 ID | `ONTOLOGY-OWL-CONCEPT-MAP-2026-09` |
| 版本 | v1.0 |
| 关联 | [`ONTOLOGY_EXECUTABLE_MODEL.md`](./ONTOLOGY_EXECUTABLE_MODEL.md) · [`ONTOLOGY_RUNTIME_AUTHORITY.md`](./ONTOLOGY_RUNTIME_AUTHORITY.md) · [`ONTOLOGY_NARRATIVE.md`](./ONTOLOGY_NARRATIVE.md) · [`ONTOLOGY_XINGYE_PPT_ANALYSIS.md`](./ONTOLOGY_XINGYE_PPT_ANALYSIS.md) |
| 用途 | 把教科书级 OWL 概念对齐到本仓库实现；**不**把本文件写成「运行时 OWL 已上线」 |
| 维护人 | Oliver Zhu |

---

## 一句话

**OWL**（W3C Web Ontology Language）把本体从词表升级为**形式化、可推理**的知识模型。  
**aiPlat** 运行时权威是 **域 YAML（说明书 TBox）+ GraphIndex（真实层 ABox）+ ActionRegistry L1（可执行写回）**——追求「该做什么、做了怎样、可否决、可审计」，**不以 HermiT/Pellet 等推理机作运行时权威**（决议见 [`ONTOLOGY_EXECUTABLE_MODEL.md`](./ONTOLOGY_EXECUTABLE_MODEL.md)）。

---

## 1. 概念对照表

| OWL 概念 | 教科书含义 | aiPlat 对应 | 诚实边界 |
|----------|------------|-------------|----------|
| **Class** | 领域概念 | 域 YAML `classes`（含 `label` / 状态机） | 类层次多为显式配置，非 DL 自动分类结果 |
| **Object / Data Property** | 关系 / 字面量属性 | `object_properties` + GraphIndex 边 / 实体 `metadata` | 无完整 RDF 属性特征公理层 |
| **Individual** | 实例 | GraphIndex 节点（路径 B/C/Action/confirm 写入） | 序列化不必是 RDF；权威在图，不在 Wiki |
| **Axiom** | 逻辑约束 | YAML `axioms`（多为 **L2** 软约束 / 编译进 prompt）+ Action **L1**（`required_state` / ACL 等硬门） | L2 ≠ 描述逻辑完备推理；L1 是工程否决 |
| **TBox** | 术语/模式层 | `~/.aiplat/ontologies/{domain}.yaml` + 提案 apply | 变更走 VersionedOntologyStore，禁止 Evolve 静默改 |
| **ABox** | 断言/事实层 | GraphIndex | 路径 A 不直接产实例 |
| **Reasoner** | 一致性 / 分类 / 实例化 | **非运行时目标**；运营侧用硬门 + 状态机 + 图遍历/SOP | 禁止宣称 HermiT/Pellet/ELK 已上线 |
| **URI / 互操作** | 全局标识与共享 | `namespace` + `domain_id` + registry | 促进域内一致；不宣称全域统一 TBox |

知识图谱常见说法「OWL = Schema、RDF = 实例」在本平台应改述为：

> **YAML ≈ TBox 说明书，GraphIndex ≈ ABox 真实层**；不必绑定 RDF/OWL 序列化。

---

## 2. 「推理」对照（防假绿）

| OWL 推理能力 | aiPlat 实际做法 |
|--------------|-----------------|
| 一致性检查 | 配置/提案校验、Action 参数与状态门；**非**本体级 DL 一致性证明 |
| 分类（子类推断） | 人工/提案维护类层次；不自动推出「隐含子类」为权威 |
| 实例化（类型推断） | 写入时校验 `class ∈ 说明书`；不跑实例分类器填隐含类型 |
| 查询回答（蕴含） | GraphIndex 查询、GraphRAG、Agent 在硬门内规划；**审计快照不以推理蕴含为准** |
| 传递属性 / 属性链 | 可用显式边 + 应用逻辑走图；**不**宣称 `owl:TransitiveProperty` 行为 |

卖点差异：**OWL 卖「什么是真的」；aiPlat 卖「该做什么、写回是否合法、可否决」。**

---

## 3. 开放世界假设（OWA）

| | OWL 默认 | aiPlat 运营路径 |
|--|----------|-----------------|
| 假设 | **开放世界**：未声明 ≠ 假 | Action / 工单更接近**封闭世界式工程校验** |
| 例 | 未说「张三是医生」≠「不是医生」 | 缺 `required_state` / 非法转移 → **blocked** |
| 注意 | 用 OWL 思维做工单会误判「系统该放行」 | 用数据库思维要求 OWL「未知即假」也会误用推理机 |

二者不可混谈：说明书可保留「软公理」叙事；**改现实**一律过 L1。

---

## 4. OWL 2 Profiles（仅背景）

EL / QL / RL / DL / Full 用于权衡表达力与推理复杂度。  
aiPlat **不选择任一 profile 作为运行时上线承诺**，避免「我们用了 OWL 2 RL」类假绿话术。

---

## 5. 禁止表述

与 [`ONTOLOGY_NARRATIVE.md`](./ONTOLOGY_NARRATIVE.md) / EXECUTABLE_MODEL 一致：

- 「OWL / SPARQL 级推理已上线」「HermiT 已融合进运行时」
- 「完整企业本体 / 全域统一语义已建成」
- 「YAML axioms = OWL DL 公理且可完备分类」

---

## 6. 可选远期（须另开 RFC）

离线 OWL 导出或一致性检查：**仅离线、非审计权威、不得阻断 L1**。未开 RFC 前视为非目标。
