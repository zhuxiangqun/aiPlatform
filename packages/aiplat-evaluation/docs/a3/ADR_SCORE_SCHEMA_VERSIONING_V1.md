# ADR：评测 score schema 版本与历史兼容（P1a）

> **状态**：Accepted（2026-11-05）  
> **范围**：package `aiplat-evaluation` 工程计分；不打开 `accuracy_claim`  
> **关联**：[ADR_CANONICAL_RUNNERS_V1](./ADR_CANONICAL_RUNNERS_V1.md) · [P1_CANONICAL](./P1_CANONICAL.md) · [P1_DIMENSIONS](./P1_DIMENSIONS.md)

## 决策

1. **Schema 字符串**（结果信封）：  
   - `eval.scoring.semantics.v1` — runner `scoring` 块  
   - `eval.scoring.composite.v1` — composite 块（外层 schema 名保持稳定）  
   - 语义变更用 **`policy.composite_version`**（当前 **`v1.1`**：`text_quality` report-only）区分，避免静默改写历史 JSON schema 名导致解析器全挂。

2. **何时升 `composite_version`（v1.x）**：metric_role / 族权重 / 归一化规则变更，导致同输入可能得到不同 `score`。  
3. **何时升外层 schema（v2）**：字段删除/重命名、或无法向后兼容读取。须迁移说明 + 影子运行。  
4. **历史报告**：不静默重算；趋势图默认只比相同 `composite_version`；跨版本标「不可直接比较」。  
5. **门禁**：新版本影子运行 + 差异分析前，不替换旧 gate 口径。  
6. **Central `legacy_7dim`**：永久 report-only；与 package composite **永不**混加权。

## 当前登记

| 版本 | 要点 |
|---|---|
| composite v1 | groundedness gold-gated；text_quality 曾 scored |
| composite **v1.1** | `text_quality` → report-only smoke；其余 scored 规则同 v1 |

## 非目标

≠ G2b accuracy schema · ≠ 自动回填历史分 · ≠ 删除 legacy Central 字段
