---
name: speech_analyzer
description: >-
  对音轨做 ASR 转写（transcript）与声学标签（语种/说话人/情绪/VAD）。
  平台 Path0 handler 执行；task_id / duration_seconds / tenant_id 可选。
execution_type: prompt
version: 1.1.0
status: enabled
completion_criterion: |
  - 输出 transcript（可空）+ transcript_segments；无音轨时 SKIPPED/空转写并标注
triggers:
  - 语音转写
  - ASR
  - 声学分析
effects:
  - type: write
    resources: [filesystem:~/.aiplat/apps/{{app_name}}/tasks]
    idempotent: true
    rollback_available: false
input_schema:
  media_ref:
    type: string
    required: false
  video_path:
    type: string
    required: false
  task_id:
    type: string
    required: false
  duration_seconds:
    type: number
    required: false
    description: optional bound for segment clamps; handler probes when absent
  has_audio:
    type: boolean
    required: false
  tenant_id:
    type: string
    required: false
output_schema:
  task_id:
    type: string
    required: true
  transcript:
    type: string
    required: true
  transcript_segments:
    type: array
    required: false
  vad_segments:
    type: array
    required: false
  status:
    type: string
    required: true
---
# 语音转写与声学分析

## 输入校验
- 需要可解析媒体路径；duration_seconds/task_id/tenant_id 可选
- 分段时间戳若提供：start_sec>=0；若已知 duration 则 end_sec<=duration

## 核心处理
1. ASR → transcript / transcript_segments
2. VAD / 声学标签
3. 无音轨 → 空转写 + 原因标注

## 错误处理
- 无媒体 → failed
- 无音轨 → 降级继续
