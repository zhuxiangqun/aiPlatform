# Ontology A3 进程拆分硬门清单

> `process_split_authorized` 仅当下列全部为 ✅（🟨 = 本地演练，≠ 授权）。  
> ADR：[`ADR-ONTOLOGY-A3.md`](../../../../reports/five-products/ADR-ONTOLOGY-A3.md) **Accepted（有条件）**  
> 刷新：`bash packages/aiplat-ontology/scripts/a3_local_rehearsal.sh` → `a3_prep_check.sh`

| # | 项 | Owner | Done |
|---|----|-------|:----:|
| 1 | `ontology.api.v0` + `/ontology/healthz` 契约回归 | 平台 | 🟨 |
| 2 | 独立 Chart / 安装前缀骨架 | 运维 | ✅ |
| 3 | 存储迁移/回填 + 双写或只读切换演练 | 运维 | 🟨 |
| 4 | platform apps 零 `core.harness.knowledge` 直导 | 架构 | ✅ |
| 5 | 回滚演练（切回共宿 D1） | 运维 | 🟨 |
| 6 | ADR Accepted 联签 | 架构 | ✅ |

`process_split_authorized: false`

## 自动 vs 人工

| 自动（prep / local_rehearsal） | 仍须人工 |
|-------------------------------|----------|
| #1 healthz/adapter 单测（🟨） | #3 迁移/双写 **live** |
| #2 chart + `a3_process_split_authorized=false` | #5 回滚 **live** |
| #4 platform apps 无 harness.knowledge 直导 | |
| #3/#5 本地文件树演练（🟨） | |
| #6 ADR Accepted（有条件） | |
