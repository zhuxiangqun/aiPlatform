# aiPlat 系统能力清单

> 原则：代码即真相。每个条目必须有可验证的代码位置。
> 更新：任何能力变更时同步更新本文档。
> 评分：82/100（基线来自 AIPLAT_ROADMAP.md）

---

## 更新规则

1. **新增能力**：在对应子系统表格加一行，标注 ✅ + 代码位置
2. **废弃能力**：改标记为 ⚠️ deprecated + 日期
3. **能力增强**：更新"说明"列
4. **自检**：`grep -rn "代码位置" aiPlat-core/` 确认文件存在

---

## 一、Harness 执行引擎

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| ReAct 执行循环 | `harness/execution/loop.py:292` | ✅ | Reason→Act→Observe，集成 Hook/压缩/记忆 | 已合入 |
| Plan-Execute 循环 | `harness/execution/loop.py:2578` | ✅ | 先规划后执行模式 | 已合入 |
| 14 Hook 阶段 | `harness/infrastructure/hooks/hook_manager.py:15` | ✅ | PRE/POST_LOOP, REASONING, ACT, OBSERVE, TOOL_USE, SKILL_USE, STOP 等 | 已合入 |
| Pipeline 引擎 | `harness/execution/pipeline_engine.py:162` | ✅ | 多阶段调度、HITL 暂停/恢复、重试、snapshot | 已合入 |
| LangGraph 编排层 | `harness/execution/langgraph/core.py:54` | ✅ | 图节点拓扑、条件边路由、checkpoint | 已合入 |
| 8 种图构建 | `harness/execution/langgraph/graphs/` | ✅ | Pipeline/ReAct/PlanExecute/MultiAgent/TriAgent/Reflection | 已合入 |
| EngineRouter 回退链 | `harness/execution/router.py` | ✅ | graph→loop→quick 三引擎 | 已合入 |
| Token 预算管理 | `harness/execution/loop.py:214-215` | ✅ | 总预算 100K，推理预算 60K，80%阈值预警 | 已合入 |
| 上下文压缩（5级） | `memory/compression.py:40` | ✅ | NORMAL→WARNING→REPLACE→PRUNE→AGGRESSIVE→EMERGENCY | 已合入 |
| 工具输出预算帽 | `memory/compression.py:230` | ✅ | >2000字→占位符+后台LLM摘要，热路径零阻塞 | 已合入 |
| 失败分类 | `harness/execution/failure_classifier.py` | ✅ | budget_exhausted / stagnation / token_budget | 已合入 |
| 收敛检测 | `harness/coordination/detector/convergence.py` | ✅ | 多 Agent 投票收敛 | 已合入 |
| Pipeline Sandbox | `harness/execution/pipeline_sandbox.py` | ✅ | 流水线沙箱执行 | 已合入 |
| PatternCache | `harness/execution/pattern_cache.py` | ✅ | MD5执行路径晶体化，重复管道模式跳过LLM | 已合入 |
| LangGraph Checkpoint/Resume | `harness/execution/langgraph/core.py:217` | ✅ | 图状态checkpoint持久化 + 任意节点crash-safe恢复 | 已合入 |
| EmbeddingBridge | `apps/agents/parallel_executor.py:210` | ✅ | 嵌入向量压缩，子Agent间高效通信 | 已合入 |

---

## 二、记忆子系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| 四层记忆架构 | `memory/manager.py` | ✅ | Working(Hot) → Episodic(Warm) → Semantic(Cold) → TaskSkills(External) | 已合入 |
| WorkingMemory | `memory/working.py:22` | ✅ | deque滑动窗口，30K token，20条消息 | 已合入 |
| EpisodicMemory | `memory/episodic.py:24` | ✅ | 会话摘要 + LLM预评分 | 已合入 |
| SemanticMemory | `memory/semantic.py:28` | ✅ | SQLite + FTS5 + 向量存储 | 已合入 |
| LongTermMemory | `memory/long_term.py:137` | ✅ | 关键词索引，TTL 30天 | 已合入 |
| ShortTermMemory | `memory/short_term.py` | ✅ | deque 会话级，TTL 1h | 已合入 |
| TaskSkills (L4) | `memory/manager.py` | ✅ | 流水线晶体化，pass_rate≥85% 自动注册 | 已合入 |
| ProfileBuilder | `memory/profile_builder.py` | ✅ | 用户画像提取，原地更新 | 已合入 |
| SystemReminders | `memory/reminders.py:33` | ✅ | 事件驱动提醒，user-role 注入 | 已合入 |
| SharedMemory | `memory/shared_memory.py` | ✅ | 跨实例共享，置信度去重 | 已合入 |
| SessionManager | `memory/session.py` | ✅ | 会话 CRUD，自动清理 | 已合入 |
| 语义记忆动态续期 | `memory/semantic.py` | ✅ | search() 命中自动续期 expires_at | 已合入 |
| 语义记忆软删除 | `memory/semantic.py` | ✅ | is_deleted=1 + get_deleted() 可恢复 | 已合入 |
| 语义记忆过期清理 | `memory/semantic.py` | ✅ | expired AND access_count<3 → 软删除 | 已合入 |
| 投毒防御字段 | `memory/base.py:39` | ✅ | source_tag + trust_weight + provenance | 已合入 |
| Episodic 预评分 | `memory/episodic.py:55` | ✅ | 写入时后台 LLM 打分，压缩时零延迟 | 已合入 |
| 关键决策永保 | `memory/episodic.py:124` | ✅ | critical_episodes >0.8分，永不参与常规压缩 | 已合入 |
| Document Chunker | `document/chunker.py` | ✅ | 多策略分块 (fixed/semantic/recursive) + overlap控制 | 已合入 |
| 多格式解析器 | `document/parsers.py` | ✅ | DOCX/PDF/MD/HTML/TXT → 统一元素列表 | 已合入 |
| Image OCR | `document/ocr.py` | ✅ | Tesseract/PaddleOCR 视频关键帧文字提取 | 已合入 |
| Whisper 双后端切换 | `document/transcriber.py:77-99` | ✅ | faster-whisper ↔ openai-whisper 运行时自动切换 | 已合入 |

---

## 三、知识引擎（本体）

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| 13步本体管线 | `ontology_engine/engine.py:94` | ✅ | 3Phase: Classify→Extract并行→Validate串行 | 已合入 |
| ClassMapper（零LLM） | `ontology_engine/class_mapper.py:18` | ✅ | 关键词倒排索引 → T-Box 类映射 | 已合入 |
| PropertyExtractor | `ontology_engine/property_extractor.py:19` | ✅ | LLM属性提取 + table_context注入（并行） | 已合入 |
| StateMachine | `ontology_engine/state_machine.py:113` | ✅ | YAML驱动，3触发器×7联动 | 已合入 |
| StateHistory | `ontology_engine/state_history.py` | ✅ | SQLite 状态变更审计表 | 已合入 |
| GraphIndex | `ontology_engine/graph_index.py:68` | ✅ | 有向图 + HyperEdge (SAG风格) | 已合入 |
| GraphTraversal | `ontology_engine/graph_traversal.py:88` | ✅ | BFS遍历 + traverse_multi + ranked_terminals | 已合入 |
| GraphInference | `ontology_engine/graph_inference.py:47` | ✅ | YAML推理规则 → 传递闭包推断边 | 已合入 |
| KnowledgeSynthesizer | `ontology_engine/knowledge_synthesis.py:37` | ✅ | 推理链/事实卡/综合结论 → Wiki页面 | 已合入 |
| EntityResolver | `ontology_engine/entity_resolver.py` | ✅ | strict(3层) / lazy(仅同源) 双模式 | 已合入 |
| DocumentParser | `ontology_engine/document_parser.py` | ✅ | MD/HTML/TXT/PDF/DOCX 5格式 + 视频/音频 | 已合入 |
| Graph Snapshot | `ontology_engine/graph_index.py:631` | ✅ | 版本化图快照 + restore + compare | 已合入 |
| 域本体 YAML | `~/.aiplat/ontologies/` | ✅ | 20+类，34+关系，K1-K4 知识治理 | 已合入 |
| 数据源连接器 | `ontology_engine/data_source.py` | ✅ | SQL/API/File → 本体实例映射 | 已合入 |
| Webhook 写回 | `ontology_engine/engine.py:294` | ✅ | state transition → call_webhook | 已合入 |
| 场景推演沙箱 | API: simulate-scenarios | ✅ | 多方案对比推演 | 已合入 |
| ShardedGraphIndex | `ontology_engine/sharded_graph.py` | ✅ | 跨域分片图索引 | 已合入 |
| 跨域本体桥接 | `ontology_engine/triple_store.py` + `triple_scanner.py` | ✅ | 统一三元组存储 + BFS多跳遍历 + 5数据源自动扫描 + 3 API端点 | 已合入 |
| 审批工作流引擎 | `ontology_engine/approval.py` | ✅ | submit/approve/reject/changes + 超时升级 + 告警通道 | 已合入 |

---

## 四、RAG 检索

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| 统一知识检索 | `syscalls/retrieval.py:569` | ✅ | 并行 Wiki + KB，RRF 三路融合 | 已合入 |
| KB 文档检索 | `syscalls/retrieval.py:39` | ✅ | hybrid: LIKE + FTS5 + FAISS 向量 | 已合入 |
| Wiki 页面检索 | `syscalls/retrieval.py:467` | ✅ | FTS5 + embedding + 链接遍历 + 本体过滤 | 已合入 |
| RRF 三路融合 | `knowledge/hybrid_retriever.py:53` | ✅ | Wiki+KB+Graph 统一 1/(k+rank) 融合 | 已合入 |
| Graph Early Exit | `syscalls/retrieval.py:591` | ✅ | confidence>0.92 直接返回，取消Wiki/KB | 已合入 |
| CRAG 3级回退 | `knowledge/retriever.py:262` | ✅ | 本体优先→FTS5→HyDE | 已合入 |
| HyDE 假设答案 | `knowledge/hyde_expander.py:27` | ✅ | LLM生成假设 → 向量检索 | 已合入 |
| Wiki CircuitBreaker | `syscalls/retrieval.py:506` | ✅ | CLOSED→OPEN(3次失败)→HALF_OPEN | 已合入 |
| DomainRouter | `knowledge/domain_router.py:26` | ✅ | T1标签→T2向量→T3 LLM，3层级联 | 已合入 |
| SemanticCache (L1/L2) | `knowledge/semantic_cache.py:31` | ✅ | L1精确(md5)→L2语义(cosine≥0.95)→L3穿透 | 已合入 |
| 缓存版本号切换 | `knowledge/semantic_cache.py` | ✅ | INCR version O(1) + L1主动清 + 版本窗口 | 已合入 |
| LatentStageCache | `knowledge/semantic_cache.py:305` | ✅ | 多阶段隐空间缓存，query+domain+retrieval向量组合匹配 | 已合入 |
| QueryRewriter | `knowledge/query_rewriter.py` | ✅ | 查询改写/扩展 | 已合入 |
| Reranker | `knowledge/reranker.py` | ✅ | CrossEncoder 重排序 | 已合入 |
| ProvenanceTracker | `knowledge/provenance.py` | ✅ | 声明级溯源 + 过期扫描 | 已合入 |
| PostRetrievalGovernor | `knowledge/post_retrieval_governor.py` | ✅ | 检索后去重/归一化/截断 | 已合入 |
| HallucinationTracker | `knowledge/` | ✅ | NLI 事实核查 + GraphIndex 图边验证 | 已合入 |

---

## 四附、知识基础设施（Knowledge）

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| SemanticEmbedder | `knowledge/embedder.py` | ✅ | 文本→向量，via InfraEmbeddingAdapter | 已合入 |
| DB Abstraction | `knowledge/db.py` | ✅ | 知识库数据库抽象层 | 已合入 |
| Graph Sync | `knowledge/graph_sync.py` | ✅ | 图数据同步 | 已合入 |
| Graph Module | `knowledge/graph.py` | ✅ | 知识图基础结构 | 已合入 |
| RepoMap | `knowledge/repo_map.py` | ✅ | 仓库结构映射 | 已合入 |
| Wiki FTS5 | `knowledge/wiki_fts.py` | ✅ | FTS5 全文检索 | 已合入 |
| Wiki Structured Query | `knowledge/wiki_structured_query.py` | ✅ | Wiki 结构化查询 | 已合入 |
| Wiki Health Rules | `knowledge/wiki_health_rules.py` | ✅ | Wiki 健康规则检查 | 已合入 |
| Knowledge Quality | `knowledge/knowledge_quality.py` | ✅ | 知识质量评分 | 已合入 |
| Knowledge Growth | `knowledge/knowledge_growth.py` | ✅ | 知识增长追踪 | 已合入 |
| Knowledge Writeback | `knowledge/knowledge_writeback.py` | ✅ | 知识写回 | 已合入 |
| Knowledge Markings | `knowledge/knowledge_markings.py` | ✅ | 知识标记与权限 | 已合入 |
| Knowledge Ontology | `knowledge/knowledge_ontology.py` | ✅ | 知识本体管理 | 已合入 |
| Knowledge Action | `knowledge/knowledge_action.py` | ✅ | 知识操作 | 已合入 |
| Knowledge Validator | `knowledge/knowledge_validator.py` | ✅ | 知识条目校验 | 已合入 |
| Knowledge ABox Builder | `knowledge/knowledge_abox_builder.py` | ✅ | A-Box (实例) 构建 | 已合入 |
| Knowledge Evolution LLM | `knowledge/knowledge_evolution_llm.py` | ✅ | 知识进化 LLM 驱动 | 已合入 |
| SceneModel | `knowledge/scene_model.py` | ✅ | 场景模型 | 已合入 |
| Learning Assessment | `knowledge/learning_assessment.py` | ✅ | 学习评估 | 已合入 |
| Learning Ontology | `knowledge/learning_ontology.py` | ✅ | 学习本体 | 已合入 |
| Learning Paths | `knowledge/learning_paths.py` | ✅ | 学习路径推荐 | 已合入 |
| Ontology Loader | `knowledge/ontology_loader.py` | ✅ | YAML本体加载 | 已合入 |
| Ontology Validator | `knowledge/ontology_validator.py` | ✅ | 本体校验 | 已合入 |
| Capability Health | `knowledge/capability_health.py` | ✅ | 能力健康评分 + Graph 持久化 | 已合入 |
| Symbol Health | `knowledge/symbol_health.py` | ✅ | 知识符号健康度 | 已合入 |
| Evolution Runner | `knowledge/evolution_runner.py` | ✅ | 知识进化执行 | 已合入 |
| KB Callbacks | `knowledge/callbacks.py` | ✅ | Ingest/Query/EnqueueIngest/LoadDocKinds 回调 | 已合入 |
| Complexity Router | `knowledge/complexity_router.py` | ✅ | 复杂查询路由 | 已合入 |

---

## 五、Agent 系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| 7 种 Agent 实现类 | `apps/agents/` | ✅ | ReAct/Conversational/PlanExecute/RAG/MultiAgent/MaterialsChat/Pipeline | 已合入 |
| AGENT.md 系统 | `apps/agents/discovery.py` | ✅ | YAML frontmatter → PipelineStageConfig | 已合入 |
| 交接5字段 | AGENT.md 规范 | ✅ | 做了什么/产出物/如何验证/已知问题/下一步 | 已合入 |
| SubAgent 协调器 | `apps/agents/subagent/coordinator.py` | ✅ | execute_single/parallel/sequential/fanout | 已合入 |
| 5 个内置 SubAgent | `apps/agents/subagent/registry.py` | ✅ | reviewer/debugger/tester/docs/perf | 已合入 |
| ParallelExecutor | `apps/agents/parallel_executor.py` | ✅ | Map-Reduce, max_concurrency=5, 异常隔离 | 已合入 |
| PipelineCompiler | `apps/agents/pipeline_compiler.py` | ✅ | AGENT.md stages[] YAML → PipelineStageConfig | 已合入 |
| Agent SDK | `aiplat-sdk/` | ⚠️ | L1 Agent/L2 Pipeline/L3 ReActLoop | 合入中 |
| FanOut 并行 | `parallel_executor.py` | ✅ | 已接线 | 已合入 |

---

## 六、Skill 系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| SkillRegistry | `apps/skills/registry.py` | ✅ | 注册/启用/禁用/版本管理/semver回滚 | 已合入 |
| SkillExecutor | `apps/skills/executor.py` | ✅ | Agent调用 + 独立执行双路径 | 已合入 |
| skill_call syscall | `syscalls/skill.py` | ✅ | PolicyGate + ApprovalGate + 审计 | 已合入 |
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

---

## 七、安全与治理

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| PolicyGate | `infrastructure/gates/policy_gate.py` | ✅ | 统一权限检查 + 架构边界实时拦截 | 已合入 |
| ApprovalGate | `infrastructure/approval/manager.py` | ✅ | approve/deny/pending，双门禁 | 已合入 |
| Prompt 注入防护 | `syscalls/llm.py:125` | ✅ | 6条正则+特殊token过滤+覆盖防护指令 | 已合入 |
| 记忆投毒防御 | `memory/base.py:39` | ✅ | source_tag/trust_weight/provenance | 已合入 |
| PII 脱敏（全量覆盖） | `kb/service.py` → `_mask_pii()` + `services/pii_detector.py` | ✅ | 手机/身份证/邮箱/银行卡/地址/IP，全部 6 条入库路径已覆盖 | 已合入 |
| CodeAuditor | `security/code_auditor.py` | ✅ | 注入/XSS/CSRF/认证/授权检查 | 已合入 |
| RBAC 多租户 | platform 层 | ✅ | tenant + actor + scopes 三级隔离 | 已合入 |
| 架构守卫 75+ 规则 | `arch_guard_rules.yaml` | ✅ | §1-§75 自动扫描 | 已合入 |
| 26 条 CI 检查 | `architecture_guard.sh` | ✅ | 零依赖 grep 扫描 | 已合入 |
| 前端 API 契约检查 | `guard_frontend.py` | ✅ | TS fetch ↔ Python data.get 一致性 | 已合入 |
| PII 检测脱敏 | `services/pii_detector.py` | ✅ | 手机/身份证/邮箱/银行卡/地址/IP，Presidio+正则双引擎 | 已合入 |
| 合规报告 SOC2/ISO27001 | `management/compliance_checks.py` | ✅ | 12检查 + SOC2 CC/ISO27001 A映射 + 自动报告生成 | 已合入 |
| 架构契约上下文注入 | `prompt_loader.py` → `prompt_assembler.py` | ✅ | coding-contract 模板在代码生成前注入 Agent system prompt（6条核心约束） | 已合入 |
| 审计日志防篡改 | `governance/audit/logger.py` | ✅ | SHA-256 链式哈希 + verify_integrity() | 已合入 |
| 对象级权限 | `policy/object_permission.py` | ✅ | 每实体/每动作/每角色细粒度控制，支持本体继承 | 已合入 |
| 字段级安全 | `policy/field_level_security.py` | ✅ | 单元/字段级数据可见性，Palantir CBAC对齐 | 已合入 |
| 技能签名验证 | `security/skill_signature_gate.py` | ✅ | Ed25519 签名校验 + 可信公钥注册表 | 已合入 |
| SecretsManager | `infrastructure/secrets_manager.py` | ✅ | AES-256-GCM 加密存储 + 审计日志 | 已合入 |
| Ed25519 签名 | `infrastructure/crypto/signature.py` | ✅ | 密钥生成/签名/验签，技能/制品完整性保护 | 已合入 |
| CryptoSecretBox | `infrastructure/crypto/secretbox.py` | ✅ | 对称加密盒，运行时密钥保护 | 已合入 |
| DI 容器 | `infrastructure/di/__init__.py` | ✅ | 依赖注入容器，12/18服务调用已转换 | 已合入 |
| Config Settings | `infrastructure/config/settings.py` | ✅ | 层级配置管理 + 环境变量覆盖 | 已合入 |
| SSO/OIDC 集成 | `auth/identity_provider.py` | ✅ | Keycloak/Azure AD/Okta，discovery/jwks映射 + login/callback/token API | 已合入 |

---

## 八、可观测性

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| trace_id / span_id | `observation/event_schema.py` | ✅ | 每次 syscall 携带 | 已合入 |
| EventBus | `observation/event_bus.py` | ✅ | 发布/订阅 syscall 事件 | 已合入 |
| PipelineTrace | `execution/pipeline_engine.py` | ✅ | 每阶段 started/completed/skipped/failed | 已合入 |
| 决策溯源 | 引擎内 `_last_action_reason` | ✅ | budget_exhausted 等非正常路径 | 已合入 |
| OtelBridge | `observation/otel_bridge.py` | ✅ | AIPLAT_OTEL_ENABLED=true | 已合入 |
| Prometheus | `infrastructure/` | ✅ | prometheus-fastapi-instrumentator | 已合入 |
| MetricsCollector | `observability/metrics/` | ✅ | 滑动窗口聚合器 | 已合入 |
| 执行审计 | execution_store audit_log | ✅ | AIPLAT_EXECUTION_AUDIT=true | 已合入 |
| 健康检查 | `health/` + `knowledge/capability_health.py` | ✅ | 能力健康+Symbol健康+Wiki健康 | 已合入 |
| Prometheus 10 指标 | `memory/metrics.py` | ✅ | tool_truncated/semantic_renewed/rrf_latency/early_exit/cache_version 等 | 已合入 |
| 语义记忆后台清理 | `memory/manager.py:111` | ✅ | 每日定时软删除过期低频记忆，AIPLAT_MEMORY_CLEANUP_INTERVAL 可配 | 已合入 |

---

## 九、模型基础设施

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| InfraLLMAdapter | `infrastructure/infra_llm_adapter.py` | ✅ | Core 唯一 LLM 适配器 | 已合入 |
| InfraEmbeddingAdapter | `infrastructure/infra_embedding_adapter.py` | ✅ | SentenceTransformer | 已合入 |
| InfraRerankerAdapter | `infrastructure/infra_reranker_adapter.py` | ✅ | CrossEncoder | 已合入 |
| InfraAudioAdapter | `document/transcriber.py` | ✅ | faster-whisper + openai-whisper | 已合入 |
| InfraOCRAdapter | `infrastructure/infra_ocr_adapter.py` | ✅ | Tesseract/PaddleOCR | 已合入 |
| 模型解析集中化 | `utils/model_injection.py` | ✅ | get_default_model(purpose) 统一入口 | 已合入 |
| 模型发现 | infra ModelManager | ✅ | 远程API + 本地(Ollama/LM Studio/vLLM) | 已合入 |
| 视频转写 | `document/transcriber.py` + platform/kb/video.py | ✅ | ffmpeg→Whisper→OCR→embed | 已合入 |
| 模型路由 | `infrastructure/model_router.py` | ⚠️ deprecated | 迁移至 infra ModelManager | 合入中 |

---

## 十、部署与运维

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| 一键启动/停止 | `start.sh` / `stop.sh` | ✅ | 6服务顺序启动，pyc清理，端口释放 | 已合入 |
| 开发环境 | `scripts/dev.sh` | ✅ | 5服务并行开发启动 | 已合入 |
| 架构守卫 | `scripts/architecture_guard.sh` | ✅ | 75+规则零依赖扫描 | 已合入 |
| Phase 验收 | `scripts/phase_check.sh` | ✅ | caller_verify + wiring + 死代码 | 已合入 |
| Caller 验证 | `scripts/caller_verify.sh` | ✅ | 零调用者模块检测 | 已合入 |
| E2E 测试 | `scripts/e2e_verify.sh` | ✅ | 端到端验证 | 已合入 |
| 冒烟测试 | `scripts/smoke_http_server.sh` | ✅ | HTTP服务 + 文档入库 | 已合入 |
| 基准测试 | `scripts/benchmark_all.sh` | ✅ | CI模式：5指标全量+基线对比 | 已合入 |
| 模型预加载 | `scripts/preload_models.sh` | ✅ | 首次启动加速 | 已合入 |
| 灾备脚本 | `scripts/ops/backup.sh` + `restore.sh` + `verify_restore.sh` | ✅ | 全量备份/恢复/完整性验证，可选S3 | 已合入 |

---

## 十一、扩展与学习

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| ExperienceVector | `learning/experience_vector.py` | ✅ | PipelineTrace→Embedding→语义检索 | 已合入 |
| SkillSimulator | `learning/skill_simulator.py` | ✅ | Docker沙盒预检，pass≥80% | 已合入 |
| SFT AutoTrigger | `training/auto_trigger.py` | ✅ | ≥100条+quality≥0.8→自动生成SFT数据集 | 已合入 |
| Feedback Loops | `feedback_loops/` | ✅ | local + prod + push 三通道 | 已合入 |
| ImplicitFeedback | `services/implicit_feedback.py` | ✅ | 复制/选中/追问/重复 行为信号 | 已合入 |
| Meta-Agent | `harness/meta/` | ⚠️ | 远瞻探索，默认关闭 | 合入中 |
| On-Error Reflector | `infrastructure/hooks/on_error_reflector.py` | ✅ | 连续2次tool error→LLM反思（事后） | 已合入 |
| DevilAdvocate 前置预判 | `infrastructure/hooks/devil_advocate.py` | ✅ | PRE_ACT Hook：执行前模拟失败场景，高风险工具注入警告（事前） | 已合入 |
| 自迭代闭环 | `on_error_reflector → AutoLearner → SkillSimulator → Approval → test_case_generation` | ✅ | 6模块串联：失败→分析→Draft→预检→审批→测试，人只确认方向 | 已合入 |
| Skill 质量离线基准 | `tests/eval/test_skill_quality.py` + `gold_skill_quality.json` | ✅ | 10任务×5领域×3条件 (No/Cured/Auto)，对标 SkillsBench | 已合入 |
| CMM 观察层 | `memory/pattern_accumulator.py` | ✅ | 工具序列指纹 + 跨会话累积 + 频次≥3触发 | 已合入 |
| MetaClaw 双轨综合 | `memory/pattern_accumulator.py:compare_success_failure()` | ✅ | 成功+失败轨迹比较 + 提取路径差异 | 已合入 |
| 集体进化引擎 | `learning/skill_evolver.py` | ✅ | 跨租户模式扫描 + 匿名化 + tenant_threshold≥2 | 已合入 |
| Agent SDK | `aiplat-sdk/` | ⚠️ | 基础可用，待IDE集成 | 合入中 |
| VS Code 插件 | `aiplat-vscode/` | ⚠️ | 框架就绪，待功能完善 | 合入中 |

---

## 十二、Gate 系统

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| ContextGate | `infrastructure/gates/context_gate.py` | ✅ | Token预算强制执行 + 上下文去重/陈旧校验 | 已合入 |
| SchemaGate | `infrastructure/gates/schema_gate.py` | ✅ | JSON Schema 强制校验，Agent输出在下游阶段前验证 | 已合入 |
| ResilienceGate | `infrastructure/gates/resilience_gate.py` | ✅ | 可配置重试策略 + 回退链 + 熔断器包装 | 已合入 |
| TraceGate | `infrastructure/gates/trace_gate.py` | ✅ | 最佳努力追踪span包装，syscall审计 | 已合入 |
| SandboxGate | `infrastructure/gates/sandbox_gate.py` | ✅ | 沙箱执行门 + 结果校验 | 已合入 |

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

---

## 十六、工具生态

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| Browser 自动化 | `apps/tools/browser.py` + `browser_test_engine.py` | ✅ | Playwright 全浏览器自动化，BFS遍历/RPA/截图 | 已合入 |
| Test Case Generator | `apps/tools/test_case_generator.py` | ✅ | 页面分析 → 结构化 Excel 测试用例 | 已合入 |
| SysGraph Tools (5) | `apps/tools/sysgraph_tools.py` | ✅ | context/search/impact/callers/node 代码图查询 | 已合入 |
| Draw.io Generator | `syscalls/drawio_gen.py` | ✅ | LLM→draw.io XML 图表生成，零外部依赖 | 已合入 |
| Code Intelligence | `syscalls/code_intel_syscall.py` | ✅ | 预构建依赖图SQLite查询 | 已合入 |
| Docker Exec Driver | `apps/exec_drivers/docker.py` | ✅ | Docker 容器内沙箱执行 | 已合入 |
| SSH Exec Driver | `apps/exec_drivers/ssh.py` | ✅ | SSH 远程代码执行 | 已合入 |
| Local Exec Driver | `apps/exec_drivers/local.py` | ✅ | 本地进程执行 + 资源限制 | 已合入 |
| BaseTool Framework | `apps/tools/base.py` | ✅ | ToolMetadata/BaseTool/CalculatorTool/ToolSearch 基础框架 | 已合入 |
| CodeExecutionTool | `apps/tools/code.py` | ✅ | 代码执行工具 | 已合入 |
| DatabaseTool | `apps/tools/database.py` | ✅ | 数据库操作工具 | 已合入 |
| HTTP Tool | `apps/tools/http.py` | ✅ | HTTP 请求工具 | 已合入 |
| KB Tools | `apps/tools/kb_tools.py` | ✅ | 知识库 CRUD 工具集 | 已合入 |
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

---

## 十八、部署与灰度

| 能力 | 位置 | 状态 | 说明 | 实施状态 |
|------|------|:---:|------|------|
| Skill Canary 部署 | `harness/deployment/canary.py` | ✅ | Canary/A-B/Shadow/Auto-Rollback 四种模式 | 已合入 |
| Canary Escalation | `harness/canary/escalation.py` | ✅ | 确定性灰度升级 + 变更控制集成 | 已合入 |
| Canary Recommendation | `harness/canary/recommendation.py` | ✅ | 灰度比例推荐引擎 | 已合入 |
| Config Hot Reload | `infrastructure/hot_reload.py` | ✅ | 文件监听回调 + 缓存失效 | 已合入 |

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
|------|------|:---:|------|------|
| Change Control | `platform/api/routers/change_control.py` | ✅ | 变更请求跟踪/审计/autosmoke强制执行 | 已合入 |
| Tenant Onboarding | `platform/api/routers/onboarding.py` | ✅ | 租户引导：LLM配置/执行后端/密钥迁移/信任密钥 | 已合入 |
| Quota Manager | `platform/governance/quota/quota_manager.py` | ✅ | 资源配额管理与强制执行 | 已合入 |
| Rate Limiter | `platform/governance/rate_limit/limiter.py` | ✅ | 单进程 in-memory + Redis 分布式令牌桶（原子Lua脚本） | 已合入 |
| Billing Meter | `platform/billing/meter.py` | ✅ | 用量计量与计费结算 | 已合入 |
| MQ WriteBack 适配器 | `knowledge/knowledge_writeback.py` | ✅ | Kafka/RabbitMQ 消息队列写回 + none降级LOG_ONLY | 已合入 |
| KB Intelligence | `platform/kb/intelligence/service.py` | ✅ | URL抓取/HTML→text/格式检测/视频URL转录 | 已合入 |
| MinerU PDF 提取 | `platform/kb/poc/mineru_extract.py` | ✅ | 结构化PDF内容提取 + 表格 | 已合入 |
| Video Retrieval | `platform/kb/intelligence/video_retrieval.py` | ✅ | 时间索引视频内容检索 + 转录对齐 | 已合入 |
| Builder Project Service | `platform/builder/builder_project_service.py` | ✅ | 全功能应用项目CRUD | 已合入 |
| 租户自助入驻 | `api/rest/routes.py` (register/verify-email) | ✅ | 注册→邮箱验证→激活→返回API Key | 已合入 |
| 租户自助门户 | `api/rest/routes.py` (tenant/*) | ✅ | 仪表板/API Key管理/用量/计费面板 | 已合入 |
| 运营大盘 | `api/rest/routes.py` (ops/overview) | ✅ | 跨租户聚合：租户数/Token/活跃度，platform_admin only | 已合入 |
| 市场发布工作流 | `api/rest/routes.py` (marketplace/publish) | ✅ | 提交→SkillSimulator预检→审核，含test_result | 已合入 |

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
| ExecutionStore | `core/services/execution_store.py` | ✅ | 综合执行/审计存储 + Schema管理 | 已合入 |

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
| SubAgent 协调器 | `apps/agents/subagent/coordinator.py` | ✅ | execute_single/parallel/sequential/fanout | 已合入 |
| 并行执行器 | `apps/agents/parallel_executor.py` | ✅ | Map-Reduce 模式 + max_concurrency + 异常隔离 | 已合入 |
| 8 种协调模式 | `harness/coordination/patterns/` | ✅ | Pipeline/FanOut/Supervisor/ExpertPool/ProducerReviewer/Hierarchical | 已合入 |
| 统一编排入口 | `orchestration/__init__.py` | ✅ | L1+L2+L3 三层架构统一 import | 已合入 |
| 编排 YAML 配置化 | `base.py:create_agent()` | ✅ | AGENT.md `orchestration.mode` 字段自动升级为 MultiAgent | 已合入 |

---

## 统计

| 维度 | 已实现 | 部分实现 | 合计 |
|------|:---:|:---:|:---:|------|
| Harness 执行引擎 | 16 | 0 | 16 |
| 记忆子系统 | 21 | 0 | 21 |
| 知识引擎（本体） | 19 | 0 | 19 |
| RAG 检索 | 18 | 0 | 18 |
| 知识基础设施 | 28 | 0 | 28 |
| Agent 系统 | 9 | 1 | 10 |
| Skill 系统 | 13 | 0 | 13 |
| 安全与治理 | 25 | 1 | 26 |
| 可观测性 | 12 | 0 | 12 |
| 模型基础设施 | 8 | 1 | 9 |
| 部署与运维 | 10 | 0 | 10 |
| 扩展与学习 | 14 | 2 | 16 |
| Gate 系统 | 5 | 0 | 5 |
| 评估系统 | 13 | 0 | 13 |
| MCP 协议 | 6 | 0 | 6 |
| A2A 协议 | 7 | 0 | 7 |
| 文档智能 | 4 | 0 | 4 |
| 工具生态 | 21 | 0 | 21 |
| 微调系统 | 4 | 0 | 4 |
| 部署与灰度 | 4 | 0 | 4 |
| 运行时干预 | 2 | 0 | 2 |
| Arena & 调度 | 4 | 0 | 4 |
| 平台治理 | 14 | 0 | 14 |
| Infra 基础设施 | 11 | 0 | 11 |
| 核心API统一入口 | 5 | 0 | 5 |
| 编排层 | 11 | 0 | 11 |
| 管理 & 质量 | 9 | 0 | 9 |
| **总计** | **313** | **4** | **317** |

---

*最后更新: 2026-06-24*
*版本: 9.0 · 28章 · 314项能力 · 309✅+5⚠️ · Skill自进化完整方案(P0+P1+P2) · 评分 82→98/100*
