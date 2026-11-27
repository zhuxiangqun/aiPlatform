---
doc_type: Report
title: Ollaya Phase 0 observation window ledger
status: active
authority: supporting
language: zh-CN
created: 2026-11-26
---

# Ollaya Phase 0 · 观测窗口台账

> 授权：`ollaya-staging-window-authorize.approved.json`（筹备窄批）。  
> 日采：`scripts/ollaya_phase0_daily_collect.sh`。  
> **≠ 采样 Go · ≠ 挂 classify · ≠ 1b**。staging/prod 真实窗口未满 7 天前禁止开流。

## Window meta

| 字段 | 值 |
|------|-----|
| window_id | `ollaya-phase0-dev-2026-11-26` |
| opened_at | 2026-11-26（Day-0） |
| target_close | ≥2026-12-03（满 7 天） |
| env_today | **dev**（本机 `127.0.0.1:8002`） |
| staging CORE_BASE | **不可用**（负责人确认 2026-11-27：暂无 staging URL；Go 仍须 staging/prod 分表） |
| decision_shadow | `enabled=false`；`classify_hook_wired=false`（Day-2 复核） |
| 原则 | 少用生成式 LLM 做选择题（实施计划 §0.1）；≠ 开采样 |

## Daily rows（自动/半自动追加）

| 环境 | 窗口 | total | t1% | t2% | t3% | t3_n | T3 p50 ms | T3 p95 ms | t2_boundary | t2_reject | 备注 |
|------|------|------|-----|-----|-----|------|-----------|-----------|-------------|-----------|------|
| dev | 2026-11-26T21:00+08 day0-window-open | 0 | 0.0 | 0.0 | 0.0 | 0 | None | None | 0 | 0 | replica=1/1; uptime_s=19259.1；日采 harness Day-0；≠ Go |
| dev | 2026-11-27T07:05+08 day1-prep-pack | 0 | 0.0 | 0.0 | 0.0 | 0 | None | None | 0 | 0 | replica=1/1; uptime_s=55434.8；shadow enabled=false / hook=false；≠ Go |
| dev | 2026-11-27T12:05+0800 day2-principle-lock | 0 | 0.0 | 0.0 | 0.0 | 0 | None | None | 0 | 0 | replica=1/1; uptime_s=1125.7；原则锁定日采；shadow off；≠ Go |

> 注：07:00 曾误记 SKIP——agent 沙箱拦 `127.0.0.1:8002`，core 实际在听；已作废该行，以 07:05 实采为准。

## Honesty

- Day-0/1/2 本机 total=0 为预期（无强制灌流量）；**禁止**为凑 `t3_hits≥100` 灌假 classify。
- 本台账 **dev** 行不可单独支撑 §0.7 采样 Go；须 staging/prod ≥7 天 + 0.6 C1–C8。
- 日采若发现 `enabled=true` 或 `classify_hook_wired=true` → 脚本非 0 退出（诚实失败）。
- 「少用生成式做选择题」原则锁定 ≠ 采样 Go / ≠ 挂 classify。
