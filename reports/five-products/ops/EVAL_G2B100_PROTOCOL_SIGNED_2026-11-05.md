---
generated_at: 2026-11-11
doc_type: Report
---

# G2B-100 Protocol — 三方已签（2026-11-05）

> **状态**：✅ **SIGNED** · Holdout **方案 A**  
> **母版**：[G2B_100_PROTOCOL.md](../../../packages/aiplat-evaluation/docs/a3/G2B_100_PROTOCOL.md)（文首已改为 SIGNED）  
> **起草稿**：[EVAL_G2B100_PROTOCOL_SIGNOFF_PARTIAL_2026-11-05.md](./EVAL_G2B100_PROTOCOL_SIGNOFF_PARTIAL_2026-11-05.md)  
> **硬锁**：签署后仍默认 `accuracy_claim=false`；可开 31–100 确认性双标计入本版本

---

## 签署摘要

| 项 | 值 |
|---|---|
| Benchmark | `eval.g2b.benchmark.v1` |
| Holdout | **方案 A**：n=100 全部确认性；门槛按 n=100 |
| Evaluation 产品负责人 | 朱向群 · 2026/11/05 |
| 评测方法负责人 | 朱莹 · 2026/11/05 |
| 独立 QA / 标注协调人 | 朱鸿林 · 2026/11/05 |
| Model/prompt freeze owner | 拟朱向群 · hash **PENDING** |
| Freeze 时间戳 | **PENDING** |
| 出卷包 | `human_pack/20261105T132500Z-n100/`（70 条待双标） |

配额 / 门槛 / κ / claim 模板以母版 §3–6 为准（签署即冻结）。

### 结论摘录

```
Protocol：G2B_100_PROTOCOL · eval.g2b.benchmark.v1 · SIGNED 2026-11-05
Holdout：方案 A
签署：朱向群 / 朱莹 / 朱鸿林
下一步：freeze → 双标 31–100 → κ/accuracy aggregate → 范围审查（默认不翻 accuracy_claim）
```
