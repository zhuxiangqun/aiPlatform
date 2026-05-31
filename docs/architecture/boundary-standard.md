# aiPlatform 层边界判断标准

> 本文档是 aiPlatform 四层架构中 **各层之间** 模块归属的权威判断标准。
> 当设计文档、代码实现、PR 评审中出现归属争议时，以本文档为准。
>
> 当前覆盖：Core ↔ Platform（完整）、Platform ↔ App（新增）、App ↔ 外部
>
> 父文档：`docs/architecture/system-architecture-contract.md`
> 子文档：`aiPlat-core/docs/contracts/01-architecture-contract.md`
>
> 最后更新：2026-05

---

## 1. 两条铁律

### 铁律 1：模型推理归属 Core

任何加载并执行 AI 模型的代码属于 Core 的 AI 运行时职责。具体包括：

| 模型类型 | 示例 | Core 中的位置（现有/规划） |
|---------|------|--------------------------|
| LLM 推理 | `sys_llm_generate` | `harness/syscalls/llm.py` ✅ |
| Embedding 生成 | SentenceTransformer / OpenAI Embeddings API | `harness/knowledge/embedder.py` ✅ |
| 语音转写 | Whisper (faster-whisper / openai-whisper) | **需新建** `harness/document/transcriber.py` |
| 图像 OCR | Tesseract / PaddleOCR | **需新建** `harness/document/ocr.py` |
| 语义分块 | 基于 Embedding 的 semantic chunking | **需新建** `harness/document/chunker.py` |

**规则**：Platform 只能通过 CoreFacade 或 provider 回调间接使用模型能力，**禁止直接 import 模型库**（如 `import faster_whisper`、`import pytesseract`）。

**理由**：模型切换不应改动 Platform。这和 infra 层负责"LLM API 调用细节"是同一条原则的延伸——Core 管理模型加载和推理，Infra 管理 API 传输和配置。

### 铁律 2：可复用性决定归属

删除具体的 Platform 应用概念后，该能力是否对 ≥2 个其他场景有价值？

```
是 → Core（例：文档解析——聊天、Code Review、RAG 都需要）
否 → Platform（例：预算关键词匹配——仅"投资预算"场景需要）
```

**自检问题**：如果未来要支持"会议纪要助手""合同审查助手""论文研读助手"，这个能力是否需要重新实现？需要 → 该能力应该已经在 Core 中。

---

### 1.3 Infra Bridge 模式：依赖倒置的三步走

Platform 禁止直接依赖 Infra。但当 Platform 需要数据库、向量存储等基础设施时，通过 Core 提供的 **Infra Bridge** 端口访问。具体模式：

```
步骤 1: Core 定义抽象端口（在 core/harness/infrastructure/ 或 core/harness/knowledge/ 中）
        DatabasePort    = Protocol { execute(sql, params) → rows }
        VectorStorePort = Protocol { add(vectors, metadata); search(qvec, top_k) → results }

步骤 2: Infra 提供具体实现（在 aiPlat-infra/infra/ 中）
        SqliteClient   implements DatabasePort
        FaissStore     implements VectorStorePort

步骤 3: Platform 注入并调用（通过 infra_bridge 获取端口实例）
        db = create_infra_database_client()  ← 返回 DatabasePort，而非裸 sqlite3.Connection
        db.execute("SELECT ...")             ← 通过端口调用，不直接 import sqlite3

规则:
  ✅ Platform 代码中: from core.harness.infrastructure.infra_bridge import create_infra_database_client
  ❌ Platform 代码中: import sqlite3
  ❌ Platform 代码中: import faiss
```

**当前状态**：`core/harness/infrastructure/infra_bridge.py` 已有 `create_infra_vector_client()`、`get_infra_embedding()` 和 `create_infra_database_client()`。`core/harness/infrastructure/database_port.py` 定义 `DatabasePort` Protocol。Platform 的 `storage/sqlite.py`、`kb/db.py`、`api/rest/routes.py` 均已通过 bridge 获取数据库连接，不再直接 `import sqlite3`。

**设计原理**：依赖倒置（Dependency Inversion）。Core 定义"我需要什么能力"（端口），Infra 提供"我能怎么实现"（适配器），Platform 通过 Core 的桥接获取端口实例——三方都不形成直接耦合。

---

## 2. 决策树

将任意模块 X 代入以下流程，即可确定归属：

```
模块 X
  │
  ├─ 是否加载/执行 AI 模型？
  │   └─ 是 → Core（铁律 1）
  │
  ├─ 删除 Platform 的应用概念后，是否有 ≥2 个其他场景？
  │   └─ 是 → Core（铁律 2）
  │
  ├─ 是否属于以下 Platform 专属领域？
  │   ├─ REST API 定义（路径/请求体/响应体）
  │   ├─ 多租户路由（tenant_id → 存储路径/DB 连接）
  │   ├─ 权限鉴权（scope 检查、Token 验证）
  │   ├─ 异步任务队列（job 创建/轮询/状态管理）
  │   ├─ 具体存储实现（KBSqlite、S3 路径、表结构）
  │   └─ 应用特定业务逻辑（领域关键词匹配、行业术语格式化）
  │   └─ 是 → Platform
  │
  ├─ 是否是 Internal Policy（策略选择/分类判断/路由决策）？
  │   └─ 是 → Core（`core/apps/document_intelligence/` 或同级）
  │
  └─ 无法判断 → 默认归属 Core
      （原则：宁可 Core 多一份通用能力，也不让 Platform 背负 AI 逻辑）
```

---

## 3. 模块归属目录：白名单

### 3.1 Core 层拥有

| 一级分类 | 模块 | 位置 | 状态 |
|---------|------|------|------|
| **模型推理** | LLM syscall | `harness/syscalls/llm.py` | ✅ |
| | Embedding 生成 | `harness/knowledge/embedder.py` | ✅ |
| | 语音转写 | `harness/document/transcriber.py` | 🔧 待新建 |
| | 图像 OCR | `harness/document/ocr.py` | 🔧 待新建 |
| **文档处理** | 文档解析 (docx/pptx/md/pdf) | `harness/document/parsers.py` | 🔧 待从 platform 上移 |
| | 文本分块 (fixed/semantic/recursive) | `harness/document/chunker.py` | 🔧 待新建 |
| | 视频帧抽取 (ffmpeg/ffprobe) | `harness/document/video.py` | 🔧 待从 platform 上移 |
| **知识系统** | 类型体系 | `harness/knowledge/types.py` | ✅ |
| | 检索接口 | `harness/knowledge/retriever.py` (IRetriever/IEmbedder) | ✅ |
| | 检索实现 | `harness/knowledge/retriever.py` (InMemory/VectorStore/KBSqlite) | ✅ 已有 InMemory + VectorStore |
| | 向量存储 provider | `harness/knowledge/db.py` | ✅ |
| | 语义嵌入缓存 | `harness/knowledge/embedder.py` | ✅ |
| **Internal Policy** | 问题分析 | `apps/document_intelligence/question_analysis.py` | ✅ |
| | 检索策略 | `apps/document_intelligence/retrieval_policy.py` | ✅ |
| | 回答策略 | `apps/document_intelligence/answer_strategy.py` | ✅ |
| | 策略解析 | `apps/document_intelligence/strategy_resolver.py` | ✅ |
| | KB provider 桥接 | `apps/document_intelligence/kb_provider.py` | ✅ |
| | 文档分类 | `apps/document_intelligence/classifier.py` | 🔧 待从 platform 上移 |
| | 文档摘要 | `apps/document_intelligence/summarizer.py` | ✅ 已从 platform 上移 |
| **Engine Skill** | 知识查询 | `engine/skills/knowledge_query/` | ✅ 通过 kb_provider |
| | 知识入库 | `engine/skills/knowledge_ingest/` | ✅ 通过 kb_provider |
| **代码优先技能** | Skill 原生执行（handler.py） | `apps/skills/registry.py` (autoload) | ✅ 已实现 |
| **自改进环** | 每阶段反射采集 | `harness/execution/pipeline_engine.py::_capture_stage_reflection` | ✅ 已实现 |
| **审计子系统** | Prompt 质量审计 | `harness/audit/prompt_auditor.py` | ✅ 已实现 |
| **ISA 制品** | 理想状态制品（升级 PRD） | `schemas_builder.py::ISAArtifact` | ✅ 已实现 |

### 3.2 Platform 层拥有

| 一级分类 | 模块 | 位置 | 状态 |
|---------|------|------|------|
| **API 网关** | REST 端点（全部 KB 端点） | `api/rest/routes.py` | ✅ |
| | 身份解析 (JWT→tenant/actor/scopes) | `api/rest/routes.py::_resolve_identity` | ✅ |
| | Scope 检查 (kb:read/kb:write) | `api/rest/routes.py::_require_scope` | ✅ |
| **存储实现** | SQLite 表结构与 CRUD | `kb/db.py::KBSqlite` | ✅ |
| | 多租户文件布局 | `kb/storage.py` | ✅ |
| **应用编排** | 文档入库流水线 | `kb/service.py::ingest_document` | ✅ 调 Core parsers → 存 SQLite |
| | 视频入库流水线 | `kb/video.py::ingest_video_document` | ✅ 调 Core video pipeline → 存 SQLite |
| | 异步任务队列 | `kb/db.py::kb_jobs` 表 + 轮询 | ✅ |
| | 检索编排路由 | `kb/intelligence/query.py` | ✅ 调 Core retriever → 编排调用顺序 |
| **业务逻辑** | 预算查询 | `kb/budget_query.py` | ✅ |

### 3.3 App 层拥有

| 一级分类 | 模块 | 位置 | 状态 |
|---------|------|------|------|
| **消息网关** | 渠道适配器 (Telegram/Slack/Wework/CLI) | `channels/` | ✅ |
| | 消息解析与格式转换 | `channels/<adapter>/parser.py` | ✅ |
| | Webhook 接收端点 | `channels/<adapter>/webhook.py` | ✅ |
| **事件系统** | 事件总线 (EventBus) | `events/` | ✅ |
| | 事件订阅与分发 | `events/` | ✅ |
| **CLI** | 终端命令入口 | `cli/` | ✅ |
| **外部桥接** | Platform REST 客户端 | `services/client.py` | ✅ 唯一对 Platform 的接触点 |
| | 响应格式化 (→ 渠道消息) | `services/formatter.py` | ✅ |

---

## 平台层 ↔ 应用层 边界 (Platform ↔ App)

### P1. 核心原则

Platform 和 App 之间通过 **HTTP REST API** 通信，而非 Python import。这是与 Core↔Platform 最根本的区别：

| 特性 | Core ↔ Platform | Platform ↔ App |
|------|----------------|----------------|
| 通信机制 | Python import (CoreFacade) | HTTP REST API |
| 依赖方向 | Platform → Core (import) | App → Platform (HTTP call) |
| 耦合程度 | 编译时耦合（模块级） | 运行时耦合（网络级） |
| 天然隔离 | 弱（容易无意 import） | 强（必须显式 HTTP 调用） |
| 主要风险 | 无意中越层 import | API 版本不兼容 |

### P2. 两条铁律（Platform ↔ App）

#### 铁律 P-1：身份解析只有 Platform 一个权威来源

App 层 **禁止** 自己解析 JWT、API Key、或任何身份凭证。App 接收到的身份信息必须以 Platform 的 HTTP 响应为准。

```
✅ 正确：App 调用 GET /api/v1/identity → Platform 返回 { tenant_id, actor, scopes }
❌ 错误：App 自己 import jwt 并 decode token
```

**理由**：身份解析涉及多租户路由、API Key↔Scope 映射、JWT 密钥轮换——这些是 Platform 的核心职责。App 重复实现会导致安全策略不一致。

#### 铁律 P-2：App 不直接访问 Core

App 对 Core 的所有 AI 能力访问必须经过 Platform 的 REST API。App **禁止** import Core 模块。

```
✅ 正确：App → HTTP → Platform → CoreFacade → Core
❌ 错误：App → import aiPlat_core.harness.syscalls.llm
```

**理由**：App 是多渠道的薄网关，不应承载模型推理、策略判断、知识检索等 AI 逻辑。所有 AI 调用统一经过 Platform 的鉴权、限流、审计链路。

### P3. 决策树（Platform vs App）

```
模块 X
  │
  ├─ 是否处理外部消息渠道的协议差异？
  │   ├─ Telegram Bot API 格式 → App
  │   ├─ Slack Events API 格式 → App
  │   ├─ Wework 回调格式 → App
  │   └─ 是 → App（铁律 P-1：渠道适配）
  │
  ├─ 是否提供对外的 HTTP REST 端点？
  │   ├─ GET /api/v1/kb/search → Platform
  │   ├─ POST /api/v1/kb/ingest → Platform
  │   └─ 是 → Platform
  │
  ├─ 是否涉及权限鉴权与多租户路由？
  │   └─ 是 → Platform（铁律 P-2）
  │
  ├─ 是否是 CLI 终端命令？
  │   └─ 是 → App
  │
  ├─ 是否属于以下 Platform 专属领域？
  │   ├─ Builder 项目管理（团队/项目 CRUD）
  │   ├─ KB 知识库存储（collection/chunk CRUD）
  │   ├─ 治理/审核（内容审核、使用统计）
  │   └─ 是 → Platform
  │
  ├─ 是否属于以下 App 专属领域？
  │   ├─ 消息格式归一化（渠道消息 → 统一内部格式）
  │   ├─ 响应格式适配（内部格式 → 渠道特定卡片/按钮/Markdown）
  │   ├─ Webhook 端点签名验证（Telegram secret token / Slack signing secret）
  │   └─ 是 → App
  │
  └─ 无法判断 → 默认归属 Platform
      （原则：宁可 Platform 多一份管理能力，也不让 App 承载业务逻辑）
```

### P4. 跨层调用标准模式

```
┌──────────┐  HTTP REST   ┌──────────┐
│   App    │ ──────────→  │ Platform │
│ (Layer3) │              │ (Layer2) │
└──────────┘              └──────────┘
     │                          │
     │ 唯一接触点：               │
     │ services/client.py        │
     │                          │
     │  ❌ 禁止 import platform   │
     │  ❌ 禁止 import core       │
     │  ❌ 禁止 import infra      │
     │                          │
     └── POST /api/v1/... ──────→ Platform 处理
```

App 中唯一允许调用 Platform 的模块是 `services/client.py`，它封装 HTTP 请求。App 的其他模块通过 `services/client.py` 间接访问 Platform 能力。

### P5. 数据流：从外部消息到 AI 响应

```
外部用户 ─→ Telegram/Slack/Wework ─→ [Webhook] ─→ App channels/<adapter>/
                                                        │
                                                    解析消息
                                                    验证签名
                                                    归一化格式
                                                        │
                                               services/client.py
                                                  HTTP POST
                                                        │
                                                        ▼
                                                   Platform API
                                                        │
                                                    身份解析
                                                    鉴权检查
                                                    限流
                                                        │
                                                   CoreFacade
                                                        │
                                                   Core AI Pipeline
                                                        │
                                                   CoreFacade (response)
                                                        │
                                                   Platform API
                                                        │
                                                  HTTP Response
                                                        │
                                                        ▼
                                               App services/formatter.py
                                                        │
                                                    适配渠道格式
                                                    (Telegram卡片 /
                                                     Slack Block Kit /
                                                     Markdown)
                                                        │
                                                        ▼
                                              App → External User
```

### P6. 唯一允许的跨层调用：`services/client.py`

```
aiPlat-app/services/client.py
  ├─ class PlatformClient:
  │   ├─ chat(tenant_id, message) → str          POST /api/v1/chat
  │   ├─ search_kb(tenant_id, query) → List       GET  /api/v1/kb/search
  │   ├─ get_identity(token) → Identity           GET  /api/v1/identity
  │   └─ ...其他 Platform REST API 的封装...
  │
  └─ 禁止在此模块中：
      ❌ 实现业务逻辑
      ❌ 实现 AI 推理
      ❌ 实现数据持久化
      ✅ 只做 HTTP 请求/响应序列化
```

### P7. 完整性自检清单

每次 App 新增功能时，自检以下 5 问：

1. 如果不通过 HTTP 调用 Platform，这个功能能独立运行吗？→ 能 = 可能正确
2. 这项功能是否已经被 Platform 的 REST API 覆盖？→ 是 = 应走 HTTP，不重复实现
3. 这项功能是否需要访问 Core 的模型推理？→ 是 = 必须经过 Platform → CoreFacade
4. 这项功能是否特定于某个消息渠道（Telegram/Slack）？→ 是 = 应在 App channels/
5. 这项功能是否需要管理数据存储或用户鉴权？→ 是 = 应在 Platform

---

## 4. 反模式：常见违规对照

### 4.1 Core ↔ Platform

| ❌ 违规 | ✅ 正确 | 违反规则 |
|--------|--------|---------|
| Platform 的 `embeddings.py` 自己缓存并调用 `hash_embed` | 缓存层由 `core/harness/knowledge/embedder.py` 统一提供；Platform 直接 `from core import embed_text` | 铁律 1 |
| Platform 的 `doc_parser.py` 实现 `parse_docx` | Core `harness/document/parsers.py` 实现；Platform 调 Core | 铁律 2 |
| Platform 的 `video.py` 直接 `import faster_whisper` | Core `harness/document/transcriber.py` 加载模型；Platform 调 Core pipeline | 铁律 1 |
| Platform 的 `classifier.py` 实现分类逻辑 | Core `apps/document_intelligence/classifier.py` 实现（Internal Policy） | 决策树 |
| Platform 的 `query.py::query_elements` 实现检索算法（余弦相似度、关键词评分） | Core `harness/knowledge/retriever.py` 实现检索算法；Platform 只编排（if/elif 选择模式） | 铁律 2 |
| Core 缺少 `harness/document/` 目录 | 应包含 parsers/chunker/video/transcriber/ocr | 完整性 |
| `core/apps/` 与 `aiPlat-app/` 命名冲突 | 建议重命名为 `core/policy/` 或 `core/intelligence/` | 一致性 |
| Platform 的 `KBSqlite` 直接 `import sqlite3` | 通过 Core 的 `infra_bridge` 获取 `DatabasePort` 实例；不直接导入底层驱动 | Infra Bridge |
| Provider 回调签名使用 `Any` 类型 | 在 Core 中定义 `Protocol`（如 `KBIngestCallback`），Platform 实现该 Protocol | Provider 回调 |

### 4.2 Platform ↔ App

| ❌ 违规 | ✅ 正确 | 违反规则 |
|--------|--------|---------|
| App 的 `channels/telegram/adapter.py` 直接 `import jwt` 解析 token | App 调用 `GET /api/v1/identity`，由 Platform 返回身份信息 | 铁律 P-1 |
| App 的 `services/chat.py` 直接 `from aiPlat_core.harness import PipelineEngine` | App 调用 POST /api/v1/chat → Platform → CoreFacade → Core | 铁律 P-2 |
| App 散落在各 channel 中各自实现 HTTP 调用 Platform | 统一通过 `services/client.py` 封装，其他模块只调 client | P6 唯一接触点 |
| App 中实现 KB 搜索逻辑（embedding、rerank、余弦相似度） | 走 Platform REST API：GET /api/v1/kb/search | 铁律 P-2 |
| App 中实现 Builder 项目创建/管理逻辑 | 走 Platform REST API：POST /api/v1/builder/projects | 决策树 |
| Platform 的 `api/` 中包含渠道适配逻辑（Telegram XML → 统一格式） | 渠道适配在 App channels/ 中完成；Platform 只接受归一化格式 | 决策树 |
| App 直接 `import sqlite3` 做消息历史持久化 | 消息历史通过 Platform API 存入 KB 或 session store | Infra Bridge |

---

## 5. 自动化验证标准

### 5.1 architecture_guard.sh 应新增的检查项

```
§10: Platform 不直接 import AI 模型库
     grep -rn "import faster_whisper\|import whisper\b\|import pytesseract\
                \|import paddleocr\|import sentence_transformers" aiPlat-platform/
     → 命中 = 违规（铁律 1）

§11: 文档解析/嵌入/分类逻辑不在 Platform 的 intelligence/ 子目录
     grep -rn "def parse_docx\|def parse_pptx\|def parse_markdown\
                \|def hash_embed\|def classify_document" aiPlat-platform/kb/intelligence/
     → 命中 = 违规（铁律 2 + 决策树）

§12: Platform 的检索逻辑只做编排，不做算法实现
     grep -rn "def cosine_similarity\|def _score_text\|def _dedupe\
                \|def retrieve\b" aiPlat-platform/kb/intelligence/query.py
     → 命中 = 违规（铁律 2）
```

### 5.2 constitution tests 应新增的语义检查

```
test_platform_no_model_imports.py:
  - 检查 aiPlat-platform/ 下无直接 import 模型库

test_core_document_parsing.py:
  - 检查 core/harness/document/ 目录存在且包含 parsers/chunker

test_core_embedding_unified.py:
  - 检查 Platform 通过 core 获取 embed 能力，不自建缓存

test_platform_retrieval_orchestrate_only.py:
  - 检查 Platform query.py 只做路由编排，不实现检索算法
```

### 5.3 architecture_guard.sh: Platform ↔ App 边界检查

```
§13: App 不直接 import Core/Platform/Infra 模块
     grep -rn "import aiPlat_core\b\|from aiPlat_core\b" aiPlat-app/
     grep -rn "import aiPlat_platform\b\|from aiPlat_platform\b" aiPlat-app/
     grep -rn "import aiPlat_infra\b\|from aiPlat_infra\b" aiPlat-app/
     → 命中 = 违规（铁律 P-2 / Infra Bridge）

§14: App 不直接 import 身份解析库
     grep -rn "import jwt\b\|import pyjwt\b\|from jose\b" aiPlat-app/
     → 命中 = 违规（铁律 P-1）

§15: App 对 Platform 的 HTTP 调用只在 services/client.py 中
     grep -rn "requests\.\(get\|post\|put\|delete\)\b\|httpx\.\(get\|post\|put\|delete\)\b" aiPlat-app/ --include="*.py" | grep -v "services/client.py"
     → 命中 = 违规（P6 唯一接触点）

§16: Platform 不包含渠道适配逻辑
     grep -rn "def.*telegram\|def.*slack\|def.*wework\|TelegramBot\|SlackClient" aiPlat-platform/
     → 命中 = 违规（决策树）
```

### 5.4 constitution tests: Platform ↔ App 边界检查

```
test_app_no_direct_core_import.py:
  - 检查 aiPlat-app/ 下无 import aiPlat_core 或 import aiPlat_platform

test_app_http_only_to_platform.py:
  - 检查 aiPlat-app/ 除 services/client.py 外无直接 HTTP 调用到 localhost:8003

test_app_no_auth_reimplementation.py:
  - 检查 aiPlat-app/ 下无 JWT/API Key 解析实现

test_platform_no_channel_adapters.py:
  - 检查 aiPlat-platform/ 下无 Telegram/Slack/Wework 特定适配代码
```

### 5.5 Provider 回调模式 — 签名定义规范

Core 通过 Provider 回调模式解耦与 Platform 的反向依赖。回调 **签名必须在 Core 中定义为 Protocol**，而非使用 `Any` 类型。

```
正确模式:
  Core 中定义:
    # core/harness/knowledge/callbacks.py
    from typing import Protocol

    class KBIngestCallback(Protocol):
        def __call__(self, *, tenant_id: str, collection_id: str,
                     file_path: str, kind: str, ...) -> Dict[str, Any]: ...

    class KBQueryCallback(Protocol):
        def __call__(self, *, tenant_id: str, collection_id: str,
                     question: str, year: int = ..., limit: int = ...) -> Dict[str, Any]: ...

  Core 中声明变量:
    _ingest_fn: Optional[KBIngestCallback] = None
    _query_fn: Optional[KBQueryCallback] = None

  Platform 中注册:
    set_knowledge_ingest_fn(ingest_document)  ← ingest_document 符合 KBIngestCallback 签名

规则:
  ✅ 回调签名使用 Protocol 定义在 Core 中，提供类型安全
  ❌ _ingest_fn: Any = None （Core 不知道回调的输入输出是什么）
```

**当前状态**：`core/apps/document_intelligence/kb_provider.py` 使用 `Any` 类型。需改造为 Protocol。

**设计原理**：Core 定义"我需要 Platform 提供什么签名的函数"，Platform 提供符合签名的实现——这是依赖倒置的另一种形式。和 Infra Bridge 的区别：Bridge 用于 Core→Infra 方向（端口固定），Provider 回调用于 Platform→Core 反向注入（签名可变，但应在 Core 中定义）。

---

## 6. 与现有设计文档的关系

| 文档 | 关系 |
|------|------|
| `docs/architecture/system-architecture-contract.md` | 父文档：定义四层职责与依赖方向 |
| `aiPlat-core/docs/contracts/01-architecture-contract.md` | 子文档：Core 内部 Harness/Policy/Agent/Skill 边界 |
| `docs/index.md` §设计原则 | 引用本标准的决策树和铁律 |
| `CLAUDE.md` §5.29（内核无关应用原则） | 铁律 1 和铁律 2 是 §5.29 的具体化 |

**冲突解决优先级**：本标准 > 各层 CLAUDE.md > 各层 docs/index.md > 代码注释
