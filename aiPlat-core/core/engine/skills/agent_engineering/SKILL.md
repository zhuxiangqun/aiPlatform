---
name: agent_engineering
display_name: Agent 工程
description: >-
  根据PRD和架构设计,将应用需求分解为Agent和多个Skill的Agent模型应用。
  输出AGENT.md和多个SKILL.md文件。
category: generation
version: 1.0.0
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

用 `## FILE:` 格式输出，每个文件一个代码块:

```
## FILE: ~/.aiplat/agents/{agent_name}/AGENT.md
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
- [ ] 至少生成 1 个 AGENT.md
- [ ] 每个核心功能对应 1 个 SKILL.md
- [ ] 所有 Skill 的 input/output 字段完整
- [ ] AGENT.md 的 SOP 引用所有 Skills
- [ ] scoring_dimensions 已定义(3-4个维度)
- [ ] 优先使用 execution_type: prompt
- [ ] 没有生成 Python 或 React 代码
