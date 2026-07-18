# aiPlat — 三层知识系统

> **aiPlat 不是一个功能列表，而是一个会持续生长的知识系统。**

## 系统架构：三层 + 三循环

### 三层结构

| 层级 | 作用 | 实现 |
|:---|:---|:---|
| **Raw Sources（原始资料层）** | 论文、报告、合同、网页、传感器数据——只读、可追溯，是事实来源 | `DataSource` 抽象层（SQL/API/File） + `DocumentParser` + 13 步 `OntologyEngine` 管道 |
| **Wiki（知识层）** | 实体页、概念页、关系页、主题综述——LLM 持续编译，通过链接和引用形成知识网络 | `GraphIndex` + `KnowledgeSynthesizer` → Markdown Wiki + `vectors.json` 向量缓存 + FTS5 全文索引 |
| 诊断模型层级 | `management/api/diagnostics.py` | ✅ | `GET /model-tier` — 模型层级路由状态 | 2026-07-18 |
| **Schema（规则层）** | 域本体（YAML）、命名规范、更新流程——让知识库不会失控 | `ontology_loader.py` → `OntologyDomain` + `KnowledgeValidator`（6 种 axiom 验证） + `AGENTS.md` |

### 三个持续循环

| 循环 | 动作 | 实现 |
|:---|:---|:---|
| **Ingest（摄入循环）** | 新资料进入 → 自动提取实体 → 生成 Wiki → 更新关联页面 → 向量化 | 13 步管道（`ClassMapper` → `PropertyExtractor` → `RelationMapper` → `GraphIndex` → `KnowledgeSynthesizer` → Wiki → Vector） |
| **Query（查询循环）** | 多 Agent 从 Wiki + Graph + Vector 三路检索 → CRAG 三级回退 → 回答带来源 → 在线验证 | `DomainRouter`（3 层级联） + `sys_knowledge_retrieve`（RRF 融合） + `MaterialsChatAgent`（Self-RAG） + `HallucinationTracker` |
| **Lint（自检循环）** | 在线验证边一致性 → 离线检查过期/矛盾/孤立/无来源 → 发现问题自动触发增量更新 | `sys_graph_validate`（在线） + `KnowledgeValidator`（离线） + `EvolutionEngine`（夜间） + Lint-to-Ingest 回路 |

### 核心原则

> 代码即真相。每个条目必须有可验证的代码位置。
> 更新：任何能力变更时同步更新本文档。
> 评分：98/100（2026-07-13 — 543✅）

---

## 更新规则

1. **新增能力**：在对应子系统表格加一行，标注 ✅ + 代码位置
2. **废弃能力**：改标记为 ⚠️ deprecated + 日期
3. **能力增强**：更新"说明"列
4. **自检**：`grep -rn "代码位置" aiPlat-core/` 确认文件存在
5. **同步更新统计表**：能力数与 ✅ 数必须一致
6. **通知下游文档**：若数字变更，在本文件统计表更新后，检查以下引用位置是否过时：
   - `AIPLAT_ROADMAP.md` 头部引用行 (384→400 时需同步)
   - CLI 启动 Banner 中的能力数字

---

## 一、Harness 执行引擎

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| debate | `harness/execution/debate.py` | ✅ | 自动同步 | 已合入 |
| conditional | `harness/execution/conditional.py` | ✅ | 自动同步 | 已合入 |
| stage_runner | `harness/execution/langgraph/stage_runner.py` | ✅ | 自动同步 | 已合入 |
| verification | `harness/execution/verification.py` | ✅ | 自动同步 | 已合入 |
| event_loop | `harness/execution/event_loop.py` | ✅ | 自动同步 | 已合入 |
| quick_engine | `harness/execution/engines/quick_engine.py` | ✅ | 自动同步 | 已合入 |
| graph_engine | `harness/execution/engines/graph_engine.py` | ✅ | 自动同步 | 已合入 |
| plan_engine | `harness/execution/engines/plan_engine.py` | ✅ | 自动同步 | 已合入 |
| team_planner | `harness/execution/team_planner.py` | ✅ | 自动同步 | 已合入 |
| state_mgr | `harness/execution/loop/state_mgr.py` | ✅ | 自动同步 | 已合入 |
| graph_injector | `harness/execution/loop/graph_injector.py` | ✅ | 自动同步 | 已合入 |
| tri_agent | `harness/execution/langgraph/graphs/tri_agent.py` | ✅ | 自动同步 | 已合入 |
| target_continuity | `harness/execution/loop/target_continuity.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| ReAct 执行循环 | `harness/interfaces/loop.py:292` | ✅ | Reason→Act→Observe，集成 Hook/压缩/记忆 | 已合入 |
| Plan-Execute 循环 | `harness/execution/loop/_facade.py` | ✅ | 先规划后执行模式 | 已合入 |
| 20 Hook 阶段 | `harness/infrastructure/hooks/hook_manager.py:15` | ✅ | PRE/POST_LOOP, REASONING, ACT, OBSERVE, TOOL_USE, SKILL_USE, STOP, CONTRACT_CHECK, APPROVAL 等 | 已合入 |
| Pipeline 引擎 | `harness/execution/pipeline_engine.py:162` | ✅ | 多阶段调度、HITL 暂停/恢复、重试、snapshot | 已合入 |
| LangGraph 编排层 | `harness/execution/langgraph/core.py:54` | ✅ | 图节点拓扑、条件边路由、checkpoint | 已合入 |
| 8 种图构建 | `harness/execution/langgraph/graphs/` | ✅ | Pipeline/ReAct/PlanExecute/MultiAgent/TriAgent/Reflection | 已合入 |
| EngineRouter 回退链 | `harness/execution/router.py` | ✅ | graph→loop→quick 三引擎 | 已合入 |
| Token 预算管理 | `harness/execution/loop/_facade.py:214` | ✅ | 总预算 100K，推理预算 60K，80%阈值预警 | 已合入 |
| 上下文压缩（5级） | `harness/memory/compression.py:40` | ✅ | NORMAL→WARNING→REPLACE→PRUNE→AGGRESSIVE→EMERGENCY | 已合入 |
| 工具输出预算帽 | `harness/memory/compression.py:230` | ✅ | >2000字→占位符+后台LLM摘要(2026-07-06修复adapter API,原chat_complete/model_name为死代码),热路径零阻塞 | 已合入 |
| 对话级 LLM 语义摘要 | `harness/memory/compression.py:_llm_summarize_conversation` | ✅ | AGGRESSIVE/EMERGENCY 级对话压缩为 4 类结构化摘要(目标/结论/工具/待办)，超时3s优雅降级 | 2026-07-06 |
| 失败分类 | `harness/execution/failure_classifier.py` | ✅ | budget_exhausted / stagnation / token_budget | 已合入 |
| 收敛检测 | `harness/coordination/detector/convergence.py` | ✅ | 多 Agent 投票收敛 | 已合入 |
| Pipeline Sandbox | `harness/execution/pipeline_sandbox.py` | ✅ | 流水线沙箱执行 | 已合入 |
| PatternCache | `harness/execution/pattern_cache.py` | ✅ | MD5执行路径晶体化，重复管道模式跳过LLM | 已合入 |
| LangGraph Checkpoint/Resume | `harness/execution/langgraph/core.py:217` | ✅ | 图状态checkpoint持久化 + 任意节点crash-safe恢复 | 已合入 |
| EmbeddingBridge | `apps/agents/parallel_executor.py:210` | ✅ | 嵌入向量压缩，子Agent间高效通信 | 已合入 |
| 跨阶段回退 | `schemas_builder.py:313-315` + `harness/execution/pipeline_engine.py:2855` | ✅ | `rollback_on_reject` 自动回退到上游阶段重写（委托+对抗模式） | 已合入 |
| Prompt Caching | `harness/utils/prompt_caching.py` | ✅ | system_and_N 缓存策略，system + 末尾N消息标记cache_control | 已合入 |
| Log Redaction | `harness/utils/redaction.py` | ✅ | RedactingFormatter 全局日志脱敏 | 已合入 |
| Decorrelated Jitter | `harness/infrastructure/gates/resilience_gate.py` | ✅ | golden-ratio hash退避抖动，避免惊群效应 | 已合入 |

---

## 二、记忆子系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| migrate_semantic | `harness/memory/migrate_semantic.py` | ✅ | 自动同步 | 已合入 |
| shared_pool | `harness/memory/shared_pool.py` | ✅ | 自动同步 | 已合入 |
| gossip_protocol | `harness/memory/gossip_protocol.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| 四层记忆架构 | `harness/memory/manager.py` | ✅ | Working(Hot) → Episodic(Warm) → Semantic(Cold) → TaskSkills(External) | 已合入 |
| WorkingMemory | `harness/memory/working.py:22` | ✅ | deque滑动窗口，30K token，20条消息 | 已合入 |
| EpisodicMemory | `harness/memory/episodic.py:24` | ✅ | 会话摘要 + LLM预评分 | 已合入 |
| SemanticMemory | `harness/memory/semantic.py:28` | ✅ | SQLite + FTS5 + 向量存储 | 已合入 |
| LongTermMemory | `harness/memory/long_term.py:137` | ✅ | 关键词索引，TTL 30天 | 已合入 |
| ShortTermMemory | `harness/memory/short_term.py` | ✅ | deque 会话级，TTL 1h | 已合入 |
| TaskSkills (L4) | `harness/memory/manager.py` | ✅ | 流水线晶体化，pass_rate≥85% 自动注册 | 已合入 |
| ProfileBuilder | `harness/memory/profile_builder.py` | ✅ | 用户画像提取，原地更新 | 已合入 |
| SystemReminders | `harness/memory/reminders.py:33` | ✅ | 事件驱动提醒，user-role 注入 | 已合入 |
| SharedMemory | `harness/memory/shared_memory.py` | ✅ | 跨实例共享，置信度去重 | 已合入 |
| SessionManager | `harness/memory/session.py` | ✅ | 会话 CRUD，自动清理 | 已合入 |
| 语义记忆动态续期 | `harness/memory/semantic.py` | ✅ | search() 命中自动续期 expires_at | 已合入 |
| 语义记忆软删除 | `harness/memory/semantic.py` | ✅ | is_deleted=1 + get_deleted() 可恢复 | 已合入 |
| 语义记忆过期清理 | `harness/memory/semantic.py` | ✅ | expired AND access_count<3 → 软删除 | 已合入 |
| 投毒防御字段 | `harness/memory/base.py:39` | ✅ | source_tag + trust_weight + provenance | 已合入 |
| Episodic 预评分 | `harness/memory/episodic.py:55` | ✅ | 写入时后台 LLM 打分，压缩时零延迟 | 已合入 |
| 关键决策永保 | `harness/memory/episodic.py:124` | ✅ | critical_episodes >0.8分，永不参与常规压缩 | 已合入 |
| MemoryProvider (可插拔ABC) | `harness/memory/providers.py` | ✅ | SQLite/Redis/Postgres/Memory 可插拔后端 + 工厂模式 | 已合入 |
| 物理分区存储 | `harness/memory/semantic.py` + `migrate_semantic.py` | ✅ | per-tenant SQLite文件 (memory_semantic_{tid}.sqlite3) + 存量迁移 | Phase 18.4 |
| 检索预算机制 | `harness/memory/manager.py` | ✅ | build_context(retrieval_budget=): full→minimal→working_only 3级 | Phase 18.1 |
| 计划性遗忘 | `harness/memory/episodic.py` | ✅ | 同topic 2x降权→3x归档(status=archived) + 索引比较(非is引用) | Phase 18.5 |
| 结构化压缩 | `harness/memory/compression.py` | ✅ | LLM工具输出→JSON(completed/pending/preference) + 自由文本回退 | Phase 18.3 |
| 统一知识库健康仪表盘 | `api/routers/diagnostics.py` | ✅ | 6模块聚合+5维成熟度评分(L0-L5)+Markdown中文报告(四步框架语境) | Phase 19 |
| 通用推理链审计框架 | `harness/infrastructure/gates/audit_trail_gate.py` + `harness/ontology_engine/audit_rules.py` | ✅ | 域无关+6操作符引擎+证据指纹锁存+parent_step_id因果追溯 | Phase 20 |
| Prompt迭代优化编排器 | `harness/optimization/prompt_optimizer.py` | ✅ | Champion-challenger自循环+5零件串联(ReActLoop+DarwinArena+prompt_optimize+PipelineEngine+EvolutionRunner) | Phase 21 |
| 关键决策人工确认 | `apps/agents/operator_agent.py` + `api/routers/agents.py` | ✅ | 3道防线(L1静默/L2确认/L3全量)+审批approve/reject+超时自动拒绝 | Phase 22 |
| 数据血缘追溯 | `api/routers/diagnostics.py` | ✅ | 5模块只读聚合(sources→processing→model→quality),零新表零新模块 | Phase 23 |
| Memory OS 记忆治理 | `semantic.py` + `episodic.py` + `integration.py` | ✅ | 事实矛盾检测+Episodic TTL清理+检索反馈闭环+MemoryOSAgent独立实体 | Phase 23.1-23.4 |

---

## 三、知识引擎（本体）

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| knowledge_gap_detector | `harness/ontology_engine/knowledge_gap_detector.py` | ✅ | 自动同步 | 已合入 |
| graph_importer | `harness/ontology_engine/graph_importer.py` | ✅ | 自动同步 | 已合入 |
| audit_rules | `harness/ontology_engine/audit_rules.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| 13步本体管线 | `harness/ontology_engine/engine.py:94` | ✅ | 3Phase: Classify→Extract并行→Validate串行 | 已合入 |
| ClassMapper（零LLM） | `harness/ontology_engine/class_mapper.py:18` | ✅ | 关键词倒排索引 → T-Box 类映射 | 已合入 |
| PropertyExtractor | `harness/ontology_engine/property_extractor.py:19` | ✅ | LLM属性提取 + table_context注入（并行） | 已合入 |
| StateMachine | `harness/ontology_engine/state_machine.py:113` | ✅ | YAML驱动，3触发器×7联动 | 已合入 |
| StateHistory | `harness/ontology_engine/state_history.py` | ✅ | SQLite 状态变更审计表 | 已合入 |
| GraphIndex | `harness/ontology_engine/graph_index.py:68` | ✅ | 有向图 + HyperEdge (SAG风格) | 已合入 |
| GraphTraversal | `harness/ontology_engine/graph_traversal.py:88` | ✅ | BFS遍历 + traverse_multi + ranked_terminals | 已合入 |
| GraphInference | `harness/ontology_engine/graph_inference.py:47` | ✅ | YAML推理规则 → 传递闭包推断边 | 已合入 |
| KnowledgeSynthesizer | `harness/ontology_engine/knowledge_synthesis.py:37` | ✅ | 推理链/事实卡/综合结论 → Wiki页面 | 已合入 |
| EntityResolver | `harness/ontology_engine/entity_resolver.py` | ✅ | strict(3层) / lazy(仅同源) 双模式 | 已合入 |
| DocumentParser | `harness/ontology_engine/document_parser.py` | ✅ | MD/HTML/TXT/PDF/DOCX 5格式 + 视频/音频 | 已合入 |
| Graph Snapshot | `harness/ontology_engine/graph_index.py:631` | ✅ | 版本化图快照 + restore + compare | 已合入 |
| 域本体 YAML | `~/.aiplat/ontologies/` | ✅ | 20+类，34+关系，K1-K4 知识治理 | 已合入 |
| 数据源连接器 | `harness/ontology_engine/data_source.py` | ✅ | SQL/API/File → 本体实例映射 | 已合入 |
| Webhook 写回 | `harness/ontology_engine/engine.py:294` | ✅ | state transition → call_webhook | 已合入 |
| 场景推演沙箱 | API: simulate-scenarios | ✅ | 多方案对比推演 | 已合入 |
| ShardedGraphIndex | `harness/ontology_engine/sharded_graph.py` | ✅ | 跨域分片图索引 | 已合入 |
| 跨域本体桥接 | `harness/ontology_engine/triple_store.py` + `harness/ontology_engine/triple_scanner.py` | ✅ | 统一三元组存储 + BFS多跳遍历 + 5数据源自动扫描 + 3 API端点 | 已合入 |
| 审批工作流引擎 | `harness/ontology_engine/approval.py` | ✅ | submit/approve/reject/changes + 超时升级 + 告警通道 | 已合入 |
| Interface 原语 (多态抽象) | `harness/knowledge/ontology_loader.py` | ✅ | 本体Interface定义 + implements声明 + get_entities_by_interface()查询 | 已合入 |
| SQL Ontology Bridge | `harness/knowledge/sql_ontology.py` | ✅ | 三层架构(物理→语义→应用) + concept→SQL自动翻译 + virtual-first零摄取 | 已合入 |
| RunContext 运行时上下文 | `harness/kernel/types.py` | ✅ | entity/type/situation/priority/constraints + to_compact()序列化 | Phase 10.1 |
| GraphIndex → RunContext 自动填充 | `apps/agents/materials_chat.py` | ✅ | 实体名提取→GraphIndex遍历→RunContext自动构建 | Phase 10.2 |
| DataSource → RunContext 实时桥接 | `apps/agents/materials_chat.py` + YAML | ✅ | DataSourceRegistry查询→API响应→RunContext字段映射+优雅降级 | Phase 10.3 |
| RunContext 三层合并 | `apps/agents/materials_chat.py` | ✅ | caller>realtime>graph优先级规则 + constraints合并去重 | Phase 10.2 |
| 主动综合 (Active Synthesis) | `harness/knowledge/active_synthesis.py` | ✅ | STORM式5步管道: detect_gaps→research_questions→retrieve→synthesize→proposal | 缺口一 |
| Wiki 内容质量监控 | `harness/knowledge/wiki_quality_monitor.py` | ✅ | LLM评估Wiki页面vs原始文档保真度(completeness/accuracy/overall) | 缺口二 |
| 文档新鲜度警告 | `harness/knowledge/wiki_engine.py` | ✅ | 过期文档(>30天)在检索返回时自动追加交互式警告前缀(所有Agent受益) | Phase 18.2 |
| 跨域语义类比发现 | `harness/knowledge/ontology_query_mapper.py:392` | ✅ | 输入概念名→遍历所有域本体→嵌入相似度匹配→返回跨域类比类名+关键属性(HMESI Step 1) | 2026-07-11 |
| 跨阶段一致性门控 | `harness/knowledge/consistency_gate.py` | ✅ | FDE报告后处理：5条规则扫描§1-§7矛盾(数据低推大模型/私有推SaaS/信创推非国产/POC过大等) | 2026-07-11 |
| AI方案原型库 | `~/.aiplat/ontologies/ai-solution.yaml` + `apps/skills/registry.py:1712-1750` | ✅ | 12类标准化AI方案原型(含数据成熟度/成本/周期/部署/信创约束)→§6推荐时自动注入约束规则 | 2026-07-11 |
| FDE图查询接线 | `apps/skills/registry.py` | ✅ | 诊断前查询域GraphIndex→traverse痛点头实体→注入图谱遍历路径→§1来源列引用图谱关系 | 2026-07-11 |
| FDE推理验证接线 | `apps/skills/registry.py` | ✅ | 诊断后运行GraphInference.infer()→检查推理规则与AI机会匹配度→不匹配降置信度标注 | 2026-07-11 |
| FDE图谱回写接线 | `apps/skills/registry.py` | ✅ | 诊断完成后自动注册DiagnosisSubject实体+has_opportunity关系→下一次诊断可遍历跨报告关联 | 2026-07-11 |
| FDE交付跟踪本体 | `~/.aiplat/ontologies/fde-delivery.yaml` + `apps/skills/registry.py:1789-1825,1979-2025` | ✅ | DiagnosisSession+DeliveryAction类定义→诊断后自动创建跟踪实例→下次诊断注入交付率统计(§4.6ROI数据驱动) | 2026-07-11 |
| FDE追问端点 | `platform/apps/fde/api/fde.py` + `apps/skills/registry.py:1896-1914` | ✅ | POST /fde/ask — 基于诊断上下文回答后续问题，复用域图谱+历史+方案原型全链路(HMESI B0) | 2026-07-11 |
| FDE证据等级映射 | `apps/skills/registry.py:2053-2076` | ✅ | 诊断报告返回时附加evidence_map数组(每条§1结论的证据等级+来源)→前端可直接渲染颜色标签(HMESI C0) | 2026-07-11 |
| FDE交付反馈API | `platform/apps/fde/api/fde.py` | ✅ | POST /fde/delivery/feedback — 标记Session+Action状态→更新交付率统计→触发§4.6ROI重新计算(HMESI D) | 2026-07-11 |
| FDE诊断自优化 | `apps/skills/registry.py:1827-1863` | ✅ | 基于历史交付率(≥60%/30-60%/<30%)自动调整§1置信度标注策略+§6方案推荐排序(HMESI E) | 2026-07-11 |
| FDE多角色模拟 | `apps/skills/registry.py:1865-1881` | ✅ | 生成前注入CIO/开发者/终端用户三视角采纳风险评估表→§7标注各角色风险信号+降级规则(HMESI F) | 2026-07-11 |
| FDE知识缺口检测 | `apps/skills/registry.py:2089-2132` | ✅ | 诊断后对比§1AI机会与域本体类+方案原型标签→无匹配标记为knowledge_gaps→反馈域本体扩展(HMESI G) | 2026-07-11 |
| FDE健康检查 | `platform/apps/fde/api/fde.py:1772-1879` | ✅ | GET /fde/health — 5维组件状态(域注册/图索引/交付跟踪/本体YAML/模型可用性)+自动降级标记 | 2026-07-11 |
| FDE完整性验证 | `platform/apps/fde/api/fde.py:1882-1960` | ✅ | GET /fde/validate — 8项E2E连通测试(域路由/图谱/交付/Ontology/一致性门/跨域类比)一次性全检 | 2026-07-11 |
| FDE会话历史 | `platform/apps/fde/api/fde.py:1975-2060` | ✅ | GET /fde/sessions — 列表查询历史诊断会话(按行业/公司/状态过滤)→含交付行动数+时间线 | 2026-07-11 |
| FDE行业基准 | `platform/apps/fde/api/fde.py:2068-2145` | ✅ | GET /fde/benchmark — 跨行业聚合统计(会话数/交付率/TOP推荐)+per-industry breakdown | 2026-07-11 |
| FDE会话详情 | `platform/apps/fde/api/fde.py:2304-2428` + `apps/skills/registry.py:2154-2200` | ✅ | GET /fde/sessions/{id} — 聚合单次诊断全视图(evidence_map+knowledge_gaps+交付时间线+关联会话+证据统计) | 2026-07-11 |
| 关系类型约束 | `ontology_engine/graph_index.py:160-210` | ✅ | add_relation()增加domain/range校验→从域YAML object_properties读取约束→违规降置信度0.3(N) | 2026-07-11 |
| 证据实体绑定 | `~/.aiplat/ontologies/fde-delivery.yaml` + `apps/skills/registry.py:2212-2225` | ✅ | Evidence实体类型+has_evidence关系→诊断回写时每条§1结论创建证据节点(O) | 2026-07-11 |
| 实体归一 | `ontology_engine/entity_resolver.py:71-148` | ✅ | normalize_term()同域强归一(去后缀/全角转半角)+build_alias_index跨域弱关联(P) | 2026-07-11 |
| Schema校验 | `ontology_engine/graph_index.py:138-158,694-714` | ✅ | add_entity()校验class_name∈域YAML已知类→未知类WARNING日志(Q) | 2026-07-11 |
| 业务术语字典 | `~/.aiplat/ontologies/enterprise-terms.yaml` + `apps/skills/registry.py:1882-1896` | ✅ | Term实体类(名称+定义+域+本体类映射)+诊断时注入术语锚点(R) | 2026-07-11 |
| 术语自播种 | `apps/skills/registry.py:2150-2165` | ✅ | 知识缺口检测后自动创建Term桩→随诊断次数增加术语字典自我丰富(S) | 2026-07-11 |
| 数字员工角色匹配 | `apps/skills/registry.py:1898-1927` | ✅ | §6方案推荐时自动匹配数字员工角色(合规审查/关系挖掘/知识顾问等9类)→报告从技术方案升级为角色实体(Y) | 2026-07-11 |
| 跨系统数据桥接 | `platform/apps/fde/api/fde.py:2930-2988` | ✅ | POST /fde/ingest — 接受ERP/CRM/MES原始数据→字段映射→标准FDE输入→展示本体作跨系统语义桥梁(X) | 2026-07-11 |
| 能力自描述 | `platform/apps/fde/api/fde.py:2991-3090` | ✅ | GET /fde/capabilities — 结构化能力清单(6层/30+模块/12端点)→系统自我声明"企业大脑原型"(Z) | 2026-07-11 |
| 本体覆盖率度量 | `platform/apps/fde/api/fde.py:3079-3190` | ✅ | GET /fde/sessions/{id}/ontology-coverage — 四维分解(本体实例%/历史案例%/LLM推测%/术语%)→量化"本体包住多少不确定性" | 2026-07-11 |
| 覆盖率改进建议 | `platform/apps/fde/api/fde.py:3208-3330` | ✅ | GET /fde/sessions/{id}/improve — 基于覆盖率生成可执行改进(新增本体类/创建术语/补充历史案例)→度量→行动闭环 | 2026-07-11 |
| SECI知识原子域 | `~/.aiplat/ontologies/knowledge-atom.yaml` | ✅ | KnowledgeAtom+KnowledgeLink类定义→atom_type(6类)+source(5源)+3种关系(SIMILAR_TO/DERIVED_FROM/CONFLICTS_WITH) | 2026-07-11 |
| SECI Engine (S→E+E→C) | `harness/knowledge/seci_engine.py` | ✅ | socialize_to_external(记忆→原子)+external_to_combine(跨域关联→KnowledgeLink)→Phase 1完成 | 2026-07-11 |
| SECI POST_LOOP Hook | `harness/knowledge/seci_engine.py:248-330` | ✅ | POST_LOOP自动捕获scored>0.8的对话→SECIEngine.socialize→atom→跨域关联→全自动S→E→C(Phase 2) | 2026-07-11 |
| SECI C→I + I→S | `harness/knowledge/seci_engine.py:220-322` + `apps/skills/registry.py:101-121` + `harness/routing/skill_routing.py:247-285` | ✅ | combine_to_internal(阻尼调整Skill权重)+internal_to_socialize(Canary→原子→闭环)(Phase 3) | 2026-07-11 |
| SECI状态面板 | `platform/apps/fde/api/fde.py:3333-3420` | ✅ | GET /fde/seci-status — 知识创造引擎实时状态(原子/关联/来源分布/权重/螺旋健康度) | 2026-07-11 |
| 收敛引擎 | `harness/knowledge/convergence_engine.py` + `knowledge-atom.yaml:150-165` | ✅ | scan_and_converge()四触发器(skill_weight/agent_prompt/pipeline_stage/correction_rollback)+版本链防循环+元闭环回写 | 2026-07-11 |
| 收敛能力注册 | `apps/skills/registry.py:1091-1112` + `harness/knowledge/seci_engine.py:208-235` | ✅ | SkillRegistry.apply_convergence()+DEPRECATES关系检测→收敛建议→系统行为调整→元闭环 | 2026-07-11 |
| POST_LOOP自动收敛 | `harness/knowledge/seci_engine.py:514-526` | ✅ | atom>5时POST_LOOP自动触发ConvergenceEngine.scan_and_converge()→SECI→Convergence全自动闭环 | 2026-07-11 |
| 本体消费总线 | `harness/knowledge/ontology_bus.py` + `~/.aiplat/ontologies/ai-solution.yaml` | ✅ | OntologyBus动态加载YAML数据→方案原型表+数字员工映射从硬编码迁移为YAML驱动→新增方案零代码 | 2026-07-11 |
| 术语动态注入 | `apps/skills/registry.py:1889-1919` | ✅ | 术语字典注入从静态字符串替换为GraphIndex动态加载→随自播种自动增长→零硬编码 | 2026-07-11 |
| YAML热加载 | `harness/knowledge/ontology_bus.py:28-62` | ✅ | mtime缓存→YAML文件变更自动检测→零重启配置更新→新增方案原型实时生效 | 2026-07-11 |
| 本体治理工程化声明 | `platform/apps/fde/api/fde.py:3440-3665` | ✅ | GET /fde/governance — 8项治理能力矩阵成熟度自评+对传统数据治理/睿治Agent行业对标+实时状态 | 2026-07-11 |
| 治理自审计 | `platform/apps/fde/api/fde.py:3668-3760` | ✅ | GET /fde/governance/validate — 8项能力逐一可执行审计(代码可查/端点可调/约束可测)→8/8 pass in 50ms | 2026-07-11 |
| 术语定义自动补全 | `apps/skills/registry.py:1331-1390,2200-2215` | ✅ | 术语自播种时关键词匹配生成定义(15个预置定义)→无LLM调用→零延迟→无匹配时留空待人工补全 | 2026-07-11 |
| 跨域术语去重 | `apps/skills/registry.py:2217-2235` | ✅ | 术语播种前检测enterprise-terms中同名概念→已有则创建similar_to跨域关联→防止跨域术语碎片化 | 2026-07-11 |
| FDE仪表板 | `platform/apps/fde/api/fde.py:3771-3838` | ✅ | GET /fde/dashboard — 单次请求聚合关键指标+最近活动+主动告警+治理健康度→前端首页即用 | 2026-07-11 |
| **文档系统下载** | `management/api/docs.py` + `DocsViewer.tsx` | ✅ | GET /api/docs/download?path=... — 文档系统支持文件下载（Content-Disposition attachment） | 2026-07-18 |
| 会话对比 | `platform/apps/fde/api/fde.py:3885-3980` | ✅ | GET /fde/sessions/compare?left=id1&right=id2 — 双会话并排对比(就绪度/证据覆盖率/行动数/知识缺口)→增量分析 | 2026-07-11 |
| 上下文总线 | `harness/knowledge/context_bus.py` | ✅ | assemble_field_assessment()统一10层上下文组装→registry.py从~350行注入缩减为~10行→各层可独立复用 | 2026-07-12 |
| 管线状态 | `platform/apps/fde/api/fde.py:4005-4075` | ✅ | GET /fde/pipeline-status — ContextBus逐层健康诊断+数据可用性快照(graphs/YAMLs)→注入管线透明化 | 2026-07-12 |
| 演示数据播种 | `platform/apps/fde/api/fde.py:4107-4202` | ✅ | POST /fde/bootstrap-test-data?industry=&company= — 支持4行业专属演示数据(actions/evidence/readiness差异化) | 2026-07-12 |
| 全行业播种 | `platform/apps/fde/api/fde.py:4205-4250` | ✅ | POST /fde/bootstrap-all — 一键播种4行业(政务/金融/制造/医疗)完整演示数据→12 actions+8 terms | 2026-07-12 |
| 场景化技能包 | `ai-solution.yaml` + `ontology_bus.py` + `apps/skills/registry.py` | ✅ | digital_employee_roles增加skills字段→load_role_skills()/get_role_by_keyword()/filter_by_role()→角色与Skill动态绑定 | 2026-07-12 |
| 对象语义开放 | `platform/apps/fde/api/fde.py` | ✅ | GET /fde/domain/{d}/operations → Agent可查询域中类的属性/状态转换/推理规则/对象属性(P1) | 2026-07-12 |
| 权限边界建模 | `fde-delivery.yaml` + `graph_index.py` + `ontology_bus.py` | ✅ | YAML permissions字段(admin/operator/viewer三层)→_load_permission_rules()→check_permission()(P2) | 2026-07-12 |
| 系统时序列观察 | `knowledge-atom.yaml` + `platform/apps/fde/api/fde.py:3382-3405,4480-4580` | ✅ | SystemSnapshot持久化→GET /fde/trends/system(12周趋势)+/fde/health/history(历史对比)→自演进数据基础 | 2026-07-12 |
| 系统主动诊断 | `harness/knowledge/system_diagnostician.py` + `platform/apps/fde/api/fde.py:4578-4592` | ✅ | SystemDiagnostician(5条规则)→跨子系统关联分析(seci/evidence/skill/knowledge/convergence)→GET /fde/diagnose | 2026-07-12 |
| 系统自修复 | `harness/knowledge/system_diagnostician.py:306-430` + `platform/apps/fde/api/fde.py:4596-4613` | ✅ | SystemHealer(confidence≥0.9安全门+5条自动修复+效果验证+审计快照)→POST /fde/heal | 2026-07-12 |
| 系统自主演化 | `harness/knowledge/system_evolver.py` + `platform/apps/fde/api/fde.py:4622-4638` | ✅ | SystemEvolver(4条演化规则→术语自动发布/方案草稿审批)→GET /fde/evolve | 2026-07-12 |
| 系统自演进路由 | `api/routers/system.py` + `harness/knowledge/seci_engine.py:523-528` | ✅ | GET /system/overview/diagnose/evolve+POST /system/heal/self-check →POST_LOOP每10次自动诊断 | 2026-07-12 |
| 项目化手册生成 | `platform/apps/fde/api/fde.py:4738-5011` | ✅ | POST /fde/manuals(创建)+GET/PUT/regenerate/versions(生命周期)→项目专属手册+3个CUSTOM_SECTION+非破坏性再生成 | 2026-07-12 |
| 全局编码宪法 | `_facade.py:1724` + `registry.py:1544` + `executor.py:369` | ✅ | karpathy_v1从可选开关→全局默认→所有Skill执行自动遵循4原则(编码前思考/简洁优先/精准修改/目标驱动) | 2026-07-12 |
| 反馈→SECI接入 | `system_diagnostician.py` | ✅ | feedback_pattern诊断规则+_apply_feedback_correction修复→用户修正行为自动转化为KnowledgeAtom(P0) | 2026-07-12 |
| 置信度校准 | `system_diagnostician.py` | ✅ | confidence_overconfident诊断规则→detminism_score vs delivery_rate偏差>20%告警(P1) | 2026-07-12 |
| 知识新鲜度 | `system_diagnostician.py` + `knowledge-atom.yaml` | ✅ | knowledge_stale诊断规则→超90天无更新原子告警(P2) | 2026-07-12 |
| Agent对话质量诊断 | `system_diagnostician.py:476-508` | ✅ | agent_quality_decline规则→7天原子产出<3告警→Agent/Pipeline/Memory全接入OS诊断(A) | 2026-07-12 |
| Pipeline阶段健康 | `pipeline_engine.py:1954-1964` + `system_diagnostician.py:212-245` | ✅ | pt_快照持久化→pipeline_stage_failing规则→24h内同阶段失败≥3告警(B) | 2026-07-12 |
| Memory压缩健康 | `compression.py:120-123` + `system_diagnostician.py:747-761` | ✅ | compression_stats属性暴露→compression_ineffective规则→压缩比<30%告警+agent↔compress关联(C) | 2026-07-12 |
| 技能生命周期管理 | `skill_curator.py` + `registry.py:84` + `system.py:249-256,357-371` | ✅ | Hermes Agent式Curator→每7天审查(30d stale/90d archive/重叠合并)→GET /system/curate-skills | 2026-07-12 |
| 智能澄清对话 | `platform/apps/fde/api/fde.py` + `FdeDashboard.tsx` | ✅ | POST /fde/assess/dialog(多轮状态机)→_compute_readiness gaps驱动追问→就绪度≥60自动触发诊断+前端Dialog | 2026-07-12 |
| 多子系统上下文 | `harness/knowledge/context_bus.py:345-405` | ✅ | assemble_agent/skill/pipeline_context()→Agent(3层)/Skill(2层)/Pipeline(3层)各自轻量注入→总线覆盖全系统 | 2026-07-12 |
| Agent领域上下文 | `harness/knowledge/context_bus.py:408-452` | ✅ | SESSION_START hook→所有Agent启动时自动注入术语字典+数字员工→领域知识全局可用 | 2026-07-12 |
| 质量总线 | `platform/apps/fde/api/fde.py:4176-4270` | ✅ | GET /fde/quality-summary — 跨子系统质量聚合(FDE/SECI/Convergence/ContextBus四维评分)→统一0-100评分 | 2026-07-12 |
| FDE趋势分析 | `platform/apps/fde/api/fde.py:2431-2550` | ✅ | GET /fde/trends — 时间序列统计(会话数/交付率/就绪度趋势)+术语增长曲线+行业分布(T) | 2026-07-11 |
| FDE统一搜索 | `platform/apps/fde/api/fde.py:2578-2710` | ✅ | GET /fde/search?q=&scope= — 跨实体全文检索(会话/行动/术语/证据/行业)合并排序(U) | 2026-07-11 |
| FDE质量评分 | `platform/apps/fde/api/fde.py:2717-2820` | ✅ | GET /fde/sessions/{id}/quality — 四维加权评分(证据覆盖率+行动完成率+术语覆盖率+状态变迁)0-100(V) | 2026-07-11 |
| FDE主动告警 | `platform/apps/fde/api/fde.py:2805-2920` | ✅ | GET /fde/alerts — 扫描所有会话检测blocked/stale/low_quality/zero_evidence/high_gaps五类告警(W) | 2026-07-11 |
| FDE动作闭环 | `platform/apps/fde/api/fde.py:1688-1807,2198-2300` | ✅ | StateTransition实体化(每次状态变更创建记录)→has_transition关系→GET timeline查看完整生命周期(Palantir L4) | 2026-07-11 |

---

## 四、RAG 检索

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| wiki_engine | `harness/knowledge/wiki_engine.py` | ✅ | 自动同步 | 已合入 |
| capability_graph | `harness/knowledge/capability_graph.py` | ✅ | 自动同步 | 已合入 |
| sqlite_retriever | `harness/knowledge/sqlite_retriever.py` | ✅ | 自动同步 | 已合入 |
| code_graph | `harness/knowledge/code_graph.py` | ✅ | 自动同步 | 已合入 |
| doc_compressor | `harness/knowledge/doc_compressor.py` | ✅ | 自动同步 | 已合入 |
| ontology_query_mapper | `harness/knowledge/ontology_query_mapper.py` | ✅ | 自动同步 | 已合入 |
| wiki_retriever | `harness/knowledge/wiki_retriever.py` | ✅ | 自动同步 | 已合入 |
| cap_health_rules | `harness/knowledge/cap_health_rules.py` | ✅ | 自动同步 | 已合入 |
| skill_deps | `harness/knowledge/skill_deps.py` | ✅ | 自动同步 | 已合入 |
| code_graph_persist | `harness/knowledge/code_graph_persist.py` | ✅ | 自动同步 | 已合入 |
| cap_graph_persist | `harness/knowledge/cap_graph_persist.py` | ✅ | 自动同步 | 已合入 |
| reparse_queue | `harness/knowledge/reparse_queue.py` | ✅ | 自动同步 | 已合入 |
| text_cleaner | `harness/knowledge/text_cleaner.py` | ✅ | 自动同步 | 已合入 |
| doc_quality_monitor | `harness/knowledge/doc_quality_monitor.py` | ✅ | 自动同步 | 已合入 |
| sql_ontology | `harness/knowledge/sql_ontology.py` | ✅ | 自动同步 | 已合入 |
| wiki_quality_monitor | `harness/knowledge/wiki_quality_monitor.py` | ✅ | 自动同步 | 已合入 |
| active_synthesis | `harness/knowledge/active_synthesis.py` | ✅ | 自动同步 | 已合入 |
| code_entropy_detector | `harness/knowledge/code_entropy_detector.py` | ✅ | 自动同步 | 已合入 |
| adaptive_context | `harness/knowledge/adaptive_context.py` | ✅ | 自动同步 | 已合入 |
| wiki_indexer | `harness/knowledge/wiki_indexer.py` | ✅ | 自动同步 | 已合入 |
| skill_marketplace | `harness/knowledge/skill_marketplace.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| 统一知识检索 | `harness/syscalls/retrieval.py:569` | ✅ | 并行 Wiki + KB，RRF 三路融合 | 已合入 |
| KB 文档检索 | `harness/syscalls/retrieval.py:39` | ✅ | hybrid: LIKE + FTS5 + FAISS 向量 | 已合入 |
| Wiki 页面检索 | `harness/syscalls/retrieval.py:467` | ✅ | FTS5 + embedding + 链接遍历 + 本体过滤 | 已合入 |
| RRF 三路融合 | `harness/knowledge/hybrid_retriever.py:53` | ✅ | Wiki+KB+Graph 统一 1/(k+rank) 融合 | 已合入 |
| Graph Early Exit | `harness/syscalls/retrieval.py:591` | ✅ | confidence>0.92 直接返回，取消Wiki/KB | 已合入 |
| CRAG 3级回退 | `harness/knowledge/retriever.py:262` | ✅ | 本体优先→FTS5→HyDE | 已合入 |
| HyDE 假设答案 | `harness/knowledge/hyde_expander.py:27` | ✅ | LLM生成假设 → 向量检索 | 已合入 |
| Wiki CircuitBreaker | `harness/syscalls/retrieval.py:506` | ✅ | CLOSED→OPEN(3次失败)→HALF_OPEN | 已合入 |
| DomainRouter | `harness/knowledge/domain_router.py:26` | ✅ | T1标签→T2向量→T3 LLM，3层级联 | 已合入 |
| SemanticCache (L1/L2) | `harness/knowledge/semantic_cache.py:31` | ✅ | L1精确(md5)→L2语义(cosine≥0.95)→L3穿透 | 已合入 |
| 缓存版本号切换 | `harness/knowledge/semantic_cache.py` | ✅ | INCR version O(1) + L1主动清 + 版本窗口 | 已合入 |
| LatentStageCache | `harness/knowledge/semantic_cache.py:305` | ✅ | 多阶段隐空间缓存，query+domain+retrieval向量组合匹配 | 已合入 |
| QueryRewriter | `harness/knowledge/query_rewriter.py` | ✅ | 查询改写/扩展 | 已合入 |
| Reranker | `harness/knowledge/reranker.py` | ✅ | CrossEncoder 重排序 | 已合入 |
| ProvenanceTracker | `harness/knowledge/provenance.py` | ✅ | 声明级溯源 + 过期扫描 | 已合入 |
| PostRetrievalGovernor | `harness/knowledge/post_retrieval_governor.py` | ✅ | 检索后去重/归一化/截断 | 已合入 |
| HallucinationTracker | `knowledge/` | ✅ | NLI 事实核查 + GraphIndex 图边验证 | 已合入 |
| 答案生成管道 | `harness/generation/answer_generator.py` | ✅ | generate_answer + generate_stream_answer + build_rag_user_message | 重构 |
| Action 闭环桥接 | `harness/actions/action_bridge.py` | ✅ | OperatorAgent决策→webhook通知 + execute_decision_actions | 重构 |

---

## 四附、知识基础设施（Knowledge）

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| SemanticEmbedder | `harness/knowledge/embedder.py` | ✅ | 文本→向量，via InfraEmbeddingAdapter | 已合入 |
| DB Abstraction | `harness/knowledge/db.py` | ✅ | 知识库数据库抽象层 | 已合入 |
| Graph Sync | `harness/knowledge/graph_sync.py` | ✅ | 图数据同步 | 已合入 |
| Graph Module | `harness/knowledge/graph.py` | ✅ | 知识图基础结构 | 已合入 |
| RepoMap | `harness/knowledge/repo_map.py` | ✅ | 仓库结构映射 | 已合入 |
| Wiki FTS5 | `harness/knowledge/wiki_fts.py` | ✅ | FTS5 全文检索 | 已合入 |
| Wiki Structured Query | `harness/knowledge/wiki_structured_query.py` | ✅ | Wiki 结构化查询 | 已合入 |
| Wiki Health Rules | `harness/knowledge/wiki_health_rules.py` | ✅ | Wiki 健康规则检查 | 已合入 |
| Knowledge Quality | `harness/knowledge/knowledge_quality.py` | ✅ | 知识质量评分 | 已合入 |
| Knowledge Growth | `harness/knowledge/knowledge_growth.py` | ✅ | 知识增长追踪 | 已合入 |
| Knowledge Writeback | `harness/knowledge/knowledge_writeback.py` | ✅ | 知识写回 | 已合入 |
| Knowledge Markings | `harness/knowledge/knowledge_markings.py` | ✅ | 知识标记与权限 | 已合入 |
| Knowledge Ontology | `harness/knowledge/knowledge_ontology.py` | ✅ | 知识本体管理 | 已合入 |
| Knowledge Action | `harness/knowledge/knowledge_action.py` | ✅ | 知识操作 | 已合入 |
| Knowledge Validator | `harness/knowledge/knowledge_validator.py` | ✅ | 知识条目校验 | 已合入 |
| Knowledge ABox Builder | `harness/knowledge/knowledge_abox_builder.py` | ✅ | A-Box (实例) 构建 | 已合入 |
| Knowledge Evolution LLM | `harness/knowledge/knowledge_evolution_llm.py` | ✅ | 知识进化 LLM 驱动 | 已合入 |
| SceneModel | `harness/knowledge/scene_model.py` | ✅ | 场景模型 | 已合入 |
| Learning Assessment | `harness/knowledge/learning_assessment.py` | ✅ | 学习评估 | 已合入 |
| Learning Ontology | `harness/knowledge/learning_ontology.py` | ✅ | 学习本体 | 已合入 |
| Learning Paths | `harness/knowledge/learning_paths.py` | ✅ | 学习路径推荐 | 已合入 |
| Ontology Loader | `harness/knowledge/ontology_loader.py` | ✅ | YAML本体加载 | 已合入 |
| Ontology Validator | `harness/knowledge/ontology_validator.py` | ✅ | 本体校验 | 已合入 |
| Capability Health | `harness/knowledge/capability_health.py` | ✅ | 能力健康评分 + Graph 持久化 | 已合入 |
| Symbol Health | `harness/knowledge/symbol_health.py` | ✅ | 知识符号健康度 | 已合入 |
| Evolution Runner | `harness/knowledge/evolution_runner.py` | ✅ | 知识进化执行 | 已合入 |
| KB Callbacks | `harness/knowledge/callbacks.py` | ✅ | Ingest/Query/EnqueueIngest/LoadDocKinds 回调 | 已合入 |
| Complexity Router | `harness/knowledge/complexity_router.py` | ✅ | 复杂查询路由 | 已合入 |
| CandidateKnowledgePool | `harness/knowledge/candidate_pool.py` | ✅ | FDE 现场反馈候选池：去重 + 语义冲突检测(>100°) + N≥3 自动触发 ActiveSynthesis | 2026-07-17 |

---

## 五、Agent 系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| kpi_agent | `harness/agents/kpi_agent.py` | ✅ | 自动同步 | 已合入 |
| strategy_agent | `harness/agents/strategy_agent.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| 7 种 Agent 实现类 | `apps/agents/` | ✅ | ReAct/Conversational/PlanExecute/RAG/MultiAgent/MaterialsChat/Pipeline | 已合入 |
| AGENT.md 系统 | `apps/agents/discovery.py` | ✅ | YAML frontmatter → PipelineStageConfig | 已合入 |
| 交接5字段 | AGENT.md 规范 | ✅ | 做了什么/产出物/如何验证/已知问题/下一步 | 已合入 |
| SubAgent 协调器 | `apps/agents/subagent/coordinator.py` | ✅ | execute_single/parallel/sequential/fanout | 已合入 |
| 5 个内置 SubAgent | `apps/agents/subagent/registry.py` | ✅ | reviewer/debugger/tester/docs/perf | 已合入 |
| ParallelExecutor | `apps/agents/parallel_executor.py` | ✅ | Map-Reduce, max_concurrency=5, 异常隔离 | 已合入 |
| PipelineCompiler | `apps/agents/pipeline_compiler.py` | ✅ | AGENT.md stages[] YAML → PipelineStageConfig | 已合入 |
| Agent SDK | `aiplat-sdk/` | ✅ | L1 Agent/L2 Pipeline/L3 ReActLoop — execute/stream/chat 全路径可用 | 已合入 |
| FanOut 并行 | `apps/agents/parallel_executor.py` | ✅ | 已接线 | 已合入 |
| DelegateManager | `harness/infrastructure/delegate_tool.py` | ✅ | 子Agent委托 + 资源预算隔离 + 重试退避 + 输出摘要(§5.26) | 已合入 |
| OperatorAgent | `apps/agents/operator_agent.py` | ✅ | 运维决策助手 — 消费RunContext → 结构化JSON(severity/impact/actions/can_continue) | Phase 10.4 |
| operator-decision prompt | `harness/utils/prompt_loader.py` | ✅ | 决策框架 + 输出格式 + 约束规则 | Phase 10.4 |
| 共享检索管道 | `harness/knowledge/orchestrated_retrieval.py` | ✅ | traverse_ontology_graph + ontology_first_retrieve + build_reasoning_path | 重构 |
| HyDE 检索统一 | `harness/knowledge/hyde_expander.py` | ✅ | hyde_retrieve() 封装全管道(生成→检索→格式化) | 重构 |
| 成本路由决策 | `harness/knowledge/cost_estimator.py` | ✅ | resolve_routing_mode() 统一成本→路由映射 | 重构 |
| 查询守卫 | `harness/knowledge/query_guard.py` | ✅ | sanitize_query + enforce_scope | 重构 |
| 语义缓存钩子 | `harness/knowledge/semantic_cache_hook.py` | ✅ | try_cache_hit + write_cache_result (任意Agent复用) | 重构 |
| PipelineTracer | `harness/utils/pipeline_tracer.py` | ✅ | 时序轨道上下文管理器 | 重构 |
| 会话摘要器 | `harness/utils/turn_summarizer.py` | ✅ | question+answer → 中文摘要 | 重构 |
| 答案提取器 | `harness/utils/answer_extractor.py` | ✅ | 循环输出 → 纯文本答案 | 重构 |
| 琐问处理器 | `harness/utils/trivial_handlers.py` | ✅ | 时间/数学表达式即时响应 | 重构 |

---

## 六、Skill 系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| review_report | `engine/skills/autoreview/review_report.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| SkillRegistry | `apps/skills/registry.py` | ✅ | 注册/启用/禁用/版本管理/semver回滚 | 已合入 |
| **autoreview skill** | `engine/skills/autoreview/` | ✅ | 自动代码审查引擎：单引擎/硬投票面板/MoA Deep Mode、3套preset、Scope Governor、auto_fixer (git stash回滚) | v2.1 |
| autoreview handler | `engine/skills/autoreview/handler.py` | ✅ | 执行入口：温度分层(0.6探索/0.3决策)、preset加载、引擎隔离 | 已合入 |
| autoreview diff_loader | `engine/skills/autoreview/diff_loader.py` | ✅ | Git Diff驱动：8000 tokens截断、dev/null保护、拒绝全仓库审查 | 已合入 |
| autoreview aggregator | `engine/skills/autoreview/report_aggregator.py` | ✅ | MoA投票聚合：行号锚点+3级投票+Aggregator LLM综合判断 | 已合入 |
| autoreview evidence_chain | `engine/skills/autoreview/review_report.py` | ✅ | v2.2: build_evidence()+clean_evidence()+to_markdown自动附加+_persist_review持久化 | 已合入 |
| autoreview pipeline_stage | `engine/skills/autoreview/pipeline_stage.yaml` | ✅ | depends_on[code_gen,test_gen], failure_strategy:skip_stage, timeout:120s | 已合入 |
| SkillExecutor | `apps/skills/executor.py` | ✅ | Agent调用 + 独立执行双路径 | 已合入 |
| skill_call syscall | `harness/syscalls/skill.py` | ✅ | PolicyGate + ApprovalGate + 审计 | 已合入 |
| 5 准入标准 | `skills/architecture.md` | ✅ | 独立/边界/复用/治理/执行单元 | 已合入 |
| 副作用声明 | SKILL.md frontmatter | ✅ | effects: type/idempotent/rollback | 已合入 |
| EvolutionEngine | `apps/skills/evolution/engine.py` | ✅ | AI草稿→模拟→人工审批 | 已合入 |
| Skill Lint 10规则 | `management/lint_rules.yaml` | ✅ | name/version/category/schema 校验 | 已合入 |
| 滑动窗口衰减追踪 | `apps/skills/registry.py` | ✅ | recent_pass_rate + decayed_at | 已合入 |
| AutoLearner | `harness/evolution_engine.py` | ✅ | 失败分析→SkillDraft→审批→注册 | 已合入 |
| SkillRouting | `harness/routing/skill_routing.py` | ✅ | Canary/A-B/Shadow/Auto-Rollback | 已合入 |
| Completion Criterion | 30个 SKILL.md frontmatter | ✅ | 每个 skill 显式声明完成条件，5类模板（知识/生成/工程/测试/交互） | 已合入 |
| Grilling 追问技能 | `engine/skills/grilling/SKILL.md` | ✅ | Matt Pocock 风格：一次一问 + ≤3推荐选项 + 读文件原则 | 已合入 |
| Leading Words 术语表 | `engine/skills/leading_words.md` | ✅ | 8个工程先验词汇（tight loop/tracer bullet/deep module/seam等） | 已合入 |
| Action Type 操作契约 | `harness/interfaces/skill.py` + `apps/skills/executor.py` | ✅ | submission_criteria前置校验 + permissions角色控制 + side_effects声明 + _evaluate_criterion()执行前拦截 | 已合入 |
| field-assessment HMESI增强 | `apps/skills/registry.py:1651-1690` | ✅ | 诊断报告注入历史案例检索(search_pages)+跨域类比(discover_cross_domain_analogs)+§4.65预期干预效果表格(HMESI Step 3) | 2026-07-11 |
| 诊断溯源（证据等级） | `apps/skills/registry.py:1318-1323` + `:1692-1710` | ✅ | §1表格新增证据等级列(本体实例/历史案例/LLM推测)+system prompt注入三级标注规则，至少50%行需有据可查 | 2026-07-11 |
| **canary_runner** | `engine/skills/canary_runner/SKILL.md` | ✅ | 灰度发布执行器（prompt），调用 /fde/canary API | 2026-07-18 |
| **manual_generator** | `engine/skills/manual_generator/SKILL.md` | ✅ | 交付手册生成器（prompt），调用 /fde/manual/generate | 2026-07-18 |
| **register_fde_prompts** | `apps/fde/prompts.py` | ✅ | FDE域prompt自动注册（7个），启动时回调注册 | 2026-07-18 |
| **模块 Prompt 管理系统** | `apps/{module}/prompts.py`（6 模块） | ✅ | prompt_loader 域 prompt 迁移至各模块：fde(8)/builder(8)/skills(4)/eval(2)/knowledge(5)/workbench(4) | 2026-07-18 |
| **finetune 模块搬迁** | `apps/finetune/` | ✅ | 从 harness/finetune/ + schemas_finetune.py 搬迁至标准模块目录结构 | 2026-07-18 |

---

## 七、安全与治理

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| prompt_auditor | `harness/audit/prompt_auditor.py` | ✅ | 自动同步 | 已合入 |
| semantic_gate | `harness/infrastructure/gates/semantic_gate.py` | ✅ | 自动同步 | 已合入 |
| cross_validation_gate | `harness/infrastructure/gates/cross_validation_gate.py` | ✅ | 自动同步 | 已合入 |
| completion_gate | `harness/infrastructure/gates/completion_gate.py` | ✅ | 自动同步 | 已合入 |
| audit_trail_gate | `harness/infrastructure/gates/audit_trail_gate.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| PolicyGate | `harness/infrastructure/gates/policy_gate.py` | ✅ | 统一权限检查 + 架构边界实时拦截 | 已合入 |
| ApprovalGate | `harness/infrastructure/approval/manager.py` | ✅ | approve/deny/pending，双门禁 | 已合入 |
| Prompt 注入防护 | `harness/syscalls/llm.py:125` | ✅ | 6条正则+特殊token过滤+覆盖防护指令 | 已合入 |
| 记忆投毒防御 | `harness/memory/base.py:39` | ✅ | source_tag/trust_weight/provenance | 已合入 |
| PII 脱敏（全量覆盖） | `kb/service.py` → `_mask_pii()` + `services/pii_detector.py` | ✅ | 手机/身份证/邮箱/银行卡/地址/IP，全部 6 条入库路径已覆盖 | 已合入 |
| CodeAuditor | `harness/security/code_auditor.py` | ✅ | 注入/XSS/CSRF/认证/授权检查 | 已合入 |
| RBAC 多租户 | platform 层 | ✅ | tenant + actor + scopes 三级隔离 | 已合入 |
| 架构守卫 172 规则 | `arch_guard_rules.yaml` | ✅ | §1-§76 自动扫描 | 已合入 |
| 172 条 CI 检查 | `architecture_guard.sh` | ✅ | 零依赖 grep 扫描 | 已合入 |
| 前端 API 契约检查 | `../../scripts/guard_frontend.py` | ✅ | TS fetch ↔ Python data.get 一致性 | 已合入 |
| PII 检测脱敏 | `services/pii_detector.py` | ✅ | 手机/身份证/邮箱/银行卡/地址/IP，Presidio+正则双引擎 | 已合入 |
| 合规报告 SOC2/ISO27001 | `management/compliance_checks.py` | ✅ | 12检查 + SOC2 CC/ISO27001 A映射 + 自动报告生成 | 已合入 |
| 架构契约上下文注入 | `harness/utils/prompt_loader.py` → `harness/assembly/prompt_assembler.py` | ✅ | coding-contract 模板在代码生成前注入 Agent system prompt（6条核心约束） | 已合入 |
| 审计日志防篡改 | `../../aiPlat-platform/governance/audit/logger.py` | ✅ | SHA-256 链式哈希 + verify_integrity() | 已合入 |
| 对象级权限 | `policy/object_permission.py` | ✅ | 每实体/每动作/每角色细粒度控制，支持本体继承 | 已合入 |
| 字段级安全 | `policy/field_level_security.py` | ✅ | 单元/字段级数据可见性，Palantir CBAC对齐 | 已合入 |
| 技能签名验证 | `security/skill_signature_gate.py` | ✅ | Ed25519 签名校验 + 可信公钥注册表 | 已合入 |
| SecretsManager | `harness/infrastructure/secrets_manager.py` | ✅ | AES-256-GCM 加密存储 + 审计日志 | 已合入 |
| Ed25519 签名 | `harness/infrastructure/crypto/signature.py` | ✅ | 密钥生成/签名/验签，技能/制品完整性保护 | 已合入 |
| CryptoSecretBox | `harness/infrastructure/crypto/secretbox.py` | ✅ | 对称加密盒，运行时密钥保护 | 已合入 |
| DI 容器 | `harness/infrastructure/di/__init__.py` | ✅ | 依赖注入容器，12/18服务调用已转换 | 已合入 |
| Config Settings | `harness/infrastructure/config/settings.py` | ✅ | 层级配置管理 + 环境变量覆盖 | 已合入 |
| SSO/OIDC 集成 | `../../aiPlat-platform/auth/identity_provider.py` | ✅ | Keycloak/Azure AD/Okta，discovery/jwks映射 + login/callback/token API | 已合入 |
| CrisisDetector | `harness/security/crisis_detector.py` | ✅ | 自伤/暴力/危急三級检测，WARN/BLOCK/SILENT 模式 | 已合入 |
| CrisisGate | `harness/security/crisis_gate.py` | ✅ | syscall 边界危机拦截，ALLOW/WARN/FLAG/BLOCK/ESCALATE | 已合入 |
| EmotionTracker | `harness/security/emotion_tracker.py` | ✅ | 跨会话情绪弧追踪 + 过度依赖检测 | 已合入 |
| ApprovalGate (危险命令) | `harness/infrastructure/gates/approval_gate.py` | ✅ | 25规则危险操作检测，CRITICAL/HIGH/MEDIUM/LOW 四级，集成 PolicyGate | 已合入 |
| SkillsGuard (威胁扫描) | `harness/infrastructure/gates/skills_guard.py` | ✅ | 78威胁模式，skill注册前安全扫描，11类别全覆盖 | 已合入 |

---

## 八、可观测性

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| trace_id / span_id | `harness/observation/event_schema.py` | ✅ | 每次 syscall 携带 | 已合入 |
| EventBus | `harness/observation/event_bus.py` | ✅ | 发布/订阅 syscall 事件 | 已合入 |
| PipelineTrace | `harness/execution/pipeline_engine.py` | ✅ | 每阶段 started/completed/skipped/failed | 已合入 |
| 决策溯源 | 引擎内 `_last_action_reason` | ✅ | budget_exhausted 等非正常路径 | 已合入 |
| OtelBridge | `harness/observation/otel_bridge.py` | ✅ | AIPLAT_OTEL_ENABLED=true | 已合入 |
| Prometheus | `infrastructure/` | ✅ | prometheus-fastapi-instrumentator | 已合入 |
| MetricsCollector | `observability/metrics/` | ✅ | 滑动窗口聚合器 | 已合入 |
| 执行审计 | execution_store audit_log | ✅ | AIPLAT_EXECUTION_AUDIT=true | 已合入 |
| 健康检查 | `health/` + `harness/knowledge/capability_health.py` | ✅ | 能力健康+Symbol健康+Wiki健康 | 已合入 |
| Prometheus 10 指标 | `harness/memory/metrics.py` | ✅ | tool_truncated/semantic_renewed/rrf_latency/early_exit/cache_version 等 | 已合入 |
| 语义记忆后台清理 | `harness/memory/manager.py:111` | ✅ | 每日定时软删除过期低频记忆，AIPLAT_MEMORY_CLEANUP_INTERVAL 可配 | 已合入 |
| TraceVisualizer | `harness/execution/trace_visualizer.py` | ✅ | 决策痕迹可视化: 犹豫检测/重复检测/异常预警→Spec调整建议 | 已合入 |
| Evaluation Summary Cron | `harness/scheduler/cron.py` | ✅ | 每周自动生成 FDE 运营周报（聚合 RAGDiagnosticsCollector + HallucinationTracker + FeedbackRadar）→ LLM NL 草稿 → 写入 _DIAG_CACHE["weekly_report"] | 2026-07-17 |
| FDE 周报前端 | `frontend/Diagnostics/WeeklyReport.tsx` | ✅ | 诊断中心新增"周报"卡片：NL 渲染 + 一键复制为客户简报 + FDE 批注修订 | 2026-07-17 |
| FDE Dashboard | `api/routers/workbench.py:fde-dashboard` + `UserWorkbench.tsx` | ✅ | 4卡聚合(待决策/信号预警/执行异常/训练)+时间轴+Spec筛选联动 | 已合入 |
| TrendDetector (熵增预警) | `harness/infrastructure/trend_detector.py` | ✅ | 6桶滑动窗口+双缓冲+状态机(NORMAL/ALERTING/HIGH_ALERT/RESOLVED)+7天基线 | 已合入 |

---

## 九、模型基础设施

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| infra_bridge | `harness/infrastructure/infra_bridge.py` | ✅ | 自动同步 | 已合入 |
| base_model_adapter | `harness/infrastructure/base_model_adapter.py` | ✅ | 自动同步 | 已合入 |
| infra_audio_adapter | `harness/infrastructure/infra_audio_adapter.py` | ✅ | 自动同步 | 已合入 |
| feedback_translator | `harness/infrastructure/feedback_translator.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| InfraLLMAdapter | `harness/infrastructure/infra_llm_adapter.py` | ✅ | Core 唯一 LLM 适配器 | 已合入 |
| InfraEmbeddingAdapter | `harness/infrastructure/infra_embedding_adapter.py` | ✅ | SentenceTransformer | 已合入 |
| InfraRerankerAdapter | `harness/infrastructure/infra_reranker_adapter.py` | ✅ | CrossEncoder | 已合入 |
| InfraAudioAdapter | `harness/document/transcriber.py` | ✅ | faster-whisper + openai-whisper | 已合入 |
| InfraOCRAdapter | `harness/infrastructure/infra_ocr_adapter.py` | ✅ | 统一OCR入口 (Tesseract/PaddleOCR, text/structured/pdf) | 已合入 |
| BaseCircuitBreaker | `harness/infrastructure/circuit_breaker.py` | ✅ | 统一熔断器基类 (closed/open/half_open) — LLM/Wiki/MCP 共用 | 已合入 |
| 模型解析集中化 | `harness/utils/model_injection.py` | ✅ | get_default_model(purpose) 统一入口 | 已合入 |
| 模型发现 | infra ModelManager | ✅ | 远程API + 本地(Ollama/LM Studio/vLLM) | 已合入 |
| 路径工具 | `core/utils/paths.py` | ✅ | 统一 AIPLAT_HOME 路径解析 + 子目录捷径 | 已合入 |
| 常量定义 | `core/utils/constants.py` | ✅ | 截断/token/超时/domain 公共常量 | 已合入 |
| HTTP错误工具 | `core/api/http_errors.py` | ✅ | HTTPException 标准化构造器 | 已合入 |
| 视频转写 | `harness/document/transcriber.py` + platform/kb/video.py | ✅ | ffmpeg→Whisper→OCR→embed | 已合入 |
| 模型路由 | `harness/utils/model_injection.py` → infra `ModelManager.select()` | ✅ | model_router.py 已删除，create_selected_adapter 为唯一路径 | 已合入 |
| T1-T5 分层路由 | `harness/routing/model_tier_router.py` + `llm_profile.yaml` | ✅ | complexity→tier→cheapest capable model, 5级可配置 | Phase 12 |
| 复杂度感知选择 | `ModelManager.select_by_purpose(complexity=)` | ✅ | routing_rules 过滤 + best_model_for_purpose(messages=) | Phase 12.1 |
| 模型能力档案 | `llm_profile.yaml.model_capabilities` | ✅ | per-model routing_rules/min_complexity/max_complexity | Phase 12 |
| 会话模型覆盖 (/model) | `model_injection.py` + `adapters.py` | ✅ | set_model_override + clear_model_override + POST /model-override | Phase 13 |
| 模型层级仪表板 | `diagnostics.py` + frontend `ModelTierPanel` | ✅ | GET /diagnostics/model-tier + T1-T5 可视面板 + 一键切换 | Phase 14 |
| FingerprintCollector | `harness/knowledge/model_fingerprint.py` | ✅ | 8探针黑盒指纹采集：token分布/延迟曲线/拒答率/格式遵从 | 已合入 |
| ModelAudit | `harness/knowledge/model_audit.py` | ✅ | 模型身份报告生成 + 双模型指纹对比 + 已知签名匹配 | 已合入 |
| CredentialPool | `infra/management/model/credential_pool.py` | ✅ | Round-Robin + 黑名单冷却 + 多key轮换 | 已合入 |
| CredentialPool 热路径接线 | `openai_compatible.py` chat 重试循环 → `_rotate_key()` + `mark_rate_limited`/`mark_success` liveness | ✅ | 429/403/timeout 自动密钥轮换（chat+stream 全路径）；`status()` 脱敏池健康经 get_metrics 暴露；单key模式向后兼容 | 2026-07-06 |
| Model Pricing (llm_profile) | `config/infra/llm_profile.yaml` | ✅ | deepseek-v4-pro真实定价(prompt$0.27+completion$1.10/1M)+context_window 131072 | 已合入 |

---

## 十、部署与运维

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| 一键启动/停止 | `start.sh` / `stop.sh` | ✅ | 6服务顺序启动，pyc清理，端口释放 | 已合入 |
| 开发环境 | `scripts/dev.sh` | ✅ | 5服务并行开发启动 | 已合入 |
| 架构守卫 | `scripts/architecture_guard.sh` | ✅ | 172规则零依赖扫描 | 已合入 |
| Phase 验收 | `scripts/phase_check.sh` | ✅ | caller_verify + wiring + 死代码 | 已合入 |
| Caller 验证 | `scripts/caller_verify.sh` | ✅ | 零调用者模块检测 | 已合入 |
| E2E 测试 | `scripts/e2e_verify.sh` | ✅ | 端到端验证 | 已合入 |
| 冒烟测试 | `scripts/smoke_http_server.sh` | ✅ | HTTP服务 + 文档入库 | 已合入 |
| 基准测试 | `scripts/benchmark_all.sh` | ✅ | CI模式：5指标全量+基线对比 | 已合入 |
| 模型预加载 | `scripts/preload_models.sh` | ✅ | 首次启动加速 | 已合入 |
| 灾备脚本 | `scripts/ops/backup.sh` + `restore.sh` + `verify_restore.sh` | ✅ | 全量备份/恢复/完整性验证，可选S3 | 已合入 |
| KB 数据迁移 | `scripts/migrate_kb_to_instances.py` | ✅ | 一次性工具：已有 KB 文档 → 本体实例 → Wiki 页面 | 已合入 |
| Gold Dataset 更新 | `scripts/update_gold_dataset.py` | ✅ | 从工具/Skill 提取 gold examples 并合并到种子数据集 | 已合入 |
| KB SDK 生成 | `scripts/generate_kb_sdk.sh` | ✅ | 从 OpenAPI spec 生成 Python/TypeScript SDK | 已合入 |
| Wiki E2E 测试 | `scripts/e2e_wiki_test.sh` | ✅ | Wiki 后端 API + 前端集成端到端测试 | 已合入 |
| 文档入库冒烟测试 | `scripts/smoke_documents_ingest.sh` | ✅ | 启动服务 → 入录 fixture → 轮询 job → 校验 elements | 已合入 |
| ProcessRegistry | `harness/infrastructure/process_registry.py` | ✅ | 进程生命周期管理 + 异步健康监控 + 优雅关闭 | 已合入 |
| **fde_project_freeze** | `platform/apps/fde/api/fde.py` | ✅ | POST /fde/project/freeze — 中止项目冻结归档（§7.4） | 2026-07-18 |
| **security_preflight** | `scripts/security_preflight.sh` | ✅ | FDE 安全行前检查脚本（§1.4） | 2026-07-18 |
| **sanitize_logs** | `scripts/sanitize_logs.sh` | ✅ | FDE 日志脱敏脚本（§1.4） | 2026-07-18 |
| DB Utils (SQLite连接池) | `harness/infrastructure/db_utils.py` | ✅ | 统一WAL+busy_timeout连接层，冷路径context manager + 热路径persistent conn | 已合入 |

---

## 十一、扩展与学习

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| cmm_graduation | `harness/learning/cmm_graduation.py` | ✅ | 自动同步 | 已合入 |
| integration | `harness/integration.py` | ✅ | 自动同步 | 已合入 |
| toolsets | `harness/tools/toolsets.py` | ✅ | 自动同步 | 已合入 |
| deepseek | `apps/finetune/providers/deepseek.py` | ✅ | 自动同步 | 已合入 |
| skill_lint_scan | `harness/maintenance/skill_lint_scan.py` | ✅ | 自动同步 | 已合入 |
| model_feedback | `harness/routing/model_feedback.py` | ✅ | 自动同步 | 已合入 |
| execution_context | `harness/kernel/execution_context.py` | ✅ | 自动同步 | 已合入 |
| wiki_context | `harness/syscalls/wiki_context.py` | ✅ | 自动同步 | 已合入 |
| trajectory_scorer | `harness/training/trajectory_scorer.py` | ✅ | 自动同步 | 已合入 |
| rl_trainer | `harness/training/rl_trainer.py` | ✅ | 自动同步 | 已合入 |
| value_calculator | `harness/finance/value_calculator.py` | ✅ | 自动同步 | 已合入 |
| distillation | `harness/training/distillation.py` | ✅ | 自动同步 | 已合入 |
| full_training | `harness/training/full_training.py` | ✅ | 自动同步 | 已合入 |
| _json | `harness/document/converters/_json.py` | ✅ | 自动同步 | 已合入 |
| _eml | `harness/document/converters/_eml.py` | ✅ | 自动同步 | 已合入 |
| _csv | `harness/document/converters/_csv.py` | ✅ | 自动同步 | 已合入 |
| _markdown | `harness/document/converters/_markdown.py` | ✅ | 自动同步 | 已合入 |
| _html | `harness/document/converters/_html.py` | ✅ | 自动同步 | 已合入 |
| playbook | `harness/learning/playbook.py` | ✅ | 自动同步 | 已合入 |
| proposal_store | `harness/learning/proposal_store.py` | ✅ | 自动同步 | 已合入 |
| action_bridge | `harness/actions/action_bridge.py` | ✅ | 自动同步 | 已合入 |
| answer_generator | `harness/generation/answer_generator.py` | ✅ | 自动同步 | 已合入 |
| model_tier_router | `harness/routing/model_tier_router.py` | ✅ | 自动同步 | 已合入 |
| prompt_optimizer | `harness/optimization/prompt_optimizer.py` | ✅ | 自动同步 | 已合入 |
| strategy_tracker | `harness/optimization/strategy_tracker.py` | ✅ | 自动同步 | 已合入 |
| goal_generator | `harness/optimization/goal_generator.py` | ✅ | 自动同步 | 已合入 |
| search_engine | `harness/optimization/search_engine.py` | ✅ | 自动同步 | 已合入 |
| goal_executor | `harness/optimization/goal_executor.py` | ✅ | 自动同步 | 已合入 |
| tool_bootstrap | `harness/optimization/tool_bootstrap.py` | ✅ | 自动同步 | 已合入 |
| dynamic_orchestrator | `harness/coordination/dynamic_orchestrator.py` | ✅ | 自动同步 | 已合入 |
| swarm_broker | `harness/coordination/swarm_broker.py` | ✅ | 自动同步 | 已合入 |
| cost_tracker | `harness/optimization/cost_tracker.py` | ✅ | 自动同步 | 已合入 |
| integrator | `harness/multimodal/integrator.py` | ✅ | 自动同步 | 已合入 |
| kanban_engine | `harness/coordination/kanban_engine.py` | ✅ | 自动同步 | 已合入 |
| wake_agent | `harness/monitoring/wake_agent.py` | ✅ | 自动同步 | 已合入 |
| tool_evolution | `harness/optimization/tool_evolution.py` | ✅ | 自动同步 | 已合入 |
| voice_loop | `harness/multimodal/voice_loop.py` | ✅ | 自动同步 | 已合入 |
| sla_tracker | `harness/security/sla_tracker.py` | ✅ | 自动同步 | 已合入 |
| cron_loader | `harness/scheduler/cron_loader.py` | ✅ | 自动同步 | 已合入 |
| wake_scheduler | `harness/scheduler/wake_scheduler.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| ExperienceVector | `harness/learning/experience_vector.py` | ✅ | PipelineTrace→Embedding→语义检索 | 已合入 |
| ToolDriftDetector | `harness/learning/tool_drift_detector.py` | ✅ | 4类漂移检测(struct/field/latency/error) + 重放校验自适应 | 已合入 |
| ImmuneMemory | `harness/security/immune_memory.py` | ✅ | 三级渐进拦截(>0.95拦截/>0.88防御前缀/<0.88放行) + 防御Skill自动生成 | 已合入 |
| SkillSimulator | `harness/learning/skill_simulator.py` | ✅ | Docker沙盒预检，pass≥80% | 已合入 |
| SFT AutoTrigger | `harness/training/auto_trigger.py` | ✅ | ≥100条+quality≥0.8→自动生成SFT数据集 | 已合入 |
| HITL 反馈记忆回路 | `harness/infrastructure/approval/manager.py:428` + `harness/learning/__init__.py:150` | ✅ | 拒绝原因→ExperienceVectorCache→enrich_skill_draft 错题本检索 | 已合入 |
| SuccessGeneralizer | `harness/learning/success_generalizer.py` | ✅ | ≥85% hot skill → 参数抽象 → 跨运行验证 → GeneralizedRule | 已合入 |
| Feedback Loops | `feedback_loops/` | ✅ | local + prod + push 三通道 | 已合入 |
| ImplicitFeedback | `services/implicit_feedback.py` | ✅ | 复制/选中/追问/重复 行为信号 | 已合入 |
| Meta-Agent | `harness/meta/` | ✅ | 远瞻探索，默认关闭（设 `AIPLAT_META_AGENT_ENABLED=true` 激活） | 已合入 |
| On-Error Reflector | `harness/infrastructure/hooks/on_error_reflector.py` | ✅ | 连续2次tool error→LLM反思（事后） | 已合入 |
| DevilAdvocate 前置预判 | `harness/infrastructure/hooks/devil_advocate.py` | ✅ | PRE_ACT Hook：执行前模拟失败场景，高风险工具注入警告（事前） | 已合入 |
| 自迭代闭环 | `on_error_reflector → AutoLearner → SkillSimulator → Approval → test_case_generation` | ✅ | 6模块串联：失败→分析→Draft→预检→审批→测试，人只确认方向 | 已合入 |
| Skill 质量离线基准 | `tests/eval/test_skill_quality.py` + `gold_skill_quality.json` | ✅ | 10任务×5领域×3条件 (No/Cured/Auto)，对标 SkillsBench | 已合入 |
| CMM 观察层 | `harness/memory/pattern_accumulator.py` | ✅ | 工具序列指纹 + 跨会话累积 + 频次≥3触发 | 已合入 |
| MetaClaw 双轨综合 | `harness/memory/pattern_accumulator.py:compare_success_failure()` | ✅ | 成功+失败轨迹比较 + 提取路径差异 | 已合入 |
| 集体进化引擎 | `harness/learning/skill_evolver.py` | ✅ | 跨租户模式扫描 + 匿名化 + tenant_threshold≥2 | 已合入 |
| Agent SDK | `aiplat-sdk/` | ✅ | L1/L2/L3 三级可用，`pip install aiplat-sdk` 可安装，待IDE集成 | 已合入 |
| VS Code 插件 | `aiplat-vscode/` | ✅ | SSE 流式聊天 + 代码选择发送 + Apply fix + 隐式反馈，可打包 .vsix | 已合入 |
| SpecLifecycle | `harness/models/spec_lifecycle.py` | ✅ | Spec 版本状态机: DRAFT→PENDING→EXECUTING→REVIEW→STABLE→ARCHIVED | 已合入 |
| FeedbackRadar | `harness/learning/feedback_radar.py` | ✅ | 5种用户信号检测→Spec调整建议 (boundary/direction/overload/drift/cold) | 已合入 |
| InlineSelfCorrect | `harness/execution/loop/_facade.py` | ✅ | 内联自纠错: PostObserve→reflection-critic→reflection-improve, 1次/步 | 已合入 |
| MCPToolLazyLoad | `apps/mcp/client.py` | ✅ | MCP工具延迟加载: 启动仅加载名称, Schema首次调用时按需获取, AIPLAT_MCP_LAZY_LOAD控制 | 已合入 |
| PromptCaching | `harness/syscalls/llm.py` | ✅ | Prompt Caching: stable消息cache_control注入 + SHA256跨会话持久化(~/.aiplat/cache/), AIPLAT_PROMPT_CACHE_ENABLED控制 | 已合入 |
| ThreeLayerPermissions | `gates/policy_gate.py:_match_tool_rule` | ✅ | 三层权限(deny>ask>allow)+参数级fnmatch匹配 | 已合入 |
| SubagentIsolation | `subagent/coordinator.py:isolate_context` | ✅ | 子代理上下文隔离: 仅传摘要+只读模式, 默认开启 | 已合入 |
| FileBasedMemory | `harness/memory/file_store.py` | ✅ | 文件记忆: Markdown双写(MEMORY.md+日期文件)+SQLite索引, 人类可验证 | 已合入 |
| AutoMemory | `harness/memory/file_store.py:auto_save_learning` + `harness/memory/manager.py:save_interaction` | ✅ | 自动记忆: 纠正≥2次/10轮交互自动保存到文件, AIPLAT_AUTO_LEARNING_ENABLED控制 | 已合入 |
| PluginSlot | `apps/plugins/manager.py` | ✅ | 插件Slot: 同类别单一活跃, 旧插件状态归档 | 已合入 |
| StageSandbox (子进程) | `harness/execution/sandbox.py:StageSandbox` | ✅ | 进程级沙箱: 资源限制(cpu/memory/processes)+凭证隔离+超时控制 | 已合入 |
| DockerSandbox (容器) | `harness/execution/sandbox.py:DockerSandbox` | ✅ | 容器级沙箱: Docker隔离(--network none)+fallback到子进程, sandbox_mode='docker' | 已合入 |
| 五维 ROI 计算 | `harness/finance/value_calculator.py:compute_monthly()` | ✅ | 效率/质量/安全/创新/体验五维价值计量, 月度聚合 | 已合入 |
| 三受众翻译 | `harness/finance/value_calculator.py:translate_for()` | ✅ | CEO(战略+目标)/CFO(成本+ROI)/PM(准确度+满意度) 三视角自动翻译 | 已合入 |
| BusinessGoalTracker | `harness/finance/value_calculator.py` | ✅ | 目标设定→进度追踪→偏离预警, on_track/at_risk/behind 实时状态 | 已合入 |
| GoalAwareRouter | `harness/execution/dynamic_router.py:GoalAwareRouter` | ✅ | 业务目标感知调度: Speed(提速)/Quality(反思)/Safety(HITL) 策略自动切换 | 已合入 |
| KPIAgent 监控 | `harness/agents/kpi_agent.py` | ✅ | 自动追踪 KPI → 偏离预警 → strategy_suggest, EvolutionEngine Step12 触发 | 已合入 |
| Value Center API | `core/api/routers/value.py` + `core/schemas_value.py` | ✅ | CRUD endpoints: `/all/goals`, `/all/goals/{id}`, `/all/goals/{id}/trend`, `/all/strategy`; Schemas: `GoalCreateRequest`, `GoalUpdateRequest`, `GoalSourceConfigRequest` | 已合入 |
 `core/api/routers/value.py` | ✅ | `get_all_goals`, `create_goal_all`, `update_goal_all`, `delete_goal_all`, `create_business_goal`, `get_goal_trend_all`, `get_strategy_all` + 4 REST endpoints (`/all/goals`, `/all/strategy`, `/all/goals/{id}`, `/all/goals/{id}/trend`) | 已合入 |
| Proposal 工作流 | `harness/learning/proposal_store.py` | ✅ | draft→pending_approval→approved→merged/rejected + branch/merge语义 (Palantir AIP对齐) | 已合入 |
| FDEBuilderOrchestrator | `apps/fde/orchestration/builder.py` | ✅ | FDE 对话式 Agent 构建：_clarify()→DomainRouter→SkillRegistry→auto_fill→Builder.deploy_app() | 2026-07-17 |
| Agent 可发现性 | `wiki.py:/ontology/{domain}/discover` | ✅ | Agent动态查询 ObjectTypes/Links/Actions/Interfaces，自主发现操作能力 | 已合入 |

---

## 十二、Gate 系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| ContextGate | `harness/infrastructure/gates/context_gate.py` | ✅ | Token预算强制执行 + 上下文去重/陈旧校验 | 已合入 |
| SchemaGate | `harness/infrastructure/gates/schema_gate.py` | ✅ | JSON Schema 强制校验，Agent输出在下游阶段前验证 | 已合入 |
| ResilienceGate | `harness/infrastructure/gates/resilience_gate.py` | ✅ | 可配置重试策略 + 回退链 + 熔断器包装 | 已合入 |
| TraceGate | `harness/infrastructure/gates/trace_gate.py` | ✅ | 最佳努力追踪span包装，syscall审计 | 已合入 |
| SandboxGate | `harness/infrastructure/gates/sandbox_gate.py` | ✅ | 沙箱执行门 + 结果校验 | 已合入 |
| ErrorTranslator | `harness/infrastructure/gates/error_translator.py` | ✅ | 7级分类流水线 + 15种FailoverReason + 4 recovery flags + 智能重试 | 已合入 |
| ToolResult 结构化错误诊断 | `syscalls/tool.py:_enrich_tool_error` + `error_translator.py:recovery_hint_for` | ✅ | 工具失败经 ErrorTranslator 分类填充 error_type/exit_code/stderr/recovery_hint，注入 LLM observation `[DIAGNOSTICS]` | 2026-07-06 |
| ExecutionSnapshot 自助恢复 API | `platform/api/routers/execution_snapshots.py` + `core_facade.py:list/get/compare/restore_execution_snapshot` | ✅ | `/platform/execution/snapshots/*` list/get/compare/restore，经 CoreFacade 暴露 snapshot.py 存量能力 + RBAC 门禁 | 2026-07-06 |
| FileCheckpoint 文件系统物理安全网 | `harness/execution/file_checkpoint.py` + `syscalls/file.py:_checkpoint_before_overwrite` | ✅ | sys_file_write/edit 覆盖前自动备份文件内容(hash去重+大文件跳过+保留50)，`/platform/execution/file-checkpoints/*` 自助恢复 | 2026-07-06 |
| RateLimitTracker | `harness/infrastructure/gates/rate_limit_tracker.py` | ✅ | 滑动窗口 + 指数退避(max 120s) + asyncio.Lock | 已合入 |
| SemanticGate | `harness/infrastructure/gates/semantic_gate.py` | ✅ | 3层语义合规验证(entity/value/relation) + warn/audit/block模式 | Phase 11.2 |
| CompletionChecklistGate | `harness/infrastructure/gates/completion_gate.py` | ✅ | 2层完成度验证(固定模板+LLM深层) + 低置信度重试闭环 | Phase 15 |
| 统一出口门控层 | `harness/integration.py` | ✅ | 8 gates在统一出口: Completion+SemanticGate+self_review+Hallucination+cache+pattern+memory+action_bridge | Phase 15 |
| 工具白名单 | `llm_profile.yaml` + `model_tier_router.py` + `integration.py` | ✅ | T1-T5每层max_tools限缩, 低复杂度→少工具 | Phase 16 |
| 代码熵检测器 | `harness/knowledge/code_entropy_detector.py` | ✅ | 文件长度/函数数/TODO标记 3维度评分, GET /diagnostics/code-entropy | Phase 17 |
| 本体感知路由 | `harness/execution/router.py` | ✅ | _ontology_routing_hint: 实体名匹配→邻居计数→graph/loop抉择 | Phase 11.1 |
| CrossValidationGate | `harness/infrastructure/gates/cross_validation_gate.py` | ✅ | 3层跨域验证(设备↔工艺↔质量) + 52/50跨域连接已达标 | Phase 11.3 |

---

## 十三、评估系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| EvaluationRunner | `harness/evaluation/eval_runner.py` | ✅ | 全流水线评估执行引擎 | 已合入 |
| EvalMetricsEngine | `harness/evaluation/eval_metrics.py` | ✅ | 从 ExecutionStore trace 计算综合评估指标 | 已合入 |
| HallucinationTracker | `harness/evaluation/hallucination_tracker.py` | ✅ | NLI事实核查 + GraphIndex图边验证 | 已合入 |
| RAG Evaluator | `harness/evaluation/rag_evaluator.py` | ✅ | Ragas: faithfulness/relevancy/precision/recall | 已合入 |
| DriftDetector | `harness/evaluation/drift_detector.py` | ✅ | 零成本推理质量下降检测 (confidence/error/stagnation) | 已合入 |
| EvaluationWorkbench | `harness/evaluation/workbench.py` | ✅ | 标准化评估报告 + 阈值门 + 制品持久化 | 已合入 |
| AB Optimizer | `harness/evaluation/ab_optimizer.py` | ✅ | A/B 测试优化 | 已合入 |
| CoverageGate | `harness/evaluation/coverage_gate.py` | ✅ | 覆盖率阈值强制执行 | 已合入 |
| GraphDiff | `harness/evaluation/graph_diff.py` | ✅ | 本体图状态对比，回归检测 | 已合入 |
| EvidenceDiff | `harness/evaluation/evidence_diff.py` | ✅ | 证据级差异计算 | 已合入 |
| ScoringDimensions | `harness/evaluation/dimensions.py` | ✅ | 配置驱动评分维度注册 | 已合入 |
| EvalTypes | `harness/evaluation/eval_types.py` | ✅ | 类型化评估结果Schema | 已合入 |
| 工具选择离线评估 | `tests/eval/test_tool_selection.py` + `gold_tool_selection.json` | ✅ | 15 case gold + compute_tool_quality + CI 回归 + 混淆矩阵 + 安全边界 + 覆盖率检查 | 已合入 |

---

## 十四、MCP 协议

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| MCP JSON-RPC 2.0 | `apps/mcp/protocol.py` | ✅ | 完整 MCP 协议实现 (init, tools/list, tools/call) | 已合入 |
| MCP HTTP+SSE Server | `apps/mcp/server.py` | ✅ | 远程工具暴露服务 | 已合入 |
| MCP Stdio Transport | `apps/mcp/local_tools_server.py` | ✅ | 工作区工具暴露给 AI 编辑器 | 已合入 |
| MCP Runtime Wiring | `apps/mcp/runtime.py` | ✅ | MCP Server → ToolRegistry 运行时绑定 + PolicyGate | 已合入 |
| MCP Client Manager | `apps/mcp/client.py` | ✅ | 多服务端客户端连接生命周期管理 | 已合入 |
| MCP Production Policy | `core/mcp/prod_policy.py` | ✅ | 生产安全策略 (risk level, allowed tools) | 已合入 |

---

## 十四附、A2A 协议 (Agent-to-Agent)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| Agent Card | `apps/a2a/agent_card.py` | ✅ | 自动枚举 Skill/Tool 能力 + JSON-LD 上下文 | 已合入 |
| Task Send | `apps/a2a/server.py` | ✅ | POST /tasks → 复用 core_chat 执行 | 已合入 |
| Task Get | `apps/a2a/server.py` | ✅ | GET /tasks/{id} → 复用 ExecutionStore | 已合入 |
| Task Stream | `apps/a2a/server.py` | ✅ | SSE /tasks/{id}/stream → 复用 ReActLoop | 已合入 |
| Task Cancel | `apps/a2a/server.py` | ✅ | POST /tasks/{id}/cancel | 已合入 |
| Task Artifacts | `apps/a2a/server.py` | ✅ | GET /tasks/{id}/artifacts → 复用 TaskSkills | 已合入 |
| Task List | `apps/a2a/server.py` | ✅ | GET /tasks 任务列表 | 已合入 |

---

## 十五、文档智能

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| Document Classifier | `apps/document_intelligence/classifier.py` | ✅ | 文档类型分类 + KB provider集成 | 已合入 |
| Document Summarizer | `apps/document_intelligence/summarizer.py` | ✅ | LLM 文档摘要，可配置策略 | 已合入 |
| Structured Chunker | `apps/document_intelligence/chunking/structured_chunker.py` | ✅ | 内容感知结构化分块 + 策略自动选择 | 已合入 |
| Question Analysis | `apps/document_intelligence/question_analysis.py` | ✅ | 问题分类与分解，检索策略决策 | 已合入 |
| ConverterRegistry | `harness/document/protocol.py:get_document_registry()` | ✅ | 统一文档解析调度，13 个 built-in converter，优先级链 + 降级链 | 已合入 |
| PDF Converter | `harness/document/converters/_pdf.py` | ✅ | markitdown→pdfplumber→raw text 三级降级 + 文件头检测 | 已合入 |
| DOCX Converter | `harness/document/converters/_docx.py` | ✅ | markitdown→python-docx→raw text 降级 + table 保留 | 已合入 |
| PPTX Converter | `harness/document/converters/_pptx.py` | ✅ | markitdown→python-pptx→raw text 降级 | 已合入 |
| XLSX Converter | `harness/document/converters/_xlsx.py` | ✅ | markitdown→raw text 降级 | 已合入 |
| Audio/Video Converter | `harness/document/converters/_audio.py` `_video.py` | ✅ | Whisper 转录，via ffmpeg extract | 已合入 |
| Image Converter | `harness/document/converters/_image.py` | ✅ | Tesseract/PaddleOCR 文字提取 | 已合入 |
| 多格式统一解析 | `harness/document/parsers.py` → `protocol.py` | ✅ | 12 种格式 → 13 个 DocumentConverter → 统一 DocumentElement | 已合入 |
| Azure DI 集成 | `harness/document/converters/_pdf.py:_convert_via_azure_di()` | ✅ | 环境变量驱动：设 `AIPLAT_AZURE_DOCINTEL_ENDPOINT` 即激活，自动降级到本地 | 已合入 |
| DocumentConverter 协议 | `harness/document/protocol.py` | ✅ | ABC: accepts() + convert()，13 个内置 converter，优先级调度 | 已合入 |
| ConverterRegistry | `harness/document/protocol.py:get_document_registry()` | ✅ | 全局单例，单点派发，消除 5 处硬编码 dispatch | 已合入 |
| 内容级文件检测 | `harness/document/protocol.py:_guess_extension_from_header()` | ✅ | 文件头魔数检测，扩展名与内容矛盾时自动修正 | 已合入 |
| 完整降级链 | `harness/document/protocol.py:convert_with_fallback()` | ✅ | 遍历所有 converter → 异常聚合 → 兜底 raw text | 已合入 |
| 结构角色检测 | `harness/document/protocol.py:detect_structure_role()` | ✅ | h1-h6/table/list_item/caption/code_block/paragraph 自动识别 | 已合入 |
| 插件系统 | `harness/document/protocol.py:_load_plugins()` | ✅ | entry_points group=aiplat.document_converter，零侵入扩展 | 已合入 |
| 集中格式映射 | `api/facades/kb_facade.py:_KIND_TO_EXT` | ✅ | 40+ 同义词 → 规范扩展名，统一 kb_facade/core_facade/routes | 已合入 |
| Whisper 双后端切换 | `harness/document/transcriber.py:77-99` | ✅ | faster-whisper ↔ openai-whisper 运行时自动切换 | 已合入 |
| Image OCR | `harness/document/ocr.py` | ✅ | Tesseract/PaddleOCR 关键帧文字提取 | 已合入 |
| Document Chunker | `harness/document/chunker.py` | ✅ | 多策略分块 (fixed/semantic/recursive) + overlap控制 | 已合入 |
| 多格式解析器 | `harness/document/parsers.py` | ✅ | DOCX/PDF/MD/HTML/CSV/Audio/Image/Video/EML/JSON → 统一元素，已升级为协议化架构 | 已合入 |

---

## 十六、工具生态

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| Browser 自动化 | `apps/tools/browser.py` + `browser_test_engine.py` | ✅ | Playwright 全浏览器自动化，BFS遍历/RPA/截图 | 已合入 |
| Test Case Generator | `apps/tools/test_case_generator.py` | ✅ | 页面分析 → 结构化 Excel 测试用例 | 已合入 |
| SysGraph Tools (5) | `apps/tools/sysgraph_tools.py` | ✅ | context/search/impact/callers/node 代码图查询 | 已合入 |
| Draw.io Generator | `harness/syscalls/drawio_gen.py` | ✅ | LLM→draw.io XML 图表生成，零外部依赖 | 已合入 |
| Code Intelligence | `harness/syscalls/code_intel_syscall.py` | ✅ | 预构建依赖图SQLite查询 | 已合入 |
| Docker Exec Driver | `apps/exec_drivers/docker.py` | ✅ | Docker 容器内沙箱执行 | 已合入 |
| SSH Exec Driver | `apps/exec_drivers/ssh.py` | ✅ | SSH 远程代码执行 | 已合入 |
| Local Exec Driver | `apps/exec_drivers/local.py` | ✅ | 本地进程执行 + 资源限制 | 已合入 |
| BaseTool Framework | `apps/tools/base.py` | ✅ | ToolMetadata/BaseTool/CalculatorTool/ToolSearch 基础框架 | 已合入 |
| CodeExecutionTool | `apps/tools/code.py` | ✅ | 代码执行工具 | 已合入 |
| DatabaseTool | `apps/tools/database.py` | ✅ | 数据库操作工具 | 已合入 |
| HTTP Tool | `apps/tools/http.py` | ✅ | HTTP 请求工具 | 已合入 |
| KB Tools | `apps/tools/kb_tools.py` | ✅ | 知识库 CRUD 工具集，含文档入库自动域分类(DomainRouter.classify)(HMESI Step 2) | 已合入 |
| KB Auto-Domain | `apps/tools/kb_tools.py:35-58` | ✅ | 文档入库时自动检测域标签：默认collection下读取文档片段→DomainRouter.classify→路由到对应collection | 2026-07-11 |
| MCP Adapter | `apps/tools/mcp_adapter.py` | ✅ | MCP→Tool 适配器 | 已合入 |
| Permission Tool | `apps/tools/permission.py` | ✅ | 权限管理工具 | 已合入 |
| Recaller Tool | `apps/tools/recaller.py` | ✅ | 记忆召回工具 | 已合入 |
| Repo Tool | `apps/tools/repo.py` | ✅ | 代码仓库操作工具 | 已合入 |
| Skill Tools | `apps/tools/skill_tools.py` + `skill_script_tools.py` | ✅ | Skill 管理 + 脚本化工具集 | 已合入 |
| WebFetch Tool | `apps/tools/webfetch.py` | ✅ | 网页抓取工具 | 已合入 |
| Tool Discovery | `apps/tools/discovery.py` | ✅ | 工具自动发现 | 已合入 |

---

## 十七、微调系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| MLX LoRA Trainer | `harness/finetune/mlx_trainer.py` | ✅ | Apple Silicon 本地 QLoRA 微调，MPS后端 | 已合入 |
| GGUF Exporter | `harness/finetune/gguf_exporter.py` | ✅ | 模型导出 GGUF 格式 | 已合入 |
| Fine-tune Job Manager | `harness/finetune/job_manager.py` | ✅ | 微调任务生命周期管理 | 已合入 |
| SFT Dataset Manager | `harness/finetune/dataset_manager.py` | ✅ | SFT 数据集准备/版本化/存储 | 已合入 |
| RLOOUpdater | `harness/training/rl_trainer.py` | ✅ | RLOO 优势值更新: EMA 平滑, 多目标权重自适应, clip_range=0.2 | 已合入 |
| CodeTestReward | `harness/training/rl_trainer.py` | ✅ | 代码测试奖励: 从 PipelineState 提取 test pass_rate 自动评分 | 已合入 |
| VerifierReward | `harness/training/rl_trainer.py` | ✅ | 验证器奖励: LLM 输出正确性评分, 语义一致性检查 | 已合入 |
| Online Rollout | `harness/training/rl_trainer.py:_rollout_online` | ✅ | 在线策略探索: Semaphore(2), timeout(300s), 深拷贝状态隔离 | 已合入 |
| SFT→RL 桥接 | `harness/finetune/job_manager.py:239` → `rl_trainer.py:_detect_latest_sft_model` | ✅ | SFT 完成→~/.aiplat/sft_models/latest.json 信号→RL 自动检测最新模型 | 已合入 |
| TrajectoryScorer 四维 | `harness/training/trajectory_scorer.py` | ✅ | 正确性+效率+优雅性+可学习性四维评分, score_batch 批量处理 | 已合入 |
| 混合采样 | `harness/training/auto_trigger.py:_mixed_sample_by_task_type` | ✅ | coding/terminal/qa/general 分组均匀采样, 防止单一来源主导 | 已合入 |
| 可模仿性过滤 | `harness/training/auto_trigger.py:learnability` | ✅ | 学生模型必须能模仿教师轨迹, is_learnable() 预筛选 | 已合入 |

---

## 十八、部署与灰度

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| Skill Canary 部署 | `harness/deployment/canary.py` | ✅ | Canary/A-B/Shadow/Auto-Rollback 四种模式 | 已合入 |
| Canary Escalation | `harness/canary/escalation.py` | ✅ | 确定性灰度升级 + 变更控制集成 | 已合入 |
| Canary Recommendation | `harness/canary/recommendation.py` | ✅ | 灰度比例推荐引擎 | 已合入 |
| Config Hot Reload | `harness/infrastructure/hot_reload.py` | ✅ | 文件监听回调 + 缓存失效 | 已合入 |

---

## 十九、运行时干预

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| Howl Intervention | `harness/intervention/howl.py` | ✅ | Agent 停滞/退化检测 + redirect/clarify/fallback策略 | 已合入 |
| RunState Restatement | `harness/restatement/run_state.py` | ✅ | 结构化/版本化/人可编辑的进度制品 | 已合入 |

---

## 二十、Arena & 调度

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| Darwin Arena | `harness/arena/arena.py` | ✅ | 多Agent竞技，Bayesian Elo评分 + Champion晋升 | 已合入 |
| Arena Regression | `harness/arena/regression.py` | ✅ | Champion 能力退化检测 | 已合入 |
| Cron Scheduler | `harness/scheduler/cron.py` | ✅ | 定时任务调度 | 已合入 |
| AutoSmoke Scheduler | `harness/smoke/autoscheduler.py` | ✅ | 自动冒烟测试调度执行 | 已合入 |

---

## 二十一、平台治理

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
| authenticator | `aiPlat-platform/auth/authenticator.py` | ✅ | 自动同步 | 已合入 |
| pdf_render | `aiPlat-platform/kb/poc/pdf_render.py` | ✅ | 自动同步 | 已合入 |
| prompt_app | `api/routers/prompt_app.py` | ✅ | 自动同步 | 已合入 |
| entropy | `api/routers/entropy.py` | ✅ | 自动同步 | 已合入 |
| roles | `api/routers/roles.py` | ✅ | 角色CRUD + `override_strategy` + `update_agent_role` | 已合入 |
| Roles Schemas | `core/schemas_roles.py` | ✅ | `RoleAgentUpdateRequest` + `RoleStrategyOverrideRequest` | 2026-07-18 |
| workspace_packages | `api/routers/workspace_packages.py` | ✅ | 自动同步 | 已合入 |
| workspace_agents | `api/routers/workspace_agents.py` | ✅ | 自动同步 | 已合入 |
| wiki_ontology_patterns | `api/routers/wiki_ontology_patterns.py` | ✅ | 自动同步 | 已合入 |
| wiki_ontology_domains | `api/routers/wiki_ontology_domains.py` | ✅ | 自动同步 | 已合入 |
| fde_domain_ops | `api/routers/fde_domain_ops.py` | ✅ | 自动同步 | 已合入 |
| fde_pipeline | `api/routers/fde_pipeline.py` | ✅ | 自动同步 | 已合入 |
| fde_handover_v2 | `api/routers/fde_handover_v2.py` | ✅ | 自动同步 | 已合入 |
| fde_sessions_compare | `api/routers/fde_sessions_compare.py` | ✅ | 自动同步 | 已合入 |
| mcp_admin | `api/routers/mcp_admin.py` | ✅ | 自动同步 | 已合入 |
| fde_sessions_v2 | `api/routers/fde_sessions_v2.py` | ✅ | 自动同步 | 已合入 |
| wiki_ontology_sql | `api/routers/wiki_ontology_sql.py` | ✅ | 自动同步 | 已合入 |
| fde_diagnostics_v2 | `api/routers/fde_diagnostics_v2.py` | ✅ | 自动同步 | 已合入 |
| wiki_proposals | `api/routers/wiki_proposals.py` | ✅ | 自动同步 | 已合入 |
| fde_overview | `api/routers/fde_overview.py` | ✅ | 自动同步 | 已合入 |
| fde_validate | `api/routers/fde_validate.py` | ✅ | 自动同步 | 已合入 |
| wiki_markings | `api/routers/wiki_markings.py` | ✅ | 自动同步 | 已合入 |
| wiki_ontology_engine | `api/routers/wiki_ontology_engine.py` | ✅ | 自动同步 | 已合入 |
| fde_quality_summary | `api/routers/fde_quality_summary.py` | ✅ | 自动同步 | 已合入 |
| wiki_field_security | `api/routers/wiki_field_security.py` | ✅ | 自动同步 | 已合入 |
| fde_acceptance | `api/routers/fde_acceptance.py` | ✅ | 自动同步 | 已合入 |
| wiki_health_quality | `api/routers/wiki_health_quality.py` | ✅ | 自动同步 | 已合入 |
| wiki_writeback | `api/routers/wiki_writeback.py` | ✅ | 自动同步 | 已合入 |
| fde_trends | `api/routers/fde_trends.py` | ✅ | 自动同步 | 已合入 |
| fde_bootstrap | `api/routers/fde_bootstrap.py` | ✅ | 自动同步 | 已合入 |
| wiki_evidence | `api/routers/wiki_evidence.py` | ✅ | 自动同步 | 已合入 |
| fde_manuals | `api/routers/fde_manuals.py` | ✅ | 自动同步 | 已合入 |
| wiki_semantic_suggestions | `api/routers/wiki_semantic_suggestions.py` | ✅ | 自动同步 | 已合入 |
| wiki_ontology_export | `api/routers/wiki_ontology_export.py` | ✅ | 自动同步 | 已合入 |
| wiki_learning | `api/routers/wiki_learning.py` | ✅ | 自动同步 | 已合入 |
| fde_delivery | `api/routers/fde_delivery.py` | ✅ | 自动同步 | 已合入 |
| fde_governance | `api/routers/fde_governance.py` | ✅ | 自动同步 | 已合入 |
| fde_ask | `api/routers/fde_ask.py` | ✅ | 自动同步 | 已合入 |
| fde_maintenance | `api/routers/fde_maintenance.py` | ✅ | 自动同步 | 已合入 |
| fde_reports | `api/routers/fde_reports.py` | ✅ | 自动同步 | 已合入 |
| wiki_loop_triggers | `api/routers/wiki_loop_triggers.py` | ✅ | 自动同步 | 已合入 |
| wiki_scenes | `api/routers/wiki_scenes.py` | ✅ | 自动同步 | 已合入 |
| diagnostics_capability | `api/routers/diagnostics_capability.py` | ✅ | 自动同步 | 已合入 |
| fde_dashboard_v2 | `api/routers/fde_dashboard_v2.py` | ✅ | 自动同步 | 已合入 |
| schemas_policy | `aiPlat-platform/auth/schemas_policy.py` | ✅ | 自动同步 | 已合入 |
| learning_releases | `api/routers/learning_releases.py` | ✅ | 自动同步 | 已合入 |
| learning_misc | `api/routers/learning_misc.py` | ✅ | 自动同步 | 已合入 |
| prompt_templates | `api/routers/prompt_templates.py` | ✅ | 自动同步 | 已合入 |
| learning_autocapture | `api/routers/learning_autocapture.py` | ✅ | 自动同步 | 已合入 |
| prompt_eval | `api/routers/prompt_eval.py` | ✅ | 自动同步 | 已合入 |
|------|------|:---:|------|------|
| Change Control | `platform/api/routers/change_control.py` | ✅ | 变更请求跟踪/审计/autosmoke强制执行 | 已合入 |
| Tenant Onboarding | `platform/api/routers/onboarding.py` | ✅ | 租户引导：LLM配置/执行后端/密钥迁移/信任密钥 | 已合入 |
| Quota Manager | `platform/governance/quota/quota_manager.py` | ✅ | 资源配额管理与强制执行 | 已合入 |
| Rate Limiter | `platform/governance/rate_limit/limiter.py` | ✅ | 单进程 in-memory + Redis 分布式令牌桶（原子Lua脚本） | 已合入 |
| Billing Meter | `platform/billing/meter.py` | ✅ | 用量计量与计费结算 | 已合入 |
| MQ WriteBack 适配器 | `harness/knowledge/knowledge_writeback.py` | ✅ | Kafka/RabbitMQ 消息队列写回 + none降级LOG_ONLY | 已合入 |
| KB Intelligence | `platform/kb/intelligence/service.py` | ✅ | URL抓取/HTML→text/格式检测/视频URL转录 | 已合入 |
| MinerU PDF 提取 | `platform/kb/poc/mineru_extract.py` | ✅ | 结构化PDF内容提取 + 表格 | 已合入 |
| Video Retrieval | `platform/kb/intelligence/video_retrieval.py` | ✅ | 时间索引视频内容检索 + 转录对齐 | 已合入 |
| Builder Project Service | `platform/builder/builder_project_service.py` | ✅ | 全功能应用项目CRUD | 已合入 |
| 租户自助入驻 | `api/rest/routes.py` (register/verify-email) | ✅ | 注册→邮箱验证→激活→返回API Key | 已合入 |
| 租户自助门户 | `api/rest/routes.py` (tenant/*) | ✅ | 仪表板/API Key管理/用量/计费面板 | 已合入 |
| 运营大盘 | `api/rest/routes.py` (ops/overview) | ✅ | 跨租户聚合：租户数/Token/活跃度，platform_admin only | 已合入 |
| 市场发布工作流 | `api/rest/routes.py` (marketplace/publish) | ✅ | 提交→SkillSimulator预检→审核，含test_result | 已合入 |
| MessagingGateway | `harness/infrastructure/gateway/messaging.py` | ✅ | 飞书/企业微信/Slack三渠道通知，Pipeline失败自动广播 | 已合入 |

---

## 二十二、Infra 基础设施

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| Model Health Checker | `infra/management/model/health_checker.py` | ✅ | 模型可用性/延迟/质量健康监控 | 已合入 |
| Local Model Scanner | `infra/management/model/local_model_scanner.py` | ✅ | 自动发现 Ollama/LM Studio/vLLM/oMLX 本地模型 | 已合入 |
| Model Quality Validator | `infra/management/model/quality_validator.py` | ✅ | 输出质量验证 + 基准评分 | 已合入 |
| Model Latency Tracker | `infra/management/model/latency_tracker.py` | ✅ | 每模型延迟跟踪 + 滑动窗口统计 | 已合入 |
| Multi-Backend Cache | `infra/cache/` | ✅ | Redis/Memory/File 三后端缓存 + 工厂模式 | 已合入 |
| Multi-Backend Vector | `infra/vector/` | ✅ | FAISS/Chroma/Milvus/Pinecone 多后端向量存储 | 已合入 |
| Multi-Backend Messaging | `infra/messaging/` | ✅ | Kafka/RabbitMQ/Redis 消息队列 | 已合入 |
| Multi-Database | `infra/database/` | ✅ | SQLite/MySQL/PostgreSQL/MongoDB + 连接池 | 已合入 |
| Multi-Backend Storage | `infra/storage/clients.py` | ✅ | S3/MinIO/Local 文件对象存储 | 已合入 |
| File Watcher | `infra/management/file_watcher.py` | ✅ | 跨进程文件监听 + 回调注册，支持热重载 | 已合入 |
| PlatformDB 持久化 | `storage/platform_db.py` | ✅ | 统一 SQLite 持久化：tenants/api_keys/quotas/billing 4表 | 已合入 |

---

## 二十三、核心API统一入口

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| Intent API (Unified) | `core/api/intents.py` | ✅ | 三统一意图：core_chat, core_execute, core_query | 已合入 |
| CoreFacade | `core/api/core_facade.py` | ✅ | 统一门面，84K行暴露所有核心能力 | 已合入 |
| ContextService | `core/services/context_service.py` | ✅ | 完整对话上下文管理 + 记忆集成 | 已合入 |
| ConfigRegistry | `core/services/config_registry_store.py` | ✅ | 版本化/哈希校验的配置注册中心 | 已合入 |
| ExecutionStore | `core/services/execution_store/` | ✅ | 综合执行/审计存储 + Schema管理 | 已合入 |

---

## 二十四、编排系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| Pipeline Orchestrator | `core/orchestration/orchestrator.py` | ✅ | 多步流水线编排 + 能力映射 | 已合入 |
| Capability Mapper | `core/orchestration/capability_mapper.py` | ✅ | Intent→Capability→Executor 解析链 | 已合入 |
| Chain Planner | `core/orchestration/chain_planner.py` | ✅ | 执行链拓扑规划 | 已合入 |
| Intent Analyzer | `core/orchestration/intent_analyzer.py` | ✅ | 意图分类与分解 | 已合入 |

---

## 二十五、管理 & 质量

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| Asset Installer | `management/asset_installer.py` | ✅ | Git/dir/zip 导入 Agent/Skill/MCP，host allowlist安全 | 已合入 |
| Format Adapters | `management/format_adapters.py` | ✅ | 多格式导入 (YAML/JSON/TOML frontmatter) | 已合入 |
| N8N/LangChain Adapter | `management/n8n_langchain_adapter.py` | ✅ | n8n workflow + LangChain chain 导入 | 已合入 |
| Coze/Dify Adapter | `management/coze_adapter.py` + `dify_adapter.py` | ✅ | Coze/Dify 平台 Agent 导入 | 已合入 |
| Capability Convergence | `management/capability_convergence.py` | ✅ | Agent/Skill/Tool 能力重叠检测与去重 | 已合入 |
| Compliance Checks | `management/compliance_checks.py` | ✅ | 可扩展生产就绪审计 + 自动发现检查函数 | 已合入 |
| Plugin Manager | `apps/plugins/manager.py` | ✅ | 插件生命周期管理 (install/enable/disable/remove) | 已合入 |
| Quality Gate Suite | `apps/quality/gates.py` | ✅ | 多阶段质量门 | 已合入 |
| Quality Scanner | `apps/quality/scanner.py` | ✅ | 自动代码/技能质量扫描 | 已合入 |
| StandardsValidator | `evaluation/standards_validator.py` | ✅ | 10条声明式规则：缺节/占位符/版本/术语检查，YAML驱动 | 已合入 |
| StructuredMerger | `coordination/merger.py` | ✅ | Map-Reduce 合稿：交叉引用验证+悬空引用检测+LLM合稿 | 已合入 |
| FullStack 诊断 | `api/routers/diagnostics.py:_check_full_stack` | ✅ | 12项全域检查(入驻/知识/协作/学习/FDE日常 5条旅程) | 已合入 |
| Spec 冒烟测试 | `scripts/smoke_spec_lifecycle.sh` | ✅ | 8阶段自动化: create→submit→poll→trace→dashboard→stable | 已合入 |
| Workbench API | `api/routers/workbench.py` + `core/schemas_workbench.py` | ✅ | Spec生命周期(`create_spec:SpecCreateRequest`, `revise_spec`, `approve:SpecApproveRequest`, `reject:SpecRejectRequest`, `promote:SpecPromotionRequest`) + Skill安装(`install_skill_from_url:SkillInstallRequest`) + `submit_task` + `submit_feedback` | 已合入 |
| 合规审计 (ComplianceChecks) | `management/compliance_checks.py` | ✅ | 可扩展生产就绪审计: 任务规格/MemoryManager/PolicyGate/RBAC/CLAUDE.md检查 | 已合入 |
| 架构守卫诊断集成 | `api/routers/diagnostics.py:_check_arch_guard` | ✅ | 架构守卫违规数自动检测→诊断卡片展示, 0违规=满分 | 已合入 |
| Skill Lint 诊断 | `api/routers/diagnostics.py:_check_skill_lint` | ✅ | 全量 Skill Lint 扫描→error/warning 统计→诊断评分 | 已合入 |
| Core 运行时诊断 | `api/routers/diagnostics.py:_check_core_runtime` | ✅ | ExecutionStore 初始化状态检查 | 已合入 |
| 能力图谱健康 | `api/routers/diagnostics.py:_check_capability` | ✅ | 孤立Agent/未解析引用/入口重复自动检测 | 已合入 |
| Wiki 健康检查 | `api/routers/diagnostics.py:_check_wiki_health` | ✅ | 死链/孤立/矛盾/过期页面检测→health_score 评分 | 已合入 |
| 链路追踪诊断 | `api/routers/diagnostics.py:_check_traces` | ✅ | 链路追踪完整性: span_id/trace_id/事件持久化检查 | 已合入 |

---

## 二十六、编排层 (Orchestration)

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| 意图分析 | `orchestration/intent_analyzer.py` | ✅ | 意图分类与分解 | 已合入 |
| 链规划 | `orchestration/chain_planner.py` | ✅ | 执行链拓扑规划 | 已合入 |
| 能力映射 | `orchestration/capability_mapper.py` | ✅ | Intent→Capability→Executor 解析链 | 已合入 |
| DAG 编排器 | `orchestration/orchestrator.py` | ✅ | 多步流水线编排 + DAG 输出 | 已合入 |
| Pipeline 引擎 | `harness/execution/pipeline_engine.py` | ✅ | 多阶段调度/HITL暂停/重试/snapshot | 已合入 |
| LangGraph 图执行 | `harness/execution/langgraph/` | ✅ | 节点拓扑执行+条件边路由+checkpoint | 已合入 |
| DynamicRouter (LLM路由) | `harness/execution/dynamic_router.py` | ✅ | LLM驱动动态下一跳选择 + Reducer状态合并防并行覆盖 + 灰度上线(AIPLAT_DYNAMIC_ROUTER_PERCENTAGE) | 已合入 |
| DebateMode | `harness/execution/debate.py` | ✅ | N-Agent辩论: 收敛检测 + Manager合成, routing_mode="debate" | 已合入 |
| Swarm | `harness/execution/swarm.py` | ✅ | N-Agent竞选择优: 同任务独立执行→Arena评分→胜出合并, routing_mode="swarm" | 已合入 |
| Roundtable | `harness/execution/roundtable.py` | ✅ | 多Agent平等讨论: 每轮全员发言→共识收敛→综合合成, routing_mode="roundtable" | 已合入 |
| Matter (验收+交付) | `SpecDetail.tsx` revise modal | ✅ | 交付物定义 + 验收标准字段, 存储于 SpecVersion.content | 已合入 |
| CoT AutoInject | `harness/syscalls/llm.py:253` + `harness/utils/prompt_loader.py:cot-auto-inject` | ✅ | 每次LLM调用自动注入4步推理指令, AIPLAT_COT_AUTO_INJECT控制 | 已合入 |
| SubAgent 协调器 | `apps/agents/subagent/coordinator.py` | ✅ | execute_single/parallel/sequential/fanout | 已合入 |
| 并行执行器 | `apps/agents/parallel_executor.py` | ✅ | Map-Reduce 模式 + max_concurrency + 异常隔离 | 已合入 |
| 8 种协调模式 | `harness/coordination/patterns/` | ✅ | Pipeline/FanOut/Supervisor/ExpertPool/ProducerReviewer/Hierarchical | 已合入 |
| 统一编排入口 | `orchestration/__init__.py` | ✅ | L1+L2+L3 三层架构统一 import | 已合入 |
| 编排 YAML 配置化 | `base.py:create_agent()` | ✅ | AGENT.md `orchestration.mode` 字段自动升级为 MultiAgent | 已合入 |

---

## 统计

| 维度 | 已实现 | 部分实现 | 合计 |
|------|:---:|:---:|:---:|------|
| Harness 执行引擎 | 34 | 0 | 34 |
| 记忆子系统 | 31 | 0 | 31 |
| 知识引擎（本体） | 107 | 0 | 107 |
| RAG 检索 | 40 | 0 | 40 |
| 知识基础设施 | 29 | 0 | 29 |
| Agent 系统 | 23 | 0 | 23 |
| Skill 系统 | 23 | 0 | 23 |
| 安全与治理 | 33 | 0 | 33 |
| 可观测性 | 16 | 0 | 16 |
| 模型基础设施 | 27 | 0 | 27 |
| 部署与运维 | 17 | 0 | 17 |
| 扩展与学习 | 79 | 0 | 79 |
| Gate 系统 | 17 | 0 | 17 |
| 评估系统 | 13 | 0 | 13 |
| MCP 协议 | 6 | 0 | 6 |
| A2A 协议 | 7 | 0 | 7 |
| 文档智能 | 24 | 0 | 24 |
| 工具生态 | 21 | 0 | 21 |
| 微调系统 | 12 | 0 | 12 |
| 部署与灰度 | 4 | 0 | 4 |
| 运行时干预 | 2 | 0 | 2 |
| Arena & 调度 | 4 | 0 | 4 |
| 平台治理 | 59 | 0 | 59 |
| Infra 基础设施 | 11 | 0 | 11 |
| 核心API统一入口 | 5 | 0 | 5 |
| 编排系统 | 4 | 0 | 4 |
| 管理 & 质量 | 21 | 0 | 21 |
| 编排层 | 17 | 0 | 17 |
| **总计** | **699** | **0** | **699** |

---

*最后更新: 2026-07-11*
*版本: 18.5 · 28章 · 686项能力 · 686✅ · 企业大脑竣工+智能澄清对话*

**自检命令**：
```bash
# 1. 验证 ✅ 数与统计表一致
grep -c '✅' AIPLAT_CAPABILITIES.md
# 预期: 应匹配统计表的 "400 ✅"

# 2. 验证代码位置仍存在
grep '^\|.*`.*\.py:.*`.*\|' AIPLAT_CAPABILITIES.md | grep -oP '`[^`]+\.py[^`]*`' | while read f; do
  path=$(echo "$f" | tr -d '`')
  [ -f "aiPlat-core/core/$path" ] || echo "MISSING: $path"
done
```
