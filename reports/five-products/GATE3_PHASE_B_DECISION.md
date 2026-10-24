# Gate3 Phase B 决定（2026-10-24）

**结论：批准 Gate3 Phase B（Pi Thin 试点升格）。**

## 依据

| 项 | 内容 |
|----|------|
| 授权人 | 架构决策 owner × 业务场景 owner（兼任） |
| 对话授权 | 2026-10-24「可以授权」×2（Phase A G3-1/2/3 已闭环后） |
| 前置 | `GATE3_DECISION.md` / ADR-08 / G3-1–G3-3 已接线 |
| 场景 | `fp-customer-lock-service-bundle-pi-diag-001` |

## 批准范围（可执行）

| ID | 范围 |
|----|------|
| G3-B1 | 试点消费 **export_pi_bundle 产物**（非仅 fixtures 源目录）作 `AIPLAT_APP_HOME` |
| G3-B2 | HTTP Thin 在 `AIPLAT_SLICE_EVIDENCE=1` 时写入切片证据 JSONL（含 `scenario_id`） |
| G3-B3 | `gate3_pi_thin_pilot.sh` 支持 `GATE3_PI_THIN_PHASE=b`：export → smoke → 断言证据落盘 |
| G3-B4 | 文书：本文件 + `GATE3_PI_THIN_PILOT.md` Phase B DoD；仍禁 ENTERPRISE=1 混跑 |

## 明确不在本次批准内

| 项 |
|----|
| 五产品一次全拆 / 搬仓 / 控制面拆库 |
| 对外 E4 宣传或宣称五产品已全面产品化 |
| 本体进主路径；诊断 Evaluation 二期；自动跨平台修复 |
| 无 ADR 修订的第二产品拆分 |

## 签署

架构 × 业务（兼任）：**批准 Gate3 Phase B — Bundle + 证据发射** · 2026-10-24  
