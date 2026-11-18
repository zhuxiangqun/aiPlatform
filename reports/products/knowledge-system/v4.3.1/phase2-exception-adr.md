---
doc_type: Report
title: Phase 2 — 知识系统符合性例外 ADR 包（Batch F1 §9.4 exception_adr 槽位）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
standard: docs/standards/knowledge-system/v4.3.1/normative-appendix.md §N
---

# Phase 2 / 例外 ADR 包（Batch F1）

> 实施权威：附录 N 认证证据包 `certification_slots.exception_adr` 最小填空。  
> **集中登记当前 partial 例外**；**非**全量 ADR 体系；**未宣称** 例外已关闭或 Core 认证。

## 例外清单（范围 / 期限 / 补偿）

| ID | 范围 | 期限 | 补偿 |
|----|------|------|------|
| N01 | FactLedger 读时 hash + DataSourceConfig content_hash→Raw；非全连接器矩阵 | 至 N01 全量/试点签字 | 见 `phase2-raw-integrity-evidence.md` + `phase2-datasource-raw-evidence.md` |
| N03 | Claim 证据硬门+冲突记录最小切片；非全量 Claim 状态机 | 至 N03 全量加深 | suite/gate；见 `phase2-claim-evidence-evidence.md` |
| N06 | FactLedger F.1 契约；非统一 Query Gateway | 至 Gateway 统一入口 | confidence_factors + 契约门 |
| N09 | FactLedger + ObjectSet/UnifiedAudit（K1）+ Wiki/KB（K2）+ GraphRAG（K3）+ caller（K4）+ GraphIndex（K5）+ 图写入（K6）+ 跨域/snapshot（K7）+ ontology_editor HTTP（K8）+ class/rollback（K9）+ view/meta（K10）+ process_monitor（K11）+ process_instances/engine（K12）+ auto_ontology_pipeline（K13）+ staleness/diagnostics（K14）+ staleness cron/health（K15）+ garden/file/self_heal（K16）+ diagnostics drift 身份（K17）+ metric/scoring CRUD（K18）+ governance/maturity（K19）+ ontology quality（K20）+ context_bus/health（K21）+ evolver/SECI/retrieval（K22）+ diagnostician/convergence/case/recon（K23）+ wiki/graph syscall（K24）+ wiki_ontology_engine（K25）+ ontology_engine（K26）+ builtin_handlers（K27）+ FDE service（K28）+ facade/system/eval/infra（K29）+ skills/pipeline/router（K30）+ platform FDE API wave1（K31）+ wave2（K32）+ handlers/scripts（K33）+ GraphIndex ctor/branch（K34）+ scripts ctor（K35）+ branch registry（K36）+ branch YAML（K37）+ FDE tracking domain（K38）+ FDE terms/atom/kb（K39）+ harness atom/kb/terms（K40）+ competition domain（K41）+ GraphIndex ctor domain（K42）+ KB/tracking fallbacks（K43）+ KB domain signature defaults（K44）+ default graph domain signature defaults（K45）+ it-ops/data-gov signature defaults（K46）+ aiplat-system signature defaults（K47）+ icebreaker config（K48）+ default tenant SSOT（K49）+ outer tenant signature defaults（K50）+ tenant SQL/assign literals（K51）+ collection/profile SSOT（K52）+ default session SSOT（K53）+ tenant runtime fallbacks（K54）；未宣称全域 0 泄漏 | 至 governance 管线内透传 / certified | 跨租户套件门槛门 |
| N04/N12 | 写入硬门+transition；非 reviewer RBAC | 开放 | source_policy + fact_state_machine |
| N07/N22 | ObjectSet + link.traverse ACL；非 Wiki/KB 全入口 | 开放 | ABox ACL 切片 |
| N11/N14 | 本地双写对账；切写未授权 | 开放 | migration 演练 |
| N24 | Package + Fact/Claim/Source revision + restore + audit + 审批式 restore + ActionExecution 桥接 + HTTP + 管理端薄 UI + 只读统一视图 + 统一审计 UI + 写总线 + Package/Action 热路径 + ActionStore 合流 + 物理 tenant_id + 存量回填；非 certified | 至 N24 全量加深 | 见 revision 系列 + `phase2-unified-audit-action-store-tenant-backfill-evidence.md` |
| SLO | 目标已登记；生产遥测未接线 | 开放 | 本 ADR + `phase2-slo-target-evidence.md` |

权威条目 note 以 [`n24-conformance-catalog.yaml`](./n24-conformance-catalog.yaml) 为准；本表为人读汇总。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| catalog `exception_adr` path 非空且文件存在 | pass | catalog 槽位 |
| 结构门无 explicit-missing warning | pass | conformance pack 测 |
| certified 恒 false | pass | honesty |

## 明确未做

- 例外自动过期/关闭工作流
- 用本包冒充附录 N 全量符合或风险已接受签字
