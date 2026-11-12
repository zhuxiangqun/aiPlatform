---
doc_type: Report
---

# E8 内容合并收口

## 1. 扫描结果

内容合并完成后再次扫描维护区文档，剩余高相似集群全部属于已确认的“不同角色/不同证据”：

| 集群 | 相似度 | 结论 |
|---|---:|---|
| `reports/framework/` 三份报告 | 1.00 | 已统一按中间报告处理，角色不同 |
| 包级 `PERF_BASELINE` | 1.00 | 包级独立证据，不合并 |
| 包级 `uat/UAT` | 0.78 | 包级独立验收，不合并 |
| 两份 ADR 草案 | 0.86 | 不同主题，已补边界 |
| `aiPlat-infra/docs/{network,messaging,compute,memory}/index.md` | 0.78 | 模板结构相同，子系统内容独立 |

## 2. 判定

```text
没有新的未处理重复文档
```

剩余相似来自：

- 统一模板结构；
- 包级证据格式；
- 同批报告/草案的写作范式。

不是同一内容的多个权威副本。

## 3. 内容分布

```text
产品定义 → docs/products/
框架/评估报告 → reports/framework/
运行证据 → reports/five-products/ops/
标准/契约 → docs/standards/、docs/contracts/
决策 → docs/decisions/
```

## 4. 最终验证

```text
文档总数：961
doc_type：961/961
维护区断链：0
archive 断链：0
```

## 5. 结论

```text
内容合并 E1–E8：完成
剩余相似：均为已确认的不同角色/证据
不再进行合并
```
