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
| [phase0-conformance-gap-n24.md](./phase0-conformance-gap-n24.md) | 附录 N 24 项差距表 |
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

试点域：`lock-service` · 目标等级：Core（未达成）· G0/G1/G2 测量通过 ≠ 附录 N 全量符合。
