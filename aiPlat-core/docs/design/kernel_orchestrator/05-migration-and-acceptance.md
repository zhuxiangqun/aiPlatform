# 05｜分期迁移与验收（Migration Plan & Acceptance）

状态：草案（已补齐“可执行验收口径”；冻结需 CI/集成测试跑通）  
更新时间：2026-04-16

---

## 1. 目标

- 以“可上线、可回滚、可验收”为核心，把内核化改造拆成可交付阶段
- Phase 1~3 保证“入口收敛 + 副作用封口 + 治理必经”且尽量不改变行为
- Phase 4~6 再逐步引入 prompt/context 收敛、多路径编排、自学闭环

---

## 1.5 验收方法与口径（必须可执行）

> 本节把“验收条款”落到可执行的检查方法，避免只写指标但无法复现。

### 1.5.1 静态验收（不可绕过）

以 `rg` 静态扫描作为冻结前置条件，口径详见：
- `docs/design/kernel_orchestrator/02-syscalls-and-gates.md` / 6.2（包含 allowlist/denylist）

冻结前置条件：
- 扫描结果为空（或仅包含显式豁免目录）

### 1.5.2 数据库验收（落库完整率、链路字段）

ExecutionStore 是 sqlite（db_path 由运行时配置决定）。下列 SQL 用于抽样或 CI 中做阈值检查：

```sql
-- agent 执行：trace_id 覆盖率
SELECT
  COUNT(1) AS total,
  SUM(CASE WHEN trace_id IS NULL OR trace_id='' THEN 1 ELSE 0 END) AS missing_trace
FROM agent_executions;

-- syscall_events：trace_id 覆盖率（用于替代“span 完整率”的近似指标）
SELECT
  COUNT(1) AS total,
  SUM(CASE WHEN trace_id IS NULL OR trace_id='' THEN 1 ELSE 0 END) AS missing_trace
FROM syscall_events;

-- approval_requests：pending 数量（用于验证审批链路是否可观测）
SELECT COUNT(1) AS pending
FROM approval_requests
WHERE status='pending';
```

推荐工具化：
- `scripts/kernel_metrics.py --db <db_path> --min-trace-coverage 0.99 --min-span-id-coverage 0.99`

> 注：Phase 3 起已支持 `syscall_events.span_id` 与 `spans` 表关联（schema v10）。因此可用 `span_id_coverage` 与 join 校验作为“span 完整率”的可执行指标。

### 1.5.3 API 验收（approval_required → approve → resume）

Phase 3.5 引入“可恢复执行”后，建议用 API 回归用例保证闭环不回归（见 2.4 / 3.5）。

也可用最小集成测试做“落库 + span 链路”验证：
```bash
pytest -q core/tests/integration/test_phase35_approval_resume_span.py
```

## 2. 分期计划（建议）

### Phase 1（P0）：单入口（Integration.execute）
**目标**：server 执行入口全部转发到 Kernel execute，不改业务行为。  
**主要改动**：
- 新增 `core/harness/integration.py::HarnessIntegration.execute`
- 修改 `core/server.py`：执行类 route 统一调用 execute
**验收**：
- 执行入口收敛：`core/server.py` 中执行类路由统一调用 `harness.execute(exec_req)`（代码审查 + grep）
- 运行时字段：agent/skill/graph/tool 的返回中包含 `run_id/trace_id`（集成测试覆盖）
- ExecutionStore：至少记录 request 元信息与最终状态（见 `agent_executions/skill_executions/graph_runs`）
**回滚**：
- **当前实现未提供 feature flag 级别回滚开关**（冻结前建议补齐：保留旧 handler 路由开关，或提供“旁路执行”用于紧急切回）

### Phase 2（P0）：syscalls 封口（llm/tool/skill）
**目标**：任何 LLM/Tool/Skill 的实际执行只能走 syscalls。  
**主要改动**：
- 新增 `core/harness/syscalls/*`
- Loop/Graph/SkillExecutor/ToolCalling 调用点改走 syscalls
**验收**：
- 主路径中绕过 syscalls 的调用点为 0（静态扫描，allowlist/denylist 见 02 文档）
- syscall 记录 span（哪怕 gate 先最小实现）
**回滚**：syscall 内部可暂时透传到旧实现

### Phase 3（P0）：四大 Gate 下沉 Kernel
**目标**：权限+审批 / trace / context budget / retry+fallback 成为必经设施。  
**主要改动**：
- 新增 `core/harness/infrastructure/gates/*`
- syscalls 与 execute 强制调用 gates
**验收**：
- Tool 调用：权限检查覆盖率 100%
  - 口径：所有 tool 调用都必须经 sys_tool（由 Phase 2 静态扫描保证）
- 审批命中可观测
  - 口径：触发审批时，`approval_requests` 表有记录，且 API `GET /approvals/pending` 可查询
- Trace：可执行指标（Phase 3）
  - 口径：`syscall_events.trace_id` 覆盖率 ≥ 99%（SQL 见 1.5.2）
- Resilience：最小策略（Phase 3）
  - 口径：syscalls 使用统一 timeout 包装；retry/fallback 策略在 Phase 5 统一落地
**回滚**：Gate 可按开关降级为“只记录不阻断”

### Phase 3.5（P0）：审批闭环与可恢复执行（Approval → Resume）
**目标**：approval_required 不再“崩溃/卡死”，而是可暂停、可批准、可续跑，并可审计回放。  
**主要改动**（As-Is 已落地示例）：
- `ApprovalManager` + ExecutionStore `approval_requests`
- `sys_tool` 标准化返回 `approval_required`（含 approval_request_id）
- Loop PAUSED + `loop_state_snapshot`
- API：`/approvals/*` 与 `/agents/executions/{execution_id}/resume`

**验收（API 用例示例）**：
1) 触发审批（需开启：`AIPLAT_SYSCALL_ENFORCE_APPROVAL=true`）
   - `POST /agents/{agent_id}/execute` → 返回 `status=approval_required` 且包含 `approval_request_id`
2) 审批通过
   - `POST /approvals/{approval_request_id}/approve`
3) 续跑
   - `POST /agents/executions/{execution_id}/resume` → 返回 `status=completed`（或继续 approval_required）
4) 审计聚合
   - `GET /approvals/{approval_request_id}` → 返回 related（agent_executions + syscall_events）

### Phase 4（P1）：ContextAssembler + PromptAssembler 收敛
**目标**：Loop/Graph 不再自行拼 prompt，上下文预算一致。  
**主要改动**：
- 新增 `core/harness/assembly/*`（PromptAssembler/ContextAssembler）
- sys_llm 通过 PromptAssembler 生成标准 messages + prompt_version（可通过环境变量 AIPLAT_ENABLE_PROMPT_ASSEMBLER 开关）
- 后续 Phase 4.1 起逐步引入 ContextAssembler 做预算/裁剪
**验收**：
- prompt_version 写入 ExecutionStore（通过 syscall_events.result.prompt_version 记录）
- ContextAssembler 已提供接口且被 syscalls/engines 使用（即使当前仅写 metadata）
- 回归测试（最小）：
  ```bash
  AIPLAT_ENABLE_PROMPT_ASSEMBLER=true pytest -q core/tests/integration/test_phase3_span_coverage.py
  ```
**回滚**：保留旧 prompt 拼装路径开关

### Phase 5（P1）：Orchestrator 引入（只产 plan）
**目标**：吸收 rangen_core 智能编排优势，多路径执行但不分叉。  
**主要改动**：
- 新增 `core/orchestration/*`
- EngineRouter + fallback 链
**验收**：
- plan explain/fallback_trace 可观测、可审计
- Orchestrator 层静态扫描：无副作用调用
**回滚**：Orchestrator 可降级为“固定 plan”（全部走 Loop）

最小回归（Phase 5.1：engine 元数据落库）：
```bash
pytest -q core/tests/integration/test_phase51_engine_metadata.py
```

最小回归（Phase 5.2：Orchestrator 只产 plan 并落库）：
```bash
AIPLAT_ENABLE_ORCHESTRATOR=true pytest -q core/tests/integration/test_phase52_orchestrator_plan.py
```

### Phase 6（P2）：自学闭环（受控演进）
**目标**：Evaluation + Feedback + Evolution 产生版本化改进并可灰度/回滚。  
**主要改动**：
- ExecutionStore/Trace 与 evaluation 打通
- evolution 产物版本化发布
**验收**：
- 任意学习产物可追溯 run 与指标
- 一键回滚可用

补充（Phase 6 占位实现口径）：
- ExecutionStore schema v11 新增 `learning_artifacts` 表（仅存储产物与关联关系；线上执行默认不依赖该表）。
- 每条 learning_artifact 必须包含：`kind/target_type/target_id/version/status/trace_id/run_id`，以保证可追溯。

最小回归（落库 roundtrip）：
```bash
pytest -q core/tests/integration/test_phase6_learning_artifacts_store.py
```

Phase 6.1（离线导入/产物生成）：
- 可使用 `scripts/learning_cli.py` 将 evaluation 结果（BenchmarkResult JSON）写入 learning_artifacts。
```bash
python3 scripts/learning_cli.py --db <db_path> create-eval-artifact \
  --target-type agent --target-id <agent_id> --version <version> --benchmark-json <bench.json>
python3 scripts/learning_cli.py --db <db_path> list --target-type agent --target-id <agent_id>
```

Phase 6.2（离线汇总在线执行反馈）：
- 将某次 agent run（agent_executions + syscall_events）汇总为 feedback_summary artifact：
```bash
python3 scripts/learning_cli.py --db <db_path> summarize-run --run-id <run_id> --version <version>
```

Phase 6.3（离线回归检测产物化）：
- 将 current/baseline benchmark JSON 对比生成 regression_report artifact：
```bash
python3 scripts/learning_cli.py --db <db_path> create-regression-artifact \
  --target-type agent --target-id <agent_id> --version <version> \
  --current-json <current.json> --baseline-json <baseline.json>
```

Phase 6.4（skill evolution lineage/version 产物化 + 回滚记录）：
- 将 SkillVersion JSON 写入 skill_evolution artifact：
```bash
python3 scripts/learning_cli.py --db <db_path> create-skill-version-artifact \
  --skill-version-json <skill_version.json> --version <artifact_version>
```
- 记录一次 skill rollback（仅记录，不执行回滚）：
```bash
python3 scripts/learning_cli.py --db <db_path> create-skill-rollback-artifact \
  --skill-id <skill_id> --from-version <from_v> --to-version <to_v> --version <artifact_version> --reason <reason>
```

Phase 6.5（受控自动记录：evolution/rollback → learning_artifacts）：
- 打开开关后，Skill EvolutionEngine 在触发演进成功/自动回滚时，会**仅记录**对应 learning_artifacts（不改变演进/回滚逻辑）：
  - skill_evolution（成功演进）
  - skill_rollback（回滚触发）
```bash
AIPLAT_RECORD_LEARNING_ARTIFACTS=true pytest -q core/tests/integration/test_phase65_evolution_engine_learning_artifacts.py
```

Phase 6.6（发布候选与回滚：仅改变产物状态，不改变线上行为）：
- 生成 release_candidate（引用一组 artifact_ids）：
```bash
python3 scripts/learning_cli.py --db <db_path> create-release-candidate \
  --target-type agent --target-id <agent_id> --version <rc_version> --artifact-ids <id1,id2,...> --summary <summary>
```
- 发布（可选审批）：第一次会返回 approval_request_id；approve 后带上 approval_request_id 再发布：
```bash
python3 scripts/learning_cli.py --db <db_path> publish-release --candidate-id <candidate_id> --user-id <user_id> --require-approval
python3 scripts/learning_cli.py --db <db_path> approve --approval-request-id <approval_request_id> --approved-by <reviewer> --comments <comments>
python3 scripts/learning_cli.py --db <db_path> publish-release --candidate-id <candidate_id> --user-id <user_id> --require-approval --approval-request-id <approval_request_id>
```
- 回滚（仅将 candidate + 引用 artifacts 标记为 rolled_back）：
```bash
python3 scripts/learning_cli.py --db <db_path> rollback-release --candidate-id <candidate_id> --reason <reason>
```

Phase 6.7（线上执行 metadata 注入：active release，可观测不改行为）：
- 开启开关后，HarnessIntegration 会在 agent 执行落库 metadata 中写入 active_release（来自已发布 release_candidate）：
```bash
AIPLAT_ENABLE_LEARNING_APPLIER=true pytest -q core/tests/integration/test_phase67_learning_applier_metadata.py
```

Phase 6.8（PromptRevision 应用：受控改行为，可回滚）：
- 需要同时开启：
  - AIPLAT_ENABLE_LEARNING_APPLIER=true（解析 active release）
  - AIPLAT_ENABLE_PROMPT_ASSEMBLER=true（统一 prompt 入口）
  - AIPLAT_APPLY_PROMPT_REVISIONS=true（真正应用 prompt_revision patch）
```bash
AIPLAT_ENABLE_LEARNING_APPLIER=true AIPLAT_ENABLE_PROMPT_ASSEMBLER=true AIPLAT_APPLY_PROMPT_REVISIONS=true \
  pytest -q core/tests/integration/test_phase68_prompt_revision_apply.py
```

Phase 6.9（PromptRevision 产物化 + 发布流水线）：
- 通过 CLI 创建 prompt_revision artifact（默认 draft）：
```bash
python3 scripts/learning_cli.py --db <db_path> create-prompt-revision-artifact \
  --target-type agent --target-id <agent_id> --version <pr_version> --prepend "<text>" --append "<text>"
```
- 将其纳入 release_candidate 并发布（publish 会把 candidate + 引用 artifacts 标记为 published）：
```bash
python3 scripts/learning_cli.py --db <db_path> create-release-candidate \
  --target-type agent --target-id <agent_id> --version <rc_version> --artifact-ids <pr_artifact_id> --summary "apply prompt"
python3 scripts/learning_cli.py --db <db_path> publish-release --candidate-id <candidate_id> --user-id <user_id>
```
- 最小回归（CLI→发布→运行时应用）：
```bash
pytest -q core/tests/integration/test_phase69_prompt_revision_cli_release_apply.py
```

Phase 6.10（PromptRevision 冲突检测/严格模式）：
- prompt_revision 可选 metadata：`exclusive_group`。同组内出现多个 revision 时：
  - 默认：仍合并应用，但会在 syscall_events 中记录 conflicts
  - 严格模式（AIPLAT_PROMPT_REVISION_STRICT=true）：同组仅保留第一个，其余记为 ignored
```bash
AIPLAT_PROMPT_REVISION_STRICT=true pytest -q core/tests/integration/test_phase610_prompt_revision_conflict_strict.py
```

Phase 6.11（PromptRevision priority 与合并顺序冻结）：
- 合并顺序冻结为：priority 降序，其次按 release_candidate 中 artifact_ids 的顺序（稳定可复现）。
- 严格模式下（AIPLAT_PROMPT_REVISION_STRICT=true）：同一 exclusive_group 仅保留 priority 最高者（tie 按 release 顺序）。
```bash
pytest -q core/tests/integration/test_phase611_prompt_revision_priority_strict.py
```

Phase 6.12（Execution metadata：落库 prompt revision audit）：
- 在执行落库的 agent_executions.metadata 中增加 `prompt_revision_audit`（聚合本次执行所有 LLM 调用的 applied/ignored/conflicts）：
```bash
pytest -q core/tests/integration/test_phase612_prompt_revision_audit_metadata.py
```

Phase 6.13（Trace/span 可观测：prompt revision 应用信息写入 span attributes）：
- sys.llm.generate span attributes 将包含 active_release、applied/ignored/conflicts 等字段，便于 trace 侧直接检索：
```bash
pytest -q core/tests/integration/test_phase613_trace_span_prompt_revision_attrs.py
```

Phase 6.14（Release TTL/过期自动回滚：离线执行）：
- publish-release 支持设置 TTL / expires_at（写入 release_candidate.metadata.expires_at）：
```bash
python3 scripts/learning_cli.py --db <db_path> publish-release --candidate-id <candidate_id> --user-id <user_id> --ttl-seconds 86400
```
- 通过 expire-releases 扫描并回滚已过期的 published release_candidate（仅改变 artifact 状态）：
```bash
python3 scripts/learning_cli.py --db <db_path> expire-releases
```
- 最小回归：
```bash
pytest -q core/tests/integration/test_phase614_release_expiry.py
```

Phase 6.15（基于线上指标的自动回滚：离线执行）：
- auto-rollback-metrics 会读取近期 agent_executions（metadata.active_release.candidate_id 匹配），计算 error_rate/avg_duration 并在超过阈值时触发 rollback（仅改变 artifacts 状态）：
```bash
python3 scripts/learning_cli.py --db <db_path> auto-rollback-metrics \
  --agent-id <agent_id> --error-rate-threshold 0.3 --min-samples 20 --window 200
```
- 最小回归：
```bash
pytest -q core/tests/integration/test_phase615_auto_rollback_metrics.py
```

Phase 6.16（回归检测式自动回滚：current vs baseline window）：
- auto-rollback-regression 会对比“当前候选版本窗口”和“基线窗口”的指标差值（默认 error_rate_delta），减少偶发波动误判：
```bash
python3 scripts/learning_cli.py --db <db_path> auto-rollback-regression \
  --agent-id <agent_id> --current-window 50 --baseline-window 50 --min-samples 20 --error-rate-delta-threshold 0.1
```
- 最小回归：
```bash
pytest -q core/tests/integration/test_phase616_auto_rollback_regression.py
```

Phase 6.17（baseline 自动选择升级：上一代 published candidate）：
- auto-rollback-regression 在未显式指定 --baseline-candidate-id 时，会默认选择“上一代 published release_candidate”（按 created_at 排序取当前 candidate 的前一个）；无可用则回退到 != current 的基线策略。
```bash
pytest -q core/tests/integration/test_phase617_auto_rollback_regression_prev_candidate.py
```

Phase 6.18（baseline 多级回退：上一代样本不足则递补更早 candidate）：
- auto-rollback-regression 会按 published candidates 的时间顺序向前尝试基线（rc-1 → rc-0 → ...），直到满足 min-samples；并在输出中返回 baseline_selection.tried 记录每次尝试的样本量。
```bash
pytest -q core/tests/integration/test_phase618_auto_rollback_regression_multilevel_baseline.py
```

Phase 6.19（回滚原因产物化：regression_report 决策产物）：
- 当 auto-rollback-regression 触发回滚时，会同时落库一个 regression_report artifact，记录 baseline_selection/指标差值/阈值/回滚原因，并在 candidate.metadata.rollback_regression_report_id 中建立关联。
```bash
pytest -q core/tests/integration/test_phase619_regression_report_artifact.py
```

Phase 6.20（回滚决策与 trace/run 关联：evidence 写入 regression_report）：
- auto-rollback-regression 生成的 regression_report 会：
  - trace_id：优先取 current window 中任一 execution 的 trace_id（无则退化）
  - run_id：自动生成 `auto-rollback-regression:<candidate_id>:<ts>`
  - payload.deltas.evidence：记录 current/baseline 的 execution_ids 与 trace_ids，便于从 trace/run 反查回滚原因
```bash
pytest -q core/tests/integration/test_phase620_regression_report_trace_run_link.py
```

Phase 6.21（从执行反查回滚决策：回写 regression_report_id 到 executions）：
- auto-rollback-regression 触发回滚时，会将 regression_report_id 写回 current window 的 agent_executions.metadata.regression_report_id，便于从任一失败执行直接定位到回滚决策产物。
```bash
pytest -q core/tests/integration/test_phase621_link_regression_report_to_executions.py
```

Phase 6.22（可选回写 baseline executions：link-baseline）：
- auto-rollback-regression 支持通过 `--link-baseline` 将 baseline window 的 executions 也回写 regression_report_id，便于从基线执行侧反查决策；同时 regression_report.payload.deltas.evidence 会记录 linked_*_execution_ids。
```bash
pytest -q core/tests/integration/test_phase622_link_baseline_executions.py
```

Phase 6.23（幂等与证据防膨胀：linked_* 去重与长度上限）：
- 对 executions 的回写是幂等的（相同 regression_report_id 会跳过）。
- regression_report.payload.deltas.evidence.linked_*_execution_ids 会做去重并限制最大长度（默认 200），避免重复更新导致膨胀。
```bash
pytest -q core/tests/integration/test_phase623_regression_report_evidence_cap.py
```

Phase 6.24（证据上限可配置：--max-linked-evidence + 截断标记）：
- auto-rollback-regression 支持 `--max-linked-evidence`（默认 200），并在输出与 regression_report.payload.deltas.evidence 中标记：
  - linked_evidence_cap
  - linked_current_truncated / linked_baseline_truncated
```bash
pytest -q core/tests/integration/test_phase624_configurable_evidence_cap.py
```

Phase 6.25（回滚审批门：先生成 report，再审批后回滚）：
- auto-rollback-regression 支持 `--require-approval`：
  - 第一次运行（不带 --approval-request-id）会创建 regression_report + approval_request，并返回 status=approval_required（不执行回滚）。
  - 审批通过后，再次运行并携带 `--approval-request-id` 才会执行回滚，并复用同一个 regression_report_id。
```bash
pytest -q core/tests/integration/test_phase625_rollback_approval_gate.py
```

Phase 6.26（清理过期回滚审批：cleanup-rollback-approvals）：
- 当候选版本已被回滚/不再处于 published 时，之前遗留的 pending `learning:rollback_release` 审批请求可以通过离线命令自动取消：
```bash
python3 scripts/learning_cli.py --db <db_path> cleanup-rollback-approvals
```
- 最小回归：
```bash
pytest -q core/tests/integration/test_phase626_cleanup_rollback_approvals.py
```

Phase 6.27（cleanup 分页扫描 + 过滤）：
- cleanup-rollback-approvals 支持分页扫描所有 pending（--page-size）并可选按 user_id / candidate_id 过滤：
```bash
python3 scripts/learning_cli.py --db <db_path> cleanup-rollback-approvals --page-size 500 --user-id <user> --candidate-id <candidate>
```
- 最小回归：
```bash
pytest -q core/tests/integration/test_phase627_cleanup_rollback_approvals_pagination_filters.py
```

Phase 6.22（可选链接 baseline executions：--link-baseline）：
- auto-rollback-regression 增加 --link-baseline：除 current window 外，也将 baseline window 的 agent_executions.metadata 回写 regression_report_id。
- 同时会将回写的 execution_id 列表写回到 regression_report.payload.deltas.evidence.linked_* 字段。
```bash
pytest -q core/tests/integration/test_phase622_link_baseline_executions.py
```

---

## 3. 验收指标（建议量化）

### 3.1 覆盖率
- syscall 覆盖率：LLM/Tool/Skill 调用 100% 经 syscalls
- Gate 覆盖率：所有 tool_call 100% 经 PolicyGate/TraceGate/ResilienceGate

### 3.2 可观测性
- trace：Phase 3 用 `syscall_events.trace_id` 覆盖率近似（≥ 99%）；Phase 4+ 补齐真正 span 统计
- 执行落库完整率 ≥ 99%（需给出“分母口径”：例如每次 agent execute 视为一次执行）

### 3.3 安全与合规
- 绕过治理的调用点 = 0（CI 静态扫描，见 02 文档）
- 审批命中可回放：approval_required 状态可重放/可恢复（Phase 1 可先返回 pending）

### 3.4 稳定性
- 关键路径 p95 时延回归 ≤ X%（待基线测量后填）
- 工具失败回退成功率 ≥ Y%（待定义）

---

## 4. 回归测试策略（建议）

- 单元测试：
  - syscalls（权限/审批/trace/重试）
  - gates（决策输出、落库字段）
  - PromptAssembler（模板版本与变量校验）
- 集成测试：
  - agent execute 主链路（loop-first）
  - graph 执行（langgraph engine）与 fallback
  - approval_required 流程
- 回放测试：
  - 选取固定执行记录（golden runs）对比输出与审计字段

---

## 5. 风险与缓解

- 行为漂移：Phase 1~3 不改策略，只加封装与观测；Phase 4 引入模板版本灰度
- 分叉回归：CI 静态扫描 + syscall 封口
- 性能回归：Gate 轻量化；重计算异步/分级；关键路径缓存

---

## 6. 评审检查清单

- [ ] 每期改动点是否可独立上线与回滚？
- [ ] 验收指标是否可量化、可观测？
- [ ] 回归测试是否覆盖“不可绕过”与“可回放”？
