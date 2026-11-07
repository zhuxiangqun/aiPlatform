# Eval Exam Runtime Tiers — 评测档位 ↔ 运行时契约

> **类型**：短契约（字段语义 + 映射；非长白皮书）  
> **版本**：v1.3 · 2026-11-07  
> **状态**：字段语义锁定 · **实际执行面**与**目标交付形态**已拆分 · Pi 离线/Skill quality 归档纠偏 · **不**改选模/Agent 执行路径 · **不**改 `process_split_authorized`  
> **关联**：[`EVAL_RUNTIME_CONTRACT.md`](./EVAL_RUNTIME_CONTRACT.md) · [`pi-thin-runtime.md`](./pi-thin-runtime.md) · [`eval-production-independent-service.md`](./eval-production-independent-service.md) · [`eval-object-contract-and-plan.md`](./eval-object-contract-and-plan.md) · [`packages/aiplat-pi-runtime/README.md`](../../../packages/aiplat-pi-runtime/README.md)  
> **诚实性**：`accuracy_claim=false` 与 runtime 正交；覆盖 ≠ 充分；B2-L 本地工程 ≠ 生产切流 ≠ Agent exam 已上 Worker。

---

## 0. 目标与分工

### 0.1 本契约目标

1. 每次评测结果可归档到明确的 **`runtime_tier`（实际执行面，单一主键）**。  
2. 用独立字段 **`target_runtime`（目标交付形态）** 说明「对象打算在哪交付/被评」，**不得**与实际执行面混写进同一字段。  
3. 用 **`runtime_claim` / `runtime_claim_reason`** 说明「本次结论可就**实际** `runtime_tier` 范围作何种有限陈述」。  
4. 分离 **执行平面迁移/授权** 与 **本次 job 实际 runner**，避免误读。

**非目标**：决定哪些题适用于哪个对象（见 Object Contract）；宣称充分/准确/发布认证；把 Agent live 接到 Pi；宣称执行平面已迁移。

### 0.2 与 Eval Object Contract 的分工（锁定）

| 契约 | 回答的问题 | 不回答 |
|------|------------|--------|
| **[`eval-object-contract-and-plan.md`](./eval-object-contract-and-plan.md)** | 评谁、哪些题适用、用什么判分器、五态结果（含不适用） | 本次实际在哪台运行时执行 |
| **本文** | 本次**实际**在哪执行、结论能说明哪个运行时范围 | 题目适不适合该对象；评测是否充分 |

示例：`qa_agent` 在工作区 Execute **真实运行** → `runtime_tier=workspace_execute`，`target_runtime` 可含 `workspace_execute`。仅规则/dry-run 检查试卷、**未调用被测对象** → `runtime_tier=fixture`（`target_runtime` 仍可写该对象的目标形态）。

`runtime_claim=true` **只**表示可对**本次实际** `runtime_tier` 作有限陈述；≠ accuracy、充分性或发布认证。

---

## 1. 双字段：实际 vs 目标

| 字段 | 含义 | 规则 |
|------|------|------|
| **`runtime_tier`** | **本次 job 实际执行面**（归档主键） | 只按「有没有、在哪调用了被测对象 / 宿主」取值；禁止用「目标交付是 Pi」填成 `pi` |
| **`target_runtime`** | **对象目标交付/评测形态**（可与契约 `target_runtime[]` 对齐；单值时取主目标） | 可与 `runtime_tier` 不同；离线结构校验、未调 Pi CLI 时仍可为 `pi` |
| `execution_mode` | 细模式字符串（可选） | **不得替代** `runtime_tier` |

### 1.1 判定口诀

> **有没有真正跑到该档位的宿主/被测对象？有 → 该档；没有 → 不得标该档。**  
> 目标形态另写 `target_runtime`。

---

## 2. `runtime_tier` 档位（实际执行面）

| tier_id | 含义（实际） | 典型用途 | 诚实边界 |
|---------|--------------|----------|----------|
| `fixture` | 规则 / 金标 / 结构导出 / dry-run；**不加载、不调用被测对象**（Agent / Skill / App 等一律适用） | 预检、仅导出校验、路由候选评分、未调宿主的冒烟 | **不得**声明被测对象运行行为 |
| `pi` | **确已**在厂外薄宿主 [`aiplat-pi-runtime`](../../../packages/aiplat-pi-runtime/README.md) 执行（如 Pi CLI 成功路径） | 生成应用 Pi **live** 冒烟 | ≠ 工作区 ReAct / PolicyGate；仅结构导出 ≠ `pi` |
| `workspace_execute` | Core `run_workspace_agent` + 真实 AgentInfo | Agent 正式 live、本地标准冒烟 | 仅本命名工作区 Execute；≠ Eval Worker |
| `core_skill_execute` | Core `skill_manager`（或等价）**已调用被测 Skill** | Skill suite · quality | ≠ Agent `workspace_execute`；≠「未执行 handler 的 trigger」 |
| `eval_worker` | 独立 Eval API / Worker allowlist runner **确在 Worker 执行** | 验管道 Job 在 Worker 时 | ≠「执行平面已迁移」；≠ 默认 Agent exam |
| `external_pull` | **确已**对外部 HTTP 目标发起拉对话（scored pull） | 外部目标 live | ≠ workspace；≠ pi；dry 未拉 ≠ 本档 |

v1.2→v1.3：**新增** `core_skill_execute`；**纠正**「目标 Pi / 未调 CLI 却标 `pi`」「Skill quality 调了 skill 却标 `fixture`」。

---

## 3. 强制报告字段

每次 exam / 可比对的评测响应与落盘应显式携带：

| 字段 | 类型 | 说明 |
|------|------|------|
| `runtime_tier` | string | §2 之一（**实际**） |
| `target_runtime` | string | 目标交付形态（常为 `pi` / `workspace_execute` / `external_pull` / `core_skill_execute` / …）；可与 tier 不同 |
| `runtime_claim` | bool | 是否可就**实际** tier 范围作有限陈述 |
| `runtime_claim_reason` | string | `runtime_claim=false` 时**必填**；建议写清实际 vs 目标差异 |
| `accuracy_claim` | bool | **独立**；工程默认 `false`；与 runtime 正交 |
| `runner_id` | string? | 仅 `eval_worker`（或验管道 Worker Job）建议带上 |
| `execution_mode` | string? | 细模式（如 `skill_trigger_heuristic` / `skill_manager_quality`） |

`runtime_claim=true` **不等于** accuracy、充分性或发布认证。

---

## 4. `runtime_claim` 判定表（相对实际 tier）

| tier | 何时可为 `true` | 否则 `false` + reason 示例 |
|------|-----------------|---------------------------|
| `fixture` | **永不**对被测对象行为 claim | `fixture does not execute subject` |
| `pi` | 本次确在 Pi 宿主执行 | `pi CLI not invoked` · `structural/export only` |
| `workspace_execute` | 仅声明本命名工作区 Execute 表现 | `not eval_worker` · `do not extrapolate` |
| `core_skill_execute` | 仅声明「经 Core skill_manager 调用该 Skill」的表现 | `trigger only; handler not executed` |
| `eval_worker` | 该次确由 Worker allowlist runner 执行 | `agent exam still on workspace_execute` |
| `external_pull` | 仅声明该外部 HTTP 拉模式表现 | `dry-run; no scored pull` |

---

## 5. B2 双态分离（禁止混称）

| 概念 | 含义 | 产品表现 |
|------|------|----------|
| **执行平面迁移 / 授权** | Central 是否授权切到独立 Eval 生产平面 | Banner「执行平面尚未迁移（B2）」；`process_split_authorized=false` |
| **本次 job 实际 runner** | 该条 Job 是否跑在 Worker | `runtime_tier=eval_worker` + `runner_id` |

**锁定句**：B2-L「Worker / 契约门本地已实现」≠「workspace Agent exam 已切到 Eval Worker」。  
**当前**：Agent 正式 live / 本地冒烟 = `workspace_execute`。

---

## 6. 预检归档（按实际行为，不按按钮名）

| 实际行为 | `runtime_tier` | `target_runtime`（例） | `runtime_claim` |
|----------|----------------|------------------------|-----------------|
| 仅校验试卷 / dry-run；不调用被测对象 | `fixture` | 对象目标（如 `workspace_execute`） | `false` · `fixture does not execute subject` |
| 真实加载或调用 Agent | `workspace_execute` | `workspace_execute` | 按 §4 |

一期：`live=false` Agent exam → **`fixture`**。若预检演变为会调对象，必须改 tier。

---

## 7. 入口映射（实际 tier + 目标；v1.3）

| 入口 | `runtime_tier`（实际） | `target_runtime` | `runtime_claim` | 备注 |
|------|------------------------|------------------|-----------------|------|
| Agent 预检（dry-run） | `fixture` | `workspace_execute` | false | §6 |
| Agent 正式 live / 本地标准冒烟 | `workspace_execute` | `workspace_execute` | true | 真实 AgentInfo |
| 外部目标 dry（未 scored pull） | `fixture` | `external_pull` | false | 仅校验目标/试卷 |
| 外部目标 live（已 pull） | `external_pull` | `external_pull` | true | |
| 验管道 Job | `fixture` 或 `eval_worker` | 按 Job | 按 §4 | 确在 Worker → 后者 + `runner_id` |
| 评测生成应用 · runs_eval | `fixture` | `pi` | false | 平台路径；**未**跑 Pi 宿主 |
| 评测生成应用 · Pi 冒烟 offline | `fixture` | `pi` | false | 导出+结构；**CLI 未调** |
| 评测生成应用 · Pi 冒烟 live | `pi` | `pi` | true（CLI 成功） | 失败则 claim=false，tier 仍以是否进入 Pi 为准 |
| Skill suite · trigger | `fixture` | `core_skill_execute` | false | 仅路由候选；**不**执行被测 handler；`execution_mode=skill_trigger_*` |
| Skill suite · quality | `core_skill_execute` | `core_skill_execute` | true（限该路径） | 经 Core `skill_manager` **已调**被测 skill；`execution_mode=skill_manager_quality` |
| 验管道 skill_suite Job | `fixture` 或 `eval_worker` | 按 Job | 按 §4 | ≠ Skills 页成果物 |

**v1.2 冲突已消解**：离线 Pi ≠ `runtime_tier=pi`；Skill quality ≠ `fixture`。

---

## 8. 与 Pi / Eval Worker / Object Contract 边界

- Pi：厂外薄交付宿主；**目标**用 `target_runtime=pi`；**实际**仅当 Pi 宿主被调用才标 `runtime_tier=pi`。  
- Eval Worker：见 `EVAL_RUNTIME_CONTRACT.md`；本文只规定 exam 入口如何标注。  
- 选题 / 适用 / 判分器 / 不适用：见 Object Contract；本文不筛选用例。

---

## 9. 变更规则

- 新增实际 tier 必须改本文 + CAPABILITIES + `exam_runtime_tier` / 前端 `examRuntimeTier`，并保证 UI/落盘可归档。  
- 禁止用「目标交付是 X」填写 `runtime_tier=X`。  
- 禁止用文案「本地联调成功」暗示 `process_split_authorized=true` 或 Agent exam=`eval_worker`。  
- 与 Object Contract 的 `target_runtime[]` 对齐时：报告单值字段取主目标；多值时在 reason/附录列出。
