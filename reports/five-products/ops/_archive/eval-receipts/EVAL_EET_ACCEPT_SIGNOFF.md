# EET 证据标签映射 — 治理 Accept 签认

> **门**：P1a EET 治理批准 — **不阻塞** UI 发布；阻塞「把 EET 写入正式发布 gate 矩阵」
> **母版映射**：EVAL_EVIDENCE_LEVEL_MAP_V1.md（历史链接失效）
> **依据**：[改善执行计划](../../EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md) §6
> **硬锁**：Accept ≠ 新建与落地 E0–E5 并行的正式成熟度等级；≠ 自动打开 `accuracy_claim`

---

## 0. 元数据

| 项 | 填写 |
|---|---|
| 映射版本 | `EVAL_EVIDENCE_LEVEL_MAP_V1` |
| 评审日期 |  |
| 评测方法负责人 |  |
| 项目治理 owner |  |
| 结论 | ☐ **Accept** · ☐ **Reject（退回修订）** · ☐ **Defer（保持 Proposed）** |

---

## 1. 必读与消歧（勾选即已读）

| # | 检查 | 结果 |
|---|---|---|
| 1.1 | 已读映射 §1：落地 E0–E5 / EVAL_V1 E* / EET-1..4 **三套勿混** | ☐ |
| 1.2 | 已读 §2：EET-1 smoke 不可单独进本地 engineering gate；EET 全员不可开通用 accuracy | ☐ |
| 1.3 | 已读 §3–4：EET 只标证据类型，**不**替代落地 E4/E5 或 EVAL 里程碑 | ☐ |
| 1.4 | 确认 Accept 后仍禁止：用 EET 宣称生产就绪 / 用 EVAL E5 冒充落地 E5 | ☐ |

---

## 2. 工程接线抽查（Accept 前建议核）

| # | 检查 | 方法 | 结果 | 证据 |
|---|---|---|---|---|
| 2.1 | `infer_evidence_level` 可导入 | `python3 -c` 从 `packages/aiplat-evaluation` | ☐ |  |
| 2.2 | 报告 meta 可带 `evidence_level` | 评测中心 → Reports 详情可见字段 | ☐ | 截图/路径 |
| 2.3 | UI 未把 EET 当成发布成熟度徽章 | 详情无「E4/E5 生产」类误标 | ☐ |  |

命令示例：

```bash
cd <repo>
python3 -c "
import sys; sys.path.insert(0,'packages/aiplat-evaluation')
from app.scoring.report_stamp import infer_evidence_level
assert infer_evidence_level(meta={'evidence_level':'EET-1'}) == 'smoke'
assert infer_evidence_level(meta={'evidence_level':'gold'}) == 'gold'
print('ok')
"
```

---

## 3. Accept 后允许 / 仍禁止

| Accept 后允许 | 仍禁止 |
|---|---|
| 在本地/文档门禁矩阵中引用 EET-1..4 作**证据类型约束**（如「禁止仅 EET-1」） | 把 EET 当作第二套正式部署成熟度等级对外宣传 |
| 继续使用已接线的 `metrics.meta.evidence_level` | 仅凭 EET-3/4 打开 `accuracy_claim=true` 或 `process_split_authorized` |
| 对象卡 / G2b / Arena 文案统一用 smoke/fixture/gold/human | 用 Accept 替代 A1 部署签认或 G2B protocol 签署 |

---

## 4. 签认栏

| 角色 | 姓名 | 日期 | 决定 |
|---|---|---|---|
| 评测方法负责人 |  |  | Accept / Reject / Defer |
| 项目治理 owner |  |  | Accept / Reject / Defer |

### 结论摘录

```
映射：EVAL_EVIDENCE_LEVEL_MAP_V1
EET 结论：Accept | Reject | Defer
日期：
备注：Accept 后更新映射文首状态 Proposed→Accepted；handoff 勾掉本项
```

---

完成后：副本落到 `reports/five-products/ops/EVAL_EET_ACCEPT_<date>.md`，并把 `EVAL_EVIDENCE_LEVEL_MAP_V1.md`（历史链接失效） 文首改为 **Accepted**（含签字日期）。
