# 四轨正式 defer（Live / Authorize 暂缓）

- decided_at: `2026-10-31`
- formalized_at: `2026-11-01`
- decision: **运维路径 B — 正式 defer**（无预发 DSN/OIDC；不假造 staging）
- **工程环境**：同期锁定 **环境方案 B（本机 VM/Docker）全轨** — 见 [`OPTION_B_LOCAL_VM.md`](./OPTION_B_LOCAL_VM.md) · `bash scripts/ops_option_b_all.sh`
- `staging_ready`: **false**（见 [`STAGING_READY.md`](./STAGING_READY.md)）
- last_kickoff: `2026-10-31T23:35:04Z` · `ops_pgha_live_kickoff.sh` **exit 2**（按设计）
- review_by: **2026-11-08**（若仍无预发则续 defer；有则再评估方案 A/C 进真实 staging）

| 轨 | 本地状态 | 硬门 |
|----|----------|------|
| PG/HA | prep + docker reh 🟨 | `cutover_authorized=false` |
| Ontology A3 | local reh 🟨 | `process_split_authorized=false` |
| Evaluation A3 | local reh 🟨 | `process_split_authorized=false` |
| Pi D3 | bundle + SOC file-sink 🟨 | `d3_production_authorized=false` |

## 禁止（硬门生效期间）

- 用本地 Docker PG 冒充 `staging`
- 手改 checklist 🟨→✅
- 改 `authorize` 脚本放行
- 把 scaffold live 写成 `production_signed=true`
- 假造 DSN / OIDC

## 当前唯一工程环境（环境方案 B · 非授权）

**全部轨**走本机 Docker/VM local staging；证据必须 `environment=local`（`local-*.json`），**不能** authorize。  
决策与范围：[`OPTION_B_LOCAL_VM.md`](./OPTION_B_LOCAL_VM.md) · 拓扑：[`LOCAL_STAGING.md`](./LOCAL_STAGING.md)。

```bash
# 一键全轨（含 PG :5433 + Keycloak :8081 + A3/D3 + Pi D1/D2 + FDE）
bash scripts/ops_option_b_all.sh
```

## 主轨（defer 期间）

不依赖真实预发：**环境方案 B 全轨**（上表）+ Pi D1/D2。  
PG/HA live → sign → authorize 等 `staging_ready=true`（需方案 A/C 级独立预发，**不是**本机 B）。

跨轨 runlog：[`LOCAL_TRACKS_RUNLOG.md`](./LOCAL_TRACKS_RUNLOG.md) · 最近全跑：[`OPTION_B_LAST_RUN.md`](./OPTION_B_LAST_RUN.md) · 工程收口：[`ENGINEERING_LOCAL_CLOSEOUT.md`](./ENGINEERING_LOCAL_CLOSEOUT.md)

## 复审后（真实预发 · 方案 A/C）

若有闲置机或免费云档满足 [`STAGING_READY.md`](./STAGING_READY.md)：再谈 live → sign → authorize。  
否则续本文件 + 继续环境方案 B。见 [`PGHA_LIVE_RUNLOG.md`](./PGHA_LIVE_RUNLOG.md) · [`OPS_HANDOFF.md`](../OPS_HANDOFF.md)。
