# 本体对外叙事（责任语言）

| 字段 | 值 |
|------|-----|
| 文档 ID | `ONTOLOGY-NARRATIVE-2026-09` |
| 版本 | v1.19 |
| 关联 | [`ONTOLOGY_EXECUTABLE_MODEL.md`](./ONTOLOGY_EXECUTABLE_MODEL.md) · [`ONTOLOGY_OWL_CONCEPT_MAP.md`](./ONTOLOGY_OWL_CONCEPT_MAP.md) · [`ONTOLOGY_RUNTIME_AUTHORITY.md`](./ONTOLOGY_RUNTIME_AUTHORITY.md) · [`ONTOLOGY_COMPLETENESS.md`](./ONTOLOGY_COMPLETENESS.md) · [`ONTOLOGY_PPT_SCENARIOS.md`](./ONTOLOGY_PPT_SCENARIOS.md) · [`ONTOLOGY_XINGYE_PPT_ANALYSIS.md`](./ONTOLOGY_XINGYE_PPT_ANALYSIS.md) · [`ONTOLOGY_OUTCOME_GOALS.md`](./ONTOLOGY_OUTCOME_GOALS.md) · [`ONTOLOGY_DEMO_PLAYBOOK.md`](./ONTOLOGY_DEMO_PLAYBOOK.md) · [`ONTOLOGY_CONNECTOR_TEMPLATES.md`](./ONTOLOGY_CONNECTOR_TEMPLATES.md) |
| 维护人 | Oliver Zhu |

---

## 一句话（销售）

我们卖的不是知识图谱，而是**可配置的业务世界 + 可执行的边界**：改域配置就能扩展客户语义，Agent 越界会被系统否决，每次否决可审计。

---

## 一段话（客户）

贵司的业务对象、状态和规则写在域本体里；运行中的事实落在业务图里。智能体查事实、做判断、调动作时，必须遵守域里的类与状态约束。平台知识库（Wiki）帮助检索文档，但**不替代**贵司业务权威定义。配置变更走「配置 Evolve」观测窗；本体变更走分级审批的「本体提案」——两条路径分开，避免静默改规则。

---

## 一页纸（技术评审）

1. **定位**：我们是 **Palantir 式可执行本体（企业 OS 内核）**——说明书 + 真实层 + Action 硬门；**不是**运行时 OWL 推理机产品。详见 [`ONTOLOGY_EXECUTABLE_MODEL.md`](./ONTOLOGY_EXECUTABLE_MODEL.md)。OWL 教科书概念如何映射到本平台：[`ONTOLOGY_OWL_CONCEPT_MAP.md`](./ONTOLOGY_OWL_CONCEPT_MAP.md)。  
2. **权威**：业务 Action / 审计快照 / GraphRAG 业务对象 → 域 YAML + GraphIndex；Wiki 仅知识库轨道。  
3. **约束**：L1 Action 硬门 > L2 域公理 prompt 软约束 > L3 审计；无 L1 不得上 customer_action 生产。  
4. **演化二分**：Evolve = 白名单配置键；本体演化 = VersionedOntologyStore tier 门。  
5. **注册**：`registry.json` 为配置源，`DomainRouter` 为运行时权威。  
6. **入轨**：路径 A（提案改说明书）/ B（webhook·JSON·**表/CSV 映射** 写真实层）/ C（模板种图）；生产监控进图走 B webhook。  
7. **试点**：`lock-service` · `it-ops` · `data-gov` · `retail-ops`；ACL 接身份角色（viewer/analyst/admin）。  
8. **建议层**：`GraphInference` / 导出 OWL **不是**已确认事实；落图须 `assert_inferred_*` 或提案。  
9. **非目标**：运行时 HermiT/Pellet/ELK、建模期内置 OWL 推理机、SQL Bridge 全量接通、28 域全量 axioms、Fleet、全域 CBAC。

**禁止表述**：「完整企业本体已建成」「OWL/SPARQL 级推理已上线」「全域统一语义」「HermiT 已融合进运行时」「推理建议已自动确认为业务事实」「建模已内置 OWL 完备推理」。

完整性官方定义与 OCS 见 [`ONTOLOGY_COMPLETENESS.md`](./ONTOLOGY_COMPLETENESS.md)（平台能力完整 + 客户纵深完整，非跨企业统一 TBox）。

**口径统一**：星邺「融合 OWL」在我方表述为「OWL 可作**导出与离线审稿**；规则可作建议；运行时权威仍是 YAML + 图 + Action」——导出 ≠ 推理已上线。

### 星邺五层 ↔ aiPlat（code_graph 分桶量级）

| 星邺层 | aiPlat | 图谱分桶量级（约） |
|--------|--------|-------------------|
| OntoStar | YAML + GraphIndex + Action + 提案门 | Onto 内核 ~35 文件 |
| AIStar | infra 模型 + Skill/Syscall | Agent 平台 ~83 |
| SuperStar | Pipeline + FDE + Eval（验证=硬门/审计） | Pipeline ~35 |
| 数字员工 | 场景竖切 / 工厂应用 | FDE 场景 ~48 |
| 适配层 | webhook / 表映射 / 文档提案 | 入轨偏薄→本方案加厚 |

---

## UI 入口映射（管理端）

| 侧边栏 | 含义 |
|--------|------|
| **业务本体** `/knowledge/business` | 权威轨：工厂流水线 / 域管理 / 编辑器 |
| **知识库** `/knowledge/library` | 检索轨：向量 / Wiki / Vault；不替代业务权威 |

---

## 对标星邺 PPT（愿景 vs 工程）

产品愿景分层、Palantir/OWL 关系、亮点缺口与对照表（含诚实句）见 [`ONTOLOGY_XINGYE_PPT_ANALYSIS.md`](./ONTOLOGY_XINGYE_PPT_ANALYSIS.md)。  
**场景解题图**仍只读 [`ONTOLOGY_PPT_SCENARIOS.md`](./ONTOLOGY_PPT_SCENARIOS.md)（上下篇分开）。  
对外禁止把星邺宣传能力说成 aiPlat 已上线。

---

## 场景说明入口（星邺 / aiPlat 请分开读）

详细图文见 [`ONTOLOGY_PPT_SCENARIOS.md`](./ONTOLOGY_PPT_SCENARIOS.md)（**v3.0**）：

- **应有能力路径 A/B/C**（§0.2）：数据源→说明书 / 数据源→真实层（含 **webhook·表/CSV**） / **已有说明书→模板或手动种真实层**  
- **§0.3**：三柱、建议≠权威、ACL 竖切、OWL 非目标  
- 路径 C：AcceptTab 演示直线 + 教学复杂拓扑；路径 B：表/CSV 样例（B3.3b）  
- 本体不凭空生成实例；生产真实层主路径仍是数据源  
- 两篇分开读  

下表仅作一页纸摘要（细节以分章正文为准）：

| 步骤 | 星邺 PPT 叙事 | aiPlat 落地 |
|------|---------------|-------------|
| 世界模型 | 系统/服务/中间件/主机/告警 + 调用/部署等关系类型 | 域 `it-ops` YAML + GraphIndex 实例 |
| 规划 | SuperStar 抽出诊断步骤链 | Agent/流程可读 SOP；每步仍过动作硬门 |
| 执行 | 对象上的动作 | `customer_action:it-ops:*`（分诊→挂疑似→确认根因） |
| 权威 | 材料未钉死 | GraphIndex 快照；Wiki/OWL 不进审计权威链 |
| 推理机 | 材料会提 | 运行时非目标 |

**一句话**：两边都可讲「对象 + 动作 + 走图」；aiPlat 要求**说明书 = 真实层词表 = 推理用词**，并把可否决钉在动作硬门上。

---

## 与假绿相关的诚实句（内部/评审）

在线图校验若未实际执行检查，必须返回 `status=unchecked` 且 `valid=false`，不得显示通过。详见权威契约 §6。
