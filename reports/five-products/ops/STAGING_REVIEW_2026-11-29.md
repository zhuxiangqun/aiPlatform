# Staging review checklist — 2026-11-29（草稿）

> 承继 [`STAGING_REVIEW_2026-11-22.md`](./STAGING_REVIEW_2026-11-22.md)（**continue_defer**）。  
> **禁止**本机 Docker 冒充 staging / 手改 🟨→✅ / 假 DSN·OIDC。

## Pre-work（复审前可做）

| # | 准备项 | 状态模板 |
|---|--------|----------|
| 1 | 独立主机候选（旧笔记本 / 闲置机 / 免费云） | `_TBD_` |
| 2 | 按 [`STAGING_PROVISIONING.md`](./STAGING_PROVISIONING.md) 装 PG+Keycloak | `_not_started_` |
| 3 | 填 [`STAGING_READY.md`](./STAGING_READY.md) 四项 | 当前全 **未齐** |
| 4 | operator / 变更窗口 / 回滚预案书面 | `_TBD_` |
| 5 | 冻结自检绿 | `bash scripts/ops_engineering_freeze_check.sh` |

## Decision tree（复审日）

1. 四项 STAGING_READY 是否齐？  
   - **否** → 再 `continue_defer`；写下次 `review_by`；Option B 继续。  
   - **是** → 置 `staging_ready=true` 仅当证据齐 → kickoff → live → sign → checklist ✅ → authorize。

## Outcome（复审日填写）

- reviewed_at: `_TBD_`
- decision: `_continue_defer | enter_staging_A_or_C_`
- staging_ready: `_false until conditions met_`
- notes: `_…_`
