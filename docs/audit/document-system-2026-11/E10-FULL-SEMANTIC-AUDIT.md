---
doc_type: Report
---

# E10 全文语义事实审计（自动扫描）

> 日期：2026-11-12  
> 范围：809 份活跃文档（docs/reports/packages/子仓 docs）  
> 方法：自动化扫描 + 抽检；不替代逐段人工语义审计。

## 1. 扫描结果

```text
active_docs=809
root_qualified_missing_paths=259
stale_directory_tokens=77
stale_numeric_claims=1
```

## 2. 主要发现

### 2.1 旧目录引用

仍存在的旧目录 token：

```text
docs/whitepaper/
docs/manuals/
docs/API/
docs/matrix/
docs/framework/
docs/security/
docs/policy/
docs/mcp/
docs/articles/
docs/harness/
```

大部分来自：

- 迁移/分类记录（如 `CLASSIFICATION.md`）；
- 历史报告；
- 旧版本引用说明。

但部分活跃文档仍直接引用旧路径，需要后续逐篇修正。

### 2.2 根路径缺失

259 条 root-qualified 路径在仓库中不存在。  
典型类别：

```text
迁移前的 docs/whitepaper/*
迁移前的 docs/manuals/*
已归档的 contracts/ONTOLOGY_*
旧脚本/旧 schema 路径
```

其中一部分是**迁移文档刻意保留的旧→新对照**，不是错误。

### 2.3 旧数字

检测到：

```text
225 → 旧 archive 断链数
```

这是历史报告中的旧数字，当前实际为 `0`。

## 3. 抽检结论

E9 的 10 份高影响文档：

```text
数字/路径/目录断言：未发现阻断性矛盾
```

## 4. 限制

本次审计**不是全文人工事实核验**：

- 不验证商业承诺、客户案例、市场数据；
- 不验证旧截图/旧 UI；
- 不逐段判断叙述是否过时。

## 5. 结论

```text
全量自动扫描：完成
阻断性事实矛盾：未发现
旧路径/旧数字：仍有非阻断残留
全文人工语义审计：未完成
```

## 6. 建议

```text
1. 优先修正活跃文档中的旧目录引用
2. 迁移/分类记录中的旧路径保留
3. 对商业/客户类文档做人工复核
```
