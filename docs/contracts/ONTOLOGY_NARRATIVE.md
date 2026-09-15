# 本体对外叙事（责任语言）

| 字段 | 值 |
|------|-----|
| 文档 ID | `ONTOLOGY-NARRATIVE-2026-09` |
| 版本 | v1.0 |
| 关联 | [`ONTOLOGY_RUNTIME_AUTHORITY.md`](./ONTOLOGY_RUNTIME_AUTHORITY.md) · [`ONTOLOGY_COMPLETENESS.md`](./ONTOLOGY_COMPLETENESS.md) |
| 维护人 | Oliver Zhu |

---

## 一句话（销售）

我们卖的不是知识图谱，而是**可配置的业务世界 + 可执行的边界**：改域配置就能扩展客户语义，Agent 越界会被系统否决，每次否决可审计。

---

## 一段话（客户）

贵司的业务对象、状态和规则写在域本体里；运行中的事实落在业务图里。智能体查事实、做判断、调动作时，必须遵守域里的类与状态约束。平台知识库（Wiki）帮助检索文档，但**不替代**贵司业务权威定义。配置变更走「配置 Evolve」观测窗；本体变更走分级审批的「本体提案」——两条路径分开，避免静默改规则。

---

## 一页纸（技术评审）

1. **权威**：业务 Action / 审计快照 / GraphRAG 业务对象 → 域 YAML + GraphIndex；Wiki 仅知识库轨道。  
2. **约束**：L1 Action 硬门 > L2 域公理 prompt 软约束 > L3 审计；无 L1 不得上 customer_action 生产。  
3. **演化二分**：Evolve = 白名单配置键；本体演化 = VersionedOntologyStore tier 门。  
4. **注册**：`registry.json` 为配置源，`DomainRouter` 为运行时权威。  
5. **试点**：`lock-service` 五件套（类/状态/证据/Action/回写）；闭环深度目标中档+深档。  
6. **非目标**：全域 OWL 推理机、SQL Bridge 生产接通、28 域全量 axioms、Fleet 产品化。

**禁止表述**：「完整企业本体已建成」「OWL/SPARQL 级推理已上线」「全域统一语义」。

完整性官方定义与 OCS 见 [`ONTOLOGY_COMPLETENESS.md`](./ONTOLOGY_COMPLETENESS.md)（平台能力完整 + 客户纵深完整，非跨企业统一 TBox）。

---

## 与假绿相关的诚实句（内部/评审）

在线图校验若未实际执行检查，必须返回 `status=unchecked` 且 `valid=false`，不得显示通过。详见权威契约 §6。
