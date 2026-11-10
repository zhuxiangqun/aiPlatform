# Eval 对象现状卡（P0-A2 → P1b 工程刷新）

> **依据**：[改善执行计划](../EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md) §2.1 / 附录 A  
> **性质**：现状盘点，不是目标指标设计  
> **日期**：2026-11-05（工程字段对照 #596–#606 刷新；**Owner 已核实**）  
> **汇总**：工程事实 agent 代填；七卡 Owner 均为 **朱向群**（已签 · [核实一页纸](../EVAL_OBJECT_CARDS_OWNER_VERIFY.md)）

| # | 对象 | 文件 | Gate 资格（摘要） | 默认 `evidence_level`（推断） |
|---|---|---|---|---|
| 1 | Agent | [01-agent.md](./01-agent.md) | 不可单独作 accuracy/发布质量 gate | fixture（`replay_trace`） |
| 2 | Skill | [02-skill.md](./02-skill.md) | fixture smoke；不可作 live skill 认证 | fixture |
| 3 | Prompt | [03-prompt.md](./03-prompt.md) | engineering / gold 对照可入本地回归；≠ accuracy；**SubjectAdapter 已注册**（`prompt.capability`；同轨还有 `workflow`/`model`/`kb`/`code_review`/`session`/`tool`） | gold（有 exact/expected）/ fixture |
| 4 | KB/RAG | [04-kb-rag.md](./04-kb-rag.md) | fixture 检索检查；≠ RAG 准确率；**SubjectAdapter 已注册**（`kb.capability`） | fixture |
| 5 | Arena | [05-arena.md](./05-arena.md) | **smoke only**（长度 winner） | **smoke** |
| 6 | Code Review | [06-code-review.md](./06-code-review.md) | gold match 回归；≠ 真实仓库 E2E；**SubjectAdapter 已注册**（`code_review.capability`） | gold |
| 7 | Session | [07-session.md](./07-session.md) | fixture 多轮；≠ 长程 Agent；**SubjectAdapter 已注册**（`session.capability`） | fixture / gold（有 expected） |

另：**Tool/MCP** 无独立对象卡；`ToolSubjectAdapter` + `tool.capability` 已注册（mock tool_trace A3–A5；claim=false；≠ live）。

`accuracy_claim=false` · `process_split_authorized=false` · EET≠发布门禁等级 全程适用。

**P1b 工程接线（全对象共用）**：`create_report` → `ensure_report_scoring` / `ensure_report_meta`（`composite_version` + runner/judge + `evidence_level`）；Reports UI：对比 / 失败样本 / composite 过滤 / report_only 徽章。交接见 [EVAL_P1B_AGENT_HANDOFF.md](../EVAL_P1B_AGENT_HANDOFF.md)。
