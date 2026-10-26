# ADR-10 接线 Phase C — 诊断单产品加深（建议顺序第 1 步）

- **状态**：**已批（本批）** · 2026-10-26  
- **依据**：ADR-10 Accepted（有条件）§5；`ADR09_DEFER_FULL_SPLIT_E4_PROD.md` 建议顺序第 1 步  
- **触发**：「按照建议顺序实施」  
- **决策人**：架构 × 业务 × 诊断 R（兼任）

## 本批授权（仅第 1 步）

| 项 | 本批 |
|----|:----:|
| 诊断 MVP **单产品加深**：双端稳定窗复跑 + 回滚演练复跑 + 重复烟测归档 | ✅ |
| 书面接受「无独立 7×24、兼任 on-call」**仅限本加深范围** | ✅ |
| 改生产默认路径 / 长驻诊断微服务 | ❌（建议顺序第 2 步，须另批） |
| 对外 E4 | ❌（第 3 步） |
| 五产品全拆 / ADR-09 Accepted | ❌（第 4 步） |

## 兼任风险明示（本加深）

架构 × 业务 × 诊断 R（兼任）接受：本 Phase C **无**独立 7×24；故障由兼任运维承担；**不**把本批当作对外 SLA 或 E4 证据。

## DoD

1. `scripts/adr10_diagnosis_mvp_phase_c.sh` 合入；拒绝 `AIPLAT_DIAGNOSIS_PROD_DEFAULT=1`  
2. 宿主：start 烟测 → 间隔 → close 烟测 → 均 PASS；重复次数可配（默认 ≥2）  
3. `AIPLAT_DIAGNOSIS_PROD_DEFAULT=1` → exit 3  
4. compose one-shot PASS（有 daemon）+ `down -v`；无 daemon 可 SKIP，须在 ROLLBACK 记残差  
5. RUNLOG 归档；更新 `ADR10_DIAGNOSIS_MVP_ROLLBACK_DRILL.md`

## 本机执行（2026-10-26）

| 项 | 结果 |
|----|------|
| 拒切 `AIPLAT_DIAGNOSIS_PROD_DEFAULT=1` | PASS（exit 3） |
| 宿主 start×2 → gap → close×2 | PASS（隔离 `AIPLAT_HOME`） |
| compose | SKIP（本机无 Docker daemon） |
| 归档 | [`ADR10_PHASE_C_RUNLOG.txt`](./ADR10_PHASE_C_RUNLOG.txt) |

签署：架构 × 业务 × 诊断 R（兼任）· 2026-10-26 · **仅 Phase C；不停泊 DEFER 对第 2–4 步的否决**  
