# compose 长驻部署边界清单（ADR-09 后续 #1）

- **状态**：**清单已立** · 2026-10-27 — 授权真源 `ADR09_COMPOSE_LONG_RUNNING_DECISION.md`（#463）  
- **范围**：仅 compose 长驻（正式可选 profile）  
- **不含**：强制全环境生产默认长驻；超边界 E4；第二 Identity/PolicyGate；一次写满五套长驻

## As-Is（当前）

| 面 | 现状 |
|----|------|
| 诊断 | `compose.adr10-diagnosis-mvp.yml` — `run --rm` one-shot |
| Pi Thin | `compose.gate3-pi-thin.yml` / `compose.pi-thin-optional.yml` — 试点/可选；文档要求 `down -v` |
| FDE / 本体 / 控制面 | 仅主机 one-shot health；无专用长驻 compose |
| 生产默认 | 仍以共部署 / one-shot 为主；长驻未强制 |

## To-Be（长驻立项后 · 分 PR）

| 面 | 目标 | 回滚 |
|----|------|------|
| Profile | 每已批产品可有**显式** `*.long-running.yml`（或 compose profile 名）；`up -d` + 文档化停机 | `down -v`；切回 one-shot |
| 首批建议 | Pi Thin 长驻升格（已有 compose 真源）→ 诊断 → 其余按需 | 停对应服务 |
| 端口 / 卷 | env 驱动；禁止硬编码业务名进 core | 改回 one-shot env |
| 默认 | **可选**启用；禁止本 BOUNDARY 默示改全仓生产默认 | 不设 `restart: always` 为全环境强制 |

## 分 PR 建议顺序（各 ≤ inflation）

| 序 | 主题 | 非目标 |
|----|------|--------|
| A | ✅ 本清单 + SCHEDULE / LANDING 引用 | 搬仓；一次五套 |
| B | ✅ Pi Thin：`compose.pi-thin-long-running.yml` + README 启停 | 强制生产默认；改 Identity；一次五套 |
| C | ✅ 烟测：`scripts/adr09_compose_pi_thin_long_running_smoke.sh`（up→health→down -v） | 常驻 CI 占资源不清理 |

## 回滚总则

1. `docker compose -f <long-running.yml> down -v`  
2. 切回 one-shot / 主机 `*_phase_health.sh` / pilot 脚本  
3. 不启用第二 Identity 权威  
4. 生产是否默认长驻须**另决**（本清单不授权）
