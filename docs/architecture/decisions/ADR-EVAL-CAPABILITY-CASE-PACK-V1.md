# ADR: Eval 能力驱动 Case Pack 与 Suite Profile

- **状态**：Proposed（设计评审用，不实施；v0.2.4 区分 Subject×Capability×Method×Evidence；§6.1 待签字）
- **日期**：2026-11-08
- **决策范围**：Evaluation 题库、选题、执行与证据组织
- **关联**：
  - [`eval-capability-driven-case-pack.md`](../plans/eval-capability-driven-case-pack.md) v0.2.4
  - [`CAPABILITY_ID_MAP_V1.md`](../plans/CAPABILITY_ID_MAP_V1.md)
  - [`CASE_TEST_PURPOSE_SCHEMA_V1.md`](../plans/CASE_TEST_PURPOSE_SCHEMA_V1.md)
  - [`SUITE_PROFILE_SCHEMA_V1.md`](../plans/SUITE_PROFILE_SCHEMA_V1.md)
  - [`eval-case-pack-factory.md`](../plans/eval-case-pack-factory.md)
  - [`eval-object-contract-and-plan.md`](../plans/eval-object-contract-and-plan.md)
  - [`eval-trust-boundary-lab-vs-cert.md`](../plans/eval-trust-boundary-lab-vs-cert.md)
  - [`workspace-isolation-contract.md`](../plans/workspace-isolation-contract.md)
  - 权威 `OBJECT_TYPES`：`core/apps/eval/service/target_contract.py`（9 类）

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

### 决策 7：权威存储路径 + scope 按创建来源默认（硬约束）

#### 7.1 权威路径

Case Pack / Capability Bank 运行时权威路径：

```text
$AIPLAT_HOME/eval_packs/global
$AIPLAT_HOME/workspaces/{workspace_id}/eval_packs
$AIPLAT_HOME/tenants/{tenant_id}/eval_packs
```

**拒绝** `core/engine/eval_packs/` 作为权威存储（双源风险）。  
仓库 `core/engine/eval_sets/*.json` 仅作旧卷种子/映射源。

#### 7.2 Scope 默认：按创建来源，禁止「全局默认 global」

| 创建来源 | 默认 scope | 写权限 | 说明 |
|---|---|---|---|
| 内置 / 官方导入 | **`global`** | P0 只读；平台发布角色才能发新版本 | 跨工作区可见的官方基准 |
| 用户新建 pack | **`workspace`** | 同 workspace ACL | **默认**；防跨工作区泄漏 |
| 租户共享 pack | **`tenant`** | 同 tenant ACL | **必须显式开启**；P0 不默认 |

**不要设“全局默认 global”。** 用户随手建的 pack 若默认 global 会直接泄漏。

#### 7.3 配套规则（与默认值一并冻结）

1. **缺省 scope 不得静默推断**  
   - 内置导入 → `global`；  
   - 用户创建 → `workspace`；  
   - `tenant` → 必须显式传，且需 tenant admin；  
   - 调用方无法判定创建来源 → **400 `scope_required`**，禁止默认成 global。

2. **跨 scope 引用**  

   | 引用方 | 可引用 |
   |---|---|
   | workspace | 自己的 workspace + `global` 只读 |
   | tenant | 同 tenant + `global` 只读 |
   | global | **不得**引用用户 workspace/tenant pack |

   **禁止跨 workspace 引用。**

3. **修改 scope = 新 pack version**  
   - 禁止原地把 workspace pack 改成 global/tenant；  
   - 只能 clone + 新 version + 新 hash；  
   - 保留 provenance；  
   - 升入 global 需平台审核。

4. **frozen / deprecate**  
   - frozen 不可改，只能 deprecate；  
   - `global` 由平台 deprecate；workspace 由 owner deprecate；  
   - 删除/deprecate 前检查是否被 Profile / manifest 引用。

5. **manifest / report 必须带 scope**  

   ```json
   {
     "pack_id": "agent.capability",
     "version": "0.1.0",
     "scope": "workspace",
     "workspace_id": "ws-a"
   }
   ```

   审计须能区分「全局基准」与「工作区私有题」。

### 决策 8：v1 声明范围为「文本可观测能力子集」

本阶段不接 live tools / microVM。  
A3–A5（工具选择/参数/结果使用）默认不可宣称 `covered`，无环境时标 `unknown`。  
A6 仅允许「失败措辞/定位」级证据，不得宣称真实工具恢复已测。  
A8 / A9 在 v1 默认可测子集外（`in_scope=false` → `unknown`）。  
**详见 Plan §4.2.2。**

### 决策 9：Subject × Capability × Method × Evidence；Agent 为参考实现

采纳四元组（**对象 ≠ 方法 ≠ 维度**）：

```text
Subject（被测物） × Capability（测什么） × Method（怎么测） × Evidence（证据）
```

统一骨架：

```text
Target Contract / Capability 元模型 / Case+test_purpose /
SuiteProfile / sample_manifest / Evidence / Claim Gate
```

按 Subject 适配（`EvalSubjectAdapter`）：`build_contract` / `capability_catalog` /
`validate_case` / `execute` / `judge` / `normalize`。

**当前 `OBJECT_TYPES`（9）**：`agent|prompt|skill|workflow|model|api|generated_app|dataset|system`。  
**不是一等 object_type**：KB/Code Review（独立路径→Subject 候选）；Session/Trace（偏 runtime/evidence）；Tool/MCP、Multi-Agent（未来 Subject）。  
**Method（禁止塞进 OBJECT_TYPES）**：Arena、G2b、S1、Calibration、Human Review、Static/Replay/Dynamic。  
**Dimension（跨 Subject 复用）**：安全、PII/合规、成本、延迟等——对齐能力矩阵，不新建 object_type。

拒绝：

- 一套 `prompt + must_contain` 通吃所有 Subject；  
- 为每个 Subject 复制一整套 Plan/Profile/Manifest 引擎；  
- 把 Arena/G2b/S1/PII/成本等 **方法或维度** 硬编码成 `object_type`；  
- Core 内 `if object_type ==` 堆业务分支（须 SubjectAdapter registry）。

落地顺序：AgentAdapter → 抽出 `EvalSubjectAdapter` → Prompt/Workflow/Model →
KB/RAG → Code Review → Session → Tool/MCP / Multi-Agent；Arena/G2b/S1 保持方法轨。  
已有契约层见 [`eval-object-contract-and-plan.md`](../plans/eval-object-contract-and-plan.md)；本 ADR 不重写该契约，只约束能力 Case Pack 与跨 Subject 扩展方式。

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
| 用户新建 pack 默认 `global` | 拒绝 | 跨工作区泄漏 |
| 缺省 scope 静默推断为 global | 拒绝 | 必须 `scope_required` |
| 无工具环境却标工具能力 covered | 拒绝 | 违反 unknown≠pass |
| 一套题通吃所有 Subject | 拒绝 | 执行/判分形态不可通约 |
| 每 Subject 复制 Plan 引擎 | 拒绝 | SubjectAdapter，复用编排 |
| Arena/G2b/S1 升为 object_type | 拒绝 | 属 Method，保持方法轨 |
| PII/成本等升为 object_type | 拒绝 | 属 Dimension，跨 Subject 复用 |
| 现有方案 | 采纳 | 四元组 + 工厂复用 + Profile + manifest + claim gate + Agent-first adapter |

---

## 5. 与现有系统的关系

| 系统 | 关系 |
|---|---|
| Case Pack 工厂 P0–P3.1 | **复用，不重写**；P3 只做覆盖驱动补题 |
| Plan v2 | 增量支持 `profile_id` / 能力配额 / `sample_manifest` |
| G2b-100 | **Method** 轨（人工双盲），独立 L1，不升 object_type |
| Arena / S1 / calibration | **Method** 轨，可选导入为 pack 镜像；不升 object_type |
| Workspace 隔离 | pack 必须声明 `scope`，跨 workspace 禁止 |
| Scorecard | 只读消费证据；不因本方案自动改分 |

---

## 6. 实施前置条件

### 6.1 阻塞 P0（必须先签/先冻结）

| # | 项 | 产出 | 状态 |
|---|---|---|---|
| 1 | capability ID 对照表 | [`CAPABILITY_ID_MAP_V1.md`](../plans/CAPABILITY_ID_MAP_V1.md) | Frozen-draft · **待 owner 签字** |
| 2 | v1 可测子集 | Plan §4.2.2 签字页 | Frozen-draft · **待 `SIGNED v1_measurable_subset`** |
| 3 | `test_purpose` schema | [`CASE_TEST_PURPOSE_SCHEMA_V1.md`](../plans/CASE_TEST_PURPOSE_SCHEMA_V1.md) | Frozen-draft · **待签字** |
| 4 | Suite Profile schema | [`SUITE_PROFILE_SCHEMA_V1.md`](../plans/SUITE_PROFILE_SCHEMA_V1.md) | Frozen-draft · **待签字** |
| 5 | 权威存储路径 | ADR 决策 7.1 | ✅ |
| 6 | scope 按创建来源默认 | ADR 决策 7.2–7.3 | ✅ 闭环（不单独签 ADR） |

**签字顺序建议**：#1 → #3 → #4 → #2 → 四项齐后 ADR Proposed→**Accepted** → 另开实施变更单（勾选 §6.1）。  
**scope 不与「是否实施」绑定。**

### 6.2 可后置到 P2/P4

1. Regression 配额固定 vs 风险加权；
2. Benchmark holdout 比例与统计方法批准方；
3. judge 校准一致率升级阈值；
4. `test_purpose` 是否允许按对象类型扩展字段（在统一必填集之上）。

本 ADR 通过后，仍需**单独变更单**实施；变更单须勾选 §6.1 已满足。

---

## 7. 开放问题（已分类）

### 阻塞 P0（仍待签）

1. ~~`scope`~~ → 已采纳决策 7.2–7.3  
2. [`CAPABILITY_ID_MAP_V1.md`](../plans/CAPABILITY_ID_MAP_V1.md) owner 签字？  
3. [`CASE_TEST_PURPOSE_SCHEMA_V1.md`](../plans/CASE_TEST_PURPOSE_SCHEMA_V1.md) owner 签字？  
4. [`SUITE_PROFILE_SCHEMA_V1.md`](../plans/SUITE_PROFILE_SCHEMA_V1.md) owner 签字？  
5. Plan §4.2.2 `SIGNED v1_measurable_subset`？

### 可后置 P2/P4

6. Regression 配额风险加权（v1 已定 **fixed**，见 Profile schema）  
7. Benchmark holdout 比例与统计方法由谁批准？  
8. judge 校准达到什么一致率才允许 report-only 升级？  
9. 工具/Session 环境就绪后，A3–A5 / A8 / A9 如何升为 in-scope？

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

**采纳“能力驱动 Case Pack + Suite Profile + test_purpose + manifest”作为题库扩展基线；采纳 `Subject × Capability × Method × Evidence` + `EvalSubjectAdapter`（Agent 参考实现）作为跨对象扩展方式。**

不采纳“固定卷无限加题”“运行时随机出题”“LLM 直接当 gold”“题数等于完整性”“双源存储”“无环境却宣称工具能力已测”“一套题通吃所有 Subject”“把 Arena/G2b/S1/维度硬塞进 object_type”。

**本 ADR 只做设计决策，不实施；实施需另开变更单，且 §6.1 阻塞项齐备。**
