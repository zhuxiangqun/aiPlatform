---
name: production_readiness_check
display_name: 生产就绪检查
description: AI Agent 上线前的 11 项自检清单。检查输入侧、动作侧、观察侧、验收侧、治理侧五个维度，确保 Agent 在生产环境中安全可靠。
category: governance
version: 1.0.0
status: enabled
execution_mode: prompt
permissions:
  - "audit:read"
  - "runs:read"
  - "evaluation:read"
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
  project_id:
    type: string
    description: 关联的 Builder 项目 ID（可选）
output_schema:
  checklist:
    type: array
    description: 11项检查结果
  overall:
    type: string
    description: PASS/FAIL/WARN
  recommendations:
    type: array
    description: 修复建议
---

## SOP

你是一个 AI Agent 生产就绪审查员。根据以下 11 项清单，对目标 Agent 进行逐项检查。

每项检查按以下标准评分：
- ✅ PASS：该维度覆盖完整，风险可控
- 🔶 WARN：有基础能力但缺少防护，建议改进
- ❌ FAIL：缺失关键能力，禁止上线

---

### 一、输入侧：定义任务与上下文

**1. Task Specification（任务规格）**
- 检查 AGENT.md frontmatter 是否定义了 agent_type、skills、tools、model
- 检查 PipelineStageConfig 是否配置了 input_artifacts、output_artifact、phase
- 风险：Agent 行为边界不清晰，可能执行超出预期的操作
- 判断标准：AGENT.md 有 agent_type + skills/tools → ✅；只有 agent_type → 🔶；无 → ❌

**2. Context Selection（上下文选择）**
- 检查 ContextAssembler 的 5 级压缩是否启用
- 检查 CLAUDE.md 是否作为系统提示注入（永不压缩）
- 检查 token_budget 是否在 AGENT.md 中配置
- 风险：上下文噪音太多导致 token 浪费，或关键信息被裁剪导致回答不准确
- 判断标准：token_budget 已设 + CLAUDE.md 存在 → ✅；只有其1 → 🔶；无 → ❌

### 二、动作侧：执行与状态管理

**3. Tool Access（工具访问授权）**
- 检查 Agent 的 tools 列表是否限定了可调用范围
- 检查 PolicyGate 是否启用（默认 deny-by-default）
- 检查 sys_tool_call 通道是否有 timeout 保护
- 风险：无策略工具调用，Agent 可能执行危险操作（写文件、执行命令）
- 判断标准：tools 限定 + PolicyGate enabled → ✅；tools 限定但无 gate → 🔶；全量 tools → ❌

**4. Project Memory（项目记忆）**
- 检查 MemoryManager 是否在执行循环中被调用
- 检查 save_interaction 是否在 loop.py 中接入
- 检查 long_term_memories 表是否已初始化
- 风险：跨 session 记忆丢失，Agent 每次启动都"失忆"
- 判断标准：MemoryManager wired + SQLite table exists → ✅；wired 但无表 → 🔶；未 wired → ❌

**5. Task State（任务状态）**
- 检查 Pipeline checkpoint 机制是否启用
- 检查 _snapshot() 和 _load_checkpoints_from_disk() 是否存在
- 检查 crash recovery 是否经过测试
- 风险：context reset 或进程重启导致长时间任务中断
- 判断标准：checkpoint enabled + snapshot works → ✅；checkpoint only → 🔶；无 → ❌

### 三、观察侧：可观测与归因

**6. Observability（可观测性）**
- 检查 sys_llm_generate / sys_tool_call / sys_skill_call 是否携带 trace_id
- 检查 ExecutionStore 是否持久化所有 syscall_events
- 检查 Diagnostics/Runs 页面是否能查询到执行记录
- 风险：Agent 黑盒执行，出问题无法排查
- 判断标准：trace_id + span_id + events persisted → ✅；缺1项 → 🔶；全无 → ❌

**7. Failure Attribution（失败归因）**
- 检查 _last_action_reason 是否在关键决策点写入
- 检查 failure_classifier 是否能区分模型错误/工具错误/上下文错误
- 检查 DriftDetector 是否已激活
- 风险：失败后不知原因，反复重试浪费资源
- 判断标准：3项全覆盖 → ✅；2项 → 🔶；不足2项 → ❌

### 四、验收侧：验证与权限

**8. Verification（结果验证）**
- 检查 EvaluationPolicy 是否配置了 scoring_dimensions
- 检查 regression_gate 是否在 CI 中接线
- 检查 RagEvaluator 的 RAG Triad 评分是否在 pipeline 中执行
- 风险：危险路径产出的结果未经验证直接输出
- 判断标准：scoring + regression_gate wired → ✅；scoring only → 🔶；无 → ❌

**9. Permissions（权限校验）**
- 检查 RBAC guard 是否在 HTTP 层做了身份注入
- 检查 PermissionManager deny-by-default 策略是否启用
- 检查审批门禁（ApprovalGate）是否对写操作开启
- 风险：无权限控制的 Agent 可能越权操作资源
- 判断标准：RBAC + deny-by-default → ✅；RBAC only → 🔶；无 → ❌

### 五、治理侧：熵审计与干预记录

**10. Entropy Auditing（熵审计）**
- 检查 entropy_ledger 表是否存在
- 检查 DriftDetector 的 drift 记录是否数量化管理
- 检查是否有技术债累积告警
- 风险：小 drift 积累成不可维护的大问题
- 判断标准：entropy_ledger exists + drift counted → ✅；drift detected but not stored → 🔶；无追踪 → ❌

**11. Intervention Recording（干预记录）**
- 检查 HITL 审批是否有审计日志（_audit_hitl）
- 检查 approve/reject/review_gate 是否记录在案
- 检查 change_control events 是否可查询
- 风险：人工干预无记录，合规审查无依据
- 判断标准：audit + change_control wired → ✅；audit only → 🔶；无 → ❌

---

## Output Format

```json
{
  "checklist": [
    {"id": 1, "name": "Task Specification", "result": "PASS", "detail": "...", "suggestion": null},
    {"id": 2, "name": "Context Selection", "result": "WARN", "detail": "...", "suggestion": "建议添加 CLAUDE.md"}
  ],
  "overall": "PASS",
  "score": "10/11",
  "recommendations": [
    "第2项: 添加 CLAUDE.md 作为永不压缩的系统提示",
    "第10项: entropy_ledger 表已创建但无历史数据，运行一次全量 drift 扫描"
  ]
}
```

---

## 使用方式

在 Pipeline 中绑定此 Skill，每次发布前自动运行：
```yaml
stage:
  agent_id: auditor
  skills: [production_readiness_check]
  input_artifacts: [prd, architecture, code, test_report]
```

也可以在管理界面通过 Execute Agent 手动触发检查。
