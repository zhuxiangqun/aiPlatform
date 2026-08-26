---
name: agent_engineering
display_name: Agent 工程
description: >-
  根据PRD和架构设计,将应用需求分解为Agent和多个Skill的Agent模型应用。
  输出AGENT.md和多个SKILL.md文件。
category: generation
version: 1.1.0
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

**不需要生成 FastAPI 路由或 React 组件**。Agent 本身即是应用。

## SOP

### 修复模式（最高优先级 — 上下文出现 `## 🛑 REGENERATE WITH FEEDBACK` 时执行）

当输入上下文中出现 `## 🛑 REGENERATE WITH FEEDBACK` 段落时，**进入修复模式，跳过下方 Step 0-4 的从零生成流程**：

1. **只修与自己职责相关的 Bug**：只处理 feedback 中与 Agent/Skill 后端逻辑相关的 Bug（校验逻辑、错误处理分支、业务状态流转、认证/授权、文件处理等）；**纯前端 UI/组件配置的 Bug（组件名如 progress_poller/result_dashboard/data_form、按钮、对话框等）不是你的职责，直接忽略**。
2. **逐条精确落地 `suggested_fix`**：对每条相关的 `suggested_fix`，在对应 SKILL.md 的「输入校验」「核心处理」「错误处理」中写出**明确的、可定位的文字**。禁止只堆砌关键词（如只写"支持重试/取消"），必须写清楚**在哪个分支、什么触发条件、返回什么**。例如：
   - "上传格式非法 → 返回『不支持的文件格式,仅支持 MP4/MOV/AVI/MKV』并拒绝入库"
   - "转码任务进行中收到删除请求 → 先调用取消转码再删除记录，状态置为已取消"
3. **保留未提及的内容**：上一版产物中未被 feedback 指出的正确逻辑要原样保留，不要因重写而丢失。
4. **重新输出完整产物**：修复后必须重新输出完整的 `agent_manifest.json` + 全部 AGENT.md + SKILL.md（下游需要完整文件，不要只输出 diff 或只输出被修改的部分）。

---

### Step 0: 多 Agent 评估
根据 PRD 的复杂度，决定单 Agent 还是多 Agent 架构：

| PRD 信号 | Agent 数量 | 架构 |
|---------|:---:|------|
| ≤3 个功能需求，无异步流程 | 1 | 单 Agent 处理全部 |
| 4-6 功能需求，有异步任务 | 2-3 | 拆分为: orchestrator + 1-2 个 sub-agent |
| ≥7 功能需求，有实时+批量混合 | 4+ | orchestrator + 多个 sub-agent |
| 有实时通知/定时任务 | +1 | 加 notification_agent |
| 有审批/多角色 | +1 | 加 orchestrator_agent 协调流程 |

**多 Agent 模式必须生成 `agent_manifest.json`**，记录：
- 每个 Agent 的 name、display_name
- 每个 Agent 负责哪些 Skills
- Skill → Agent 的路由映射表

### Step 1: 分析需求，确定 Agent 身份
1. 读取 PRD 的标题、目标用户、核心功能
2. 确定 Agent 的 `agent_type`（影响引擎自动授予的能力等级）:
   - `conversational` — 纯对话 Agent（引擎授予 minimal: 仅基础上下文+质量评分）
   - `react` — 需要工具调用的复杂任务（引擎授予 autonomous: 全部 ~40 项核心能力）
   - `rag` — 以知识检索为主（引擎授予 full: 上下文+安全+检索+工具调用）
3. 确定 Agent 的显示名和描述

### Step 2: 分解功能为 Skills
对 PRD 的每个 `functional_requirement`:
1. 判断是独立的能力单元还是内部步骤
2. 独立能力 → 生成 SKILL.md
3. 统一声明 `execution_type: prompt` — LLM 推理即可。本 pipeline 没有后端代码生成 stage，**不会生成 handler.py**；若声明 `handler` 会导致 Skill 注册时报错（§17），因此一律用 `prompt`。

**每个 SKILL.md 必须包含以下 3 个执步:**

1. **输入校验** — 验证所有输入的有效性:
   - 格式校验 (文件扩展名/URL格式/数据类型)
   - 范围校验 (大小限制/长度限制/取值限制)
   - 白名单校验 (平台列表/格式列表/清晰度列表)
   - 校验失败 → 返回明确错误消息 (不要只写"错误",要写具体消息如"不支持的文件格式,仅支持 MP4/MOV/AVI/MKV")

2. **核心处理** — 实际的业务逻辑

3. **错误处理** — 失败的降级策略:
   - 输入无效 → 返回友好提示+修正指引
   - 处理超时 → 返回超时提示+重试建议
   - 资源不存在 → 返回"不存在"提示+替代方案
   - 内部异常 → 返回通用错误+建议联系管理员

**Skill 拆分原则**:
- 一个 Skill 做一件事(单一职责)
- SKILL.md frontmatter 必须用 input_schema/output_schema 对象格式（字段: name/type/required/description）
- 禁止用 input/output 列表格式（registry 读 input_schema/output_schema，列表格式导致 schema 丢失）
- 所有 Skill 的 input_schema/output_schema 能串联成完整链路
- 优先复用平台已有的 Engine Skill(39个),不重复造

### Step 3: 生成 AGENT.md
1. 写入 frontmatter (agent_type, required_skills, required_tools)
   - agent_type 必须根据 Step 1 的规则设定（react/conversational/rag）
2. 写入 SOP: 描述用户对话→调用哪个Skill→得到什么结果→如何反馈
3. 写入反模式 (常见错误+修正)
4. 写入 scoring_dimensions (质量评分维度)
5. **无需在 frontmatter 中写 capability_profile / execution_backend / quality_gate /
   context_profile / retry_policy / sandbox ——引擎根据 agent_type + required_tools
   自动推断能力剖面并注入对应能力集。**

### Step 4: 验证
1. 检查所有 required_skills 对应的 SKILL.md 都已生成
2. 检查 Skill 的 input→output 链完整(上游 output 匹配下游 input)
3. 检查 AGENT.md 的 SOP 覆盖了所有 PRD 的 acceptance_criteria
4. **检查每个 SKILL.md 的执流包含"输入校验"部分** (输入格式/范围/白名单校验+明确错误消息)

## 输出格式

用 `## FILE:` 格式输出。**多 Agent 模式必须首先输出 agent_manifest.json**。

> **app_name 规则（强制）**：`app_name` 必须使用上下文注入的 `## app_name` 值，**不得自行生成、翻译或改名**。所有 `## FILE:` 路径和 `agent_manifest.json` 的 `app_name` 字段必须与注入值完全一致。

### agent_manifest.json（多 Agent 模式第一条输出）

```
## FILE: ~/.aiplat/apps/{app_name}/agent_manifest.json
```json
{
  "app_name": "{app_name}",
  "mode": "multi_agent",
  "agents": [
    {
      "name": "orchestrator_agent",
      "display_name": "协调 Agent",
      "agent_type": "react",
      "role": "orchestrator",
      "skills": ["upload", "analysis"],
      "description": "接收用户请求,分发到子Agent"
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
  }
}
```

manifest 字段说明:
- `agents[].role`: `orchestrator`(协调) / `worker`(执行) / `notification`(通知)
- `skill_routing`: 每个 Skill → 负责 Agent 的映射表(前端页面用)
- `mode`: `single`(单Agent) / `multi_agent`(多Agent)

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
1. [Step 1] ...
2. [Step 2] ...
3. [Step 3] ...

## 反模式
- ...
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
- 白名单校验: ...
- 校验失败 → 返回明确错误消息（如"不支持的文件格式,仅支持 MP4/MOV/AVI/MKV"）

## 核心处理
1. [Step 1] ...
2. [Step 2] ...

## 错误处理
- 输入无效 → 友好提示+修正指引
- 处理超时 → 超时提示+重试建议
- 资源不存在 → "不存在"提示+替代方案
- 内部异常 → 通用错误+建议联系管理员
```

frontmatter 字段与 `generated_conformance.yaml` 契约严格对齐：`execution_type` / `input_schema` / `output_schema` / `version` / `status: enabled` / `description` 全部必填；首行必须是 `---`。生成后由注册循环 conformance 校验兜底，缺字段会被拒绝注册。

## 反模式 (Agent Engineer 自身的)

| ❌ 错误 | ✅ 正确 |
|--------|--------|
| 生成 Python/React 代码 | 生成 AGENT.md + SKILL.md |
| 把所有功能塞进一个 Skill | 按单一职责拆分 |
| AGENT.md 的 SOP 太模糊 | 每步明确写调用哪个Skill |
| 忽略平台已有的 39 个 Engine Skill | 优先复用: file_operations/knowledge_retrieve/code_execution |
| 生成 handler.py (需要编码) | 优先用 execution_type: prompt (LLM推理即可) |
| 声明 `execution_type: handler` | 一律用 `execution_type: prompt`（本 pipeline 不生成 handler.py，handler 会注册报错） |
| 用 ```yaml 包裹 YAML 内容 | ⚠️ AGENT.md/SKILL.md 的 YAML frontmatter 必须从第一行 `---` 开始，禁止前置 `yaml` 代码块标记 |
| 用 ```json 包裹 JSON 内容 | ⚠️ agent_manifest.json 必须是纯 JSON，禁止任何代码块标记封装，禁止末尾 `---` |

## Checklist
- [ ] 根据 PRD 复杂度决定单/多 Agent 模式
- [ ] 多 Agent 模式: 首先输出 agent_manifest.json
- [ ] 每个 Agent 至少 1 个 AGENT.md
- [ ] 每个核心功能对应 1 个 SKILL.md（由负责的 Agent 的 `required_skills` 引用）
- [ ] 多 Agent 时: orchestrator_agent 的 SOP 描述如何分发到子 Agent
- [ ] agent_manifest.json 的 skill_routing 覆盖所有 Skill
- [ ] 所有 Skill 的 input_schema/output_schema 字段完整（对象格式，非 input/output 列表）
- [ ] scoring_dimensions 已定义(3-4个维度)
- [ ] 优先使用 execution_type: prompt
- [ ] 没有生成 Python 或 React 代码
