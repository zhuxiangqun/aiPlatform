---
id: canary_runner
name: canary_runner
display_name: 灰度发布执行器
description: 调用 /fde/canary/status 和 /fde/canary/rollback 执行灰度操作，监控质量指标并决定是否推进流量
execution_type: handler
category: fde
version: 1.0.0
status: enabled
effects:
  - type: read
    resources: ["http://localhost:8002/api/core/fde/canary"]
    idempotent: true
    rollback_available: false
  - type: write
    resources: ["http://localhost:8002/api/core/fde/canary/rollback"]
    idempotent: false
    rollback_available: true
input_schema:
  type: object
  properties:
    action:
      type: string
      enum: [status, advance, rollback]
      description: 灰度操作类型
    target_percent:
      type: integer
      description: 目标流量百分比（仅 advance 需要）
      minimum: 0
      maximum: 100
    rollback_reason:
      type: string
      description: 回滚原因（仅 rollback 需要）
  required:
    - action
output_schema:
  type: object
  properties:
    markdown:
      type: string
      description: 灰度报告摘要（Markdown 格式）
    canary_result:
      type: object
  required:
    - markdown
---

# 灰度发布 Skill

## 触发条件
当 FDE 在 ⑥ 评测护栏 Tab 中触发灰度操作时调用。

## SOP

### Step 1: 获取当前灰度状态
- 通过 `sys_tool_call` 调用 HTTP 请求：`GET /api/core/fde/canary/status`
- 解析返回的当前阶段、流量比例、关键质量指标（错误率、P95延迟、Golden Query通过率）

### Step 2: 根据 action 执行对应操作

- **status**: 仅返回当前状态摘要，不执行变更
- **advance**: 
  - 检查当前阶段质量指标是否全部达标（错误率<5%, P95延迟<20s, Golden Query通过率≥80%）
  - 若达标 → 推进流量到 `target_percent`，输出建议进入下一阶段
  - 若未达标 → 输出警告，建议暂缓推进
- **rollback**:
  - 记录 `rollback_reason`
  - 调用 `POST /api/core/fde/canary/rollback` 
  - 输出回滚摘要

### Step 3: 输出灰度报告
- 汇总当前灰度阶段状态、质量指标、流量进度
- 给出下一步建议（继续推进 / 暂停观察 / 回滚）

## 输出格式

```markdown
## 灰度状态报告

| 指标 | 当前值 | 阈值 | 状态 |
|------|:---:|:---:|:---:|
| 流量比例 | X% | — | — |
| 错误率 | X% | <5% | ✅/❌ |
| P95 延迟 | Xms | <20s | ✅/❌ |
| Golden Query 通过率 | X% | ≥80% | ✅/❌ |

**下一步建议**: [继续推进到 XX% / 暂停观察 / 立即回滚]
```

## 反模式

| 错误 | 正确 |
|------|------|
| 不检查当前指标就直接推进流量 | 先调用 status，确认全部达标再 advance |
| 回滚后不记录原因 | rollback 必须附带 `rollback_reason`，写入审计日志 |
| 全量上线后不输出质量对比 | 100% 后输出灰度阶段的质量趋势对比 |
