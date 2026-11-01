# 四轨正式 defer（Live / Authorize 暂缓）

- decided_at: `2026-10-31`
- formalized_at: `2026-11-01`
- reviewed_at: `2026-11-01T11:12+08:00`（按 11-15 清单提前开审 → **继续 defer**）
- decision: **运维路径 B — 正式 defer（续）**（无独立预发 DSN/OIDC；本机 `:5433` 不计 staging；不买服务器）
- **工程环境**：同期锁定 **环境方案 B（本机 VM/Docker）全轨** — 见 [`OPTION_B_LOCAL_VM.md`](./OPTION_B_LOCAL_VM.md) · `bash scripts/ops_option_b_all.sh`
- `staging_ready`: **false**（见 [`STAGING_READY.md`](./STAGING_READY.md)）
- last_kickoff: `2026-11-01` · `can_record=false`（`AIPLAT_LIVE_DRILL_ENV=local` · 按设计）
- review_by: **2026-11-22**（仍无独立预发则再续；有则评估方案 A/C）
- 复审结论：[`STAGING_REVIEW_2026-11-15.md`](./STAGING_REVIEW_2026-11-15.md)（承继 [`STAGING_REVIEW_2026-11-08.md`](./STAGING_REVIEW_2026-11-08.md)）

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
- 为「凑预发」购买服务器（本决策明确不买）

## 当前唯一工程环境（环境方案 B · 非授权）

**全部轨**走本机 Docker/VM local staging；证据必须 `environment=local`（`local-*.json`），**不能** authorize。  
决策与范围：[`OPTION_B_LOCAL_VM.md`](./OPTION_B_LOCAL_VM.md) · 拓扑：[`LOCAL_STAGING.md`](./LOCAL_STAGING.md)。

```bash
# 一键全轨（含 PG :5433 + Keycloak :8081 + A3/D3 + Pi D1/D2 + FDE）
bash scripts/ops_option_b_all.sh
```

## 主轨（defer 期间）

不依赖真实预发：**环境方案 B 全轨**（上表）+ 已冻结的本地 D1–D3/E2E 证据。  
PG/HA live → sign → authorize 等 `staging_ready=true`（需方案 A/C 级独立预发，**不是**本机 B）。

跨轨 runlog：[`LOCAL_TRACKS_RUNLOG.md`](./LOCAL_TRACKS_RUNLOG.md) · 最近全跑：[`OPTION_B_LAST_RUN.md`](./OPTION_B_LAST_RUN.md) · 工程收口：[`ENGINEERING_LOCAL_CLOSEOUT.md`](./ENGINEERING_LOCAL_CLOSEOUT.md) · **工程冻结**：[`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md) · 复审：[`STAGING_REVIEW_2026-11-15.md`](./STAGING_REVIEW_2026-11-15.md) · 下次草稿：[`STAGING_REVIEW_2026-11-22.md`](./STAGING_REVIEW_2026-11-22.md)

## 复审后（真实预发 · 方案 A/C）

若有闲置机或免费云档满足 [`STAGING_READY.md`](./STAGING_READY.md)：再谈 live → sign → authorize。  
否则续本文件 + 继续环境方案 B。见 [`PGHA_LIVE_RUNLOG.md`](./PGHA_LIVE_RUNLOG.md) · [`OPS_HANDOFF.md`](../OPS_HANDOFF.md)。
