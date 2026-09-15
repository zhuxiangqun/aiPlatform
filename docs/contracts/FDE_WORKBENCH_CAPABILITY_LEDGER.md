# FDE 工作台能力台账（已填实例）

| 字段 | 值 |
|------|-----|
| 文档 ID | `FDE-LEDGER-2026-09` |
| 版本 | v1.11 |
| 模板 | [`FDE_CAPABILITY_LEDGER_TEMPLATE.md`](./FDE_CAPABILITY_LEDGER_TEMPLATE.md) |
| 关联 | [`FDE_WORKBENCH_CONTRACT.md`](./FDE_WORKBENCH_CONTRACT.md) v1.12 · [`ONTOLOGY_RUNTIME_AUTHORITY.md`](./ONTOLOGY_RUNTIME_AUTHORITY.md) · [`ONTOLOGY_NARRATIVE.md`](./ONTOLOGY_NARRATIVE.md) · [`ONTOLOGY_RUNTIME_CLOSEOUT.md`](./ONTOLOGY_RUNTIME_CLOSEOUT.md) · [`ONTOLOGY_COMPLETENESS.md`](./ONTOLOGY_COMPLETENESS.md) · [`FDE_DECISION_RECORD.md`](./FDE_DECISION_RECORD.md) · [`FDE_AI_FDE_CONTROLLED_APPLY_LOOP.md`](./FDE_AI_FDE_CONTROLLED_APPLY_LOOP.md) · [`FDE_BUSINESS_METRIC_HANDOVER.md`](./FDE_BUSINESS_METRIC_HANDOVER.md) · [`FDE_ESCORT_EXIT_CHECKLIST.md`](./FDE_ESCORT_EXIT_CHECKLIST.md) · [`FDE_USAGE_SIGNAL_MINIMAL_SET.md`](./FDE_USAGE_SIGNAL_MINIMAL_SET.md) |
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
| T10 | ⑥ 护栏 | canary 状态 / 回滚 | `production` | `manual:` `/canary/status` · rollback · ⑧ KPI | Tab⑥+⑧ | sync-ops 可 canary 回滚 | Oliver Zhu | 0 |
| T11 | ⑥b 预检 | 安全 dry-run | `production` | `test:` phase4 preflight · Facade dry-run | Tab⑥b | 不改写 severity | Oliver Zhu | 4A |
| T12 | ⑦ 验收 | 签收硬门（**交付质量门**） | `production` | `test:` `test_preflight_signoff_*` · HTTP 409 | Tab⑦ | ≠客户成功 | Oliver Zhu | 4A |
| T13 | ⑦ 验收 | 客户 Action 执行 | `production` | `test:` `test_fde_phase2*` · `benchmark:` bench_p95 | Tab⑦ | alias `accept_order` 已 deprecated | Oliver Zhu | 2 |
| T18 | ⑦ 验收 | 业务指标交接单 | `production` | `test:` `test_customer_success.py` · `/metric-handover` · AcceptTab | Tab⑦ | P2 客户侧字段仍手工；跨客户基线未做 | Oliver Zhu | 5 |
| T14 | ⑧ 运营 | Evolve 队列 | `production` | `test:` enqueue/list · EvolutionTab | Tab⑧ | — | Oliver Zhu | 4B |
| T15 | ⑧ 运营 | 受控 apply / rollback | `production` | `test:` observing + tick + quality/canary sync-ops | Tab⑧ | Registry platform_action 审计名可选 | Oliver Zhu | 4B |
| T16 | ⑧ 运营 | D6 反向指标 + 观测窗 | `production` | `test:` metrics + survival · sync-ops · Applied UI | Tab⑧ | — | Oliver Zhu | 4B |
| T19 | ⑧ 运营 | 使用信号 S1–S4 + 基线/趋势 | `production` | `test:` usage + baseline · `/usage-*` · sparkline | Tab⑧ | 跨客户横向基线未做 | Oliver Zhu | 4B/5 |
| T20 | ⑧ 运营 | 护航退出清单 | `production` | `test:` escort evaluate · A 组 audit 代理 · `/escort-exit` | Tab⑧ | a3 签收源 N/A；a2 为失败次数代理 | Oliver Zhu | 5 |
| T21 | ⑧ 运营 | 域级横向基线 | `production` | `test:` `test_domain_peers_*` · `/domain-peers` | Tab⑧ | 单位=domain；非同域多客户 | Oliver Zhu | 5 |
| T22 | 横切 | 本体运行时权威 / OCS 完整性 | `production` | `test:` OCS+lifecycle+confirm→提案 · `report_ontology_completeness.py --min-ocs 70` · contract: COMPLETENESS | 知识工厂/Action | 现场演示仍可加深 | Oliver Zhu | Ont-A–D |
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
| V06 | Phase 4B | Evolve 受控应用 | `production` | `test:` apply→observing→stable/rollback · quality/canary sync-ops · Applied UI | Tab⑧ | Registry 审计名可选 | Oliver Zhu | 4B |
| V07 | Phase 5 | 第二客户域可复制 | `production` | `test:` assign · OCS≥82 · `scan:` domain_literals | Tab①/⑦ | 现场加深可选 | Oliver Zhu | 5 |
| V08 | Ont-A | lock-service 纵深完整 (OCS≥80) | `production` | `test:` OCS+lifecycle · report: OCS≥86 · actions: accept/assign/start/complete | Tab⑦ | 现场半真实数据可再加深 | Oliver Zhu | Ont-A |
| V09 | Ont-B | OCS 方法产品化 + confirm→提案 | `production` | `script:` report_ontology_completeness · new_domain_scaffold · D1 enqueue | CI/知识工厂 | CI 全量域门禁可选 | Oliver Zhu | Ont-B |
| V10 | Ont-C/D | service-domain 复用 + 接口模块 + unified_customer | `production` | seed · OCS≥82 · interfaces · cross_domain_views · 零 harness 分叉 | Tab① | 跨域 view 运行时消费者可再加深 | Oliver Zhu | Ont-C/D |

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
| 质量分（运营） | Quality Bus `/quality-summary` | `real`@⑧ | SLA `scores.total` 回退 | Oliver Zhu |
| Action 成功率（使用 S3） | `action_audit.result_status` | `real`@⑧ | `/usage-signal` | Oliver Zhu |
| 日活 actor / 日调用 / 活跃天（S1/S2/S4） | `action_audit.actor` / 行数 / `created_at` | `real`@⑧ | `/usage-signal` | Oliver Zhu |
| canary 状态（运营） | `/canary/status` | `real`@⑥+⑧ | sync-ops → canary_anomaly 回滚 | Oliver Zhu |
| Evolve reject_rate（运营） | `get_evolve_metrics` | `real` | — | Oliver Zhu |
| Evolve rollback_rate（运营） | 同上 | `real` | — | Oliver Zhu |
| Evolve mean_survival（运营） | survival_seconds on rollback | `real`（仅回滚样本） | 观测窗结束也记存活 | Oliver Zhu |
| 待审抽取 | `/extractions/pending` | `real` | — | Oliver Zhu |
| 跨客户域基线 | `list_domain_peers` / `/domain-peers` | `real`@⑧ | **域级** peer（无 tenant 键）；同域多客户待加 | Oliver Zhu |
| trace_anomalies / training | stub | `stub-hidden` | 删除或真接线 | Oliver Zhu |

---

## 6. 死 API / 无消费方清单（FdeDashboard）

| API | 原消费方 | 当前状态 | 处理建议 | Owner |
|-----|----------|----------|----------|-------|
| `POST …/heal` | — | 无工作台消费 | 运维入口登记或 deprecate | Oliver Zhu |
| `/bootstrap*` | 演示 | 无工作台消费 | 运维/演示 CLI | Oliver Zhu |
| `/trends*` | — | 无工作台消费 | 运维或并入⑧ | Oliver Zhu |
| `/quality-summary` | Tab⑧ | **已消费**（展示 + sync-ops） | 保留 | Oliver Zhu |
| `/usage-signal` · `/usage-trend` | Tab⑧ | **已消费**（S1–S4；trend API 已挂、折线图可选） | 保留 | Oliver Zhu |
| `/domain-peers` | Tab⑧ | **已消费**（域级横向表） | 保留；同域多客户需 tenant | Oliver Zhu |
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
| Evolve 恶化 | sync-ops / 人工 rollback |

### 7.1 交付质量 vs 客户成功（速查）

| 问题 | 答 |
|------|----|
| 交付验收全绿说明什么？ | **交付质量门**通过，不证明客户在用 |
| 「客户用没用」看什么？ | 使用信号 S1–S4（⑧ `/usage-signal`）+ 交接单 P2/P3 |
| 护航何时结束？ | [`FDE_ESCORT_EXIT_CHECKLIST.md`](./FDE_ESCORT_EXIT_CHECKLIST.md) 条件达标，非纯日历 |
| FDE 算不算 ROI？ | **不算**；只记基线与可观测部分 |

---

## 8. 与闭环 / 客户成功文档的关系

| 台账行 | 现状 | 下一步 |
|--------|------|--------|
| T15 / T16 / V06 | **`production`**：observing→stable；sync-ops 自动回滚 | 可选 Registry 审计名 |
| T18 / T19 / T20 | **均 `production`**；A 组 a1/a2/a4 可自动勾 | a3 签收记录源；同域多客户 tenant |
| T21 | **`production`**：域级 `/domain-peers` | 同域多客户对照 |

---

## 9. 更新记录

| 日期 | 更新人 | 变更 |
|------|--------|------|
| 2026-09-15 | Oliver Zhu | v1.0 初填（叙述型） |
| 2026-09-15 | Oliver Zhu | v1.1 对齐模板 ID（T/V/E）+ 填 §2/§4；挂闭环设计 |
| 2026-09-15 | Oliver Zhu | v1.2 T15/T16/V06 → production（观测窗+质量自动回滚） |
| 2026-09-15 | Oliver Zhu | v1.3 Quality Bus + canary sync-ops；§6 quality-summary 已消费 |
| 2026-09-15 | Oliver Zhu | v1.4 三层指标正名；T18–T20；挂交接单/退出清单/使用信号 |
| 2026-09-15 | Oliver Zhu | v1.5 T19 usage-signal API + ⑧ S1–S4 卡 |
| 2026-09-15 | Oliver Zhu | v1.6 T18/T20 production：交接单 + 护航退出 + 基线/趋势 |
| 2026-09-15 | Oliver Zhu | v1.7 T21 域级横向基线 `/domain-peers` |
| 2026-09-15 | Oliver Zhu | v1.8 护航 A 组自动勾（非平台 actor / 失败代理 / 联系人） |
| 2026-09-15 | Oliver Zhu | v1.9 挂本体运行时权威；`sys_graph_validate` 假绿禁令 + 测试 |
| 2026-09-15 | Oliver Zhu | v1.10 T22→production：lock-service 中/深档闭环 + CLOSEOUT |
| 2026-09-15 | Oliver Zhu | v1.11 OCS 完整路线：COMPLETENESS 合同；lock OCS≥86；service-domain OCS≥82；scaffold/D1 |
