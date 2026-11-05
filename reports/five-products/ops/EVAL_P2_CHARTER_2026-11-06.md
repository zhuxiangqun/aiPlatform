# EVAL P2 Charter（2026-11-06）

> **状态**：✅ P2-0 human calibration **已收口**（n=60 · disagree_rate=0.2667 · claim=false）· [closeout](./EVAL_P2_CALIBRATION_CLOSEOUT_2026-11-06.md)  

> **Unfreeze**：[ENGINEERING_UNFREEZE_EVAL_P2.md](./ENGINEERING_UNFREEZE_EVAL_P2.md)  
> **计划**：[EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md](./EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md) §5

## 1. 目标

在不阻塞已关闭的 P0/P1b 前提下，为评测侧研究/治理能力建立可排期的 P2 轨道：每项有 owner、风险、数据要求与预算，禁止「补几个 fixture」冒充研究闭环。

## 2. Owner 候选（可改）

| 角色 | 候选人 | 职责 |
|---|---|---|
| Evaluation 产品负责人 | 朱向群 | 范围、风险接受、claim 文案 |
| 评测方法负责人 | 朱莹 | 协议、抽样、校准设计 |
| 独立 QA | 朱鸿林 | 抽查、数据完整性 |
| 工程执行 | agent / 平台工程 | 本地工具与证据链 |

## 3. 首切片建议：**P2-0 Evaluator calibration**

**为什么先做**：计划写明校准是自学习可信度的前置；且**不依赖公网**，可在本地用已有 G2b/Arena/preference 证据抽样。

### 3.1 范围（v0）

| 项 | 定义 |
|---|---|
| 对象 | 现有 judge/runner 输出（优先：G2b model pass vs gold、Arena length smoke vs blind、preference） |
| 动作 | 人工抽样复核：误报 / 漏报 / 明显漂移 |
| 产出 | `eval.calibration.v0` 聚合 + 方法说明；**不**自动改 composite 权重 |
| n（候选） | 每对象 ≥20 条抽查或全量若更小；预注册后再动 |

### 3.2 非目标

≠ 翻 `accuracy_claim` · ≠ 替换 Arena length smoke 默认 · ≠ 上线自学习写回 · ≠ 生产拆分

### 3.3 粗估（待确认）

| 项 | 粗估 |
|---|---|
| 方法协议 + 抽查表 | 0.5–1 人日 |
| 人工抽查（三对象） | 1–2 人日 |
| 工程聚合脚本 / 证据 | 0.5–1 人日 |
| **合计** | **约 2–4 人日** |

### 3.4 风险

| 风险 | 缓解 |
|---|---|
| 抽查与原标注者同一人 | QA/方法交叉；禁止自检自己的标签轨 |
| 把校准当 accuracy | 协议写死 claim=false |
| 范围膨胀到记忆/自学习 | 本切片出口不含写回 |

## 4. 后续切片（未开工）

| ID | 主题 | 前置 |
|---|---|---|
| P2-1 | 上下文管理基准 | P2-0 协议可复用抽样方法 |
| P2-2 | 持久记忆 Recall@k | 租户夹具；P2-0 |
| P2-3 | 自学习抗性 | **P2-0 完成** |
| P2-4 | 生产治理 | **正式环境 / 门 C**（当前无公网 → 搁置） |

## 5. 确认清单（产品负责人）

- [x] 同意本 charter 与 unfreeze 开篇（2026-11-06 继续推进）
- [x] 同意首切片 = P2-0 Evaluator calibration
- [x] owner 表按候选执行（可后改）
- [x] 粗估 2–4 人日可接受（默认）

工程已开：[`ENGINEERING_UNFREEZE_EVAL_P2_CALIBRATION.md`](./ENGINEERING_UNFREEZE_EVAL_P2_CALIBRATION.md) · 协议 [`CALIBRATION_V0.md`](../../../packages/aiplat-evaluation/docs/a3/CALIBRATION_V0.md)
