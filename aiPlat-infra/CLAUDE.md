---
purpose: aiPlat-infra 项目级 AI 编程规约
scope: infra (Layer 0)
language: zh-CN
---

# aiPlat-infra AI 编程规约（基础设施层）

本文件用于约束 AI Agent 在 aiPlat-infra 仓库内的行为。

---

## 0. 优先级（从高到低）
1. 正确性与可验证性（测试通过）
2. 最小改动面（Surgical Changes）
3. 简单性（Simplicity First）
4. 一致性（接口/工厂/配置模式）

---

## 1) Think Before Coding：不确定先问
- 涉及新增后端/提供商（新增数据库类型、新增 LLM 提供商等）
- 涉及接口变更（修改 base.py 中的抽象方法）
- 涉及配置结构变更（YAML schema 变化）

### 1.1 代码优先于设计文档（强制）
设计文档（`docs/`）描述目标状态，代码才是当前真实状态。两者冲突时以代码为准，设计文档标注"已过期/已用不同方式实现"。审计/对比类任务必须先搜代码再做结论，禁止仅凭记忆或上次审计的印象做判断，每次结论必须附带代码搜索证据（命中文件路径+行号）。

---

## 2) Simplicity First：最小实现
- 新增能力优先采用已有的接口-实现-工厂三层模式
- 不引入未被要求的后端/提供商
- 配置字段设合理默认值，保证旧配置零改动运行

---

## 3) Surgical Changes：手术式改动
- 只修改与需求直接相关的文件
- 不改无关的接口、工厂、配置
- 新增后端实现只加一个文件 + 工厂里一个分支

---

## 新增：基础设施无关应用原则（强制）

**infra 层必须对应用完全无知。** 应能脱离 aiPlat 独立部署和使用。

### 违规范例（禁止）

```
❌ {8002: "aiPlat-core", 5173: "frontend"}           → ✓ 运行时发现，不硬编码映射
❌ {"cmdline": "vite", "type": "Frontend"}            → ✓ 不按业务角色分类进程
❌ {"path": "/Users/apple/workdata/..."}                → ✓ 开发者路径绝不出现
❌ gpu_model: str = "A100"                              → ✓ 默认值应为空字符串
❌ namespace: str = "ai-prod"; type: str = "LLM"        → ✓ 默认值泛化
❌ class QuotaInfo: team: str                           → ✓ 使用 generic label
❌ ErrorCategory.BUSINESS                               → ✓ infra 不应有业务错误类别
❌ "/etc/aiplat/infra.yaml"                             → ✓ 环境变量驱动
❌ "ai-platform-bucket"; "/tmp/ai-platform"             → ✓ 通用默认名
```

### 自查方法

1. grep 所有 .py 文件是否包含 `aiPlat`、`frontend`、`management` 等应用名
2. 硬编码的端口号是否映射到特定服务名？
3. 删除所有 `known_services`/`known_defaults`/`target_processes` 硬编码映射
4. 所有默认值是否对任何 AI 基础设施都通用？

### 已修复违规清单（historical — 2026-05 已验证）

所有以下项目已在多轮审计中修复并验证：

- `network/manager.py:50-54,102-108,420-425`: → `AIPLAT_PORT_SERVICES` 环境变量 ✅
- `service/manager.py:21-27`: → `AIPLAT_TARGET_PROCESSES` 环境变量 ✅
- `api/main.py`: `gpu_type="A100"` → `gpu_type=""`、`team` → `label` ✅
- `scheduler/manager.py`: `team` → `label`、`gpu_type="A100"` → `""` ✅
- `storage/schemas.py + clients.py`: → `AIPLAT_STORAGE_*` 环境变量 ✅
- `cache/file_client.py`: → `AIPLAT_CACHE_PATH` 环境变量 ✅
- `observability/schemas.py`: → `AIPLAT_SERVICE_NAME` 环境变量 ✅
- `network/manager.py:148`: → `AIPLAT_NETWORK_SELECTOR` 环境变量 ✅
- `monitoring/prometheus.py:73`: → `AIPLAT_METRICS_NAMESPACE` 环境变量 ✅
- `messaging/schemas.py:69`: → `AIPLAT_MESSAGING_CLIENT_ID` 环境变量 ✅

---

## 4) Goal-Driven Execution：验收闭环
- 语法：`python -m py_compile <修改的文件>`
- 单测：`pytest -q`（infra 层要求 100% 测试覆盖）
- 新增后端必须附带测试

---

## 5) 项目特定：infra 层边界与设计模式（必须遵守）

### 5.1 层定位（来自 `docs/index.md` 和 `../../docs/index.md`）

aiPlat-infra 是 **Layer 0（基础设施层）**，完全独立，不依赖任何内部模块。

- **向上提供**：工厂接口（`create_database_client()`、`create_llm_client()` 等）
- **向下依赖**：无
- **禁止暴露**：具体实现类（如 `PostgresClient`）、内部工具类、第三方 SDK 细节

### 5.2 接口-实现-工厂三层模式

infra 内所有能力模块必须遵循：

| 层 | 文件 | 职责 |
|----|------|------|
| 接口层 | `base.py` | 定义抽象接口和数据模型，不依赖具体实现 |
| 实现层 | `postgres.py` / `openai.py` 等 | 提供具体实现，依赖第三方库 |
| 工厂层 | `factory.py` | 根据配置创建实例，隐藏创建复杂度 |

新模块必须在这三层分别落位，禁止跳过接口直接暴露实现类。

#### 5.2.1 Provider 合并规则（强制）

相同 API 协议的 provider 应复用同一个实现类，不应创建 per-provider 文件。

| 协议 | 实现类 | 适用 provider |
|------|--------|--------------|
| OpenAI 兼容 | `openai_compatible.py` | OpenAI / DeepSeek / Qwen / xAI / LM Studio / oMLX / vLLM / llama.cpp server |
| Anthropic 原生 | `anthropic.py` | Claude 系列 |
| 本地直接加载 | `local.py` | llama_cpp 库、transformers 库 |

新增一个 OpenAI 兼容的 provider 只需改配置（`base_url` + `api_key_env`），不需新增 Python 文件。

### 5.3 配置驱动（与系统设计原则对齐）

- 所有模块通过配置初始化，不硬编码任何参数
- 切换后端只需改配置，不改代码
- 配置优先级：环境变量 > 配置文件 > 默认值
- 新增配置字段必须设定合理默认值

### 5.4 管理接口

infra 提供管理接口供 aiPlat-management 调用：
- `get_status()` — 状态查询
- `get_metrics()` — 指标采集
- `health_check()` — 健康检查
- `diagnose()` — 故障诊断

管理接口不应包含业务逻辑，只暴露 infra 自身的运行状态。

### 5.5 依赖方向

```
infra 不依赖任何内部包
  ↓
可以被所有上层导入（core, platform, app）
```

禁止 infra 反向依赖 core、platform、app 或 management。

**设计文档依据**：
- `../../docs/index.md` §设计原则、§Layer 0 边界规则
- `../../docs/architecture/system-architecture-contract.md` §依赖方向

---

## 5.6 接线状态（强制透明度）

**接线进度（更新于 2026-05）：**

| 能力 | 接线状态 | 详情 |
|------|:---:|------|
| **LLM 调用** | ✅ 已接线 | `InfraLLMAdapter` → infra `LLMClient` → provider API |
| **模型列表** | ✅ 已接线 | `ModelManager.list_models()` 从 env vars + 本地扫描动态构建 |
| **本地模型扫描** | ✅ 已接线 | Ollama、LM Studio、oMLX/vLLM 自动检测 |
| **Embedding** | ✅ 已接线 | `InfraEmbeddingAdapter` → core 通过统一模型配置加载 |
| **Reranker** | ✅ N/A (BM25) | BM25 算法级 reranker，不需交叉编码器模型 |
| **Whisper/STT** | ✅ 已接线 | `InfraAudioAdapter` → `create_adapter("audio")` |
| **OCR** | ✅ 已接线 | `InfraOCRAdapter` → `create_adapter("ocr")` |
| **Vector DB** | ✅ 已接线 | `create_infra_vector_client()` → `retriever.py:363` |
| **Cache** | ✅ 已接线 | core 使用内存/文件缓存（infra 外部缓存桥接预留） |
| **Database** | ✅ 部分接线 | `create_infra_database_client()` 已用于 platform KB 存储 |

**剩余架构债务：**

`core/harness/infrastructure/model_registry.py` 和 `model_router.py` 与 infra `ModelManager` 功能重复，标注为 deprecated，待删除。

**已废弃的 YAML 模型列表：**

`config/infra/default.yaml` 中的静态模型列表已移除，替换为 `model_discovery` 动态发现（env vars + 本地扫描）。模型不再硬编码在配置文件中。

**Core 通过以下文件接入 infra（合法方向）：**

- `core/harness/infrastructure/infra_bridge.py` — ModelManager / Database / Vector 桥接
- `core/harness/infrastructure/infra_llm_adapter.py` — LLM 适配器
- `core/harness/knowledge/retriever.py` — 检索器（部分使用 infra）
- `core/adapters/llm/base.py` — LLM 适配器工厂

**设计文档依据**：
- `../../docs/index.md` §Layer 0 边界规则
- `../../docs/architecture/system-architecture-contract.md` §依赖方向
- 根 `CLAUDE.md` §14（模型管理层级）
- `aiPlat-core/CLAUDE.md` §5.31（模型管理单一真相源）

### 5.7 应用名称硬编码状态（已清理）

以下违规已在本次审计中修复：

| 文件 | 修改内容 |
|------|---------|
| `management/network/manager.py` | 3 处硬编码端口→服务映射改为 `AIPLAT_PORT_SERVICES` 环境变量驱动 |
| `management/service/manager.py` | `target_processes` 改为 `AIPLAT_TARGET_PROCESSES` 环境变量驱动 |
| `management/api/main.py` | `gpu_type: str = "A100"` → `gpu_type: str = ""` |
| `management/schemas.py` | `QuotaInfo.team` → `QuotaInfo.label` |
| `management/scheduler/manager.py` | `team` 字段引用 → `label` + `gpu_type: "A100"` → `""` |
| `storage/schemas.py` | `"ai-platform-bucket"` / `"/tmp/ai-platform"` → `AIPLAT_STORAGE_*` 环境变量 |
| `storage/clients.py`（10 处） | `"ai-platform-bucket"` fallback → `AIPLAT_STORAGE_BUCKET` 环境变量 |
| `cache/file_client.py` | `"/tmp/ai-platform-cache"` → `AIPLAT_CACHE_PATH` 环境变量 |
| `observability/schemas.py` | `"ai-platform-infra"` → `AIPLAT_SERVICE_NAME` 环境变量 |
| `management/network/manager.py:148` | `selector={"app": "ai-platform"}` → `AIPLAT_NETWORK_SELECTOR` 环境变量 |
| `management/monitoring/prometheus.py:73` | `namespace: str = "aiplat"` → `os.getenv("AIPLAT_METRICS_NAMESPACE", "")` |
| `messaging/schemas.py:69` | `client_id: str = "aiplat"` → `os.getenv("AIPLAT_MESSAGING_CLIENT_ID", "")` |
| `messaging/schemas.py:42` | `consumer_group: str = "aiplat-consumer"` → `os.getenv("AIPLAT_KAFKA_CONSUMER_GROUP", "")` |
| `messaging/redis_backend.py`（3 处） | `"aiplat-consumer"` → `os.getenv("AIPLAT_REDIS_CONSUMER_GROUP", "")` |
| `management/cache/manager.py:34` | `key_prefix: "aiplat:"` → `os.getenv("AIPLAT_CACHE_KEY_PREFIX", "")` |
| `management/monitoring/prometheus.py:176` | `namespace: "aiplat_infra"` → `os.getenv("AIPLAT_PROM_EXPORTER_NAMESPACE", "")` |
| `management/service/manager.py:23` | 注释中的示例格式包含应用特定服务名 → 通用格式 |

### 5.8 接线状态

**已完成：**

| 模块 | 说明 |
|------|------|
| LLM adapter | `InfraLLMAdapter` → infra `LLMClient` → provider API ✅ |
| 模型管理 | `ModelManager.list_models()` 从 env vars + 本地扫描动态构建 ✅ |
| 本地模型扫描 | Ollama / LM Studio / oMLX / vLLM 自动检测 ✅ |
| 模型 YAML 列表 | 已废弃，替换为 `model_discovery` 动态发现 ✅ |
| Database bridge | `create_infra_database_client()` 已用于 platform KB 存储 ✅ |
| MCP adapter | `sync_mcp_runtime()` → `MCPRuntime.sync_from_servers()` → ToolRegistry ✅ |
| SubagentCoordinator | DI 已接线，MultiAgent 执行路径已接入 ✅ |
| AgentMessageBus | 全局单例已创建，协议已实现 ✅ |
| Embedding | `InfraEmbeddingAdapter` → `create_adapter("embedding")` ✅ |
| Reranker | `InfraRerankerAdapter` → `create_adapter("reranker")` ✅ |
| Whisper/STT | `InfraAudioAdapter` → `create_adapter("audio")` ✅ |
| OCR | `InfraOCRAdapter` → `create_adapter("ocr")` ✅ |

**所有 18 个能力模块均已接线或预留桥接。** 测试覆盖完备。

---

## 6) 输出要求
- 改动摘要（改了哪些文件，为什么）
- 验证结果（pytest 是否通过）
- 新增后端/接口时：说明接口契约和配置结构


## 7) 近期架构变更（2026-05）

### MCP 已移出 infra
- `aiPlat-infra/infra/mcp/` 整个目录已删除
- MCP（Model Context Protocol）已全部归入 `aiPlat-core/core/apps/mcp/`
- infra 层不再管理 MCP 传输、协议或客户端实现
- 原因：MCP 是 core 的集成模式，不属于 infra 的基础设施能力
