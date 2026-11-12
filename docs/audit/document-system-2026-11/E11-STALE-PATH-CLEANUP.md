---
doc_type: Report
---

# E11 旧路径清理

## 1. 处理

对活跃文档中的旧目录路径做**存在性校验后**替换：

```text
docs/manuals/   → docs/guides/
docs/API/       → docs/reference/API/
docs/matrix/    → docs/reference/matrix/
docs/security/  → docs/reference/security/
docs/policy/    → docs/reference/policy/
docs/compliance/→ docs/reference/compliance/
docs/articles/  → docs/reference/articles/
docs/mcp/       → docs/reference/mcp/
docs/agents/    → docs/reference/agents/
docs/harness/   → docs/reference/harness/
docs/skills/    → docs/reference/skills/
docs/tools/     → docs/reference/tools/
docs/framework/ → docs/reference/framework/
docs/whitepaper/→ docs/reference/explanatory/
```

仅当目标真实存在时替换，避免制造新断链。

## 2. 结果

```text
修改文件：42
旧目录 token：77 → 33
root-qualified missing paths：259 → 178
```

## 3. 保留

以下内容**不自动替换**：

- `docs/audit/` 中的审计记录；
- `DOCUMENT_SYSTEM.md` 中的旧/新对照；
- `CLASSIFICATION.md` 中的迁移映射；
- archive/_archive 历史材料；
- 目标文件不存在的旧引用。

## 4. 剩余

```text
178 条 root-qualified 缺失路径
33 个旧目录 token
1 个旧数字（225，历史报告）
```

多数为：

- 旧版本迁移记录；
- 已归档契约；
- 历史报告中的旧路径；
- 有意保留的旧→新对照。

## 5. 验证

```text
维护区断链：0
doc_type：全部有效
```
