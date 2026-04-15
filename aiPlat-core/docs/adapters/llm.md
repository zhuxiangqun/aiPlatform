# 适配器层 (Adapters)

> 提供外部服务的适配能力，包括 LLM 适配器等。

---

## 一句话定义

**适配器层是 Harness 的外部服务集成层**——通过适配器模式，解耦外部服务实现，支持多 LLM 无缝切换。

---

## 核心模块

### LLM 适配器

```
adapters/
└── llm/
    ├── base.py                    # 适配器基类
    ├── openai_adapter.py          # OpenAI 适配器
    ├── anthropic_adapter.py      # Anthropic 适配器
    └── local_adapter.py          # 本地模型适配器
```

### 适配器基类

**适配器基类**

定义 LLM 适配器的标准接口：

- **生成响应**：接收消息列表，返回 LLM 响应内容
- **流式生成**：支持逐 Token 流式输出
- **连接验证**：验证与 LLM 服务的连接状态

**响应对象**：内容文本、模型名称、Token 用量、完成原因

### OpenAI 适配器

**OpenAI 适配器**

适配 OpenAI API：

- 支持 GPT 系列模型
- 支持标准 API 和流式调用
- 支持自定义 base_url（代理或兼容接口）
- 使用 API Key 认证

### Anthropic 适配器

**Anthropic 适配器**

适配 Anthropic API：

- 支持 Claude 系列模型
- 支持标准 API 和流式调用
- 使用 API Key 认证

### 本地模型适配器

**本地模型适配器**

适配本地部署的模型服务：

- 支持 vLLM、Ollama 等推理引擎
- 支持标准 OpenAI 兼容接口
- 通过 base_url 指定服务地址

---

## 使用示例

**使用方式**

通过配置选择适配器类型，统一调用 `generate()` 方法：

- 根据配置实例化对应适配器（OpenAI/Anthropic/Local）
- 调用 `generate()` 方法传入消息列表
- 获取统一格式的响应对象

具体代码示例请参考开发者指南。

---

## 与 Harness 的关系

| 组件 | 关系 |
|------|------|
| **harness/models** | 使用适配器进行模型调用 |
| **harness/infrastructure/langchain** | LangChain 底层调用适配器 |
| **harness/execution** | 执行循环使用模型进行推理 |

---

## 相关文档

- [Harness 索引](./harness/index.md) - Harness 完整定义
- [基础设施文档](./harness/infrastructure.md) - LangChain 集成

---

*最后更新: 2026-04-14*