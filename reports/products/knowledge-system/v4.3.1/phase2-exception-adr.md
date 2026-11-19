---
doc_type: Report
title: Phase 2 — 知识系统符合性例外 ADR 包（Batch F1 §9.4 exception_adr 槽位）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
standard: docs/standards/knowledge-system/v4.3.1/normative-appendix.md §N
---

# Phase 2 / 例外 ADR 包（Batch F1）

> 实施权威：附录 N 认证证据包 `certification_slots.exception_adr` 最小填空。  
> **集中登记当前例外**；**非**全量 ADR 体系；试点 Core（朱鸿林）+ Extended（朱莹）+ Operational（朱莹）+ 全量（朱向群，conditional）已批准；SLO 目标已登记且遥测已接线（非生产达标）。  
> 2026-11-19：Core 12 / Extended 6 / Operational 6 均按附录 N.2–N.4 标为等级 scoped `exists`；N09 **探针集冻结**；深度缺口记为后续加深，不阻塞已开徽章。

## 例外清单（范围 / 期限 / 补偿）

| ID | 范围 | 期限 | 补偿 |
|----|------|------|------|
| N01 | FactLedger 读时 hash + DataSourceConfig content_hash→Raw；非全连接器矩阵 | 至 N01 全量/试点签字 | 见 `phase2-raw-integrity-evidence.md` + `phase2-datasource-raw-evidence.md` |
| N03 | Claim 证据硬门+冲突记录最小切片；非全量 Claim 状态机 | 至 N03 全量加深 | suite/gate；见 `phase2-claim-evidence-evidence.md` |
| N06 | FactLedger F.1 契约；非统一 Query Gateway | 至 Gateway 统一入口 | confidence_factors + 契约门 |
| N09 | Core 探针集已冻结（`n09_core_probe_freeze`）；K1–K70 加深证据保留；**停止**无等级 default mop 作为 Core 条件；未宣称全域 0 泄漏 / N09 certified | Core 足够；全域深度开放 | 跨租户套件门槛门 + `phase2-core-cert-path-evidence.md` |
| N13/校准 | ECE/`high_precision` 保守默认；Core 不以校准为阻塞；未达标诚实封顶 medium | 至 Operational 校准流水线 | 附录 O + ADR |
| N23/OCS | 阈值须预注册；属 Operational，非 Core 阻塞 | 开放 | 白皮书 §13.4 |
| N04/N12 | 写入硬门+transition；非 reviewer RBAC | 开放 | source_policy + fact_state_machine |
| N07/N22 | ObjectSet + link.traverse + retrieve/KB/CRAG + 裸 Wiki/GraphRAG + OKF/OWL/suggestions/offline 导出字段 ACL + EvolutionRunner + platform auto 身份透传 + 字段/ABox ACL 薄 UI + DELETE + preview + H.1 condition 等值/$eq/$ne/$in + masked_properties + apply/list_h1_policy；非 certified/非表达式语言/非完整策略编辑器 | 开放 | ABox ACL + … + apply + `phase2-abox-acl-h1-list-evidence.md` |
| N11/N14 | 本地双写对账；切写未授权 | 开放 | migration 演练 |
| N24 | Package + Fact/Claim/Source revision + restore + audit + 审批式 restore + ActionExecution 桥接 + HTTP + 管理端薄 UI + 只读统一视图 + 统一审计 UI + 写总线 + Package/Action 热路径 + ActionStore 合流 + 物理 tenant_id + 存量回填；非 certified | 至 N24 全量加深 | 见 revision 系列 + `phase2-unified-audit-action-store-tenant-backfill-evidence.md` |
| SLO | 目标已登记；遥测已接线；生产达标未宣称 | 开放 | 本 ADR + `phase2-slo-target-evidence.md` + `phase2-slo-telemetry-wiring-evidence.md` |

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
