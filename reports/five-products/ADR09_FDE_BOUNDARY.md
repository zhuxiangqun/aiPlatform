# FDE 部署边界清单（ADR-09 下一单产品后续 #1）

- **状态**：**清单已立** · 2026-10-26 — 授权真源 `ADR09_NEXT_FDE_DECISION.md`  
- **产品**：FDE（交付验收面）  
- **对照**：`ADR-01-boundaries-draft.md` · `contracts/delivery-fp-001.md` · Gate3 Phase D（签收绑 `report_id`）  
- **不含**：compose 长驻；本体 / 控制面拆；超边界 E4；新建第二套验收系统；一次大搬仓

## As-Is（当前）

| 面 | 现状 |
|----|------|
| 进程 | FDE HTTP 与控制面**共进程**（`aiPlat-platform` 挂载 `apps/fde`） |
| 路由归属 | `registry/apps.yaml` → `api_prefix: /api/platform/apps/fde`；实现 `aiPlat-platform/apps/fde/api/` |
| 业务逻辑 | 无 HTTP 逻辑在 `aiPlat-core/core/apps/fde/`；经 CoreFacade，禁止 platform→harness 直连 |
| 签收入口 | **唯一**：`POST …/fde/acceptance/signoff` → `validate_slice_signoff_reports`（D2 可强制 report） |
| 前端 | management FDE 工作台消费上述前缀；不另起验收 API |
| Compose | 无 FDE 专用长驻 profile；随控制面共部署 |
| 回滚 | 保持共部署路径；关任何实验性独立进程即可 |

## To-Be（单产品立项后 · 分 PR）

| 面 | 目标 | 回滚 |
|----|------|------|
| 进程 | FDE 可作**正式可选**独立进程（仍挂同一路由前缀语义）；发布节奏可独立 | 停独立进程；切回控制面共部署 |
| 路由 | 继续 `apps/fde` + `/api/platform/apps/fde`；**禁止**平行 `/acceptance/signoff` | 指回共部署挂载 |
| 签收 | **保留**现有 `acceptance/signoff` 为唯一权威；不另起验收系统 | D2 / 切片开关按既有 env |
| 数据 | 可选独立 home 子目录（验收会话 / 交付工件）；与控制面库隔离可选 | 指回共部署 home |
| Compose | 仅允许 one-shot / 显式试点；**长驻须另批** | `down -v` |
| 与诊断 / Pi | 消费者关系不变（引用 `report_id`）；不扩大诊断 / Pi 范围 | 既有 Gate3 / ADR-10 路径 |

## 分 PR 建议顺序（各 ≤ inflation）

| 序 | 主题 | 非目标 |
|----|------|--------|
| A | ✅ 本清单 + CLOSEOUT / SCHEDULE 引用立项 | 搬仓 |
| B | ✅ `apps/fde/README.md` + `fde_optional.env.example`：「正式可选」用语（非强制默认独立） | 改生产默认强制独立；compose 长驻 |
| C | ✅ one-shot health：`adr09_fde_optional_phase_health.sh` + `health_server.py`（127.0.0.1，停即退） | 第二套 signoff；compose 长驻；拆本体 / 控制面 |

## 回滚总则

1. 停任何 FDE 独立进程 / `compose … down -v`  
2. 切回控制面共部署 FDE API / 工作台路径  
3. 签收继续走既有 `acceptance/signoff`（不启用平行入口）  
4. 切片应急：`AIPLAT_FDE_REQUIRE_DIAG_REPORT_FOR_SLICE=0`（仅紧急；默认保持切片开启）
