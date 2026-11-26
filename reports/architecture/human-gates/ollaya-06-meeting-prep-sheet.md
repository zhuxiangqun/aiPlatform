---
doc_type: Report
title: Ollaya 0.6 会签 Prep 单（可打印）
status: active
authority: supporting
language: zh-CN
created: 2026-11-27
---

# Ollaya 0.6 · 会签 Prep 单

> **性质**：开会材料 + 会前核对。**不是** 采样 Go，**不是** 挂 classify，**不是** 1b。  
> 权威勾选表：[ollaya-phase0-06-signoff-pack.md](../../../docs/architecture/plans/ollaya-phase0-06-signoff-pack.md)  
> 窄批已有：`ollaya-staging-window-authorize.approved.json`（仅筹备窗口）

## 1. 会前核对（今日可勾）

| # | 项 | 实测 2026-11-27 | 勾选 |
|---|----|-----------------|:----:|
| P1 | 0.6 会签包与 C1–C8 表已打印/共享 | ✅ 已落盘 | ☐ |
| P2 | staging 窗口窄授权已批（≠ Go） | ✅ authorize_prep | ☐ |
| P3 | 日采脚本可用 | ✅ `scripts/ollaya_phase0_daily_collect.sh` | ☐ |
| P4 | 台账已开（dev Day-0） | ✅ ledger；Day-1 core 离线 SKIP | ☐ |
| P5 | staging `CORE_BASE` 已登记 | ❌ **未配置** | ☐ |
| P6 | 隐私 owner（C7）已邀约 | ☐ 待填 | ☐ |
| P7 | 值班 owner + 健康检查入口（C8）已邀约 | ☐ 待填 | ☐ |

### 运维登记栏（会上填）

| 字段 | 值 |
|------|-----|
| staging CORE_BASE | `https://________________/core` |
| 日采 cron（谁/哪台） | |
| 隐私会签人 C7 | |
| 值班 owner C8 | |
| 健康检查入口 | |

## 2. 阻塞采样 Go（不得跳过）

| # | 条件 | 现状 |
|---|------|------|
| W1 | staging/prod 部署含 route-stats + decision_shadow | 未确认 |
| W2 | 日采 ≥7 天（staging 分表） | Day-0=dev；Day-1=SKIP；staging=0 |
| W3 | §0.3/0.4 填实（勿混 dev） | 空 |
| W4 | `t3_hits≥100` 或（`t3_llm_pct≥5%` 且 total≥500） | 未达标 |
| W5 | C7 隐私批 | 未签 |
| W6 | C8 值班 | 未签 |

## 3. 会上只做这两档

| 档 | 允许结论 | 产出 |
|----|----------|------|
| A · 筹备复核 | 「材料齐；继续采 staging」 | 纪要 + 更新台账 meta |
| B · 正式 0.6 会签 | C1–C8 全勾（或有条件闭环） | 签批表填满；**仍不等于** 开采样 |

## 4. 解锁后另批（禁止本会偷渡）

**仅当** W1–W6 + C1–C8 齐后，**另 PR** 使用：

```text
批准：Ollaya 挂 classify 钩子 + 开低采样。
含：decision_shadow 低采样开流（环境：staging|prod；比例：___%）。
不含：阶段 1b 替换 T3；省 token 叙事；默认全量开采样；准确率宣称。
批准人：________（非作者） 日期：________
```

落地：新建 `reports/architecture/human-gates/ollaya-sampling-go.approved.json`  
**禁止**改写 `ollaya-staging-window-authorize.approved.json` 冒充采样 Go。

## 5. 明确不交付

采样 Go · 挂 classify · 1b · 假灌 `t3_hits` · 用 dev 台账冒充 staging 满窗。
