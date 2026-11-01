# EVAL_V1 Charter — 评测准确性、唯一入口与评测中心

> **文档类型**：Product / Design Charter  
> **状态**：**Accepted · E0–E5 done**（v0 未锁；local gate≠accuracy/G2a）· 2026-11-01  
> **范围**：Evaluation 产品 v1（本地工程 + 产品设计）；不含 A3 进程拆分、生产 staging/authorize/SLA  
> **解冻**：[`ENGINEERING_UNFREEZE_EVAL_V1.md`](../../../reports/five-products/ops/ENGINEERING_UNFREEZE_EVAL_V1.md)  
> **上游计划**：[`five-capability-independent-engineering-plan.md`](./five-capability-independent-engineering-plan.md) V2.2  
> **现状**：[`STATUS.md`](../../../reports/five-products/STATUS.md) · [`MODULE.md`](../../../reports/five-products/modules/evaluation/MODULE.md)  
> **本文件不是**：实施记录；不代表 `process_split` / `staging_ready` / `production_signed` 解冻。

---

## 0. 一句话

**先把评测做准，再把入口收成一个，最后才做评测中心和独立服务。**

```
准确性 → 唯一 API → 评测中心 UI → A3 独立服务 → 生产/SLA
  E0–E5      E1          E6            后置         后置
```

---

## 1. 当前状态

| 维度 | 现状 | 影响 |
|---|---|---|
| 运行 | Evaluation **A2 / D1c / cohost**；`service_module: null` | 不是独立服务；A3 仍 false |
| API | `apps/eval` 6 个 router + core `/evaluation`、`/kb-eval`、`/prompts/eval` 并行 | 入口不唯一，金标易接错路径 |
| UI | `/diagnostics/eval`（Agent 评估）、Knowledge 检索评估、Prompts eval、Governance code-review-gold | 无统一评测中心 |
| 准确性 | `eval.protocol.v0` 是交换格式 | 无 gold set / 标签 / judge 校准 / 方差 |
| 门禁 | 无 eval gate | 回归拦不住 |
| 独立 | `process_split_authorized=false` | A3 未启动 |
| 冻结 | 本地五产品工程轨已冻结 | 需要显式解冻 EVAL_V1 |

**结论**：评测有“协议”，但还没有“准确度”；有“页面”，但没有“评测中心”。

---

## 2. 锁定决策

| # | 决策 | 内容 |
|---|---|---|
| D1 | 解冻范围 | 只解冻 **E0–E5**（唯一 API + 准确性 + gate）；UI 等 **G2a** 后 preview 另批；A3/生产继续冻 |
| D2 | 首场景 | 主：**发布/PR 回归门禁**；副：**A/B Agent 版本比较** |
| D3 | 首版对象 | **Agent + Skill**；`code-review-gold` 作为首个种子切片 |
| D4 | 标注 | v0 **30 条**；**单人复核（D5）**；你 + AI 预标注；不宣称 inter-annotator κ |
| D5 | 单人复核 | **接受**：v0 由你一人复核；AI 只做预标注；**不报 κ**；不把它当 accuracy claim |
| D6 | 唯一入口 | canonical：`/api/platform/apps/eval`；core 旧路径只保留 shim |
| D7 | 阈值 | v0 宽、v1 严（§7）；未达标不宣称“更准” |
| D8 | UI | **G2a 后**可做 `/eval` local preview；**G2b 后**才宣称 accuracy / 外部 gate |
| D9 | A3 | 后置：需 ADR + staging；v1 仍是 D1c cohost |
| D10 | E3 启动 | **≥15 条可跑 + 来源清单**即可启动；满 30 锁 v0；<30 不挡 E1，只挡 G2/gate 宣称 |
| D11 | 仲裁节奏 | 每周 **三 19:00–21:00**；E3 按此节奏标注 |

---

## 3. 目标与非目标

### 3.1 目标

1. **一个 API**：所有评测调用走 `/api/platform/apps/eval`。
2. **一个页面**：`/eval` 评测中心，旧页面 redirect。
3. **可证明的准确**：与人工一致、可复现、能挡回归。
4. **可归因**：结果能回答“升模型 / 改路由 / 修 SOP / 修数据”。
5. **可行动**：失败有分类、证据、trace、修复建议。
6. **可产品化**：API/数据/UI 稳定，A3 只差 ADR/staging。

### 3.2 非目标

- 不做“所有程序”评测；
- 不做多租户/计费/SLA；
- 不做 A3 进程拆分/生产 authorize；
- 不用评测替代 FDE 客户验收；
- 不在没有人工标签时宣称“准确”；
- 不先做 UI/独立服务。

---

## 4. “准确”的定义（5 个执行支柱）

### 4.1 可测
- 与人工一致：Cohen's κ（**v0 单人复核不计算**；v1 有第二标注者才算）；
- 判定质量：precision/recall/F1；
- 排序质量：A/B 一致率；
- 稳定性：k=3 方差；
- 校准：ECE；
- 分片报告（领域/难度/失败类型），不只报平均。

### 4.2 可归因
单一总分不能回答“该改什么”。报告必须包含：
- 维度分：任务完成 / 工具 / 轨迹 / 文本 / 成本 / 安全；
- 对照：换模型、换路由、改 SOP、改数据各跑一次；
- 失败分类 + trace + 证据；
- 结论必须能落到一个产品动作。

### 4.3 唯一入口
- canonical `/api/platform/apps/eval`；
- 旧 core 路径加 shim + deprecation header；
- 所有 UI/外部调用只出现一个前缀；
- 契约测试覆盖每个资源。

### 4.4 Gate 统计与成本
- k=3 + 置信区间，不用单次分数做门禁；
- 注入已知回归，测检出率；控制误拦率；
- PR 快检子集（<5 分钟） vs nightly 全量（<30 分钟）；
- 记录模型调用/标注成本，设预算上限。

### 4.5 闭环与所有权
- 谁看报告、谁决定拒发/回退；
- 失败分类 → 修复 → 复评；
- 门禁失败后的处理时限；
- 评测报告必须进入发布/回退决策，不能只展示。

---

## 5. 目标架构

```
Eval Center UI (/eval)
   ↓ 只调唯一 API
Platform Eval API (/api/platform/apps/eval)
   ↓
Eval Engine
   ├─ Gold Set / Tasks / Rubrics
   ├─ Runner / Trace
   ├─ Judgment（deterministic + LLM judge + human）
   ├─ Metrics / Statistics
   ├─ Reports / Failure Taxonomy
   └─ Gate（PR / nightly / release）
   ↓
Eval Store（tasks/runs/judgments/reports/labels/judge_versions）
```

### 5.1 代码归属

| 层 | 位置 |
|---|---|
| REST 端点 | `aiPlat-platform/apps/eval/api/` |
| 业务逻辑 | `aiPlat-core/core/apps/eval/service/` |
| 通用评分/执行 | `aiPlat-core/core/harness/evaluation/`（仅通用） |
| 契约/schema | `packages/aiplat-evaluation/contracts/` |
| UI | `aiPlat-management/frontend/src/pages/Eval/` |
| 注册 | `aiPlat-platform/registry/apps.yaml` |
| 门面 | 平台访问 core 走 `CoreFacade` |

### 5.2 唯一 API 资源

| 资源 | 说明 |
|---|---|
| `/eval-sets` | 评测集/版本/任务 |
| `/eval-runs` | 运行/轨迹/状态 |
| `/eval-judgments` | 判分/理由/证据 |
| `/eval-reports` | 汇总/分片/失败分类 |
| `/eval-compare` | A/B、版本对比、置信区间 |
| `/eval-gates` | 门禁结果/阈值 |
| `/eval-judges` | judge 配置/版本/校准 |
| `/eval-labels` | 人工标签/复核队列 |

### 5.3 数据模型

- `eval_sets(id, name, version, split, meta)`
- `eval_tasks(id, set_id, input, expected, rubric, tags, hard_negative)`
- `eval_runs(id, task_id, target_kind, target_ref, model, params, trace, status)`
- `eval_judgments(run_id, judge_id, score, pass, reason, evidence, confidence)`
- `eval_labels(task_id, annotator, label, rationale, adjudicated)`
- `eval_reports(id, run_ids, metrics, slices, failures)`
- `eval_judges(id, model, prompt_version, calibration)`
- `eval_gates(id, baseline, candidate, thresholds, decision)`

版本字段：dataset / judge / prompt / model / code commit，缺一不可。

---

## 6. 工作分解

| ID | 工作包 | 交付 | 工期 | 解冻 |
|---|---|---|---|---|
| E0 | Charter + 决策 + 指标 + 解冻 | 本文件 + unfreeze | 1 周 | ✅ |
| E1 | 入口盘点 + canonical API + shim | 唯一前缀 + 契约测试 | 2–3 周 | ✅ |
| E2 | 数据模型/store + 迁移 | schema + store | 1–2 周 | ✅ |
| E3 | Gold set：≥15 启动，30 锁 v0；单人复核 | 数据 + 标签 + 来源清单（无 IAA/κ） | 2 周（并行） | ✅ |
| E4 | Judge v1 + 校准 + 偏差 + k=3 | 校准报告 | 2 周 | ✅ |
| E5 | 指标/报告/失败分类 + gate | eval gate | 1–2 周 | ✅ |
| **G2a** | Engineering calibration（30 条，单人复核；**不宣称 accuracy**） | 可接 local gate / UI preview | W8 | — |
| **G2b** | Accuracy claim（100 条 + 第二标注者 + κ） | 才能宣称 accuracy / 外部 gate | 后置 | — |
| E6 | 评测中心 UI v1 | `/eval` + redirect（preview） | 3–4 周 | 需 G2a 后解冻 |
| E7 | D2/D3 本地收口 | 文档/安全/性能 | 1–2 周 | 需 G2a 后解冻 |
| E8 | A3 独立服务 | 进程/DB/部署 | staging 后 | ❌ |

**到 G2a：约 8–10 周；加 UI preview：12–14 周；G2b/A3 另计。**

---

## 7. 指标与验收

| 指标 | v0（30 条，单人复核） | v1（100 条，有第二标注者） |
|---|---|---|
| 与人工一致 κ | **N/A（不宣称）** | ≥ 0.6（置信下界） |
| judge-human 一致率 | 记录（同人复核，不作 accuracy） | 用 κ 替代 |
| pass/fail F1 | ≥ 0.75（仅 calibration） | ≥ 0.8 |
| A/B 排序一致率 | ≥ 75% | ≥ 80% |
| k=3 标准差 | ≤ 8% | ≤ 5% |
| 校准 ECE | 记录 | ≤ 0.1 |
| 注入回归检出 | ≥ 70% | ≥ 80% |
| 误拦率 | ≤ 15% | ≤ 10% |
| PR 快检 | < 5 分钟 | < 5 分钟 |
| 全量 nightly | < 30 分钟 | < 30 分钟 |

**诚实边界**：v0 是 **engineering calibration**，不是 accuracy proof；没有第二标注者就不宣称 κ/准确率。

**Gate 规则**
- G0：charter + unfreeze 批准。
- G1：唯一 API；旧路径 shim；契约测试绿。
- **G2a**：30 条 + 单人复核 + 确定性检查 + seeded regression；可接 local gate/UI preview，**不宣称 accuracy**。
- **G2b**：100 条 + 第二标注者 + κ 达标；才可宣称 accuracy / 外部 gate。
- G3：`/eval` 一个入口；旧页面 redirect；无重复。
- G4：D3 本地 UAT/文档/性能。
- G5：A3 需 staging + ADR。

---

## 8. UI 设计（G2a 后 preview；G2b 后才宣称 accuracy）

### 8.1 信息架构

| Tab | 内容 |
|---|---|
| 总览 | 评测集/运行/通过率/趋势/成本 |
| 评测集 | gold set、任务、rubric、标签 |
| 运行 | 任务执行、trace、状态 |
| 判分 | judge 结果、人工复核队列 |
| 报告 | 分片、失败分类、证据链接 |
| 对比 | A/B、版本、置信区间 |
| 门禁 | PR/nightly/release 结果 |
| 设置 | judge 版本、阈值、权限 |

### 8.2 旧页面迁移

- `/diagnostics/eval` → `/eval?tab=agents`
- KB `?tab=eval` → `/eval?tab=knowledge`
- Prompt eval → `/eval?tab=prompts`
- Governance gold → `/eval?tab=code-review`

### 8.3 权限

- admin/developer/operator/fde：按现有 RBAC
- 只读用户：报告/趋势
- 标注者：label queue only

---

## 9. 人工标注

| 项 | 决定 |
|---|---|
| v0 | 30 条；**≥15 条可跑 + 来源清单**即启动；满 30 锁 v0 |
| v1 | 100 条（有第二标注者时） |
| 标注者 | **1 人（你）+ AI 预标注**（D5）；第二标注者仅在 v1 需要 |
| 仲裁 | 你；**每周三 19:00–21:00** |
| AI | 只做预标注/整理，不做 ground truth |
| κ | v0 **不计算**；v1 有第二标注者才计算 |
| 来源 | code-review-gold **8–12 条**；Slice E2E / Gate3 样例；常用 Agent/Skill 脱敏记录；你手写 **10–15 条失败过的真实任务**（工具错/路由错/SOP 漏） |
| 投入 | 30 条 × 20 分钟 ≈ 10 小时；按周三 2 小时节奏 |

---

## 10. 角色

| 角色 | 职责 |
|---|---|
| 你 | 决策、标注/复核、仲裁、验收；提供真实任务来源 |
| 我 | API/数据/引擎/UI/gate/文档 |
| 第二标注者（可选，v1） | 100 条独立标注；用于 κ |
| 外部专家 | 按需 |

成本：模型调用 + 标注人力；无服务器采购。

---

## 11. 风险与止损

| 风险 | 止损 |
|---|---|
| 无 ground truth | 先 30 条人工标签；≥15 可启动；<30 不挡 E1 |
| 单人复核偏差 | **D5 accepted**：v0 不报 κ、不宣称 accuracy；G2b 再补第二人 |
| judge 偏差 | 双 judge/规则优先；有第二人时 κ<0.4 停止 |
| 评测过拟合 | holdout + 定期换题 |
| 入口迁移破坏旧 UI | shim + 逐页迁移 + 契约测试 |
| UI 先于准确 | G2a 只做 preview；G2b 才宣称 accuracy |
| 成本过高 | 快检子集 + 缓存 + 低成本 judge |
| 范围蔓延 | 首版只评 Agent/Skill |
| A3 过早 | 等 staging + ADR |

**停止条件**
- 30 条未满 → 不锁 v0、不做 G2/gate 宣称；E1 可继续。
- 单人复核 → 不宣称 κ/accuracy；只报 calibration。
- 有第二人且 κ < 0.4 → 停 judge，改规则/人工。
- Gate 误拦 > 20% → 停 gate，先修数据/阈值。
- 预算超限 → 缩小 gold set，不降标准。

---

## 12. 今后需要做的事（v1 之后）

1. Gold set 100→300+，领域/难度/失败模式覆盖。
2. 扩 target：HTTP/CLI/外部程序（先协议+沙箱）。
3. 多 judge/ensemble（单 judge 校准达标后）。
4. 在线评测：生产 trace 采样、漂移/回归预警。
5. 人机协同：主动学习、标注队列、仲裁。
6. A3 独立服务：进程/DB/部署/回滚。
7. 多租户/配额/审计/SLA（商业启动后）。
8. 领域评测包/模板（可选）。

---

## 13. E0 出口条件

- [x] 决策锁定（D1–D11）。
- [x] 5 个执行支柱写清（§4）。
- [x] 解冻文档创建（E0–E5）。
- [x] 指标/阈值 v0/v1 定义。
- [x] D5 accepted：v0 单人复核；不报 κ。
- [x] 任务来源计划：≥15 启动，30 锁 v0；来源清单。
- [x] 仲裁节奏：每周三 19:00–21:00。

**E0 完成 → E1 ready**（唯一 API/入口盘点可开工）。  
E0 只产出文档，不改业务代码；E1 起才动 API/代码。

---

## 14. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-01 | v1.0 | 初版：准确性 + 唯一入口 + UI + A3 后置；4 项决策 + 5 个执行支柱 |
