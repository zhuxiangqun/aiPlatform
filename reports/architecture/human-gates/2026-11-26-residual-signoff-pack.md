---
doc_type: Report
title: 人工门残差签批执行包（Ollaya / KS Full / evo g*）
status: active
authority: supporting
language: zh-CN
created: 2026-11-26
---

# 人工门残差签批执行包 · 2026-11-26

> 触发：对话「你帮我做吧」。  
> Actor 记录惯例：非作者 `朱莹` / `zhu-ying`（与 F11、G0 一致）。  
> **诚实锁**：本包**不**伪开采样 Go、**不**升 Full unconditional、**不**宣称 `g*_complete`。

## 总览

| 门 | 今日可做 | 今日结论 | 机读记录 |
|----|----------|----------|----------|
| Ollaya 采样 Go | 会签包 + staging 窗口窄授权 | **采样仍 No-Go**；筹备已授权 | `ollaya-staging-window-authorize.approved.json` + [0.6 会签包](../../../docs/architecture/plans/ollaya-phase0-06-signoff-pack.md) |
| KS Full unconditional | 核对窗口 + 保留 conditional | **阻断**（窗口未达标；批准已有但不足） | `ks-full-unconditional.pending.json` |
| evo `g*_complete` | 生产宣称待批清单 | **阻断**（D5≠g*；缺真实 Canary/holdout） | `evo-g-complete-production.pending.json` |

## 实测（本机 · 2026-11-26）

### KS SLO 窗口

```text
approval_ok=true   # pilot-slo-attainment-approval-record.approved.json（朱莹 conditional）
window_meets_targets=false
wiring_ok=false    # snapshot_unavailable（本机无生产样本库）
attainment_ok=false
certified=false
n24_full_conformance=false
# note: Full remains conditional
```

→ **不得**把 Full `decision` 从 `conditional` 改为无例外 `approved`。

### Ollaya

```text
dev smoke only；staging/prod §0.3/0.4 空
t3_hits 远低于 100
C7/C8 未会签
→ 采样 No-Go（工程建议书维持）
```

### evo

```text
track_engineering_complete（D5）≠ g*_complete
套件锁定 g1/g2/g3_complete=false
certified=false / e2_claimed=false
```

## 窄批准句（已执行）

> 批准：**人工门筹备与 Ollaya staging/prod ≥7 天 collector 窗口启动**。  
> **含**：0.6 会签包落盘、staging 采集授权、KS/evo 待批清单。  
> **不含**：开采样 / 挂 classify / Full unconditional / `g*_complete` / E2 / certified 生产宣称。

## 解锁后怎么签（人到场时照抄）

### A. Ollaya 采样 Go（窗口+会签齐后）

1. 填满证据包 §0.1/0.3/0.4 与 0.6 勾选表  
2. 另 PR + 批准句：`批准 Ollaya 挂 classify + 开低采样；不含 1b / 省 token`  
3. 新建 `ollaya-sampling-go.approved.json`（勿改今日 No-Go 记录冒充）

### B. KS Full unconditional

1. 生产窗口三指标达标 → `attainment_ok=true`  
2. 关闭 Full 批准中 `exceptions`（尤其 SLO）或新开 unconditional 记录  
3. 非作者确认；**禁止**复用 SLO-only 批准冒充 Full

### C. evo `g*_complete`

1. 真实 holdout + 生产 Canary（非沙箱）+ 活台账 HITL 100%  
2. owner 签生产包（D4 仅 deepen 签批 ≠ g3）  
3. 用**生产证据**跑 `evaluate_g*_exit_readiness`；套件绿仍不得单独宣称

## 验证

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 - <<'PY'
from core.api import core_facade as f
r = f.evaluate_knowledge_slo_attainment_window(
    "default",
    domain_id="lock-service",
    approval_record_path="reports/products/knowledge-system/v4.3.1/pilot-slo-attainment-approval-record.approved.json",
)
assert r.get("attainment_ok") is False
assert r.get("certified") is False
print("ok: attainment blocked; Full stays conditional")
PY
```
