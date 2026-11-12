---
doc_type: Report
---

# E5 FDE 内容边界与去重

## 1. 结论

FDE 目录不是一组同义文档，而是：

```text
01-04  任务指南/操作
05     方法论
06     标准交付 SOP
templates/  模板正文
contracts/  规范契约
```

## 2. 本轮去重

### `02-fde-delivery.md`

删除了重复的：

- 交付手册模板结构；
- 行前检查清单表。

改为指向：

```text
templates/fde-delivery-manual.md
```

保留：

- FDE 八步操作；
- 各阶段输出模板索引。

### `05-fde-implementation-process.md`

删除了重复的：

- 交付手册模板结构；
- 10 个模板的重复列表；
- 旧 `docs/manuals/fde/` 路径。

改为指向：

```text
templates/fde-delivery-manual.md
02-fde-delivery.md §七
```

## 3. 保留边界

```text
02  = 日常交付操作
05  = 方法论
06  = 标准交付 SOP
模板 = 模板正文
契约 = 工作台规范
```

## 4. 验证

- 维护区断链 0；
- 模板正文唯一；
- 02/05 不再复制模板结构。
