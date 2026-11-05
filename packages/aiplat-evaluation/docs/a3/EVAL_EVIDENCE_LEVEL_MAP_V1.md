# Eval 证据标签映射（E0–E5 ↔ EET · P1a）

> **状态**：Proposed → 待项目治理 owner 批准  
> **日期**：2026-11-05  
> **依据**：[改善执行计划](../../../../reports/five-products/ops/EVALUATION_IMPROVEMENT_EXECUTION_PLAN_2026-11-04.md) §6 · 落地方案 §3.6  
> **原则**：不另建与 E0–E5 并行的正式 gate 等级；Eval 侧只用 **EET** 证据类型标签。

## 1. 三套「E」勿混用

| 符号 | 含义 | 权威 |
|---|---|---|
| **落地 E0–E5** | 能力路径证据成熟度：文档→源码→单测→集成→干净部署→生产 | [落地方案 §3.6](../../../../docs/architecture/plans/ai-platform-five-products-landing-plan.md)：「E0 文档 · E1 源码 · E2 单测 · E3 集成 · E4 干净部署 · E5 生产」 |
| **EVAL_V1 E0–E5** | 评测交付里程碑（charter/API/store/gold/judge/gate） | [`ENGINEERING_UNFREEZE_EVAL_V1.md`](../../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_V1.md) |
| **EET-1..4** | 单次评测结果的证据**类型**（非部署成熟度） | 本表 |

禁止：用 EET 替代落地 E* 宣称「已生产」；用 EVAL 里程碑 E5 冒充落地 E5。

## 2. EET 定义（Eval 唯一证据类型）

| 标签 | 含义 | 典型来源 | 可进本地 engineering gate？ | 可开 accuracy_claim？ |
|---|---|---|---|---|
| **EET-1 smoke** | 启发/探针（长度、可打印、fixture wrap） | `arena` length winner；`text_quality` | **否**（单独） | 否 |
| **EET-2 fixture** | 受控载荷、无真人金标 | `kb_rag` hits；`skill_suite` cases；`session_eval` 无 expected | 可（工程回归） | 否 |
| **EET-3 gold** | 预置期望/集合匹配 | `prompt_eval` exact；`code_review_gold`；gold-gated groundedness | 可（本地回归） | 否（仍须 G2b+attestation） |
| **EET-4 human** | 双人盲标/仲裁/偏好 | G2b labels；Preference；Arena 盲评（设计中） | 视 protocol | 仅 scoped + 产品签认 |

`evidence_level` 字段建议取值：`smoke` / `fixture` / `gold` / `human`（与 EET-1..4 一一对应）。

**写入（工程，Proposed 批准前可用）**：`ensure_report_meta` / `create_report` 经 `infer_evidence_level` 写入 `metrics.meta.evidence_level`（显式 meta 优先；`EET-1..4` 可映射；无依据不发明；`human` 仅显式信号）。≠ 发布 gate 新等级。

## 3. 与落地 E0–E5 的对照（非升降级）

| EET | 通常能支撑到的落地证据上限（粗） | 说明 |
|---|---|---|
| EET-1 | ≤ E1（源码存在启发逻辑） | 不能当 E2+ 行为证明 |
| EET-2 | ≤ E2（单测/本地 fixture） | 达不到端到端 E3 |
| EET-3 | ≤ E2–E3（有金标的集成回归） | 仍 ≠ 干净部署 E4 / 生产 E5 |
| EET-4 | 可支撑**限定 benchmark** 披露 | 不自动等于落地 E4/E5 或通用准确率 |

## 4. 与 EVAL_V1 里程碑

| EVAL 里程碑 | 主要消费的 EET |
|---|---|
| E1–E2 API/store | 无强制 EET |
| E3 gold bootstrap | EET-3（+ 单人复核 ≠ EET-4 双人） |
| E4 calibrate | EET-2/3 工程校准 |
| E5 local gate | EET-2/3；禁止仅 EET-1 |
| G2b | EET-4 |

## 5. 批准栏

| 角色 | 日期 | 决定 |
|---|---|---|
| 评测方法负责人 |  | Proposed |
| 项目治理 owner |  |  |

未批准前：实现与报告可使用 smoke/fixture/gold/human 文案；**不**把 EET 写入正式发布 gate 矩阵为新等级。

**工程接线（Proposed 期间可用）**：`ensure_report_meta` → `infer_evidence_level` 写入 `metrics.meta.evidence_level`；管理端详情展示该字段。仍须治理 Accept 后才可进发布门禁矩阵。
