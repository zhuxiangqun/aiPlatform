# 人侧剩余项 — 工程已就绪清单（2026-11-05 / 再确认 2026-11-06）

> 日收口：[EVAL_P1B_HUMAN_TRACK_CLOSEOUT_2026-11-05.md](./EVAL_P1B_HUMAN_TRACK_CLOSEOUT_2026-11-05.md)

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| 1 | A1 生产 | **长期搁置** `blocked_not_released` | 2026-11-06 再确认**无公网**；有域名/主机再开；**勿用隧道顶生产** |
| 2 | G2b 31–100 | ✅ 关闭 | scoped · claim=false · freeze ✅ |
| 3 | Arena pilot | ✅ 关闭（含 QA fail 留档） | smoke 未替换；重跑用 `for_annotators/` |

## 本轮结论

P1b 人侧可做项已做完。唯一未解除项是 A1 生产，属资源阻塞，不是工程欠账。

## 诚实锁

`accuracy_claim=false` · 本地 A1 ≠ 生产 A1 · Arena QA fail ≠ gate · `process_split_authorized=false`
