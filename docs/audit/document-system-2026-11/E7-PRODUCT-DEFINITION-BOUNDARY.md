---
doc_type: Report
---

# E7 产品定义与 reports 边界

## 1. 结论

`reports/five-products/` 不应同时承担：

- 产品定义；
- 运行证据；
- 产品 ADR；
- 历史快照。

本轮把 **模块定义** 移到 `docs/products/`。

## 2. 已移动

```text
docs/products/five-products/modules/
→ docs/products/five-products/modules/
```

包含：

- aiplat
- diagnosis
- evaluation
- fde
- ontology
- pi

## 3. 保留在 reports/

```text
reports/five-products/ops/       运行证据/收口
reports/five-products/contracts/ 产品契约证据
reports/five-products/ADR-*      决策/方案
reports/five-products/*.md       方案/报告/快照
```

## 4. 边界

```text
产品定义/模块边界 → docs/products/
运行证据/收口     → reports/
决策              → reports/ 或 docs/decisions/
```

## 5. 验证

- 维护区断链 0；
- 产品模块入口可解析；
- 运行证据仍保留在 reports/。
