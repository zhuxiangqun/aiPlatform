---
name: app_page_generation
display_name: 应用页面生成
description: >-
  根据PRD和Agent的Skill清单,生成app_page.json页面布局协议。
  输出声明式组件配置,平台AppPage动态渲染。不生成原生代码。
category: generation
version: 1.0.0
status: enabled
execution_mode: prompt
execution_type: prompt
triggers:
  - 应用页面
  - 生成页面
  - app page
protected: true
idempotent: false
completion_criterion: |
  1. app_page.json包含所有PRD用户故事的交互
  2. 每个stage的component引用正确的平台组件
  3. 每个stage的skill引用真实的Agent Skill名
input_schema:
  prd:
    type: object
    required: true
    description: PRD(功能需求/用户故事)
  architecture:
    type: object
    required: false
    description: 架构设计(页面清单/组件类型)
  agent_app:
    type: object
    required: true
    description: 后端Agent的Skill清单
output_schema:
  app_page:
    type: object
    required: true
    description: app_page.json页面布局协议
keywords:
  objects:
  - 页面
  - app_page
  - 布局
  actions:
  - 生成
  - 设计
trigger_conditions:
- when: 需要生成应用页面
  query: 生成页面/app_page/app页面
effects:
  - type: read
    resources: ["pipeline_state:prd", "pipeline_state:agent_app"]
    idempotent: true
    rollback_available: false
skip_when: code_generation已处理代码模式
---

# 应用页面生成（Engine）

根据 PRD 和后端 Agent 的 Skill 清单，生成 `app_page.json`——声明式页面布局协议。

## 设计原则

生成的页面运行在平台的 `AppPage` 渲染器上，由预置组件库动态渲染:
- `file_upload` — 文件/图片上传
- `progress_poller` — 异步任务进度轮询
- `result_dashboard` — 多 section 结果展示
- `data_form` — 分步表单录入
- `data_table` — 表格列表
- `chat_panel` — 对话式交互

**不生成原生代码**。app_page.json 是协议，平台组件是渲染器。

## 组件匹配规则

| PRD 交互关键词 | 组件 | 配置要点 |
|-------------|------|------|
| 上传/导入/拖拽文件 | `file_upload` | accept/max_size/label/hint |
| 处理中/等待/异步/轮询 | `progress_poller` | status_field/poll_ms/stages/labels |
| 查看/展示/报告/预览/结果 | `result_dashboard` | sections[{key,label,type}] |
| 填写/输入/提交/申请 | `data_form` | fields[{name,label,type,required}] |
| 列表/搜索/筛选/排序 | `data_table` | columns[{key,label,sortable}] |
| 对话/问答/咨询/聊天 | `chat_panel` | hint/custom_prompt |

## SOP

1. 读 PRD 的用户故事和交互流程
2. 从 agent_app 的 agent_manifest.json 中提取 skill_routing 的 keys——这些是后端实际可调用的 Skill 名，必须精确匹配（含下划线和大小写）
3. 确定页面模式(mode):
   - `wizard` — 多步骤(上传→处理→结果)
   - `dashboard` — 组件平铺(监控/总览)
   - `chat` — 纯对话
4. 为每个交互步骤选择正确的平台组件
5. 每个 stage 指定对应的 Skill 名
6. 输出 `app_page.json`

## 输出格式

```json
{
  "app_name": "{app_name}",
  "app_title": "{应用标题}",
  "project_id": "{project_id}",
  "mode": "wizard",
  "stages": [
    {
      "id": "step1",
      "title": "步骤标题",
      "skill": "对应Skill名",
      "component": "file_upload|progress_poller|result_dashboard|data_form|data_table|chat_panel",
      "config": { ... }
    }
  ],
  "side_chat": { "enabled": true, "hint": "随时问我问题" }
}
```

## 反模式

| ❌ 错误 | ✅ 正确 |
|--------|--------|
| 生成 React/TSX 代码 | 生成 app_page.json |
| stage 不设 skill 字段 | 每个 stage 明确引用 Agent Skill |
| 引用不存在的 Skill 名或名称不匹配 | **必须**从 agent_manifest.json 的 skill_routing 字典中精确复制 key 名 |
| 自行编造 Skill 名 | 只能用 agent_manifest.json 里声明的 skill 名 |
| 组件的 input 用 JSON body | 用 `"{{prev_stage.field}}"` 引用上游结果 |
