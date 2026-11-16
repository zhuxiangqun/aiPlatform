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
| 1 | Raw 不可变 | partial | G1 FactLedger sha256（`phase1-g1-evidence.md`） | 有实现无证据 | W1 |
| 2 | 语义模型版本化 | partial | 域 YAML version + Package 切片 | 有数据无契约 | W2 |
| 3 | Fact/Claim 有 evidence | partial | G1 published 拒空 evidence | 有实现无证据 | W3 |
| 4 | 来源策略与冲突裁决 | missing | — | 缺失 | W3 |
| 5 | Wiki/索引有条件重建 | partial | Wiki 读模型硬门 + G2 可重建 | 有 Wiki 无事实源 | W4 |
| 6 | Gateway 查询契约 | partial | FactLedger 网关 + ObjectSet；非附录 M 统一入口 | 有实现无证据 | W6 |
| 7 | 权限召回前过滤 | partial | ObjectSet 租户前置 + ACL | 有查询无权限 | W6/W8 |
| 8 | 动作 Policy/Approval/Audit | partial | ActionRegistry L1 + 幂等/快照；bypass 仍存 | 有动作无门禁 | W5/W7 |
| 9 | 跨租户 0 泄漏 | partial | ACL/Scenario 负向用例；未认证全域 0 | 有实现无证据 | W8 |
| 10 | 评测定义/数据集/门槛 | partial | Confidence Calibration 附录 O | 有实现无证据 | W10 |
| 11 | 迁移/回滚方案 | partial | Migration 双写/对账/回滚演练；切写未授权 | 有实现无证据 | W10 |
| 12 | Fact 状态机 | missing | — | 缺失 | W3 |
| 13 | confidence 校准规则 | partial | 失败/缺失 → 最高 medium | 有实现无证据 | W10 |
| 14 | 跨存储失败恢复/对账 | partial | Migration 本地 store 对账 | 有实现无证据 | W10 |
| 15 | JSON Schema 与附录一致 | exists | phase0 标准包 | 标准包就绪 | — |
| 16 | 附录示例 Schema 校验 | exists | phase0 标准包 | 标准包就绪 | — |
| 17 | 记录级语义校验 | exists | phase0 参考策略 | 标准包就绪 | — |
| 18 | 实现方语义测试 | missing | — | 缺失 | W10 |
| 19 | 运行时权威与审计快照 | partial | ActionExecution before/after | 有实现无证据 | W7 |
| 20 | L1/L2/L3 约束分层 | partial | G2 / FunctionContract L1 | 有动作无门禁 | W7 |
| 21 | 防假绿 | partial | OCS/校准诚实锁 | 有实现无证据 | W6/W10 |
| 22 | 实例/字段级 ACL | partial | ObjectSet ABox ACL | 有查询无权限 | W8 |
| 23 | OCS 完整度 | partial | §13.4 覆盖计分 + gate | 有实现无证据 | W10 |
| 24 | 版本/变更/审计 | partial | Package + Action 审计碎片 | 有实现无证据 | W2–W3 |

## 汇总（相对 2026-11-15 基线）

| 状态 | 项数 | 说明 |
|------|:----:|------|
| exists | 3 | #15–17 标准包（不变） |
| partial | 18 | W5–W10 最小切片推进后由 missing 升格 |
| missing | 3 | #4 来源策略 / #12 Fact 状态机 / #18 实现方语义套件 |

**目标等级（记录）**：Core（仍未达成）。  
**禁止话术**：不得因本表 partial 增多而宣称「附录 N 已符合」或「可认证」。
