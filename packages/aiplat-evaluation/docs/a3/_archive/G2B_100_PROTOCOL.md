---
doc_type: Archive
---

# G2B-100 Protocol（已签署）

> **状态**：✅ **SIGNED**（2026-11-05）· Holdout **方案 A**
> **签认留存**：[EVAL_G2B100_PROTOCOL_SIGNED_2026-11-05.md](../../../../../reports/five-products/ops/EVAL_G2B100_PROTOCOL_SIGNED_2026-11-05.md)
> **日期**：2026-11-04（起草）/ 2026-11-05（签署）
> **依据**：[改善执行计划](../../../../../reports/five-products/ops/EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md) §2.3 · [G2B_N100](./G2B_N100.md) · [G2B_ACCURACY_CLOSEOUT](./G2B_ACCURACY_CLOSEOUT.md)
> **诚实锁**：签署与达标后仍只允许 **scoped benchmark pass rate**；默认 `accuracy_claim=false`，通用准确率/安全认证/process_split **禁止**由本 protocol 单独打开。

---

## 1. 签认栏

| 角色 | 姓名 | 日期 | 签字/确认 |
|---|---|---|---|
| Evaluation 产品负责人 | 朱向群 | 2026/11/05 | ☑ SIGNED |
| 评测方法负责人 | 朱莹 | 2026/11/05 | ☑ SIGNED |
| 独立 QA / 标注协调人 | 朱鸿林 | 2026/11/05 | ☑ SIGNED |

签署即冻结：任务配额、抽样/加权、门槛、区间方法、切片最低 n、claim 范围。变更须新 protocol 版本。

---

## 2. 范围与 freeze

| 项 | 预注册值 |
|---|---|
| Benchmark 名称/版本 | `eval.g2b.benchmark.v1`（n=100 expand；含已完成的 01–30） |
| 目标 n | **100** 条二分类任务（双人独立盲标） |
| 已完成 | **n=100** 双标+仲裁+κ+accuracy closeout（2026-11-05）：pass_rate=**0.72**（72/100），Wilson 95% CI=[0.6251,0.7986]，κ=0.7624；另保留 n=30 中间态记录 |
| 门槛对照 §4 | pass_rate **未达**（0.72&lt;0.80）· CI 下界 **未达**（0.6251&lt;0.70）· κ **达标** → **仅 scoped 披露，不得 accuracy_claim** |
| Model/prompt freeze owner | **朱向群**（已确认） |
| Freeze 时间戳 | **CONFIRMED** 20261105T151547Z — [`evidence/g2b_freeze_record.v1.json`](../evidence/g2b_freeze_record.v1.json)；变更 → 新版本 |
| 出卷包（工程） | `docs/a3/human_pack/20261105T132500Z-n100/`（双标已回填；model_outputs 复用 `20261104T064000Z-n100`） |
| 确认性数据用途 | 不得反馈调参；泄漏即标记为开发运行 |

### Holdout 方案（已勾选）

- [x] **方案 A（推荐）**：n=100 全部为确认性 benchmark；可选 20 条封存哨兵，但团队可见结果则不得称未见测试。门槛按 n=100。
- [ ] **方案 B**：80 开发 + 20 holdout；门槛/CI 按 **n=20** 预注册；禁止合并后称未见测试。

---

## 3. 分层配额（边际；允许交叉）

| 分层 | 数量 | 示例范围 |
|---|---:|---|
| Prompt | 15 | 指令遵循、格式、拒答 |
| KB/RAG | 20 | 检索、来源支持、引用 |
| Code Review | 15 | finding 匹配、P0 覆盖 |
| Agent/Skill | 15 | 任务完成、触发/工具行为（fixture 边界内） |
| Session | 15 | 2–8 轮、目标保持 |
| Safety/Refusal | 20 | 注入、越权、拒答 |
| **合计** | **100** | |

| 交叉约束 | 目标 |
|---|---|
| 难度 easy/medium/hard | 30 / 50 / 20 |
| 来源 | ≥50 真实任务 / ≥30 curated regression / ≤20 adversarial-edge |
| 语言 | 中文约 70% / 英文约 30% |

须保存对象×难度×来源×语言交叉表，避免单一切片由单一来源驱动。

---

## 4. 候选门槛（签署前可调整；签署后冻结）

| 条件 | 候选门槛 |
|---|---|
| 样本/标注 | n=100；两名不同真人独立盲标；分歧按预定 rubric 仲裁 |
| 总体加权 pass rate | ≥80% |
| Wilson 95% CI 下界 | ≥70%（描述性；相关样本时不得单独作严格总体推断） |
| 工程/数据质量 κ | ≥0.60；报告 agreement、标签分布、仲裁率 |
| 标注可靠性门（scoped 报告） | κ≥0.70；或 κ≥0.65 且满足争议上限/盲标/抽查 |
| Safety 切片 | 目标 n=20；n&lt;20 或方法负责人降为 n=10 → **report-only** |
| Code Review P0 | 低于预注册最小 n → report-only |
| 数据完整性 | 无缺项；无同人双填；无 gold 泄漏；freeze 可追溯 |

未同时满足：可发布 scoped observed pass rate + CI，**不得** accuracy claim。
κ ≠ 准确率；总体 pass rate ≠ 线上任务分布估计。

---

## 5. 统计与切片

- 总体 pass rate：按本 protocol 冻结的对象边际配额**加权**；同时披露各对象原始 n、通过数、未加权结果。
- Wilson 95%：常规二项描述区间；任务族相关时优先预注册 cluster bootstrap（样本不足则只描述、不作确认性 claim）。
- 多切片默认不作显著性宣称；若检验须预注册多重比较控制。
- 任一切片不得借用总体 CI/门槛宣称该切片通过。

---

## 6. Claim 模板（预写入）

> 在 **[benchmark 名称/版本]**、**[模型及版本/标识]**、**[prompt/config 版本]** 和 **[任务范围]** 上，n=[ ]，按预注册配额加权 pass rate 为 [ ]；[区间类型/方法] 95% CI 为 [ ]；双标一致性 κ=[ ]，仲裁率=[ ]。该结果仅描述此 benchmark 与配置，不能推出通用准确率、其他任务分布表现或安全认证。

---

## 7. 工时与执行顺序

| 阶段 | 说明 |
|---|---|
| 签署本 protocol | 三方完成 §1 + 勾选 holdout |
| Freeze | model/prompt/config hash 入档 |
| 双标 31–100 | 预算约 25–30 人时（含培训/仲裁/抽查） |
| 仲裁 + κ + accuracy aggregate | 复用 `g2b_kappa.py` / `g2b_accuracy_closeout.py` |
| 范围审查 | 三方审查后决定是否仅 scoped 披露；默认不翻 `accuracy_claim` |

参考命令见 [`G2B_N100.md`](./G2B_N100.md)。

---

## 8. 明确不宣称

≠ 通用准确率 · ≠ 安全认证 · ≠ FDE 签收 · ≠ `process_split_authorized` · ≠ staging 生产授权
