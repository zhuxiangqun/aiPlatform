markdown
---
name: history_query
description: 查询和管理用户的历史分析任务记录，支持搜索、查看详情和删除。
execution_type: prompt
input:
  - name: action
    type: string
    required: true
    description: 操作类型，枚举值为 'list'（列表）、'search'（搜索）、'detail'（查看详情）、'delete'（删除）。
  - name: filters
    type: object
    required: false
    description: 搜索过滤条件，包含 video_name（视频名称）、start_time（开始时间）、end_time（结束时间）。
  - name: page
    type: integer
    required: false
    description: 页码，默认 1。
  - name: page_size
    type: integer
    required: false
    description: 每页条数，默认 20。
  - name: record_id
    type: string
    required: false
    description: 历史记录ID（detail 和 delete 时必填）。
output:
  - name: history_list
    type: array
    description: 历史记录列表，每条包含 record_id、video_name、analysis_status、analysis_time、result_summary。
  - name: total_count
    type: integer
    description: 符合条件的总记录数。
  - name: detail
    type: object
    description: 单条历史记录的详细分析结果（detail 操作时返回）。
  - name: delete_confirmation
    type: string
    description: 删除确认信息（delete 操作时返回）。
---

# 历史记录管理

## 功能描述

管理用户的历史分析任务，支持分页列表、搜索过滤、查看详情和删除。

## 处理流程

1. **列表查询**：分页返回历史记录，每页 20 条。
2. **搜索过滤**：支持按视频名称、上传时间范围过滤。
3. **查看详情**：返回指定历史记录的完整分析结果。
4. **删除记录**：删除指定记录，删除前二次确认，删除后不可恢复。

## 边界情况

- 搜索无结果：返回空列表并提示「未找到匹配的历史记录」。
- 删除不存在的记录：提示「记录不存在」。
- 删除操作：需用户二次确认，确认后数据不可恢复。