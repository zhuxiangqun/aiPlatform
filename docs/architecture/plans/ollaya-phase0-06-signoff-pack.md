---
doc_type: Architecture
doc_id: OLLAYA_PHASE0_06_SIGNOFF_PACK
status: active
authority: supporting
created: 2026-11-26
last_reviewed: 2026-11-26
language: zh-CN
purpose: Ollaya 0.6 正式会签执行包（≠ 采样 Go；≠ 挂 classify）
---

# Ollaya 阶段 0 · 0.6 正式会签包

> 触发：对话「你帮我做吧」（2026-11-26）。  
> 依据：`ollaya-phase0-baseline-evidence.md` §0.6–0.7；`ollaya-phase0-go-nogo-recommendation.md`。  
> **性质**：会签筹备与窄授权执行包。**不是** 采样 Go，**不是** 挂 classify，**不是** 进 1b。

## 1. 今日窄批准（已记录）

| 项 | 结论 |
|----|------|
| 默关骨架豁免 | **维持 Go**（#616；`enabled=false`；`classify_hook_wired=false`） |
| staging/prod ≥7 天 collector 窗口 | **授权启动**（见 `reports/architecture/human-gates/ollaya-staging-window-authorize.approved.json`） |
| 0.6 正式评审会 | **授权筹备**（本包为议程与勾选表） |
| **开采样 + 挂 classify** | **仍 No-Go**（缺真实窗口 + C7/C8 未签） |
| 阶段 1b 替换 T3 | **仍 No-Go** |

## 2. 会前必补（阻塞采样 Go）

| # | 动作 | Owner | 状态 |
|---|------|-------|:----:|
| W1 | staging（或 prod 只读副本）部署含 route-stats + decision_shadow 的 core | 运维 | ☐ |
| W2 | 跑 `scripts/collect_domain_router_route_stats.py --env staging` ≥7 天 | 运维 | ☐ |
| W3 | 把窗口填入证据包 §0.1 / §0.3 / §0.4（分表，勿混 dev） | 试点负责人 | ☐ |
| W4 | 达 §0.7 阈值：`t3_hits≥100` 或（`t3_llm_pct≥5%` 且 total≥500） | 测量 | ☐ |
| W5 | 隐私批 C7（字段白名单 + TTL） | Data Governance | ☐ |
| W6 | 指定决策服务值班 / 健康检查入口 C8 | 试点负责人 | ☐ |

### W2 参考命令

```bash
# staging 日采（示例；以实际 base URL 为准）
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform \
  python3 scripts/collect_domain_router_route_stats.py --env staging
# 影子骨架状态（须仍 enabled=false）
curl -sS "$CORE_BASE/api/core/diagnostics/decision-shadow/status"
```

## 3. 0.6 评审勾选表（会上填 · 未签前禁止合并影子开流）

| # | 检查项 | 工程预审 | 评审结论 |
|---|--------|----------|----------|
| C1 | 影子关闭时 `classify` 语义不变 | 建议通过 | ☐通过 ☐有条件 ☐驳回 |
| C2 | 主路径无 await 决策 HTTP | 建议通过 | ☐通过 ☐有条件 ☐驳回 |
| C3 | 队列满/超时仅 drop | 建议通过 | ☐通过 ☐有条件 ☐驳回 |
| C4 | `decision_shadow.enabled` 默认 false | 建议通过 | ☐通过 ☐有条件 ☐驳回 |
| C5 | 审计字段 ⊆ 白名单；默认无原文 | 建议有条件（隐私确认数字） | ☐通过 ☐有条件 ☐驳回 |
| C6 | 可一键关闭 | 建议有条件（附页已备） | ☐通过 ☐有条件 ☐驳回 |
| C7 | 隐私/脱敏策略已批 | **工程不可自签** | ☐通过 ☐有条件 ☐驳回 |
| C8 | 有人维护决策服务 | **工程不可自签** | ☐通过 ☐有条件 ☐驳回 |

| 字段 | 填写 |
|------|------|
| 评审日期 | |
| 与会人 | |
| 纪要链接/附件 | |
| 会签（试点负责人） | ☐签字 |
| 隐私会签（C7） | ☐签字 |
| 值班 owner（C8） | 姓名：________ · 健康检查入口：________ |

## 4. 会后解锁序（禁止偷渡）

1. 本表 C1–C8 全部通过（或有条件且条件闭环）  
2. §0.3/0.4 真实窗口达标  
3. **另 PR** 书面批准「挂 classify 钩子 + 开低采样」  
4. 仅此后允许影子流量；1b 另案

## 5. 明确不交付

采样 Go、挂 classify、默认开采样、省 token 叙事、1b 替换、影子延迟认证、Ollaya 准确率。
