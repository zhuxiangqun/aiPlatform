# Diagnosis A3 进程拆分硬门清单

> `process_split_authorized` 仅当下列全部为 ✅（🟨 = 本地演练，≠ 授权）。  
> ADR：[`ADR-DRAFT-diagnosis-d1.md`](../../../../reports/five-products/ADR-DRAFT-diagnosis-d1.md) **Draft**（未 Accepted）  
> 刷新：`bash packages/aiplat-diagnosis/scripts/a3_local_rehearsal.sh`

| # | 项 | Owner | Done |
|---|----|-------|:----:|
| 1 | healthz + report schema 契约回归 | 平台 | 🟨 |
| 2 | 独立 Chart / 安装前缀骨架 | 运维 | ✅ |
| 3 | 控制面经 API；无跨库直读诊断表 | 架构 | ✅ |
| 4 | 备份恢复 + 回滚演练（切回共宿） | 运维 | 🟨 |
| 5 | ADR Accepted 联签 | 架构 | ⬜ |

`process_split_authorized: false`

## 自动 vs 人工

| 自动（prep / local_rehearsal） | 仍须人工 |
|-------------------------------|----------|
| #1 healthz/schema 单测（🟨） | #4 备份/回滚 **live** |
| #2 chart + `a3_process_split_authorized=false` | #5 ADR Accept |
| #3 platform apps 无 harness 直导诊断业务表 | |
| #4 本地 SQLite 演练（🟨） | |
