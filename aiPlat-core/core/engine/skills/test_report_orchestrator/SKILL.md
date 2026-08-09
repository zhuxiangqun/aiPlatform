---
name: test_report_orchestrator
display_name: 修复编排器
description: 读取test_report，分析Bug归属，调用regenerate触发各阶段修复
category: orchestration
version: 1.0.0
status: enabled
execution_type: prompt
$ref: fix_summary
permissions:
  - http:read
  - http:write
effects:
  - type: write
    resources: ["http:regenerate"]
    idempotent: false
    rollback_available: true
output_schema:
  total_bugs:
    type: integer
    required: true
  fixed_stages:
    type: integer
    required: true
  stages:
    type: array
    required: true
---

# 修复编排器 SOP

你从上游拿到 test_report（已生成）。你的任务：分析 Bug → 调 regenerate → 输出修复小结。

重要：最终输出必须是纯 JSON，不含推理文字。

## Step 1: 读 test_report

test_report 已在你的上下文里（不需要 HTTP GET）。直接搜索 `"bug_summary"`。

如果找不到 bug_summary → 输出 `{"total_bugs":0,"fixed_stages":0}` 并终止。

## Step 2: 分析 Bug → 调 regenerate

从 bug_summary 读每条 Bug：
- `suggested_fix` 提到哪个 agent → 这就是归属 stage
- 用 `agent_id` 匹配 stage

对每个需要修复的 stage，调 POST：
```
http://localhost:8003/platform/builder/projects/{project_id}/regenerate
{"stage_id":"<agent_id>", "feedback":"测试发现Bug: ... 修复建议: ..."}
```
对于多次调用，用多步执行（每次一个 HTTP POST）。

project_id 从上下文中提取。

## Step 3: 输出纯 JSON 小结

```json
{"total_bugs":3,"fixed_stages":2,"stages":[{"stage_id":"agent_engineer","status":"regenerating"}]}
```

⚠️ 禁止在 JSON 前后加任何文字。禁止使用 ``` 代码块包裹。
