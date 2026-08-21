# 企业级 AI 可信落地全景图 × aiPlat 对照（2026-08-19）

> **背景**：以六层"决策操作系统"框架（战略罗盘 / 静态知识底座 / 动态感知 / 混合推理 / 双重可信审计 / 受控行动与进化）为标尺，对照 aiPlat 现状。
> **方法**：逐层代码实证（`文件:行号`），与框架要求逐一比对，标注成熟度与差距。
> **总体结论**：**六层全覆盖**（无缺失层，对照三方只有 aiPlat 同时具备本体+推理+审计+Action+进化）；**原 3 个真实缺口已全部闭环**（L2 业务事件流 P0-L2 #58、L4 反事实扰动+SIRG #62/#63、L3 本体公理约束编译 #62，2026-08-19~21）；**3 个强项已验证**（本体学习闭环、Action 阶梯+本体版本管理、证据验证基础）；**P2 治理强化全落地**（#64）：L1 本体分层治变（tier 分级审批 + 升格复用证明）、L0 立项四问工具化、L5 Action 阶梯 Lv 标注 + 自动闭环误报率门（FP<0.5%）。

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

### L0 战略罗盘（方向盘）—— ⭐⭐⭐⭐ 方法论有 + 已工具化（P2-L0 四问评估）

**框架要求**：立项四问（决策反复发生 / 跨 3+ 系统 / 有 Owner+量化指标 / 可写回 Action）+ MVP 本体分层实施。

**aiPlat 现状**：
- ✅ FDE 诊断→证据映射→覆盖率→改进→交付→评分→对比→基准→目标分解→自主部署→外部发现 是 aiPlat 的核心定位（第 5 层架构）
- ✅ **立项四问已工具化（P2-L0）**：`core/apps/fde/service/four_questions.py`——四问（反复/跨系统/Owner+指标/Action）→ 0-100 分 + go/conditional/sandbox 结论 + MVP 本体 tier 建议；FDE 诊断卡端点 `GET/POST /fde/diagnostics/four-questions`

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

### L5 受控行动与现场进化（副驾+修路队）—— ⭐⭐⭐⭐⭐ 强（P2-L5 量化门已加）

**框架要求**：Action 阶梯（Lv1 只读→Lv4 自动闭环，逐级真实业务考验）；FDE 学习回路（例外→SWRL/对象升格）；Branch/Proposal/Rebase 本体版本管理；驳回数据反哺（原因标签）。

**aiPlat 现状**：
- ✅ **Action 阶梯**：Action Contract v3 + ApprovalGate + Action Registry（aiPlat 强项，企业治理核心）
- ✅ **本体版本管理**：`versioned_ontology_store`（`create_proposal:78` / `list_proposals:99` / `apply_proposal:104`）——框架"Branch/Proposal/Rebase"的 Proposal 骨架
- ✅ **驳回原因反哺**：`proposal_store.rejected_reason`（`:57/79`）
- ✅ **FDE 学习回路**：aiPlat 定位即 FDE（例外→技能/规则沉淀，AutoLearner/evolution_runner）
- ✅ **量化门已显式（P2-L5）**：`ActionLevel`（lv1_readonly→lv4_auto_close，默认 Lv2 保守）+ `compute_closure_gate`（Lv4 自动闭环需历史误报 <0.5%，超标降级人工确认）

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

## 3.5 路线图执行进度（2026-08-21 更新）

| 优先级 | 项 | 状态 | 实施 |
|---|---|---|---|
| **P0-L2** | 业务事件流（GPS 层） | ✅ **已实施** | #58：Action 成功 → EventBus + business_event_bridge 即时 GraphIndex 增量更新（替代定期 ABox 重建） |
| **P1-L3** | 本体公理约束编译（SWRL/ABox → 生成前 System Prompt/JSON Schema） | ✅ **已实施** | #62：`ontology_constraint_compiler`（AXIOMS/类字段 → 硬规则）+ `prompt_assembler` opt-in 注入（`meta.inject_ontology_contract`，默认不注入保 prompt cache） |
| **P1-L4a** | EAEV 反事实扰动 | ✅ **已实施** | #62：`counterfactual_perturb` 实体替换→同上下文重验→漂移>0.3 且原置信>0.6 判记忆惯性，best-effort 接入 evaluate |
| **P1-L4b** | SIRG 推理链 vs 规则链一致性 | ✅ **已实施** | #63：`sirg_auditor`（rule_chain_for + audit_reasoning），缺失规则→违规报告；推理链取可观测执行面 |
| **P2-L1** | 本体三层分离（tier 字段） | ✅ **已实施** | #64：`OntologyClass.tier`（core/logic/edge，默认 logic 兼容存量）+ loader 解析/校验 + `versioned_ontology_store` 分级审批（core 需架构评审 / logic 产品侧 / edge 自服务）+ edge→logic 升格需复用证明（reuse_count≥3）+ ontology_audit 按 tier 分组 |
| **P2-L0** | 立项四问工具化 | ✅ **已实施** | #64：`four_questions.evaluate_four_questions`（反复/跨系统/Owner+指标/Action 四问 → 0-100 分 + go/conditional/sandbox 结论 + MVP tier 建议）+ FDE 诊断卡端点（GET/POST /fde/diagnostics/four-questions） |
| **P2-L5** | Action 阶梯量化门 | ✅ **已实施** | #64：`ActionLevel`（lv1_readonly→lv4_auto_close，默认 Lv2 保守）+ `compute_closure_gate`（Lv4 自动闭环需历史误报 <0.5%，超标降级人工确认）+ 修复 `_get_entity`（`g.get()`→`get_node`，GraphIndex 实体加载此前恒失败） |

**执行原则**：程序修改暂停于 P0-L2 之后（2026-08-19），文档先行同步；后续按 P1 → P2 顺序恢复实施。**P0 + P1 全部 + P2 全部（L1/L0/L5）已闭环**，路线图仅剩后续扩展方向（见 §3.6）。

---

## 3.6 改进后的整体效果（从"部件清单"到"系统能力"）

### 一句话画像

- **改进前**：aiPlat 是"带本体的知识问答系统"——知识管线有空壳（向量/图增强声明未接线）、感知靠定期重建、检索含中文失真、本体靠专家手写。
- **改进后**：aiPlat 是"企业级 AI 决策操作系统"——知识全链路真实、业务实时感知、检索语义化、本体可学习可演进、行动可治理。

### 端到端效果（以"合同续约决策"为例）

| 环节 | 改进前 | 改进后 | 代码实证 |
|---|---|---|---|
| 知识入库 | 向量/图增强是空壳（0 写入者），检索靠 FTS | 摄取 → kb_embeddings（**真语义 384 维**）+ kb_graph + wiki 全链路真实 | #50 / #54 |
| 本体 | 专家手写 YAML，无自动学习 | 文档 → 概念聚类 → is-a 层次 → **OWL/TTL 输出**（可审查、可导入） | #51 / #53 |
| 感知 | 下午 3 点签约，凌晨重建才可见 | **签约即感知**（BUSINESS_ACTION → GraphIndex 即时，实测 `sign_contract` → `contract-1001` 即时创建） | #58 |
| 检索 | 中文相关性失真（完全包含也 0 分） | 中文 bigram 切词 **0 → 0.71** | #49 |
| 推理 | 取块靠 wiki 名义向量 | GraphRAG 实体路由 → **真向量取块**（kb_embeddings 优先） | #55 |
| 行动 | Action 阶梯 + 审批已具备 | 本体 Proposal 版本管理 + 驳回原因反哺（FDE 进化闭环） | 既有强项 |

### 业务价值层（对 CTO / CEO / 业务方的语言）

1. **实时性**：决策数据从"隔夜"到"即时"——风控/续约/库存场景的响应窗口从 **24 小时级 → 秒级**（事件桥）。
2. **可信性**：中文相关性可度量 + 证据验证 + 检索质量门——回答的"相关性"从凭感觉变成可审计指标（中文 0 → 0.71）。
3. **可演进性**：本体学习（文档→OWL）+ Proposal 版本管理——业务变化以天/周为单位落地，**不重构核心**（tier 分层设计已就绪）。
4. **可治理性**：Action 阶梯 + 审批 + 驳回反哺——AI 动手有边界，进化有原因标签，自动闭环有量化门。

### 量化效果（可验证，非口号）

| 指标 | 改进前 | 改进后 |
|---|---|---|
| 知识五要素（数据元/本体/向量/wiki/RAG）真实数据流 | 2 个空壳（kb_embeddings / kb_graph 0 写入者） | **全部真实**（接线 + DDL 补齐） |
| 本体来源 | 仅专家手写 | 专家 + **学习**（4 类建议 → OWL/TTL 文件） |
| 业务动作 → 本体实例 | 定期全量重建（隔夜） | **事件驱动即时**（秒级） |
| 中文检索相关性 | 0.0（完全包含也失分） | **0.71**（bigram 切词） |
| 向量质量 | hash 占位 / 伪向量 | **真语义 384 维**（embed + GraphRAG 取块） |

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
