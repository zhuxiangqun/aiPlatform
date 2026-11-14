---
doc_type: Reference
---

# R11 · 元评测初始阈值 + Owner 签字页

> 计划 §4.4 / §15 R11 · 改阈值 = semantic → 走 [`SHA_CHANGE_LOG.md`](./SHA_CHANGE_LOG.md)  
> **状态**：**已签字（2026-11-14）** → §15 R11 可勾完成  
> **诚实锁**：**≠** Tier A 扩容自动放行（仍须元评测绿灯）

---

## 初始阈值（v0）

| 检查 | 初始阈值 | Owner 角色 |
|---|---|---|
| Judge calibration | agreement ≥ **0.80**；κ ≥ **0.60**；ECE ≤ **0.10** | 评测 owner |
| Gold audit | 抽样错误率 ≤ **5%**；争议有仲裁记录 | 标注/仲裁 |
| Contamination | 超阈 → **advisory**（不得当 Tier A 硬阻断宣称） | 评测 owner |
| Holdout isolation | 开发/调参禁止碰 holdout；仅发布前一次揭榜 | 评测 owner |
| Inter-annotator 稳定 | 双人 κ ≥ **0.60**；漂移超阈触发重标 | 标注/仲裁 |

阈值版本：`meta-eval-thresholds.v0`（2026-11-14）

---

## Owner 签字栏（已完成）

| 字段 | 值 |
|---|---|
| 阈值版本 | meta-eval-thresholds.v0 |
| Owner | 朱向群 |
| 签字日 | 2026-11-14 |
| 结论 | **☑ accept 初值** |
| 备注 | 可调阈值须走 SHA/semantic 变更控制 |

签字记录：[`evidence/r11_meta_eval_thresholds_signoff.v1.json`](./evidence/r11_meta_eval_thresholds_signoff.v1.json)

---

## 与 Phase 3.5 关系

签字只锁定**尺子门槛**；Phase 3.5 落地协议可另文 `META_EVAL_V0.md`。无元评测绿灯前，不新增 Tier A gate 宣称。
