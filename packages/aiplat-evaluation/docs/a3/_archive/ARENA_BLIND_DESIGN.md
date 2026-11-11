---
doc_type: Archive
---

# Arena 盲评设计（P1a · 设计稿）

> **状态**：设计完成 ≠ 新评分上线
> **日期**：2026-11-05
> **依据**：[改善执行计划](../../../../../reports/five-products/ops/EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md) P1a/P1b
> **现状 runner**：`arena` = `length_heuristic` · `evidence_level=smoke` · **不可进质量 gate**
> **Rubric 冻结**：[ARENA_BLIND_RUBRIC_V1](../ARENA_BLIND_RUBRIC_V1.md) · **Pilot 脚手架**：[ARENA_BLIND_PILOT](./ARENA_BLIND_PILOT.md)

## 1. 问题

当前 `run_arena` 用回答长度选 winner。该分只可作 smoke，不得展示为正式质量胜负或用户偏好。

## 2. 目标判分（上线后方可替换门禁）

| 项 | 预注册 |
|---|---|
| 标签 | A / B / Tie（强制三选一；禁止「差不多」自由文本当标签） |
| 盲评 | 评审不可见模型名、长度、长度 winner；两侧随机左右 |
| 评审人数 | ≥2 独立盲评 / 对 |
| Pilot 规模 | 最小 30 对，目标 30–50 对 |
| Rubric | 任务完成、正确性/ grounded 线索、有害/拒答、指令遵循（冻结后再跑） |
| 一致性 | 报告 agreement + κ（A/B/Tie 三类）；分歧仲裁 |
| 版本 | 新 judge version（如 `arena.blind.v1`）；历史长度 winner 保留为 smoke |

## 3. Pilot 完成定义

- Rubric 冻结文档存在且评审培训完成
- ≥30 对、每对 ≥2 盲评
- 结果单独 schema/version；不回写覆盖历史长度 winner
- 独立 QA 抽查盲评流程记录
- 若无法落实两人/最小样本：本轮只交设计/阻塞记录，Arena 继续 smoke

## 4. 工时粗算

按每人每对 ~3 分钟：30–50 对 × 2 人 ≈ 3–5 人时纯评审，另加培训/仲裁/整理。

## 5. 非目标

≠ accuracy claim · ≠ Preference/G2b 替代 · ≠ 上线即替换 composite 质量门（须影子运行 + 差异分析）
