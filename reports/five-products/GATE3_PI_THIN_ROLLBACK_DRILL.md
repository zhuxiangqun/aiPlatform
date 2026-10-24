# Gate3 Pi Thin — Rollback Drill Record

| Field | Value |
|-------|-------|
| Scene | `fp-customer-lock-service-bundle-pi-diag-001` |
| Date | 2026-10-24 |
| Operator | platform owner + delivery owner (dual-role) |
| Result | **PASS** (scripted process stop + documented Bundle-first path) |
| Residual risk | Stub only; agent mode must not leave `AIPLAT_PI_*` in control-plane env |
| Sign-off | Dual-role owner — re-run before any non-stub Gate3 expansion |

## Priority (ADR-08 / G3-3)

1. **Bundle 版本回滚优先** — 控制面仍用既有 `export_pi_bundle` / 部署目录：将试点 `AIPLAT_APP_HOME` 指回上一已签名 Bundle 目录（或 `current` → 上一版本 symlink），再重启 Thin。  
2. **Runtime 备选** — 停试点进程/容器，切回共置 Thin；删除或改名 `.env.gate3-pi-thin`；控制面路径不变。

## Runtime drill (executed)

```bash
cd packages/aiplat-pi-runtime
bash scripts/gate3_pi_thin_pilot.sh   # expect PASS smoke
# Ctrl-C / kill → process gone; control plane unchanged
# optional container: docker compose -f compose.gate3-pi-thin.yml down
```

## Bundle-first drill (checklist)

```bash
# 1) Note current AIPLAT_APP_HOME / bundle_id from pilot env
# 2) Point AIPLAT_APP_HOME at previous exported app dir (or flip current→prev)
# 3) bash scripts/gate3_pi_thin_pilot.sh   # expect PASS with prior bundle fixtures
# 4) If still bad → Runtime 备选 (stop process / compose down)
```

## Re-run — observation kickoff（2026-10-24）

| Field | Value |
|-------|-------|
| Authority | `GATE3_OBSERVATION_WINDOW_DECISION.md`（G3-OBS2） |
| Window | 2026-10-24 → 2026-10-31（7 日历日） |
| Operator | architecture × business (dual-role) |
| Runtime | `GATE3_PI_THIN_PHASE=a` → **PASS**（stub smoke） |
| Bundle / slice path | `GATE3_PI_THIN_PHASE=d` → **PASS**（export → ingest → FDE bind `rep-caaf208cdfcd`） |
| Result | **PASS** — kickoff re-run complete |
| Next | 窗口结束前（≤2026-10-31）同等复跑一轮 → 候选勾 ADR-09 前置 #1 |

```bash
GATE3_PI_THIN_PHASE=a bash packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh
GATE3_PI_THIN_PHASE=d bash packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh
```
