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

## 6) 输出要求
- 改动摘要（改了哪些文件，为什么）
- 验证结果（pytest 是否通过）
- 新增后端/接口时：说明接口契约和配置结构
