---
doc_type: Report
title: evo g*_complete 生产宣称 Prep 单（可打印）
status: active
authority: supporting
language: zh-CN
created: 2026-11-27
---

# evo · `g*_complete` 生产宣称 Prep 单

> **性质**：生产宣称前核对单。**不是** g* 完成证明。  
> 待批机读：`evo-g-complete-production.pending.json`  
> D5 证据：`reports/architecture/evo-compute/production-deepen-d5-evidence.md`

## 1. 会前核对（今日实测）

| # | 检查 | 2026-11-27 | 通过? |
|---|------|------------|:-----:|
| E1 | D5 `track_engineering_complete` | `true`（仅工程轨） | ◐ |
| E2 | `g1_complete` | `false` | — |
| E3 | `g2_complete` | `false` | — |
| E4 | `g3_complete` | `false` | — |
| E5 | `certified` / `e2_claimed` | `false` / `false` | — |
| E6 | `evaluate_evo_g{1,2,3}_exit_readiness` | 均为 `ready=false` | ☐ |
| E7 | 生产 holdout 认证 | **缺** | ☐ |
| E8 | 真实 Canary + 回滚演练 | **缺** | ☐ |
| E9 | 活台账 HITL 100%（HUMAN_GATE） | **缺** | ☐ |

→ **今日结论：不得**宣称任一 `g*_complete` / E2 / certified。

## 2. 分闸解锁清单（按闸分别另批）

| 闸 | 工程可证 | 生产宣称额外要 | 宣称前 API |
|----|----------|----------------|------------|
| G1 | suite / slice 绿 | 生产 holdout（surrogate≠生产） | `evaluate_evo_g1_exit_readiness` → ready |
| G2 | suite 绿 | 实测 eval/FDE 覆盖 | `evaluate_evo_g2_exit_readiness` → ready |
| G3 | AIS slice≠claim | 活台账 HITL 100% + owner 生产包 | `evaluate_evo_g3_exit_readiness` → ready |

**铁律**：`track_engineering_complete`（D5）**≠** 任一 `g*_complete`。套件绿不得单独宣称。

## 3. 批准句模板（单闸 · 条件满足后另 PR）

```text
批准：evo 生产宣称 gN_complete（N=1|2|3）。
前置：evaluate_evo_gN_exit_readiness.ready=true；附生产 holdout/Canary/HITL 证据路径。
含：更新生产宣称记录；开放对应运营叙事。
不含：顺带宣称其他 g*；certified；e2_claimed；用沙箱 fixture 冒充生产。
批准人：________（owner / 非作者按闸规） 日期：________
证据：________
```

落地：按闸新建 `evo-gN-complete-production.approved.json`  
**禁止**把 `evo-g-complete-production.pending.json` 直接改 `approved`。

## 4. 今日可签（窄）

```text
确认：D5 track_engineering_complete 仅表示加深工程轨收口；
g1/g2/g3_complete、certified、e2_claimed 全部维持 false。
不含：任何生产 g* / E2 / certified 宣称。
确认人：________ 日期：2026-11-27
```

## 5. 验证命令

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 - <<'PY'
from core.api import core_facade as f
d5 = f.evaluate_evo_production_deepen_track_closeout()
assert d5.get("track_engineering_complete") is True
assert d5.get("g1_complete") is False
assert d5.get("g2_complete") is False
assert d5.get("g3_complete") is False
assert d5.get("certified") is False
assert d5.get("e2_claimed") is False
for fn in (f.evaluate_evo_g1_exit_readiness, f.evaluate_evo_g2_exit_readiness, f.evaluate_evo_g3_exit_readiness):
    r = fn()
    assert r.get("ready") is False
print("ok: D5≠g*; exit readiness not ready")
PY
```
