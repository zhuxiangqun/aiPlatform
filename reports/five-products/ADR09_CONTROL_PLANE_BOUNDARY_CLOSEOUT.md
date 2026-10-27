# 控制面边界轨收口（ADR-09 下一单产品）

- **状态**：**已收口** · 2026-10-27  
- **授权**：`ADR09_NEXT_CONTROL_PLANE_DECISION.md`（#458）  
- **边界**：`ADR09_CONTROL_PLANE_BOUNDARY.md` A–C 全齐

## 已完成

| 序 | 内容 | PR |
|----|------|-----|
| 立项 | 控制面单产品 Accepted（compose 长驻不含） | #458 → `e5c9364` |
| A | 部署边界清单 | #459 → `92d8e0c` |
| B | README / env「正式可选」用语 | #460 → `8ab4aa3` |
| C | one-shot health（127.0.0.1，停即退） | 本 PR |

## 生产含义（窄）

- 控制面 **可选**独立健康探针；**非**强制生产默认共置改独立  
- Identity / Policy 仍单一权威（ADR-02）；禁止第二 PolicyGate  
- 入口：`bash scripts/adr09_control_plane_optional_phase_health.sh`  
- 回滚：进程退出；切回共部署

## 主轨后进度

| 项 | 状态 |
|----|------|
| 五产品单产品边界 | ✅ 诊断 / Pi / FDE / 本体 / 控制面均已收口 |
| compose 长驻 | ❌ 见 `ADR09_REMAINING_PRODUCTS_DRAFT.md` |
