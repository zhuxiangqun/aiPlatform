---
name: agent_readiness_check
display_name: Agent 上线检查
description: 单个 Agent 上线前的 3 项自检清单（任务规格、上下文选择、任务状态）。适用于 Pipeline QA 阶段自动审计。
category: governance
version: 1.0.0
status: enabled
execution_mode: prompt
permissions:
  - "agent:read"
  - "pipeline:read"
effects:
  - type: read
    resources: ["filesystem:~/.aiplat", "database:execution_store"]
    idempotent: true
    rollback_available: false
input_schema:
  agent_id:
    type: string
    required: true
    description: 要检查的 Agent ID
output_schema:
  score:
    type: string
  checklist:
    type: array
  recommendations:
    type: array
---

## SOP

你是一个 Agent 上线审查员。对目标 Agent，按以下 3 项 Agent 级清单检查。

每项评分：✅ PASS / 🔶 WARN / ❌ FAIL

---

### 1. Task Specification（任务规格）

检查 AGENT.md frontmatter：
- `agent_type` 是否定义
- `skills` / `tools` 是否限定范围（非空列表）
- `model` 是否配置
- `phase` 是否在 Pipeline 中有明确定位

评分标准：
- 4 项齐全 → ✅
- 缺 1-2 项 → 🔶（建议补齐）
- 缺 3 项以上 → ❌

### 2. Context Selection（上下文选择）

检查 Agent 上下文策略：
- `token_budget` 是否在 Pipeline 或 AGENT.md 中配置
- ContextAssembler 的 5 级压缩是否已在 loop.py 中启用
- CLAUDE.md 是否作为系统提示注入（永不压缩）

评分标准：
- token_budget 配置 + 压缩启用 → ✅
- 只有 token_budget → 🔶
- 无上下文限制 → ❌

### 3. Task State（任务状态）

检查 Agent 的 Pipeline checkpoint：
- Pipeline checkpoint 机制是否启用
- `_snapshot()` 是否在 pipeline_engine 中
- `_load_checkpoints_from_disk()` 是否存在
- crash recovery 测试是否通过过

评分标准：
- checkpoint 启用 + snapshot 存在 → ✅
- checkpoint only → 🔶
- 无 → ❌

---

## Output Format

```json
{
  "agent_id": "...",
  "score": "2/3",
  "overall": "WARN",
  "checklist": [
    {"id": 1, "name": "Task Specification", "result": "PASS", "detail": "agent_type=conversational, skills=[test_case_generation], model=deepseek-chat"},
    {"id": 2, "name": "Context Selection", "result": "WARN", "detail": "token_budget not configured in AGENT.md", "suggestion": "添加 token_budget: 50000 到 AGENT.md frontmatter"},
    {"id": 3, "name": "Task State", "result": "PASS", "detail": "Pipeline checkpoint enabled, _snapshot() present"}
  ],
  "recommendations": [
    "第2项: 在 AGENT.md 中添加 token_budget 配置"
  ]
}
```

---

## 使用

绑定到 QA Agent：
```yaml
required_skills: [..., agent_readiness_check]
```

Pipeline QA 阶段 → `sys_skill_call("agent_readiness_check", {agent_id: "xxx"})` → 输出 3 项检查清单。
