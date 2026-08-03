---
name: pipeline_manager
display_name: 流水线管理器
description: 启动流水线→异步轮询→HITL挂起/恢复→部署—6步闭环
category: orchestration
version: 1.0.0
status: enabled
execution_type: prompt
execution_backend: agent
input_schema:
  project_id:
    type: string
    required: true
    description: 项目ID
  stages:
    type: array
    required: true
    description: team_assembly输出的带order的stages
output_schema:
  result:
    type: object
    required: true
    description: {status, deploy_url, report}
triggers:
  - 启动流水线
  - 构建
  - 审批
  - 部署
effects:
  - type: read
    resources: ["pipeline_state:project"]
    idempotent: true
    rollback_available: false
  - type: write
    resources: ["pipeline_state:deploy"]
    idempotent: false
    rollback_available: true
---

# 流水线管理器 (Pipeline Manager)

启动流水线构建，通过异步轮询监控进度，在HITL审批点挂起/恢复，完成后触发部署。

## 执行流程

### Phase 1: 启动
```
1. 调用 pipeline.start Tool → 返回 project_id, status
2. 如果已存在活跃运行 → 跳过创建，直接进入轮询
```

### Phase 2: 异步轮询
```
while phase != "done":
  调 projectApi.getState(project_id)
  → phase == "executing" → sleep 3s → 继续
  → phase == "paused" or phase contains "approval"
      → Phase 3: 挂起
  → phase == "failed" → 记录错误 → 退出
  → phase == "done" → Phase 4: 部署
```

### Phase 3: HITL挂起/恢复 (关键机制)
**挂起 (Suspend)**:
1. 将 {project_id, current_step, context} 持久化到内存 HITL context 表
2. 通过 EventBus 发送 HITL_PAUSED 事件 → 前端显示"审批通过/驳回"按钮
3. 调用 `raise SuspendException` → ReActLoop 捕获 → Agent 进入 IDLE → 释放线程
4. 关键: 不阻塞循环等待——立即退出，由外部 Tool 触发恢复

**恢复 (Resume)**:
1. 用户点击前端按钮 → 前端调 factory_agent 的 `pipeline.approve`/`pipeline.reject` Tool
2. Tool 从 HITL context 读取 project_id, current_step → 调平台 API approve/reject
3. Tool 返回 {status: "resumed"} → ReActLoop 重新进入 pipeline_manager → 从 Phase 2 继续轮询

### Phase 4: 部署
```
phase == "done" →
  1. 调 app.deploy Tool
  2. 返回 {status: "completed", deploy_url: "http://..."}
```

## 反模式
- ❌ while循环阻塞等待审批 → 应主动退出+等待回调
- ❌ 不持久化挂起上下文 → 审批回调时找不到project_id
- ❌ 部署前不检查phase → 可能部署未完成的构建
- ✅ 轮询用sleep 3s避免过密调用
- ✅ 挂起时raise SuspendException让ReActLoop释放线程
- ✅ 恢复时从HITL context重新加载执行状态
