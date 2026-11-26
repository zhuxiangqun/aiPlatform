---
doc_type: Report
title: KS Full unconditional Prep 单（可打印）
status: active
authority: supporting
language: zh-CN
created: 2026-11-27
---

# KS Full · unconditional Prep 单

> **性质**：升 unconditional 前核对单。**不是** 批准本身。  
> 待批机读：`ks-full-unconditional.pending.json`  
> 现网批准：`pilot-full-approval-record.approved.json` → `decision=conditional` · `exceptions=[SLO]`

## 1. 会前核对（今日实测）

| # | 检查 | 2026-11-27 | 通过? |
|---|------|------------|:-----:|
| K1 | SLO 批准存在且非作者 | `approval_ok=true`（朱莹 conditional） | ◐ |
| K2 | 生产窗口三指标达标 | `window_meets_targets=false` | ☐ |
| K3 | 遥测快照可接线 | `wiring_ok=false`（snapshot_unavailable） | ☐ |
| K4 | attainment | `attainment_ok=false` | ☐ |
| K5 | certified / n24_full | **恒 false**（本门不宣称） | — |
| K6 | Full 现为 conditional + SLO 例外 | ✅ 已核对 JSON | ☐ |

→ **今日结论：不得**把 Full 从 `conditional` 改为无例外 `approved`。

## 2. 升 unconditional 前置（全绿才开批）

1. 生产样本库可 `get_slo_snapshot`（`wiring_ok=true`）  
2. 窗口达目标（`window_meets_targets=true`）→ `attainment_ok=true`  
3. 关闭 Full 批准中 `exceptions`（尤其 `SLO`），或**新建** unconditional 记录  
4. 非作者独立确认（禁止作者自签；禁止复用 SLO-only 批准冒充 Full）

## 3. 批准句模板（条件满足后另 PR）

```text
批准：pilot lock-service Full unconditional（清除 SLO 例外）。
前置证据：attainment_ok=true；window_meets_targets=true；wiring_ok=true。
含：更新/新建 Full 批准记录 decision=approved 且 exceptions=[]。
不含：准确率宣称；用本机 sandbox 样本冒充生产窗口；certified 口头升级。
批准人：________（非作者） 日期：________
证据路径：________
```

落地：新建 `pilot-full-approval-record.unconditional.approved.json`（或同等 record_id）  
同时将 `ks-full-unconditional.pending.json` 的 `status` 改为 `superseded` 并指向新记录。  
**禁止**原地把 pending 改成 approved 而不附生产证据。

## 4. 今日可签（窄）

若只需确认「仍保持 conditional」：

```text
确认：KS Full 维持 conditional（SLO 例外仍在）。
不含：unconditional；certified；n24_full_conformance 生产宣称。
确认人：________ 日期：2026-11-27
```

## 5. 验证命令（升批前后必跑）

```bash
PYTHONPATH=aiPlat-core:aiPlat-infra:aiPlat-platform python3 - <<'PY'
from core.api import core_facade as f
r = f.evaluate_knowledge_slo_attainment_window(
    "default",
    domain_id="lock-service",
    approval_record_path="reports/products/knowledge-system/v4.3.1/pilot-slo-attainment-approval-record.approved.json",
)
print({k: r.get(k) for k in (
    "approval_ok","wiring_ok","window_meets_targets","attainment_ok",
    "certified","n24_full_conformance")})
# 升 unconditional 前至少：
assert r.get("certified") is False
# 升 unconditional 时还须：
# assert r.get("attainment_ok") is True and r.get("window_meets_targets") is True
PY
```
