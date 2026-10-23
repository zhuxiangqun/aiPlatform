# 架构文档导航

## 核心参考（当前状态）

| 文档 | 说明 |
|------|------|
| [overview.md](overview.md) | 权威架构全景 |
| [boundary-standard.md](boundary-standard.md) | 层边界判定标准 |
| [system-architecture-contract.md](system-architecture-contract.md) | 跨层 API 契约 |
| [execution-decision-matrix.md](execution-decision-matrix.md) | **执行决策矩阵（Living Spec）**：按场景选用程序/LLM/Skill/Agent/流水线；三层架构人话说明；代码证据见文末附录 |
| [execution-quality-gates.md](execution-quality-gates.md) | 执行产物质量门禁 + 结果展示：`output_schema` / `x-display-profile` 驱动统一渲染（非按 Agent 复制 UI；与决策矩阵互补） |
| [capability-profile.md](capability-profile.md) | 能力剖面等级与注入表（决策矩阵层 C） |
| [core/core-layer1-latest.md](core/core-layer1-latest.md) | Core 层最新架构详述 |
| [governance.md](governance.md) | 治理文档 |
| [../knowledge-system.md](../knowledge-system.md) | 知识系统完整指南：向量KB/GraphIndex/Wiki/本体/检索/运维 |
| [slo.md](slo.md) | SLO 定义 |

## 当前交付：Pi Thin Runtime

| 文档 | 说明 |
|------|------|
| [plans/pi-thin-runtime.md](plans/pi-thin-runtime.md) | Pi 产品定位与轴 A/B living 摘要（Thin；≠ 五产品 Enterprise Runtime） |
| [../../packages/aiplat-pi-runtime/README.md](../../packages/aiplat-pi-runtime/README.md) | 包入口、Pi-only 与企业可选回连 |

## ADR 裁决

| 文档 | 说明 |
|------|------|
| [decisions/evaluator_calibration.md](decisions/evaluator_calibration.md) | 评估器校准 |
| [decisions/tot_reserve.md](decisions/tot_reserve.md) | ToT 保留决策 |

## 规划与路线图（非现状）

> 下列文档描述目标边界或执行草案，**不代表**当前仓库已拆成五服务或已交付完整 Enterprise Runtime。现行 Pi 见上方「当前交付」。

| 文档 | 说明 |
|------|------|
| [五产品 Decision Brief](plans/ai-platform-five-products-decision-brief.md) | 评审会摘要：批准范围、非目标、5 项当场决策和 Gate |
| [plans/](plans/) | 其他规划文档（竞品对比、优化路线图、路由迁移等） |
| [五产品目标架构与 ADR 母稿](plans/ai-platform-five-products-target-architecture.md) | aiPlat / Pi / 本体 / FDE / 诊断的产品边界、数据 owner、共享契约与部署拆分原则 |
| [五产品评审与首个纵向切片执行计划](plans/ai-platform-five-products-execution-plan.md) | 现状盘点、契约、兼容矩阵、MVP 范围、决策门与端到端验收计划 |

## 合规

| 文档 | 说明 |
|------|------|
| [eu-ai-act-compliance.md](eu-ai-act-compliance.md) | EU AI Act 合规评估 |
