---
name: app_page_generation
display_name: 应用页面生成
description: >-
  根据PRD和Agent的Skill清单,生成app_page.json页面布局协议。
  输出声明式组件配置,平台AppPage动态渲染。不生成原生代码。
category: generation
version: 1.0.0
skill_model_purpose: code_gen
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

## 输出禁令
1. **直接输出**：第一个可见字符必须是 `{` 或 `#`（`## FILE:`）。禁止「步骤1–4」「方案比较」。
2. `result_dashboard` 的语音相关文案必须跟 PRD `decisions.speech_pipeline`（或等价表述）对齐：
   - **`audio_features_only`（不转写）**：sections **禁止**写「语音识别/转写/ASR」；用「语音声学特征 / VAD」；**不要**加 `transcript` section。
   - **`asr` / `hybrid`（含转写）**：**必须**有 `{"key":"transcript","label":"语音转写","type":"subtitle_timeline"}`；speech section 仍可用「语音声学特征」承载语种/说话人等粗标签，**禁止**把转写塞进 subtitle 冒充。
   - 未写明时：若 PRD 功能含「转写/ASR/语音识别」，按 `asr` 处理；仅「声学粗标签/不转写」按 `audio_features_only`。

## 组件匹配规则

| PRD 交互关键词 | 组件 | 配置要点 |
|-------------|------|------|
| 上传/导入/拖拽文件 | `file_upload` | accept/max_size/label/hint |
| 处理中/等待/异步/轮询 | `progress_poller` | status_field/poll_ms/stages/labels |
| 查看/展示/报告/预览/结果 | `result_dashboard` | sections[{key,label,type}] |

### result_dashboard.sections.type（强制闭集 — 与平台 ResultDashboard 一致）

**禁止**自造 type（`gallery`/`json`/`card` 等）。测真 `stage.result_sections_ok` 会 FAIL；sanitize `ensure_result_dashboard_sections` 会 remap。仅允许：

| type | 适用数据 |
|------|---------|
| `key_value` | 扁平对象（metadata、acoustic_labels）；degraded/failed 友好提示 |
| `image_timeline` | 关键帧数组（`local_path`/`url`/`time_sec`）；平台 `/app/media/{app}/{task}/...` |
| `timeline` | 时间点/区间（场景切换、VAD） |
| `subtitle_timeline` | 字幕 cues、**ASR 转写片段**、或无轨降级对象 |
| `markdown` / `text_block` | 摘要字符串 |
| `table` | 对象数组 |
| `tag_cloud` | 字符串数组 |

媒体结果推荐（**按 speech_pipeline 二选一**）：

- 不转写：`metadata` / `keyframes` / `scene_changes` / `subtitle` / `speech` / `vad` / `summary`
- 含转写（asr/hybrid）：在 `subtitle` 与 `speech` 之间插入 **`transcript:subtitle_timeline`（label=语音转写）**，其余同上。

| PRD 交互关键词 | 组件 | 配置要点 |
|-------------|------|------|
| 填写/输入/提交/申请 | `data_form` | fields[{name,label,type,required}] |
| 列表/搜索/筛选/排序 | `data_table` | columns[{key,label,sortable}] |
| 对话/问答/咨询/聊天 | `chat_panel` | hint/custom_prompt |

## Skill 引用与组件匹配（按 output 判断，不按名字）

`skill` 字段必须指向**其 output 满足该组件展示需求**的 Skill。**看 Skill 的 `output` 字段，而不是 Skill 的名字**——名字含 `result`/`download` 不代表语义。

| 组件 | 应指向的 Skill（按 output 判断） | 反例（禁止） |
|------|------|------|
| `result_dashboard` | 输出「分析/解析结果」的 Skill（output 含 `metadata`/`report`/`result`/`summary` 等展示数据） | 指向下载类 Skill（output 是 `file_name`/`file_content`/`download_url`） |
| `progress_poller` | 输出「状态/进度」或**同步分析管线终态**的 Skill（output 含 `status`；媒体类可指向与 `result_dashboard` 相同的报告 Skill，一次调用返回 `status=completed`） | 指向纯表单类 Skill；**禁止**与上一阶段相同的纯下载/入库 Skill（会空转轮询） |
| `data_form` | 输出「表单字段」或「下载链接」的 Skill（下载用 `download_link` 类型字段） | — |

**示例**：视频解析场景中，`report_json_export` 输出 `metadata`（展示数据），`video_downloader` 输出 `file_path`/`task_id`（入库）。则：
- 「选择来源 / 上传」→ `data_form` / `file_upload` → `skill: video_downloader`
- 「分析中」→ `progress_poller` → `skill: report_json_export`（或 ui_bindings.result_dashboard），`input` 含 `task_id` + `video_path`
- 「查看结果」→ `result_dashboard` → 同一报告 Skill

若 PRD 没有独立的「下载」交互，则不要硬造下载 stage。

## 输出格式（完整模板——AGENT.md 引用此节，2026-08-26 归属迁移）

用 `## FILE:` 格式，输出一个 app_page.json（下列完整模板按 **speech_pipeline=asr**；若为 audio_features_only 则去掉 transcript section）：

```json
{
  "app_name": "video_sense",
  "app_title": "智能视频理解",
  "project_id": "{project_id}",
  "mode": "wizard",
  "stages": [
    {
      "id": "source",
      "title": "选择视频来源",
      "skill": "video_downloader",
      "component": "data_form",
      "config": {
        "fields": [
          {
            "name": "source_type",
            "label": "视频来源",
            "type": "select",
            "required": true,
            "options": [
              {"value": "url", "label": "视频链接"},
              {"value": "upload", "label": "本地上传"}
            ]
          },
          {
            "name": "video_url",
            "label": "视频链接 URL",
            "type": "url",
            "required": true,
            "show_when": {"source_type": "url"},
            "hint": "仅支持 HTTP/HTTPS 直链"
          }
        ],
        "submit_label": "开始分析"
      },
      "next": "upload"
    },
    {
      "id": "upload",
      "title": "上传视频",
      "skill": "video_downloader",
      "component": "file_upload",
      "config": {
        "accept": "video/*",
        "max_size_mb": 500,
        "label": "选择视频文件",
        "hint": "支持 MP4/MOV/AVI/MKV，最大 500MB",
        "input": {
          "source_type": "{{source.source_type}}",
          "video_url": "{{source.video_url}}"
        }
      },
      "next": "progress"
    },
    {
      "id": "progress",
      "title": "分析中",
      "skill": "report_json_export",
      "component": "progress_poller",
      "config": {
        "status_field": "status",
        "poll_ms": 3000,
        "stages": ["pending", "analyzing", "processed", "completed"],
        "labels": {
          "pending": "排队中",
          "analyzing": "AI分析中",
          "processed": "聚合报告中",
          "completed": "已完成",
          "failed": "失败"
        },
        "input": {
          "task_id": "{{upload.task_id}}",
          "video_path": "{{upload.video_path}}"
        }
      },
      "next": "results"
    },
    {
      "id": "results",
      "title": "分析结果",
      "skill": "report_json_export",
      "component": "result_dashboard",
      "config": {
        "sections": [
          {"key": "metadata", "label": "视频元数据", "type": "key_value"},
          {"key": "keyframes", "label": "关键帧", "type": "image_timeline"},
          {"key": "scene_changes", "label": "场景切换", "type": "timeline"},
          {"key": "subtitle", "label": "软字幕轨", "type": "subtitle_timeline"},
          {"key": "transcript", "label": "语音转写", "type": "subtitle_timeline"},
          {"key": "speech", "label": "语音声学特征", "type": "key_value"},
          {"key": "vad", "label": "语音活动区间", "type": "timeline"},
          {"key": "summary", "label": "AI 摘要", "type": "markdown"}
        ],
        "input": {
          "task_id": "{{progress.task_id}}",
          "video_path": "{{progress.video_path}}"
        }
      }
    }
  ],
  "side_chat": {"enabled": true, "hint": "对结果有疑问?点我问"}
}
```

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
2. 从 agent_app 的 agent_manifest.json 接线 Skill（禁止编造）：
   - **优先**用上下文 `## ui_bindings`：每个 stage 的 `component` 查表得到 `skill`（精确复制）。
   - 其次用 `## skill_routing` 的 keys；无 ui_bindings 时按步骤语义选一个 routing key。
   - **禁止**因「summary 里看不到」而把 `skill` 留空；有 routing/bindings 时每个 stage 必须填精确 key。
   - 仅当 agent_app **与** skill_routing 都缺失时，才允许 `skill: ""`（绝不编造）。
   - 引擎落库后会按 ui_bindings 确定性补全空 skill；你仍应首稿写对。
3. 确定页面模式(mode):
   - `wizard` — 多步骤(上传→处理→结果)
   - `dashboard` — 组件平铺(监控/总览)
   - `chat` — 纯对话
4. 为每个交互步骤选择正确的平台组件（组件 id 应与 ui_bindings 的 key 对齐）
5. 每个 stage 的 skill 优先来自 ui_bindings[component]
6. **URL + 本地上传（强制）**：若 PRD 同时要求视频链接与本地上传，wizard **必须**含两个接入 stage：
   - `file_upload` → ui_bindings.file_upload（或同一 ingest skill）
   - `data_form`（字段 `video_url`，且当存在 `source_type` 选择器时 URL 字段必须带 `show_when: {source_type: url}`）→ ui_bindings.data_form（可与 file_upload 同 skill）
   禁止只生成一个 file_upload 而丢掉直链入口。
7. **进度/结果 I/O（强制）**：`progress_poller.config.input` 必须引用上游 `task_id` 与 `video_path`（或等价路径字段）；`result_dashboard.config.input` 必须引用 progress 的同名字段。进度 Skill **不得**与纯入库 Skill 相同。
8. 输出 `app_page.json`

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
| 引用不存在的 Skill 名或名称不匹配 | **必须**从 ui_bindings[component] 或 skill_routing 精确复制 |
| 忽略 ui_bindings 自行猜 skill | 有 ui_bindings 时 **必须**按 component 查表 |
| 自行编造 Skill 名 | 只能用 agent_manifest.json 里声明的 skill 名 |
| 读不到 agent_app 时编造 skill 名 | `skill` 字段留空 `""` 并保留 stage，宁可缺失也绝不编造 |
| `result_dashboard` 指向下载类 Skill | 展示结果 → 指向输出 metadata/结果的 Skill；下载 → `data_form` + download_link 指向下载 Skill |
| 组件的 input 用 JSON body | 用 `"{{prev_stage.field}}"` 引用上游结果 |
| PRD 有 URL+上传却只有 file_upload stage | **必须**增加 data_form（video_url）stage |
| `progress_poller` 与入库 Skill 同名且只传 task_id | 进度指向报告/分析 Skill，`input` 含 `task_id`+`video_path` |
| 有 `source_type` 却始终展示 URL 字段 | URL 字段加 `show_when: {source_type: url}` |
| result_dashboard 在 `audio_features_only` 时写「语音识别/转写」 | 不转写口径用「语音声学特征」；**不要**加 transcript |
| result_dashboard 在 `asr`/`hybrid` 时缺少 transcript | **必须**有 `transcript` + label「语音转写」 |
| 先写步骤推理再写 JSON | **直接**输出 app_page.json |
