# 企业级 AI 可信落地全景图 × aiPlat 对照（2026-08-19）

> **背景**：以六层"决策操作系统"框架（战略罗盘 / 静态知识底座 / 动态感知 / 混合推理 / 双重可信审计 / 受控行动与进化）为标尺，对照 aiPlat 现状。
> **方法**：逐层代码实证（`文件:行号`），与框架要求逐一比对，标注成熟度与差距。
> **总体结论**：**六层全覆盖**（无缺失层，对照三方只有 aiPlat 同时具备本体+推理+审计+Action+进化）；**原 3 个真实缺口，L2 业务事件流已闭环（P0-L2 事件桥，2026-08-19）**，剩 **2 个**（L4 反事实扰动+SIRG、L3 本体公理约束编译）；**3 个强项已验证**（本体学习闭环、Action 阶梯+本体版本管理、证据验证基础）。

---

## 1. 六层对照总表

| 层 | 框架要求 | aiPlat 现状（代码实证） | 成熟度 |
|---|---|---|---|
| **L0 战略罗盘** | 立项四问（反复/跨系统/Owner+指标/Action）、MVP 本体 | FDE 诊断闭环是 aiPlat 定位核心（诊断→证据→改进→交付→评分→部署）；"立项四问"是业务方法论，无系统化工具 | ⭐⭐⭐ 方法论有，工具化缺 |
| **L1 静态底座** | 六步 ETL、三层分离（稳定核心/可变逻辑/实验边缘）、SWRL、一致性校验 | 本体 TBox YAML + ABox 构建 + 本体学习→OWL + `to_sparql_rules`（`knowledge_ontology.py:898`）+ `graph_inference.add_rule`（推理规则引擎，`graph_inference.py:189`）+ `validate_tbox` 校验 | ⭐⭐⭐⭐ 强 |
| **L2 动态感知** | GraphDB(TBox)+Neo4j(ABox)、业务事件流（审批/库存/合同 Kafka/Flink） | GraphIndex（本体图）+ kb_embeddings/wiki（双库对应物）；**业务事件桥已建**（P0-L2：#58，`Action 成功 → BUSINESS_ACTION 事件 + business_event_bridge 即时 GraphIndex 增量更新`，替代定期 ABox 重建） | ⭐⭐⭐ 骨架已建（事件源可扩展） |
| **L3 混合推理** | 路由分流（SPARQL/Pellet/向量 RAG）、生成前约束编译（SWRL→prompt/schema） | `ontology_query_mapper` + `traverse_ontology_graph`（本体→图遍历）+ GraphRAG（真向量）+ `coding-contract` 约束注入（`prompt_loader.py:287`——雏形，但为编码契约非本体公理） | ⭐⭐⭐ 路由强，约束编译待本体化 |
| **L4 双重审计** | EAEV（外部证据对账+反事实扰动）、SIRG（内部推理图对比公理路径） | `hallucination_tracker`（EAEV 对应物：claim→证据验证→quality_flag/confidence，`hallucination_tracker.py:102-125`）+ `decision_trace`（决策溯源） | ⭐⭐⭐ 无反事实扰动；SIRG 未实现 |
| **L5 受控行动+进化** | Action 阶梯（Lv1-4）、FDE 学习回路、Branch/Proposal/Rebase 本体版本、驳回原因反哺 | Action Contract v3 + ApprovalGate + 阶梯（aiPlat 强项）+ `versioned_ontology_store`（create_proposal/apply_proposal，`:78-104`）+ `proposal_store.rejected_reason`（驳回原因，`:57/79`） | ⭐⭐⭐⭐ 强 |

---

## 2. 逐层详析

### L0 战略罗盘（方向盘）—— ⭐⭐⭐ 方法论有，工具化缺

**框架要求**：立项四问（决策反复发生 / 跨 3+ 系统 / 有 Owner+量化指标 / 可写回 Action）+ MVP 本体分层实施。

**aiPlat 现状**：
- ✅ FDE 诊断→证据映射→覆盖率→改进→交付→评分→对比→基准→目标分解→自主部署→外部发现 是 aiPlat 的核心定位（第 5 层架构）
- ❌ "立项四问"未工具化：FDE 诊断卡无"决策性价比"评估步骤；MVP 本体 vs 全域本体无显式分层引导

**改进建议**：FDE 诊断卡加"四问"评估步骤（0.5 天）。

### L1 静态知识底座（地图）—— ⭐⭐⭐⭐ 强

**框架要求**：多源采集→NER→概念聚类(is-a)→关系抽取→公理规则编码(SWRL)→一致性校验；三层分离（稳定核心/可变逻辑/实验边缘）。

**aiPlat 现状**：
- ✅ 六步 ETL 对应：DocumentIngestor 分块 → EntityExtractor（9 类实体）→ 本体学习聚类（new_class）→ LLM 层次发现（new_subclass）→ 关系抽取 → `to_sparql_rules` 规则导出
- ✅ `graph_inference.add_rule`（`graph_inference.py:189`）：推理规则引擎（框架"SWRL"的运行时对应物）
- ✅ `validate_tbox`：T-Box 一致性校验（property domain/range 引用 class）
- ❌ **三层分离未显式化**：本体是整体 YAML，无"稳定核心/可变逻辑/实验边缘"分层标记

**改进建议**：ontology YAML 加 `tier: core|logic|edge` 字段 + 变更审计按 tier 分级（1 天）。

### L2 动态感知与实例填充（GPS）—— ⭐⭐⭐ 骨架已建（2026-08-19 P0-L2）

**框架要求**：GraphDB（TBox+物化推理）+ Neo4j（ABox 实例）双库；业务事件流（审批进度/库存扣减/合同签署 Kafka/Flink）回答"现在在哪里"。

**aiPlat 现状**：
- ✅ 双库对应物：GraphIndex（本体图/实例）+ kb_embeddings（向量）+ wiki（FTS）
- ✅ **业务事件桥已建（P0-L2，#58）**：`AsyncActionRegistry.execute` 动作成功 → `BUSINESS_ACTION` 事件（observability EventBus 审计）+ `business_event_bridge` 即时增量更新 GraphIndex（`add_entity` 幂等 upsert + last_action/status/actor）——实例数据从"定期重建"升级为"事件驱动即时反映"（实测 `sign_contract` → `contract-1001` 即时创建）
- ⏳ 扩展方向：审批状态/流水线完成等更多业务动作接入桥；外部系统事件（Kafka/Flink 类）需在部署层接

**改进建议（P0）**：✅ **已实施（#58）**——骨架完成，可扩展更多动作源。

### L3 混合推理与生成引擎（大脑）—— ⭐⭐⭐ 路由强，约束编译待本体化

**框架要求**：路由分流（确定事实→Text-to-SPARQL；复杂逻辑→Pellet 推理；开放语义→向量 RAG）；**生成前约束编译**（SWRL/OWL 公理实时编译为 System Prompt 硬规则 / JSON Schema）。

**aiPlat 现状**：
- ✅ 路由：`ontology_query_mapper`（本体映射）+ `traverse_ontology_graph`（图遍历，3 生产调用者）+ GraphRAG（真向量，本批）
- ✅ 约束注入雏形：`coding-contract`（`prompt_loader.py:287`）在代码生成前注入架构约束
- ❌ **约束编译非本体驱动**：coding-contract 是编码契约，不读本体公理（如"合同必须含生效日期"类业务约束未从 OWL/规则编译）

**改进建议（P1）**：把 `to_sparql_rules`/ABox 实例约束编译为生成前 System Prompt/JSON Schema（复用 `_sync_resolve` 注入机制，1 天）。

### L4 双重可信审计（交规）—— ⭐⭐⭐ 有基础，缺反事实与 SIRG

**框架要求**：EAEV（外部证据对账：实体抽取→三维度对齐→**反事实扰动**→判幻觉）+ SIRG（内部推理图：捕获语义推理图→对比 OWL 公理路径→违规报告）。

**aiPlat 现状**：
- ✅ EAEV 基础：`hallucination_tracker`（`hallucination_tracker.py:102-125`）——claim 验证 + evidence 引用 + quality_flag（ok/needs_review/low_evidence）+ confidence
- ✅ 决策溯源：`decision_trace`（根因定位）
- ❌ **无反事实扰动**：替换实体（阿司匹林→布洛芬）→ 对齐分数波动 → 判幻觉，未实现
- ❌ **SIRG 未实现**：无"推理图 vs OWL 公理路径"比对（决策溯源是执行留痕，非语义推理图审计）

**改进建议（P1）**：① 反事实扰动模块（替换高置信实体重验，1 天）；② 在 `graph_inference` 基础上做"推理链 vs 规则链"一致性报告（1-2 天）。

### L5 受控行动与现场进化（副驾+修路队）—— ⭐⭐⭐⭐ 强

**框架要求**：Action 阶梯（Lv1 只读→Lv4 自动闭环，逐级真实业务考验）；FDE 学习回路（例外→SWRL/对象升格）；Branch/Proposal/Rebase 本体版本管理；驳回数据反哺（原因标签）。

**aiPlat 现状**：
- ✅ **Action 阶梯**：Action Contract v3 + ApprovalGate + Action Registry（aiPlat 强项，企业治理核心）
- ✅ **本体版本管理**：`versioned_ontology_store`（`create_proposal:78` / `list_proposals:99` / `apply_proposal:104`）——框架"Branch/Proposal/Rebase"的 Proposal 骨架
- ✅ **驳回原因反哺**：`proposal_store.rejected_reason`（`:57/79`）
- ✅ **FDE 学习回路**：aiPlat 定位即 FDE（例外→技能/规则沉淀，AutoLearner/evolution_runner）
- ⚠️ 小差距：Action 阶梯的 Lv 划分与"误报率<0.5% 才自动闭环"的量化门未见显式声明

**改进建议**：Action 阶梯加显式 Lv 标注 + 自动闭环量化门（0.5 天）。

---

## 3. 改进建议汇总（按优先级）

| 优先级 | 差距 | 建议 | 工作量 |
|---|---|---|---|
| **P0-L2** | 业务实时事件流缺失（GPS 层） | ✅ **已实施（#58）**：Action 成功 → EventBus + GraphIndex 增量更新 | ✅ 0.5-1 天 |
| **P1-L4a** | EAEV 无反事实扰动 | 反事实扰动模块（替换高置信实体→对齐分数波动→判幻觉） | 1 天 |
| **P1-L4b** | SIRG 未实现（推理图 vs 公理路径） | `graph_inference` 基础上做推理链 vs 规则链一致性报告 | 1-2 天 |
| **P1-L3** | 约束编译非本体驱动 | `to_sparql_rules`/ABox 实例约束编译为生成前 Prompt/JSON Schema | 1 天 |
| **P2-L1** | 三层分离未显式化 | ontology YAML 加 `tier: core|logic|edge` + 变更审计分级 | 1 天 |
| **P2-L0** | 立项四问未工具化 | FDE 诊断卡加四问评估 | 0.5 天 |
| **P2-L5** | Action 阶梯量化门未显式 | 阶梯 Lv 标注 + 自动闭环误报率门 | 0.5 天 |

---

## 3.5 路线图执行进度（2026-08-19 更新）

| 优先级 | 项 | 状态 | 实施 |
|---|---|---|---|
| **P0-L2** | 业务事件流（GPS 层） | ✅ **已实施** | #58：Action 成功 → EventBus + business_event_bridge 即时 GraphIndex 增量更新（替代定期 ABox 重建） |
| **P1-L3** | 本体公理约束编译（SWRL/ABox → 生成前 System Prompt/JSON Schema） | ⏳ 待实施 | 复用 `_sync_resolve` 注入机制（1 天） |
| **P1-L4a** | EAEV 反事实扰动 | ⏳ 待实施 | hallucination_tracker 加扰动函数（1 天） |
| **P1-L4b** | SIRG 推理链 vs 规则链一致性 | ⏳ 待实施 | graph_inference 推理链导出（1-2 天） |
| **P2-L1** | 本体三层分离（tier 字段） | ⏳ 待实施 | ontology YAML 加 `tier: core|logic|edge`（1 天） |
| **P2-L0** | 立项四问工具化 | ⏳ 待实施 | FDE 诊断卡四问评估（0.5 天） |
| **P2-L5** | Action 阶梯量化门 | ⏳ 待实施 | Lv 标注 + 自动闭环误报率门（0.5 天） |

**执行原则**：程序修改暂停于 P0-L2 之后（2026-08-19），文档先行同步；后续按 P1 → P2 顺序恢复实施。

---

## 4. 核心结论

1. **六层全覆盖**：aiPlat 无缺失层——本体+推理+审计+Action+进化同时具备，这在四系统对照中是唯一（Claude Code 无引擎无审计、DSH 无企业治理、Hermes 无审计留痕）。
2. **"分层治变"已有骨架**：`versioned_ontology_store` 的 Proposal 机制 + 建议的 tier 字段 = 框架"稳定核心/可变逻辑/实验边缘 + Branch/Proposal/Rebase"的工程化对应。
3. **"双向校验"差两环（当前最大改进空间）**：事前约束（L3 本体公理编译）与事后审计（L4 反事实+SIRG）是框架的灵魂，aiPlat 各有雏形（coding-contract / hallucination_tracker / decision_trace）但**未本体化**；L2 事件流缺口已闭环（#58），这两项成为下一批实施目标。
4. **"现场进化"是 aiPlat 差异化**：FDE 定位 + AutoLearner + evolution_runner + Proposal 版本管理，已超越框架 L5 的多数要求。

---

## 5. 验证命令

```bash
# L1 规则引擎
grep -n "def add_rule" aiPlat-core/core/harness/ontology_engine/graph_inference.py  # :189
# L1 SPARQL 导出
grep -n "def to_sparql_rules" aiPlat-core/core/harness/knowledge/knowledge_ontology.py  # :898
# L3 约束注入雏形
grep -n "coding-contract" aiPlat-core/core/harness/utils/prompt_loader.py  # :287
# L4 证据验证
grep -n "_verify_claim" aiPlat-core/core/harness/evaluation/hallucination_tracker.py  # :102
# L5 本体 Proposal 版本
grep -n "def create_proposal\|def apply_proposal" aiPlat-core/core/harness/knowledge/versioned_ontology_store.py  # :78/:104
```
