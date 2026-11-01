# 四轨正式 defer（Live / Authorize 暂缓）

- decided_at: `2026-10-31`
- formalized_at: `2026-11-01`
- reviewed_at: `2026-11-01T13:16+08:00`（停日历空转 → **事件驱动 defer**）
- decision: **运维路径 B — 正式 defer（续）**（无独立预发；不买服务器；**无主机不排复审**）
- **工程环境**：方案 B 本机 VM/Docker — [`OPTION_B_LOCAL_VM.md`](./OPTION_B_LOCAL_VM.md) · `bash scripts/ops_option_b_all.sh`
- `staging_ready`: **false**（[`STAGING_READY.md`](./STAGING_READY.md)）
- last_kickoff: `can_record=false`（`AIPLAT_LIVE_DRILL_ENV=local`）
- review_policy: **事件驱动** — [`STAGING_REVIEW_EVENT_DRIVEN.md`](./STAGING_REVIEW_EVENT_DRIVEN.md)
- review_by: **无日历日期**（出现主机/DSN/OIDC/operator 窗口才开审）
- 最近结论：[`STAGING_REVIEW_2026-11-22.md`](./STAGING_REVIEW_2026-11-22.md) continue_defer

| 轨 | 本地状态 | 硬门 |
|----|----------|------|
| PG/HA | prep + docker reh 🟨 | `cutover_authorized=false` |
| Ontology A3 | local reh 🟨 | `process_split_authorized=false` |
| Evaluation A3 | local reh 🟨 | `process_split_authorized=false` |
| Pi D3 | bundle + SOC file-sink 🟨 | `d3_production_authorized=false` |

## 禁止（硬门生效期间）

- 用本地 Docker PG 冒充 `staging`
- 手改 checklist 🟨→✅ / 假造 DSN·OIDC
- 为凑预发买服务器
- **无触发条件时排下一场日历复审**（制造文档 churn）

## 当前唯一工程环境（方案 B · 非授权）

证据必须 `environment=local`；**不能** authorize。

```bash
bash scripts/ops_option_b_all.sh
```

## 主轨

本地工程已冻结（**无必须产品代码**）。  
live → sign → authorize 仅当事件驱动复审通过且 `staging_ready=true`。

见 [`ENGINEERING_FREEZE.md`](./ENGINEERING_FREEZE.md) · [`STAGING_REVIEW_EVENT_DRIVEN.md`](./STAGING_REVIEW_EVENT_DRIVEN.md)。
