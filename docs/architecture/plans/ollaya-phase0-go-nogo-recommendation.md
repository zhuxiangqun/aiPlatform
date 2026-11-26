---
doc_type: Architecture
doc_id: OLLAYA_PHASE0_GO_NOGO_RECOMMENDATION
status: recommendation
authority: supporting
created: 2026-11-26
last_reviewed: 2026-11-27
language: zh-CN
purpose: 阶段 0 Go/No-Go 工程建议（≠ 正式会签；≠ 开采样）
---

# Ollaya 阶段 0 · Go/No-Go 工程建议

> 依据：`ollaya-decision-layer-implementation-plan.md` §0.7；证据包 `ollaya-phase0-baseline-evidence.md`。  
> **性质**：工程建议书。**不是** 0.6 正式会签，**不是** 批准开采样 / 挂 classify / 进 1b。  
> Prep 单入口：`reports/architecture/human-gates/2026-11-27-prep-pack.md`。

## 建议结论（2026-11-26 · 2026-11-27 维持）

| 轨 | 建议 | 理由 |
|----|------|------|
| 有条件豁免（默关骨架） | **维持 Go** | #616 已合入；`enabled=false`；`classify_hook_wired=false` |
| **开采样 + 挂 classify** | **No-Go** | 缺 staging/prod ≥7 天窗口；本机 `t3_hits` 远低于 100；0.6 C7/C8 未会签 |
| 阶段 1b 替换 T3 | **No-Go** | 未达阶段 1 退出门槛 |

## 对照 §0.7 默认阈值

| 条件 | 现状 |
|------|------|
| 0.1 填实 | 本机冒烟有；staging/prod 窗口空 |
| 0.3/0.4 真实窗口 | 仅 dev smoke（total=10 / t3=7） |
| 0.6 C1–C8 会签 | 工程自评草稿有；正式会签空；C7/C8 不可工程自签 |
| `t3_hits ≥ 100` 或（≥5% 且 total≥500） | **未达标** |

## 解锁开采样前必须

1. staging（或 prod 只读副本）跑 collector ≥7 天并填 0.3/0.4  
2. 召开 0.6 正式评审并勾选 C1–C8（含隐私 C7、值班 C8）  
3. 书面批准「挂 classify 钩子 + 开低采样」另 PR（禁止与骨架同批偷渡）

## 2026-11-26 执行进度（clause-sync）

| 项 | 状态 |
|----|------|
| 工程建议（采样 No-Go） | **维持** |
| 0.6 会签包 | ✅ [ollaya-phase0-06-signoff-pack.md](./ollaya-phase0-06-signoff-pack.md) |
| staging 窗口窄授权 | ✅ `reports/architecture/human-gates/ollaya-staging-window-authorize.approved.json` |
| 日采 harness + Day-0 台账 | ✅ `scripts/ollaya_phase0_daily_collect.sh` + `ollaya-window-ledger.md`（**dev**；≠ staging Go） |
| staging/prod 满窗 / C7 / C8 / 采样 Go | ☐ 仍待 |
| 2026-11-27 Prep 单（可打印） | ✅ `reports/architecture/human-gates/ollaya-06-meeting-prep-sheet.md`；Day-1 实采 total=0 / shadow 默关（dev；≠ Go） |

## 明确不交付

影子延迟认证、Ollaya 准确率、默认开采样、省 token 叙事、1b 替换。
