# Staging review checklist — 2026-11-22

> 承继 [`STAGING_REVIEW_2026-11-15.md`](./STAGING_REVIEW_2026-11-15.md)（**continue_defer**）。  
> **禁止**本机 Docker 冒充 staging / 手改 🟨→✅ / 假 DSN·OIDC。

## Pre-work（复审前）

| # | 准备项 | 状态（开审时） |
|---|--------|----------------|
| 1 | 独立主机候选（旧笔记本 / 闲置机 / 免费云） | **无候选**（不买服务器） |
| 2 | 按 [`STAGING_PROVISIONING.md`](./STAGING_PROVISIONING.md) 装 PG+Keycloak | **not_started** |
| 3 | 填 [`STAGING_READY.md`](./STAGING_READY.md) 四项 | 全 **未齐** |
| 4 | operator / 变更窗口 / 回滚预案书面 | **未提交** |
| 5 | 冻结自检绿 | **PASS** · `ops_engineering_freeze_check.sh` |
| 6 | 本地门禁 | **PASS** · authorize 全 REFUSE |
| 7 | G0 CI | **PASS** · 锚点见 [`G0_CLOSEOUT.md`](../G0_CLOSEOUT.md) |

## Decision tree（复审日）

1. 四项 STAGING_READY 是否齐？  
   - **否** → 再 `continue_defer`；写下次 `review_by`；Option B 继续。  
   - **是** → 置 `staging_ready=true` 仅当证据齐 → kickoff → live → sign → checklist ✅ → authorize。

## Outcome（提前开审 · 2026-11-01）

- reviewed_at: `2026-11-01T13:03+08:00`（按 11-22 清单提前开审；用户明确 **继续 defer**）
- decision: **`continue_defer`**
- staging_ready: **`false`**（不变）
- next_review_by: **`2026-11-29`**
- freeze_check: **PASS**
- authorize: 四轨 **REFUSE**；`ready_to_authorize=false`
- kickoff: `ops_pgha_live_kickoff.sh`（`AIPLAT_LIVE_DRILL_ENV=local`）→ **`can_record=false`**

### STAGING_READY 四项核对

| # | 项 | 结果 | 证据 |
|---|----|------|------|
| 1 | Staging Postgres DSN | **FAIL** | 仅 Option B `127.0.0.1:5433` ≠ 独立预发 |
| 2 | OIDC | **FAIL** | kickoff：`missing AIPLAT_OIDC_ISSUER` |
| 3 | Operator / 窗口 / 回滚 | **FAIL** | 无书面预发变更窗 |
| 4 | `AIPLAT_LIVE_DRILL_ENV` | **FAIL（诚实）** | 复验用 `local`；禁止伪标 `staging` |

### Notes

1. 本地工程已冻结收口；**无必须代码任务**。  
2. 不买服务器、不实施供给包。  
3. 工程环境仍为 Option B：`bash scripts/ops_option_b_all.sh`。  
4. 下次复审：**2026-11-29**（[`STAGING_REVIEW_2026-11-29.md`](./STAGING_REVIEW_2026-11-29.md)）。

### Explicitly not done

- no `staging_ready=true`
- no host provisioned / no server purchase
- no checklist 🟨→✅
- no `production_signed` / authorize
