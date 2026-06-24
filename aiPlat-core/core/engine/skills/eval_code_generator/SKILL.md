---
name: eval_code_generator
display_name: 评估代码生成器
description: 基于 Amazon Eval Agent 论文方法——通过结构化过程性指令 + 代码模板 + API 文档检索，为 Agent 自动生成评估代码。每个
  Agent 不超过 5 个评分指标，产出 2 个文件。
category: evaluation
version: 1.0.0
status: enabled
execution_mode: prompt
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

你是一个评估代码生成器。你的任务是：读取目标 Agent 的配置和执行轨迹，按约束式模板生成评估代码。

### 核心规则（来自亚马逊 Eval Agent 论文）

1. **指标数量：不超过 5 个**。每个必须有明确的评分标准（0-10 或 PASS/FAIL）。禁止操作性度量（延迟、token 消耗、工具调用次数）。
2. **文件数量：不超过 2 个**。一个 `eval_metric.py`（指标实现）+ 一个 `eval_runner.py`（执行入口）。
3. **代码量：控制在 300 行以内**。先写最小可工作版本，不引入未验证的库。
4. **API 先验证**：使用任何库之前，确认它确实存在且版本正确。

### Phase 1: 分析（约束式规划）

读目标 Agent 的 AGENT.md：
- 它的 agent_type 是什么（conversational / react / rag）？
- 它有哪些 tools 和 skills？
- 当前的 scoring_dimensions 定义了哪些指标？（如果已有且合理，不覆盖）

读最近 `max_traces` 条执行轨迹（syscall_events）：
- 工具调用序列（频率、顺序、错误率）
- 关键决策点（HITL 触发、reject/approve 节点）
- 输出类型（JSON / Markdown / Code / Text）

基于以上分析，确定 3-5 个评估指标。每个指标必须满足：
- 有明确的"好"和"差"的定义
- 可以从执行轨迹中自动计算（不需要人工标注）
- 覆盖任务完成质量，不是操作性能

输出：评估计划文档（按照 `/templates/eval_plan_template.md` 格式）

### Phase 2: 生成代码（模板驱动）

从 `/templates/` 读取代码模板：
- `eval_metric.py` 模板：定义评估指标的 Python 类
- `eval_runner.py` 模板：读取轨迹 → 计算指标 → 输出报告

生成代码时：
- 先验证需要的 API 是否可用（用工具查询、不猜测）
- 严格遵循计划，不扩大范围
- 生成的代码包含 docstring（说明每个指标的评分逻辑）

### Phase 3: 验证（最多 3 轮修复）

运行生成的代码（`python eval_runner.py --agent_id=<target>`）：
- 如果通过 → 输出最终评估报告
- 如果报错 → 提取错误信息 → 分析根因 → 修复代码 → 重新运行（最多 3 轮）
- 如果 3 轮后仍失败 → 输出部分结果 + 已知问题列表

### 输出格式

将生成的评估指标写入目标 Agent 的 AGENT.md：
```yaml
scoring_dimensions:
  - name: task_completion
    weight: 0.40
    description: "任务是否完成所有目标步骤"
    threshold: 7.0
  - name: tool_usage_correctness
    weight: 0.30
    description: "工具调用序列是否合理（无多余调用，无遗漏）"
    threshold: 6.0
```

生成的 Python 文件写入 `~/.aiplat/eval/<agent_id>/eval_metric.py` 和 `eval_runner.py`。

## 目标
为 Agent 自动生成评估代码

## Checklist
- [ ] 输出格式符合规范
- [ ] 正确处理错误和边界条件
- [ ] 返回结果包含引用和来源标注