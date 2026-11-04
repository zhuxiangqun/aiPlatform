# Eval 对象现状卡（P0-A2）

> **依据**：[改善执行计划](../EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md) §2.1 / 附录 A  
> **性质**：现状盘点，不是目标指标设计  
> **日期**：2026-11-04  
> **汇总**：Evaluation owner（agent 代填，待各对象 owner 核实签字）

| # | 对象 | 文件 | Gate 资格（摘要） |
|---|---|---|---|
| 1 | Agent | [01-agent.md](./01-agent.md) | 不可单独作 accuracy/发布质量 gate |
| 2 | Skill | [02-skill.md](./02-skill.md) | fixture smoke；不可作 live skill 认证 |
| 3 | Prompt | [03-prompt.md](./03-prompt.md) | engineering / gold 对照可入本地回归；≠ accuracy |
| 4 | KB/RAG | [04-kb-rag.md](./04-kb-rag.md) | fixture 检索检查；≠ RAG 准确率 |
| 5 | Arena | [05-arena.md](./05-arena.md) | **smoke only**（长度 winner） |
| 6 | Code Review | [06-code-review.md](./06-code-review.md) | gold match 回归；≠ 真实仓库 E2E |
| 7 | Session | [07-session.md](./07-session.md) | fixture 多轮；≠ 长程 Agent |

`accuracy_claim=false` · `process_split_authorized=false` 全程适用。
