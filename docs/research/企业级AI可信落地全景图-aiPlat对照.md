# 企业级 AI 可信落地全景图 × aiPlat 对照（2026-08-21）

> **背景**：以六层"决策操作系统"框架（战略罗盘 / 静态知识底座 / 动态感知 / 混合推理 / 双重可信审计 / 受控行动与进化）为标尺，对照 aiPlat 现状。
> **方法**：逐层代码实证（`文件:行号`），与框架要求逐一比对，标注成熟度与差距。
> **总体结论**：**六层全覆盖**（无缺失层，对照三方只有 aiPlat 同时具备本体+推理+审计+Action+进化）；**原 3 个真实缺口已全部闭环**（L2 业务事件流 P0-L2 #58、L3 本体公理约束编译 P1-L3 #62、L4 反事实扰动+SIRG P1-L4a/L4b #62/#63）；**3 个强项已验证**（本体学习闭环、Action 阶梯+本体版本管理、证据验证基础）；**P2 治理强化全落地**（#64）：L0 立项四问工具化、L1 本体分层治变（tier 分级审批 + 升格复用证明）、L5 Action 阶梯 Lv 标注 + 自动闭环误报率门（FP<0.5%）。

---

## 1. 六层对照总表

| 层 | 框架要求 | aiPlat 现状（代码实证） | 成熟度 |
|---|---|---|---|
| **L0 战略罗盘** | 立项四问（反复/跨系统/Owner+指标/Action）、MVP 本体 | FDE 诊断闭环是 aiPlat 定位核心（诊断→证据→改进→交付→评分→部署）；**立项四问已工具化**（P2-L0 #64：`four_questions.py` → 0-100 分 + go/conditional/sandbox + MVP tier 建议，端点 `GET/POST /fde/diagnostics/four-questions`） | ⭐⭐⭐⭐ 已工具化 |
| **L1 静态底座** | 六步 ETL、三层分离（稳定核心/可变逻辑/实验边缘）、SWRL、一致性校验 | 本体 TBox YAML + ABox 构建 + 本体学习→OWL + `to_sparql_rules`（`knowledge_ontology.py:919`）+ `graph_inference.add_rule`（推理规则引擎，`graph_inference.py:189`）+ `validate_tbox` 校验；**三层分离已实施**（P2-L1 #64：`OntologyClass.tier` core/logic/edge + 分级审批） | ⭐⭐⭐⭐⭐ 强 |
| **L2 动态感知** | GraphDB(TBox)+Neo4j(ABox)、业务事件流（审批/库存/合同 Kafka/Flink） | GraphIndex（本体图）+ kb_embeddings/wiki（双库对应物）；**业务事件桥已建**（P0-L2：#58，`Action 成功 → BUSINESS_ACTION 事件 + business_event_bridge 即时 GraphIndex 增量更新`，替代定期 ABox 重建） | ⭐⭐⭐ 骨架已建（事件源可扩展） |
| **L3 混合推理** | 路由分流（SPARQL/Pellet/向量 RAG）、生成前约束编译（SWRL→prompt/schema） | `ontology_query_mapper` + `traverse_ontology_graph`（本体→图遍历）+ GraphRAG（真向量）；**约束编译已本体化**（P1-L3 #62：`ontology_constraint_compiler` 编译 AXIOMS/类字段 → 生成前硬规则，`prompt_assembler` opt-in 注入保 prompt cache） | ⭐⭐⭐⭐ 路由强 + 约束已本体化 |
| **L4 双重审计** | EAEV（外部证据对账+反事实扰动）、SIRG（内部推理图对比公理路径） | `hallucination_tracker`（EAEV：claim→证据验证→quality_flag/confidence）+ `decision_trace`（决策溯源）；**反事实扰动已实施**（P1-L4a #62：`counterfactual_perturb` 实体替换→漂移>0.3 判记忆惯性）；**SIRG 已实施**（P1-L4b #63：`sirg_auditor` 推理链 vs 规则链一致性报告） | ⭐⭐⭐⭐ 双审计已闭环 |
| **L5 受控行动+进化** | Action 阶梯（Lv1-4）、FDE 学习回路、Branch/Proposal/Rebase 本体版本、驳回原因反哺 | Action Contract v3 + ApprovalGate + Action 阶梯（强项）+ `versioned_ontology_store`（create_proposal/apply_proposal，`:122/180`）+ `proposal_store.rejected_reason`（驳回原因）；**Lv 标注 + 误报率门已实施**（P2-L5 #64：`ActionLevel` lv1-4 + `compute_closure_gate` FP<0.5%） | ⭐⭐⭐⭐⭐ 强 |

---

## 2. 逐层详析

### L0 战略罗盘（方向盘）—— ⭐⭐⭐⭐ 方法论有 + 已工具化（P2-L0 四问评估）

**框架要求**：立项四问（决策反复发生 / 跨 3+ 系统 / 有 Owner+量化指标 / 可写回 Action）+ MVP 本体分层实施。

**aiPlat 现状**：
- ✅ FDE 诊断→证据映射→覆盖率→改进→交付→评分→对比→基准→目标分解→自主部署→外部发现 是 aiPlat 的核心定位（第 5 层架构）
- ✅ **立项四问已工具化（P2-L0，#64）**：`core/apps/fde/service/four_questions.py`——四问（反复/跨系统/Owner+指标/Action）逐项打分（0-100）加权 → 总分 + go/conditional/sandbox 结论 + MVP 本体 tier 建议；FDE 诊断卡端点 `GET /fde/diagnostics/four-questions`（元信息）+ `POST /fde/diagnostics/four-questions/evaluate`（评估）
- ✅ MVP 本体分层引导：四问输出直接建议 tier（edge=沙盘验证 / logic=MVP 起步 / core=承重墙需架构评审），与 P2-L1 分层语义贯通

**改进建议**：✅ **已实施（#64）**——四问评估步骤已加入 FDE 诊断卡。

### L1 静态知识底座（地图）—— ⭐⭐⭐⭐⭐ 强（P2-L1 三层分离已落地）

**框架要求**：多源采集→NER→概念聚类(is-a)→关系抽取→公理规则编码(SWRL)→一致性校验；三层分离（稳定核心/可变逻辑/实验边缘）。

**aiPlat 现状**：
- ✅ 六步 ETL 对应：DocumentIngestor 分块 → EntityExtractor（9 类实体）→ 本体学习聚类（new_class）→ LLM 层次发现（new_subclass）→ 关系抽取 → `to_sparql_rules` 规则导出
- ✅ `graph_inference.add_rule`（`graph_inference.py:189`）：推理规则引擎（框架"SWRL"的运行时对应物）
- ✅ `validate_tbox`：T-Box 一致性校验（property domain/range 引用 class）
- ✅ **三层分离已实施（P2-L1，#64）**：`OntologyClass.tier`（core=承重墙 / logic=软装 / edge=沙盘，默认 logic 兼容存量）+ `ontology_loader` 解析校验 + `versioned_ontology_store.approve_proposal` 分级审批（core 需架构评审角色 / logic 产品侧 / edge 自服务）+ edge→logic 升格需复用证明（`promotion_proof.reuse_count ≥ 3`）+ `ontology_audit` 按 tier 分组

**改进建议**：✅ **已实施（#64）**——tier 字段 + 变更审计分级已落地。

### L2 动态感知与实例填充（GPS）—— ⭐⭐⭐ 骨架已建（2026-08-19 P0-L2）

**框架要求**：GraphDB（TBox+物化推理）+ Neo4j（ABox 实例）双库；业务事件流（审批进度/库存扣减/合同签署 Kafka/Flink）回答"现在在哪里"。

**aiPlat 现状**：
- ✅ 双库对应物：GraphIndex（本体图/实例）+ kb_embeddings（向量）+ wiki（FTS）
- ✅ **业务事件桥已建（P0-L2，#58）**：`AsyncActionRegistry.execute` 动作成功 → `BUSINESS_ACTION` 事件（observability EventBus 审计）+ `business_event_bridge` 即时增量更新 GraphIndex（`add_entity` 幂等 upsert + last_action/status/actor）——实例数据从"定期重建"升级为"事件驱动即时反映"（实测 `sign_contract` → `contract-1001` 即时创建）
- ⏳ 扩展方向：审批状态/流水线完成等更多业务动作接入桥；外部系统事件（Kafka/Flink 类）需在部署层接

**改进建议（P0）**：✅ **已实施（#58）**——骨架完成，可扩展更多动作源。

### L3 混合推理与生成引擎（大脑）—— ⭐⭐⭐⭐ 路由强 + 约束编译已本体化（P1-L3）

**框架要求**：路由分流（确定事实→Text-to-SPARQL；复杂逻辑→Pellet 推理；开放语义→向量 RAG）；**生成前约束编译**（SWRL/OWL 公理实时编译为 System Prompt 硬规则 / JSON Schema）。

**aiPlat 现状**：
- ✅ 路由：`ontology_query_mapper`（本体映射）+ `traverse_ontology_graph`（图遍历，3 生产调用者）+ GraphRAG（真向量）
- ✅ **约束编译已本体化（P1-L3，#62）**：`ontology_constraint_compiler.compile_ontology_constraints`——本体 AXIOMS description + 类 required_fields → 自然语言硬规则块；`prompt_assembler` opt-in 注入（`meta.inject_ontology_contract` 时编译注入 system prompt，默认不注入保 prompt cache 稳定）
- ✅ 编码契约保留：`coding-contract`（`prompt_loader.py:287`）仍负责代码生成前架构约束注入（与本体公理约束互补）

**改进建议（P1）**：✅ **已实施（#62）**——公理/类字段已编译为生成前硬规则。

### L4 双重可信审计（交规）—— ⭐⭐⭐⭐ 双审计已闭环（P1-L4a 反事实 + P1-L4b SIRG）

**框架要求**：EAEV（外部证据对账：实体抽取→三维度对齐→**反事实扰动**→判幻觉）+ SIRG（内部推理图：捕获语义推理图→对比 OWL 公理路径→违规报告）。

**aiPlat 现状**：
- ✅ EAEV 基础：`hallucination_tracker`（`hallucination_tracker.py:216` `_verify_claim`）——claim 验证 + evidence 引用 + quality_flag（ok/needs_review/low_evidence）+ confidence
- ✅ **反事实扰动已实施（P1-L4a，#62）**：`counterfactual_perturb`——抽取最高频实体 → 替换为无关 token → 同上下文重验 → 置信度漂移 >0.3 且原置信度 >0.6 判定"记忆惯性幻觉"（模型靠预训练记忆硬撑）→ claim.quality_flag=needs_review；evaluate 循环内 best-effort 接入
- ✅ **SIRG 已实施（P1-L4b，#63）**：`sirg_auditor`——`rule_chain_for(conclusion)` 提取本体标准规则链 + `audit_reasoning(实际触发规则, 结论)` 对比缺失/多余规则 → 可解释违规报告（"推理跳过了 N 条规则"）；实际推理链取自可观测执行面（decision_trace/工具调用审计/inference rule_hits），不依赖 LLM 内部表示
- ✅ 决策溯源：`decision_trace`（根因定位）

**改进建议（P1）**：✅ **已实施（#62/#63）**——反事实扰动 + SIRG 推理链审计双闭环。

### L5 受控行动与现场进化（副驾+修路队）—— ⭐⭐⭐⭐⭐ 强（P2-L5 量化门已加）

**框架要求**：Action 阶梯（Lv1 只读→Lv4 自动闭环，逐级真实业务考验）；FDE 学习回路（例外→SWRL/对象升格）；Branch/Proposal/Rebase 本体版本管理；驳回数据反哺（原因标签）。

**aiPlat 现状**：
- ✅ **Action 阶梯 + Lv 标注**：Action Contract v3 + ApprovalGate + Action Registry（aiPlat 强项，企业治理核心）；**P2-L5（#64）**新增 `ActionContractModel.action_level`（`ActionLevel`：lv1_readonly→lv4_auto_close，默认 Lv2 保守）
- ✅ **自动闭环量化门（P2-L5，#64）**：`compute_closure_gate`——Lv4 自动闭环前检查历史误报率（result_status ∈ rejected/corrected/rolled_back/overridden 视为误报），`fp_rate < CLOSURE_FP_RATE_MAX`（0.5%）才允许闭环；超标 → 降级人工确认（走 approval gate）或返回 closure_gated
- ✅ **本体版本管理**：`versioned_ontology_store`（`create_proposal:122` / `list_proposals:143` / `apply_proposal:180`）——框架"Branch/Proposal/Rebase"的 Proposal 骨架；P2-L1 分级审批叠加
- ✅ **驳回原因反哺**：`proposal_store.rejected_reason`（`:57/79`）
- ✅ **FDE 学习回路**：aiPlat 定位即 FDE（例外→技能/规则沉淀，AutoLearner/evolution_runner）

**改进建议**：✅ **已实施（#64）**——Lv 显式标注 + 误报率量化门已落地。

---

## 3. 改进建议汇总（按优先级）

| 优先级 | 差距 | 建议 | 状态 |
|---|---|---|---|
| **P0-L2** | 业务实时事件流缺失（GPS 层） | Action 成功 → EventBus + GraphIndex 增量更新 | ✅ **已实施（#58）** |
| **P1-L3** | 约束编译非本体驱动 | `to_sparql_rules`/ABox 实例约束编译为生成前 Prompt/JSON Schema | ✅ **已实施（#62）**：`ontology_constraint_compiler` + `prompt_assembler` opt-in 注入 |
| **P1-L4a** | EAEV 无反事实扰动 | 反事实扰动模块（替换高置信实体→对齐分数波动→判幻觉） | ✅ **已实施（#62）**：`counterfactual_perturb` 漂移>0.3 判记忆惯性 |
| **P1-L4b** | SIRG 未实现（推理图 vs 公理路径） | `graph_inference` 基础上做推理链 vs 规则链一致性报告 | ✅ **已实施（#63）**：`sirg_auditor` 缺失规则→违规报告 |
| **P2-L1** | 三层分离未显式化 | ontology YAML 加 `tier: core|logic|edge` + 变更审计分级 | ✅ **已实施（#64）**：tier 字段 + 分级审批 + 审计分组 |
| **P2-L0** | 立项四问未工具化 | FDE 诊断卡加四问评估 | ✅ **已实施（#64）**：四问 → 总分 + 结论 + MVP tier |
| **P2-L5** | Action 阶梯量化门未显式 | 阶梯 Lv 标注 + 自动闭环误报率门 | ✅ **已实施（#64）**：ActionLevel + compute_closure_gate |

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

- **改进前**：aiPlat 是"带本体的知识问答系统"——知识管线有空壳（向量/图增强声明未接线）、感知靠定期重建、检索含中文失真、本体靠专家手写、推理无事前约束、审计无反事实/SIRG、治理无分层。
- **改进后**：aiPlat 是"企业级 AI 决策操作系统"——知识全链路真实、业务实时感知、检索语义化、本体可学习可演进、生成前有约束编译、事后有双重审计、行动可治理（tier 分级 + 阶梯量化门）。

### 端到端效果（以"合同续约决策"为例）

| 环节 | 改进前 | 改进后 | 代码实证 |
|---|---|---|---|
| 知识入库 | 向量/图增强是空壳（0 写入者），检索靠 FTS | 摄取 → kb_embeddings（**真语义 384 维**）+ kb_graph + wiki 全链路真实 | #50 / #54 |
| 本体 | 专家手写 YAML，无自动学习 | 文档 → 概念聚类 → is-a 层次 → **OWL/TTL 输出**（可审查、可导入） | #51 / #53 |
| 治理 | 所有类同权、一刀切审批 | **tier 分级**：core 架构评审 / logic 产品侧 / edge 自服务，edge→logic 升格需复用证明 | #64 |
| 立项 | 拍脑袋决定做不做 | **四问评估**：反复/跨系统/Owner+指标/Action → 0-100 分 + MVP tier 建议 | #64 |
| 感知 | 下午 3 点签约，凌晨重建才可见 | **签约即感知**（BUSINESS_ACTION → GraphIndex 即时，实测 `sign_contract` → `contract-1001` 即时创建） | #58 |
| 检索 | 中文相关性失真（完全包含也 0 分） | 中文 bigram 切词 **0 → 0.71** | #49 |
| 推理 | 取块靠 wiki 名义向量；生成前无本体约束 | GraphRAG 实体路由 → **真向量取块** + **约束编译**（生成前注入本体硬规则） | #55 / #62 |
| 审计 | 仅正向证据验证 | **反事实扰动**（漂移>0.3 判记忆惯性）+ **SIRG**（推理链 vs 规则链一致性） | #62 / #63 |
| 行动 | Action 阶梯 + 审批已具备 | **Lv 标注 + 自动闭环误报率门**（FP<0.5% 才闭环）+ 本体 Proposal 版本管理 + 驳回原因反哺 | #64 / 既有强项 |

### 业务价值层（对 CTO / CEO / 业务方的语言）

1. **实时性**：决策数据从"隔夜"到"即时"——风控/续约/库存场景的响应窗口从 **24 小时级 → 秒级**（事件桥）。
2. **可信性**：中文相关性可度量 + 证据验证 + 反事实压力测试 + SIRG 推理合规审计——回答的"相关性"与"推理合规性"从凭感觉变成可审计指标。
3. **可演进性**：本体学习（文档→OWL）+ Proposal 版本管理 + **tier 分层治变**——业务变化以天/周为单位落地，承重墙变更阻断直至架构评审，**不重构核心**。
4. **可治理性**：立项四问把关"值不值得做" + Action 阶梯 + 分级审批 + 误报率量化门——AI 动手有边界、进化有原因标签、自动闭环有数据背书。

### 量化效果（可验证，非口号）

| 指标 | 改进前 | 改进后 |
|---|---|---|
| 知识五要素（数据元/本体/向量/wiki/RAG）真实数据流 | 2 个空壳（kb_embeddings / kb_graph 0 写入者） | **全部真实**（接线 + DDL 补齐） |
| 本体来源 | 仅专家手写 | 专家 + **学习**（4 类建议 → OWL/TTL 文件） |
| 本体变更治理 | 一刀切审批 | **tier 分级**（core 阻断 / logic 产品侧 / edge 自服务 + 升格复用证明） |
| 立项决策 | 拍脑袋 | **四问评分**（0-100 + go/conditional/sandbox） |
| 业务动作 → 本体实例 | 定期全量重建（隔夜） | **事件驱动即时**（秒级） |
| 中文检索相关性 | 0.0（完全包含也失分） | **0.71**（bigram 切词） |
| 向量质量 | hash 占位 / 伪向量 | **真语义 384 维**（embed + GraphRAG 取块） |
| 生成前约束 | 仅编码契约 | **本体公理约束编译**（AXIOMS/类字段 → 硬规则） |
| 审计深度 | 仅正向证据验证 | **反事实 + SIRG 双审计** |
| 自动闭环 | 无量化门槛 | **误报率 <0.5% 才允许 Lv4 闭环** |

---

## 4. 核心结论

1. **六层全覆盖**：aiPlat 无缺失层——本体+推理+审计+Action+进化同时具备，这在四系统对照中是唯一（Claude Code 无引擎无审计、DSH 无企业治理、Hermes 无审计留痕）。
2. **"分层治变"已工程化**：`versioned_ontology_store` 的 Proposal 机制 + `tier` 字段（P2-L1 实施） = 框架"稳定核心/可变逻辑/实验边缘 + Branch/Proposal/Rebase"的完整对应——承重墙变更走版本化 Proposal + 架构评审，沙盘变更自服务且绝不自动升格。
3. **"双向校验"已闭环（原最大改进空间）**：事前约束（L3 本体公理编译 #62）与事后审计（L4 反事实扰动 #62 + SIRG #63）已全部实施——生成前知道红线，生成后可审计推理合规。
4. **"现场进化"是 aiPlat 差异化**：FDE 定位 + AutoLearner + evolution_runner + Proposal 版本管理 + tier 分级审批，已覆盖框架 L5 全部要求并超出。
5. **"决策性价比"已可度量**：L0 立项四问（#64）把"值不值得做一个 AI 决策系统"从拍脑袋变成 0-100 评分 + MVP tier 引导，与 L5 误报率门共同构成"入口把关 + 出口量化"的完整治理闭环。

---

## 5. 验证命令

```bash
# L1 规则引擎
grep -n "def add_rule" aiPlat-core/core/harness/ontology_engine/graph_inference.py  # :189
# L1 SPARQL 导出
grep -n "def to_sparql_rules" aiPlat-core/core/harness/knowledge/knowledge_ontology.py  # :919
# L1 三层分离（tier 字段）
grep -n "normalize_tier" aiPlat-core/core/harness/knowledge/knowledge_ontology.py  # tier 归一化
# L1 tier 分级审批
grep -n "load_tier_approval_roles" aiPlat-core/core/harness/knowledge/versioned_ontology_store.py  # 角色矩阵配置加载
# L0 立项四问
grep -n "def evaluate_four_questions" aiPlat-core/core/apps/fde/service/four_questions.py
# L2 业务事件桥
grep -n "async def publish_business_action" aiPlat-core/core/harness/ontology_engine/business_event_bridge.py
# L3 约束编译
grep -n "def compile_ontology_constraints" aiPlat-core/core/harness/knowledge/ontology_constraint_compiler.py
# L3 约束注入（编码契约）
grep -n "coding-contract" aiPlat-core/core/harness/utils/prompt_loader.py  # :287
# L4 证据验证
grep -n "def _verify_claim" aiPlat-core/core/harness/evaluation/hallucination_tracker.py  # :216
# L4 反事实扰动
grep -n "def counterfactual_perturb" aiPlat-core/core/harness/evaluation/hallucination_tracker.py
# L4 SIRG 推理链审计
grep -n "def audit_reasoning" aiPlat-core/core/harness/ontology_engine/sirg_auditor.py
# L5 本体 Proposal 版本
grep -n "async def create_proposal\|async def apply_proposal" aiPlat-core/core/harness/knowledge/versioned_ontology_store.py  # :122/:180
# L5 Action 阶梯 + 误报率门
grep -n "class ActionLevel" aiPlat-core/core/harness/infrastructure/action_contract.py
grep -n "async def compute_closure_gate" aiPlat-core/core/harness/ontology_engine/action_registry.py
```
