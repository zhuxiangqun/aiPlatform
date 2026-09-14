# FDE 工作台演进完整方案（控制台 + 执行核）

| 字段 | 值 |
|------|-----|
| 版本 | **v1.1+**（方案稿，**非实施清单强制开工令**） |
| 日期 | 2026-09-14 |
| 状态 | 待评审 / 待排期 → **Phase 0–5 于 2026-09-14 竖切闭环**（见决策记录 / 契约勾选） |
| 安全方案 | security_view / security_review Phase A/B/C（已有实现基线） |

### 关联契约清单（状态）

| 文档 | 状态 | 作用 |
|------|------|------|
| [`docs/contracts/FDE_WORKBENCH_CONTRACT.md`](../../contracts/FDE_WORKBENCH_CONTRACT.md) | **已有 / 待评审** | 控制台边界、两类 Action、否定清单 |
| [`aiPlat-core/core/harness/schemas/audit_schema.v1.yaml`](../../../aiPlat-core/core/harness/schemas/audit_schema.v1.yaml) | **已有 / Phase 1 冻语义** | 审计字段、Eval 门、变更面白名单 |
| [`docs/contracts/FDE_GUARD_REGISTRY_LANDING.md`](../../contracts/FDE_GUARD_REGISTRY_LANDING.md) | **已有 v1.1（盘点已填） / 待评审** | 接到现有 guard / Registry / ActionStore |
| [`docs/contracts/domain_literals_scan.md`](../../contracts/domain_literals_scan.md) | **v1.1 · Phase 5 关闭（error）** | Domain 字面量；行为分叉=0 |
| [`docs/contracts/FDE_DECISION_RECORD.md`](../../contracts/FDE_DECISION_RECORD.md) | **v1.3 · D2/D5 关闭** | 六问决议追踪 |
| [`docs/contracts/action_branch_scan.md`](../../contracts/action_branch_scan.md) | **v0.2（硬违规≈0；P8 已签）** | Action 分支存量 |
| [`docs/contracts/FDE_WORKBENCH_GUARD_AND_AUDIT_MAPPING.md`](../../contracts/FDE_WORKBENCH_GUARD_AND_AUDIT_MAPPING.md) | **v0.5** | 否定清单矩阵 + 路径强制 + 映射验收 |
| [`docs/contracts/FDE_PHASE0_KICKOFF_CHECKLIST.md`](../../contracts/FDE_PHASE0_KICKOFF_CHECKLIST.md) | **v1 · 已宣布开工 2026-09-14** | 勾完即开工 |
| [`docs/contracts/FDE_PHASE5_CUSTOMER_ONBOARDING.md`](../../contracts/FDE_PHASE5_CUSTOMER_ONBOARDING.md) | **v1.0 · Phase 5** | 新客户配置驱动接入 |
| Pipeline 挂起/恢复 | **已有代码，非独立契约文件** | `pipeline_engine.py` / `pipeline_stage.py` / `stage_handoff.py` |
| Action 审批存储 | **已有** | `ActionStore.pending_approvals`（无独立 ApprovalStore 文件名） |

---

## 0. 方案定位（先读）

### 0.1 一句话

把 FDE 工作台从「工具集合 / 半真半假进度条」演进为：**现场工程师控制台 + 工厂执行核**；人做决策，Agent 在护栏内执行；复用工厂、ActionRegistry、Ontology、Eval，**不另起 IDE，不另起执行栈**。

### 0.2 本文件是什么 / 不是什么

| 是 | 不是 |
|----|------|
| 方向、阶段、验收、风险、与安全方案的映射 | 本周必须合入的 PR 任务单 |
| 工程契约与度量定义的总览 | 立即大规模改 harness / 前端的实施 diff |
| 排期与决策点（Go / No-Go） | 推倒重做 Builder 或新建第二套 ActionRegistry |

**原则：先冻结方案与契约，再按 Phase 开工；未评审通过前，默认不改程序。**

### 0.3 总判断（现状）

| 维度 | 判断 |
|------|------|
| 与文章路径（FDE→Ontology→Agent→AI FDE→Fleet） | **部分符合**：前三步有基础，第四步未真闭环，Fleet 未展开 |
| 工作台定位 | 已有 `/diagnostics/fde` 与多 Tab，但易滑向「第二个 Builder」 |
| 最短路径 | **不要推倒重做**；诚实化 → 跑真 `fde_delivery_v1` → lock-service 竖切 Action 写回 |
| 安全汇合点 | FDE Phase 4A ↔ security Phase B/C |

---

## 1. 目标与非目标

### 1.1 目标

1. **控制台清晰**：选客户、看运行态、批 Action、盯 KPI/告警；刷新后状态与服务端一致。
2. **执行核唯一**：交付走契约化 Pipeline；客户运营写回走 ActionRegistry + PolicyGate + 审计。
3. **两类 Action 边界可治理**：`customer_action:*` vs `platform_action:*`（权限、审计、回滚、Eval 不同）。
4. **域解析收敛**：DomainRouter 为唯一入口；harness 禁止业务域名字面量行为分叉。
5. **可演示竖切**：lock-service「工单 → 提议 → 人批 → 状态迁移 → 证据 → KPI」。
6. **与安全方案同语义**：上线前检查复用 security_review，不发明第二套 severity。

### 1.2 非目标（明确不做）

1. 工作台内嵌代码编辑器 / 文件树 / 调试器 / 自由多 Agent 编排。
2. 新建平行 `architecture_guard` 或平行 `ActionRegistry` 包（接到现有引擎）。
3. Phase 2 前铺开多客户 / Agent Fleet。
4. Phase 4 前开放「Agent 任意改配置 / 写库」。
5. 用 LLM 断言替代物理证据进入 security `confirmed`。

---

## 2. 架构原则（一等公民）

### 2.1 分层

```
┌─────────────────────────────────────────────────────────┐
│  FDE 工作台（控制台）                                      │
│  客户上下文 · Pipeline 观测 · Action 审批 · KPI/Eval       │
│  入口: /diagnostics/fde → /api/platform/apps/fde/*         │
└──────────────────────────┬──────────────────────────────┘
                           │ 仅经 CoreFacade
┌──────────────────────────▼──────────────────────────────┐
│  执行核                                                   │
│  PipelineEngine（交付） · AsyncActionRegistry（运营写回）   │
│  PolicyGate · HITL · ActionStore 审计 · Eval 门            │
└──────────────────────────┬──────────────────────────────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    fde-delivery     客户域 Ontology    security_review
    （平台跟踪元层）   （如 lock-service）  （Phase A/B/C）
```

### 2.2 两类 Action（必须升格为架构原则）

| | 客户运营 `customer_action:` | 平台诊断 `platform_action:` |
|--|--|--|
| 影响面 | 客户业务数据（合同责任） | 平台自身状态（可重建） |
| 示例 | `customer_action:lock-service:accept_order` | `platform_action:fde-delivery:field_assessment` |
| 默认 | Agent 提议 + 人审批；高风险 HITL(+admin MFA) | 人可直接执行；HITL 按策略 |
| 审计 | 永久；完整前后快照 + 审批者 | 按平台保留策略 |
| 回滚 | 必须有补偿/回滚或显式 irreversible | 不强制 |
| Eval | `customer_action_safety`（全过+人审+可复用安全结果） | `platform_action_health`（可阈值门） |
| UI | 运营动作卡 / 独立审批与审计视图 | 诊断/移交面板，视觉区分 |

### 2.3 DomainRouter

- **唯一**客户域解析入口。
- harness 禁止以 `"lock-service"` / `"fde-delivery"` 等字面量做行为分叉（常量白名单与 DomainRouter 调用参数除外）。
- 前端行业映射不得绕过后端 DomainRouter 校验。

### 2.4 工作台否定清单（防 IDE 化）

1. 无 Monaco/CodeMirror/Ace 等代码编辑器  
2. 无仓库文件树  
3. 无内嵌终端/调试器  
4. 无「聊天直接触发未注册 Action」  
5. 无前端配置 Agent 拓扑 / dynamic spawn  
6. 无绕过 PolicyGate 的一键执行  
7. harness 无 `if action == "accept_order"` 业务分支  
8. 无 React 本地假进度条冒充 Pipeline  
9. 无空 stub 冒充 KPI  
10. 无新增 `/api/core/fde` 平行路径  

### 2.5 复用，不平行

| 能力 | 权威实现 | 禁止 |
|------|----------|------|
| 架构守卫 | `scripts/architecture_guard.py` + `arch_guard_rules*` | 新建 `core/tools/architecture_guard` |
| Action 执行 | `AsyncActionRegistry` | 新建第二套 Registry |
| 审计存储 | `ActionStore.action_audit`（增量对齐 schema） | 平行审计库 |
| 安全审查 | security_view + security_review team | 工作台自造 finding 语义 |

---

## 3. 现状差距（方案依据，非实施 diff）

| 区域 | 现状摘要 | 方案含义 |
|------|----------|----------|
| 入口 | `/diagnostics/fde`，多 Tab | 保留；定位改为控制台 |
| 交付 Pipeline | `fde_delivery_v1` 模板存在；UI 进度可疑 | Phase 1 必须跑真 session |
| Orchestrator | `FDEBuilderOrchestrator` 零 caller 风险 | Phase 0 定生死 |
| Tab⑤ | 易被理解为「已构建客户应用」 | 诚实化为平台离线包 |
| 客户写回 | lock-service 有实体/状态机/Action 种子，工作台未竖切闭环 | Phase 2 主战场 |
| 域硬编码 | 历史上 GraphIndex/域名字面量问题；守卫已有部分规则 | Phase 0/1 契约化 + §98 |
| API | canonical 应为 `/api/platform/apps/fde` | Phase 0 统一，旧路径仅兼容 |
| 安全 | Phase A/B/C 已有基线 | Phase 4A 对接，命名显式映射 |

---

## 4. 与文章 / 安全方案的衔接

### 4.1 文章路径映射

| 文章概念 | 本方案 | 阶段 |
|----------|--------|------|
| FDE 进场理解业务 | 客户 Profile、域绑定、field_assessment | 0–1 |
| Ontology 世界模型 | lock-service 客户域（防空心；种子可扩展） | 2 |
| Agent 进业务 | ActionCard → Registry → 状态机 | 2 |
| AI FDE 改系统 | 迷你 Evolve + 变更面白名单 + Eval 门 | 4B |
| Agent Fleet | 多客户 DomainRouter 规模化 | 5（后置） |

### 4.2 阶段命名对齐（强制写清，避免读者脑内映射）

| FDE 方案阶段 | 安全方案 | 关系 |
|--------------|----------|------|
| Phase 0–3 | — | 控制台/交付/竖切/Builder |
| **Phase 4A** | **security Phase B/C** | 工作台「上线前检查」一键调用现有 dry-run；severity 不变 |
| FDE Phase 4B | （成本度量） | Evolve **立项时成本度量为硬前置**（可对接 security Phase D 或平台既有成本观测）；不得以「Phase D 未立项」跳过对比基线 |
| Phase 5 | — | 多客户 |

安全 severity 仍为：`candidate` →（有物理证据）`confirmed` | `refuted` | `inconclusive`。  
**禁止** FDE 侧另造 confirmed 语义。

---

## 5. 分阶段方案（详细）

### Phase 0 — 诚实与统一（约 Week 1）

**目的**：去掉「技术债伪装成能力」，否则 Phase 1 必返工。

| 工作项 | 验收标准 | 风险若跳过 |
|--------|----------|------------|
| API 前缀统一 | 前端/文档只推 `/api/platform/apps/fde`；旧路径标兼容不新增 | 双轨永久化 |
| Tab⑤ 文案 | 「平台离线包」≠「客户应用已构建」；可另加灰态「启动交付」入口 | 客户预期错乱 |
| Orchestrator 定生死 | 接线工厂 **或** 删除/归档计划进文档 | 假能力残留 |
| dashboard stub | 真数据或隐藏 | 空 KPI 误导 |
| `fde_delivery_v1` 标注 | 「模板已有 / 执行未接线」诚实状态 | 以为已可交付 |
| 契约入库 | Workbench Contract + audit_schema + **Guard Landing** 作为基线 | 后续扯皮 |
| DomainRouter 存量扫描 | 产出 [`domain_literals_scan.md`](../../contracts/domain_literals_scan.md)；量化分布与升 error 条件 | Phase 5 补丁堆 |
| DomainRouter 硬规则进守卫 | §98 `fde_domain_literals` 等（**warning**；不阻塞 Phase 1） | 漂移 |

**Phase 0 不做**：lock-service 大规模种子、Evolve、多客户、审计表破坏性迁移。

---

### Phase 1 — 跑真交付 Pipeline + 冻结前置契约（约 Week 1–2）

**目的**：控制台真正驱动执行核；把审计 / Eval / 变更面定义冻在 Phase 2/4 之前。

#### 1.1 功能

- 工作台可 **启动** `fde_delivery_v1` 并 **查询** session（进度来自服务端，禁止本地假进度）。
- 4 阶段可跑通：`customer_profile → solution_design → deployment_package → acceptance_report`。
- HITL：暂停 / 恢复 / 刷新恢复。

#### 1.2 必须提前冻结（不可推迟到 Phase 2/4）

1. **审计 schema**（`audit_schema.v1`）  
   - **文件已存在**于 `core/harness/schemas/audit_schema.v1.yaml`（冻语义，非 Phase 1 从零新建）。  
   - 最低可回答：「谁在何时批准了什么，执行前后实体状态是什么？」  
   - 字段底线：时间戳、actor、approver、action、params 哈希、前后快照、结果、PolicyGate 决策、retention。  
   - 存储：增量对齐 `ActionStore`，不平行建库。  
   - **与 ActionStore 映射**：见 Landing §4（Phase 1 优先 `params`/`entity_snapshot` JSON 嵌入；Phase 2 再加列；加列必须允许 NULL）。

2. **Eval 门语义**（禁止口头「全过」）  
   - `customer_action_safety`：all_pass + no_regression + 人审 + 可要求 security_review  
   - `platform_action_health`：阈值门 + no_regression  
   - `fde_delivery_pipeline`：阶段级，失败走 `failure_strategy`  
   - `evolve_proposal`：全过 + 人审 + 变更面白名单  
   - `security_audit_confirmed`：必须物理证据，禁止纯 LLM  

3. **变更面白名单**（YAML，见 audit_schema `change_surface_whitelist`）  
   - 允许例：`prompt_extra.*`、有限 model/retry/cache 键  
   - 禁止：`policy_gate.*`、`auth.*`、`database.*`、`sandbox.*`、`audit.*`  
   - 清单外一律 HITL  

4. **Pipeline HITL 组件引用（补齐）**  
   - 挂起/恢复：`PipelineEngine` + `pipeline_stage`（`stage.hitl` / `failure_strategy`）+ `stage_handoff`  
   - Action 审批：`ActionStore.pending_approvals`（非独立 ApprovalStore 文件）  
   - 验收必须证明：刷新后从服务端 session 恢复，而非本地 React state  

#### 1.3 HITL 硬验收（审查意见升格）

- [ ] 真实客户 Profile 跑完 4 阶段，**至少 2 次** HITL 暂停/恢复  
- [ ] 刷新后：阶段、待审批、产物链接全部正确  
- [ ] 阶段失败：`failure_strategy` 生效，可重试/跳过，不整链崩  
- [ ] 刷新后状态一致率 **100%**（相对服务端 session）

#### 1.4 成功度量

- Pipeline 刷新一致率  
- HITL 恢复成功率  
- （通过率仅作参考，不单独作为人审 KPI）

---

### Phase 2 — lock-service 最小竖切（约 Week 2–3）

**目的**：证明「Agent 进业务」——不是元层 fde-delivery，而是客户运营写回。

#### 2.1 为何选 lock-service

- 已有多类实体、状态机、accept_order 等 Action、UI 映射基础  
- 比 fde-delivery（元层）和更薄的 supply-chain 更适合「进业务」叙事  
- 演示故事具体：工单 → 提议 accept → 人批 → 状态迁移 → 证据 → KPI  

#### 2.2 竖切范围（最小）

1. 种子：1 客户站点 + 工单（**脚本可生成**，非仅手工 2 条）  
2. AcceptTab：**一张** ActionCard 真执行（经 Registry，不直写库）  
3. 完整 `audit_record`（customer_full profile）  
4. 文档声明：此为 **客户运营 Action**，区别于平台诊断 Action  
5. 扩展验收：**2 → 200 工单**，状态机与 Action 执行无异常（防 Ontology 空心只够演示）

#### 2.3 硬验收（含 200 工单量化标准）

- [x] 审计完整率 100%（必填字段无缺） — bench sample `schema=audit.v1` + `action_namespace=customer_action`
- [x] 可按 entity_id 查询「谁何时批准了什么」 — `ActionStore.list_audit(entity_id=…)`
- [x] 失败路径可触发补偿或明确 irreversible — contract `compensation` 字段 + AcceptTab 展示
- [x] UI 上两类 Action 视觉可区分 — `action_kind` badge（客户运营 / 平台诊断）
- [x] **压测（建议默认硬门，决策点可下调至 20）：**  
  - 200 工单 `accept`：**失败率 = 0**（非业务拒绝；基础设施/状态机异常计失败）  
  - 审计记录 **200 条**且完整率 100%  
  - Action 执行耗时：**从 `Registry.execute` 入口到 `insert_audit` 返回的全链路 P95 &lt; 500 ms**（含校验/快照/审计；**不含**人工审批等待）；环境在决策记录 D4 填写  
  - 按 entity 审计查询 **P95 &lt; 100 ms**（单实体最近 50 条）  
  - 若 D4 降为 20：须书面接受空心风险，并采用补偿（建议状态机组合测试 ≥200 种）  

证据（2026-09-14）：`PYTHONPATH=aiPlat-core:. .venv/bin/python scripts/bench_accept_order_p95.py --count 200` → PASS（exec_p95≈32ms，query_p95≈0.4ms）。

#### 2.4 不做

- 全量工单类型覆盖、技师排班优化、多站点联邦  

---

### Phase 3 — Builder 接线（真实交付物）

**目的**：交付产物来自工厂，而不是工作台假装构建。

- [x] 工作台只启动/观测/验收 Builder/Pipeline 产物链接  
- [x] **生成物适用性**：遵循工作区规约 CLAUDE.md §23；FDE 工作台本身属平台应用能力，生成 agent 交付物走 builder 已接线路径，工作台不平行实现构建。  
- [x] Eval：交付物走 `fde_delivery_pipeline` 门（链接 Builder 时未观测/失败 → `eval_blocked`）  

证据（2026-09-14）：`test_fde_phase3_builder_link.py`；API `link-builder` / `observe-builder` / `start-builder`；Tab⑤ Builder project_id。

---

### Phase 4 — 迷你 AIP Evolve + 安全汇合

#### 4A — 上线前安全检查（对接已有安全方案）

**接口契约（复用已有，不新造）：**

| 项 | 定义 |
|----|------|
| 暴露层 | `core.api.core_facade.run_security_review_dry(**kwargs)` |
| HTTP（已有） | `POST /api/.../diagnostics/code-intel/security-review-dry` |
| 工作台调用 | 仅经 CoreFacade（或已有 platform 代理），**禁止**直导 `security_*` handler |
| 参数 | `force: bool`，`max_paths: int=20`，`phase_c_enabled: bool=False`（或 env `AIPLAT_SECURITY_PHASE_C`） |
| 范围语义 | 当前实现基于仓库 code_graph / security_view；**默认 scope=当前工作区图**；若需 path/diff 范围，须先扩展 Facade 再改 UI（禁止 UI 私下扫盘） |
| 产物 | dry-run 报告 dict；Phase C 时 `regression_evidence.v1` 落盘 cache/tmp |
| Evidence | 路径写入报告 / evidence_ref；纳入 FDE Evidence 展示时只读引用，不改 severity 枚举 |
| 与 Eval 门 | `customer_action_safety.security_review_required` 可消费同次 dry-run 的 critique+evidence 摘要；**confirmed 仍要求物理证据** |

- [x] UI：独立「⑥b 上线前检查」入口（D5）  
- [x] 命名写清「FDE 4A = security B/C」  
- [x] 默认 Phase B；Phase C 显式开关  

#### 4B — Evolve（严格护栏）

- [x] Agent 仅可改白名单配置键；清单外 HITL  
- [x] 提案必须过 `evolve_proposal` 门后才进人审队列  
- [x] **不可**无审批写客户 ABox / Ontology 静默写  
- [x] **受控应用**：批准后 `apply_evolve_proposal` 写入 `fde_evolve_applied_config.json`；可 `rollback`；D6 指标（reject/rollback/survival；pass_rate 仅参考）  

#### 4 的成功度量（含反向指标，防橡皮图章）

| 指标 | 用途 |
|------|------|
| 人审拒绝率 + 理由分布 | 规则是否回写 |
| 人审通过后回滚率 | 批准质量 |
| 补丁平均存活时间 | 真实稳定性 |
| 人审通过率 | **仅参考，不得单独作 KPI** |

证据（2026-09-15）：`test_evolve_apply_rollback_metrics`；API `…/approve|reject|apply|rollback` + `/metrics`；EvolutionTab 操作按钮。  
证据（2026-09-15+）：`test_preflight_signoff_gate_blocks_missing_and_high`；`test_service_domain_assign_registers_and_executes`；AcceptTab 409 反馈。

---

### Phase 5 — 多客户与规模化（后置）

- [x] 新增客户 = DomainRouter 注册 + 本体/Action 配置，**不改 harness**（见 [`FDE_PHASE5_CUSTOMER_ONBOARDING.md`](../../contracts/FDE_PHASE5_CUSTOMER_ONBOARDING.md)）  
- [x] Agent Fleet 叙事仅在单域竖切稳定后展开 — **本阶段不产品化**（拓扑面板隔离）  
- [x] 前置条件：DomainRouter 硬规则已升 **error** 且行为分叉清零（`domain_literals_scan.md` v1.1；D2 关闭）  

证据（2026-09-14）：`test_fde_phase5_domain_literals.py`；`FdeDomainLiteralsAstCheck.level == "error"`。

---

## 6. 契约与守卫（方案层，非「现在就改」）

### 6.1 契约与运行时组件角色

| 文件 / 组件 | 作用 |
|-------------|------|
| `FDE_WORKBENCH_CONTRACT.md` | 控制台边界、两类 Action、否定清单、阶段映射、验收勾选 |
| `audit_schema.v1.yaml` | 审计字段、Eval 门、变更面白名单、保留策略（**已存在**） |
| `FDE_GUARD_REGISTRY_LANDING.md` | 接到现有 guard / Registry / ActionStore（盘点+映射） |
| `domain_literals_scan.md` | Domain 字面量存量与升 error 条件 |
| `PipelineEngine` / `pipeline_stage` / `stage_handoff` | 交付 Pipeline 挂起/恢复 / failure_strategy |
| `ActionStore.pending_approvals` | Action 级审批（方案中的 ApprovalStore 语义落点） |
| `ActionStore.action_audit` | 唯一审计写入；与 schema 增量对齐见 Landing §4 |

### 6.2 守卫规则与严重级别迁移

| 规则意图 | Week 1 | 升级条件 | 是否阻塞 Phase 1 |
|----------|--------|----------|------------------|
| `fde_domain_literals` | warning → **error（已升）** | 行为分叉清零 + 扫描关闭项；**升 error Owner/时点写入决策记录 D2** | **否**（阻塞 Phase 5 — **已解除**） |
| workbench_forbidden_components | error | — | 是（新增违规即拦） |
| no_hardcoded_action_branch | warning | 硬违规清零（初扫≈0，见 `action_branch_scan.md`） | 否 |
| no_parallel_fde_api | warning | 无新增平行路径 | 否 |
| no_workbench_direct_harness | error | — | 是 |

**落地策略**：扩展现有 `arch_guard_rules`（详见 Landing）；不新建独立 guard 包。  
**存量量化：** domain ~10 处（须分类：示例保留 / prompt 必改 / 行为分叉必清）；action 硬分支 ≈0。  
**domain_literals Phase 0 结束：** 扫描须交分类清单签字，不只报数量。

### 6.3 ActionRegistry 校验

注册时（当 `action_namespace` 已声明）——**钩子已存在**于 `AsyncActionRegistry.register`：

- 名与命名空间前缀一致  
- customer 不得使用平台跟踪域  
- 高风险 customer 必须 HITL（`require_approval`）  
- eval_gate 必须在 audit_schema 中存在  

执行时（Phase 2 接线完整 audit 形状）：

- 现有 7 步 + `build_audit_record` → `map_audit_to_action_store` → `insert_audit`  
- 审批走 `pending_approvals`  

存量 Action：`action_namespace` 为空则过渡期不强制。

---

## 7. 风险与缓解（审查意见固化）

| # | 风险 | 缓解（写入哪一阶段） |
|---|------|---------------------|
| 1 | 两类 Action 混注册导致审计/权限崩 | Phase 0 原则 + Phase 1 字段 + Phase 2 强制 customer 前缀 |
| 2 | DomainRouter 低估 → Phase 5 硬编码补丁 | Phase 0 守卫 + Phase 1 硬验收 |
| 3 | Ontology 空心（2 工单演示过关） | Phase 2：种子可扩展 + 200 工单压测验收 |
| 4 | Evolve「配置」范围过大 | Phase 1 白名单 YAML；Phase 4 只碰清单 |
| 5 | 审计形态不清 | Phase 1 冻 schema；Phase 2 落地 |
| 6 | HITL 端到端被低估 | Phase 1 三条硬验收 |
| 7 | Eval「全过」歧义 | Phase 1 冻门 ID；与 security confirmed 对齐 |
| 8 | 人审通过率反向激励 | Phase 4 强制反向指标组合 |
| 9 | 与安全阶段命名混淆 | 文档/UI 显式映射表 |

---

## 8. 建议排期（可评审，非承诺）

| 时段 | 焦点 | 产出物 | 默认是否改代码 |
|------|------|--------|----------------|
| **评审周前半** | 本方案 + 契约；决策记录填 Owner | Go/No-Go；D1–D6 Owner；§0.5 假设确认 | **否** |
| **评审周后半** | Landing + 两份扫描；Deadline；D5 延期责任人 | Landing 签字；domain/action 扫描确认；决策 v0.2→推进已决 | **否** |
| **评审周结束** | **六件套**勾选 Phase 0 生效 | 决策记录生效勾选 | **否** |
| Week 1 前半 | Phase 0 诚实化最小项 | API/文案/Orchestrator 决策落地 | 仅 Phase 0 最小项 |
| Week 1 后半 | Phase 1 启动 + 守卫 warning 观察 | 可查询 session | 是（有界） |
| Week 2 | Phase 2 竖切设计→演示 | accept_order 命名空间 + 审计可查 + 压测门 | 是 |

---

## 9. 决策点（需拍板：建议答案 + owner/deadline）

| # | 问题 | **建议答案（可驳回）** | Owner | Deadline |
|---|------|------------------------|-------|----------|
| 1 | Orchestrator：接线 vs 删除？ | **删除或归档**（零 caller 假能力）；交付一律工厂 Pipeline | _TBD_ | 评审周结束 |
| 2 | `fde-delivery` 是否允许唯一常量？ | **允许** `PLATFORM_TRACKING_DOMAIN`；禁止 Compare 行为分叉 | _TBD_ | 评审周结束 |
| 3 | `accept_order` 改前缀时机？ | Phase 2：**新 id + 旧别名**；Phase 3 废弃别名 | _TBD_ | Phase 2 开工前 |
| 4 | 200 工单硬门还是先 20？ | **默认 200**；降 20 须标注空心风险 + 补偿（建议状态机组合 ≥200 种）；P95=execute→insert_audit 全链路 | _TBD_ | Phase 2 开工前 |
| 5 | Phase 4A 放哪一 Tab？默认开 Phase C？ | 独立入口；默认 B，C 显式开关；立项时补范围与 evidence 生命周期 | _TBD_ | Phase 4 立项时 |
| 6 | 人审通过率作个人考核？ | **禁止作为唯一 KPI**；拒绝率+回滚率+存活时间 | _TBD_ | 评审周结束 |

---

## 10. 推荐的下一步（方案动作，非默认可写码）

1. **评审周前半**：评方案；决策记录填 Owner + §0.5 假设。  
2. **评审周后半**：签 Landing；确认 `domain_literals_scan`（分类）+ `action_branch_scan`；填 Deadline；指定 D5 延期责任人。  
3. **评审周结束**：**六件套**勾选 Phase 0 生效（决策记录 §3/§4）。  
4. **Phase 0 开工前**：最小项 + 回滚写入决策记录 §4。  
5. 未勾选 Phase 0 生效前：**冻结大规模程序改动**。

---

## 11. 附录：文档地图

```
docs/architecture/plans/fde-workbench-evolution-plan.md   ← 本方案（总览）
docs/contracts/FDE_WORKBENCH_CONTRACT.md
docs/contracts/FDE_GUARD_REGISTRY_LANDING.md
docs/contracts/domain_literals_scan.md
docs/contracts/action_branch_scan.md                      ← Action 分支初扫 v0.2
docs/contracts/FDE_DECISION_RECORD.md                     ← 决策记录 v0.3
docs/contracts/FDE_PHASE0_KICKOFF_CHECKLIST.md            ← 开工清单（勾完即开工）
docs/contracts/FDE_WORKBENCH_GUARD_AND_AUDIT_MAPPING.md   ← 否定清单/映射设计 v0.2
aiPlat-core/core/harness/schemas/audit_schema.v1.yaml
Pipeline HITL: core/harness/execution/pipeline_{engine,stage}.py + stage_handoff.py
Action 审批/审计: infrastructure/action_store.py (pending_approvals + action_audit)
安全 4A: core_facade.run_security_review_dry + regression_evidence.v1
生成物: CLAUDE.md §23 + scripts/check_generated_artifact_wiring.py
```

---

## 12. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-09-14 | 初稿：阶段、契约、风险、先方案后改码 |
| v1.1 | 2026-09-14 | 吸收评审：Landing/扫描、审计映射、Pipeline、4A 接口、200 量化、决策建议答案 |
| v1.1+ | 2026-09-14 | 决策 v0.2；六件套；action_branch；P95；4B 成本硬前置 |
| v1.1++ | 2026-09-14 | 路径强制回溯；决策 v0.3；开工清单；契约 README 索引；扫描/映射缺口补齐 |
