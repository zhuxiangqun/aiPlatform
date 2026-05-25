# 知识管理 (Knowledge)

> 说明：本文档描述 Harness 的 Knowledge 子系统（`core/harness/knowledge/*`）。
> 状态标记遵循 [`ARCHITECTURE_STATUS.md`](../ARCHITECTURE_STATUS.md) 的 As-Is / To-Be 规范。
> 跨层归属判断参见：`docs/architecture/boundary-standard.md`
>
> 最后更新：2026-05-13

---

## 1. 模块定位

Knowledge 模块为 Agent 提供知识库管理和语义检索能力，是 Harness 框架的核心组件之一。

**代码位置**：`core/harness/knowledge/`

**状态标记说明**：

| 标记 | 含义 |
|------|------|
| ✅ 已实现 | 代码存在且功能可用 |
| 🔧 结构存在 | 接口/框架存在，关键实现待从 Platform 上移 |
| ❌ 未实现 | 代码不存在（仅有 .pyc 缓存残留） |
| 📝 规划中 | 设计文档描述但尚未实施 |

---

## 2. 模块结构（As-Is）

```
harness/knowledge/
├── __init__.py              ← 模块出口 ✅
├── types.py                 ← KnowledgeType/Entry/Query/Result 类型体系 ✅
├── retriever.py             ← IRetriever/IEmbedder 接口 + InMemoryRetriever + VectorStoreRetriever ✅
├── embedder.py              ← SemanticEmbedder + hash_embed fallback + 缓存层 ✅
└── db.py                    ← Provider 桥接 (set/get_knowledge_db) ✅
```

**已删除/已迁移**：
- `indexer.py` — 仅有 .pyc 残留，源文件从未实现。属于 📝 规划中。
- `evolution.py` — 仅有 .pyc 残留，源文件从未实现。属于 📝 规划中。
- `competition/` 子目录 — 不存在。

---

## 3. 核心组件

### 3.1 KnowledgeRetriever — 知识检索器 ✅

**代码入口**：`retriever.py::KnowledgeRetriever`

**检索后端**（通过 IRetriever 接口切换）：

| 后端 | 类 | 状态 | 说明 |
|------|-----|------|------|
| 内存检索 | `InMemoryRetriever` | ✅ | 默认后端，支持语义嵌入 |
| 向量存储检索 | `VectorStoreRetriever` | ✅ | FAISS/Milvus/Chroma/Pinecone，通过 infra_bridge |
| SQLite 检索 | `KBSqliteRetriever` | 🔧 待实现 | 直接从 platform SQLite 检索 |

**检索能力**（As-Is）：
- ✅ 语义相似度检索（通过 SemanticEmbedder）
- ✅ 关键词回退（通过 `_score_text`，目前仍在 Platform，待上移）
- ❌ 混合检索（向量 + 关键词联合）—— 规划中
- ❌ 重排序（rerank）—— 规划中

**核心方法**：

| 方法 | 状态 | 说明 |
|------|------|------|
| `search()` | ✅ | 语义检索 |
| `search_by_type()` | ✅ | 按类型过滤检索 |
| `add_knowledge()` | ✅ | 添加知识条目 |
| `hybrid_retrieve()` | ❌ | 混合检索——规划中 |
| `rerank()` | ❌ | 结果重排序——规划中 |

### 3.2 SemanticEmbedder — 语义嵌入器 ✅

**代码入口**：`embedder.py::SemanticEmbedder`

**嵌入后端**（通过 `AIPLAT_EMBED_BACKEND` 环境变量切换）：

| 后端 | 状态 | 说明 |
|------|------|------|
| `hash` | ✅ | SHA-256 n-gram hash（默认，零依赖） |
| `transform` | ✅ | sentence-transformers (`all-MiniLM-L6-v2`) |
| `api` | ✅ | OpenAI 兼容 Embedding API |

**缓存层**：✅ 内置于 `embedder.py`，替代了原先 Platform `embeddings.py` 中的独立缓存。

### 3.3 文档处理 📝 🔧

**设计规范**（To-Be，来自 `docs/architecture/boundary-standard.md` §3.1）：

| 模块 | 位置 | 状态 | 说明 |
|------|------|------|------|
| 文档解析 | `harness/document/parsers.py` | 🔧 待从 Platform 上移 | docx/pptx/md 文本提取 |
| 文本分块 | `harness/document/chunker.py` | 🔧 待新建 | fixed/semantic/recursive |
| 视频转写 | `harness/document/transcriber.py` | 🔧 待从 Platform 上移 | Whisper 模型推理 |
| 图像 OCR | `harness/document/ocr.py` | 🔧 待从 Platform 上移 | Tesseract 模型推理 |

**当前实现（As-Is）**：
- 🔧 文档解析：在 `platform/kb/intelligence/doc_parser.py`（违规，待上移）
- 🔧 视频转录+OCR：在 `platform/kb/video.py`（违规，待上移）
- ❌ 文本分块：不存在，需新建

### 3.4 KnowledgeIndexer ❌

**设计描述**（To-Be）：
- 文档解析（PDF、Markdown、代码）
- 智能分块
- 向量嵌入生成
- 索引构建与更新

**当前实现（As-Is）**：❌ 不存在（`indexer.py` 仅残留 `__pycache__/indexer.cpython-*.pyc`，源文件从未创建）。文档解析能力当前以独立函数分散在 Platform 中（见 §3.3）。

### 3.5 KnowledgeEvolution ❌

**设计描述**（To-Be）：
- 增量索引新文档
- 更新检测与同步
- 版本管理
- 过期知识清理

**当前实现（As-Is）**：❌ 不存在（`evolution.py` 仅残留 .pyc 缓存）。相关能力当前由 Platform 的 `enqueue_ingest` + job 队列实现。

---

## 4. 检索流程（As-Is）

```
用户查询
    │
    ▼
┌─────────────────────┐
│  KnowledgeRetriever │  ← core/harness/knowledge/retriever.py ✅
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    ▼             ▼
语义检索      关键词回退       ← 语义检索在 Core ✅ / 关键词在 Platform 🔧
(InMemory/     (_score_text,
 VectorStore)  当前在 platform)
    │             │
    └──────┬──────┘
           ▼
       结果合并 + 去重
           │
           ▼
      Top-K 结果
```

> **注意**：完整检索流程（语义 + 关键词 + 合并 + 去重）当前部分在 `platform/kb/intelligence/query.py::query_elements()` 中实现，待上移到 `core/harness/knowledge/retriever.py`。

---

## 5. Core ↔ Platform 依赖关系

```
Platform (Layer 2)
  │
  │ 通过 provider 回调 → kb_provider.py
  │ 通过 CoreFacade    → KnowledgeRetriever / SemanticEmbedder
  │
  ▼
Core (Layer 1)
  harness/knowledge/       ← 知识系统接口 + 实现
  harness/document/        ← 文档处理 (待新建)
  apps/document_intelligence/ ← Internal Policy
  │
  │ 通过 infra_bridge
  ▼
Infra (Layer 0)
  infra/vector/            ← FAISS/Milvus/Chroma/Pinecone (已实现，已接线 ✅)
```

**规则**：
- Platform **禁止**直接 import 模型库（faster_whisper、pytesseract 等）—— 违反铁律 1
- Platform **禁止**在 `intelligence/` 子目录中实现检索算法—— 违反铁律 2
- Platform 通过 `kb_provider` 回调模式或 CoreFacade 访问 Core 能力—— 正确

---

## 6. 相关文档

- [边界判断标准（权威）](../../docs/architecture/boundary-standard.md) — 跨层归属标准
- [系统整体架构规范](../../docs/architecture/system-architecture-contract.md) — 四层契约
- [Architecture Contract (Core Internal)](../contracts/01-architecture-contract.md) — Core 内部边界
- [Harness 索引](../harness/index.md)
- [RAG Agent](../../core/apps/agents/rag.py)

---

## 7. 证据索引

- Knowledge 模块入口：`core/harness/knowledge/__init__.py`
- 检索器：`core/harness/knowledge/retriever.py` (`KnowledgeRetriever`, `InMemoryRetriever`, `VectorStoreRetriever`)
- 嵌入器：`core/harness/knowledge/embedder.py` (`SemanticEmbedder`, `hash_embed`, `cosine_similarity`)
- 类型体系：`core/harness/knowledge/types.py`
- Provider 桥接：`core/harness/knowledge/db.py`
- KB Provider 回调：`core/apps/document_intelligence/kb_provider.py`
- 架构守卫（导入检查）：`scripts/architecture_guard.sh`
- 架构守卫（语义检查）：`tests/constitution/` (规划中：`test_platform_no_model_imports.py` 等)
