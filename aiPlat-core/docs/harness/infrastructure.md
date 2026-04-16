# 基础设施 (Infrastructure)（设计真值：以代码事实为准）

> 本文档描述 Harness 的基础设施与集成层。部分内容为 To-Be 规划（如更完整的 LangChain 适配/持久化/生命周期管理），需以代码事实与测试为准。  
> 统一口径参见：[架构实现状态](../ARCHITECTURE_STATUS.md)。

---

## 一句话定义

**基础设施是 Harness 的系统服务层**——提供 LangChain 集成、配置管理、生命周期、钩子扩展等底层支持。

---

## 核心模块

### 1. LangChain 集成

> LangChain 作为 Harness 的基础设施工具链

#### 目录位置

```
harness/infrastructure/
└── langchain/                      # LangChain 集成
    ├── models.py                   # 模型集成
    ├── (无 memory.py)              # 记忆集成当前位于 `core/harness/memory/langchain_adapter.py`
    ├── tools.py                    # 工具集成
    └── prompts.py                  # 提示词集成
```

#### 组件映射

| LangChain 组件 | Harness 实现 | 说明 |
|---------------|-------------|------|
| **ChatOpenAI** | ModelProvider | OpenAI 模型封装 |
| **ChatAnthropic** | ModelProvider | Anthropic 模型封装 |
| **ConversationMemory** | ShortTermMemory | 短期记忆 |
| **VectorStoreRetriever** | KnowledgeRetriever | 知识检索 |
| **Tool** | Tool | 工具接口 |
| **Agent** | Agent | 智能体接口 |

#### LCEL 表达式

aiPlat-core 使用 LCEL（LangChain Expression Language）构建调用链：

**模型调用链**：model → prompt → output_parser

**带记忆的链**：memory → model → prompt → output_parser

**带工具的链**：model → bind_tools(tools) → output_parser

---

### 2. 配置管理

#### 目录位置

```
harness/infrastructure/
└── config/
    └── settings.py                # 配置设置
```

#### 配置项

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| model | str | 默认模型 | gpt-4 |
| temperature | float | 温度参数 | 0.7 |
| max_tokens | int | 最大 token 数 | 4096 |
| timeout | int | 超时时间(秒) | 30 |
| max_retries | int | 最大重试次数 | 3 |

---

### 3. 生命周期管理

#### 目录位置

```
harness/infrastructure/
└── lifecycle/
    └── manager.py                # 生命周期管理器
```

#### 生命周期阶段

| 阶段 | 说明 | 钩子 |
|------|------|------|
| **初始化** | 加载配置、初始化组件 | PreInit, PostInit |
| **启动** | 启动服务、注册组件 | PreStart, PostStart |
| **运行** | 正常运行、监控状态 | PreRun, PostRun |
| **停止** | 优雅关闭、保存状态 | PreStop, PostStop |
| **销毁** | 清理资源、释放连接 | PreDestroy, PostDestroy |

---

### 4. 钩子系统

#### 目录位置

```
harness/infrastructure/
└── hooks/
    └── hook_manager.py           # 钩子管理器
```

#### 钩子类型

| 阶段 | 钩子 | 说明 |
|------|------|------|
| 执行前 | PreLoop | 初始化状态 |
| 推理前 | PreReasoning | 准备思考 |
| 推理后 | PostReasoning | 验证推理 |
| 行动前 | PreAct | 准备工具调用 |
| 行动后 | PostAct | 验证工具结果 |
| 观察前 | PreObserve | 准备观察 |
| 观察后 | PostObserve | 处理观察结果 |
| 执行后 | PostLoop | 清理和保存 |
| 完成前 | Stop | 强制验证 |
| 会话开始 | SessionStart | 状态恢复 |

#### 钩子实现

钩子管理器核心能力：

- **触发钩子**：在指定时机触发注册的钩子回调
- **注册钩子**：向指定钩子点注册自定义钩子函数
- **钩子链**：支持多个钩子按顺序执行

---

### 5. 启动引导

#### 目录位置

```
harness/infrastructure/
└── bootstrap/
    └── __init__.py               # 启动引导
```

#### 引导流程

```
1. 加载配置 (Load Config)
     ↓
2. 初始化基础设施 (Init Infrastructure)
     ↓
3. 注册组件 (Register Components)
     ↓
4. 启动服务 (Start Services)
     ↓
5. 就绪 (Ready)
```

---

### 6. 依赖注入

#### 目录位置

```
harness/infrastructure/
└── di/
    └── __init__.py               # 依赖注入
```

#### 注入方式

依赖注入容器核心能力：

- **注册依赖**：将接口与具体实现绑定
- **解析依赖**：根据接口获取具体实现实例
- **生命周期管理**：支持单例、临时等不同生命周期

---

## 与其他模块的关系

| 模块 | 关系 |
|------|------|
| **execution** | 使用基础设施的 LangChain 集成 |
| **observability** | 使用生命周期管理 |
| **feedback_loops** | 使用钩子系统 |
| **apps** | 使用依赖注入获取服务 |

---

## 证据索引（Evidence Index｜抽样）

- LangChain adapter（记忆）：`core/harness/memory/langchain_adapter.py`
- HookManager（默认 hooks 注册）：`core/harness/infrastructure/hooks/hook_manager.py`
- infra 层 DI（生产级 DI 在 infra）：`aiPlat-infra/infra/di/*`

## 相关文档

- [Harness 索引](./index.md) - Harness 完整定义
- [执行系统](./execution.md) - 执行循环
- [框架基础文档](../framework/index.md) - LangChain/LangGraph 关系

---

*最后更新: 2026-04-14*
