---
name: {{skill_name}}
description: Aggregate processor outputs into a unified report and export JSON for result_dashboard.
execution_type: prompt
version: 1.0.0
status: enabled
completion_criterion: |
  - Aggregator: build unified report from shared state; task may reach completed only after export succeeds
  - Output includes structured report fields and exportable JSON; degrade missing dimensions without failing whole task
triggers:
  - 查看报告
  - 导出报告
  - 分析结果汇总
effects:
  - type: write
    resources: [filesystem:~/.aiplat/apps/{{app_name}}/reports]
    idempotent: true
    rollback_available: false
input_schema:
  task_id:
    type: string
    required: true
    description: Task id from ingress
  analysis_results:
    type: object
    required: true
    description: Processor outputs keyed by dimension
output_schema:
  status:
    type: string
    required: true
    description: completed|failed
  report_json:
    type: object
    required: true
    description: Unified report payload for result_dashboard
  report_id:
    type: string
    required: true
    description: Report id for frontend fetch
---
# Report export

## 输入校验
- task_id 必填；analysis_results 须为对象（可含部分维度 unavailable）

## 核心处理
1. 聚合各 processor 维度结果，按时间轴对齐（若有时间字段）
2. 生成可导出 JSON 报告，写入受管 reports 目录
3. 返回 report_id + report_json；本 Skill 为 aggregator，成功后任务可标 completed

## 错误处理
- 全部维度缺失 → status=failed
- 部分维度缺失 → 报告中标注 unavailable，status=completed
