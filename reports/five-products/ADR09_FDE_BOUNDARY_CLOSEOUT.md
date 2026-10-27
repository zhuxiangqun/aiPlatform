# FDE 边界轨收口（ADR-09 下一单产品）

- **状态**：**已收口** · 2026-10-26  
- **授权**：`ADR09_NEXT_FDE_DECISION.md`（#448）  
- **边界**：`ADR09_FDE_BOUNDARY.md` A–C 全齐

## 已完成

| 序 | 内容 | PR |
|----|------|-----|
| 立项 | FDE 单产品 Accepted（compose 长驻不含） | #448 → `36ad7a2` |
| A | 部署边界清单 | #449 → `584a273` |
| B | README / env「正式可选」用语 | #450 → `79b57d9` |
| C | one-shot health（127.0.0.1，停即退） | #451 → `40891a2` |

## 生产含义（窄）

- FDE **可选**独立健康探针；**非**强制生产默认共置改独立  
- 签收唯一入口仍为控制面 `POST …/fde/acceptance/signoff`  
- 入口：`bash scripts/adr09_fde_optional_phase_health.sh`  
- 回滚：进程退出；切回共部署；`AIPLAT_FDE_REQUIRE_DIAG_REPORT_FOR_SLICE=0` 仅应急

## 主轨后进度

| 项 | 状态 |
|----|------|
| 诊断 MVP / Pi Thin / FDE 边界 | ✅ 均已收口 |
| 本体单产品 + 边界 A–C | ✅ #453–#456 / `ADR09_ONTOLOGY_BOUNDARY_CLOSEOUT.md`（长驻不含） |
| 控制面单产品 + 边界 A–C | ✅ #458–#461 / `ADR09_CONTROL_PLANE_BOUNDARY_CLOSEOUT.md`（长驻不含） |
| compose 长驻 | ❌ 见 `ADR09_REMAINING_PRODUCTS_DRAFT.md` |
