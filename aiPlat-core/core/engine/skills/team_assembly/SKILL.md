---
name: team_assembly
display_name: 团队组装
description: 分析PRD→能力匹配→Agent选择→拓扑排序→输出完整pipeline stages
category: orchestration
version: 1.0.0
status: enabled
execution_type: prompt
execution_backend: agent
input_schema:
  prd:
    type: object
    required: true
    description: 结构化PRD(functional_requirements/user_stories/constraints)
  agent_catalog:
    type: array
    required: false
    description: 可用Agent列表(不传则自动扫描~/.aiplat/agents/)
output_schema:
  stages:
    type: array
    required: true
    description: 带order的stage列表(拓扑排序已完成)
triggers:
  - 组建团队
  - 推荐团队
  - 编排流水线
effects:
  - type: read
    resources: ["filesystem:~/.aiplat/agents"]
    idempotent: true
    rollback_available: false
---

# 团队组装 (Team Assembly)

分析PRD中的功能需求，从Agent Catalog中匹配合适的Agent，通过`depends_on`声明做依赖拓扑排序，输出完整的pipeline stages配置。

## SOP

### Step 1: 能力需求提取
从 `functional_requirements` 推断需要的阶段能力：
- FR中含"测试/验证/质量检验" → 需要 test_executor
- FR中含"部署/发布/上线" → 需要 deploy_agent
- FR中含"数据清洗/分析/报告" → 需要 data_agent
- 基础阶段总是需要: pm_agent, architect_agent, agent_engineer, frontend_developer

### Step 2: Agent匹配
对每个能力，在agent_catalog中查找：
```
agent.skills ∩ required_capabilities ≠ ∅ → 匹配
```

优先级规则：
- 精确匹配（agent.phase 匹配能力关键词）> 模糊匹配
- `execution_backend: agent` 的agent优先用于复杂任务
- 同一能力最多匹配1个agent（去重）

### Step 3: 依赖拓扑排序
调用 `_topological_order(stages)`：
- 读取每个stage的 `depends_on` 声明
- Kahn算法建DAG → 分配order
- depends_on可引用agent_id或output_artifact名
- 同一order的stage可并行执行（FanOut模式）

### Step 4: 配置注入
对每个stage调用 `_enrich_stage_from_agent()`：
- 从AGENT.md自动填充execution_backend/skill_name/required_skills等
- 已在YAML中显式声明的字段保留

### Step 5: 输出
返回带order的完整stages数组，human-readable reasoning说明每个stage的选择理由。

## 反模式
- ❌ 硬编码order值 → 应通过depends_on拓扑计算
- ❌ 跳过能力需求提取 → 直接返回所有agent
- ❌ 忽略depends_on声明 → 导致阶段顺序错误
- ✅ 根据PRD功能需求精确匹配Agent
- ✅ depends_on拓扑排序自动分配order
- ✅ _enrich_stage_from_agent()自动补全配置字段
