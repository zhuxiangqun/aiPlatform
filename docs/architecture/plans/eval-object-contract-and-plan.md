# Eval Object Contract & Evaluation Plan — 通用评测对象契约

> **类型**：短契约（字段语义 + 匹配/状态机 + 报告强制披露；非长白皮书）  
> **版本**：v0.5 · 2026-11-07  
> **状态**：**字段语义锁定** · **P0–P3 已接线**（MatchReport + 五态 + Plan + 多 object_type 适配器）· **仍不得宣称充分/准确认证**  
> **关联**：[`eval-exam-runtime-tiers.md`](./eval-exam-runtime-tiers.md) · [`external-agent-eval-contract.md`](./external-agent-eval-contract.md) · [`EVAL_RUNTIME_CONTRACT.md`](./EVAL_RUNTIME_CONTRACT.md) · [`eval-v1-charter.md`](./eval-v1-charter.md) · [`workspace-isolation-contract.md`](./workspace-isolation-contract.md)  
> **诚实性**：`accuracy_claim` / `sufficiency_claim` **绑定评测范围**（对象版本 × 运行时 × 用例包 × 判分器 × 维度 × 样本量）；覆盖 ≠ 充分；未测/不适用 ≠ 通过。

---

## 0. 目标与非目标

### 0.1 目标

1. 评测对象不限于 Agent：同一流程覆盖 **Agent / Prompt / Skill / Workflow / 模型 / API / 生成应用 / 数据集 / 系统组合**。  
2. 用 **对象契约（EvalTarget Contract）** + **用例适用条件** 做可解释匹配，替代「固定题单绑任意对象」。  
3. 统一 **Evaluation Plan** 编译：契约 → 用例包 → 运行时 → 判分器 → 执行 → 限定结论。  
4. 结果状态至少五态；报告强制披露适用范围、覆盖与未测/不适用。

### 0.2 与 Runtime Tiers 的分工（锁定）

| 契约 | 负责 | 不负责 |
|------|------|--------|
| **本文（Object Contract）** | 评谁、哪些题适用、oracle、五态（含不适用）、Plan 选题 | 本次实际在哪台运行时执行 |
| **[`eval-exam-runtime-tiers.md`](./eval-exam-runtime-tiers.md)** | **`runtime_tier`=实际执行面**；`target_runtime`=目标交付形态；`runtime_claim` 范围 | 题目适不适合对象；是否充分 |

契约字段 `target_runtime[]`（对象声明的目标形态）由本文维护；落盘报告里的单值 `target_runtime` / 实际 `runtime_tier` 由 Runtime Tiers 契约取值规则归档。二者**不得**合并成一个字段。

### 0.3 非目标（本契约明确不做）

- 不为每个对象手工维护完全不相交的私有题库作为唯一路径。  
- 不靠 `agent_id` / 显示名 / skills 关键词猜角色（禁止 core `if agent_id ==`）。  
- 不把 LLM「动态出题」直接当作可比回归金标（生成题仅候选，须审核 + 版本锁定）。  
- 不因画像筛题而静默去掉安全/权限类义务（无执行权仍须测拒执/转交）。  
- 不把本契约等同于 `accuracy_claim=true` 或发布认证。  
- 不重定义 `runtime_tier` 取值（以 Runtime Tiers 文档为权威）。

### 0.4 与现状的关系（代码事实）

| 现状 | 含义 |
|------|------|
| `core/engine/eval_sets/*.json` + `BUILTIN_EXAM_SUITE` | **固定卷序**；全体 Agent 冒烟共用 |
| `agent_exam_ops._bind_set_to_agent` | 只改执行者 `agent_id`，**不**改题目/金标 |
| `runtime_tier` + `target_runtime`（runtime-tiers v1.3） | 实际执行面与目标形态已拆分；本契约 **消费** 之不重定义 |
| formal report / 矩阵 | **P1**：五态含 `not_applicable`（formal `v1.11`）；缺失值占位 ≠ 不适用语义 |
| P0 `target_contract` + `match_report` | exam / `POST /evaluation/match-cases` 已挂载；**仍不筛题** |

目标态：冒烟改为 Plan 编译产物（P2）。

---

## 1. 核心流水线（唯一形状）

```text
EvalTarget（类型+版本+契约） + 评测目的
          ↓
匹配适用用例包（基础 / 能力 / 专项）→ MatchReport（可解释）
          ↓
选择 runtime_tier + oracle（符合契约前置）
          ↓
执行 → 轨迹 / 证据 / 版本戳
          ↓
五态结果 + 限定结论（scope-bound claims）
```

禁止并行实现第二套「按名字选题」入口；所有对象类型适配器只编译进同一 Plan。

---

## 2. EvalTarget Contract（对象契约）

每次评测必须解析并落盘一份契约快照（不可变；与对象版本绑定）。

### 2.1 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `schema` | string | 固定 `eval.target_contract.v1` |
| `object_type` | enum | 见 §2.2 |
| `object_id` | string | 稳定 ID（Agent 名 / skill 名 / `ext:{id}` / app id …） |
| `object_version` | string | 语义化或内容哈希；缺省须标 `version_unspecified` 并记复现限制 |
| `capabilities` | string[] | **显式**能力标签（配置维护；平台可建议，不可只靠猜测） |
| `tools` | string[] | 声明可用工具名（可空） |
| `permissions` | string[] | 如 `read_only` / `workspace_write` / `shell` … |
| `target_runtime` | string[] | 该对象**目标**交付/评测形态（如 `pi` / `workspace_execute`）；**≠** 本次实际 `runtime_tier` |
| `eval_purpose` | string[] | 如 `behavior` / `compat` / `perf` / `safety` / `regression` |
| `boundaries` | object | 不能做什么 / 禁止副作用（短声明） |

### 2.2 `object_type` 枚举（可扩展，扩展须改本文）

`agent` · `prompt` · `skill` · `workflow` · `model` · `api` · `generated_app` · `dataset` · `system`

### 2.3 可选但推荐

| 字段 | 说明 |
|------|------|
| `roles` | 软标签（如 `qa` / `codegen`）；**不得**单独作为匹配唯一依据 |
| `required_env` | 模型、沙箱、网络、密钥名（非密钥值） |
| `source_refs` | AGENT.md / OpenAPI / 导出物路径等溯源 |

### 2.4 生成规则

- Agent：优先读 `config.eval_profile`；`AgentManager` 加载时也会把 AGENT.md **顶层** `eval_profile` 注入 `config`（与写在 `config:` 下等价）。缺省时 `resolve_agent_eval_profile` 用 skills/tools **子串 hint** 推导（`profile_source=derived_hints`）；禁止 `if agent_id ==`。  
- 外部 HTTP：契约来自 target registry + 协议能力（见 external contract）。  
- Skill / Prompt / App：来自各自元数据与已接线评测入口；无契约则 Plan 只能跑「类型基础包」中标记 `requires_contract=false` 的子集，并强制 `sufficiency_claim=false`。

**AGENT.md 样例（种子）**：`engine/agents/conversational_agent`、`rag_agent`、`react_agent`；workspace `platform_consultant`。字段形状：

```yaml
eval_profile:
  capabilities: [clarify_or_ask, multi_turn_memory]  # 或 retrieval / error_recovery / code_gen …
  permissions: [read_only]
  roles: [conversational]
  target_runtime: [workspace_execute]
  eval_purpose: [behavior, regression, safety]
  boundaries:
    note: human-readable scope
```

---

## 3. 用例适用条件（Case Applicability）

每条用例（或卷级默认 + 题级覆盖）声明：

| 字段 | 说明 |
|------|------|
| `case_id` / `set_id` | 稳定 ID |
| `applies_to.object_types` | 适用对象类型列表 |
| `requires.capabilities` | 对象须声明的能力（空 = 不限能力） |
| `requires.tools` | 须具备的工具（空 = 不要求） |
| `requires.permissions` | 须具备的权限 |
| `requires.runtime` | 允许的**目标**形态与/或实际执行面约束（匹配时写清查的是 `target_runtime` 还是本次 `runtime_tier`） |
| `evaluates` | 贡献哪些评测维度 ID |
| `oracle` | 见 §5 |
| `pack` | `core` \| `capability` \| `special` |
| `risk_level` | `low` \| `medium` \| `high` |

**匹配语义（锁定）**：

1. `object_type ∉ applies_to` → **不适用**（记原因 `object_type_mismatch`）。  
2. `requires.*` 任一不满足 → **不适用**（原因逐条列出）；**例外**：`pack=special` 且 `evaluates` 含安全/权限、且用例标记 `obligation=refuse_or_handoff` 时，对「缺执行权限」的对象改为 **适用**（测拒执/转交），不得标不适用而跳过。  
3. 满足 requires 但本次 Plan 未选入 → **未测**（适用未跑）。  
4. 匹配结果必须产出 `MatchReport`（入选 / 不适用 / 原因），进入报告与落盘。

---

## 4. 用例包分层

| 包 | 含义 | 默认是否入 Plan |
|----|------|----------------|
| **类型基础包 `core`** | 该 `object_type` 几乎都应满足的契约行为（理解约束、基础安全边界、声明范围内的最小交付） | **默认入选**（匹配后） |
| **能力包 `capability`** | 按契约 `capabilities` 选择（检索、代码生成、追问、工具使用、测试设计…） | 默认入选匹配项 |
| **专项包 `special`** | 高风险确认、工具故障注入、长程记忆、成本延迟、外部 API、沙箱 | **显式开启**或目的含 `safety`/`perf`/`reliability` 时入选；未跑 → **未测** |

报告必须分别展示三包的覆盖；禁止只跑能力包却暗示「全维已测」。

---

## 5. Oracle（判分器）契约

| `oracle.type` | 适用 | 说明 |
|---------------|------|------|
| `deterministic_assert` | API / schema / 单测出口 | 程序断言 |
| `lexical_must_contain` | 标识符、固定格式、代码结构锚点 | 词面；误判风险高，须在题面注明 |
| `lexical_must_contain_any` | 追问/拒答等多措辞 | 仍词面，宽于全部命中 |
| `semantic_rubric` | 生成式行为 | 明确可接受范围；须校准样本；默认不可 `accuracy_claim` |
| `trajectory_in_order` | 工具名序列 | 见 external / eval metrics；≠ 副作用充分 |
| `state_delta` | 有副作用对象 | 权限边界 + 状态变化证据 |
| `human_review` | 争议/高风险 | 人工；未完成 → 无法判定 |

每题只允许一个主 oracle；可附加 `evidence_requirements`（须保存响应摘录脱敏、工具轨迹、会话 ID 等）。  
**禁止**用词面规则冒充语义充分；放宽金标须改版本化用例，不得为刷绿临时改阈值且不改 `case` 版本。

---

## 6. 结果状态机（五态）

每个 **用例** 与每个 **维度** 归档为恰好一态：

| 状态 | 含义 | 可否进「失败计数」 | 可否当通过 |
|------|------|:---:|:---:|
| `pass` | 适用且证据满足 oracle | 否 | 是 |
| `fail` | 适用且有失败证据 | 是 | 否 |
| `untested` | 适用但本次未跑 | 否 | **否** |
| `not_applicable` | 契约/requires 不匹配（或义务例外外的不适用） | 否 | **否** |
| `inconclusive` | 已跑但证据不足 / 探针未核实 | 否（可进「需关注」） | **否** |

### 6.1 聚合规则（锁定原则）

- 维度状态由所属用例状态按维度策略聚合；默认：**任一适用且 fail → 维 fail**；存在 inconclusive 且无 fail → 维可 `inconclusive`；全部 untested → `untested`；全部 not_applicable → `not_applicable`。  
- **综合「不通过」** 仅由 `fail`（及安全硬门槛 veto）驱动；不得因大量 `untested`/`not_applicable` 单独判不通过。  
- **工程复合分**（若仍用 legacy_7dim）：`not_applicable` **不得**填满分；`untested`/`inconclusive` 按已文档化的 missing_fill（中性占位）并进 `filled_keys`；硬门槛 veto 单独否决。细则变更须同步 formal report `score_policy`。  
- 安全硬门槛：`veto=true` → 发布讨论否决；与平均分正交。

---

## 7. Evaluation Plan（编译产物）

### 7.1 Plan 对象（逻辑字段）

| 字段 | 说明 |
|------|------|
| `plan_id` | 稳定或内容哈希 |
| `target_contract` | §2 快照 |
| `purpose` | 评测目的 |
| `selected_cases[]` | case_id + pack + 入选原因 |
| `excluded_cases[]` | case_id + `not_applicable` 原因 或「本目的未选专项」 |
| `runtime_tier` | **实际**执行面（runtime-tiers） |
| `target_runtime` | 主目标交付形态（可与实际不同） |
| `oracle_binding` | case_id → oracle.type |
| `claims_policy` | `accuracy_claim`/`sufficiency_claim` 默认 false + 解禁条件引用 |

### 7.2 相对 `BUILTIN_EXAM_SUITE` 的迁移

| 阶段 | 行为 |
|------|------|
| 今（P2） | 套件仍为模板 ID；冒烟先 `compile-plan` 再执行 selected；N/A/专项未测 → skipped |
| Plan v1 | ✅ 默认 core+capability；special 按 purpose/include_special |
| Plan v2 | ✅ UI 以 Plan 为选题真相：预览 Plan + purpose 控件；`BUILTIN_EXAM_SUITE` 仅模板；编译失败阻断开跑（不回退全套） |

选题真相：`compile-plan` / Evaluation Plan；固定套件不再作为第二真相。

---

## 8. 报告强制披露（四个问题）

正式报告（及 attributable 摘要）必须能回答：

1. **测了什么 / 没测什么？** — 三包覆盖数、未测列表。  
2. **哪些用例适用、依据？** — MatchReport（capabilities / permissions / runtime）。  
3. **失败归因粗分** — `agent_or_object_behavior` · `case_mismatch` · `oracle_too_narrow` · `runtime_or_instrumentation`（允许「待核定」）。  
4. **结论范围** — 对象版本、runtime_tier、plan_id、维度、样本量；`accuracy_claim` 仅在范围门槛满足时可对**该范围**为 true。

建议增加计数：`applicable` / `pass` / `fail` / `untested` / `not_applicable` / `inconclusive`。

**接线（formal `v1.12`）**：`buildObjectContractDisclosure` → 报告 `object_contract` + Markdown §2.1 + EvalFullReportPanel「1.1」；含 `plan_ids`、三包覆盖、MatchReport 入选/排除、失败归因粗分。

---

## 9. 动态生成题（候选通道）

| 允许 | 禁止 |
|------|------|
| 按契约生成**候选**用例 → 人工/门禁审核 → 写入版本化集 | 每次 live 即时生成并直接进可比回归 |
| 生成题标记 `provenance=generated` + `locked_version` | 无版本锁定却对比历史分数 |
| 默认 `accuracy_claim=false` | 生成题自动抬升 accuracy |

---

## 10. 对象类型适配器（实现边界）

| object_type | 典型 `target_runtime` | 实际 `runtime_tier` 示例 | 备注 |
|-------------|----------------------|-------------------------|------|
| `agent` | `workspace_execute` | live→`workspace_execute`；dry→`fixture` | 现状主路径 |
| `api` / 外部对话 | `external_pull` | live pull→`external_pull`；dry→`fixture` | external contract |
| `generated_app` | `pi` | live Pi CLI→`pi`；offline/runs_eval→`fixture` | **禁止**未调 Pi 却标实际 `pi` |
| `skill` | `core_skill_execute` | quality→`core_skill_execute`；trigger→`fixture` | 不得冒充 agent workspace |
| `prompt` / `model` / `dataset` | 按入口 | 多为 `fixture` 或专用路径 | 经 Plan 挂载 |
| `system` | 组合声明 | 按子执行面分别归档 | 子对象结论不可自动外推 |

新对象类型：先补契约字段与适配器，再进 UI；禁止只加按钮不改 MatchReport。

---

## 11. 实施阶段（设计锁定；开工另批）

| 阶段 | 交付 | 验收 |
|------|------|------|
| **P0** | `eval.target_contract.v1` + `applicability_draft.json` + MatchReport + `POST /evaluation/match-cases`；exam 响应挂载 advisory 报告 | ✅ 单测可解释入选/不适用；high_risk refuse_or_handoff；**不**改执行选题 |
| **P1** | 报告/矩阵五态含 `not_applicable`；formal `v1.11`；MatchReport 排除卷→维 N/A | ✅ 不计失败；与 untested 分列；旧「未测/不适用」混称保留兼容 |
| **P2** | `compile_evaluation_plan` + `POST /evaluation/compile-plan`；冒烟按 Plan 跳过 N/A/专项未测 | ✅ 默认 core+匹配 capability；special 需 purpose 或 include_special；本地冒烟 purpose 含 safety/reliability |
| **P3** | `object_adapters` + 类型默认用例模板；skill/api/generated_app 挂载同一 Plan | ✅ 同一 `eval.evaluation_plan.v1`；agent 卷对 skill 标 N/A |

**本文件状态 = P0–P3 已接线。**

---

## 12. 变更规则

1. 改匹配语义、五态或 pack 定义 → 升本文版本 + formal report / attributable 同步。  
2. 新增 `object_type` 或 `oracle.type` → 改 §2.2 / §5 并登记 CAPABILITIES。  
3. 与 `runtime_tier` / 报告侧 `target_runtime` 冲突时：**以 runtime-tiers 文档为实际/目标归档权威**；本契约只定义对象声明的 `target_runtime[]` 与选题匹配。  
4. 宣称「已按能力画像评测」前：须有 MatchReport 落盘证据与非测试调用方。

---

## 13. 一句话

**统一评测流程与报告契约：不同对象用适用的用例、运行时和判分器；公共指标可比较；未测与不适用必须诚实可见，不能靠筛题或刷绿假装充分。**
