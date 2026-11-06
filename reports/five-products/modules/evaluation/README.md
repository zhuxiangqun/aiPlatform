# Evaluation 产品 — 现行文档入口

> **从这里开始。** 本页是评测产品的唯一导航入口。  
> 大量 `ops/EVAL_*` 收口凭证与 `docs/a3/*` 预备稿是**历史证据**，不是产品定义，今后不要当入口读。

## 现行权威（维护区）

| 用途 | 路径 |
|------|------|
| 模块边界与接线 | [`MODULE.md`](./MODULE.md) |
| 评测协议 | [`EVAL_PROTOCOL.md`](./EVAL_PROTOCOL.md) |
| 模块清单 | [`module.yaml`](./module.yaml) |
| 产品根与范围 | [`packages/aiplat-evaluation/docs/a3/PRODUCT_ROOT_V1.md`](../../../../packages/aiplat-evaluation/docs/a3/PRODUCT_ROOT_V1.md) |
| 记分范围（非准确率） | [`packages/aiplat-evaluation/docs/a3/SCORE_SCOPE_V1.md`](../../../../packages/aiplat-evaluation/docs/a3/SCORE_SCOPE_V1.md) |
| 评审基线（2026-11-04） | [`ops/EVALUATION_PRODUCT_REVIEW_2026-11-04.md`](../../ops/EVALUATION_PRODUCT_REVIEW_2026-11-04.md) |
| 改进执行计划 | [`ops/EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md`](../../ops/EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md) |
| 能力事实（跟代码同步） | [`AIPLAT_CAPABILITIES.md`](../../../../AIPLAT_CAPABILITIES.md)（搜 Evaluation / Eval Center） |

## 平台白皮书（整平台，非评测专册）

评测**没有**单独的「技术白皮书 + 产品白皮书」成对专册。对外论证走平台五维卷：

| 卷 | 路径 | 与评测关系 |
|----|------|------------|
| 技术 | [`docs/whitepaper/volumes/01-tech-architecture.md`](../../../../docs/whitepaper/volumes/01-tech-architecture.md) | 平台技术论证；评测为子系统切片 |
| 产品 | [`docs/whitepaper/volumes/02-product-capability.md`](../../../../docs/whitepaper/volumes/02-product-capability.md) | 场景表含「评测治理」一行 |

同步：`bash scripts/sync_whitepapers.sh`（跟 CAPABILITIES，不跟每份 ops 收口）。

## 历史 / 中间文档（勿作产品定义）

| 类别 | 位置 | 说明 |
|------|------|------|
| 收口凭证（已迁） | [`ops/_archive/eval-receipts/`](../../ops/_archive/eval-receipts/) | CLOSEOUT / SIGNOFF / PARTIAL / BLOCKED 等 |
| 解冻门（已迁） | [`ops/_archive/eval-gates/`](../../ops/_archive/eval-gates/) | `ENGINEERING_UNFREEZE_EVAL_*`；原路径留 stub |
| 盘点/交接（已迁） | [`ops/_archive/eval-inventories/`](../../ops/_archive/eval-inventories/) | E1 / E3 / P1b handoff；原路径留 stub |
| A3 预备与基准稿 | `packages/aiplat-evaluation/docs/a3/` | 门禁/证据包；已收官 closeout 见 `a3/_archive/` |

完整分类：[`ops/EVAL_DOCS_LIFECYCLE.md`](../../ops/EVAL_DOCS_LIFECYCLE.md)。

## 强制边界（现行）

- `accuracy_claim=false`
- `process_split_authorized=false`（未完成拆分授权前）
- 本地 proxy / Docker sandbox ≠ 生产独立发布
