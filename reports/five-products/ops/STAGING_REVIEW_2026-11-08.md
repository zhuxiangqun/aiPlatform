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

- reviewed_at: `_TBD_`
- decision: `_continue_defer | enter_staging_A_or_C_`
- staging_ready: `_false until conditions met_`
- notes: `_…_`
