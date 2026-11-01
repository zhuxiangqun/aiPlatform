# Pi D3 生产宣称硬门清单

> `d3_production_authorized` 仅当下列全部为 ✅（🟨 = 本地/自动部分绿，≠ 生产宣称）。  
> ADR：[`ADR-PI-D3.md`](../../../../reports/five-products/ADR-PI-D3.md) **Accepted（有条件）**  
> 刷新：`d3_local_closeout.sh`（= local + soc + n1 + prep）；或分步 `d3_local_rehearsal` → `d3_soc_local_rehearsal` → `d3_n1_local_rehearsal` → `d3_prep_check`

| # | 项 | Owner | Done |
|---|----|-------|:----:|
| 1 | D2 admin pack 绿 | 平台 | ✅ |
| 2 | D3 Chart / 文档骨架 | 运维 | ✅ |
| 3 | Bundle 完整性策略文档 + 本地校验演练 | 平台 | 🟨 |
| 4 | 运维面 healthz/证据约定文档 | 平台 | 🟨 |
| 5 | SOC/告警出口（enterprise opt-in）演练记录 | 运维 | 🟨 |
| 6 | N-1 升级/回滚 live 或等价演练 | 运维 | 🟨 |
| 7 | enterprise 默认仍 0（回归） | 平台 | ✅ |
| 8 | ADR Accepted 联签 | 架构 | ✅ |

`d3_production_authorized: false`

## 自动 vs 人工

| 自动（prep / local） | 仍须人工 |
|----------------------|----------|
| #1 D2 admin | #5 **生产** SOC 出口 |
| #2 chart/docs | #3/#4/#6 生产类或签字升 ✅ |
| #3/#4/#6 本地 checksum/回滚（🟨） | |
| #5 本地 file-sink SOC（🟨，无外联） | |
| #7 enterprise=0 | |
| #8 ADR | |
