---
doc_type: Report
---

# Batch 02 事实审核台账

## 范围

```text
docs/contracts/ 剩余 10 份
```

## 结果

```text
pass 4 / fix 6 / needs-owner 0
```

累计 contracts：

```text
36/36 已审核
pass 33 / fix 7（已修复）/ needs-owner 3
```

## 已修复

| 文档 | 问题 | 修复 |
|---|---|---|
| `FDE_DECISION_RECORD.md` | D3 仍写 canonical + alias，Phase 3 再废弃 | 改为 canonical only；alias 已于 2026-09-15 移除 |
| `FDE_GUARD_REGISTRY_LANDING.md` | AST check 标成 warning；accept_order 别名仍写已执行 | 改为 error；alias 已移除 |
| `FDE_WORKBENCH_CONTRACT.md` | Phase 2 勾选项仍含 legacy 别名 | 注明 alias 已移除、D3 关闭 |
| `FDE_USAGE_SIGNAL_MINIMAL_SET.md` | API 契约标题写“待实施”，正文和路由已落地 | 改为“已实施” |
| `FDE_ONTOLOGY_AGENT_OPS_MANUAL.md` | 域创建路径写成 `/api/core/ontology/domains`（4 处） | 改为 `/api/core/wiki/ontology/domains` |
| `ORG_L5_PILOT_SPEC.md` | goal_id 写成 `it-ops.alert_closure.weekly` | 改为实际种子 `goal-it-ops-alert-sla` |

## 根因

```text
A. accept_order 别名移除只记录在 deprecation 文档，其他 FDE 契约未同步
B. ontology 域创建 API 路径迁移了一个 segment，manual 未同步
```

## 结论

```text
contracts：全部审核完成
fix：全部修复
needs-owner：3 份（客户签收/签名/人工签核）
```
