---
doc_type: Report
title: Phase 0 — 附录 N 24 项符合性差距表
status: active
authority: supporting
measured_at: 2026-11-15
pilot_domain: lock-service
standard: docs/standards/knowledge-system/v4.3.1/normative-appendix.md §N
---

# Phase 0：附录 N 24 项差距表

> 状态：`exists` / `partial` / `missing`。  
> **无一项在本表勾选为「已符合认证」**；`exists` 仅表示有相关实现碎片。  
> 差距类型：有实现无证据 / 有数据无契约 / 有动作无门禁 / 有查询无权限 / 有 Wiki 无事实源 / 有场景写主库 / 标准包就绪 / 缺失。

| # | 要求（附录 N） | 状态 | 证据（path:line 或 FAIL） | 差距类型 | Phase 归属 |
|---|---------------|:----:|---------------------------|----------|:----------:|
| 1 | Raw 不可变 | missing | FAIL：`DataSourceConfig` 无 hash/locator（`data_source.py:30-35`） | 缺失 | W1 / P1 |
| 2 | 语义模型版本化 | partial | 域 YAML `version: "1.2.0"`（`lock-service.yaml:4`）；无附录 B 版本化 ObjectType 发布/人审流水线 | 有数据无契约 | W2 / P1 |
| 3 | Fact/Claim 有 evidence | missing | FAIL：无 Fact Store；抽取仅有 string evidence（`extractor.py:136-149`） | 有实现无证据（字符串≠记录） | W3 / P1 |
| 4 | 来源策略与冲突裁决 | missing | FAIL：无 `source_policy` / Claim 冲突裁决实现（生产知识路径） | 缺失 | W3 / P1 |
| 5 | Wiki/索引有条件重建 | partial | 写后 invalidate + rebuild（`wiki_engine.py:631-646`）；缺重建条件分类契约 | 有 Wiki 无事实源 | W4 / P2 |
| 6 | Gateway 查询契约 | missing | FAIL：无附录 M Query Gateway 统一入口；检索分散在 syscalls/KB/Wiki | 缺失 | W6 / P1–P2 |
| 7 | 权限召回前过滤 | partial | KB SQL `tenant_id=?`（`sqlite_retriever.py:325-327`）；Wiki mismatch 阻断（`wiki_retriever.py:326-331`）；非全入口 + 无字段级 | 有查询无权限（不完整） | W6 / W8 / P1 |
| 8 | 动作执行走 Policy/Approval/Audit | partial | `AsyncActionRegistry` 审批（`action_registry.py:341-359`）；`ActionContractModel`（`action_contract.py:111-116`）；知识抽取确认未强制走同一 L1 | 有动作无门禁（部分路径） | W5 / W7 / P2 |
| 9 | 跨租户 0 泄漏 | partial | 有租户分库与 mismatch 阻断（上列）；缺专项跨租户负向套件证明 0 泄漏 | 有实现无证据 | W8 / P1 |
| 10 | 评测有定义/数据集/门槛 | missing | FAIL：知识域无绑定 v4.3.1 的 gold/门槛；评测包存在但非本标准 O 节 | 缺失 | W10 / P4 |
| 11 | 迁移/回滚方案 | partial | 计划 §8 有文字方案（`knowledge-system-v4.3.1-implementation-plan.md` §8）；无已执行双写/对账/回滚演练记录 | 有数据无契约（仅设计） | W10 / P4 |
| 12 | Fact 状态机 | missing | FAIL：无 Fact review/lifecycle 状态机实现；语义校验仅在标准用例 | 缺失 | W3 / P1 |
| 13 | confidence 校准规则 | missing | FAIL：无 Calibration Report 实现/产物；附录 O 门槛未接线 | 缺失 | W10 / P4 |
| 14 | 跨存储失败恢复/对账 | missing | FAIL：无 Raw↔Fact↔Index 对账作业 | 缺失 | W10 / P3–P4 |
| 15 | JSON Schema 与附录一致 | exists | 标准包 schema 已发布；示例校验通过（`phase0-schema-validate.log`） | 标准包就绪 | —（标准） |
| 16 | 附录示例通过 Schema 校验 | exists | `validated=22 failed=0`（同 log） | 标准包就绪 | —（标准） |
| 17 | 记录级语义校验通过 | exists | `cases=30 failed=0`（`phase0-semantics-validate.log`）— **参考策略**，非实现 | 标准包就绪 | —（标准） |
| 18 | 实现方语义测试通过 | missing | FAIL：conformance README 要求真实 RBAC/Fact Store 测试尚未交付 | 缺失 | W10 / P4 |
| 19 | 运行时权威与审计快照 | partial | Action 路径有 pending_approvals / audit 痕迹（`action_registry.py`）；Fact/Query 无 before/after 权威快照 | 有实现无证据 | W7 / P2 |
| 20 | L1/L2/L3 约束分层 | partial | Action 合同 + PolicyGate 形状（`action_registry.py:637-642` soft PolicyGate 注释）；未按标准完整分层落地知识面 | 有动作无门禁 | W7 / P2 |
| 21 | 防假绿 | partial | Evidence Envelope / 评测 honesty 存在于执行层；知识查询无统一 abstain+citations 契约 | 有实现无证据 | W6 / P2 |
| 22 | 实例/字段级 ACL | missing | FAIL：KB/Wiki 主要为租户级；字段级 ACL 未在知识召回路径落地 | 有查询无权限 | W8 / P2–P3 |
| 23 | OCS 完整度 | missing | FAIL：仅标准/归档提及 OCS；无运行时完整度度量接线 | 缺失 | W10 / P4 |
| 24 | 版本/变更/审计 | partial | 域 YAML version + Action 审计碎片；无统一知识变更审计账本（Fact Revision） | 有实现无证据 | W2–W3 / P1 |

## 汇总

| 状态 | 项数 | 说明 |
|------|:----:|------|
| exists | 3 | #15–17 仅标准包 |
| partial | 10 | 有碎片，未达 Core |
| missing | 11 | Phase 1+ 主缺口 |

**目标等级（记录）**：Core（未达成）。  
**下一步**：Gate G0 后进入实施计划 Phase 1（W1–W3 + 查询最小闭环）。
