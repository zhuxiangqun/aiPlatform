# 环境方案 B — 本机 VM/Docker 全轨实施（当前唯一工程环境）

- decided_at: `2026-11-01`
- decision: **目前全部使用方案 B**（本机 Docker / 可选 Lima·UTM·Colima VM）
- 不含：新购服务器、闲置旧机（方案 A）、免费云档（方案 C）、CI 冒充预发（方案 D）
- 与 [`LOCAL_DEFER.md`](./LOCAL_DEFER.md) 并存：
  - **环境方案 B** = 工程环境选型（本机独立容器网络）
  - **运维路径 B** = 正式 defer authorize（`staging_ready=false`）
  - 两者同时成立，互不冲突

## 独立环境最低标准（本机须满足）

| # | 要求 | 本机落点 |
|---|------|----------|
| 1 | 独立容器网络 / 可选独立 VM | `compose.local-staging.yml` · network `aiplat-local-staging` |
| 2 | 独立 Postgres 库+用户 | `:5433` · `aiplat_local` |
| 3 | 独立 OIDC realm/client | Keycloak `:8081` · `aiplat-local` |
| 4 | 独立数据卷 | compose volumes；不写开发 `$AIPLAT_HOME` |
| 5 | 固定 hostname/端口 | `127.0.0.1:5433` / `:8081` |
| 6 | 独立操作者窗口/备份 | `local-*.json` + operator 字段 |
| 7 | 无开发进程混跑 | rehearse 用 hermetic prefix / 临时 DEMO_ROOT |

## 全轨范围（全部 `environment=local`）

| 轨 | 命令 | 证据 |
|----|------|------|
| PG/HA + OIDC | `pg_ha_local_staging.sh all` | `local-pgha-*.json` · `oidc-local-*.json` |
| Ontology A3 | `a3_*` via `ops_local_rehearse_tracks` | `local-ontology-a3-*.json` |
| Evaluation A3 | 同上 | `local-evaluation-a3-*.json` |
| Pi D3 | 同上 | `local-pi-d3-*.json` |
| Pi D1 | `d1_local_regression.sh` | [`PI_D1_LOCAL_REGRESSION.md`](./PI_D1_LOCAL_REGRESSION.md) |
| Pi D2 | `d2_admin_check.sh` | [`PI_D2_ADMIN_LOCAL.md`](./PI_D2_ADMIN_LOCAL.md) |
| FDE Field | `packages/aiplat-fde/.../d1_local_regression.sh` | `local-fde-*.json` |

一键：

```bash
bash scripts/ops_option_b_all.sh
# 需要 Docker Desktop 运行中 → 全量 PG:5433 + Keycloak:8081
# daemon 不可用时脚本自动降级 sqlite/file rehearsal，并在 OPTION_B_LAST_RUN 标明 pgha_mode
```

## 硬边界（不可破）

| 字段 | 值 |
|------|-----|
| `environment` | **local**（禁止写成 staging） |
| `staging_ready` | **false** |
| `local_signed` | 允许（工程） |
| `production_signed` | **false** |
| checklist | 保持 🟨 |
| `cutover_authorized` / `process_split_*` / `d3_production_*` | **false** |

## 单宿主限制（写进证据诚实声明）

本机方案 B **能**推进 schema/OIDC/备份/回滚/手动 failover 工程准备。  
本机方案 B **不能**作为真实多机 HA / 云 PITR / 生产负载证据，也不能解锁 authorize。

复审 **2026-11-08**：若仍无方案 A/C，继续本文件 + [`LOCAL_DEFER.md`](./LOCAL_DEFER.md)；有可信独立预发再谈 `staging_ready`。

## 详见

- [`LOCAL_STAGING.md`](./LOCAL_STAGING.md) — 拓扑与证据规则  
- [`STAGING_READY.md`](./STAGING_READY.md) — 真实预发 Gate（当前未满足）  
- [`ENGINEERING_LOCAL_CLOSEOUT.md`](./ENGINEERING_LOCAL_CLOSEOUT.md) — 工程收口  
