---
name: eval_code_generator
display_name: 评估代码生成器
description: 基于 Amazon Eval Agent 论文方法——通过结构化过程性指令 + 代码模板 + API 文档检索，为 Agent 自动生成评估代码。每个
  Agent 不超过 5 个评分指标，产出 2 个文件。
category: analysis
version: 1.0.0
status: enabled
execution_mode: handler
execution_type: handler
triggers:
  - 评估生成器
  - evaluate generator
  - 测试生成
permissions:
- eval:write
- llm:generate
- agent:read
- event:read
effects:
- type: write
  resources:
  - filesystem:~/.aiplat
  idempotent: false
  rollback_available: true
input_schema:
  target_agent_id:
    type: string
    required: true
    description: 要生成评估指标的目标 Agent ID
  max_traces:
    type: integer
    default: 5
    description: 读取最近多少条执行轨迹
output_schema:
  metrics:
    type: array
  eval_plan:
    type: string
  code_files:
    type: array
  markdown:
    type: string
    required: true
    description: 面向人阅读的 Markdown 输出
metadata:
  trigger_conditions:
  - 评估代码
  - 代码评估
  - 生成评估代码
  - 评分
  - 评估生成器
  - 代码评分
  - 生成评估报告
  - 自动化评估
  keywords:
    objects:
    - 评估代码
    - 评分标准
    - 测试用例
    actions:
    - 生成
    - 评估
    - 评分
  negative_triggers:
  - 不需要特定的编程语言知识
  - 不要猜测或编造不存在的数据
  sop_goal: 为 Agent 自动生成评估代码
sop_flow:
  - "你是一个评估代码生成器。你的任务是：读取目标 Agent 的配置和执行轨迹，按约束式模板生成评估代码。"
  - "**指标数量：不超过 5 个**。每个必须有明确的评分标准（0-10 或 PASS/FAIL）。禁止操作性度量（延迟、token 消耗、工具调用次数）。"
  - "**文件数量：不超过 2 个**。一个 `eval_metric.py`（指标实现）+ 一个 `eval_runner.py`（执行入口）。"
  - "**代码量：控制在 300 行以内**。先写最小可工作版本，不引入未验证的库。"
  - "**API 先验证**：使用任何库之前，确认它确实存在且版本正确。"
  - "读目标 Agent 的 AGENT.md："
  - "它的 agent_type 是什么（conversational / react / rag）？"
  - "它有哪些 tools 和 skills？"
protected: true
completion_criterion: |
  1. 每个 acceptance_criteria 至少有一个可执行的验证步骤
  2. 测试覆盖 happy path + 至少一个边界 case
  3. red-capable command 已确认能稳定复现目标行为
keywords:
  objects:
  - 评估代码
  - eval脚本
  - 测试代码
  actions:
  - 生成
  - 编写
  - 创建
  constraints:
  - 评估标准
  - 测试框架
trigger_conditions:
- when: 用户要求生成评估代码
  query: 生成eval/写评估脚本
- when: 不应用场景
  description: 跳过条件：评估标准未明确或不具备可执行测试框架时不触发。
skip_when: 跳过条件：评估标准未明确或不具备可执行测试框架时不触发。
---



## SOP

`execution_type: handler`。`handler.py` 必须调用 CoreFacade `generate_agent_eval`（`core/apps/eval/agent_eval.py`）。禁止在 Skill 正文或 router 里另写一套 LLM 落盘逻辑。

### 输入

- `target_agent_id`（必填）：被评 Agent 的 ID，不是本 Skill 自己
- `max_traces`（可选）
- `force`（可选）：覆盖已有维度/无轨迹也生成

### 行为（由 handler 执行）

1. 缺 `target_agent_id` → `missing_target_agent_id`
2. 调用 `generate_agent_eval`：写 ≤5 个任务质量维度 + `eval_metric.py` + `eval_runner.py`
3. 已齐全 / 无轨迹 / 目标是评估生成器 → `action=skip` 并写 `last_action.json`（可审计）
4. 生成后试跑 `eval_runner.py`；失败不抛到上架路径

### 产出位置

`~/.aiplat/eval/<target_agent_id>/eval_metric.py`、`eval_runner.py`、`last_action.json`、`last_report.json`

## 目标
为指定 Agent 生成可运行的评估脚手架（唯一入口）

## Checklist
- [ ] 只走 generate_agent_eval
- [ ] skip 原因可查
- [ ] 上架 listed 失败不得阻断上架