---
doc_type: Report
title: Phase 0/2 — 附录 N 24 项符合性差距表（刷新）
status: active
authority: supporting
measured_at: 2026-11-19
pilot_domain: lock-service
standard: docs/standards/knowledge-system/v4.3.1/normative-appendix.md §N
catalog: reports/products/knowledge-system/v4.3.1/n24-conformance-catalog.yaml
---

# 附录 N 24 项差距表（2026-11-19 刷新）

> 状态：`exists` / `partial` / `missing`。  
> **无一项勾选为「已符合认证」**；Core 的 `exists` = **Core-scoped exists**（附录 N.2），≠ 签字认证。  
> **机器可读 SSOT**：[`n24-conformance-catalog.yaml`](./n24-conformance-catalog.yaml)（本表为人读摘要；含 `level`）。  
> 证据包：`build_conformance_pack` / `evaluate_core_ready_gate`（见 `phase2-core-cert-path-evidence.md`）。

| # | 要求（附录 N） | level | 状态 | 证据（摘要） | Phase |
|---|---------------|:-----:|:----:|--------------|:-----:|
| 1 | Raw 不可变 | core | exists | Core-scoped；读时验 + DataSourceConfig→Raw | W1 |
| 2 | 语义模型版本化 | core | exists | Core-scoped；域 YAML version + Package 切片 | W2 |
| 3 | Fact/Claim 有 evidence | core | exists | Core-scoped；Claim 证据硬门+冲突 | W3 |
| 4 | 来源策略与冲突裁决 | core | exists | Core-scoped；写入硬门 + Conflict/transition | W3 |
| 5 | Wiki/索引有条件重建 | extended | partial | 三分类 rebuild；非 Core | W4 |
| 6 | Gateway 查询契约 | core | exists | Core-scoped；F.1 + confidence_factors | W6 |
| 7 | 权限召回前过滤 | extended | partial | ObjectSet ACL；非 Core | W6/W8 |
| 8 | 动作 Policy/Approval/Audit | extended | partial | L1+幂等；非 Core | W5/W7 |
| 9 | 跨租户 0 泄漏 | core | exists | Core-scoped；探针集冻结（`n09_core_probe_freeze`）；非全域 certified | W8 |
| 10 | 评测定义/数据集/门槛 | operational | partial | Calibration；非 Core 阻塞 | W10 |
| 11 | 迁移/回滚方案 | operational | partial | Migration 演练；非 Core | W10 |
| 12 | Fact 状态机 | core | exists | Core-scoped；边表+审计+put_fact 硬门 | W3 |
| 13 | confidence 校准规则 | operational | partial | 失败→medium；非 Core 阻塞（ADR） | W10 |
| 14 | 跨存储失败恢复/对账 | operational | partial | Migration 对账；非 Core | W10 |
| 15 | JSON Schema 与附录一致 | core | exists | 标准包 schema | — |
| 16 | 附录示例 Schema 校验 | core | exists | phase0 schema validate | — |
| 17 | 记录级语义校验 | core | exists | 参考策略用例 | — |
| 18 | 实现方语义测试 | core | exists | Core-scoped；5 探针 + gate | W10 |
| 19 | 运行时权威与审计快照 | extended | partial | ActionExecution before/after | W7 |
| 20 | L1/L2/L3 约束分层 | extended | partial | G2 / FunctionContract L1 | W7 |
| 21 | 防假绿 | core | exists | Core-scoped；OCS/校准诚实锁 | W6/W10 |
| 22 | 实例/字段级 ACL | extended | partial | ObjectSet ABox ACL | W8 |
| 23 | OCS 完整度 | operational | partial | 阈值预注册；Operational | W10 |
| 24 | 版本/变更/审计 | operational | partial | Package/revision/统一审计；非 Core | W2–W3 |

## 汇总（相对 2026-11-19 Core 路径闭合）

| 状态 | 项数 | 说明 |
|------|:----:|------|
| exists | 12 | Core 最小集 12 项均为 **Core-scoped exists**（附录 N.2；≠ 签字认证） |
| partial | 12 | Extended 6 + Operational 6 |
| missing | 0 | — |

**目标等级（记录）**：Core — `core_ready` 结构门可判定；**签字**仍依赖 `pilot-core-approval-record.pending.json`（未宣称已认证）。  
**禁止话术**：不得因 Core-scoped exists / `core_ready` 宣称「附录 N 已符合」或「试点 Core 已签字认证」。
