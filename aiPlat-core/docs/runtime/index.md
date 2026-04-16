# Runtime（Core Layer 1）

> 本文档为**入口索引**：用于统一“Runtime = 核心执行引擎”的归属与导航，避免与 app 层“接入运行时”混淆。

## 1. 定位

在 AI Platform 四层架构中：

- **Runtime（核心执行引擎）**属于 **aiPlat-core（Layer 1）**
- 其核心目标是提供可控、可观测、可扩展的执行闭环（Harness + 编排 + Agent/Skill/Tool）

> app 层（Layer 3）只负责用户接入与会话编排（消息网关 / CLI / Web UI），不承载执行引擎实现。  
> 对 app 层接入视角，请见：[aiPlat-app 运行时接入模块](../../../aiPlat-app/docs/runtime/index.md)

## 2. 相关核心文档（推荐阅读顺序）

1. **Harness（执行引擎的核心约束与闭环）**
   - [Harness 索引](../harness/index.md)
   - [执行机制](../harness/execution.md)
   - [可观测性](../harness/observability.md)

2. **Agents（Agent 体系与架构）**
   - [Agents 索引](../agents/index.md)
   - [Agents 架构](../agents/architecture.md)

3. **Skills / Tools / Memory / Knowledge**
   - [Skills 索引](../skills/index.md)
   - [Tools 索引](../tools/index.md)
   - [Memory 索引](../memory/index.md)
   - [Knowledge 索引](../knowledge/index.md)

## 3. 术语约定

- **Core Runtime**：指 aiPlat-core 的执行引擎（Harness/编排/Agent/Skill/Tool）
- **App Runtime（接入层）**：指 aiPlat-app 的会话编排、协议适配、调用 platform API 的工程能力

