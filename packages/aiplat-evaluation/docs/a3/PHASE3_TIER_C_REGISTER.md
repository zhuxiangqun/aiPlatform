---
doc_type: Reference
---

# Phase 3 · Tier C 仅登记

> 机器：[`evidence/meta_eval/phase3_tier_c_register.v0.json`](./evidence/meta_eval/phase3_tier_c_register.v0.json) · 时点 2026-11-14T22:20:18+08:00
> n=**458** · **policy=`register_only`**

## 规则

| ✅ | ❌ |
|---|---|
| 登记符号名 | suite 挂接 / gate 宣称 |
| 保持与 A 槽隔离 | 挤占 A_candidate |
| 覆盖报表 C 列可计 n | 单一覆盖% |

```bash
python3 packages/aiplat-evaluation/scripts/phase3_tier_c_register.py
```
