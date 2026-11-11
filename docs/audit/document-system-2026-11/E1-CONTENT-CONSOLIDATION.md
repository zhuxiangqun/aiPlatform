---
doc_type: Report
---

# E1 内容去重与合并（Top 集群）

> 日期：2026-11-12  
> 范围：维护区文档；archive 只看链接，不改正文。  
> 本轮不删除正文，只归档生成快照。

## 1. 当前相似集群

| 集群 | 数量 | 判断 | 处理 |
|---|---:|---|---|
| 包级 `PERF_BASELINE.md` | 6 | 包级证据，数值不同 | 保留，已加包级标识 |
| 包级 `UAT.md` | 6 | 包级证据，验收不同 | 保留，已加包级标识 |
| `human_pack/G2B_SEND` 时间戳快照 | 7 组 | 生成证据，旧快照可归档 | 已归档 6 组，保留最新 |
| framework：`scoring-detail` / `complete-assessment` / `autonomy-framework` | 3 | 中间评估报告，不是 canonical | 已移至 `reports/framework/` |
| `ADR-DRAFT-evaluation-a3` / `ADR-DRAFT-ontology-a3` | 2 | 同批草案，主题不同 | 保留，补边界 |
| 旧 `docs/whitepaper` 生成物 | — | 已归档 | 完成 |

## 2. 本轮已执行

归档旧 human_pack 快照：

```text
packages/aiplat-evaluation/docs/a3/human_pack/20261103T125855Z
packages/aiplat-evaluation/docs/a3/human_pack/20261103T130233Z
packages/aiplat-evaluation/docs/a3/human_pack/20261103T130302Z
packages/aiplat-evaluation/docs/a3/human_pack/20261104T060000Z-n100
packages/aiplat-evaluation/docs/a3/human_pack/20261104T063000Z-n100
packages/aiplat-evaluation/docs/a3/human_pack/20261104T064000Z-n100
→ packages/aiplat-evaluation/docs/a3/_archive/human_pack/
```

保留最新：

```text
packages/aiplat-evaluation/docs/a3/human_pack/20261105T132500Z-n100
```

## 3. 待 owner 决策

### A. framework 三文档（已决定）

三份按中间报告处理：

```text
docs/reference/framework/scoring-detail.md
docs/reference/framework/aiplat-complete-assessment.md
docs/reference/framework/aiplat-autonomy-framework.md
→ reports/framework/
```

doc_type 改为 `Report`，status 改为 `historical`。原“待 owner 决策”关闭。

```text
docs/reference/framework/scoring-detail.md
docs/reference/framework/aiplat-complete-assessment.md
docs/reference/framework/aiplat-autonomy-framework.md
```

相似度接近 1.0，但角色可能不同：

- scoring-detail：评分算法；
- complete-assessment：评估叙述；
- autonomy-framework：自主性分级框架。

需要确认：

- 是否合并为一份“评估框架”；
- 还是保留“算法 / 叙述 / 分级”三份；
- 若保留，必须删除重复定义。

### B. PERF_BASELINE / UAT

包级副本可能是：

- 每包独立证据；
- 或模板复制。

需要确认：

- 独立证据 → 保留，补“包级证据”标识；
- 模板复制 → 抽公共模板，包内只保留数值差异。

### C. ADR 草案

```text
reports/five-products/ADR-DRAFT-evaluation-a3.md
reports/five-products/ADR-DRAFT-ontology-a3.md
```

主题不同，保留；补交叉边界，避免被误读为重复。

## 4. 结论

```text
生成快照：已归档
框架文档：待 owner 决策
包级模板：待确认“证据”还是“复制”
```

本轮未删除任何文档。
