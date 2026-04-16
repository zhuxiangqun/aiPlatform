# 审查报告变更日志（持续交付｜历史记录）

> **历史报告**：本文件用于记录审计产物的变更历史，不作为“当前实现能力”的唯一依据；设计真值以代码事实与最新测试结果为准。

> 规则：
> 1. `reports/audit_findings.json` 是唯一结构化事实源；`reports/aiPlat_设计文档与实现一致性审查报告.docx` 必须由生成器从 JSON 自动生成。
> 2. 每次修复/调整判定后，必须同时更新：① JSON 对应条目字段（status/fix/verification/updated_at）② 本日志追加一条记录 ③ 重新生成 docx。

## 变更记录

### 2026-04-15
- 初始化：生成首版 `audit_findings.json` 与 docx 审查报告；建立持续交付框架（schema/生成器/日志）。
- P0 修复：
  - TOOL-PERM-001：修复 PermissionManager 数据结构污染（移除 user_id:tool 的无意义写入），新增单测验证。
  - SKILL-FORK-001：修复 SkillExecutor fork 模式（改用 create_conversational_agent + AgentConfig；无 model 时返回清晰错误），新增单测验证。
- P1 修复：
  - SKILL-VERSION-API-001：修复 Skill 版本查询 API 返回空 config，改为返回真实可序列化 SkillConfig，并新增单测验证。
  - TOOL-DOC-IMPL-001：补齐 BaseTool._call_with_tracking 与 ToolRegistry 注入点，CalculatorTool 接入封装，并新增单测验证。
- P2 修复：
  - AGENT-EXEC-001：清理 ReActAgent 旧推理循环死代码，统一为 Loop 驱动执行路径。
  - HARN-COORD-001：实现第 6 种协作模式 Hierarchical Delegation，并更新工厂映射/MultiAgent 映射与文档。
  - HARN-COORD-002：明确 Pattern 契约 execute(task: str) 并加入 TypeError 保护与单测。
  - HARN-CONV-001：ConvergenceDetector 接入 LangGraph MultiAgentGraph（修复 evaluate 链路与状态初始化），并新增单测验证。
- 文档治理：
  - DOC-STATUS-001：为 ARCHITECTURE_STATUS.md 增加可追溯断言规则与证据字段，并消除与近期修复项相关的矛盾表述。

### 2026-04-16
- Round5：全仓文档（core/docs、infra/docs、reports）口径收敛：补齐 As-Is/To-Be 与 Evidence Index，修复路径/引用错误，并生成 Round5 审计产物。
- Round6：
  - CORE-EXECSTORE-001：新增 SQLite ExecutionStore 替代 server 进程内执行历史存储，接线到 API 查询端点并补齐 unit+integration 测试；生成 Round6 审计产物。
- Round7：
  - CORE-TOOLCALL-001：新增统一结构化工具调用解析器（JSON 优先、ACTION 兜底），接线 ReActLoop 与 LangGraph ActNode，并补齐单测与审计产物。
- Round8：
  - CORE-ROUTING-001：消除 Skill/Tool substring 误触发：新增 parse_action_call（显式 skill 调用），ReActLoop/PlanExecuteLoop 移除 substring 路由，并补齐回归测试与审计产物。
- Round9：
  - CORE-EXECSTORE-EXT-001：ExecutionStore 增加 schema 迁移机制、retention 清理策略与 env 配置；新增 graph_runs/graph_checkpoints 并接线 LangGraph callbacks 落库；补齐单测与审计产物。
- Round10：
  - CORE-TRACESTORE-001：ExecutionStore schema 升级 v3（traces/spans），TraceService 支持持久化后端并新增 tracer 适配；提供 /traces 与 graph run/checkpoints 查询 API；补齐 unit+integration 测试与审计产物。
- Round11：
  - CORE-RESUME-001：ExecutionStore schema 升级 v4（graph run 恢复链路 + execution↔trace 关联）；CompiledGraph 支持从 current_node 继续执行；新增 checkpoint 查询与 resume API；补齐 unit+integration 测试与审计产物。
- Round12：
  - CORE-RESUME-EXEC-001：补齐 CallbackManager.register_global 修复 callbacks 落库接线，并新增 CompiledGraph-based ReAct + resume/execute API，形成 resume→execute→落库 最小闭环；补齐集成测试与审计产物。
- Round13：
  - CORE-CLOSELOOP-001：将闭环推广到 ReActGraph/LangGraphExecutor（默认走内部 CompiledGraph），补齐 execution↔trace 联查 API，并强化 resume 幂等与权限校验；更新审计产物。
