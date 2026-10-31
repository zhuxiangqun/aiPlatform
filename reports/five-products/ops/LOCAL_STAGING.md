# Local staging（零预算 · 工程验证 · 非生产预发）

> **诚实边界**：本机 VM / Docker 可推进 PG/HA **70–80%** 工程准备；**不能**把 `cutover_authorized` 置 true。  
> 证据必须 `environment=local`；签名用 `local_signed`（可选）；**禁止** `staging` / `production_signed`。  
> 生产 authorize 仍要求 [`STAGING_READY.md`](./STAGING_READY.md) + `live-*.json`。

## 拓扑

```text
本机 Docker network `aiplat-local-staging`
  Postgres 16  → 127.0.0.1:5433  库 aiplat_local
  Keycloak     → 127.0.0.1:8081  realm aiplat-local（手工创建）
```

Compose：`packages/aiplat-central/compose.local-staging.yml`

## 能验证 / 不能验证

| 项 | 本地 | 说明 |
|----|:----:|------|
| SQLite→PG schema 演练 | ✅ | `pg_ha_local_rehearsal` + DSN |
| 应用连 PG（本机） | ✅ | 连接池/超时粗测 |
| OIDC / admin MFA | ✅ | Keycloak 协议（realm 需手工） |
| 备份/恢复 | ✅ | pg_dump/restore；RTO 粗测 |
| 手动 failover | ⚠️ | 双容器 dump/promote；无 VIP |
| 真实多机 HA / 云 PITR / 生产负载 | ❌ | 单宿主 |

## 证据规则（防假造）

| 字段 | 本地值 | 禁止 |
|------|--------|------|
| 文件名 | `local-*.json` | 不要写成 `live-*.json` |
| `environment` | `local` | `staging` / `prod-canary` |
| `production_signed` | **false** | true |
| `local_signed` | 可选（items 齐后） | 当作生产签字 |
| checklist | 保持 🟨 | 🟨→✅ |
| `cutover_authorized` | **false** | true |

Authorize 硬门会拒绝：非 `staging`/`prod-canary` 的 `live-*.json`，以及任何 `local-*.json`（根本不读）。

## 最短步骤

```bash
# 1) 起栈
bash packages/aiplat-central/scripts/pg_ha_local_staging.sh up

# 2) 演练 + 落盘 local-*.json
export AIPLAT_PG_DSN='postgresql://aiplat:aiplat_local@127.0.0.1:5433/aiplat_local'
bash packages/aiplat-central/scripts/pg_ha_local_staging.sh rehearse
# 或一次性：
bash packages/aiplat-central/scripts/pg_ha_local_staging.sh all

# 3) Keycloak：浏览器打开 http://127.0.0.1:8081 （admin / admin_local_only）
#    建 realm aiplat-local + 测试用户 + MFA；再填 oidc_full evidence

# 4) 确认硬门仍未就绪
bash packages/aiplat-central/scripts/pg_ha_cutover_authorize.sh status
# ready_to_authorize 必须为 false

# 5) 收工
bash packages/aiplat-central/scripts/pg_ha_local_staging.sh down
```

## 与 defer / 预发 Gate 的关系

- [`LOCAL_DEFER.md`](./LOCAL_DEFER.md)：生产 authorize 正式 defer；本页是 **路径 A 并行**。  
- [`STAGING_READY.md`](./STAGING_READY.md)：真实预发齐套后才允许 `live` → sign → authorize。  
- 同一 runbook 将来在真实 staging 重跑；本地证据**不迁移**为生产签字。

## Runlog（2026-11-01）

| Field | Value |
|-------|-------|
| Command | `bash packages/aiplat-central/scripts/pg_ha_local_staging.sh all` |
| Result | **PASS** (compose up → local/PG/HA rehearse → `local-*.json` → authorize still not ready → down) |
| Sample evidence | [`evidence/local-pgha-local-20261031T235030Z.json`](./evidence/local-pgha-local-20261031T235030Z.json) |
| `environment` | `local` |
| `production_signed` | **false** |
| `oidc_full` | still open（Keycloak UI realm/MFA 待手工） |
| `cutover_authorized` | **false** |

Authorize hardening：`require_signed_live` 现要求 `environment ∈ {staging, prod-canary}`；`environment=local` 即使误写 `production_signed=true` 也会 REFUSE。
