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
  3. SKILL.md的input/output字段能串联
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
2. 确定 Agent 的 `agent_type`:
   - `conversational` — 对话式交互(默认)
   - `react` — 需要工具调用的复杂任务
   - `rag` — 以知识检索为主
3. 确定 Agent 的显示名和描述

### Step 2: 分解功能为 Skills
对 PRD 的每个 `functional_requirement`:
1. 判断是独立的能力单元还是内部步骤
2. 独立能力 → 生成 SKILL.md
3. 判断 `execution_type`:
   - `prompt` — LLM 推理即可(默认,无需编写代码)
   - `handler` — 需要实际执行代码(如调用外部API)

**Skill 拆分原则**:
- 一个 Skill 做一件事(单一职责)
- input/output 字段要明确(类型+必填标记)
- 所有 Skill 的 input/output 能串联成完整链路
- 优先复用平台已有的 Engine Skill(39个),不重复造

### Step 3: 生成 AGENT.md
1. 写入 frontmatter (agent_type, required_skills, required_tools)
2. 写入 SOP: 描述用户对话→调用哪个Skill→得到什么结果→如何反馈
3. 写入反模式 (常见错误+修正)
4. 写入 scoring_dimensions (质量评分维度)

### Step 4: 验证
1. 检查所有 required_skills 对应的 SKILL.md 都已生成
2. 检查 Skill 的 input→output 链完整(上游 output 匹配下游 input)
3. 检查 AGENT.md 的 SOP 覆盖了所有 PRD 的 acceptance_criteria

## 输出格式

用 `## FILE:` 格式输出。**多 Agent 模式必须首先输出 agent_manifest.json**。

### agent_manifest.json（多 Agent 模式第一条输出）

```
## FILE: ~/.aiplat/apps/{app_name}/agent_manifest.json
```json
{
  "app_name": "video_sense",
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

## 反模式 (Agent Engineer 自身的)

| ❌ 错误 | ✅ 正确 |
|--------|--------|
| 生成 Python/React 代码 | 生成 AGENT.md + SKILL.md |
| 把所有功能塞进一个 Skill | 按单一职责拆分 |
| AGENT.md 的 SOP 太模糊 | 每步明确写调用哪个Skill |
| 忽略平台已有的 39 个 Engine Skill | 优先复用: file_operations/knowledge_retrieve/code_execution |
| 生成 handler.py (需要编码) | 优先用 execution_type: prompt (LLM推理即可) |

## Checklist
- [ ] 根据 PRD 复杂度决定单/多 Agent 模式
- [ ] 多 Agent 模式: 首先输出 agent_manifest.json
- [ ] 每个 Agent 至少 1 个 AGENT.md
- [ ] 每个核心功能对应 1 个 SKILL.md（由负责的 Agent 的 `required_skills` 引用）
- [ ] 多 Agent 时: orchestrator_agent 的 SOP 描述如何分发到子 Agent
- [ ] agent_manifest.json 的 skill_routing 覆盖所有 Skill
- [ ] 所有 Skill 的 input/output 字段完整
- [ ] scoring_dimensions 已定义(3-4个维度)
- [ ] 优先使用 execution_type: prompt
- [ ] 没有生成 Python 或 React 代码
