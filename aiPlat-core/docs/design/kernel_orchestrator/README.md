# Kernel-Orchestrator 设计文档集

本目录用于 **aiPlat-core 内核化改造（Harness=Kernel, Orchestrator=User-space）** 的设计评审与契约冻结，遵循“先文档、后改代码”的流程。

## 当前对齐状态（As-Is vs 设计）

> 重要：本目录包含 Phase 1~6 的完整 To‑Be 设计，但当前代码仅完成 Phase 1~3（其中 2/3 仍有“不可绕过”与指标量化的缺口）。  
> 如需严格验收，请先阅读：[ACCEPTANCE_REPORT.md](ACCEPTANCE_REPORT.md)。

| Phase | 目标 | 代码对齐结论（严格验收） |
|---|---|---|
| Phase 1 | 单入口 Integration.execute | PASS |
| Phase 2 | syscalls 封口 + 不可绕过 | PASS（已引入静态扫描脚本与 CI 阻断） |
| Phase 3 | 四大 Gate 下沉 | PARTIAL（Context/Resilience 最小实现；指标/CI 未冻结） |
| Phase 4 | ContextAssembler + PromptAssembler | PARTIAL（PromptAssembler 已灰度接入；ContextAssembler 仍为占位） |
| Phase 5 | Orchestrator + EngineRouter | PARTIAL（Phase 5.0 已引入 EngineRouter/LoopEngine 骨架，不改执行路径；Orchestrator 未落地） |
| Phase 6 | 自学闭环 | PARTIAL（learning_artifacts 落库表与 LearningManager 占位已提供；闭环策略与发布/回滚流程待实现） |

## 阅读顺序（评审顺序）

1. [00-architecture.md](00-architecture.md) —— 总体架构与关键取舍  
2. [01-contracts.md](01-contracts.md) —— 核心契约与数据模型（Phase 1 已对齐；Phase 4+ 待冻结）  
3. [02-syscalls-and-gates.md](02-syscalls-and-gates.md) —— syscalls + 四大 Gate（含可执行静态验收口径；待 CI 落地后冻结）  
4. [03-engines-and-routing.md](03-engines-and-routing.md) —— 多引擎接口、路由与回退链  
5. [04-security-and-audit.md](04-security-and-audit.md) —— 权限/审批/审计与 CI 规则（已对齐 As-Is；脱敏/CI 待补齐）  
6. [05-migration-and-acceptance.md](05-migration-and-acceptance.md) —— 分期迁移、回滚与验收指标（已补齐可执行验收口径）  

## 文档写作统一约束

- **以代码为准**：每个 To‑Be 模块必须映射到 As‑Is 代码路径与拟新增文件路径。  
- **契约先行**：types 与 syscall 接口先冻结，再谈实现。  
- **不可绕过**：每个设计必须回答“如何保证不可绕过”（代码结构 + CI）。  
- **可回放**：每个执行必须说明 run_id/trace_id 的产生、传递、落库字段。  
