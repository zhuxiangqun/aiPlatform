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

## Skill 引用与组件匹配（按 output 判断，不按名字）

`skill` 字段必须指向**其 output 满足该组件展示需求**的 Skill。**看 Skill 的 `output` 字段，而不是 Skill 的名字**——名字含 `result`/`download` 不代表语义。

| 组件 | 应指向的 Skill（按 output 判断） | 反例（禁止） |
|------|------|------|
| `result_dashboard` | 输出「分析/解析结果」的 Skill（output 含 `metadata`/`report`/`result`/`summary` 等展示数据） | 指向下载类 Skill（output 是 `file_name`/`file_content`/`download_url`） |
| `progress_poller` | 输出「状态/进度」的 Skill（output 含 `status`/`progress`） | 指向纯表单类 Skill |
| `data_form` | 输出「表单字段」或「下载链接」的 Skill（下载用 `download_link` 类型字段） | — |

**示例**：视频解析场景中，`video_parse` 输出 `metadata`（展示数据），`result_download` 输出 `file_name/file_content`（下载数据）。则：
- 「查看结果」阶段 → `result_dashboard` → `skill: video_parse`（展示 metadata）
- 「下载结果」阶段 → `data_form`（download_link 字段）→ `skill: result_download`

若 PRD 没有独立的「下载」交互，则不要硬造下载 stage。

## SOP

### 修复模式（最高优先级 — 上下文出现 `## 🛑 REGENERATE WITH FEEDBACK` 时执行）

当输入上下文中出现 `## 🛑 REGENERATE WITH FEEDBACK` 段落时，**进入修复模式，跳过下方 1-6 步的从零生成流程**：

1. **只修前端组件配置**：只处理 feedback 中与页面/组件/交互相关的 Bug（组件名如 progress_poller/result_dashboard/data_form/file_upload、按钮、对话框、提示、错误码展示等）；**后端 Agent/Skill 逻辑的 Bug（校验逻辑、认证、业务状态等）不是你的职责，直接忽略**。
2. **逐条精确落地 `suggested_fix`**：对每条相关的 `suggested_fix`，在对应 stage 的 `component` 和 `config` 中写出**精确的配置字段和值**。禁止只堆砌关键词（如只加"重试"字样），必须落到具体 config。例如：
   - "progress_poller 增加失败分支" → `"stages": [..., {"status": "failed", "label": "失败"}]` + `"error_display": {"show_code": true, "code_field": "error_code"}`
   - "result_dashboard 支持错误展示" → 在 result_dashboard 的 config 中增加 `"error_display": {"show_code": true}`
   - "data_form 支持暂停/取消" → `"actions": [{"type": "pause"}, {"type": "cancel"}]` + `"task_status": {"field": "status"}`
3. **保留未提及的 stage**：上一版中未被 feedback 指出的 stage 和正确配置要原样保留。
4. **重新输出完整 app_page.json**：修复后必须重新输出完整的 `app_page.json`（不要只输出 diff）。

---

1. 读 PRD 的用户故事和交互流程
2. 从 agent_app 的 agent_manifest.json 中提取 skill_routing 的 keys——这些是后端实际可调用的 Skill 名，必须精确匹配（含下划线和大小写）。**若 agent_app 缺失或无法读取，`skill` 字段留空并保留该 stage（不要删除阶段），绝不自行编造 skill 名。**
3. 确定页面模式(mode):
   - `wizard` — 多步骤(上传→处理→结果)
   - `dashboard` — 组件平铺(监控/总览)
   - `chat` — 纯对话
4. 为每个交互步骤选择正确的平台组件
5. 每个 stage 指定对应的 Skill 名
6. 输出 `app_page.json`

## 输出格式

> **app_name / project_id 规则（强制）**：`app_name` 必须使用上下文注入的 `## app_name` 值，`project_id` 必须使用上下文注入的 `## project_id` 值，**不得自行生成、翻译或改名**。`app_title` 用 PRD 的中文标题。

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
| 读不到 agent_app 时编造 skill 名 | `skill` 字段留空 `""` 并保留 stage，宁可缺失也绝不编造 |
| `result_dashboard` 指向下载类 Skill | 展示结果 → 指向输出 metadata/结果的 Skill；下载 → `data_form` + download_link 指向下载 Skill |
| 组件的 input 用 JSON body | 用 `"{{prev_stage.field}}"` 引用上游结果 |
