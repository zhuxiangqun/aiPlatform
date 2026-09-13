---
name: video_downloader
description: >-
  校验并下载/落盘本地或 URL 视频，探测时长，按 ≤10 分钟切分逻辑分段，输出 media_ref、
  segments、duration_seconds、download_status。含 SSRF/协议/大小校验。平台 Path0 handler 执行真实 ffmpeg/下载。
execution_type: prompt
version: 1.1.0
status: enabled
completion_criterion: |
  - 成功：返回 media_ref + duration_seconds + segments（≤600s）+ download_status
  - SSRF/非 http(s)/超大文件 → failed，不落盘
  - 无来源 → clarify，不创建空任务
triggers:
  - 上传视频
  - 下载视频
  - 导入视频链接
effects:
  - type: write
    resources: [filesystem:~/.aiplat/apps/{{app_name}}/tasks]
    idempotent: false
    rollback_available: true
input_schema:
  source_type:
    type: string
    required: false
    description: local|url|file|upload
  source_url:
    type: string
    required: false
    description: http(s) URL when source_type=url
  file_path:
    type: string
    required: false
    description: local/upload path
  file_ref:
    type: string
    required: false
    description: alias of file_path
  tenant_id:
    type: string
    required: false
    description: tenant isolation key
  task_id:
    type: string
    required: false
    description: optional existing task id
output_schema:
  task_id:
    type: string
    required: true
  media_ref:
    type: string
    required: true
    description: local path of downloaded/accepted video
  video_path:
    type: string
    required: true
  duration_seconds:
    type: number
    required: true
  segments:
    type: array
    required: true
    description: logical segments ≤10 minutes with start_sec/end_sec/media_ref
  download_status:
    type: string
    required: true
    description: completed|failed|clarify|pending
  status:
    type: string
    required: true
---
# 视频下载与分段

## 输入校验
- URL 仅允许 http/https；拒绝 file://、内网 IP、未声明协议
- 本地文件扩展名白名单：mp4/avi/mkv/mov；超限拒绝
- 无 URL 且无本地文件 → clarify（提示补齐来源）

## 核心处理
1. SSRF/格式/大小校验，失败立即返回 download_status=failed
2. URL 下载或本地落盘到租户任务目录，得到 media_ref/video_path
3. probe 时长 → duration_seconds；按 ≤600s 生成 segments
4. 返回 download_status=completed（或 pending/clarify）

## 错误处理
- SSRF/协议非法 → failed + 明确错误消息
- 下载失败 → failed + 可重试提示
- 无音轨等不影响本 Skill（下游 SKIPPED_*）
