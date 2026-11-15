---
doc_type: Index
doc_id: README_F42DA7
last_reviewed: 2026-11-15
status: active
authority: supporting
---
# Decisions（ADR）索引

> v2.4 顶层决策目录。架构 ADR 正文在 `architecture/`；旧 `docs/architecture/decisions/` 仅保留跳转 stub。

## 目的

记录已接受的架构、产品、安全、流程决策，采用 ADR 形式：

- 背景；
- 决策；
- 替代方案；
- 后果；
- supersedes / superseded_by。

## 目录

```text
docs/decisions/
  architecture/
  product/
  security/
  process/
```

## 架构 ADR（当前）

| 文档 | 说明 |
|------|------|
| [architecture/aiplat-l4-autonomy-assessment-v1.0.0.md](architecture/aiplat-l4-autonomy-assessment-v1.0.0.md) | 自主性 L 级定级 |
| [architecture/ADR-EVAL-CAPABILITY-CASE-PACK-V1.md](architecture/ADR-EVAL-CAPABILITY-CASE-PACK-V1.md) | Eval 能力驱动 Case Pack |
| [architecture/evaluator_calibration.md](architecture/evaluator_calibration.md) | Evaluator 自校准（设计归档） |
| [architecture/tot_reserve.md](architecture/tot_reserve.md) | ToT 延期决策 |

## 状态

- 本目录为 v2.4 目标结构；
- 架构 ADR 正文已迁入 `architecture/`（2026-11-15）；
- 新增 ADR 应写入本目录对应分类。
