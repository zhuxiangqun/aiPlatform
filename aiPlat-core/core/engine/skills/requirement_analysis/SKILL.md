---
name: requirement_analysis
display_name: 需求分析
description: >-
  分析用户需求并输出结构化PRD JSON。触发条件：pipeline需求阶段。
  输出包含完整的functional_requirements/acceppance_criteria/user_stories。
category: analysis
version: 1.0.0
status: enabled
execution_mode: prompt
execution_type: prompt
triggers:
  - 需求分析
  - PRD
  - 需求文档
permissions:
- fs:read
effects:
- type: read
  resources:
  - filesystem:~
  idempotent: true
  rollback_available: true
input_schema:
  user_requirement:
    type: string
    required: true
    description: 用户的原始需求描述
output_schema:
  prd:
    type: object
    required: true
    description: 结构化PRD JSON
  markdown:
    type: string
    required: true
    description: 面向人阅读的Markdown版PRD
protected: true
idempotent: false
completion_criterion: |
  1. functional_requirements至少3条,每条包含acceptance_criteria
  2. user_stories覆盖所有核心功能
  3. constraints包含技术约束和非功能需求
keywords:
  objects:
  - PRD
  - 需求
  - 验收标准
  actions:
  - 分析
  - 生成
  - 输出
trigger_conditions:
- when: pipeline需求阶段
  query: 生成PRD/需求分析/输出PRD
skip_when: 已有完整PRD文档
---

# 需求分析（Engine）

根据用户需求描述，生成结构化 PRD JSON。

## SOP

### Step 1: 理解需求
1. 分析用户需求中的核心关键词（做什么、给谁用、有什么约束）
2. 如有对话历史，提取用户确认过的决策
3. 区分功能需求和非功能需求

### Step 2: 分解功能需求
为每个功能点:
1. 分配唯一ID（FR-001, FR-002...）
2. 写清楚名称和简短描述
3. 从用户需求和确认的细节中提取 **acceptance_criteria**（每条一个可验证的判断）
4. 标注优先级：`high`（核心路径）/ `standard`（重要）/ `low`（锦上添花）

**acceptance_criteria 必须具体可验证**:
- ❌ "功能正常" → ✅ "上传后返回 task_id，格式为 UUID"
- ❌ "体验良好" → ✅ "上传进度条实时更新，每 500ms 刷新"
- ❌ "支持多种格式" → ✅ "支持 MP4/MOV/AVI/MKV 四种格式"

### Step 3: 生成用户故事
1. 每个用户故事格式：`作为<角色>，我想要<能力>，以便<价值>`
2. 关联到具体的 functional_requirement ID
3. 至少覆盖所有 `high` 优先级需求

### Step 4: 汇总技术约束
1. 用户明确提到的技术限制（平台、语言、框架）
2. 非功能需求（性能、安全、可用性）
3. 如有对话历史中的决策记录，一并写入

### Step 5: 输出
1. **先输出 JSON**（紧凑格式，一行，不含 ``` 包裹）
2. 再输出 Markdown 版本（供人阅读）
3. JSON 必须是合法的 JSON 对象，前端会直接 parse

## 输出格式

**重要**: JSON 必须放在最前面，且必须是单行的合法 JSON（不需要 ``` 包裹）。
Markdown 在 JSON 之后，是给人看的版本。

### JSON（结构化）

```json
{
  "title": "项目名称",
  "description": "一句话概述",
  "functional_requirements": [
    {
      "id": "FR-001",
      "name": "功能名称",
      "description": "功能描述",
      "priority": "high|standard|low",
      "acceptance_criteria": [
        "可验证的验收条件1",
        "可验证的验收条件2"
      ]
    }
  ],
  "user_stories": [
    {
      "id": "US-001",
      "story": "作为<角色>，我想要<能力>，以便<价值>",
      "related_fr": ["FR-001"],
      "priority": "high|standard|low"
    }
  ],
  "constraints": {
    "platform": "Web|Mobile|Desktop",
    "languages": ["Python", "JavaScript"],
    "performance": ["100 QPS", "P95 < 500ms"],
    "security": ["HTTPS", "认证"],
    "other": ["其他约束"]
  }
}
```

### Markdown（人读）

```
## 项目名称
{title}

## 核心功能需求
### FR-001: {name}
{description}

验收标准:
- {AC1}
- {AC2}

## 目标用户
...

## 技术约束
...
```

## 反模式

| ❌ 错误 | ✅ 正确 |
|--------|--------|
| acceptance_criteria 写"功能正常" | 写"上传后返回 task_id，格式为 UUID" |
| 所有需求 priority 都写 high | 核心路径 high，其余按实际重要性 |
| 把技术实现细节写进需求 | 需求只说"做什么"，不说"怎么做" |
| 跳过对话历史中的决策 | 提取用户确认过的时间限制、并发量等 |
