---
name: agent_engineering
display_name: Agent 工程
description: >-
  根据PRD和架构设计,将应用需求分解为Agent和多个Skill的Agent模型应用。
  输出AGENT.md和多个SKILL.md文件。
category: generation
version: 1.2.0
status: enabled
execution_mode: prompt
execution_type: prompt
triggers:
  - Agent应用
  - Agent模型
  - 生成Agent
  - Agent Engineering
permissions:
- fs:write
- fs:read
effects:
- type: write
  resources:
  - filesystem:~/.aiplat
  idempotent: false
  rollback_available: true
input_schema:
  prd:
    type: object
    required: true
    description: PRD(含功能需求/用户故事/验收标准)
  architecture:
    type: object
    required: true
    description: 架构设计(组件/API/数据模型)
output_schema:
  agent_app:
    type: object
    required: true
    description: "## FILE: AGENT.md + ## FILE: SKILL.md × N"
  summary:
    type: string
    required: true
    description: 生成摘要(Agent名/Skill数量/能力覆盖)
protected: true
idempotent: false
completion_criterion: |
  1. 生成至少1个AGENT.md文件
  2. 每个核心功能对应至少1个SKILL.md
  3. SKILL.md的 input_schema/output_schema 字段能串联（对象格式：每个字段含 name/type/required/description，
     禁止使用 input/output 列表格式——registry/discovery 只解析 input_schema/output_schema）
  4. AGENT.md的SOP正确引用所有Skills
  5. 每个 SKILL.md frontmatter 含 completion_criterion，且引用来自本轮 PRD 的 FR/AC（不得空泛）
  6. 异步任务状态机按角色一致：仅终态聚合阶段可将任务标 completed；ingress 成功不得 completed
  5. 每个 SKILL.md frontmatter 含 completion_criterion，且引用来自本轮 PRD 的 FR/AC（不得空泛）
  6. 异步任务状态机按角色一致：仅终态聚合阶段可将任务标 completed；ingress 成功不得 completed
version: 1.2.0
keywords:
  objects:
  - Agent
  - Skill
  - 应用
  actions:
  - 生成
  - 设计
  - 分解
trigger_conditions:
- when: 需要构建Agent应用
  query: 生成Agent/Agent工程/Agent应用
skip_when: 纯代码生成模式(code_generation已覆盖)
---

# Agent 工程（Engine）

## 设计原则

Agent 应用 = AGENT.md (编排) + SKILL.md × N (能力单元)。

生成的 Agent 运行在平台 ReActLoop 上，自动继承:
- 知识图谱 (domain 上下文注入)
- SECI 知识引擎 (对话→知识原子)
- 4层记忆 (Working/Episodic/Semantic/TaskSkill)
- 模型层级路由 (T1-T5)
- 平台内置工具 (文件/搜索/代码/知识检索)
- Quality Bus 评分
- Policy Gate 权限
- 自修复 + 自动学习

**例外（确定性媒体 handler）**：平台对已注册媒体 Skill 走 Path0 真实 I/O（跳过完整 ReAct），但会经 `_platform_effects_after_deterministic_skill` 补记 memory + local feedback。需要完整 ReAct 时设 `AIPLAT_FACTORY_FORCE_AGENT_SKILL=1`。

**不需要生成 FastAPI 路由或 React 组件**。Agent 本身即是应用。

## SOP

### 输出禁令（最高优先级）
1. **直接输出产物**：第一个可见字符必须是 `#`（`## FILE:`）或 `{`。禁止先输出「步骤1/步骤2」「分析关键约束」「方案A/B/C」「取舍」「Checklist」。
2. 推理过程不得落盘；Checklist 仅作自检，**不要写进回复**。

### 修复模式（最高优先级 — 上下文出现 `## 🛑 REGENERATE WITH FEEDBACK` 时执行）

当输入上下文中出现 `## 🛑 REGENERATE WITH FEEDBACK` 段落时，**进入修复模式，跳过下方 Step 0-4 的从零生成流程**：

1. **只修与自己职责相关的 Bug**：只处理 feedback 中与 Agent/Skill 后端逻辑相关的 Bug（校验逻辑、错误处理分支、业务状态流转、认证/授权、文件处理等）；**纯前端 UI/组件配置的 Bug（组件名如 progress_poller/result_dashboard/data_form、按钮、对话框等）不是你的职责，直接忽略**。
2. **逐条精确落地 `suggested_fix`**：对每条相关的 `suggested_fix`，在对应 SKILL.md 的「输入校验」「核心处理」「错误处理」中写出**明确的、可定位的文字**。禁止只堆砌关键词（如只写"支持重试/取消"），必须写清楚**在哪个分支、什么触发条件、返回什么**。例如：
   - "上传格式非法 → 返回『不支持的文件格式,仅支持 MP4/MOV/AVI/MKV』并拒绝入库"
   - "转码任务进行中收到删除请求 → 先调用取消转码再删除记录，状态置为已取消"
3. **保留未提及的内容**：上一版产物中未被 feedback 指出的正确逻辑要原样保留，不要因重写而丢失。
4. **重新输出完整产物**：修复后必须重新输出完整的 `agent_manifest.json` + 全部 AGENT.md + SKILL.md（下游需要完整文件，不要只输出 diff 或只输出被修改的部分）。

---

### Step 0: 架构选择（默认单 Agent — 2026-09 晋升契约）

**默认：`mode: single`（单 Agent + 多 Skill/工具）。** 能用单 Agent 搞定的，禁止拆多 Agent。
构建链（工厂 Pipeline 多角色）负责倒逼边界；**生成应用运行时**默认不升级为自由多 Agent。

#### 0.1 默认产出
1. 生成 **一个** AGENT.md + 所需 SKILL.md（Skills 由同一 Agent 编排调用）。
2. **必须**输出 `agent_manifest.json`，且 `"mode": "single"`。
3. `skill_routing` 可将全部 Skill 映射到该唯一 Agent；`ui_bindings` 值必须是 routing keys。

#### 0.2 升级为 `multi_agent`（五条判据全部 AND，缺一不可）
仅当下列 **全部** 成立时，才允许 `"mode": "multi_agent"`：

| # | 判据 | 必须写入 manifest |
|:-:|------|-------------------|
| 1 | 任务可自然分解为 ≥3 个正交子任务，且子任务间无频繁中间状态依赖 | `upgrade_criteria.orthogonal_subtasks`（列表，≥3） |
| 2 | 单 Agent 已在 N≥20 次执行中成功率低于阈值，且失败可归因到 `planning` 或 `tool_selection`（规划不足而非执行不足） | `upgrade_criteria.single_agent_gap`（含 n_runs / success_rate / failed_stages） |
| 3 | 存在明确 skill 路由收益：不同任务类型需加载完全不同的 skill 集，单上下文会溢出或注意力分散 | `upgrade_criteria.routing_benefit`（文字说明） |
| 4 | PolicyGate 已对工具面稳定运行 ≥1 迭代，可对每个 Agent 独立授权 | `upgrade_criteria.policy_gate_stable: true` |
| 5 | 跨 Agent 传递有 HITL/阶段契约：必须经 schema 门，禁止自由文本互调 | `upgrade_criteria.contracted_handoff: true` |

**禁止**：仅凭「功能需求数量多 / 看起来复杂 / 有异步 / 有审批」就拆 multi_agent。
**禁止**：Agent 之间直接自由调用；跨 Agent 必须经阶段契约 + schema 门 +（必要时）HITL。

#### 0.3 `multi_agent` 时 manifest 额外必填
- `multi_agent_rationale`：为何五条 AND 均满足（可复述 0.2）
- `success_metrics`：至少含 `min_runs`（≥20）、`target_success_rate`（建议起 0.80）
- `agents[]` / `skill_routing` / `ui_bindings`（与下文字段说明一致）
- 不做无门控互调：orchestrator SOP 必须写明分发键 ⊆ 下游 `input_schema`

#### 0.4 「跑通」提醒（生成物晋升，非本 Step 放行条件）
运行时晋升多 Agent 前，平台将按四维审计：E2E 成功率（N≥20）+ `failed_stage` 可归因 + conformance/real_tests 绿且有物理证据 + 工具调用在 PolicyGate 闭环。未跑通不得升级。

### Step 1: 分析需求，确定 Agent 身份
1. 读取 PRD 的标题、目标用户、核心功能
2. 确定 Agent 的 `agent_type`（影响引擎自动授予的能力等级）:
   - `conversational` — 纯对话 Agent（引擎授予 minimal: 仅基础上下文+质量评分）
   - `react` — 需要工具调用的复杂任务（引擎授予 autonomous: 全部 ~40 项核心能力）
   - `rag` — 以知识检索为主（引擎授予 full: 上下文+安全+检索+工具调用）
3. 确定 Agent 的显示名和描述

### Step 1.5: 派生验收标准（SBA 原则 17：需求是根，Plan 只拥有达成它的细节，2026-08-26）

**生成任何 SKILL.md / AGENT.md 之前，先列出 PRD 的验收契约：**

1. 从本轮输入 PRD 的 `functional_requirements` 提取每个需求的 `id` 与 `acceptance_criteria`（AC 清单），形成「验收标准表」（需求 id → AC 列表）。**只使用本轮 PRD 已给出的 id/AC 文本**，禁止编造 FR 编号或与 PRD 无关的验收句。
2. 每个生成的 SKILL.md 的 frontmatter **`completion_criterion` 字段必填**（见下方模板），且必须：
   - 点名该 Skill 覆盖的 **PRD 需求 id**（若有）与对应 AC；
   - 写成可检查条目（输入条件 → 可观察输出 / 拒绝条件）；
   - **禁止**空泛句（如「输出正确结果」「功能正常」「符合预期」）。
3. 若某条 PRD 未提供 `acceptance_criteria`，在该 Skill 的 `completion_criterion` 中显式写「验收未定义：{需求 id 或名称}」并补一组可验证默认验收（输入→预期输出→边界），不得静默省略字段。
4. **禁止**：生成物偷换/缩窄 PRD 验收——验收冲突必须回写 PRD 重新确认，不得在 Skill 内私自降级。

> 验收标准表只出现在生成过程的推理中（不落盘为独立文件）；各 SKILL.md 的 `completion_criterion` 是它的可检查投影。

### Step 1.6: 划分流水线角色（状态机依据 — 禁止按业务域名硬编码）

在写 SOP / 状态机之前，先按 **数据流位置**（而非业务词、而非 skill 名字符串匹配）给每个 Agent/Skill 标一个角色：

| 角色 | 如何判定（通用） | 任务级 status（共享状态） |
|------|------------------|---------------------------|
| `ingress` | 首次把外部输入落成可被后续步骤消费的资源（创建 task / 落盘 / 入库） | 成功 → `pending` 或 `ready`；**禁止** `completed` |
| `processor` | 读取已有资源并变换/分析，产出中间结果 | 进行中 → `processing`（或同义 `analyzing`）；本角色做完但流水线未结束 → `processed`；**禁止**任务级 `completed` |
| `aggregator` | 汇聚多路中间结果，产出用户可见终态产物（报告/摘要/交付物） | 成功 → **唯一允许**将任务标为 `completed`；失败 → `failed` |
| `orchestrator` | 路由与澄清，不单独定义终态 | 分发时携带 `task_id` + **下游 input_schema 所需字段**（字段名取自上游 `output_schema`，禁止臆造固定业务字段名） |

规则（强制）：
1. 同一应用内任务状态词表保持一致；允许同义别名（`processing`↔`analyzing`），但 **完成语义不得提前**。
2. Skill 的 `output_schema.status` 若表示 **本 Skill 调用结果**，可用 `completed`/`failed`/`skipped`；**不得**把「本 Skill 调用成功」写成「整单任务 completed」，除非该 Skill 的角色是 `aggregator`。
3. 每个 AGENT.md 的「异步任务状态机」章节必须按上表角色书写，且与 sibling Agent 不冲突（例如多个 worker 不得各自把任务标 `completed`）。
4. orchestrator SOP 必须写明：向 worker 分发时携带哪些键（来自上游 output / 下游 input 的交集），以及等待哪些完成信号后再进入下一角色。

### Step 2: 分解功能为 Skills
对 PRD 的每个 `functional_requirement`:
1. 判断是独立的能力单元还是内部步骤
2. 独立能力 → 生成 SKILL.md
3. 统一声明 `execution_type: prompt` — LLM 推理即可。本 pipeline 没有后端代码生成 stage，**不会生成 handler.py**；若声明 `handler` 会导致 Skill 注册时报错（§17），因此一律用 `prompt`。
   - **例外（平台内置）**：若 Skill 名命中平台 `media_skill_handlers`，测真与前端 `execute_skill` 会走真实 ffmpeg handler，**仍保持 SKILL.md 为 prompt**（无需生成 handler.py）。
   - **媒体能力命名约束（强制）**：凡涉及下载/抽帧/软字幕/语音能量/报告导出的 Skill，**必须**使用平台目录名（canonical 或已登记 alias），**禁止自造近义名**。
     - canonical：`video_downloader` / `frame_analyzer` / `subtitle_extractor` / `speech_analyzer` / `report_json_export`
     - 允许 alias（与平台 HANDLERS 一致）：`video_download`/`media_download`/`ssrf_check`/`file_validate` → downloader；`keyframe_extract`/`analyze_frames`/`extract_highlights`/`scene_detect`/`visual_caption` → frame；`subtitle_track_probe`/`subtitle_extract`/`srt_format` → subtitle；`audio_track_probe`/`acoustic_label`/`vad_detect`/`speech_transcription` → speech；`report_aggregate`/`build_timeline`/`result_summarization` → report
     - **禁止再拆**：不要同时发明 `analyze_frames`+`extract_highlights`（统一 `frame_analyzer`）；不要发明 `build_timeline`/`timeline_query`（并入 `report_json_export`）；不要发明 `video_import`/`video_transcription`（分别并入 `video_downloader` / `speech_analyzer`）；**禁止发明 `task_lifecycle` / 独立任务状态机 Skill**（`task_id` 由 `video_downloader` Path0 handler 自动创建；进度轮询绑 `report_json_export`，成功即 `status/task_status=completed`）；`speech_analyzer` **同时**覆盖 ASR 转写（`transcript`）+ 声学标签（语种/说话人/情绪），**禁止**拆成两个 Skill 或两个 Agent 争抢同一 routing key
     - **三一致（强制）**：`skill_routing` 的 key ≡ `skills/<name>/` 目录名 ≡ SKILL.md frontmatter `name:` ≡ AGENT.md `required_skills` 列表项；禁止同名多份 SKILL；每个 skill 只归属一个 Agent（以 `skill_routing` 为准）
     - **禁止把问答/对话 Skill 起成媒体目录名**：`video_qa` / `*_qa` / `*_chat` 为 prompt-only，**不得**命名为 `video_downloader` 或其它 handler 名（否则 Path0 会绑错真实 ffmpeg handler）。
     - **平台目录 Skill 契约（强制）**：canonical SKILL.md **不得改写平台 handler 语义**
       - `video_downloader` = 校验 + **下载/落盘** + 时长探测 + **≤10min segments**，输出 `media_ref`/`segments`/`duration_seconds`/`download_status`/`task_id`（**禁止**要求入口先传 `task_id`；**禁止**写成「仅创建 task_id=PENDING / 只写审计」；**禁止**拆出独立 `video_import`）
       - `frame_analyzer` / `speech_analyzer`：`task_id`/`duration_seconds`/`tenant_id` **均为可选**（handler 自建/探测）
       - `report_json_export` = **汇聚多模态 → 结构化报告 + timeline + report_path**，成功后 `task_status=completed`（**禁止**写成「仅进度查询 current_stage/block_status」；progress_poller **应**绑本 Skill，同步向导依赖 `completed`）
     - **progress_poller**：有 `report_json_export` 时**必须**绑报告 Skill（测真/预览需 `completed`）；**禁止**绑虚构 `task_lifecycle`；禁止长期绑纯下载 Skill 冒充全流水线进度。
     - 闸门：`quality_gate.normalize_media_skill_names` + `ensure_agent_app_skill_consistency` + `ensure_platform_media_skill_contracts`
4. 为每个 Skill 标注 Step 1.6 的角色（可写在 completion_criterion 旁的推理中；落盘 SOP/状态机必须遵守）。

**每个 SKILL.md 必须包含以下 3 个执步:**

1. **输入校验** — 验证所有输入的有效性，**必须写成确定性规则**（SBA 原则 18：低自由度判断下沉为可逐条执行的规则，禁止模糊措辞，2026-08-26）:
   - **格式校验**：给出可执行的格式判定（扩展名枚举、URL 前缀、正则/模式），禁止"检查格式是否正确"这类无法执行的描述
   - **范围校验**：给出数值边界（如大小上限、长度区间），禁止"检查大小是否合理"
   - **白名单校验**：**列全**允许值（取自本轮 PRD/约束，禁止臆造未在需求中出现的格式列表），禁止"检查是否在支持列表中"
   - **校验失败 → 返回明确错误消息**（写具体消息文本，不要只写"错误"）
   - 确定性规则评审标准：**每条校验能被一个不依赖 LLM 的检查器逐条执行**；无法写成确定值的校验必须拆成可判定的子条件

2. **核心处理** — 实际的业务逻辑（与本轮 PRD 一致）

3. **错误处理** — 失败的降级策略:
   - 输入无效 → 返回友好提示+修正指引
   - 处理超时 → 返回超时提示+重试建议
   - 资源不存在 → 返回"不存在"提示+替代方案
   - 内部异常 → 返回通用错误+建议联系管理员
   - 非关键路径失败（如可选轨道缺失）→ **降级标注并继续流水线**，不把整单标 `failed`，除非 PRD 要求硬失败

**Skill 拆分原则**:
- 一个 Skill 做一件事(单一职责)
- SKILL.md frontmatter 必须用 input_schema/output_schema 对象格式（字段: name/type/required/description）
- **frontmatter 必须含 `completion_criterion`**（见模板；缺此字段视为未完成生成）
- 禁止用 input/output 列表格式（registry 读 input_schema/output_schema，列表格式导致 schema 丢失）
- 所有 Skill 的 input_schema/output_schema 能串联成完整链路
- 优先复用平台已有的 Engine Skill,不重复造

### Step 3: 生成 AGENT.md
1. 写入 frontmatter (agent_type, required_skills, required_tools)
   - agent_type 必须根据 Step 1 的规则设定（react/conversational/rag）
2. 写入 SOP: 描述用户对话→调用哪个Skill→得到什么结果→如何反馈
3. 写入反模式 (常见错误+修正)
4. 写入 scoring_dimensions (质量评分维度)
5. 写入 **异步任务状态机**（按 Step 1.6 角色；多 Agent 时各 AGENT.md 状态机必须可拼成一条无冲突流水线）
6. **无需在 frontmatter 中写 capability_profile / execution_backend / quality_gate /
   context_profile / retry_policy / sandbox ——引擎根据 agent_type + required_tools
   自动推断能力剖面并注入对应能力集。**

### Step 4: 验证（输出前必过；失败则补全后再输出）
1. 检查所有 required_skills 对应的 SKILL.md 都已生成
2. 检查 Skill 的 input→output 链完整(上游 output 匹配下游 input)
3. 检查 AGENT.md 的 SOP 覆盖了所有 PRD 的 acceptance_criteria
4. 检查每个 SKILL.md 的执流包含「输入校验」部分
5. **逐文件检查**：每个 `## FILE: .../SKILL.md` 的 YAML frontmatter 含非空 `completion_criterion:`；若缺失 → 补写后再输出，禁止带着缺字段交付
6. **状态机检查**：ingress 成功路径无任务级 `completed`；仅 aggregator（或单 Agent 的终态步骤）可写任务级 `completed`；orchestrator 分发键 ⊆ 下游 input_schema
7. **agent_manifest.json**：必有且 `mode` 为 `single` 或（五条 AND 时）`multi_agent`；`ui_bindings` 值 ∈ `skill_routing` keys；若 PRD 同时描述「链接/URL 导入」与「本地文件上传」两类入口，则必须同时声明 `file_upload` 与 `data_form`（绑定到本轮已有 skill，不引入未声明名）
8. **multi_agent 门禁**：若 `mode=multi_agent`，必须含 `multi_agent_rationale`、`success_metrics.min_runs≥20`、`upgrade_criteria` 五条；否则改回 `single` 再输出

## 输出格式

用 `## FILE:` 格式输出。**无论 single / multi_agent，都必须首先输出 `agent_manifest.json`。**

> **app_name 规则（强制）**：`app_name` 必须使用上下文注入的 `## app_name` 值，**不得自行生成、翻译或改名**。所有 `## FILE:` 路径和 `agent_manifest.json` 的 `app_name` 字段必须与注入值完全一致。

### agent_manifest.json（默认 single — 第一条输出）

```
## FILE: ~/.aiplat/apps/{app_name}/agent_manifest.json
```json
{
  "app_name": "{app_name}",
  "mode": "single",
  "agents": [
    {
      "name": "app_agent",
      "display_name": "应用 Agent",
      "agent_type": "react",
      "role": "worker",
      "skills": ["ingress_skill", "process_skill", "report_json_export"],
      "description": "单 Agent 编排全部 Skills"
    }
  ],
  "skill_routing": {
    "ingress_skill": "app_agent",
    "process_skill": "app_agent",
    "report_json_export": "app_agent"
  },
  "ui_bindings": {
    "file_upload": "ingress_skill",
    "data_form": "ingress_skill",
    "progress_poller": "report_json_export",
    "result_dashboard": "report_json_export"
  }
}
```

### agent_manifest.json（仅当 Step 0.2 五条 AND 全满足 — multi_agent 示例）

```
## FILE: ~/.aiplat/apps/{app_name}/agent_manifest.json
```json
{
  "app_name": "{app_name}",
  "mode": "multi_agent",
  "multi_agent_rationale": "五条 AND 均满足：≥3 正交子任务；单 Agent N≥20 成功率不足且失败在 planning；skill 集互斥导致上下文溢出；PolicyGate 已稳定；跨 Agent 仅经 schema 门+HITL。",
  "success_metrics": {
    "min_runs": 20,
    "target_success_rate": 0.80
  },
  "upgrade_criteria": {
    "orthogonal_subtasks": ["ingress", "process_a", "aggregate"],
    "single_agent_gap": {
      "n_runs": 20,
      "success_rate": 0.55,
      "failed_stages": ["planning", "tool_selection"]
    },
    "routing_benefit": "媒体处理与报告聚合 skill 集互斥，单上下文溢出",
    "policy_gate_stable": true,
    "contracted_handoff": true
  },
  "agents": [
    {
      "name": "orchestrator_agent",
      "display_name": "协调 Agent",
      "agent_type": "react",
      "role": "orchestrator",
      "skills": ["upload", "check_progress"],
      "description": "接收用户请求,经契约分发到子Agent"
    },
    {
      "name": "analysis_agent",
      "display_name": "分析 Agent",
      "agent_type": "react",
      "role": "worker",
      "skills": ["video_analysis", "result_presentation"],
      "description": "执行AI分析,生成结果"
    }
  ],
  "skill_routing": {
    "video_upload": "orchestrator_agent",
    "video_analysis": "analysis_agent",
    "result_presentation": "analysis_agent",
    "check_progress": "orchestrator_agent"
  },
  "ui_bindings": {
    "file_upload": "video_upload",
    "data_form": "video_upload",
    "progress_poller": "check_progress",
    "result_dashboard": "result_presentation"
  }
}
```

manifest 字段说明:
- `mode`: **`single`（默认）** / `multi_agent`（仅 Step 0.2 五条 AND）
- `multi_agent_rationale` / `success_metrics` / `upgrade_criteria`: **仅 multi_agent 必填**（conformance 机器校验）
- `agents[].role`: `orchestrator`(协调) / `worker`(执行) / `notification`(通知)
- `skill_routing`: 每个 Skill → 负责 Agent 的映射表(前端页面用) — **必填**
- `ui_bindings`: 平台组件 id → skill 名 — **必填**（前端 stage 接线 SoT；值必须是 `skill_routing` 的 key）
  - 常见组件: `file_upload` / `progress_poller` / `result_dashboard` / `data_form` / `data_table` / `chat_panel`
  - 按 **本轮 PRD 交互步骤** 推断组件，再绑定本轮已声明的 Skill；禁止引用未在 `skill_routing` 中的名
  - **URL + 本地上传**：若 PRD 同时要求链接导入与文件上传，`ui_bindings` **必须同时**包含 `file_upload` 与 `data_form`（可指向同一或不同 ingress skill；skill 名必须已在 routing 中）
  - **`ui_bindings` 的值必须是 `skill_routing` 的 key（Skill 名）**，禁止填 Agent `name`（如误写 orchestrator / video_analyzer）
  - **`result_dashboard` 强制**：必须存在一个 **报告/导出类 Skill**（建议名 `report_json_export` 或含 `report`/`export`/`summar` 词根），并写入 `skill_routing` + 对应 AGENT 的 `required_skills`/`skills`；`ui_bindings.result_dashboard` **只能**绑该 Skill。禁止绑 Agent id，禁止绑纯分析/下载类 Skill 冒充报告。
  - 报告 Skill 的职责：从共享状态聚合各 processor 产出 → 统一时间轴/结构化报告 → 可导出 JSON；其角色为 Step 1.6 的 `aggregator`（任务级 `completed` 仅在此之后）。
  - `progress_poller` 绑定能反映任务进度/状态的 Skill（可为 ingress 或专用 `check_progress` Skill；禁止绑最终报告 Skill）
- 对外纪律：**不做无门控互调，做阶段契约 + schema 门 + HITL。**

**异步任务状态机（强制 — 按 Step 1.6 角色，禁止业务域名/skill 名硬编码分支）**：
- `ingress` 成功 → 任务 `pending`/`ready`（**不要** `completed`）
- `processor` 进行中 → `processing`/`analyzing`；本段做完流水线未结束 → `processed`（**不要**任务级 `completed`）
- 仅 `aggregator`（或单 Agent 终态步骤）成功 → 任务 `completed`；任一硬失败 → `failed`
- orchestrator SOP **必须**写明分发载荷：`task_id` + 下游 `input_schema` 所需字段（字段名来自上游 `output_schema`，例如资源路径键叫什么就传什么，禁止写死某一业务字段名）

**SKILL.md frontmatter 必须含 `completion_criterion`**：引用来自本轮 PRD 的需求 id / AC；禁止空泛「输出正确」。缺字段 = 未完成，须在 Step 4 补全。

### AGENT.md + SKILL.md
```yaml
---
name: {agent_name}
display_name: {显示名}
agent_type: conversational
model: auto
required_skills:
  - {skill_1}
  - {skill_2}
required_tools:
  - file_operations
  - knowledge_retrieve
phase: deployed
scoring_dimensions:
  - name: accuracy
    weight: 0.4
  - name: completeness
    weight: 0.3
  - name: user_experience
    weight: 0.3
---
# {显示名}

## SOP
1. ...
2. ...
3. ...

## 反模式
- ...

## 异步任务状态机
- （按 Step 1.6 角色填写；与 sibling Agent 无冲突）
```

### SKILL.md 模板（每个 Skill 必须按此骨架输出，字段不得删减——B1 骨架化 2026-08-26）

> 下面的 `yaml` 代码块仅作文档展示；**实际生成的 SKILL.md 文件首行必须是 `---`（无任何代码块标记）**，否则注册时被 conformance 契约拒绝。

```
---
name: {skill_name}                   # 必填：kebab-case
description: {一句话描述，含触发场景}  # 必填：触发路由/description 命中率依赖它
execution_type: prompt               # 必填：本 pipeline 一律 prompt（不生成 handler.py）
version: 1.0.0                       # 必填：版本（注册回滚依赖）
status: enabled                      # 必填
completion_criterion: |              # 必填：引用本轮 PRD 的需求 id/AC；禁止空泛句
  - 覆盖 {FR-id}：{摘自 PRD 的 AC 原文或等价可检查表述}
  - 边界：{拒绝/降级条件 → 可观察输出}
triggers:                            # 必填：B2 路由-知识分离——触发短语清单（用户自然语言命中路由）
  - {触发短语1}
  - {触发短语2}
effects:                             # 必填：§5.19 副作用声明（registry 注册强制，缺失被拒）
  - type: read                       # read/write/execute/both
    resources: [filesystem:~/.aiplat]
    idempotent: true                 # 幂等：同输入重复执行结果一致
    rollback_available: false
input_schema:                        # 必填：对象格式（禁止 input 列表，registry 读 input_schema）
  {参数名}:
    type: string                     # string/integer/object/array
    required: true
    description: {参数说明}
output_schema:                       # 必填：对象格式
  {结果名}:
    type: object
    required: true
    description: {结果说明}
---
# {Skill 显示名}

## 输入校验
- 格式校验: ...
- 范围校验: ...
- 白名单校验: ...（允许值取自本轮 PRD/约束）
- 校验失败 → 返回明确错误消息

## 核心处理
1. ...
2. ...

## 错误处理
- 输入无效 → 友好提示+修正指引
- 处理超时 → 超时提示+重试建议
- 资源不存在 → "不存在"提示+替代方案
- 内部异常 → 通用错误+建议联系管理员
```

frontmatter 字段与 `generated_conformance.yaml` 契约严格对齐：`execution_type` / `input_schema` / `output_schema` / `version` / `status: enabled` / `description` / **`completion_criterion`** 全部必填；首行必须是 `---`。生成后由注册循环 conformance 校验兜底，缺字段会被拒绝注册。

## 反模式 (Agent Engineer 自身的)

| ❌ 错误 | ✅ 正确 |
|--------|--------|
| 生成 Python/React 代码 | 生成 AGENT.md + SKILL.md |
| 把所有功能塞进一个 Skill | 按单一职责拆分 |
| AGENT.md 的 SOP 太模糊 | 每步明确写调用哪个Skill |
| 忽略平台已有的 Engine Skill | 优先复用: file_operations/knowledge_retrieve/code_execution |
| 生成 handler.py (需要编码) | 优先用 execution_type: prompt (LLM推理即可) |
| 声明 `execution_type: handler` | 一律用 `execution_type: prompt`（本 pipeline 不生成 handler.py，handler 会注册报错） |
| 用 ```yaml 包裹 YAML 内容 | ⚠️ AGENT.md/SKILL.md 的 YAML frontmatter 必须从第一行 `---` 开始，禁止前置 `yaml` 代码块标记 |
| 用 ```json 包裹 JSON 内容 | ⚠️ agent_manifest.json 必须是纯 JSON，禁止任何代码块标记封装，禁止末尾 `---` |
| 只写 skill_routing、不写 ui_bindings | **必须**同时输出 `ui_bindings`（组件→skill），否则前端无法确定性接线 |
| ui_bindings 指向不存在的 skill | 值必须是 `skill_routing` 的 key |
| PRD 同时有链接导入与文件上传却只绑其一 | **必须**同时绑 `file_upload` + `data_form`（skill 名取自本轮 routing） |
| `ingress`/`processor` 把任务标 `completed` | 仅 `aggregator`（终态）可将任务标 `completed`；中间阶段用 pending/processing/processed |
| 分发载荷写死某一业务字段名 | 分发键 = 下游 input_schema ∩ 上游 output_schema |
| 先写步骤1–4/方案比较再写 FILE | **直接**从 `## FILE:` 开始输出 |
| SKILL 缺 `completion_criterion` 或写「输出正确」 | frontmatter 必填，且引用本轮 PRD 的需求 id/AC |
| `result_dashboard` 绑 Agent id 或分析 Skill | 必须新增/绑定报告类 Skill（如 `report_json_export`） |
| 自造媒体 Skill 名（如 `video_fetch`/`frame_pick`） | 必须用平台目录 canonical/alias（见 Step 2 命名约束） |
| 按域名/产品名写 if 分支规则 | 规则只依赖 PRD 字段、数据流角色、schema 键名 |

## Checklist
- [ ] 根据 PRD 复杂度决定单/多 Agent 模式
- [ ] 多 Agent 模式: 首先输出 agent_manifest.json
- [ ] 每个 Agent 至少 1 个 AGENT.md
- [ ] 每个核心功能对应 1 个 SKILL.md（由负责的 Agent 的 `required_skills` 引用）
- [ ] **存在报告/导出 Skill，且 `ui_bindings.result_dashboard` 指向它（∈ skill_routing）**
- [ ] 媒体相关 Skill 名 ∈ 平台目录（canonical 或 alias），无自造近义名
- [ ] skill_routing key ≡ skills/<name>/ ≡ frontmatter name；无重复 Skill 名；问答类不用媒体 handler 名
- [ ] 多 Agent 时: orchestrator 的 SOP 描述分发键与完成信号（来自 schema，非臆造字段）
- [ ] agent_manifest.json 的 skill_routing 覆盖所有 Skill
- [ ] agent_manifest.json 的 **ui_bindings** 覆盖 PRD 交互步骤对应的平台组件，且值 ∈ skill_routing keys
- [ ] PRD 双入口（链接+上传）时同时声明 file_upload 与 data_form
- [ ] **每个** SKILL.md frontmatter 含非空 `completion_criterion`（引用本轮 PRD FR/AC）
- [ ] 任务状态机按 ingress/processor/aggregator 一致，无过早 `completed`
- [ ] scoring_dimensions 已定义(3-4个维度)
- [ ] 优先使用 execution_type: prompt
- [ ] 没有生成 Python 或 React 代码
- [ ] 回复无「步骤1–4」前缀（自检用，不输出）
