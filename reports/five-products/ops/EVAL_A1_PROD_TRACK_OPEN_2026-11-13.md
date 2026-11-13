---
generated_at: 2026-11-13
doc_type: Report
---

# A1 生产轨解冻 — OPEN（2026-11-13）

> **状态**：🔓 **Open · awaiting formal BASE**  
> **授权**：产品负责人聊天确认「1、2、3都要做」（G2b claim / Arena QA / A1·P2-4）  
> **诚实**：本文件 = 解冻授权 + 签认工作稿入口；**≠** 生产已发布；**≠** `process_split_authorized=true`

## 相对前序决策

| 文档 | 本批关系 |
|------|----------|
| [EVAL_A1_SCOPE_DECISION_LOCAL_SUFFICIENT_2026-11-06.md](./EVAL_A1_SCOPE_DECISION_LOCAL_SUFFICIENT_2026-11-06.md) | **被本解冻覆盖范围意图**（本地仍有效作历史联调证据；生产轨不再 Parked） |
| [ENGINEERING_UNFREEZE_EVAL_A1_PROD.md](./ENGINEERING_UNFREEZE_EVAL_A1_PROD.md) | 门禁归档指针；本批以本文为现行 OPEN 记录 |
| [EVAL_A1_DEPLOY_SIGNOFF_prod_OPEN_2026-11-06.md](./EVAL_A1_DEPLOY_SIGNOFF_prod_OPEN_2026-11-06.md) | 签认工作稿（归档）；继续使用其检查表，填正式 BASE 后执行 |

## 允许

- 预填/更新生产签认稿、核对 `EvalCenter` TABS、记录构建 SHA  
- 对**正式** BASE（https 非 localhost / 已批内网正式 UI）执行 curl/浏览器验收  
- 结论诚实勾选 `pass` / `blocked_not_released` / `fail`

## 禁止

- 隧道 / 本机冒充生产 BASE  
- 无 BASE 却勾 `pass`  
- 静默翻 `process_split_authorized`  
- 把本解冻写成「生产已发布」

## 当前阻塞

1. **正式 BASE URL 未提供** → 签认结论暂为 `blocked_not_released`  
2. §1–§5 全过 + §6 三人签（发布 / infra / QA）待正式环境执行  

## 出口

| 项 | 门槛 |
|----|------|
| 正式 BASE | 非 `localhost` |
| 签认落盘 | `EVAL_A1_DEPLOY_SIGNOFF_prod_<date>.md` 结论 `pass` 或诚实 blocked/fail |
| process_split | **仍 false**（另见 P2-4） |

## 下一步（需你提供）

请回复正式 BASE，例如：`https://eval.example.com`（或已批准内网正式 UI）。收到后按签认表跑 §1–§5 并更新结论。
