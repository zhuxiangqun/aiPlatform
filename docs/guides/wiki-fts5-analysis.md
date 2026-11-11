# Wiki FTS5 CJK 中文分词分析

> 调查日期: 2026-06 | 版本: v2.6

## 问题

`fts_search("记忆系统")` 返回 0 条结果。`unicode61` tokenizer 无法识别 CJK 字符，默认按空格分词。

## 环境

- SQLite: 3.51.0
- ICU tokenizer: ❌ 不支持 (`ENABLE_ICU` 编译选项不存在)
- FTS5 已启用 (`ENABLE_FTS5=1`)

## 调查结果

### 方案 A: ICU tokenizer

```sql
CREATE VIRTUAL TABLE wiki_fts USING fts5(x, tokenize='icu');
```

**结果**: ❌ `no such tokenizer: icu`

需要 SQLite 编译时启用 `ENABLE_ICU=1`。当前默认安装不支持。

### 方案 B: jieba 预分词

对中文文本在入库前用 `jieba.cut()` 分词，空格分隔后存入 FTS5（仍用 unicode61）。

```python
import jieba
text = "记忆系统采用分层架构"
tokens = ' '.join(jieba.cut(text))  # "记忆 系统 采用 分层 架构"
```

**可行性**: ✅ 代码改动量小（在 `fts_index_pages()` 中添加 jieba 分词步骤）

**缺点**: 需引入 `jieba` 依赖（约 15MB），增加分词开销

### 方案 C: 接受现状

当前检索公式中，语义检索（embedding cosine similarity）占 85% 权重，FTS5 仅占 15% 权重。中文语义检索已足够覆盖中文查询需求。FTS5 主要用于英文关键词精确匹配。

**可行性**: ✅ 零改动

## 决策

**采纳方案 C（接受现状）**。

原因：
1. ICU 不可用，重编译 SQLite 成本高
2. jieba 引入额外依赖，ROI 低（FTS5 仅占 15% 权重）
3. 语义检索（85%）已覆盖中文查询需求
4. Golden 回归 8/8 (100%) 验证检索质量达标

## 后续

如果未来需要提升中文关键词检索精度，按优先级：
1. 优先方案 B（jieba 预分词，1h 实现）
2. 备用方案 A（重新编译 SQLite + ICU，需运维配合）
