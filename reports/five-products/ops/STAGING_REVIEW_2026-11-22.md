# Staging review checklist — 2026-11-22

> 承继 [`STAGING_REVIEW_2026-11-15.md`](./STAGING_REVIEW_2026-11-15.md)（**continue_defer**）。  
> **禁止**本机 Docker 冒充 staging / 手改 🟨→✅ / 假 DSN·OIDC。  
> **本文件**：复审日前预填包（2026-11-01）；**Outcome 仍待复审日填写**。

## Pre-work（复审前 · 已预填）

| # | 准备项 | 状态（2026-11-01） |
|---|--------|-------------------|
| 1 | 独立主机候选（旧笔记本 / 闲置机 / 免费云） | **无候选**（明确不买服务器；无闲置机登记） |
| 2 | 按 [`STAGING_PROVISIONING.md`](./STAGING_PROVISIONING.md) 装 PG+Keycloak | **not_started**（无主机 → 不实施） |
| 3 | 填 [`STAGING_READY.md`](./STAGING_READY.md) 四项 | 全 **未齐**（见下表） |
| 4 | operator / 变更窗口 / 回滚预案书面 | **未提交**（无预发对象可写） |
| 5 | 冻结自检绿 | **PASS** · `ops_engineering_freeze_check.sh` |
| 6 | 本地门禁复验 | **PASS** · `five_products_gate.sh`（authorize REFUSE） |
| 7 | G0 / HEAD CI | **PASS** · 锚点见 [`G0_CLOSEOUT.md`](../G0_CLOSEOUT.md) |

### STAGING_READY 预检（复审前快照）

| # | 项 | 预检 | 备注 |
|---|----|------|------|
| 1 | Staging Postgres DSN | **FAIL** | 仅有 Option B `127.0.0.1:5433` ≠ 独立预发 |
| 2 | OIDC | **FAIL** | 无预发 issuer；kickoff 需 `AIPLAT_OIDC_ISSUER` |
| 3 | Operator / 窗口 / 回滚 | **FAIL** | 无书面变更窗（无主机可挂） |
| 4 | `AIPLAT_LIVE_DRILL_ENV` | **N/A→local only** | 复验必须用 `local`；禁止伪标 `staging` |

### 复审材料包（齐套才进入 A/C）

- [ ] 主机身份（主机名、所有者、与开发隔离证明）  
- [ ] PG DSN（redacted 可入库；密钥不进 git）  
- [ ] OIDC issuer + client id（无 secret 进 git）  
- [ ] 备份/快照证明  
- [ ] 变更窗口 + 回滚一段话  

模板来源：[`STAGING_PROVISIONING.md`](./STAGING_PROVISIONING.md) · Gate：[`STAGING_READY.md`](./STAGING_READY.md)。

## Decision tree（复审日）

1. 四项 STAGING_READY 是否齐？  
   - **否** → 再 `continue_defer`；写下次 `review_by`；Option B 继续。  
   - **是** → 置 `staging_ready=true` 仅当证据齐 → kickoff → live → sign → checklist ✅ → authorize。

## Outcome（复审日填写）

- reviewed_at: `_TBD_`
- decision: `_continue_defer | enter_staging_A_or_C_`
- staging_ready: `_false until conditions met_`
- next_review_by: `_if continue_defer_`
- notes: `_…_`

### Explicitly not done（预填时点）

- no `staging_ready=true`
- no host provisioned / no server purchase
- no checklist 🟨→✅
- no `production_signed` / authorize
