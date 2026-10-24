# 五产品落地收口（2026-10-24）

> L1 + Gate1 修订 + Gate2 落地已合入。**D13 已升格客户场景**；**Gate 3 有条件批准（仅 Pi Thin 试点）**。五产品全拆 / 对外 E4 宣传仍未批。

## 已合入（摘要）

| 项 | 证据 |
|----|------|
| 首切片 WP0–WP5 / E3 | PR [#381](https://github.com/zhuxiangqun/aiPlatform/pull/381) → `5bfdb86` |
| MB-02 models 模板 | [#382](https://github.com/zhuxiangqun/aiPlatform/pull/382) |
| MB-05 emit opt-in | [#383](https://github.com/zhuxiangqun/aiPlatform/pull/383) |
| MB-01 再核实 + MB-03 RFC + MB-04 清单 | [#384](https://github.com/zhuxiangqun/aiPlatform/pull/384) |
| inflation 豁免退役（首切片） | PR [#385](https://github.com/zhuxiangqun/aiPlatform/pull/385) → `a4c4e0c` |
| Gate2 批准 + MB-03 SQLite + MB-01 Facade | PR [#387](https://github.com/zhuxiangqun/aiPlatform/pull/387) → `5b56477` |
| Gate2 inflation 豁免退役 | PR [#388](https://github.com/zhuxiangqun/aiPlatform/pull/388) → `3530d9a` |
| MB-01 agent interfaces | PR [#389](https://github.com/zhuxiangqun/aiPlatform/pull/389) → `e0b089a` |
| D13 升格 + Gate3 有条件批准（文书） | PR [#391](https://github.com/zhuxiangqun/aiPlatform/pull/391) → `364f319` |
| Gate3/D13 inflation 豁免退役 | 本 PR：`exemptions: []` |

## Gate 2 / D13 / Gate 3

| 项 | 状态 |
|----|------|
| Gate 2 | ✅ 已落地 |
| D13 | ✅ 客户场景 `fp-customer-lock-service-bundle-pi-diag-001`（江苏锁安 / lock-service）；见 `D13_CUSTOMER_ENDORSEMENT.md` |
| Gate 3 | ✅ **有条件** — 仅 Pi Thin 试点（`GATE3_DECISION.md` + `ADR-08-deploy-split.md` + `GATE3_PI_THIN_PILOT.md`） |
| 五产品全拆 / 对外 E4 宣传 | ❌ 未授权 |

## 运维备忘

- Pi models：`~/.pi/agent/models.json`（模板见 `packages/aiplat-pi-runtime/models.json.example`）  
- 证据发射：`AIPLAT_SLICE_EVIDENCE=1`（默认关）  
- 证据存储：默认 SQLite；`AIPLAT_SLICE_EVIDENCE_STORE=file` 回退  
- Gate3 试点：见 `GATE3_PI_THIN_PILOT.md`（密钥与控制面分离）  
