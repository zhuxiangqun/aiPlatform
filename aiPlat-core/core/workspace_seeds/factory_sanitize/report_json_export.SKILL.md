---
name: report_json_export
description: >-
  汇聚转写/画面/字幕/语音结果，生成结构化报告与统一时间轴并导出 JSON（report_path）。
  成功后 task_status=completed。ProgressPoller 可重复调用（缓存命中返回同一报告）。
  禁止把本 Skill 写成「仅进度查询」——进度字段可附带，但主输出必须是报告与时间轴。
execution_type: prompt
version: 1.1.0
status: enabled
completion_criterion: |
  - 输出 report + timeline + report_path；成功后 task_status=completed
  - 缺失模态标注 skipped，不阻塞整单
  - 可被 progress_poller 与 result_dashboard 复用
triggers:
  - 生成报告
  - 导出结果
  - 查看分析结果
  - 任务进度
effects:
  - type: write
    resources: [filesystem:~/.aiplat/apps/{{app_name}}/reports]
    idempotent: true
    rollback_available: false
input_schema:
  task_id:
    type: string
    required: false
    description: optional; handler creates when absent
  media_ref:
    type: string
    required: false
  video_path:
    type: string
    required: false
  tenant_id:
    type: string
    required: false
  frame_result:
    type: object
    required: false
  speech_result:
    type: object
    required: false
  subtitle_result:
    type: object
    required: false
output_schema:
  task_id:
    type: string
    required: true
  status:
    type: string
    required: true
  task_status:
    type: string
    required: true
    description: completed when export succeeds
  report:
    type: object
    required: true
  timeline:
    type: array
    required: true
  report_path:
    type: string
    required: true
  keyframes:
    type: array
    required: false
  transcript:
    type: string
    required: false
---
# 报告合成与导出

## 输入校验
- task_id / media_ref 至少其一可解析（handler 可自建 task_id）
- 各模态结果可选；全缺时仍可由 handler 补跑后产出报告

## 核心处理
1. 汇聚 frame/speech/subtitle（或由平台 handler 补跑）
2. 生成统一 timeline 与结构化 report
3. 落盘 report_path；task_status/status=completed
4. 重复调用可返回缓存（供 progress_poller）

## 错误处理
- 无 task_id → failed
- 部分模态缺失 → 报告内标注，仍 completed
