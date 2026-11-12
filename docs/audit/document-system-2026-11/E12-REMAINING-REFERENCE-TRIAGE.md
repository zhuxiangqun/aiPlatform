---
doc_type: Report
---

# E12 剩余旧引用分类

## 1. 最新结果

```text
active_docs=810
missing_paths=173
stale_tokens=32
stale_numbers=1
```

E11 清理后，又修正了 5 份活跃文档中的明确失效路径：

```text
docs/knowledge-system.md → docs/guides/knowledge/knowledge-system.md
docs/manuals/fde/fde-delivery-manual.md → docs/guides/fde/templates/fde-delivery-manual.md
docs/contracts/ONTOLOGY_EXECUTABLE_MODEL.md → docs/contracts/_archive/ONTOLOGY_EXECUTABLE_MODEL.md
```

## 2. 剩余分类

| 类别 | 说明 | 处理 |
|---|---|---|
| 迁移/分类记录 | `CLASSIFICATION.md` 等有意保留旧→新映射 | 保留 |
| 历史报告 | 报告中的旧路径/旧数字 | 保留 |
| 已归档契约 | 指向 archive 的旧路径 | 按需补链 |
| 已删除脚本/模块 | 旧脚本路径已不存在 | 保留或标历史 |
| 生成物旧文本 | 白皮书历史版本中的旧链接 | 保留 |
| 旧目录 token | 文档叙述中的 `docs/whitepaper` 等 | 不自动替换 |

## 3. 结论

```text
自动安全替换：已完成
剩余 173 条：以历史/迁移材料为主
继续自动替换会制造错误或破坏历史记录
```

## 4. 验证

```text
维护区断链：0
doc_type：全部有效
```
