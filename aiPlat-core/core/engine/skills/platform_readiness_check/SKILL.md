---
name: platform_readiness_check
display_name: 平台就绪检查
description: AI 平台上线前的 8 项系统级自检清单。覆盖工具访问、项目记忆、可观测性、失败归因、验证、权限、熵审计、干预记录。独立运行，不绑定任何 Agent。
category: governance
version: 1.0.0
status: enabled
execution_mode: prompt
permissions:
  - "audit:read"
  - "runs:read"
  - "evaluation:read"
  - "system:read"
effects:
  - type: read
    resources: ["database:execution_store"]
    idempotent: true
    rollback_available: false
input_schema: {}
output_schema:
  score:
    type: string
  checklist:
    type: array
  recommendations:
    type: array
---

## SOP

你是一个 AI 平台上线审计员。检查以下 8 项系统级能力。**不需要输入参数**——每项检查都是全局判断。

每项评分：✅ PASS / 🔶 WARN / ❌ FAIL

---

### 1. Tool Access（工具访问授权与限流）

检查：
- PolicyGate 是否启用（默认 deny-by-default）
- `sys_tool_call` 是否有 timeout 保护
- toolset 白名单机制是否存在

评分标准：
- PolicyGate + whitewash found → ✅
- PolicyGate but no toolset whitelist → 🔶
- No gate → ❌

---

### 2. Project Memory（项目记忆）

检查：
- MemoryManager 三层架构是否已实现
- `save_interaction` 是否在 loop.py 中调用
- `build_context` / `get_reminders` 是否在 loop.py 中接入
- `long_term_memories` SQLite 表是否存在

评分标准：
- 4 项 → ✅
- 2-3 项 → 🔶
- ≤1 项 → ❌

---

### 3. Observability（可观测性）

检查：
- `sys_llm_generate` / `sys_tool_call` / `sys_skill_call` 是否携带 trace_id + span_id
- ExecutionStore 是否持久化 syscall_events
- Diagnostics/Runs 是否有执行记录可查

评分标准：
- trace_id + span_id + events persisted → ✅
- trace_id only → 🔶
- No traces → ❌

---

### 4. Failure Attribution（失败归因）

检查：
- `failure_classifier.py` 是否存在分类逻辑
- `_last_action_reason` 是否在关键决策点写入
- DriftDetector 是否已激活

评分标准：
- 3 项 → ✅
- 2 项 → 🔶
- ≤1 项 → ❌

---

### 5. Verification（结果验证）

检查：
- EvaluationPolicy 是否配置了 scoring_dimensions
- regression_gate 是否接线
- RagEvaluator 的 RAG Triad 评分是否可用
- coverage_gate 是否存在

评分标准：
- 4 项 → ✅
- 2-3 项 → 🔶
- ≤1 项 → ❌

---

### 6. Permissions（权限校验）

检查：
- RBAC guard 是否在 HTTP 层做了身份注入
- PermissionManager deny-by-default 是否启用
- ApprovalGate 是否对写操作开启

评分标准：
- 3 项 → ✅
- 1-2 项 → 🔶
- 0 项 → ❌

---

### 7. Entropy Auditing（熵审计）

检查：
- `entropy_ledger` 表是否存在（DB migration v42）
- DriftDetector.record_entropy() 是否在 loop.py 中 auto-record
- 是否有未解决的 entropy 项

评分标准：
- table exists + auto-record → ✅
- table exists only → 🔶
- No table → ❌

---

### 8. Intervention Recording（干预记录）

检查：
- `_audit_hitl()` 是否存在
- approve/reject/review_gate 是否有审计日志
- change_control events 是否可查询

评分标准：
- audit + change_control → ✅
- audit only → 🔶
- No records → ❌

---

## Output Format

```json
{
  "score": "7/8",
  "overall": "PASS",
  "checklist": [
    {"id": 1, "name": "Tool Access", "result": "PASS", "detail": "PolicyGate enabled with deny-by-default"},
    {"id": 2, "name": "Project Memory", "result": "PASS", "detail": "MemoryManager wired (build_context + save_interaction)"},
    {"id": 3, "name": "Observability", "result": "PASS", "detail": "trace_id + span_id + events persisted"},
    {"id": 4, "name": "Failure Attribution", "result": "PASS", "detail": "failure_classifier + _last_action_reason + DriftDetector"},
    {"id": 5, "name": "Verification", "result": "PASS", "detail": "EvaluationPolicy + regression_gate + RagEvaluator + coverage_gate"},
    {"id": 6, "name": "Permissions", "result": "PASS", "detail": "RBAC + deny-by-default + ApprovalGate for writes"},
    {"id": 7, "name": "Entropy Auditing", "result": "PASS", "detail": "entropy_ledger table exists, DriftDetector auto-records"},
    {"id": 8, "name": "Intervention Recording", "result": "PASS", "detail": "_audit_hitl + change_control events"}
  ],
  "recommendations": []
}
```

---

## 使用

**不绑定任何 Agent**。在管理界面 → 诊断 → 工具 → 执行此 Skill：

```bash
curl -X POST http://localhost:8002/api/core/workspace/skills/platform_readiness_check/execute
```

或通过 Pipeline 的治理阶段自动调用。
