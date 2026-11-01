# Staging review checklist — 2026-11-15

> 承继 [`STAGING_REVIEW_2026-11-08.md`](./STAGING_REVIEW_2026-11-08.md)（**continue_defer**）。  
> **禁止**本机 Docker 冒充 staging / 手改 🟨→✅ / 假 DSN·OIDC。

## Pre-work（复审前可做）

| # | 准备项 | 状态 |
|---|--------|------|
| 1 | 独立主机候选（旧笔记本 / 闲置机 / 免费云） | **未提供**（本轮明确续 defer） |
| 2 | 按 [`STAGING_PROVISIONING.md`](./STAGING_PROVISIONING.md) 装 PG+Keycloak | **not_started** |
| 3 | 填 [`STAGING_READY.md`](./STAGING_READY.md) 四项 | 当前全 **未齐** |
| 4 | operator / 变更窗口 / 回滚预案书面 | **未提交** |
| 5 | 冻结自检绿 | **PASS** · `ops_engineering_freeze_check.sh` |

## Decision tree（复审日）

1. 四项 STAGING_READY 是否齐？  
   - **否** → 再 `continue_defer`；写下次 `review_by`；Option B 继续。  
   - **是** → 置 `staging_ready=true` 仅当证据齐 → kickoff → live → sign → checklist ✅ → authorize。

## Outcome（提前开审 · 2026-11-01）

- reviewed_at: `2026-11-01T11:12+08:00`（按 11-15 清单提前开审；决策 **继续 defer**）
- decision: **`continue_defer`**
- staging_ready: **`false`**（不变）
- next_review_by: **`2026-11-22`**
- freeze_check: **PASS**
- authorize: 四轨 **REFUSE**；`ready_to_authorize=false`
- kickoff: `ops_pgha_live_kickoff.sh`（`AIPLAT_LIVE_DRILL_ENV=local`）→ **`can_record=false`**

### STAGING_READY 四项核对

| # | 项 | 结果 | 证据 |
|---|----|------|------|
| 1 | Staging Postgres DSN | **FAIL** | 无独立预发 DSN；本机 `:5433` = Option B，不计 staging |
| 2 | OIDC | **FAIL** | kickoff blocker：`missing AIPLAT_OIDC_ISSUER` |
| 3 | Operator / 窗口 / 回滚书面 | **FAIL** | 未提交独立预发变更窗口/回滚预案 |
| 4 | `AIPLAT_LIVE_DRILL_ENV` | **FAIL（诚实）** | 复验用 `local`；**禁止**标 `staging` 冒充就绪 |

### Notes

1. 用户明确 **继续 defer**；不买服务器；不启动供给包安装。  
2. 工程环境仍为 Option B：`bash scripts/ops_option_b_all.sh`。  
3. 下次复审：**2026-11-22**（[`STAGING_REVIEW_2026-11-22.md`](./STAGING_REVIEW_2026-11-22.md)）；届时仍无独立预发 → 再续。  
4. 供给包草稿仍保留备查：[`STAGING_PROVISIONING.md`](./STAGING_PROVISIONING.md)（**不实施**直至有主机）。

### Explicitly not done

- no `staging_ready=true`
- no checklist 🟨→✅
- no `production_signed=true`
- no `*_authorize` success
- no staging host provisioned
