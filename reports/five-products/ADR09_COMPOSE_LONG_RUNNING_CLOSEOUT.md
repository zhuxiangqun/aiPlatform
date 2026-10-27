# compose 长驻边界轨收口（ADR-09）

- **状态**：**已收口** · 2026-10-27  
- **授权**：`ADR09_COMPOSE_LONG_RUNNING_DECISION.md`（#463；批句 **含**）  
- **边界**：`ADR09_COMPOSE_LONG_RUNNING_BOUNDARY.md` A–C 全齐

## 已完成

| 序 | 内容 | PR |
|----|------|-----|
| 立项 | compose 长驻 Accepted（可选 profile；≠ 强制默认） | #463 → `a0e5b1a` |
| A | 部署边界清单 | #464 → `0f33829` |
| B | 首个长驻 profile：Pi Thin | #465 → `fa0c341` |
| C | 烟测：`up -d` → health → `down -v` | #466 → `30a16aa` |

## 生产含义（窄）

- 长驻为**正式可选**；**非**全环境生产默认强制  
- 入口：`packages/aiplat-pi-runtime/compose.pi-thin-long-running.yml`  
- 烟测：`bash scripts/adr09_compose_pi_thin_long_running_smoke.sh`（必 `down -v`）  
- 回滚：`docker compose -f compose.pi-thin-long-running.yml down -v`

## 主轨后进度

| 项 | 状态 |
|----|------|
| ADR-09 点名项（五产品 + compose 长驻） | ✅ 边界收口 |
| 强制全环境生产默认长驻 / 超边界 E4·SLA | ❌ 须另决 |
