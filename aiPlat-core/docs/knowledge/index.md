# 知识管理 (Knowledge)（设计真值：以代码事实为准）

> 说明：本文档描述 Harness 的 Knowledge 子系统（`core/harness/knowledge/*`）。
> 统一口径参见：[架构实现状态](../ARCHITECTURE_STATUS.md)。

> 知识管理模块负责知识库的构建、维护和查询，支持检索增强生成（RAG）等场景。

---

## 模块定位

Knowledge 模块为 Agent 提供知识库管理和语义检索能力，是 Harness 框架的核心组件之一。

**代码位置**：`core/harness/knowledge/`

**核心能力**：
- 文档解析与分块
- 向量嵌入与索引
- 语义检索与排序
- 知识图谱构建
- 知识更新与同步

---

## 模块结构

```
harness/knowledge/
├── __init__.py              # 模块入口
├── types.py                 # 知识类型定义
├── retriever.py             # 知识检索器
├── indexer.py               # 知识索引器
└── evolution.py             # 知识进化
```

## 核心组件

### 1. KnowledgeRetriever - 知识检索器

> 语义检索与混合检索能力

**位置**：`retriever.py`

**功能**：
- 语义相似度检索
- 关键词检索
- 混合检索（向量+关键词）
- 重排序

**核心方法**：

| 方法 | 功能 |
|------|------|
| `retrieve()` | 语义检索 |
| `hybrid_retrieve()` | 混合检索 |
| `rerank()` | 结果重排序 |

### 2. KnowledgeIndexer - 知识索引器

> 文档解析、分块与向量索引

**位置**：`indexer.py`

**功能**：
- 文档解析（PDF、Markdown、代码）
- 智能分块
- 向量嵌入生成
- 索引构建与更新

### 3. KnowledgeEvolution - 知识进化

> 知识库的增量更新与同步

**位置**：`evolution.py`

**功能**：
- 增量索引新文档
- 更新检测与同步
- 版本管理
- 过期知识清理

### 检索流程

```
用户查询
    │
    ▼
┌─────────────────────┐
│  KnowledgeRetriever │
└──────────┬──────────┘
           │
    ┌──────┴──────┐
    ▼             ▼
语义检索      关键词检索
    │             │
    └──────┬──────┘
           ▼
      混合结果
           │
           ▼
       重排序
           │
           ▼
      Top-K 结果
```

---

## 与其他模块的关系

| 模块 | 关系 |
|------|------|
| **harness** | 使用 Harness 的知识接口 |
| **agents** | Agent 使用知识库进行 RAG |
| **models** | 使用模型生成嵌入向量 |

---

## 相关文档

- [Harness 索引](../harness/index.md) - 智能体框架
- [RAG Agent（代码）](../../core/apps/agents/rag.py) - 检索增强生成

---

*最后更新: 2026-04-14*

---

## 证据索引（Evidence Index｜抽样）

- Knowledge 模块：`core/harness/knowledge/*`
- Retriever：`core/harness/knowledge/retriever.py`
- Indexer：`core/harness/knowledge/indexer.py`
