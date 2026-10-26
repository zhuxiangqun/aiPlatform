# ADR-10 接线 Phase D — 仅 D1 共享 home opt-in（建议顺序第 2 步）

- **状态**：**已批（本批）** · 2026-10-26  
- **依据**：`ADR10_DIAGNOSIS_MVP_PHASE_D_DRAFT.md` 推荐默认；用户「开第2步」  
- **决策人**：架构 × 业务 × 诊断 R（兼任）  
- **批句效力**：批准 **仅 D1**；接受兼任 on-call；**不含** D2 / 对外 E4 / ADR-09 Accepted / 全拆

## 范围

| 项 | 本批 |
|----|:----:|
| D1：`AIPLAT_DIAGNOSIS_PROD_DEFAULT=1` + `ADR10_ALLOW_USER_HOME=1` + `AIPLAT_HOME` 落在 `$HOME/...`（默认 `$HOME/.aiplat/adr10-diagnosis-mvp-d1`） | ✅ |
| 试点脚本 `adr10_diagnosis_mvp_phase_d.sh` + 回滚（清 flag / 可删 d1 目录） | ✅ |
| D2 平台默认绑定 / 长驻 compose profile | ❌ |
| 对外 E4 / 五产品全拆 / 改平台路由默认 | ❌ |

## 兼任风险明示

架构 × 业务 × 诊断 R（兼任）接受：本 Phase D **无**独立 7×24；D1 写入用户 home 下隔离目录；**不**作对外 SLA / E4 证据。

## DoD

1. `pilot.sh`：裸 `PROD_DEFAULT=1`（无 `ALLOW_USER_HOME`）仍 exit 3；双 flag + `$HOME` 下 home → PASS  
2. `bash scripts/adr10_diagnosis_mvp_phase_d.sh` → ingest→report PASS  
3. 回滚步骤写入 ROLLBACK（`PROD_DEFAULT=0` / 删 d1 目录）  
4. RUNLOG 归档；SCHEDULE / DRAFT 指向本决定

## 本机执行（2026-10-26）

| 项 | 结果 |
|----|------|
| 裸 `PROD_DEFAULT=1` | PASS → exit 3（护栏） |
| Phase D D1 烟测 | PASS · `report_id=rep-29d565cf2f5b` · home=`~/.aiplat/adr10-diagnosis-mvp-d1` |
| 归档 | [`ADR10_PHASE_D_RUNLOG.txt`](./ADR10_PHASE_D_RUNLOG.txt) |

签署：架构 × 业务 × 诊断 R（兼任）· 2026-10-26 · **仅 D1；D2/E4/全拆仍须另批**
