---
doc_type: Report
title: Phase 0/2 — 附录 N 24 项符合性差距表（刷新）
status: active
authority: supporting
measured_at: 2026-11-16
pilot_domain: lock-service
standard: docs/standards/knowledge-system/v4.3.1/normative-appendix.md §N
catalog: reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml
---

# 附录 N 24 项差距表（2026-11-16 刷新）

> 状态：`exists` / `partial` / `missing`。  
> **无一项勾选为「已符合认证」**；`exists` 仅表示标准包或实现碎片可用。  
> **机器可读 SSOT**：[`n24-conformance-catalog.yaml`](./n24-conformance-catalog.yaml)（本表为人读摘要）。  
> 证据包：`build_conformance_pack` / `GET …/fde/conformance-pack`（见 `phase2-conformance-pack-evidence.md`）。

| # | 要求（附录 N） | 状态 | 证据（摘要） | 差距类型 | Phase |
|---|---------------|:----:|--------------|----------|:-----:|
| 1 | Raw 不可变 | partial | 读时验 + DataSourceConfig content_hash→Raw（`phase2-datasource-raw-evidence.md`）；非 certified | 有实现无证据 | W1 |
| 2 | 语义模型版本化 | partial | 域 YAML version + Package 切片 | 有数据无契约 | W2 |
| 3 | Fact/Claim 有 evidence | partial | Claim 证据硬门+冲突记录（`phase2-claim-evidence-evidence.md`）；非 certified | 有实现无证据 | W3 |
| 4 | 来源策略与冲突裁决 | partial | 写入硬门 + Conflict/transition（`phase2-source-policy-evidence.md`） | 有实现无证据 | W3 |
| 5 | Wiki/索引有条件重建 | partial | 三分类 rebuild_mode+reason+门槛门（Wiki 硬门保持） | 有 Wiki 无事实源 | W4 |
| 6 | Gateway 查询契约 | partial | F.1 契约+confidence_factors（`phase2-gateway-contract-evidence.md`）；非统一入口/certified | 有实现无证据 | W6 |
| 7 | 权限召回前过滤 | partial | ObjectSet + link.traverse 召回前 ACL | 有查询无权限 | W6/W8 |
| 8 | 动作 Policy/Approval/Audit | partial | L1+幂等；裸 bypass 拒绝（仅 approve 重入） | 有动作无门禁 | W5/W7 |
| 9 | 跨租户 0 泄漏 | partial | FactLedger + ObjectSet/UnifiedAudit（K1）+ Wiki/KB（K2）+ GraphRAG（K3）+ caller（K4）+ GraphIndex（K5）+ 图写入（K6）+ 跨域/snapshot（K7）+ ontology_editor HTTP（K8）+ class/rollback（K9）+ view/meta（K10）+ process_monitor（K11）+ process_instances/engine（K12）+ auto_ontology_pipeline（K13）+ staleness/diagnostics（K14）+ staleness cron/health（K15）+ garden/file/self_heal（K16）+ diagnostics drift 身份（K17）+ metric/scoring CRUD（K18）+ governance/maturity（K19）+ ontology quality（K20）+ context_bus/health（K21）+ evolver/SECI/retrieval（K22）+ diagnostician/convergence/case/recon（K23）+ wiki/graph syscall（K24）+ wiki_ontology_engine（K25）+ ontology_engine（K26）+ builtin_handlers（K27）+ FDE service（K28）+ facade/system/eval/infra（K29）+ skills/pipeline/router（K30）+ platform FDE API wave1（K31）+ wave2（K32）+ handlers/scripts（K33）+ GraphIndex ctor/branch（K34）+ scripts ctor（K35）+ branch registry（K36）+ branch YAML（K37）+ FDE tracking domain（K38）+ FDE terms/atom/kb（K39）+ harness atom/kb/terms（K40；`phase2-cross-tenant-harness-atom-domain-evidence.md`）+ competition domain（K41；`phase2-cross-tenant-competition-domain-evidence.md`）+ GraphIndex ctor domain（K42；`phase2-cross-tenant-graphindex-ctor-domain-evidence.md`）+ KB/tracking fallbacks（K43；`phase2-cross-tenant-kb-domain-fallbacks-evidence.md`）+ KB domain signature defaults（K44；`phase2-cross-tenant-kb-domain-defaults-evidence.md`）+ default graph domain signature defaults（K45；`phase2-cross-tenant-default-graph-domain-defaults-evidence.md`）+ it-ops/data-gov signature defaults（K46；`phase2-cross-tenant-it-ops-domain-defaults-evidence.md`）+ aiplat-system signature defaults（K47；`phase2-cross-tenant-system-domain-defaults-evidence.md`）+ icebreaker config（K48；`phase2-cross-tenant-icebreaker-config-evidence.md`）+ default tenant SSOT（K49；`phase2-cross-tenant-default-tenant-ssot-evidence.md`）+ outer tenant signature defaults（K50；`phase2-cross-tenant-default-tenant-outer-evidence.md`）+ tenant SQL/assign literals（K51；`phase2-cross-tenant-default-tenant-sql-literals-evidence.md`）；未认证全域 0 | 有实现无证据 | W8 |
| 10 | 评测定义/数据集/门槛 | partial | Confidence Calibration 附录 O | 有实现无证据 | W10 |
| 11 | 迁移/回滚方案 | partial | Migration 双写/对账/回滚演练；切写未授权 | 有实现无证据 | W10 |
| 12 | Fact 状态机 | partial | 写入硬门 + transition 审计（`phase2-fact-state-evidence.md`） | 有实现无证据 | W3 |
| 13 | confidence 校准规则 | partial | 失败/缺失 → 最高 medium | 有实现无证据 | W10 |
| 14 | 跨存储失败恢复/对账 | partial | Migration 本地 store 对账 | 有实现无证据 | W10 |
| 15 | JSON Schema 与附录一致 | exists | phase0 标准包 | 标准包就绪 | — |
| 16 | 附录示例 Schema 校验 | exists | phase0 标准包 | 标准包就绪 | — |
| 17 | 记录级语义校验 | exists | phase0 参考策略 | 标准包就绪 | — |
| 18 | 实现方语义测试 | partial | Implementer Semantics 5 探针 + gate | 有实现无证据 | W10 |
| 19 | 运行时权威与审计快照 | partial | ActionExecution before/after | 有实现无证据 | W7 |
| 20 | L1/L2/L3 约束分层 | partial | G2 / FunctionContract L1 | 有动作无门禁 | W7 |
| 21 | 防假绿 | partial | OCS/校准诚实锁 | 有实现无证据 | W6/W10 |
| 22 | 实例/字段级 ACL | partial | ObjectSet + link.traverse ABox ACL | 有查询无权限 | W8 |
| 23 | OCS 完整度 | partial | §13.4 覆盖计分 + gate | 有实现无证据 | W10 |
| 24 | 版本/变更/审计 | partial | Package + Fact/Claim/Source revision + restore + audit + 审批式 restore + Action 桥接 + HTTP + 管理端薄 UI + 只读统一视图 + 统一审计 UI + 写总线 + Package/Action 热路径 + ActionStore 合流 + 物理 tenant_id + 存量回填；非 certified | 有实现无证据 | W2–W3 |

## 汇总（相对 2026-11-15 基线）

| 状态 | 项数 | 说明 |
|------|:----:|------|
| exists | 3 | #15–17 标准包（不变） |
| partial | 21 | W3–W10 最小切片推进后由 missing 升格（含 N04/N12/N18） |
| missing | 0 | — |

**目标等级（记录）**：Core（仍未达成）。  
**禁止话术**：不得因本表 partial 增多而宣称「附录 N 已符合」或「可认证」。
