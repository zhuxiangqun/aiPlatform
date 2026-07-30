# 模型管理系统

> **版本**：v2.2.2 ｜ **最后更新**：2026-07-25 ｜ **状态**：生产就绪

## 目录

- [概述](#概述)
- [架构](#架构)
- [模型来源](#模型来源)
- [数据模型](#数据模型)
- [API 端点](#api-端点)
- [配置文件](#配置文件)
- [管理后台](#管理后台)
- [状态流转](#状态流转)
- [LLM 模型自动选择算法](#llm-模型自动选择算法-v222)
- [错误处理](#错误处理)
- [使用示例](#使用示例)

---

## 概述

模型管理系统是 aiPlat 基础设施层的核心组件，负责 AI 平台中所有 LLM 模型的全生命周期管理：

1. **模型注册**：从适配器表、配置文件、环境变量和 Ollama 自动扫描四种来源发现并注册模型
2. **模型配置**：启用/禁用、API key 管理、连通性测试
3. **自动选择**：根据任务用途（purpose）、硬件资源、模型能力和历史质量数据，自动选出最优模型
4. **评分权重管理**：通过管理 UI 或 API 动态调整各评分维度的权重（支持场景自适应）

---

## 架构

```
┌──────────────────────────────────────────────────────────────────┐
│                  管理后台 (React + Tailwind CSS)                    │
│  ┌─────────────────────┐  ┌──────────────────────────────────┐   │
│  │   模型列表 / 配置    │  │   评分权重矩阵 (v2.2 新增)        │   │
│  └─────────────────────┘  └──────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────┤
│                   aiPlat-platform (8000)                           │
│                       路由层 + API 网关                             │
│   /api/infra/models → 转发到 infra     /api/core/models/profile   │
├──────────────────────────────────────────────────────────────────┤
│                   aiPlat-infra → ModelManager                      │
│  ┌──────────────┐  ┌───────────────┐  ┌────────────────────┐     │
│  │ ConfigLoader │  │ OllamaScanner │  │ unified_pipeline() │     │
│  │ (YAML+DB)    │  │ (GET /api/tags)│  │ (自动选择引擎)     │     │
│  └──────────────┘  └───────────────┘  └────────────────────┘     │
│  ┌──────────────┐  ┌───────────────┐  ┌────────────────────┐     │
│  │AddressStorage│  │HealthChecker  │  │ _score_model()     │     │
│  │ (models.json)│  │ (连通性测试)   │  │ (12维评分)         │     │
│  └──────────────┘  └───────────────┘  └────────────────────┘     │
└──────────────────────────────────────────────────────────────────┘
```

---

## 模型来源

| 来源 | 标签 | 可编辑 | 可删除 | 存储位置 | 说明 |
|------|------|:---:|:---:|------|------|
| **适配器表 (UI 手动添加)** | 外部 | ✅ | ✅ | SQLite `adapters` 表 | 管理 UI 添加的 API 模型和自部署模型 |
| **适配器表 (本地扫描同步)** | 本地 | ✅ | ✅ | SQLite `adapters` 表 | Ollama/LM Studio/vLLM 等自动扫描后同步 |
| **系统能力** | 内置 | ❌ | ❌ | 代码动态检测 | OCR / embedder / doc-parser（非 LLM） |

加载顺序：适配器表 → 系统能力 → YAML 配置。所有 LLM 模型统一通过适配器表管理。

加载顺序：适配器表 → 环境变量 → 用户添加（跳过同名）→ Ollama 扫描。

---

## 数据模型

### ModelInfo (infra/management/schemas.py)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 唯一标识，格式如 `adapter:xxx:model-name` 或 `ollama:model-name` |
| `name` | `str` | 模型名称，如 `qwen2.5-coder:7b`、`deepseek-chat` |
| `display_name` | `str` | 管理 UI 显示名称，默认等于 `name` |
| `type` | `ModelType` | CHAT / EMBEDDING / IMAGE / AUDIO |
| `provider` | `str` | openai / deepseek / anthropic / ollama / openrouter |
| `source` | `ModelSource` | LOCAL / EXTERNAL / CONFIG |
| `enabled` | `bool` | 是否启用（禁用后不参与任何选择） |
| `status` | `ModelStatus` | AVAILABLE / UNAVAILABLE / ERROR / NOT_CONFIGURED |
| `config` | `ModelConfig` | 配置参数（温度、max_tokens、base_url 等） |
| `stats` | `ModelStats` | 运行时统计（请求总数、成功率、延迟等） |
| `capabilities` | `List[str]` | 能力标签：chat / reasoning / function_call / json_mode / code |
| `tags` | `List[str]` | 分类标签：openai / local / qwen2 等 |
| `size` | `int?` | 模型文件大小（bytes）。Ollama 扫描自动填充，API 模型为 0 |
| `quantization` | `str?` | 量化方式：Q4_K_M / Q8_0 / F16 / None（v2.1 新增） |
| `is_downloaded` | `bool` | 是否已下载到本地（v2.1 新增） |
| `supports_gpu` | `bool` | 是否支持当前平台 GPU 加速（v2.1 新增） |
| `created_at` | `datetime` | 注册时间 |
| `updated_at` | `datetime` | 最后更新时间 |

### ModelConfig

| 字段 | 类型 | 默认值 | 说明 |
|------|------|:---:|------|
| `temperature` | `float` | 0.7 | 采样温度 |
| `max_tokens` | `int` | 2048 | 最大输出 token 数 |
| `top_p` | `float` | 1.0 | 核采样参数 |
| `api_key_env` | `str?` | None | API Key 环境变量名（如 `DEEPSEEK_API_KEY`） |
| `adapter_id` | `str?` | None | 适配器 ID（管理 UI 配置时使用，指向 SQLite 中的凭据） |
| `base_url` | `str?` | None | 自定义 API 端点 |
| `headers` | `Dict?` | None | 自定义 HTTP 请求头 |

---

## API 端点

### 模型管理 (infra 层)

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/infra/models` | 模型列表（支持 source/type/enabled/status 筛选） |
| `GET` | `/api/infra/models/{id}` | 模型详情 |
| `POST` | `/api/infra/models` | 添加模型 |
| `PUT` | `/api/infra/models/{id}` | 更新模型配置 |
| `DELETE` | `/api/infra/models/{id}` | 删除模型 |
| `POST` | `/api/infra/models/{id}/enable` | 启用模型 |
| `POST` | `/api/infra/models/{id}/disable` | 禁用模型 |
| `POST` | `/api/infra/models/{id}/test/connectivity` | 连通性测试 |
| `POST` | `/api/infra/models/{id}/test/response` | 响应测试 |
| `GET` | `/api/infra/models/local` | 扫描本地 Ollama 模型 |
| `GET` | `/api/infra/models/providers` | 获取 Provider 列表 |

### 评分权重管理 (core 层, v2.2 新增)

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/core/models/profile` | 读取当前生效的评分配置（合并系统+工作区 YAML） |
| `PUT` | `/api/core/models/profile` | 更新工作区 `config/infra/llm_profile.yaml` 中的权重配置 |

**GET 响应示例**：
```json
{
  "purpose_profiles": {
    "chat": {
      "prefer": ["chat"],
      "prefer_local": true,
      "scoring_weights": { "reasoning": 0.3, "latency": -2.5, "source_bias": 1.5 }
    }
  },
  "default_scoring_weights": {
    "source_bias": 1.0, "resource_pressure": 1.0, "gpu_compat": 1.0,
    "reasoning": 1.0, "quality": 1.0, "latency": -1.0,
    "concurrency": 1.0, "cost": -1.0, "api_credential": 3.0
  },
  "fallback": {
    "safe_model": "qwen2.5:3b",
    "safe_model_alt": "deepseek-chat",
    "safe_model_ram_limit": 4
  }
}
```

---

## 配置文件

### config/infra/llm_profile.yaml (v2.2)

系统评分权重和模型能力配置。工作区同名文件 (`config/infra/llm_profile.yaml`) 层叠覆盖系统配置。

```yaml
# 保底配置
fallback:
  safe_model: qwen2.5:3b           # ~1.9GB，离线也能跑
  safe_model_alt: deepseek-chat     # API 模型，size=0 永过硬过滤
  safe_model_ram_limit: 4           # 可用 RAM < 4GB 时跳过本地 safe_model

# 默认评分权重（purpose 未定义时回退）
default_scoring_weights:
  source_bias: 1.0
  resource_pressure: 1.0
  gpu_compat: 1.0
  reasoning: 1.0
  quality: 1.0
  latency: -1.0
  concurrency: 1.0
  cost: -1.0
  api_credential: 3.0

# 任务用途配置
purpose_profiles:
  chat:                                 # 实时对话：速度优先
    prefer: ["chat"]
    prefer_local: true
    scoring_weights: { reasoning: 0.3, latency: -2.5, source_bias: 1.5 }

  code_gen:                             # 代码生成：强推理优先
    prefer: ["chat", "code"]
    prefer_local: true
    scoring_weights: { reasoning: 2.5, latency: -0.5, source_bias: 1.5 }

  reasoning:                            # 复杂推理：极致质量
    prefer: ["chat", "reasoning"]
    prefer_external: true
    scoring_weights: { reasoning: 3.5, quality: 1.8, resource_pressure: 0.3, cost: -0.3 }

  clarify:                              # 澄清追问：极速响应
    prefer: ["chat"]
    prefer_local: true
    scoring_weights: { reasoning: 0.1, latency: -3.0, quality: 0.5 }

  skill_execution:                      # 技能执行：防 OOM 优先
    prefer: ["chat"]
    prefer_external: true
    scoring_weights: { resource_pressure: 1.5, reasoning: 1.2 }

# 模型能力元数据（用于 scoring 推理加分和 T1-T5 路由）
model_capabilities:
  qwen2.5:3b:           { reasoning_quality: 1, context_window: 32768 }
  qwen2.5-coder:7b:     { reasoning_quality: 3, context_window: 32768 }
  qwen2.5-coder:14b:    { reasoning_quality: 3, context_window: 32768 }
  qwen2.5-coder:32b:    { reasoning_quality: 4, context_window: 32768 }
  deepseek-chat:        { reasoning_quality: 5, context_window: 131072 }
  deepseek-v4-pro:      { reasoning_quality: 5, context_window: 131072 }
```

---

## 管理后台

### 模型管理页面

路径：`管理端 → 基础设施 → 模型管理`

| Tab | 功能 |
|-----|------|
| **模型列表** | 模型表格（名称/类型/来源/Provider/状态/启用开关）、筛选、搜索、添加/编辑/删除/测试连通性、扫描本地模型 |
| **评分权重** (v2.2 新增) | 可编辑的权重矩阵（行=purpose，列=评分维度）、保存到工作区 YAML、重置为默认值 |

### 评分权重矩阵

权重矩阵支持实时编辑，修改后点击「保存」写入 `config/infra/llm_profile.yaml`，下次模型选择立即生效（无需重启）。

权重语义：
- **正数权重**：放大对应维度的效果（积分更多或扣分更多）
- **负数权重**：反向放大（如 `latency=-2.0` 表示延迟惩罚加倍）
- **env var/override 匹配**：`+500`/`+80` 不参与权重，始终保持绝对/强势优先

---

## 状态流转

```
┌─────────────┐    测试通过    ┌──────────┐    启用    ┌─────────┐
│  未配置     │ ───────────→ │  已配置   │ ────────→ │  已启用 │
└─────────────┘              └──────────┘           └─────────┘
                                   │                      │
                              测试失败                禁用/下线
                                   ↓                      ↓
                              ┌──────────┐           ┌─────────┐
                              │  不可用   │ ←──────── │  已禁用 │
                              └──────────┘           └─────────┘
```

---

## LLM 模型自动选择算法 (v2.2.2)

### 入口

`best_model_for_purpose(purpose)` → `ModelManager.unified_pipeline()`

**输入**：任务用途（`chat` / `code_gen` / `reasoning` / `skill_execution` / `clarify` / `agent_creation` / `ontology_gen`）

**输出**：模型名称 (`str`)

### 设计原则

1. **统一评分管道**：所有路径收敛到同一个评分引擎，无 env var / model_overrides / fallback 硬覆盖旁路
2. **硬约束永不放宽**：RAM / VRAM / disk 是物理上限，任何降级都不能绕开
3. **软约束逐级放宽**：能力匹配 → 健康检查 → 延迟阈值，四级递进
4. **始终有模型可用**：safe_model + safe_model_alt 双保险，API 模型 size=0 永远通过硬过滤

### 流程

```
best_model_for_purpose(purpose)
  │
  ├── Step 0: session override (/model 命令) → 如果有则直接返回
  │
  ├── Step 1: _build_preferences() — 收集 env var 偏好（不再硬覆盖）
  │        └── size=None 的本地模型拒绝授予 +500，记录 Warning
  │
  ├── Step 2: _load_llm_profile() — 加载合并后的 YAML 配置
  │
  └── Step 3: unified_pipeline()
       │
       ├── Stage 1: 资源采集 (5s TTL)
       │        collect_platform_resources() → RAM/VRAM/GPU/CPU/Disk
       │
       ├── Stage 2: 硬过滤 (物理约束，永不降级)
       │        disabled / size > RAM / size > VRAM / size > disk(未下载)
       │
       ├── Stage 3: 软过滤 (4 级降级)
       │        L0: 能力+健康+延迟 → L1: 健康+延迟 → L2: 仅延迟 → L3: 全放
       │
       ├── Stage 4: 多维评分 (12 维 × 动态权重)
       │        _score_model(): 资源/来源/推理/GPU/凭证/质量/延迟/并发/成本
       │
       └── Stage 5: Safe Model 保底
                API 安全模型 → 本地安全模型 → RuntimeError
```

### Stage 1: 资源采集

`PlatformResources` 结构体，带 **5 秒 TTL 缓存**：

| 字段 | Apple Silicon | NVIDIA GPU | CPU-only |
|------|:---:|:---:|:---:|
| `ram_bytes` | `psutil.virtual_memory().available` | 同 | 同 |
| `vram_bytes` | **= ram_bytes** (统一内存) | `pynvml` 可用显存 | 0 |
| `gpu_vendor` | `"apple"` | `"nvidia"` | `None` |
| `gpu_compatible` | `True` | `True` | `False` |

### Stage 2: 硬过滤

6 项检查，任意不通过即淘汰，永不降级：

| 检查项 | 条件 | 结果 |
|--------|------|------|
| enabled | `model.enabled == False` | 淘汰 |
| size 未知 | `model.size is None` | 放行（评分阶段扣 -150） |
| API 模型 | `model.size == 0` | 放行 |
| 内存不足 | `model.size > ram_bytes` | 淘汰 |
| 显存不足 | `vram_bytes > 0` 且 `model.size > vram_bytes` | 淘汰 |
| 磁盘不足 | `not is_downloaded` 且 `model.size > disk_free` | 淘汰 |

### Stage 3: 软过滤 (四级降级)

| 级别 | 过滤组合 | 放宽内容 |
|:---:|------|------|
| L0 (full) | 能力 + 健康 + 延迟 | — |
| L1 (-cap) | 健康 + 延迟 | 放宽能力匹配 |
| L2 (-cap-hlt) | 仅延迟 | 放宽能力 + 健康 |
| L3 (none) | 全部通过 | 仅保留硬过滤 |

- `_filter_capability`: 能力是否匹配 `purpose_profiles.{p}.prefer/require/avoid`
- `_filter_health`: 近期故障率 ≤ 50%（无数据默认通过）
- `_filter_latency`: P95 延迟 ≤ 30s（无数据默认通过）

### Stage 4: 多维评分

12 维评分，每维乘以 `scoring_weights` 中的动态权重：

| # | 维度 | 基础分范围 | 权重键 | 说明 |
|:--|------|:---:|------|------|
| 0 | 未知 size 惩罚 | -150 | — (不参与权重) | size=None 的本地模型 |
| 1 | 资源压力 | -100 / -30 / -10 | `resource_pressure` | ratio = model.size / free_ram |
| 2 | 来源偏好 | +120 / +60 / +40 | `source_bias` | local > external > config |
| 3 | env var 匹配 | +500 | — (不参与权重) | `AIPLAT_{PURPOSE}_MODEL` 命中 |
| 4 | override 匹配 | +80 | — (不参与权重) | `model_overrides` 命中 |
| 5 | GPU 兼容 | +50 / -200 | `gpu_compat` | 有 GPU+50，本地无 GPU-200 |
| 6 | 推理能力 | +80 / +40 / +20 | `reasoning` | 从 `model_capabilities.reasoning_quality` 读 |
| 7 | API 凭证 | -300 | `api_credential` | 双路径：`api_key_env` OR `adapter_id` |
| 8 | 质量反馈 | -80 ~ +80 | `quality` | QualityValidator 运行时反馈 |
| 9 | 延迟惩罚 | -40 / -20 | `latency` | P95 > 10s / 5s |
| 10 | 并发容量 | +30 / +15 | `concurrency` | max_concurrency ≥ 50 / ≥ 10 |
| 11 | 成本 | -10 / -5 | `cost` | per-1k > $0.01 / $0.001 |

### Stage 5: Safe Model 保底

```
候选池为空
  → 尝试 safe_model_alt (API 模型, size=0)
  → 尝试 safe_model (本地小模型，检查 safe_model_ram_limit)
  → 都不可用 → RuntimeError (报告完整硬件状态)
```

### 配置示例

```yaml
fallback:
  safe_model: qwen2.5:3b        # 1.9GB
  safe_model_alt: deepseek-chat # API 模型
  safe_model_ram_limit: 4      # RAM < 4GB 时跳过本地 safe_model
```

### 实际选择结果 (6.7GB RAM, Apple Silicon, 无 env var 偏好)

| purpose | 选中模型 | 推理 quality | 关键权重 |
|---------|------|:---:|------|
| chat | qwen2.5:3b (1.9GB) | 1 | latency=-2.5 |
| clarify | qwen2.5:3b (1.9GB) | 1 | latency=-3.0 |
| agent_creation | qwen2.5-coder:7b (4.7GB) | 3 | source_bias=1.5 |
| ontology_gen | qwen2.5-coder:7b (4.7GB) | 3 | source_bias=1.5 |
| code_gen | deepseek-chat (API) | 5 | reasoning=2.5 |
| reasoning | deepseek-chat (API) | 5 | reasoning=3.5 + quality=1.8 |
| skill_execution | deepseek-chat (API) | 5 | resource_pressure=1.5 |

### 纵深防御 (防止 32B 越界)

| 防线 | 机制 | 效果 |
|:---:|------|------|
| 1 | `_build_preferences()` — env var 预检 | 32B > 可用 RAM → 拒绝 +500，记录 Warning |
| 2 | `_hard_filter()` — 物理约束 | 32B (19.9GB) > 6.7GB → 硬淘汰 |
| 3 | `_score_model()` — 评分惩罚 | size=None → -150；API 无凭证 → -900 |

### 代码位置

| 组件 | 文件 |
|------|------|
| 入口 | `core/harness/utils/model_injection.py:1595` |
| 统一管道 | `infra/management/model/manager.py:760` |
| 硬过滤 | `infra/management/model/manager.py:154` |
| 软过滤 | `infra/management/model/manager.py:179-207` |
| 多维评分 | `infra/management/model/manager.py:210` |
| 权重加载 | `infra/management/model/manager.py:188` |
| size 补全 | `infra/management/model/manager.py:361` |
| 资源采集 | `infra/management/model/manager.py:77` |
| 配置加载 | `core/harness/utils/model_injection.py:1527` |
| 偏好收集 | `core/harness/utils/model_injection.py:1559` |

---

## 错误处理

| 错误 | 原因 | 处理 |
|------|------|------|
| 模型未找到 | ID 不存在 | 返回 404 |
| 配置模型不可修改 | 内置模型只读 | 返回 403 |
| Ollama 连接失败 | 本地未运行 | 标记为 unavailable |
| API Key 无效 | 环境变量未设置或过期 | 标记为 not_configured |
| 无可用模型 | 所有候选被硬过滤 + 安全模型也不可用 | RuntimeError |
| size 不明 | Ollama 未启动或匹配失败 | 放行但评分 -150 |

---

## 使用示例

### 查询所有模型

```bash
curl http://localhost:8000/api/infra/models
```

### 添加自定义模型

```bash
curl -X POST http://localhost:8000/api/infra/models \
  -H "Content-Type: application/json" \
  -d '{"name":"my-model","displayName":"My Model","type":"chat","provider":"custom","config":{"baseUrl":"http://localhost:11434/v1"}}'
```

### 扫描本地 Ollama 模型

```bash
curl "http://localhost:8000/api/infra/models/local?endpoint=http://localhost:11434"
```

### 读取评分配置

```bash
curl http://localhost:8000/api/core/models/profile
```

### 更新评分权重

```bash
curl -X PUT http://localhost:8000/api/core/models/profile \
  -H "Content-Type: application/json" \
  -d '{"purpose_profiles":{"chat":{"prefer":["chat"],"prefer_local":true,"scoring_weights":{"latency":-3.0,"reasoning":0.2}}}}'
```

### 测试模型连通性

```bash
curl -X POST http://localhost:8000/api/infra/models/openai:gpt-4/test/connectivity
```

---

*最后更新：2026-07-25 (v2.2.2)*
