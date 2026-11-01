# Staging review — 事件驱动（停日历空转）

- decided_at: `2026-11-01`
- decision: **停止按日历排复审**（已连续 11-08 / 11-15 / 11-22 三次 `continue_defer`）
- `staging_ready`: **false**（不变）
- 工程环境：Option B 本机 · [`OPTION_B_LOCAL_VM.md`](./OPTION_B_LOCAL_VM.md)

## 为何改

无独立主机时，固定日期复审只会重复：无 DSN / OIDC / operator → `continue_defer` → 再开下一份草稿。  
本地工程已冻结；再排 11-29 空审 = 文档 churn，不推进生产。

## 触发条件（任一满足才开审）

| # | 触发 | 最低证据 |
|---|------|----------|
| 1 | 独立主机候选登记 | 主机名 / 所有者 / 与开发隔离说明 |
| 2 | 预发 PG DSN 可用 | TLS；非 `127.0.0.1:5433` |
| 3 | 预发 OIDC issuer 可达 | client + 测试用户路径 |
| 4 | operator + 变更窗口 + 回滚书面 | 一段话即可入库 |

齐套后再填 [`STAGING_READY.md`](./STAGING_READY.md) 四项 → 新建当日 `STAGING_REVIEW_YYYY-MM-DD.md` Outcome。  
供给步骤备查：[`STAGING_PROVISIONING.md`](./STAGING_PROVISIONING.md)（**不买服务器**；旧本/免费云）。

## 未触发时

- **不**新建下一日历复审草稿  
- **不**手改 checklist / authorize  
- 保持 [`LOCAL_DEFER.md`](./LOCAL_DEFER.md) + Option B  
- 11-29 草稿：**作废**（见 [`STAGING_REVIEW_2026-11-29.md`](./STAGING_REVIEW_2026-11-29.md)）

## 历史空转（保留证据）

| 日期 | 结论 |
|------|------|
| 2026-11-08 | continue_defer |
| 2026-11-15 | continue_defer |
| 2026-11-22 | continue_defer |
