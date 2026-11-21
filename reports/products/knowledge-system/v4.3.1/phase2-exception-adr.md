---
doc_type: Report
title: Phase 2 — 知识系统符合性例外 ADR 包（Batch F1 §9.4 exception_adr 槽位）
status: active
authority: supporting
measured_at: 2026-11-21
pilot_domain: lock-service
standard: docs/standards/knowledge-system/v4.3.1/normative-appendix.md §N
---

# Phase 2 / 例外 ADR 包（Batch F1）

> 实施权威：附录 N 认证证据包 `certification_slots.exception_adr` 最小填空。  
> **集中登记当前例外**；**非**全量 ADR 体系；试点 Core（朱鸿林）+ Extended（朱莹）+ Operational（朱莹）+ 全量（朱向群，conditional）已批准；SLO 目标已登记且遥测已接线（非生产达标）。  
> 2026-11-19：Core 12 / Extended 6 / Operational 6 均按附录 N.2–N.4 标为等级 scoped `exists`；N09 **探针集冻结**；深度缺口记为后续加深，不阻塞已开徽章。  
> 2026-11-21：非本表 catalog note 盘点见 `phase2-catalog-honesty-triage.md`（不关闭本表例外）。

## 例外清单（范围 / 期限 / 补偿）

| ID | 范围 | 期限 | 补偿 |
|----|------|------|------|
| N01 | FactLedger 读时 hash + DataSourceConfig content_hash→Raw + process Raw 默认强制（可 opt-out）+ Core file/sql/api 连接器矩阵；非 vendor 驱动矩阵 / 非 certified | 至 N01 全量/试点签字 | 见 raw-integrity + datasource-raw + process-raw + default-force + `phase2-datasource-connector-matrix-evidence.md` |
| N02 | 域 YAML version + Package + ObjectType draft→人审发布（角色门；Package schema 门可选）；非全量发布门户 / 非种子替换 / 非 certified | 至 N02 全量/试点签字 | 见 ontology-package + `phase2-object-type-publish-evidence.md` |
| N03 | Claim 证据硬门+冲突记录 + 状态写路径（transition→put_claim）；非全量 Claim 生命周期产品 / 非 certified | 至 N03 全量/试点签字 | 见 claim-evidence + `phase2-claim-status-write-evidence.md` |
| N06 | FactLedger F.1 契约 + 统一入口（fact/object_set/wiki/index → F.1）；非 MaterialsChat 全入口 / 非 certified | 至 N06 全量/试点签字 | 见 gateway-contract + `phase2-unified-query-gateway-evidence.md` |
| N09 | Core 探针集已冻结（`n09_core_probe_freeze`）；跨租户套件含统一 Gateway fact/object_set 探针；K1–K70 加深证据保留；**停止**无等级 default mop 作为 Core 条件；未宣称全域 0 泄漏 / N09 certified | Core 足够；全域深度开放 | 跨租户套件门槛门 + `phase2-cross-tenant-unified-gateway-evidence.md` |
| N13/校准 | ECE/`high_precision` 门槛 + 查询路径封顶（fact gateway）；Core 不以校准为阻塞；未达标诚实封顶 medium；非真实 ECE 训练 / 非 certified | 至 N13 全量/准确率宣称 | 附录 O + `phase2-calibration-pipeline-evidence.md` |
| N23/OCS | DomainRouter 企业域扫描 + 词汇预注册 + 门槛地板；属 Operational；非企业全域完整 / 非 certified | 至 N23 全量/签字 | §13.4 + `phase2-ocs-enterprise-scan-evidence.md` |
| N04/N12 | 写入硬门+transition + 配置驱动 reviewer 角色门（publish）；非部署 RBAC 真源 / 非 certified | 至 N04/N12 全量/签字 | source_policy + `phase2-reviewer-rbac-evidence.md` |
| N05 | 三分类 rebuild_mode+reason + Fact→Wiki 派生页有条件重建；非 wiki_engine/FTS 全量 / 非 certified | 至 N05 全量/签字 | rebuild-taxonomy + `phase2-wiki-rebuild-evidence.md` |
| N10 | 附录 O 校准门槛 + 域级 Exact-match gold 流水线（DomainRouter/显式域）；非 LLM judge / 非准确率宣称 / 非 certified | 至 N10 全量/签字 | calibration + `phase2-knowledge-gold-eval-evidence.md` |
| N17 | 记录级语义运行时权威（validate/transition/FactLedger scan）；非 reference_policy 替换 / 非 semantic_cases 全量对 Fact Store / 非 certified | 至 N17 全量/签字 | `phase2-record-semantics-evidence.md` |
| N18 | 实现方 5 探针 + 部署侧 RBAC 真源（禁 reference_policy 作权威）；非召回/聚合/导出/缓存全路径 / 非 certified | 至 N18 全量/签字 | implementer-semantics + `phase2-deployed-rbac-evidence.md` |
| N19 | customer_action before/after + Fact/Query 统一审计快照；非热路径强制落盘 / 非 N24 总线全量 / 非 certified | 至 N19 全量/签字 | action-execution + `phase2-fact-query-audit-evidence.md` |
| N20 | L1+审批 + 知识面 L1>L2>L3 约束栈；非全域强制分层 / 非 Lv4 / 非 certified | 至 N20 全量/签字 | g2/function/action + `phase2-constraint-layers-evidence.md` |
| N21 | OCS/校准诚实锁 + Fact/object_set + Wiki/KB 查询形 + MaterialsChat RAG/trivial/cache_hit + GraphRAG 信封 abstain；非 list API 改写 / 非 certified | 至 N21 全量/签字 | ocs/calibration + `phase2-query-abstain-citations-evidence.md` |
| N07/N22 | ObjectSet + link.traverse ACL + 嵌套 filter + 配置驱动角色×动作轴；非 Wiki/KB 全入口 / 非部署 RBAC 真源 / 非 certified | 至 N07/N22 全量/签字 | ABox ACL + `phase2-objectset-filter-evidence.md` + `phase2-role-action-matrix-evidence.md` |
| N08 | Registry Policy/Approval/Audit + kill switch；require_approval 强制入队；Lv4 误报门 v2（禁 0 样本假绿 + rollback）；非全量 Action Lv4 / 非 certified | 至 N08 全量/签字 | ActionRegistry + `phase2-action-policy-audit-evidence.md` + `phase2-lv4-false-positive-gate-evidence.md` |
| N11/N14 | 本地双写对账 + 作业级切写授权（token）+ Raw↔Fact↔Index 全链路 deepen；非生产切写认证 / 非 certified | 至 N11/N14 全量/签字 | migration + cutover-auth + `phase2-raw-fact-index-reconcile-evidence.md` |
| N24 | Package + Fact/Claim/Source revision + restore + audit + 审批式 restore + ActionExecution 桥接 + HTTP + 管理端薄 UI + 只读统一视图 + 统一审计 UI + 写总线 + Package/Action 热路径 + ActionStore 合流 + 物理 tenant_id + 存量回填；非 certified | 至 N24 全量加深 | 见 revision 系列 + `phase2-unified-audit-action-store-tenant-backfill-evidence.md` |
| SLO | 目标已登记；遥测已接线；生产达标未宣称 | 开放 | 本 ADR + `phase2-slo-target-evidence.md` + `phase2-slo-telemetry-wiring-evidence.md` |

权威条目 note 以 [`n24-conformance-catalog.yaml`](./n24-conformance-catalog.yaml) 为准；本表为人读汇总。  
未进本表、但仍有 catalog note 深度缺口的 exists 项，见 [`phase2-catalog-honesty-triage.md`](./phase2-catalog-honesty-triage.md)（仍开放 / 已过时 / 并入既有刀）。

## 检查表

| Gate 条件 | 状态 | 证据 |
|-----------|:----:|------|
| catalog `exception_adr` path 非空且文件存在 | pass | catalog 槽位 |
| 结构门无 explicit-missing warning | pass | conformance pack 测 |
| certified 恒 false | pass | honesty |

## 明确未做

- 例外自动过期/关闭工作流
- 用本包冒充附录 N 全量符合或风险已接受签字
