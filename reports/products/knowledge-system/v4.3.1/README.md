---
doc_type: Index
title: 知识系统 v4.3.1 Phase 0 证据目录
status: active
authority: supporting
---

# 知识系统 v4.3.1 · Phase 0 证据

> 实施权威：[`docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md`](../../../../docs/architecture/plans/knowledge-system-v4.3.1-implementation-plan.md)  
> 标准包：[`docs/standards/knowledge-system/v4.3.1/`](../../../../docs/standards/knowledge-system/v4.3.1/)  
> **本目录是测量证据，不是第二份标准或实施方案。**

| 文件 | 内容 |
|------|------|
| [phase0-standard-pack-baseline.md](./phase0-standard-pack-baseline.md) | 标准 schema/语义校验结果（原始 `*.log` 被 `.gitignore`，以本摘要为准） |
| [phase0-asset-inventory.md](./phase0-asset-inventory.md) | 资产 / owner 盘点 |
| [phase0-conformance-gap-n24.md](./phase0-conformance-gap-n24.md) | 附录 N 24 项差距表（2026-11-16 刷新；SSOT 见 catalog） |
| [n24-conformance-catalog.yaml](./n24-conformance-catalog.yaml) | 附录 N 机器可读目录（证据包 SSOT） |
| [phase0-pilot-lock-service.md](./phase0-pilot-lock-service.md) | 试点域边界与 G0 |
| [phase1-g1-evidence.md](./phase1-g1-evidence.md) | Phase 1 G1（Fact Ledger） |
| [phase2-g2-evidence.md](./phase2-g2-evidence.md) | Phase 2 G2（L1 硬门 + Fact→Graph 可重建） |
| [phase2-wiki-readonly-evidence.md](./phase2-wiki-readonly-evidence.md) | Phase 2 Wiki 读模型硬门（试点人工写拦截） |
| [phase2-function-contract-evidence.md](./phase2-function-contract-evidence.md) | Phase 2 W5 FunctionContract（无副作用硬门 + L1） |
| [phase2-objectset-evidence.md](./phase2-objectset-evidence.md) | Phase 2 W6 ObjectSet（租户前置只读查询 + L1） |
| [phase2-agent-tool-evidence.md](./phase2-agent-tool-evidence.md) | Phase 2 W6 Agent Tool（object.query / function.call） |
| [phase2-link-traverse-evidence.md](./phase2-link-traverse-evidence.md) | Phase 2 W6 link.traverse（多跳只读 + L1） |
| [phase2-object-set-aggregate-tool-evidence.md](./phase2-object-set-aggregate-tool-evidence.md) | Phase 2 W6 object_set.aggregate 工具（只读 count） |
| [phase2-action-execute-tool-evidence.md](./phase2-action-execute-tool-evidence.md) | Phase 2 W6 action.execute 工具（ActionRegistry L1） |
| [phase2-action-execution-evidence.md](./phase2-action-execution-evidence.md) | Phase 2 W7 ActionExecution（幂等 + before/after） |
| [phase2-objectset-acl-evidence.md](./phase2-objectset-acl-evidence.md) | Phase 2 W8 ObjectSet ABox ACL（实例/字段 + 跨租户负向） |
| [phase2-scenario-evidence.md](./phase2-scenario-evidence.md) | Phase 2 W9 Knowledge Scenario（模拟不写主事实 + 合并人审） |
| [phase2-ontology-package-evidence.md](./phase2-ontology-package-evidence.md) | Phase 2 W9 Ontology Package（版本/哈希校验 + 兼容 + 依赖锁定 + 回滚） |
| [phase2-confidence-calibration-evidence.md](./phase2-confidence-calibration-evidence.md) | W10 Confidence Calibration（附录 O 门槛 + 失败降级 medium） |
| [phase2-ocs-evidence.md](./phase2-ocs-evidence.md) | W10 OCS Completeness（§13.4 覆盖计分 + 门槛门；禁节点数档位） |
| [phase2-knowledge-migration-evidence.md](./phase2-knowledge-migration-evidence.md) | W10 Knowledge Migration（双写/对账/回滚演练；切写未授权） |
| [phase2-conformance-pack-evidence.md](./phase2-conformance-pack-evidence.md) | W10 Conformance / 认证证据包（N24 目录 + §9.4 槽位；非 24/24 认证） |
| [phase2-implementer-semantics-evidence.md](./phase2-implementer-semantics-evidence.md) | W10 N18 实现方语义测试（5 探针 + 门槛门；非全量认证） |
| [phase2-source-policy-evidence.md](./phase2-source-policy-evidence.md) | W3 N04 Source Policy / Conflict（策略登记 + 冲突不自动选边 + 人审；非全写入强制） |
| [phase2-fact-state-evidence.md](./phase2-fact-state-evidence.md) | W3 N12 Fact 状态机（review/lifecycle/claim + 审计；非裸 put_fact 唯一强制） |
| [phase2-claim-evidence-evidence.md](./phase2-claim-evidence-evidence.md) | Batch F2 N03 Claim 证据硬门+冲突记录（门槛门；非全量认证） |
| [phase2-slo-target-evidence.md](./phase2-slo-target-evidence.md) | Batch F1 §9.4 SLO 目标登记（非生产遥测达标） |
| [phase2-exception-adr.md](./phase2-exception-adr.md) | Batch F1 §9.4 例外 ADR 包（partial 集中登记；非全量 ADR） |
| [phase2-datasource-raw-evidence.md](./phase2-datasource-raw-evidence.md) | Batch G1 N01 DataSourceConfig content_hash→Raw（非全连接器/非 certified） |
| [phase2-fact-revision-evidence.md](./phase2-fact-revision-evidence.md) | Batch G2 N24 Fact Revision 归档/抬号（非回滚 UI/非 certified） |
| [phase2-claim-revision-evidence.md](./phase2-claim-revision-evidence.md) | Batch H1 N24 Claim Revision 归档/抬号（非 Source/回滚 UI/非 certified） |
| [phase2-source-revision-evidence.md](./phase2-source-revision-evidence.md) | Batch H2 N24 Source Revision 归档/抬号（非回滚 UI/非 certified） |
| [phase2-revision-restore-evidence.md](./phase2-revision-restore-evidence.md) | Batch I1 N24 Revision Restore 程序化恢复（非回滚 UI/非 certified） |

试点域：`lock-service` · 目标等级：Core（未达成）· G0/G1/G2 测量通过 ≠ 附录 N 全量符合。
