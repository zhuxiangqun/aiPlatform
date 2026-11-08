# ADR: Eval 能力驱动 Case Pack 与 Suite Profile

- **状态**：Proposed（设计评审用，不实施；v0.2 吸收路径/能力 ID/可测子集修订）
- **日期**：2026-11-08
- **决策范围**：Evaluation 题库、选题、执行与证据组织
- **关联**：
  - [`eval-capability-driven-case-pack.md`](../plans/eval-capability-driven-case-pack.md) v0.2
  - [`eval-case-pack-factory.md`](../plans/eval-case-pack-factory.md)
  - [`eval-object-contract-and-plan.md`](../plans/eval-object-contract-and-plan.md)
  - [`eval-trust-boundary-lab-vs-cert.md`](../plans/eval-trust-boundary-lab-vs-cert.md)
  - [`workspace-isolation-contract.md`](../plans/workspace-isolation-contract.md)

---

## 1. 背景

当前 Evaluation 的 Plan 主要按“卷”选题：

- Agent 默认 6 卷；
- 每卷 1–3 题；
- 全开约 10 题；
- 卷级适用性为主；
- 题库是固定 `eval_sets/*.json`；
- 题目没有统一的“测试目的”字段；
- 扩题只能手改 JSON，容易污染基准。

现有 Case Pack 工厂（P0–P3.1）已经提供：

- registry / hash / expand / bump / holdout；
- mutation / trace；
- LLM 候选；
- difficulty / judge 工单；
- 权威存储：`$AIPLAT_HOME/eval_packs/{global|workspaces|tenants}/…`（**不是** `core/engine/eval_packs/`）。

但没有形成：

- 能力矩阵（canonical_id）与 legacy alias；
- 测试目的卡；
- Profile 组卷；
- 覆盖闭环；
- 题级 manifest 的产品路径（Profile 选档）。

---

## 2. 决策

### 决策 1：以能力为主键组织题库

采用 **Capability Registry**：

- 每个对象类型定义能力；
- 每个 case 至少绑定一个 **canonical** 能力 ID；
- 每个能力有定义、可观测信号、oracle、环境、最低样本量；
- 没有 case / 无环境的能力标 `unknown`，不是 pass。

**理由**：题数不等于覆盖；能力矩阵才能回答“漏了什么”。

### 决策 1b：冻结 legacy ↔ canonical 对照表（阻塞 P0）

现有 `applicability_draft.json` 使用 `clarify_or_ask` 等 legacy ID；新矩阵必须含 `clarification`（A13），并维护对照表。  
canonical 为覆盖报表唯一主键；legacy 仅 alias；迁移期双写/映射。  
**详见 Plan §4.2.1。**

### 决策 2：一个 Case Bank，多套 Suite Profile

不建立四套互不相关的题库，而是：

```text
Case Bank
  ├─ smoke
  ├─ regression
  └─ benchmark
```

Profile 只决定：

- 选哪些能力（须落在 v1 可测子集或显式标 unknown）；
- 每能力几题；
- 采样策略；
- seed；
- 是否 holdout。

**理由**：避免重复维护、题目漂移和四套基准不一致。

### 决策 3：`test_purpose` 必填，且与 prompt 分离

每个 case 必须有：

- `summary`
- `why_this_case`
- `expected_behavior`
- `failure_signals`
- `not_testing`
- `oracle_rationale`

并遵循三视图：

| 视图 | 可见 |
|---|---|
| 模型 | 只看 `prompt` + 允许的工具/上下文 |
| 审核人 | 看 purpose + prompt + rubric + expected/failure |
| 报告 | 看 purpose + 结果 + failure + `not_testing` |

**理由**：人审需要知道“测什么、什么算失败、不测什么”；模型不能看到目的，否则会猜题。

### 决策 4：生成只产候选，人审后才能冻结

生成器包括：

- 模板参数化；
- 变异；
- trace 挖掘；
- LLM 候选。

所有候选必须经过：

```text
validate → dedupe → oracle check → human review → freeze
```

**LLM 不得直接当 gold；不得与 judge 同模；不得直接进 claim。**  
**实施时复用 Case Pack 工厂 P2–P3.1，不另造工厂。**

### 决策 5：`sample_manifest` 是唯一执行依据

- Runner 只执行 `sample_manifest`；
- `selected_cases` 只是兼容投影；
- manifest 为空/hash 不匹配/版本不存在 → fail closed；
- 禁止回退“整包全跑”。

**理由**：选题与执行必须可审计；不能“Plan 选 A，Runner 跑 B”。

### 决策 6：Profile 选档不自动打开 claim

- `smoke` / `regression` / `benchmark` 只决定跑法；
- `claim_eligible` 由 pack 状态和独立协议决定；
- `generated` 恒 `claim_eligible=false`；
- `frozen + human_reviewed` 也只是 claim 候选，不是自动认证。

**理由**：题多/档高不等于准确率或安全认证。

### 决策 7：权威存储路径与工厂一致（硬约束）

Case Pack / Capability Bank 运行时权威路径：

```text
$AIPLAT_HOME/eval_packs/global
$AIPLAT_HOME/workspaces/{workspace_id}/eval_packs
$AIPLAT_HOME/tenants/{tenant_id}/eval_packs
```

**拒绝** `core/engine/eval_packs/` 作为权威存储（双源风险）。  
仓库 `core/engine/eval_sets/*.json` 仅作旧卷种子/映射源。

### 决策 8：v1 声明范围为「文本可观测能力子集」

本阶段不接 live tools / microVM。  
A3–A5（工具选择/参数/结果使用）默认不可宣称 `covered`，无环境时标 `unknown`。  
A6 仅允许「失败措辞/定位」级证据，不得宣称真实工具恢复已测。  
**详见 Plan §4.2.2。**

---

## 3. 后果

### 正面

- 能力覆盖可度量；
- 题目可人审、可解释；
- 题库可扩展但不污染基准；
- 运行可复现（manifest + hash + seed）；
- Smoke/Regression/Benchmark 可共用题库；
- 与现有 Case Pack 工厂兼容，不需要重写。

### 负面 / 成本

- 需要新增能力矩阵、`test_purpose`、legacy alias；
- 需要人审队列和冻结流程（内容工作量大）；
- 需要 Profile/Plan/UI 接线；
- 需要 judge 校准，否则扩题仍不可信；
- 工具/记忆能力在 v1 大量为 `unknown`，报告须诚实披露。

### 兼容性

- 旧 `set_id` 保留映射；
- 旧 `EvalTask` 字段保留；
- 旧 API 在迁移期保留只读投影；
- v1 Plan 不塞入 manifest 语义；新路径用 v2；
- legacy capability 字符串经对照表映射，不断匹配。

---

## 4. 备选方案

| 方案 | 结论 | 原因 |
|---|---|---|
| 保持固定 6 卷，只加题 | 拒绝 | 无能力覆盖、无目的、无 Profile |
| 运行时随机出题 | 拒绝 | 不可复现、不可审计、易污染 |
| 每个档复制一套题库 | 拒绝 | 维护重复、题目漂移 |
| LLM 出题直接当 gold | 拒绝 | 自证循环、偏差、泄漏 |
| 只做能力矩阵，不改执行 | 拒绝 | 无法证明实际跑了哪些题 |
| 在 `core/engine/eval_packs/` 新建权威库 | 拒绝 | 与工厂双源 |
| 无工具环境却标工具能力 covered | 拒绝 | 违反 unknown≠pass |
| 现有方案 | 采纳 | 能力 + 工厂复用 + Profile + manifest + claim gate |

---

## 5. 与现有系统的关系

| 系统 | 关系 |
|---|---|
| Case Pack 工厂 P0–P3.1 | **复用，不重写**；P3 只做覆盖驱动补题 |
| Plan v2 | 增量支持 `profile_id` / 能力配额 / `sample_manifest` |
| G2b-100 | 独立 L1，不被本方案吞并 |
| Arena / S1 / calibration | 独立轨，可选导入为 pack 镜像 |
| Workspace 隔离 | pack 必须声明 `scope`，跨 workspace 禁止 |
| Scorecard | 只读消费证据；不因本方案自动改分 |

---

## 6. 实施前置条件

### 6.1 阻塞 P0（必须先签/先冻结）

1. 能力矩阵 v1（含 A13 `clarification`）+ **legacy↔canonical 对照表**；
2. **v1 可测能力子集**（文本可观测；A3–A5 规则）；
3. `EvalCase.test_purpose` schema；
4. Suite Profile schema；
5. 权威存储路径确认（`$AIPLAT_HOME/eval_packs/...`）；
6. `scope` 默认值（建议：内置映射 `global` 只读；用户新 pack 默认 `workspace`）。

### 6.2 可后置到 P2/P4

1. Regression 配额固定 vs 风险加权；
2. Benchmark holdout 比例与统计方法批准方；
3. judge 校准一致率升级阈值；
4. `test_purpose` 是否允许按对象类型扩展字段（在统一必填集之上）。

本 ADR 通过后，仍需**单独变更单**实施；变更单须勾选 §6.1 已满足。

---

## 7. 开放问题（已分类）

### 阻塞 P0

1. `scope` 默认是 `global` 还是 `workspace`？（建议见 §6.1.6）
2. capability_id 对照表是否按 Plan §4.2.1 冻结？
3. v1 可测子集是否按 Plan §4.2.2 采纳？
4. `test_purpose` / Profile schema 字段是否锁定？

### 可后置 P2/P4

5. Regression 最低题数按能力固定，还是按风险加权？
6. Benchmark 的 holdout 比例与统计方法由谁批准？
7. judge 校准达到什么一致率才允许 report-only 升级？
8. 工具环境就绪后，A3–A5 如何从 `unknown` 升为 in-scope？

---

## 8. 建议实施顺序（内容 + Profile 优先）

| 阶段 | 内容 |
|---|---|
| P0 | 能力矩阵 + `test_purpose` schema + 旧卷映射 + alias |
| P1 | **30–50 题 Regression 内容 + 人审冻结** |
| P2 | **Profile 编译 + UI 选档 + manifest** |
| P3 | **复用现有工厂做覆盖驱动补题** |
| P4 | judge 校准 + holdout + benchmark |

**P1 的核心是题库内容，不是工厂代码。**

---

## 9. 结论

**采纳“能力驱动 Case Pack + Suite Profile + test_purpose + manifest”作为 Evaluation 题库扩展的设计基线。**

不采纳“固定卷无限加题”“运行时随机出题”“LLM 直接当 gold”“题数等于完整性”“双源存储”“无环境却宣称工具能力已测”。

**本 ADR 只做设计决策，不实施；实施需另开变更单，且 §6.1 阻塞项齐备。**
