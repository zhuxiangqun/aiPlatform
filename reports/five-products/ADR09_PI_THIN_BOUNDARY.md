# Pi Thin 部署边界清单（ADR-09 下一单产品后续 #1）

- **状态**：**清单已立** · 2026-10-26 — 授权真源 `ADR09_NEXT_PI_THIN_DECISION.md`  
- **产品**：Pi（Thin 独立部署立项）  
- **对照**：`GATE3_PI_THIN_PILOT.md` · `ADR-08-deploy-split.md` · `GATE3_PI_THIN_ROLLBACK_DRILL.md`  
- **不含**：compose 长驻；FDE / 本体 / 控制面拆；诊断二次大搬仓

## As-Is（Gate3 试点）

| 面 | 现状 |
|----|------|
| 进程 | `gate3_pi_thin_pilot.sh` → 独立 Node `aiplat-http`（默认端口 `18787`） |
| 密钥 | `.env.gate3-pi-thin`（`gate3_pi_thin.env.example`）；`AIPLAT_ENTERPRISE=1` → exit 3 |
| Bundle | 控制面导出 / sample-app；Thin 只消费 |
| Compose | `compose.gate3-pi-thin.yml` 试点；**非**生产长驻默认 |
| 证据 | `AIPLAT_SLICE_EVIDENCE=1` → JSONL → 诊断 MVP ingest |
| 回滚 | Bundle 版本优先；停试点进程切回共置 — `GATE3_PI_THIN_ROLLBACK_DRILL.md` |

## To-Be（单产品立项后 · 分 PR）

| 面 | 目标 | 回滚 |
|----|------|------|
| 进程 | Pi Thin 可作**正式可选**独立进程（与控制面分离），发布节奏可独立 | 停独立进程；共置 Thin |
| 端口 | 继续 env 配置（如 `AIPLAT_HTTP_PORT`）；禁止硬编码进 core | 改回默认/共置 |
| 密钥 | 维持独立 env 前缀；禁止复用生产控制面密钥文件 | 切回共置凭据策略 |
| Compose | one-shot / 显式试点 profile；**长驻须另批** | `down -v` |
| 与诊断 | 证据路径不变；不新建诊断微服务 | 既有 ingest |

## 分 PR 建议顺序

| 序 | 主题 | 非目标 |
|----|------|--------|
| A | 本清单 + CLOSEOUT 引用 #443 | 搬仓 |
| B | 文档化「正式可选」启动入口（README / env）对齐立项用语 | 改生产默认强制独立 |
| C | （可选）试点 compose 与 Gate3 脚本命名收敛 | compose 长驻 |

## 回滚总则

1. 停 Pi Thin 独立进程 / `compose … down -v`  
2. Bundle 版本回滚（优先）  
3. 切回控制面共置 Thin  
4. 详见 `GATE3_PI_THIN_ROLLBACK_DRILL.md`
