# Staging review checklist — 2026-11-08

> 复审日决策：有真实预发 → 方案 A/C；否则 **续 defer** + 继续 Option B。  
> **禁止**本机 Docker 冒充 staging / 手改 🟨→✅ / 假 DSN·OIDC。

## Inputs

| 输入 | 路径 |
|------|------|
| staging gate | [`STAGING_READY.md`](./STAGING_READY.md) |
| defer 决议 | [`LOCAL_DEFER.md`](./LOCAL_DEFER.md) |
| handoff | [`OPS_HANDOFF.md`](../OPS_HANDOFF.md) |
| engineering freeze | [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md) |

## Decision tree

1. 是否有**独立**预发环境（非开发本机）且可填 [`STAGING_READY.md`](./STAGING_READY.md)？  
   - **否** → 续 `LOCAL_DEFER.md`；保持 `staging_ready=false`；Option B 继续工程演练。  
   - **是** → 勾齐 staging_ready 条件 → 四轨 live drill → `ops_live_sign` → checklist ✅ → `*_authorize`（仅当全绿 + `production_signed`）。

2. 复审记录写回本文件「Outcome」节（日期 / 决策 / 证据链接）。

## Pre-review (can run anytime)

```bash
bash scripts/ops_engineering_freeze_check.sh
bash scripts/ops_live_status.sh --json   # expect ready_to_authorize=false
```

## Outcome（复审日填写）

- reviewed_at: `2026-11-01T09:33+08:00`（提前开审；按 11-08 清单执行）
- decision: **`continue_defer`**
- staging_ready: **`false`**（不变）
- next_review_by: **`2026-11-15`**
- freeze_check: **PASS**（`ops_engineering_freeze_check.sh`）
- authorize: 四轨 **REFUSE**；`ready_to_authorize=false`
- kickoff: `ops_pgha_live_kickoff.sh` **`can_record=false`**（设计拒绝进入 record）

### STAGING_READY 四项核对

| # | 项 | 结果 | 证据 |
|---|----|------|------|
| 1 | Staging Postgres DSN | **FAIL** | 当前 `AIPLAT_PG_DSN` → `127.0.0.1:5433` = Option B 本机库，**不是**独立预发 |
| 2 | OIDC | **FAIL** | `AIPLAT_OIDC_ISSUER` **UNSET** |
| 3 | Operator / 窗口 / 回滚书面 | **FAIL** | 未提交独立预发变更窗口/回滚预案 |
| 4 | `AIPLAT_LIVE_DRILL_ENV` | **FAIL（标签不诚实）** | shell 中为 `staging`，但 DSN 为本机 `:5433` → **禁止**据此宣称预发就绪 |

### Notes

1. **不得**把本机 Docker PG / Keycloak 标成 staging 或把 `staging_ready` 改为 true。  
2. 建议本机演练时：`unset AIPLAT_LIVE_DRILL_ENV` 或显式 `export AIPLAT_LIVE_DRILL_ENV=local`，避免与真实预发混淆。  
3. 续 defer 期间工程环境仍为 Option B：`bash scripts/ops_option_b_all.sh`。  
4. 下次复审：**2026-11-15**；若届时仍无独立预发 DSN/OIDC → 再续 defer。

### Explicitly not done

- no `staging_ready=true`
- no checklist 🟨→✅
- no `production_signed=true`
- no `*_authorize` success
