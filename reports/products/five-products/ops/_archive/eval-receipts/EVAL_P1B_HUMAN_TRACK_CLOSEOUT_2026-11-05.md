---
doc_type: Archive
---

# P1b 人侧轨日收口（2026-11-05）

> 对照：EVAL_P1B_AGENT_HANDOFF.md（历史链接失效） · [EVAL_HUMAN_REMAINING_OPS_2026-11-05.md](./EVAL_HUMAN_REMAINING_OPS_2026-11-05.md)

## 今日关闭

| 轨 | 结果 | 关键数字 / 证据 |
|---|---|---|
| G2b n=100 | ✅ 双标+仲裁+κ+accuracy aggregate + **freeze 确认** + **scoped attestation** | agreement=0.90 · κ=0.7624 · pass_rate=**0.72** · §4 未达 → **claim=false** |
| Arena blind pilot | ✅ pair×30 + 双标+仲裁 + result + QA | κ=0.8459 · QA **`overall_pass=false`**（SEND 泄漏模型名）· smoke 未替换 · pack 脚本已加固分目录/守卫 |
| A1 本地 | ✅（此前已签） | 本地 ≠ 生产 |
| EET / protocol / 七卡 | ✅（此前已签） | — |

## 仍 open

| 项 | 状态 | 备注 |
|---|---|---|
| A1 生产 | `blocked_not_released` | 无公网 BASE；**勿用隧道顶生产** |
| Arena QA | ✅ 已签（fail 发现已留档） | 重跑 blind 须用新 pack（`for_annotators/`） |
| Rubric 正式签字栏 | 可选 | 非阻断 |

## 诚实锁（不变）

`accuracy_claim=false` · G2b scoped ≠ 通用准确率 · Arena blind ≠ length smoke 替换 · `process_split_authorized=false`
