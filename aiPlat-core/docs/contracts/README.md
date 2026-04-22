# aiPlat Contracts（行为约束文档集）

这套文档用于像 Claude Code 一样，用 **“约束性（normative）规范”** 来约束系统行为：当实现与文档冲突时，应优先修正实现或更新契约，并补齐验收用例。

## 术语（约束关键字）

本文档使用 RFC 2119 风格关键字：
- **MUST / 必须**：强制要求，不满足即视为缺陷
- **SHOULD / 应当**：推荐要求，除非有充分理由，否则不应偏离
- **MAY / 可以**：可选能力

## 文档目录

- [01-architecture-contract.md](./01-architecture-contract.md)  
  系统分层、边界、模块依赖约束、演进方式（ADR/变更控制）。

- [02-runtime-syscall-contract.md](./02-runtime-syscall-contract.md)  
  运行时与 Syscall 契约：ActiveRequestContext、trace/run_events、错误封装、恢复与重试语义。

- [03-tools-skills-contract.md](./03-tools-skills-contract.md)  
  Tool/Skill 的 Schema、权限/审批、动态发现（tool_search）、预算与可观测约束。

- [04-prompt-context-contract.md](./04-prompt-context-contract.md)  
  Prompt 与上下文管理契约：stable/ephemeral、cache key、prompt_mode、compaction、message guard。

- [05-governance-release-contract.md](./05-governance-release-contract.md)  
  治理与发布：policy gate、approval/change-control、rollout/rollback、autosmoke、审计证据。

- [06-acceptance-contract.md](./06-acceptance-contract.md)  
  验收与回归：每项契约的“可自动化验收点”、必跑测试集与 Definition of Done。

- [07-skill-types-contract.md](./07-skill-types-contract.md)  
  Skill 类型与发现/加载：规则型 vs 可执行型自动判别、find/load 体系、预算与生产分发建议（对齐 OpenCode find-skills）。

## 与现有设计文档的关系

Contracts 是“对外承诺/对内约束”，更偏 **可执行的规则**；现有设计文档更多解释“为什么”：
- `docs/design/kernel_orchestrator/*`：内核/编排设计与阶段性验收
- `docs/architecture/*`：架构对照与全局视图
- `docs/harness/*`：Harness 子系统说明

**MUST**：任何新增核心机制（syscall、gate、tool registry、prompt 组装层、exec backend、gateway）都应在 Contracts 中追加/更新条目，并在 `06-acceptance-contract.md` 中补齐验收用例链接。
