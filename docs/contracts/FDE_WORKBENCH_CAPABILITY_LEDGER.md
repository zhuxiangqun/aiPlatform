# FDE 工作台能力台账（已填实例）

| 字段 | 值 |
|------|-----|
| 文档 ID | `FDE-LEDGER-2026-09` |
| 版本 | v1.2 |
| 模板 | [`FDE_CAPABILITY_LEDGER_TEMPLATE.md`](./FDE_CAPABILITY_LEDGER_TEMPLATE.md) |
| 关联 | [`FDE_WORKBENCH_CONTRACT.md`](./FDE_WORKBENCH_CONTRACT.md) v1.7 · [`FDE_DECISION_RECORD.md`](./FDE_DECISION_RECORD.md) · [`FDE_AI_FDE_CONTROLLED_APPLY_LOOP.md`](./FDE_AI_FDE_CONTROLLED_APPLY_LOOP.md) |
| 维护人 | Oliver Zhu |
| 更新节奏 | 每 Phase 结束；重大变更即时 |
| 状态 | ☑ 草稿 · ☐ 评审中 · ☐ 生效 |
| 入口 | `/diagnostics/fde` · `/api/platform/apps/fde` |

> 按模板填 §2 Tab + §3 竖切 + §4 执行核（2026-09-15 代码交叉验证）。  
> 成熟度枚举与模板一致：`production` / `pilot` / `demo` / `stub-hidden` / `not-implemented` / `deprecated`。  
> 证据类型前缀：`test:` · `benchmark:` · `contract:` · `scan:` · `manual:` · `none`。

---

## 0. 使用说明（摘要）

台账是可审计清单，不是宣传页。无证据写 `none`。逾期两周未更新 → 停滞。

---

## 1. 成熟度定义

（同模板 §1，不重复。）

---

## 2. Tab 级能力台账

| ID | Tab | 能力 | 成熟度 | 证据 | 消费方 | 已知缺口 | Owner | Phase |
|----|-----|------|--------|------|--------|----------|-------|-------|
| T01 | ① 业务认知 | 客户 Profile CRUD | `production` | `manual:` FdeDashboard CustomersTab · `/customers` | Tab① | 非认知引擎；Fleet 不做 | Oliver Zhu | 0/5 |
| T02 | ① 业务认知 | 行业推断 | `pilot` | `manual:` `/infer-industry` | Tab①/壳 | 推断质量未压测 | Oliver Zhu | 0 |
| T03 | ② 评估域 | 域成熟度 / 能力面 | `pilot` | `manual:` `/health/all` · capability-boundary | Tab② | 依赖 DomainRouter 数据填充深度 | Oliver Zhu | 0 |
| T04 | ③ 问题重构 | field_assessment | `pilot` | `manual:` skill execute | Tab③ | 与 sessions/compare 等 API 未同 Tab 消费 | Oliver Zhu | 0 |
| T05 | ③ 问题重构 | 多轮澄清对话 | `pilot` | `manual:` `/assess/dialog` | Tab③ | 就绪度阈值依赖运行时 | Oliver Zhu | 1 |
| T06 | ④ 验证价值 | 模板 / POC 切换 | `demo` | `manual:` `/templates` · poc_data_inject | Tab④ | ROI 叙事 > 全自动评测闭环 | Oliver Zhu | 0 |
| T07 | ⑤ 交付 | 平台离线包 | `production` | `manual:` `/package*` + honesty 文案 | Tab⑤ | ≠客户应用包 | Oliver Zhu | 0 |
| T08 | ⑤ 交付 | 交付 session + HITL | `production` | `test:` `test_fde_phase1b_delivery*` · `done_skipped_llm` | Tab⑤ | 非 HITL 不跑 LLM（诚实） | Oliver Zhu | 1 |
| T09 | ⑤ 交付 | Builder 链接 + Eval | `production` | `test:` `test_fde_phase3*` · eval_blocked | Tab⑤ | 工厂失败需回工厂日志 | Oliver Zhu | 3 |
| T10 | ⑥ 护栏 | canary 状态 / 回滚 | `production` | `manual:` `/canary/status` · rollback | Tab⑥ | 未汇入 ⑧ KPI 卡 | Oliver Zhu | 0 |
| T11 | ⑥b 预检 | 安全 dry-run | `production` | `test:` phase4 preflight · Facade dry-run | Tab⑥b | 不改写 severity | Oliver Zhu | 4A |
| T12 | ⑦ 验收 | 签收硬门 | `production` | `test:` `test_preflight_signoff_*` · HTTP 409 | Tab⑦ | checklist 其他项可 pending | Oliver Zhu | 4A |
| T13 | ⑦ 验收 | 客户 Action 执行 | `production` | `test:` `test_fde_phase2*` · `benchmark:` bench_p95 | Tab⑦ | alias `accept_order` 已 deprecated | Oliver Zhu | 2 |
| T14 | ⑧ 运营 | Evolve 队列 | `production` | `test:` enqueue/list · EvolutionTab | Tab⑧ | — | Oliver Zhu | 4B |
| T15 | ⑧ 运营 | 受控 apply / rollback | `production` | `test:` observing + tick stable + quality breach | Tab⑧ | canary 自动触发未接；Registry platform_action 审计名可选 | Oliver Zhu | 4B |
| T16 | ⑧ 运营 | D6 反向指标 + 观测窗 | `production` | `test:` metrics + survival on stable/rollback · Applied UI | Tab⑧ | Quality Bus 未直挂观测采样 | Oliver Zhu | 4B |
| T17 | ⑨ 快速认知 | 48h 行业认知 | `pilot` | `manual:` rapid_insight 面板 | Tab⑨ | 与主交付链弱耦合 | Oliver Zhu | 0 |

---

## 3. 竖切级能力台账

| ID | 竖切 | 能力 | 成熟度 | 证据 | 消费方 | 已知缺口 | Owner | Phase |
|----|------|------|--------|------|--------|----------|-------|-------|
| V01 | Phase 0 | API 统一 / 否定清单 | `production` | `contract:` WORKBENCH_CONTRACT · Orchestrator 归档 | 全站 | — | Oliver Zhu | 0 |
| V02 | Phase 1 | 交付 session + audit 冻结 | `production` | `test:` phase1* · `contract:` audit_mapping_report **embed-only** | Tab⑤ | 表加列未默认 migrate | Oliver Zhu | 1 |
| V03 | Phase 2 | lock-service accept_order | `production` | `test:` phase2* · `benchmark:` 200p95 · `contract:` ALIAS_DEPRECATION | Tab⑦ | 旧 alias 调用方 → not registered | Oliver Zhu | 2 |
| V04 | Phase 3 | Builder 产物链接 | `production` | `test:` phase3* | Tab⑤ | — | Oliver Zhu | 3 |
| V05 | Phase 4A | 安全预检 + 签收硬门 | `production` | `test:` preflight_signoff · acceptance 409 | Tab⑥b/⑦ | — | Oliver Zhu | 4A |
| V06 | Phase 4B | Evolve 受控应用 | `pilot` | `test:` apply→observing→stable/rollback · quality breach | Tab⑧ | 观测窗+质量跌破自动回滚已落地；canary 联动仍缺 | Oliver Zhu | 4B |
| V07 | Phase 5 | 第二客户域可复制 | `pilot` | `test:` `test_fde_service_domain_assign` · seed yaml · `scan:` domain_literals v1.1 | Tab①/⑦ | Action e2e 过；**非**第二客户全旅程现场报告 | Oliver Zhu | 5 |

---

## 4. 执行核级能力台账

| ID | 组件 | 能力 | 成熟度 | 证据 | 消费方 | 已知缺口 | Owner |
|----|------|------|--------|------|--------|----------|-------|
| E01 | AsyncActionRegistry | 注册校验（namespace/domain） | `production` | `test:` phase1/2 register · seed | 全站 | — | Oliver Zhu |
| E02 | AsyncActionRegistry | 执行 + audit.v1 嵌入 | `production` | `test:` execute→insert_audit · map_audit | 全站 | 7 步细节以代码为准；非并行 Registry | Oliver Zhu |
| E03 | WorkbenchRuntimeGuard | 未注册 Action / PG 形状 / stub KPI | `pilot` | `manual:` execute 前置 · `_write_audit` 软警告 · dashboard meta | 工作台 | KPI 非硬拦；PG 非全路径证明 | Oliver Zhu |
| E04 | PolicyGate | 三态决策 | `production` | `contract:` + Registry 路径 | Registry | 工作台不得第二套门 | Oliver Zhu |
| E05 | HITL / pending_approvals | 审批存储 | `pilot` | `manual:` ActionStore `lock_id` | Registry | **无** request_id↔audit；**无** resume_token | Oliver Zhu |
| E06 | ActionStore.action_audit | audit.v1 字段 | `pilot` | `contract:` audit_mapping_report present=8 embedded=13 | 全站 | embed-only；ADD COLUMN 可选 | Oliver Zhu |
| E07 | DomainRouter | 唯一域解析 | `production` | `scan:` domain_literals_scan AST=0 · require_known_domain | 全站 | — | Oliver Zhu |
| E08 | architecture_guard | FDE 规则（含 domain_literals=error） | `production` | `scan:` fde_workbench.py · CI | CI | — | Oliver Zhu |
| E09 | preflight Facade | dry-run + evidence 摘要 | `production` | `test:` phase4 · security_preflight.py | Tab⑥b | — | Oliver Zhu |

---

## 5. KPI 数据源表（⑧）

| KPI | 数据源 | 状态 | 替代方案 | Owner |
|-----|--------|------|----------|-------|
| 质量分 | Quality Bus `/quality-summary` | `roadmap`（无 Tab 消费） | 现用 SLA `scores.total` 或 `—` | Oliver Zhu |
| Action 成功率 | ActionStore.action_audit | `roadmap` | 无 | Oliver Zhu |
| canary 状态 | `/canary/status` | `real`@⑥ · 未汇入⑧ | ⑧ 卡挂载 | Oliver Zhu |
| Evolve reject_rate | `get_evolve_metrics` | `real` | — | Oliver Zhu |
| Evolve rollback_rate | 同上 | `real` | — | Oliver Zhu |
| Evolve mean_survival | survival_seconds on rollback | `real`（仅回滚样本） | 观测窗结束也记存活 → 闭环设计 | Oliver Zhu |
| 待审抽取 | `/extractions/pending` | `real` | — | Oliver Zhu |
| trace_anomalies / training | stub | `stub-hidden` | 删除或真接线 | Oliver Zhu |

---

## 6. 死 API / 无消费方清单（FdeDashboard）

| API | 原消费方 | 当前状态 | 处理建议 | Owner |
|-----|----------|----------|----------|-------|
| `POST …/heal` | — | 无工作台消费 | 运维入口登记或 deprecate | Oliver Zhu |
| `/bootstrap*` | 演示 | 无工作台消费 | 运维/演示 CLI | Oliver Zhu |
| `/trends*` | — | 无工作台消费 | 运维或并入⑧ | Oliver Zhu |
| `/quality-summary` | — | 无工作台消费 | **P1 接⑧** | Oliver Zhu |
| `/sessions/compare` | — | 无工作台消费 | 挂③或归档 | Oliver Zhu |
| `POST …/network/evolve` | AgentNetworkPanel | 隔离面板 | **勿与 4B Evolve 混名** | Oliver Zhu |

---

## 7. 交付完成态 / 失败路径（控制台速查）

见前版细节；摘要：

| 完成态 | Eval |
|--------|------|
| `partial-skip`（`done_skipped_llm`） | 无 Builder → pass + honesty |
| `builder-linked` | 缺 artifact → `eval_blocked` |
| `full-llm` | 仅工厂；工作台不自跑 |

| 失败信号 | 恢复 |
|----------|------|
| eval_blocked | observe + artifact_links |
| 签收 409 | ⑥b 重跑消 high/critical |
| Evolve 恶化 | **人工** rollback（自动触发见闭环设计） |

---

## 8. 与闭环设计的关系

| 台账行 | 现状 | 闭环设计推进后目标 |
|--------|------|-------------------|
| T15 / T16 / V06 | **`production`（2026-09-15）**：observing→stable tick；quality_score 跌破阈值自动回滚；Applied 列表 UI | 可选：canary 自动触发、Registry `platform_action:…:evolve_*` 审计名 |

**落地顺序（采纳设计建议）：** 先维持本台账更新 → 再实施 [`FDE_AI_FDE_CONTROLLED_APPLY_LOOP.md`](./FDE_AI_FDE_CONTROLLED_APPLY_LOOP.md)。

---

## 9. 更新记录

| 日期 | 更新人 | 变更 |
|------|--------|------|
| 2026-09-15 | Oliver Zhu | v1.0 初填（叙述型） |
| 2026-09-15 | Oliver Zhu | v1.1 对齐模板 ID（T/V/E）+ 填 §2/§4；挂闭环设计 |
| 2026-09-15 | Oliver Zhu | v1.2 T15/T16/V06 → production（观测窗+质量自动回滚） |
