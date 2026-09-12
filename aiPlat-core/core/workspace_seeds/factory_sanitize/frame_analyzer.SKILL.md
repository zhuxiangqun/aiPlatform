---
name: frame_analyzer
description: >-
  按间隔抽关键帧并生成画面描述/标签。平台 Path0 handler 执行真实 ffmpeg。
  task_id / duration_seconds 均可选（handler 可自建 task_id、从媒体探测时长）。
execution_type: prompt
version: 1.1.0
status: enabled
completion_criterion: |
  - 输出 keyframes（含 timestamp/description）与 keyframe_count
  - 无有效画面标签时降级空列表，不硬失败整单
triggers:
  - 抽帧
  - 画面分析
  - 关键帧
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
    description: optional; handler probes media when absent
  interval_sec:
    type: number
    required: false
  tenant_id:
    type: string
    required: false
output_schema:
  task_id:
    type: string
    required: true
  keyframes:
    type: array
    required: true
  keyframe_count:
    type: number
    required: true
  captions:
    type: array
    required: false
  status:
    type: string
    required: true
---
# 画面关键帧分析

## 输入校验
- 需要可解析的 media_ref / video_path（或已有 task 落盘视频）
- duration_seconds / task_id / tenant_id 均为可选

## 核心处理
1. 按 interval_sec（默认 10s）抽帧
2. 生成 description/caption
3. 输出 keyframes 列表

## 错误处理
- 无媒体 → failed 明确提示
- 空标签分段 → 空列表 + 标注，不中断流水线
