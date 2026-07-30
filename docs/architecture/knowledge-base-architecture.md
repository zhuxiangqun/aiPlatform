# 知识库架构 — 数据写入与 RAG 检索全链路

> **权威参考入口。** 覆盖向量 KB、GraphIndex、LLM Wiki 三大存储系统的定位、数据流、表结构和 RAG 检索全链路。
>
> 相关文档：`manuals/knowledge-management.md`（操作指南）、`design/knowledge-ontology-plan.md`（设计提案）
>
> 最后更新：2026-07-21 · v2.9 — 新增 GrillingGate 运行时架构 + 域 interview_dimensions
>
> 最后更新：2026-07-20

---

## 一、系统总览

aiPlat 知识系统由 **三个独立存储** 构成，各自有明确职责：

```
┌──────────────────────────────────────────────────────────────────┐
│                        用户查询                                    │
│                           │                                       │
│            ┌──────────────┼──────────────┐                        │
│            ▼              ▼              ▼                        │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐                  │
│   │  向量 KB   │  │ GraphIndex │  │  LLM Wiki  │                  │
│   │  (SQLite)  │  │  (SQLite)  │  │ (Markdown) │                  │
│   └────────────┘  └────────────┘  └────────────┘                  │
│         ▲              ▲              ▲                           │
│         │              │              │                           │
│   文档入库管线      本体引擎 Step 10   本体引擎 Step 11              │
│   (不经过本体引擎)  (提取实体+关系)  (KnowledgeSynthesizer)         │
└──────────────────────────────────────────────────────────────────┘
```

| 存储 | 是什么 | 存什么 | 谁写 | 谁读 |
|:--|:--|:--|:--|:--|
| **向量 KB** | 原始文档 chunk + embedding | 解析后的文本片段 + 向量 | 文档入库管线 (`kb/service.py`) | `SqliteEmbeddingRetriever` |
| **GraphIndex** | 知识图谱 | 实体节点 + 关系边 + 超边 | 本体引擎 Step 10 (`engine.py:436`) | 图遍历 + `sys_knowledge_retrieve` |
| **LLM Wiki** | 结构化百科页面 | 实体页、合成页、知识原子 | 本体引擎 Step 11 (`KnowledgeSynthesizer`) | `WikiPageRetriever` |

**核心原则**：
- 向量 KB 存"原材料"（文档原始 chunk），本体引擎不修改它
- GraphIndex 存"结构化知识"（从原材料中提取的实体关系）
- Wiki KB 存"可读知识"（从 GraphIndex 合成的人类可读页面）
- RAG 查询时三者**并行检索 + RRF 融合**，Wiki 结果权重 1.1×

---

## 二、存储体系详解

### 2.1 向量 KB（SQLite）

**数据库文件**：`~/.aiplat/kb/tenants/{tenant_id}/kb.sqlite3`

**入口文件**：`aiPlat-platform/kb/db.py:241`（`KBSqlite` 类）

#### 核心表

| 表 | 行号 | 用途 |
|:--|:--|:--|
| `documents` | 25-36 | 文档注册表：`doc_id, collection_id, source_uri, kind, status, meta_json` |
| `collections` | 17-23 | 集合定义：`collection_id, name` |
| `kb_elements` | 75-88 | **核心内容表**：`element_id, doc_id, type, page_idx, text, cells_json, meta_json, year, quarter` |
| `kb_embeddings` | 130-141 | **向量存储**：`embedding_id, element_id, vector_json(JSON float array), model, dim` |
| `kb_elements_fts` | 268-275 | FTS5 全文索引（虚拟表） |
| `kb_jobs` | 149-163 | 任务追踪：`status(queued→running→completed/failed), progress, input/output/error_json` |
| `doc_sources` | 94-108 | 溯源表：`source_type(upload/url), content_hash(sha256)` |
| `budget_rows` | 57-69 | 预算表格结构化数据 |
| `assets` | 41-52 | 二进制资源（页面图片、帧图片） |

#### kb_elements 表结构（`db.py:75-88`）

```sql
CREATE TABLE kb_elements (
  tenant_id   TEXT NOT NULL,
  element_id  TEXT NOT NULL,
  doc_id      TEXT NOT NULL,
  type        TEXT NOT NULL,  -- text|table|image|transcript|equation
  page_idx    INTEGER,
  bbox_json   TEXT,
  text        TEXT,
  cells_json  TEXT,           -- for tables
  asset_id    TEXT,
  meta_json   TEXT,
  created_at  INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, element_id)
);
```

#### kb_embeddings 表结构（`db.py:130-141`）

```sql
CREATE TABLE kb_embeddings (
  tenant_id      TEXT NOT NULL,
  embedding_id   TEXT NOT NULL,
  doc_id         TEXT NOT NULL,
  element_id     TEXT NOT NULL,
  embedding_type TEXT NOT NULL,  -- text|paragraph|table
  model          TEXT,
  dim            INTEGER,
  vector_json    TEXT,           -- JSON float array, e.g. [0.12, -0.34, ...]
  created_at     INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, embedding_id)
);
```

**特征**：
- 每 tenant 独立 SQLite 文件（租户隔离）
- 向量以 JSON float array 存储（非专业向量数据库，适合中小规模）
- 默认 model=`hash-128`（128 维 HashEmbedding），无需 GPU
- 通过 `embed_text()` 函数（`core/api/facades/kb_facade.py`）生成

---

### 2.2 GraphIndex（知识图谱）

**数据库文件**：`~/.aiplat/graph/{domain_id}.db`

**入口文件**：`aiPlat-core/core/harness/ontology_engine/graph_index.py:89`（`GraphIndex` 类）

#### 核心表

| 表 | graph_index.py 行号 | 用途 |
|:--|:--|:--|
| `graph_nodes` | 112-119 | 实体节点：`entity_id, entity_name, class_name, source_doc_id` |
| `graph_edges` | 127-141 | 关系边：`source_id, target_id, relation_name, confidence, inferred, rule_name` |
| `graph_hyperedges` | 417 | 超边（SAG 风格）：`event_id, entity_ids(JSON), context_description, confidence` |
| `graph_snapshots` | 857 | 版本快照：`label, timestamp, data(JSON)` |

#### graph_edges 字段说明

```sql
CREATE TABLE graph_edges (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  domain_id          TEXT NOT NULL DEFAULT '',
  source_id          TEXT NOT NULL,
  target_id          TEXT NOT NULL,
  relation_name      TEXT NOT NULL DEFAULT '',
  relation_label     TEXT NOT NULL DEFAULT '',
  confidence         REAL NOT NULL DEFAULT 1.0,
  inferred           INTEGER NOT NULL DEFAULT 0,   -- 0=提取, 1=推理
  rule_name          TEXT NOT NULL DEFAULT '',     -- 推理规则名
  inferred_confidence REAL NOT NULL DEFAULT 1.0,
  context_desc       TEXT NOT NULL DEFAULT '',     -- 推理上下文
  embedding          TEXT NOT NULL DEFAULT ''
);
```

**特征**：
- 每 domain 独立 SQLite 文件（域隔离）
- `ShardedGraphIndex`（`sharded_graph.py`）封装跨域查询
- 支持跨域查询降级：`primary_domain` + `allow_cross=True`
- 推理边由 YAML `inference_rules` 驱动（零硬编码）
- 图突变后自动 `_invalidate_cache()`（`graph_index.py:742`）
- 最多 5 个 graph 的 LRU 内存缓存

---

### 2.3 LLM Wiki KB（Markdown 文件系统）

**根目录**：`~/.aiplat/wiki/`

**入口文件**：`aiPlat-core/core/harness/knowledge/wiki_engine.py:1`

#### 目录结构

```
~/.aiplat/wiki/collections/{collection_id}/
  ├── entities/          # 实体页（概念、人物、项目）
  ├── topics/            # 主题摘要（跨实体分析）
  ├── contradictions/    # 矛盾检测
  ├── atoms/             # 知识原子（原子事实）
  ├── synthesis/         # 合成页（本体引擎 Step 11 生成）
  ├── index.json         # 全局页面索引（title → page_id 映射）
  ├── index.md           # 人类可读索引（`generate_index_md()` 生成）
  ├── schema.yml         # Wiki 结构规则
  ├── proposals.json     # 合并/更新/补充提案
  ├── changelog.json     # 变更日志
  ├── vectors.json       # 缓存的页面 embedding
  ├── fts.db             # FTS5 全文索引（SQLite）
  ├── graph_cache.db     # 图可视化缓存
  └── .wiki_write_lock.db # 并发写锁
```

#### 页面格式（Markdown + YAML Frontmatter）

每个 `.md` 文件携带完整的元数据（`wiki_engine.py:30-39` FRONTMATTER_FIELDS）：

```yaml
---
title: "页面标题"
page_id: "<UUID>"         # 稳定跨引用标识符
category: entities|topics|contradictions|atoms|synthesis
tags: [标签1, 标签2]
related: ["关联页面标题"]
contradictions: ["矛盾页面标题"]
source_articles: ["kb:{doc_id}"]
source_instances: [entity1, entity2]  # 合成页特有,反向溯源
synthesis_type: reasoning_chain|fact_card|comprehensive_conclusion
stale_references: ["过期引用"]
relationships: "[{...}]"  # JSON string
last_updated: "2026-07-20T00:00:00+08:00"
version: 3
status: draft|curated|published|contradicted|resolved
marking: public|internal|confidential
summary: "页面摘要"
images: []
effective_date: "2026-01-01"  # K4 时间有效性
expiry_date: "2026-12-31"
department: "研发部"
owner: "张三"
---
# 正文内容（Markdown）
```

**特征**：
- 文件系统存储，Git 友好
- FTS5 独立索引（`fts.db`）
- embedding 缓存（`vectors.json`）
- 并发安全写锁（`.wiki_write_lock.db`）
- 增量 A-Box 推理（每次写页面时自动运行）
- 与 KB 双向链接（KB docs `meta_json.wiki_pages` 字段回写）

---

## 三、数据写入完整流程

### 3.1 阶段一：文档入库 → 向量 KB

**入口**：`aiPlat-platform/kb/service.py:46` `enqueue_ingest()`

```
用户上传/选择文档
  │
  ├─[1] enqueue_ingest() [service.py:46]
  │     ├─ 创建 doc_id = sha256(file_path)[:12]
  │     ├─ upsert_document(status="queued") → documents 表
  │     ├─ create_job(type="ingest", status="queued") → kb_jobs 表
  │     └─ 启动后台线程 _runner()
  │
  ├─[2] _runner 线程 [service.py:110]
  │     ├─ update_job(status="running")
  │     ├─ upsert_document(status="ingesting")
  │     └─ ingest_document() [service.py:416]
  │
  └─[3] ingest_document() 按文档类型分叉：

      ═══ 文本类（markdown/html/txt）═══
      ├─ kb_parse_document(file_path, kind) [CoreFacade]
      ├─ kb_chunk_elements(parsed, target_size=1000, overlap=150)
      ├─ for each chunk:
      │   ├─ insert_element() → kb_elements 表  [service.py:539]
      │   └─ insert_embedding() → kb_embeddings 表  [service.py:551]
      │       └─ embed_text(el_text) → InfraEmbeddingAdapter → hash-128 vector
      ├─ kb_classify_document() → 文档分类
      └─ upsert_document(status="ready")

      ═══ 视频类（mp4/mov）═══
      ├─ ingest_video_document() [video.py:50]
      ├─ kb_probe_video_duration() → 时长
      ├─ kb_extract_video_audio() → ffmpeg 提取音频
      ├─ kb_transcribe_audio() → Whisper 转文字
      ├─ kb_extract_video_keyframes() → 提取关键帧
      ├─ kb_ocr_keyframes() → OCR 文字识别
      │
      ├─ insert_asset() → assets 表（帧图片）
      ├─ for each segment:
      │   ├─ insert_element(type="text", meta={source: "video_transcript"})
      │   └─ insert_embedding()
      ├─ for each OCR segment:
      │   ├─ insert_element(type="text", meta={source: "video_ocr"})
      │   └─ insert_embedding()
      │
      ├─ _format_transcript_with_punctuation() → 全文加标点
      ├─ insert_element(type="paragraph") → 完整文稿
      ├─ kb_chunk_elements() → 分段检索优化
      └─ upsert_document(status="ready")

      ═══ PDF/扫描件 ═══
      ├─ MinerU Tier 3 路径（优先）: kb_parse_document() [CoreFacade]
      │   └─ 提取结构化表格行 → budget_rows 表
      ├─ OCR 路径（降级）: ingest_scanned_pdf()
      │   ├─ 逐页 OCR → 每页文本 token
      │   ├─ insert_asset() → 页面图片
      │   └─ insert_element() + insert_embedding()
      └─ upsert_document(status="ready")
```

**关键点**：
- 向量 KB 在入库阶段即完成写入，后续本体引擎不修改 `kb_elements` 和 `kb_embeddings`
- 入库管线与本体引擎是**异步解耦**的（入库完成 → 状态变为 ready → 本体引擎可随时触发）
- 视频文件有预览缓存（`.preview_cache.json`），避免重复 ffmpeg/Whisper/OCR

---

### 3.2 阶段二：本体引擎 → GraphIndex + Wiki

**入口**：`aiPlat-core/core/harness/ontology_engine/engine.py:74` `OntologyEngine.process_chunks()`

触发方式：
- 手动：管理端 → 本体编辑器 → 运行引擎
- 自动：文档入库后触发（`trigger_pipeline()` at `engine.py`）
- 定时：cron job（`AIPLAT_GOVERNANCE_CRON_HOURS`，默认 24h）

```
OntologyEngine.process_chunks(chunks, doc_id, domain)

  ═══ Phase 1: 并行分类 + 表格上下文 ═══
  Step 1 [engine.py:97-133]  ClassMapper.classify_text()
    └─ 关键词倒排索引映射文本到本体类 → 零 LLM, <1ms

  ═══ Phase 2: 并行属性提取 ═══
  Step 2 [engine.py:136-159]  PropertyExtractor.extract()
    └─ asyncio.gather() 并行 LLM, semaphore=5 → 提取类字段值

  ═══ Phase 3: 串行验证+消歧+建图 ═══
  Step 3  [engine.py:161-195]  验证 required_fields → Build 实例
  Step 4  [engine.py:221-232]  SourceTrace 溯源 → ~/.aiplat/ontology_traces/
  Step 5  [engine.py:234-253]  EntityResolver.resolve() → 实体去重合并
  Step 6  [engine.py:257-258]  compute_indicators() → 功能完整性指标
  Step 7  [engine.py:261-396]  StateMachine.evaluate_chain() → 状态转换 + side_effects
  Step 8  [engine.py:397-417]  ProcessOrchestrator → 步骤完成检测

  ═══ Phase 4: 图构建 ═══
  Step 9  [engine.py:424-433]   RelationMapper.detect_co_occurrence() → 关系检测

  Step 10 [engine.py:436-505]  GraphIndex 构建
    ├─ graph.add_entity() [line 443]     → graph_nodes 表
    ├─ graph.add_relations_batch() [451] → graph_edges 表（inferred=0）
    ├─ graph.add_hyperedge() [469]       → graph_hyperedges 表
    ├─ graph.save() [452]                → 持久化到 ~/.aiplat/graph/{domain}.db
    ├─ GraphInference.infer() [477]      → YAML inference_rules → inferred edges(inferred=1)
    │                                     → graph_edges 表
    └─ inject_case_study_nodes() [490]   → case_study 节点 + case_study_of 边

  ═══ Phase 5: 知识合成 → Wiki KB ═══
  Step 11 [engine.py:508-517]  KnowledgeSynthesizer.synthesize(write_to_wiki=True)
    ├─ 推理链页面: 从 inferred edges 生成 "A →(rel)→ B" 说明页
    │   └─ wiki_engine.write_page(category="synthesis")
    ├─ 事实卡: 从 Hyperedges 生成事件事实卡
    │   └─ wiki_engine.write_page(category="topics")
    └─ 综合结论: 从 ≥3 hyperedges 的实体生成结论页
        └─ wiki_engine.write_page(category="synthesis")
    └─ 写入 ~/.aiplat/wiki/collections/{collection_id}/synthesis/*.md

  ═══ 可选: 审批工作流 ═══
  Step 12 [engine.py:786-839]  高风险实体 → ApprovalGate
```

**数据流总结**：

```
kb_elements (原始数据)
     │
     │ process_chunks()
     ▼
┌─────────────────────────────────┐
│  ClassMapper + PropertyExtractor │  (LLM 提取)
│            ↓                     │
│   EntityResolver + StateMachine  │  (去重 + 状态)
│            ↓                     │
│  GraphIndex (graph_nodes/edges)  │  → ~/.aiplat/graph/{domain}.db
│            ↓                     │
│  KnowledgeSynthesizer            │  (合成 Wiki 页面)
│            ↓                     │
│  Wiki Pages (*.md)               │  → ~/.aiplat/wiki/collections/{id}/
└─────────────────────────────────┘
```

### 3.3 自动更新触发链路（v2.9）

文档变化后，系统通过以下链路人动触发三阶段更新：

```
原始资料变化 (文件内容改变)
  │
  ├─ watch_directory 轮询 (30s)
  │   └─ enqueue_directory_ingest() → 检测变更 → 重新入库
  │
  ├─ [阶段 1] 向量 KB 自动重导入 ✅
  │   └─ enqueue_ingest() → ingest_document() → kb_elements + kb_embeddings
  │
  ├─ [阶段 2] Wiki KB 自动生成 ✅ (即发即忘)
  │   └─ wiki_auto_update() → 解析文档 → write_page() → LLM 策展
  │       └─ auto_ontology_pipeline_for_doc() → 本体引擎 11 步
  │           ├─ 实体/关系提取
  │           ├─ GraphIndex 更新
  │           └─ KnowledgeSynthesizer → Wiki 合成页面
  │
  └─ [阶段 3] 本体引擎自动触发 ✅ (v2.9, 即发即忘)
      └─ auto_ontology_pipeline_for_doc() [core_facade.py:1037]
          ├─ 门控: AIPLAT_AUTO_ONTOLOGY_PIPELINE=true (默认开启)
          ├─ 解析文档 → 分块 → process_chunks()
          ├─ 更新 GraphIndex 节点 + 边
          └─ KnowledgeSynthesizer 合成 Wiki 页面
```

**触发位置**：
| 触发场景 | 文件:行号 |
|:--|:--|
| 单文档上传 | `platform/api/rest/routes.py:1619` → `_auto_ontology_pipeline()` |
| watch_directory 轮询 | `platform/kb/service.py:1248` → `auto_ontology_pipeline_for_doc()` |

**环境变量控制**：`AIPLAT_AUTO_ONTOLOGY_PIPELINE=false` 可关闭自动触发。

**性能考量**：每次触发运行完整的 11 步本体引擎管线（包含 LLM 调用），单文档约 2-10 秒。大体积文档限制前 20 个 chunk（每 chunk ≤8000 字符）。

---

## 四、RAG 检索完整流程

### 4.1 入口：MaterialsChatAgent

**文件**：`aiPlat-core/core/apps/agents/materials_chat.py:172` `_execute_impl()`

```
用户输入 query
  │
  ├─[1] sanitize_query(query)                  [line 199]  输入清洗
  ├─[2] Cost-aware routing estimate             [line 202]  成本估算
  ├─[3] Semantic cache L1/L2/L3 check           [line 213]  语义缓存命中检查
  │     (命中 → 直接返回, 跳过后续)
  │
  ├─[4] DMQR multi-query rewrite enrichment     [line 327]  多查询扩展
  ├─[5] QuestionAnalysis → intent + strategy    [line 316]  意图分析
  │
  ├─[6] DomainRouter.classify(query) → domain_id [line 339]
  │     └─ 3 级级联: 标签匹配 → embedding 余弦 → LLM 二分类
  │        [core/harness/knowledge/domain_router.py:43]
  │
  ├─[7] map_query_to_ontology(q, domain_id) → target_class  [line 396]
  │     └─ 本体 YAML 类名匹配, 自适应阈值
  │
  ├─[8] ShardedGraphIndex 跨域图遍历           [line 446]
  │     └─ cross_domain_neighbors(primary_domain, allow_cross)
  │
  ├─[9] ═══ sys_retrieve_crag() 三级检索 ═══   [line 509]
  │     │  (见 §4.3)
  │     └─ 返回检索结果集 (Wiki + KB 混合)
  │
  ├─[10] 答案生成                               [line 632]
  │      ├─ Domain-specific system prompt 注入  [prompt_loader]
  │      ├─ RunContext 注入 (GraphIndex 上下文)  [line 533]
  │      ├─ Doc compression (context window)     [line 548]
  │      ├─ LLM generate
  │      ├─ Hallucination check                  [line 553]
  │      └─ Self-RAG: low_evidence → HyDE 重试   [line 661]
  │
  └─[11] 返回答案 + 检索证据 + 置信度
```

### 4.2 并行检索：WSG + KB 双路 RRF 融合

**文件**：`aiPlat-core/core/harness/syscalls/retrieval.py:554` `sys_knowledge_retrieve()`

```
sys_knowledge_retrieve(query, domain_id, collection_id, ...)
  │
  ├─ GraphIndex 早期退出（confidence > 0.92）    [line 669-698]
  │
  ├─ ═══ 并行检索 (ThreadPoolExecutor, 2 workers) ═══
  │   │
  │   ├─ sys_wiki_retrieve()                      [line 619-641]
  │   │   └─ WikiPageRetriever.retrieve()          [wiki_retriever.py:306]
  │   │       ├─ _load_pages(): 加载所有 wiki 页面
  │   │       ├─ _filter_by_class(): T-Box 类过滤 + 子类展开
  │   │       ├─ _expand_by_inference(): 传递闭包 + source chains
  │   │       ├─ embed_text_semantic(query)          [line 352]
  │   │       ├─ cosine_similarity                    [line 402]
  │   │       ├─ FTS5 keyword boost                   [line 427]
  │   │       ├─ Post-retrieval governance:
  │   │       │   ├─ 新鲜度评分 (freshness)
  │   │       │   ├─ 可信度评分 (credibility)
  │   │       │   └─ 密度评分 (density)
  │   │       ├─ A-Box relation boost
  │   │       └─ 矛盾感知 surface                     [line 463-511]
  │   │
  │   └─ sys_kb_retrieve()                          [line 643-659]
  │       └─ SqliteEmbeddingRetriever.retrieve()     [sqlite_retriever.py:69]
  │           ├─ _load_embeddings(): kb_embeddings JOIN kb_elements
  │           ├─ embed_text_semantic(query) → numpy cosine
  │           ├─ FTS5 supplemental search
  │           ├─ Cross-encoder rerank                 [line 155]
  │           └─ Peak-End anchoring (top + second at end)
  │
  └─ ═══ RRF 融合 (Reciprocal Rank Fusion) ═══   [retrieval.py:700-733]
      │
      │  Formula: score(k) = Σ  w_i / (k + rank_i + 1)
      │    where k=60, w_wiki=1.1, w_kb=1.0
      │
      ├─ 按 normalized title 去重 (同文档在 Wiki+KB 都命中 → 分数相加)
      ├─ 保留 top_k × 2 条结果
      ├─ Score normalization + governance penalty       [line 735-785]
      └─ 返回 KnowledgeResult[] (已带 source_type: wiki/kb)
```

### 4.3 CRAG 三级回退机制

**文件**：`aiPlat-core/core/harness/knowledge/retrieval_crag.py:30` `sys_retrieve_crag()`

| 级别 | 策略 | 触发条件 | 速度 |
|:--:|------|------|:--:|
| **L1** | 本体优先 Wiki 检索（target_class 过滤 + 子类展开） | 始终执行 | ~100ms |
| **L2** | KB FTS5 关键词检索（`kb_elements_fts` 表） | L1 结果 < 100 字 | ~50ms |
| **L3** | HyDE 假设答案重检（LLM 生成假设答案 → 重新检索） | L2 结果 < 50 字 | ~500ms |

**L3 触发后**：LLM 先根据问题生成一个"假设的正确答案"（HyDE: Hypothetical Document Embedding），然后用这个假设答案代替原始问题进行向量检索。这能捕获原始查询中隐含但未明确表述的语义。

```python
# retrieval_crag.py:116-131
def hyde_retrieve(query, domain_id, ...):
    hypothesis = llm.generate(f"请根据以下问题生成一个假设的答案段落...\n{query}")
    return ontology_first_retrieve(hypothesis, domain_id, ...)
```

### 4.4 检索路径选优矩阵

| 条件 | 检索路径 | 优先级 |
|:--|:--|:--:|
| 本体映射 confidence ≥ 0.8 | 本体优先检索（Wiki + target_class 过滤）| 1（最高） |
| 查询包含已知实体名 | GraphIndex 遍历 + terminal entities 增强检索词 | 2 |
| 前述路径结果 < 100 字 | FTS5 关键词检索 | 3 |
| 前述路径结果 < 50 字 | HyDE 假设答案重检 | 4（最低） |

---

## 五、关系映射

### 5.1 domain_id ↔ collection_id

**文件**：`core/harness/knowledge/domain_router.py:153` `DomainRouter.resolve()`

定义在 `~/.aiplat/ontologies/registry.json`：

```json
{
  "domains": {
    "ai-knowledge": {
      "collection_id": "ai-knowledge",
      "name": "AI知识",
      ...
    }
  }
}
```

| 映射方向 | 方法 | 说明 |
|:--|:--|:--|
| collection_id → domain_id | `DomainRouter.resolve(collection_id)` | 查 registry.json |
| domain_id → collection_id | `DomainRouter.resolve_collection(domain_id)` | 反向查 registry.json |
| query → domain_id | `DomainRouter.classify(query)` | 3 级联级：标签匹配 → 向量余弦 → LLM |

在多数情况下 domain_id === collection_id（同名字符串）。

### 5.2 tenant_id ↔ collection_id

KB 数据库路径：`~/.aiplat/kb/tenants/{tenant_id}/kb.sqlite3`

`SqliteEmbeddingRetriever.__init__()` 同时接受 `tenant_id` 和 `collection_id`（`sqlite_retriever.py:40`）。

知识库检索通过 `json_extract(meta_json, '$.domain')` 做域级预过滤（向后兼容：无 domain 标签的旧数据不过滤）。

### 5.3 kb_elements → GraphIndex → Wiki 的关联链路

```
kb_elements.doc_id
  → graph_nodes.source_doc_id    (graph 节点可追溯到源文档)
  → wiki_engine 写入时 source_articles: ["kb:{doc_id}"]  (wiki 页面链接到 KB)
  → KB documents.meta_json.wiki_pages  (KB 回写关联的 wiki 页面标题)
```

### 5.4 全系统数据流总图

```
┌──────────────────────────────────────────────────────────────┐
│                    文档上传 (ingest)                          │
│                         │                                    │
│           ┌─────────────┴─────────────┐                      │
│           ▼                           ▼                      │
│  ┌─────────────────┐         ┌──────────────────┐            │
│  │  向量 KB          │         │  本体引擎 Pipeline │            │
│  │  kb_elements     │────────▶│  process_chunks() │            │
│  │  kb_embeddings   │  输入    │                    │            │
│  │  documents       │         │  Step 1-9: 提取    │            │
│  └─────────────────┘         │  Step 10: GraphIndex│           │
│        ▲                      │  Step 11: Wiki      │            │
│        │                      └────────┬───────────┘            │
│        │                               │                        │
│        │              ┌────────────────┼────────────────┐       │
│        │              ▼                ▼                │       │
│        │    ┌─────────────┐  ┌──────────────────┐      │       │
│        │    │  GraphIndex  │  │   LLM Wiki KB     │      │       │
│        │    │  (SQLite)    │  │   (Markdown)      │      │       │
│        │    │  ~/.aiplat/  │  │   ~/.aiplat/wiki/ │      │       │
│        │    │  graph/{id}.db│  │   collections/   │      │       │
│        │    └──────┬──────┘  └────────┬─────────┘      │       │
│        │           │                  │                 │       │
│        │           └──────┬───────────┘                 │       │
│        │                  │  RAG 查询                   │       │
│        │                  ▼                             │       │
│        │    ┌──────────────────────────┐               │       │
│        └────│  sys_knowledge_retrieve   │               │       │
│             │  并行 Wiki + KB 检索      │               │       │
│             │  RRF 融合 (wiki×1.1)      │               │       │
│             └────────────┬─────────────┘               │       │
│                          ▼                             │       │
│             ┌──────────────────────────┐               │       │
│             │  MaterialsChatAgent       │               │       │
│             │  LLM 生成答案             │               │       │
│             └──────────────────────────┘               │       │
└──────────────────────────────────────────────────────────────┘
```

---

## 六、运维指南

### 6.1 状态检查命令

```bash
# 查看所有 domain 的 ontology YAML
ls -la ~/.aiplat/ontologies/*.yaml

# 查看各 GraphIndex 的大小
ls -lh ~/.aiplat/graph/*.db

# 查看 kb_elements 文档统计
python3 -c "
import sqlite3, os
db = os.path.expanduser('~/.aiplat/kb/tenants/default/kb.sqlite3')
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
docs = conn.execute('SELECT collection_id, status, count(*) as c FROM documents GROUP BY collection_id, status').fetchall()
for d in docs: print(f'{d[\"collection_id\"]}: [{d[\"status\"]}] x{d[\"c\"]}')
conn.close()
"

# 查看 Wiki 页面数
ls ~/.aiplat/wiki/collections/*/entities/*.md 2>/dev/null | wc -l

# 查看最近入库任务
python3 -c "
import sqlite3, os
db = os.path.expanduser('~/.aiplat/kb/tenants/default/kb.sqlite3')
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
jobs = conn.execute('SELECT type, status, count(*) as c FROM kb_jobs GROUP BY type, status').fetchall()
for j in jobs: print(f'{j[\"type\"]}: [{j[\"status\"]}] x{j[\"c\"]}')
conn.close()
"
```

### 6.2 常见问题

| 问题 | 排查方法 | 解决方案 |
|:--|:--|:--|
| 文档入库后状态卡在 `queued` | 查看 kb_jobs 状态（`status='failed'` 说明后台入库失败） | 通过 API `POST /api/v1/kb/documents/{doc_id}/reingest` 重新触发 |
| 本体引擎结果未出现在 Wiki | 检查 `process_chunks()` 是否运行成功；查看 `~/.aiplat/ontology_traces/` | 手动触发引擎：管理端 → 本体编辑器 → 运行 |
| RAG 检索结果质量差 | 检查检索路径是否降级到 FTS5/HyDE；查看 `materials_chat.py` 日志 | 增加 CRAG L1 结果阈值；检查本体 YAML 类定义完整性 |
| Wiki 页面过期 | 查看 `expiry_date` frontmatter；检查 `search_pages(expiry_before=...)` | 手动更新页面版本；触发 KnowledgeSynthesizer 重生成 |
| 跨域查询无结果 | 检查 `ShardedGraphIndex` 跨域配置 | 设置 `allow_cross=True`；配置 `registry.json.fallback_domains` |
| 修改本体 YAML 后 GraphIndex 节点孤儿化 | 类重命名后旧 class_name 的节点不可见 | 使用 `POST /ontology/domains/{id}/migrate-classify` 迁移节点 |
| 修改本体 YAML 后 DomainRouter 分类错误 | DomainRouter 缓存未刷新（v2.9 起 CRUD 操作自动失效缓存） | v2.9+：自动；旧版：调用 `publish_ontology_domain()` 或重启服务 |

### 6.3 GrillingGate 运行时注入（v2.9）

**架构**：grilling（需求澄清）是运行时系统能力，由 ReActLoop 在执行前自动检测歧义并触发，不需要任何 Agent 声明。

```
用户输入 (任意 Agent / Pipeline / 入口)
    │
    ▼
ReActLoop.run() [loop/base.py:62]
    ├─ PRE_LOOP hooks
    ├─ Task type inference
    ├─ ═══ GrillingGate ═══ [loop/base.py:247]
    │   ├─ 检查 is_interactive (真人用户?)
    │   ├─ 检查输入歧义 (short + trigger keywords)
    │   ├─ 检查防重入 (_auto_grilled guard)
    │   └─ 条件满足 → start_grilling() → auto-answer → 注入 _grilling_output
    │
    └─ Reasoning → Acting → Observing (标准 ReAct 循环)
```

**GrillingBridge API**（`routers/grilling.py`）：
| 端点 | 方法 | 功能 |
|:--|:--|:--|
| `/api/core/grilling/start` | POST | 启动面试会话，返回第一个问题 |
| `/api/core/grilling/answer` | POST | 提交答案，返回下一问或完成 |
| `/api/core/grilling/skip` | POST | 跳过当前非必填问题 |
| `/api/core/grilling/progress/{id}` | GET | 获取会话状态（恢复断会话） |
| `/api/core/grilling/finalize` | POST | 提前结束，返回结构化输出 |

**触发路径双轨制**：
| 路径 | 触发者 | 机制 |
|:--|:--|:--|
| **运行时自动** | GrillingGate (ReActLoop) | 检测到歧义 → 自动触发 interview |
| **用户手动** | GrillPanel 前端组件 | 点击按钮 → 打开向导式澄清面板 |

**域维度映射**（`interview_dimensions` in domain YAML）：
| 域 | entry_point | 首要问题 |
|:--|:--|:--|
| fde-delivery | fde_builder | 你要构建什么类型的项目？ |
| procurement-mvo | workbench | 采购预算范围？ |
| ai-knowledge | kb_qa | 你想了解 AI 知识的哪个方向？ |
| ship-design | fde_builder | 设计的船舶类型？ |
| it-ops | agent_chat | 运维事件类型？ |
| supply-chain | workbench | 关注的供应链环节？ |
| lock-service | workbench | 涉及的锁具类型？ |
| 修改本体 YAML 后 GraphIndex 节点孤儿化 | 类重命名后旧 class_name 的节点不可见 | 使用 `POST /ontology/domains/{id}/migrate-classify` 迁移节点 |
| 修改本体 YAML 后 DomainRouter 分类错误 | DomainRouter 缓存未刷新（v2.9 起 CRUD 操作自动失效缓存） | v2.9+：自动；旧版：调用 `publish_ontology_domain()` 或重启服务 |

### 6.3 性能基线

| 指标 | 目标 | 检测命令 |
|:--|:--:|:--|
| 单文档入库 P95 | < 30s (text) / < 300s (video) | `kb_jobs` 表 `updated_at - created_at` |
| 本体引擎管道 P95 | < 60s | `bash scripts/benchmark_ontology.sh` |
| 检索 Recall@10 | > 85% | `python3 scripts/eval_retrieval.py` |
| RRF 融合延迟 | < 200ms | `syscalls/retrieval.py` 日志 `total` 字段 |

### 6.4 关键文件索引

| 文件 | 功能 |
|:--|:--|
| `aiPlat-platform/kb/service.py` | 文档入库主逻辑（`enqueue_ingest`, `ingest_document`）|
| `aiPlat-platform/kb/db.py` | KBSqlite 表定义与 CRUD |
| `aiPlat-platform/kb/video.py` | 视频处理管线 |
| `aiPlat-core/core/harness/ontology_engine/engine.py` | 本体引擎 11 步管线 |
| `aiPlat-core/core/harness/ontology_engine/graph_index.py` | GraphIndex 图存储 |
| `aiPlat-core/core/harness/knowledge/wiki_engine.py` | Wiki KB 读写检索 |
| `aiPlat-core/core/harness/knowledge/domain_router.py` | 域路由器（3 级联级） |
| `aiPlat-core/core/harness/syscalls/retrieval.py` | 统一检索 syscall（双路 RRF） |
| `aiPlat-core/core/harness/knowledge/retrieval_crag.py` | CRAG 三级回退 |
| `aiPlat-core/core/harness/knowledge/sqlite_retriever.py` | SQLite 向量检索器 |
| `aiPlat-core/core/harness/knowledge/wiki_retriever.py` | Wiki 页面检索器 |
| `aiPlat-core/core/apps/agents/materials_chat.py` | RAG Agent（MaterialsChatAgent） |
| `~/.aiplat/ontologies/registry.json` | 域注册表（domain_id ↔ collection_id） |
