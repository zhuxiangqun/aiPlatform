# 诊断 MVP 部署边界清单（ADR-09 第 4 步后续 #1）

- **状态**：**清单已立** · 2026-10-26 — 授权真源 `ADR09_STEP4_DECISION.md`  
- **产品**：诊断 MVP（ADR-10 / ADR-08 Pi Thin）  
- **本页**：As-Is + To-Be 边界；**不含**代码搬仓；**不含** compose 长驻；**不含**其余四产品

## As-Is（当前）

| 面 | 现状 |
|----|------|
| 进程 | 证据/诊断库函数跑在控制面同进程（`slice_evidence` / FDE signoff）；Pi Thin 可另进程（Gate3） |
| 数据目录 | 沙箱 `/tmp/aiplat-adr10-diag-home*`；D1 opt-in `$HOME/.aiplat/adr10-diagnosis-mvp-d1`；默认 `AIPLAT_HOME`→`~/.aiplat` |
| 入口 | `POST …/fde/acceptance/signoff` → `validate_slice_signoff_reports`（D2：`PROD_DEFAULT=1` 强制 report） |
| Compose | `compose.adr10-diagnosis-mvp.yml` **one-shot** `run --rm`；无常驻 HTTP；`PROD_DEFAULT=0` |
| 烟测 | `scripts/adr10_diagnosis_mvp_pilot.sh` · `phase_d.sh`（d1/d2）· `phase_c.sh` |

## To-Be（独立部署 · 分 PR 落地）

| 面 | 目标 | 回滚 |
|----|------|------|
| 进程 | 诊断证据写入与查询可在**独立 worker/进程**跑（仍可被控制面 HTTP 调用） | 关独立进程；控制面内嵌路径恢复 |
| 端口 | 若暴露健康检查：单独端口（env 配置，禁止写死业务名进 core） | 停听；客户端改回共部署 |
| 数据 | 独立 `AIPLAT_HOME`（或子目录 `…/diagnosis-mvp`）；与控制面库物理隔离可选 | 指回共部署 home |
| 签收 | 控制面 signoff **继续**调同一 `validate_slice_signoff_reports`（入口不拆第二套） | D2 flag=0 |
| Compose | 保持 one-shot / `down -v`；**长驻须另批** | `down -v` |

## 分 PR 建议顺序（各 ≤ inflation）

| 序 | PR 主题 | 非目标 |
|----|---------|--------|
| A | 本清单 + CLOSEOUT 引用 #438 | 搬仓 |
| B | 独立 home/路径约定 + 烟测脚本开关（仍 one-shot） | 长驻 service |
| C | （可选）薄 HTTP health 仅诊断进程 | 拆 FDE/控制面 |

## 回滚总则

1. `AIPLAT_DIAGNOSIS_PROD_DEFAULT=0`  
2. 停任何诊断独立进程；切回共部署  
3. `docker compose -f compose.adr10-diagnosis-mvp.yml down -v`  
4. 详见 `ADR10_DIAGNOSIS_MVP_ROLLBACK_DRILL.md`
