---
doc_type: Report
---

# E6 架构三文档边界

## 1. 结论

三份文档不是重复副本，而是：

| 文档 | 角色 | 是否规范 |
|---|---|---|
| `overview.md` | 全景摘要 | 否 |
| `system-architecture-contract.md` | 跨层硬约束 | 是 |
| `boundary-standard.md` | 层边界判定 | 是 |

## 2. 已修正

### `overview.md`

- 从“唯一全景入口”改为“全景摘要（非规范）”；
- 明确规范以 contract 为准；
- 明确边界以 boundary 为准。

### `system-architecture-contract.md`

- 增加 overview / boundary 的分工引用。

### `boundary-standard.md`

- 已声明父文档为 system-architecture-contract；
- 保持独立，因为被 CI/架构守卫引用。

## 3. 不再做的事

```text
不把 overview 合并进 contract
不把 boundary 合并进 contract
```

原因：

- overview 面向快速理解；
- contract 面向强制约束；
- boundary 面向归属判定，且被 CI 独立引用。

## 4. 后续规则

```text
overview 只做摘要，不新增 MUST
contract 只做规范，不复制全景叙事
boundary 只做判定，不重复 contract 全文
```
