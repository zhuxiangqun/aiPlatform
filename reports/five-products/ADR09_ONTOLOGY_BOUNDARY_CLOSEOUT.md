# 本体边界轨收口（ADR-09 下一单产品）

- **状态**：**已收口** · 2026-10-27  
- **授权**：`ADR09_NEXT_ONTOLOGY_DECISION.md`（#453）  
- **边界**：`ADR09_ONTOLOGY_BOUNDARY.md` A–C 全齐

## 已完成

| 序 | 内容 | PR |
|----|------|-----|
| 立项 | 本体单产品 Accepted（compose 长驻不含；不含控制面） | #453 → `b8e5627` |
| A | 部署边界清单 | #454 → `1e89d39` |
| B | README / env「正式可选」用语 | #455 → `7e4f062` |
| C | one-shot health（127.0.0.1，停即退） | 本 PR |

## 生产含义（窄）

- 本体 **可选**独立健康探针；**非**强制生产默认共置改独立  
- 配置权威仍为 `$AIPLAT_HOME/ontologies`（经 DomainRouter）；**禁止**平行 registry  
- 入口：`bash scripts/adr09_ontology_optional_phase_health.sh`  
- 回滚：进程退出；切回控制面共部署

## 主轨后进度

| 项 | 状态 |
|----|------|
| 诊断 MVP / Pi Thin / FDE / 本体 边界 | ✅ 均已收口 |
| 控制面 / compose 长驻 | ❌ 见 `ADR09_REMAINING_PRODUCTS_DRAFT.md` |
