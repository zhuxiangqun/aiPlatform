# Evaluation A3 进程拆分硬门清单

> `process_split_authorized` 仅当下列全部为 ✅（🟨 = 本地演练，≠ 授权）。  
> ADR：[`ADR-EVALUATION-A3.md`](../../../../reports/five-products/ADR-EVALUATION-A3.md) **Accepted（有条件）**  
> 刷新：`bash packages/aiplat-evaluation/scripts/a3_local_rehearsal.sh` → `a3_prep_check.sh`

| # | 项 | Owner | Done |
|---|----|-------|:----:|
| 1 | `eval.protocol.v0` + `/eval/healthz` 契约回归 | 平台 | 🟨 |
| 2 | 独立 Chart / DB 迁移骨架 | 运维 | ✅ |
| 3 | 控制面经 API；无跨库直读评测表 | 架构 | ✅ |
| 4 | 备份恢复 + 回滚演练（切回共宿） | 运维 | 🟨 |
| 5 | ADR Accepted 联签 | 架构 | ✅ |

`process_split_authorized: false`

## 自动 vs 人工

| 自动（prep / local_rehearsal） | 仍须人工 |
|-------------------------------|----------|
| #1 protocol/healthz 单测（🟨） | #4 备份/回滚 **live** |
| #2 chart + `a3_process_split_authorized=false` | |
| #3 platform apps 无 `core.harness` 直导 | |
| #4 本地 SQLite 演练（🟨） | |
| #5 ADR Accepted（有条件） | |
