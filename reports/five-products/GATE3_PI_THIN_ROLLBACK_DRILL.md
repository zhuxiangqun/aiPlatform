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
| Window | 同日双端（修订后；原 7 日计划废止） |
| Operator | architecture × business (dual-role) |
| Runtime | `GATE3_PI_THIN_PHASE=a` → **PASS**（stub smoke） |
| Bundle / slice path | `GATE3_PI_THIN_PHASE=d` → **PASS**（export → ingest → FDE bind `rep-caaf208cdfcd`） |
| Result | **PASS** — kickoff re-run complete |
| Next | 同日结束复跑（见下节 close） |

```bash
GATE3_PI_THIN_PHASE=a bash packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh
GATE3_PI_THIN_PHASE=d bash packages/aiplat-pi-runtime/scripts/gate3_pi_thin_pilot.sh
# or: bash packages/aiplat-pi-runtime/scripts/gate3_observation_rerun.sh
```

## Re-run — mid-window health（2026-10-24）

| Field | Value |
|-------|-------|
| Authority | 观察窗口内可选健康复跑（不替代 G3-OBS3 结束复跑） |
| Helper | `scripts/gate3_observation_rerun.sh` + `GATE3_OBS_INCLUDE_EF=1` |
| Runtime | `phase=a` → **PASS** |
| Bundle / slice | `phase=d` → **PASS** |
| Phase E | **PASS** `rep-9d7a82131134` |
| Phase F | **PASS** HTTP `signed_off` `rep-78319c54b756` |
| Result | **PASS** — mid-window（可选；不替代 close） |

```bash
GATE3_OBS_LABEL=mid-window-2026-10-24 GATE3_OBS_INCLUDE_EF=1 \
  bash packages/aiplat-pi-runtime/scripts/gate3_observation_rerun.sh
```

## Re-run — observation close（2026-10-24 · 同日双端）

| Field | Value |
|-------|-------|
| Authority | `GATE3_OBSERVATION_WINDOW_DECISION.md`（G3-OBS3 修订 · 同日双端） |
| Helper | `GATE3_OBS_LABEL=observation-close-2026-10-24 bash .../gate3_observation_rerun.sh` |
| Runtime | `phase=a` → **PASS** |
| Bundle / slice | `phase=d` → **PASS** `rep-f4ae669e858e` |
| Result | **PASS** — 同日双端关闭；ADR-09 前置 #1 **候选齐**（仍非 Accepted） |

```bash
GATE3_OBS_LABEL=observation-close-2026-10-24 \
  bash packages/aiplat-pi-runtime/scripts/gate3_observation_rerun.sh
```

## Re-run — path B defer local regression（2026-11-01）

| Field | Value |
|-------|-------|
| Authority | [`ops/LOCAL_DEFER.md`](./ops/LOCAL_DEFER.md) · PG/HA `staging_ready=false` |
| Helper | `bash packages/aiplat-pi-runtime/scripts/d1_local_regression.sh` |
| Scope | hermetic D1 install/smoke/backup/upgrade/runtime+bundle rollback + Gate3 a/b/c |
| Environment | **local** — not staging; **no** `production_signed` / authorize |
| Result | **PASS** — see [`ops/PI_D1_LOCAL_REGRESSION.md`](./ops/PI_D1_LOCAL_REGRESSION.md) |
| Fix landed | same-version `d1_upgrade` → `versions/<ver>+<UTC>` so `--runtime` rollback flips |

```bash
bash packages/aiplat-pi-runtime/scripts/d1_local_regression.sh
```
