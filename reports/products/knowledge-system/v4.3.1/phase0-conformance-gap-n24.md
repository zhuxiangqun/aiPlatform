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
> Core/Extended 的 `exists` = **等级 scoped exists**（附录 N.2/N.3），≠ 全量认证。  
> **机器可读 SSOT**：[`n24-conformance-catalog.yaml`](./n24-conformance-catalog.yaml)。

| # | 要求（附录 N） | level | 状态 | 证据（摘要） | Phase |
|---|---------------|:-----:|:----:|--------------|:-----:|
| 1 | Raw 不可变 | core | exists | Core-scoped | W1 |
| 2 | 语义模型版本化 | core | exists | Core-scoped | W2 |
| 3 | Fact/Claim 有 evidence | core | exists | Core-scoped | W3 |
| 4 | 来源策略与冲突裁决 | core | exists | Core-scoped | W3 |
| 5 | Wiki/索引有条件重建 | extended | exists | Extended-scoped；三分类 rebuild | W4 |
| 6 | Gateway 查询契约 | core | exists | Core-scoped | W6 |
| 7 | 权限召回前过滤 | extended | exists | Extended-scoped；ObjectSet ACL | W6/W8 |
| 8 | 动作 Policy/Approval/Audit | extended | exists | Extended-scoped；L1+幂等 | W5/W7 |
| 9 | 跨租户 0 泄漏 | core | exists | Core-scoped；探针冻结 | W8 |
| 10 | 评测定义/数据集/门槛 | operational | partial | Calibration；Operational | W10 |
| 11 | 迁移/回滚方案 | operational | partial | Migration；Operational | W10 |
| 12 | Fact 状态机 | core | exists | Core-scoped | W3 |
| 13 | confidence 校准规则 | operational | partial | Operational（ADR） | W10 |
| 14 | 跨存储失败恢复/对账 | operational | partial | Operational | W10 |
| 15 | JSON Schema 与附录一致 | core | exists | 标准包 | — |
| 16 | 附录示例 Schema 校验 | core | exists | phase0 | — |
| 17 | 记录级语义校验 | core | exists | 参考策略 | — |
| 18 | 实现方语义测试 | core | exists | Core-scoped | W10 |
| 19 | 运行时权威与审计快照 | extended | exists | Extended-scoped；Action before/after | W7 |
| 20 | L1/L2/L3 约束分层 | extended | exists | Extended-scoped；L1 硬门 | W7 |
| 21 | 防假绿 | core | exists | Core-scoped | W6/W10 |
| 22 | 实例/字段级 ACL | extended | exists | Extended-scoped；ABox ACL | W8 |
| 23 | OCS 完整度 | operational | partial | 阈值预注册；Operational | W10 |
| 24 | 版本/变更/审计 | operational | partial | Package/revision；Operational | W2–W3 |

## 汇总

| 状态 | 项数 | 说明 |
|------|:----:|------|
| exists | 18 | Core 12 + Extended 6（等级 scoped；≠ 全量 certified） |
| partial | 6 | Operational 6 |
| missing | 0 | — |

**目标等级**：Core `pilot_certified`（朱鸿林）；Extended `pilot_extended_certified`（朱莹）。  
**禁止话术**：不得因 scoped exists / 等级徽章宣称 24/24 或 Operational 已认证。
