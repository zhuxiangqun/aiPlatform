# aiPlat Phase 状态时间线（从 CLAUDE.md 外迁）

> 本文件汇集各 Phase 的实现状态快照，从 `aiPlat-core/CLAUDE.md` 迁出，使 CLAUDE.md 聚焦耐久治理规则。
> 能力清单见 `AIPLAT_CAPABILITIES.md`；治理规则见 `aiPlat-core/CLAUDE.md`。

last_synced: 2026-07-06

---

### 5.36 本体引擎模块总览（2026-07-04 更新 — 23 个模块）

`core/harness/ontology_engine/` 目录下的模块列表及其职责：

| # | 文件 | 行数 | 职责 |
|---|------|:---:|------|
| 1 | `engine.py` | 536 | **主编排器** — 13步管线 (3Phase并行: Classify→Extract并行→Validate串行) |
| 2 | `class_mapper.py` | 185 | 关键词倒排索引 → T-Box类映射 (零LLM) |
| 3 | `property_extractor.py` | 148 | LLM属性提取 + table_context注入 |
| 4 | `state_machine.py` | 403 | YAML驱动状态机 (3触发器 × 7联动) + compute_indicators |
| 5 | `state_history.py` | 137 | SQLite状态变更审计表 |
| 6 | `graph_index.py` | 710 | GraphIndex + HyperEdge + SQLite持久化 + GraphSnapshot |
| 7 | `graph_traversal.py` | 400 | BFS遍历 (traverse + traverse_multi + ranked_terminals + cache) |
| 8 | `graph_inference.py` | 174 | YAML推理规则 → 传递闭包推断边 |
| 9 | `relation_mapper.py` | 172 | 实例间关系检测 (共现+LLM) |
| 10 | `document_parser.py` | 500 | 5格式解析 (MD/HTML/TXT/PDF/DOCX) + StructuredTable + QAPair |
| 11 | `entity_resolver.py` | 273 | 3层消歧 (strict/lazy双模式) |
| 12 | `traversal_cache.py` | 101 | LRU遍历缓存 + 图突变失效 |
| 13 | `knowledge_synthesis.py` | 194 | 推理链/事实卡/综合结论 → Wiki页面 |
| 14 | `approval.py` | 271 | 本体变更审批工作流 |
| 15 | `cleanup.py` | 130 | 过期实体/关系定时清理 |
| 16 | `data_source.py` | 263 | 外部数据源连接器 (SQL/API/File) |
| 17 | `datasource_status.py` | 161 | 数据源健康状态监控 |
| 18 | `knowledge_gap_detector.py` | 142 | 知识缺口检测 → 自动建议补充 |
| 19 | `rule_designer.py` | 321 | 推理规则可视化设计器 |
| 20 | `rule_prompt.py` | 135 | 规则设计 LLM prompt 模板 |
| 21 | `sharded_graph.py` | 75 | 多域图分片 + 跨域邻居查询 |
| 22 | `triple_scanner.py` | 195 | AGENT.md/SKILL.md → 本体三元组扫描 |
| 23 | `triple_store.py` | 190 | 三元组持久化存储 |
| **总** | | **~6,800** | |

### 5.38 GraphIndex 数据模型

| 类型 | 用途 |
|------|------|
| `GraphNode` | 实体节点 (entity_id, entity_name, class_name, out_edges[], in_edges[]) |
| `GraphEdge` | 二元有向边 (source→target, relation_name, confidence, inferred, embedding) |
| `HyperEdge` | SAG风格超边 (event_id, entity_ids[], context_description, embedding) — 1个event连接N个entity |

**持久化**: SQLite主存 (`graph/{domain}.db`) + JSON回退兼容。

### 5.39 K4 知识治理（2026-06）

| 层 | 能力 | 实现 |
|----|------|------|
| K1 | 推理规则 | `inference_rules` YAML → `GraphInference` |
| K2 | 状态机 | `states` + `transitions` YAML → `StateMachine` |
| K3 | 同义词 | `~/.aiplat/synonyms.yaml` → `expand_query_with_synonyms()` → `search_pages()` |
| K4 | 元数据 | `effective_date`/`expiry_date`/`department`/`owner` in FRONTMATTER_FIELDS + `search_pages()`过滤 |

### 5.43 API 端点更新（2026-07-04 — 813端点）

新增端点:
- `POST /ontology/engine/traverse` — 图遍历
- `POST /ontology/engine/infer` — 图推理
- `POST /ontology/engine/synthesize` — 知识合成
- `POST /ontology/engine/simulate-state` — 状态机模拟
- `GET /ontology/engine/graph-stats/{id}` — 图统计
- `POST /ontology/engine/snapshot/{id}` — 图快照
- `GET /ontology/engine/snapshots/{id}` — 快照列表
- `POST /ontology/engine/snapshot/{id}/restore` — 快照回滚
- `GET /ontology/engine/state-history/{id}` — 状态历史
- `POST /ontology/engine/resolve` — 实体消歧
- `GET /ontology/engine/reviews/{id}` — 复查队列

### 5.59 Palantir 对齐能力总览（2026-06）

| Palantir Ontology 能力 | aiPlat 实现 | 状态 |
|----------------------|-----------|:---:|
| 语义统一 (共享词汇) | YAML 域本体 20类+34关系 + K3同义词 | ✅ |
| 逻辑一致性 (一处定义) | ClassMapper/StateMachine 全来自 YAML | ✅ |
| Action 写回业务系统 | `call_webhook` side_effect + `_fire_webhook` | ✅ |
| 场景推演沙箱 | `simulate-scenarios` 多方案对比 | ✅ |
| SDK 生成 | `GET /ontology/sdk/{domain}?language=python\|typescript` | ✅ |
| 动态本体 (实时响应) | StateMachine + state_history + 时序窗口 + 缓存失效 | ✅ |
| 三层权限 | marking + permissions + field-permissions APIs | ✅ |
| AI 上下文 | MaterialsChatAgent + ReasoningPath + CRAG/HyDE | ✅ |
| 时序特征工程 | `get_entity_window_stats` + `get_transition_rate` | ✅ |

### 5.64 检索鲁棒性四重强化（2026-06）

#### 5.64.1 关联类宽容策略

`MaterialsChatAgent` 本体映射命中 `target_class` 后，自动扩展邻接类（1跳 `related_to` 边）参与检索，避免过度裁剪：

| 条件 | 行为 |
|------|------|
| ontology_class_uri 已设置 | 通过 GraphIndex 查找对应节点，获取最邻近 3 个邻接类 |
| 邻接类存在且不同于 target_class | 追加到候选类列表，逐个执行检索后合并去重 |

**文件**: `materials_chat.py:265-291`

#### 5.64.2 min_wiki_score 计算明确化

`sys_knowledge_retrieve` 中 `min_wiki_score` 的判定基于 `WikiPageRetriever` 内部的 FTS5+embedding 融合得分，而非单一检索器原始分：

| 判定逻辑 | 说明 |
|---------|------|
| `qualified = [wr for wr in wiki_results if wr.get("score", 0) >= min_wiki_score]` | 使用 Wiki 内部融合后的归一化得分 |
| `len(qualified) >= max(1, top_k // 2)` | 足量高质量 Wiki 结果 → 不使用 KB 补充 |

**文件**: `retrieval.py:590-591`

#### 5.64.3 置信度自适应阈值

不同本体类使用不同置信度阈值，替代一刀切 0.6（原为 0.6，现为自适应）：

| 类标签 | 阈值 | 原因 |
|--------|:---:|------|
| AI方法 / AI系统 | 0.7 | 高特异性，需要强匹配 |
| AI概念 | 0.75 | 中等特异性 |
| 业务问题 / 参考资料 | 0.85 | 宽泛类，需高置信度避免误匹配 |
| Wiki 页面 / 知识原子 | 0.6-0.65 | 通用类，更宽松 |
| 船舶项目 / 设备 | 0.65-0.75 | 领域特定 |

**文件**: `ontology_query_mapper.py:49-55,157-160`

#### 5.64.4 Circuit Breaker 熔断器（状态机）

`WikiCircuitBreaker` 三态状态机，Wiki 检索连续失败时打开电路，自动降级 KB：

| 状态 | 行为 |
|------|------|
| CLOSED (正常) | Wiki 请求正常通过 |
| OPEN (熔断) | 跳过 Wiki，直接走 KB |
| HALF_OPEN (探测) | 60s 后允许 1 次探测请求；成功→CLOSED，失败→OPEN |

| 参数 | 默认值 |
|------|:---:|
| failure_threshold (连续失败次数) | 3 |
| recovery_timeout (恢复超时) | 60s |

**文件**: `retrieval.py:（参见 AIPLAT_CAPABILITIES.md 当前计数）-540,576-619`

### 5.80 可观测性标准（Phase 0.2）

| 能力 | 实现 | 环境变量 |
|------|------|---------|
| **Prometheus /metrics** | `prometheus-fastapi-instrumentator` | `AIPLAT_PROMETHEUS_ENABLED=true` |
| **OpenTelemetry 追踪** | `FastAPIInstrumentor` + 自定义 Span | `AIPLAT_OTEL_ENABLED=true` |
| **Grafana 面板** | LLM QPS / latency P95 / error rate / Pipeline 阶段延迟 | 通过 Prometheus 抓取 |

**架构守卫**：`arch_guard_rules.yaml §69.3`

### 5.81 语义缓存（Phase 0.3）

三层缓存系统降低 LLM API 费用 35-50%：

| 层 | 机制 | TTFT |
|:---:|------|:---:|
| **L1 精确匹配** | Redis `md5(query+domain)` | <50ms |
| **L2 语义相似** | embedding cosine ≥ 0.95 | <200ms |
| **L3 穿透** | 正常 RAG Pipeline → 回写缓存 | 正常延迟 |

**失效策略**：知识库更新 → 清空相关 domain 的 L1/L2 缓存。

**集成点**：`materials_chat.py:execute()` 入口处 `semantic_cache.get()` → 命中直接返回。

**架构守卫**：`arch_guard_rules.yaml §69.2`

### 5.82 Agent SDK（Phase 1.1）

独立 Python 包 `aiplat-sdk/`，3 行代码创建 Agent：

```python
from aiplat import Agent
agent = Agent(model="qwen2.5-coder:7b")
result = agent.execute("分析数据")
```

| 级别 | API | 说明 |
|:---:|------|------|
| **L1** | `aiplat.Agent` | 高级封装，对齐 Claude Code Agent SDK |
| **L2** | `aiplat.Pipeline` | 自定义流水线编排 |
| **L3** | `aiplat.harness.ReActLoop` | 直接控制 Harness 执行循环 |

**安装**：`pip install -e aiplat-sdk/`

### 5.83 Sub-Agent FanOut 并行（Phase 1.2）

Map-Reduce 模式并发执行子任务：

```python
from core.apps.agents.parallel_executor import ParallelExecutor
executor = ParallelExecutor(max_concurrency=5)
results = await executor.map_reduce(["任务A", "任务B", "任务C"], agent_factory)
```

- 每个 SubAgent 独立 `asyncio.Task` + 独立 `run_id`
- 异常隔离：单任务失败不影响其他 (`return_exceptions=True`)
- Semaphore 最大并发控制

### 5.84 增强自学习（Phase 2.1）

"AI 草稿 + 人工确认" 模式——兼顾效率和安全：

```
Agent 失败 → AutoLearner.analyze_failure() → SkillDraft
  → SkillSimulator Docker 沙盒预检 (pass ≥ 80%)
  → 管理端待审核队列
  → 管理员审批 → 注册到 SkillRegistry
```

**安全底线**：
- 同一 Agent 连续 3 次低质量 → 自动暂停 24h
- 自学习 Skill 标记 `source=self_learned` + `status=draft`
- 审批通过前不可被 Agent 调用

### 5.85 声明级溯源（Phase 2.2）

`ProvenanceTracker` 实现 Claim-Level Citation：

```python
from core.harness.knowledge.provenance import get_provenance_tracker
tracker = get_provenance_tracker()
citations = tracker.extract_citations(answer, retrieved_context)
```

`ProvenanceScanner` 自动过期扫描：源文档更新 → 标记所有已生成答案为 "⚠️ 可能过期"。

### 5.86 企业消息网关（Phase 2.3）

仅支持 3 个企业渠道（坚守定位）：

| 渠道 | 适配器 | 配置 |
|------|------|------|
| **飞书** | `FeishuAdapter` | `AIPLAT_FEISHU_WEBHOOK` |
| **企业微信** | `WeComAdapter` | `AIPLAT_WECOM_WEBHOOK` |
| **Slack** | `SlackAdapter` | `AIPLAT_SLACK_BOT_TOKEN` |

不做 Signal/WhatsApp/Telegram。

### 5.87 幻觉检测（Phase 3.1）

`HallucinationTracker` 实现 Faithfulness + GraphIndex 验证：

- **NLI 事实核查**：答案声明 × 检索证据 → entailment/contradiction/neutral
- **Faithfulness 指标**：支持声明数 / 总声明数
- **Hallucination Risk**：综合评分 [0,1] → ok / needs_review / low_evidence
- **GraphIndex 加持**：实体对查图边验证（aiPlat 独有）

### 5.88 灰度发布（Phase 3.2）

`SkillRouter` 支持 3 种模式：

| 模式 | 说明 |
|------|------|
| **Canary** | 按 `tenant_id` 或流量百分比分流到新版 |
| **A-B Test** | 双版本对比（success率 + 延迟 + 推荐结论） |
| **Shadow** | 新版静默运行，对比结果但不影响线上 |
| **Auto-Rollback** | error_rate 或 latency_p95 超阈值 → 自动回退到稳定版 |

### 5.89 执行中实时反思（Phase 4.1）

Agent 在单次任务执行中，连续工具调用失败 2 次时，自动触发轻量级 LLM 反思，
修正策略后继续执行，避免直接撞墙失败。

| 配置 | 默认值 | 环境变量 |
|------|:---:|------|
| 启用开关 | true | `AIPLAT_REFLECTOR_ENABLED` |
| 最大反思次数 | 2 | — |
| 触发阈值 | 连续 2 次 tool_call error | — |

**模块**: `core/harness/infrastructure/hooks/on_error_reflector.py`
**架构守卫**: `arch_guard_rules.yaml §71.1`

### 5.90 用户行为隐式反馈（Phase 4.2）

从用户行为中提取隐式反馈信号，自动调整答案置信度和 Provenance 权重。

| 行为 | 信号 | 效果 |
|------|:---:|------|
| 复制答案全文 | +0.3 | 标记正样本 + Provenance +0.1 |
| 选中片段 | +0.15 | 部分正向 |
| 追问 | -0.1 | 前次答案不完整 |
| 重复问题 | -0.2 | 标记负样本 |
| 30s 无操作 | -0.05 | 可能不满意 |

聚合策略: 每 10 条信号批量处理一次。

**模块**: `core/services/implicit_feedback.py` + 前端 `copy` 事件埋点
**架构守卫**: `arch_guard_rules.yaml §71.2`

### 5.91 LoRA 微调自动触发（Phase 4.3）

监听 AutoLearner 审批通过的高质量 Skill（confidence ≥ 0.8），累计 ≥ 100 条时
自动生成 ShareGPT 格式 SFT 数据集，推送管理端通知。

| 配置 | 默认值 | 环境变量 |
|------|:---:|------|
| 触发阈值 | 100 | `AIPLAT_SFT_AUTO_TRIGGER_THRESHOLD` |
| 最低质量 | 0.8 | `AIPLAT_SFT_MIN_QUALITY` |
| 启用开关 | true | `AIPLAT_SFT_ENABLED` |

**模块**: `core/harness/training/auto_trigger.py`
**架构守卫**: `arch_guard_rules.yaml §71.3`

### 5.92 元认知策略建议（Phase 4.4，远期探索）

Meta-Agent 每天分析 AutoLearner 审批历史，自动生成改进策略建议。
只读建议，不修改代码。默认关闭。

检测模式:
- **高频拒绝原因**: 识别 ≥30% 的 Draft 被拒原因 → 建议增预检规则
- **用户质量差异**: 低通过率用户 → 建议检查配置或暂停权限
- **停滞检测**: 7 天无新 Draft → 建议检查 AutoLearner
- **覆盖缺口**: 技能生成集中在单一类别 → 建议丰富多样性

**模块**: `core/harness/meta/__init__.py`
**环境变量**: `AIPLAT_META_AGENT_ENABLED=false` (默认关闭)
**架构守卫**: `arch_guard_rules.yaml §71.4`

### 5.93 经验向量缓存（Phase 5.1）

将 PipelineTrace 执行轨迹 Embedding 后存入向量库，AutoLearner 通过语义相似度检索历史经验，
生成更精准的 SkillDraft。

| 操作 | API |
|------|------|
| 存储经验 | `await cache.store(run_id, summary, label="success")` |
| 检索相似 | `await cache.search(error_description, top_k=3)` |
| 增强 SkillDraft | `context = await cache.enrich_skill_draft(error)` |

**预期收益**: 自学习精准度 +20%
**模块**: `core/harness/learning/experience_vector.py`
**架构守卫**: `arch_guard_rules.yaml §72.1`

### 5.94 多阶段隐空间缓存（Phase 5.2）

LatentStageCache 缓存 RAG Pipeline 各阶段的中间状态向量（查询改写、域路由、检索聚合），
检索时用多级相似度组合匹配。

```
combined_score = α·query_sim + β·domain_sim + γ·retrieval_sim
```

| 配置 | 默认值 | 环境变量 |
|------|:---:|------|
| query 权重 α | 0.4 | `AIPLAT_LATENT_CACHE_ALPHA` |
| domain 权重 β | 0.2 | `AIPLAT_LATENT_CACHE_BETA` |
| retrieval 权重 γ | 0.4 | `AIPLAT_LATENT_CACHE_GAMMA` |

**预期收益**: 缓存命中率 +15%
**模块**: `core/harness/knowledge/semantic_cache.py:LatentStageCache`
**架构守卫**: `arch_guard_rules.yaml §72.2`

### 5.95 Embedding 通信桥（Phase 5.3）

子 Agent 间通过 Embedding 向量传递"核心语义"，替代冗长的 Token 序列。

```
SubAgent_A → encode(长文本) → (向量+简短摘要)
                                ↓
SubAgent_B → decode(向量+摘要) → 注入 prompt 上下文
```

**预期收益**: Token -30~40%
**模块**: `core/apps/agents/parallel_executor.py:EmbeddingBridge`
**架构守卫**: `arch_guard_rules.yaml §72.3`


### 5.96 运行时上下文注入 — RunContext (Phase 10.1, 2026-07)

`RunContext` 桥接静态本体和动态业务状态，解决"同一个故障在不同上下文中有不同语义"的问题。

**核心类**: `core/harness/kernel/types.py:RunContext`

**字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| `entity` | `str` | 实体标识名，如 "注塑机#3" |
| `entity_type` | `str` | 实体类型，如 "设备" / "订单" |
| `situation` | `str` | 自由文本描述当前状态 |
| `priority` | `str` | 业务优先级 — normal / elevated / critical |
| `constraints` | `List[str]` | 约束条件列表 |
| `metadata` | `Dict[str, Any]` | 扩展字段 |

**序列化**: `to_compact()` → ~80 token: `当前设备: 注塑机#3 | 概况: 温度215℃超限 | 优先级: critical | 约束: 备件2件`

**注入位置**: MaterialsChatAgent domain prompt 之后、base role 之前。3 个 LLM 调用点全覆盖。

**数据流**: API payload.run_context → integration.py → context.variables._run_context → _inject_run_context() → system prompt

**改动文件**: `types.py` (+27), `materials_chat.py` (+25), `integration.py` (+3)


### 5.97 GraphIndex → RunContext 自动填充 (Phase 10.2, 2026-07)

无需 API 调用方手动提供上下文时，自动从 GraphIndex 提取实体并填充 RunContext。

**核心函数**: `materials_chat.py:_build_run_context_from_graph()`

**处理流程**: 扫描用户问题中的实体名 → GraphIndex.find_by_name() → get_neighbors(direction="both") → 构建 RunContext(entity/entity_type/situation)

**合并规则** (`_merge_run_context`): entity/type 调用方优先, situation/priority 调用方>实时>graph, constraints 合并去重


### 5.98 DataSource → RunContext 实时数据桥接 (Phase 10.3, 2026-07)

从外部 MES/ERP 系统通过 DataSource API 拉取动态数据填充 RunContext。

**核心函数**: `materials_chat.py:_fetch_realtime_context()`

**配置**: `~/.aiplat/datasources/<name>.yaml`, `mapping.run_context` 段定义 situation_template/priority_path/constraints_path 映射

**降级**: 无 DataSource 时返回 None → 静默降级到 GraphIndex

**合并链**: `caller > realtime_datasource > graph_index`


### 5.99 OperatorAgent — 运维决策智能体 (Phase 10.4, 2026-07)

企业运维决策支持 Agent，回答"现在怎么办"而非"是什么"。

**核心类**: `core/apps/agents/operator_agent.py:OperatorAgent(BaseAgent)`

**与 MaterialsChatAgent 的分工**: 知识查询/原因分析 → MaterialsChatAgent, 决策支持/影响评估/行动建议 → OperatorAgent

**输出**: 结构化 JSON — severity + impact(affected_entities/downtime/risk) + can_continue + recommended_actions[] + confidence

**决策框架**: ①评估严重程度 → ②评估影响范围 → ③给出可执行建议(含target+urgency) → ④二元判断

**Prompt**: `operator-decision` (prompt_loader.py)

**改动文件**: `operator_agent.py` (+145), `base.py` (+2), `prompt_loader.py` (+50), `AGENT.md` (+55)


### 5.100 Wiki 内容质量监控 (Gap 2, 2026-07)

LLM 驱动的 Wiki 页面内容保真度检查——对比 Wiki 页面与其 `source_articles` 原始文档，评估信息完整性、准确性和综合质量。

**核心模块**: `core/harness/knowledge/wiki_quality_monitor.py` (319 行)

**3 维度评估**:
| 维度 | 含义 | 检测方式 |
|------|------|---------|
| completeness | 原始文档的关键信息在 Wiki 页面中保留了多少 | LLM 对比评估 |
| accuracy | Wiki 页面是否有与原文矛盾的陈述 | LLM 事实核查 |
| overall | completeness × 0.6 + accuracy × 0.4 | 加权计算 |

**分段抽样**: 源文档 > 3000 字符时取前/中/后各 1000 字符，均匀覆盖

**触发方式**: 按需 API (`force=true`) / 事件驱动 (≥50 次 wiki 变更) / 定时 (每天 3AM)

**存储**: `wiki_quality_alerts` + `wiki_quality_trends` 双表，浮点评分支持趋势追踪

**集成**: `_inc_change_counter` 钩子 / HealthCheckRegistry / `GET /diagnostics/wiki-quality`

**改动文件**: `wiki_quality_monitor.py` (+319), `wiki_engine.py` (+15), `diagnostics.py` (+35), `server.py` (+6)


### 5.101 主动综合 — Active Synthesis (Gap 1, 2026-07)

STORM 式主动知识生成——从被动响应升级为主动发现知识缺口 → 研究 → 起草 Wiki 页面 → 提交 Proposal。

**核心模块**: `core/harness/knowledge/active_synthesis.py` (310 行)

**5 步管道**:
1. `detect_synthesis_gaps()` — 复用 knowledge_gap_detector，优先 no_instance 缺口
2. `generate_research_questions()` — LLM 生成 3-5 个聚焦研究问题，API key 缺失时优雅降级
3. `retrieve_source_documents()` — 从 kb_elements + wiki search 获取原始资料
4. `synthesize_wiki_page()` — LLM 起草含 title/body/tags/confidence 的 Markdown 页面
5. `submit_as_proposal()` — 封装为 save_proposal() 提交人工审核

**质量门控**: min_confidence 阈值(默认 0.3) / 源文档存在性检查 / LLM 不可用时回退问题

**触发**: POST /wiki/active-synthesis / 事件驱动 (via _inc_change_counter) / `AIPLAT_ACTIVE_SYNTHESIS_ENABLED=false` 默认关闭

**改动文件**: `active_synthesis.py` (+310), `wiki_engine.py` (+5), `wiki.py` (+30)


### 5.102 答案生成管道 (2026-07)

统一的 LLM 调用 + 答案提取，消除 MaterialsChatAgent 中 3 处重复的答案生成代码。

**核心模块**: `core/harness/generation/answer_generator.py`

**函数**:
| 函数 | 用途 |
|------|------|
| `generate_answer()` | 非流式 sys_llm_generate + 答案验证 + trace 信息返回 |
| `generate_stream_answer()` | 流式 sys_llm_generate_stream + chunk 收集 + queue 推送 |
| `build_rag_user_message()` | RAG 用户消息构建 (可自定义模板) |

**改动文件**: `answer_generator.py` (+108), `materials_chat.py` 3 处调用点替换


### 5.103 Action 闭环桥接 (2026-07)

OperatorAgent 决策 JSON → Action Type 匹配 → webhook 通知 → 外部系统执行。

**核心模块**: `core/harness/actions/action_bridge.py`

**函数**: `execute_decision_actions(decision, context, webhook_url)` — 遍历 recommended_actions, 构建 webhook payload, 异步 POST, 返回执行结果列表

**OperatorAgent 集成**: 决策生成后自动调用 action_bridge, metadata 记录 actions_fired + action_results

**改动文件**: `action_bridge.py` (+106), `operator_agent.py` (+15)


### 5.104 本体感知路由 (Phase 11.1, 2026-07)

EngineRouter 集成本体感知——根据查询内容的**本体拓扑复杂度**动态选择引擎，取代硬编码规则。

**核心函数**: `core/harness/execution/router.py:_ontology_routing_hint()`

**两遍式算法**:
1. Direct entity name substring matching (space-normalized) → `GraphIndex.find_by_name()` → count neighbors
2. Fallback: `map_query_to_ontology()` T-Box class matching

**路由决策**: 匹配实体的邻居总数 ≥ 3 → `graph` engine (关系密集型查询), 否则回退默认

**插入位置**: EngineRouter `route_agent()` 规则 4（短消息→quick）和规则 5（默认→loop）之间

**环境变量**: `AIPLAT_ENABLE_ONTOLOGY_ROUTING=true`, `AIPLAT_ONTOLOGY_ROUTING_MIN_NEIGHBORS=3`

**改动文件**: `router.py` (+45)


### 5.105 SemanticGate — 语义合规门控 (Phase 11.2, 2026-07)

Post-generation 语义合规验证——用 YAML 本体验证 Agent 输出中的实体、数值、关系是否在定义的语义空间内。

**核心模块**: `core/harness/infrastructure/gates/semantic_gate.py` (230 行)

**三层验证**:
| 层 | 检查内容 | 验证方式 |
|:--:|------|------|
| 1 | Entity 存在性 | `GraphIndex.find_by_name()` — 实体名是否在图中 |
| 2 | Value 值域 | `confidence` 等数值字段是否在 [0,1] 范围内 |
| 3 | Relation 合规 | block 模式下检查 action 名是否映射到 `object_properties` |

**三种模式**: warn (默认, 标记但放行) / audit (日志记录, 不改变 status) / block (拒绝标记)

**与已有 Gate 正交**: PolicyGate(权限) / ApprovalGate(审批) / TraceGate(追踪) / SemanticGate(语义)

**集成**: OperatorAgent `_execute_impl()` 中 `_parse_decision()` 之后调用

**改动文件**: `semantic_gate.py` (+230), `operator_agent.py` (+17)


### 5.106 CrossValidationGate — 跨域验证 (Phase 11.3, 远期)

设备↔工艺↔质量三层联动约束验证。框架占位，当 YAML 本体中跨域 `object_properties` 连接数 ≥ 50 时激活。

**核心模块**: `core/harness/infrastructure/gates/cross_validation_gate.py` (90 行)

**激活条件**: `CrossValidationGate.is_ready()` — 检查 `~/.aiplat/ontologies/*.yaml` 中 `domain` + `range` 的 `object_properties` 数量

**改动文件**: `cross_validation_gate.py` (+90)


### 5.108 复杂度感知模型选择 (Phase 12.1, 2026-07)

将 `llm_profile.yaml` 中已定义的 `model_capabilities.routing_rules.min/max_complexity` 接入 `ModelManager.select_by_purpose()` 评分循环。

**核心改动**: `ModelManager.select_by_purpose(complexity="simple"|"medium"|"complex")`

**复杂度映射**: simple→1, medium→2, complex→4，与 `routing_rules` 的 0-5 范围对齐

**降级**: 无 `routing_rules` 的模型默认 `min=0, max=5`（不受限）

**改动文件**: `manager.py` (+10), `model_injection.py` (+20)


### 5.109 会话模型覆盖 — /model 命令 (Phase 13, 2026-07)

允许运行时覆盖模型选择，等效于 Hermes 的 `/model` CLI 命令。

**API**: `POST /api/core/model-override` — `{"model_name": "deepseek-v4-pro"}` 设置，`{"model_name": ""}` 清除

**实现**: `model_injection.py:_get_session_model_override()`，在 `best_model_for_purpose()` Step 0.5 检查，优先级高于环境变量和层级路由

**改动文件**: `model_injection.py` (+20), `adapters.py` (+20)


---

