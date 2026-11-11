---
doc_type: Architecture
---

# Eval Object Contract & Evaluation Plan — 通用评测对象契约

> **类型**：短契约（字段语义 + 匹配/状态机 + 报告强制披露；非长白皮书）  
> **版本**：v1.0 · 2026-11-08  
> **状态**：**字段语义锁定** · 对象匹配/成熟度/derived_hints/§6.1 适用态锁定 · **运行时取值以 Runtime Tiers v1.4 为权威** · 正式报告综合结论与 `runtime_parts` 已对照接线 · **框架 P0–P3 + §0.8 残余 Runner + L5 claims_gate 已接线** · 对象级成熟度仍参差（见 §0.6；Agent 仍未达 L5 声明）  
> **关联**：[`eval-exam-runtime-tiers.md`](./eval-exam-runtime-tiers.md)（**v1.4**） · [`external-agent-eval-contract.md`](./external-agent-eval-contract.md) · [`EVAL_RUNTIME_CONTRACT.md`](./EVAL_RUNTIME_CONTRACT.md) · [`eval-v1-charter.md`](./eval-v1-charter.md) · [`workspace-isolation-contract.md`](./workspace-isolation-contract.md)  
> **诚实性**：`accuracy_claim` / `sufficiency_claim` **绑定评测范围**（对象版本 × 运行时 × 用例包 × 判分器 × 维度 × 样本量）；覆盖 ≠ 充分；未测/不适用 ≠ 通过；不完整覆盖 ≠ 通过。

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

契约字段 `target_runtime[]`（对象声明的目标形态）由本文维护；落盘报告里的单值 `target_runtime` / 实际 `runtime_tier` / `execution_mode` / `runtime_claim` **一律以 Runtime Tiers 为权威**（当前 **v1.4**）。二者**不得**合并成一个字段。  
Plan 编译期的 `runtime_tier` 仅为**顾问值**，执行落盘必须以入口实际行为重标注（见 Runtime Tiers §7）；禁止用顾问值覆盖执行结果。

### 0.3 非目标（本契约明确不做）

- 不为每个对象手工维护完全不相交的私有题库作为唯一路径。  
- 不靠 `agent_id` / 显示名 / skills 关键词猜角色（禁止 core `if agent_id ==`）。  
- 不把 LLM「动态出题」直接当作可比回归金标（生成题仅候选，须审核 + 版本锁定）。  
- 不因画像筛题而静默去掉安全/权限类义务（无执行权仍须测拒执/转交）。  
- 不把本契约等同于 `accuracy_claim=true` 或发布认证。  
- 不重定义 `runtime_tier` 取值（以 Runtime Tiers 文档为权威）。

### 0.4 与现状的关系（代码事实 · 2026-11-08）

| 现状 | 含义 |
|------|------|
| Agent 冒烟 UI（Plan v2） | `BUILTIN_EXAM_SUITE` = **题集模板**；**选题真相** = `compile-plan` / Evaluation Plan；编译失败阻断开跑（不静默空跑） |
| `eval_sets/*.json` + `_bind_set_to_agent` | **固定题面/金标**；只换执行者 `agent_id`，**不**按名字动态出题 |
| `runtime_tier` ≠ `target_runtime` | 实际执行面 vs 目标交付形态；本契约声明 `target_runtime[]`，归档规则见 runtime-tiers |
| formal / 可归因报告 | 五态含 `not_applicable`；报告切片存在 ≠ 本次 Plan 已测该维 |
| Prompt 页 / `prompt_eval_ops` | **独立 DB 用例路径**；≠ 通用 Plan 题包执行链 |
| Knowledge/KB 样本评测 | **检索/问答指标**；≠ 通用 `dataset` object_type |

**禁止混读**：「Plan 能识别/选中」≠「已有可执行评测」≠「充分/准确认证」。

### 0.5 成熟度五级（盘点强制口径 · 唯一读法）

| 级 | 含义（AND，缺一不可） | 未达时禁止说的话 |
|:--:|----------------------|------------------|
| **L1** | 有入口（Tab/API） | — |
| **L2** | 能 `compile-plan` / MatchReport 匹配（或等价适用性匹配） | 「已评测」 |
| **L3** | **同时**具备：① 版本化用例；② 明确 oracle/判分器；③ **可执行入口**（挂到该对象的 Runner/API） | 「和 Agent 同级产品」；仅 draft/JSON 无入口 ≠ L3 |
| **L4** | 在 L3 之上，另有**本次实际运行**的可复核证据（run / 轨迹 / 落盘） | 「准确率」「充分性认证」；亦勿把 L4 运行证据称作「已校准」 |
| **L5** | 在 L4 之上，**统计/充分性门槛**已满足；**可**作声明，但**仅限**明确限定的对象版本 × 任务分布 × 运行条件 × 样本量 | 未达门槛时不得作准确率/充分性声明 |

**「校准」分词（防混读）**：

| 用语 | 归属 | 含义 |
|------|------|------|
| **运行证据 / 工程校准快照** | ≤ L4 | 某次（或工程流水线）可复核执行与落盘；可做问题发现；**不是**准确率声明 |
| **统计学校准 / 准确率门槛** | L5 | 在限定范围内满足样本量与任务分布等门槛后，方可作范围限定声明 |

对象盘点必须给到 **最高已达级**，并分列 A/B/C 指标口径；**禁止**用「框架已接线」推导「该对象已完整可评」。等级读法以上表为准，下文不得另给冲突定义。

| 口径 | 是什么 | 不是什么 |
|------|--------|----------|
| **A** | 用例包 `evaluates[]`（选题贡献维） | 不等于报告已出该切片 |
| **B** | Agent 可归因报告切片（跑后工程信号） | 不等于本 Plan 入选了对应卷 |
| **C** | 各入口私有判分（trigger TP/TN、prompt expected_keys…） | 不等于统一维度表 |

### 0.6 对象状态口径（稳妥表述 · 与仓库证据对齐）

| 对象 | 最高级 | 题包 / Oracle | Runner / 入口 | 执行证据 | 稳妥表述 |
|------|:------:|---------------|---------------|----------|----------|
| **Agent** | **L4** | 固定 `default/*` JSON + 词面/路径 oracle | 冒烟 UI + exam；Plan=选题真相 | run / 可归因报告 | 固定卷+Plan+运行与报告；可做工程问题发现；**未达 L5**（`claims_gate` 已接线但默认不解禁；样本量/覆盖门槛通常未过） |
| **Skill** | **L4** | suite 正负例 / quality cases | `skill_evals` trigger·quality | suite run 落盘 | 限定 trigger 路由与 quality 路径；≠ Agent exam |
| **API** | **L4** | 外部试卷任务 | external HTTP pull | exam 结果 `ext:{id}` | 限定对话 HTTP pull；claim=false |
| **生成应用** | **L3–L4** | Pi smoke / runs_eval 探针 | apps 面板 + Pi/runs_eval | 视 live/offline | 限定 Pi smoke 与 runs_eval；offline 无 live 证据时停在 L3 |
| **Prompt·页面链** | **L3–L4** | DB `prompt_test_cases`（版本化用例）+ `expected_keys` 判分 | Prompts 页 / `prompt_eval_ops`（可执行入口） | `prompt_eval_runs` → **L4** | **独立链**：满足 L3（用例+判分+入口）；有 run 证据则达 L4。≠ 通用 Plan 路径 |
| **Prompt·Plan 链** | **L3–L4** | 版本化 `prompt/*` JSON + 词面 oracle | `POST /evaluation/prompt-plan-exam`（`prompt_plan_ops`） | dry run 落盘 → **L4**（fixture stub）；live=LLM 亦有 run | **Plan 专用链**：≠ 页面 `prompt_eval`；dry 不声明模型行为 |
| **Workflow** | **L3–L4** | 版本化 `workflow/*` + 词面 oracle | `POST /evaluation/workflow-plan-exam` | dry run → L4（fixture stub） | Plan 链可执行；≠ 真实 pipeline 宿主 |
| **Model** | **L3–L4** | 版本化 `model/*` + 词面 oracle | `POST /evaluation/model-plan-exam` | dry run → L4（fixture stub） | Plan 链可执行；**≠ 模型榜** |
| **Dataset** | **L3–L4** | 版本化 `dataset/basic` + `dataset_assert` | `POST /evaluation/dataset-plan-exam` | dry/assert run → L4 | 夹具表确定性断言；**≠ KB 样本评测** |
| **System** | **L3–L4** | 组合子对象版本化题包（默认 prompt/workflow/model/dataset basic） | `POST /evaluation/system-plan-exam` | 子 run + `runtime_parts[]` → L4 | 异质实际面不压档；顶层同质可为单值，否则 `mixed` |
| **Knowledge/KB** | 另计 | kb 样本 | Knowledge 入口 | kb reports | 检索/问答路径；**≠ `dataset` object_type** |

> 说明：`prompt`/`workflow`/`model`/`dataset`/`system` Plan Runner 已接线（§0.8 P0–P3）。`applicability_draft` 登记多项 ≠「三包产品已齐」。

### 0.7 `derived_hints` 与显式契约（防漏测）

| 规则 | 要求 |
|------|------|
| 来源标记 | `profile_source=explicit`（人写/配置） vs `derived_hints`（skills/tools 子串推导）必须落盘 |
| 置信度 | 派生能力仅为**建议选题**信号；报告须可见「派生 / 低置信」 |
| **禁止** | 仅凭 `derived_hints` **悄悄排除**用例、或把适用卷标成 `not_applicable` |
| **允许** | 在 MatchReport 中标注「建议入选 / 建议关注」；最终入选/排除须可解释且可复核 |
| 显式优先 | 有 `config.eval_profile` / 顶层 hoist 时，不得用派生结果覆盖显式 capabilities/permissions |
| **实现（2026-11-08）** | `case_match._capability_requirements_authoritative`：仅 `profile_source=explicit` 时 `missing_capability`→N/A；`derived_hints`/未知缺口记 `capability_unconfirmed:*` 并 **selected**（≠ Ollaya 决策） |
| **信任边界** | 见 [`eval-trust-boundary-lab-vs-cert.md`](./eval-trust-boundary-lab-vs-cert.md)：实验室仪器 ≠ 认证；旧 Plan `plan-924f6c070f4e1927` = `pre-fix_invalid`；重跑证据 `.aiplat/eval_trust/` |
| **Case Pack 工厂（设计基线）** | [`eval-case-pack-factory.md`](./eval-case-pack-factory.md) v0.2：**P0 前六钉未会签禁止开工**；Plan 须升 v2；`sample_manifest` 唯一执行依据 |

### 0.8 字段锁定后的残余工作（非语义债 · 对象成熟度）

字段语义锁定 **≠** 各 `object_type` 已达 Agent 同级可跑。后续实施按成熟度补齐，**不**再改 §0.5–§6.1 / Runtime Tiers 取值，除非走变更规则升版：

| 优先级 | 缺口 | 目标级 |
|--------|------|--------|
| P0 | Prompt Plan 链专用 Runner（页面链已 L3–L4） | ✅ Plan 链 ≥L3（`prompt-plan-exam`；有 run→L4） |
| P1 | Workflow / Model 专用 Runner + 执行证据 | ✅ `workflow-plan-exam` / `model-plan-exam`（typed_plan_exam；有 run→L4） |
| P2 | Dataset 通用 Runner（≠ KB 样本路径） | ✅ `dataset-plan-exam`（fixture_table `dataset_assert`；有 run→L4） |
| P3 | System 组合端到端入口（`runtime_parts` 汇总已有） | ✅ `system-plan-exam`（组合 typed parts + `runtime_parts`；有 run→L4） |
| — | L5 准确率/充分性门槛与解禁流程 | ✅ `eval.claims_gate.v1` / `POST /evaluation/claims-gate` + formal `claims_gate` + 评测中心高级「对象Plan」UI（默认 false；见 §0.9） |

### 0.9 L5 范围声明解禁（`eval.claims_gate.v1`）

| 规则 | 要求 |
|------|------|
| 默认 | `accuracy_claim` / `sufficiency_claim` **恒为 false**（Plan 编译、runtime merge、正式报告） |
| 范围绑定 | 声明必须绑定：对象类型×id×版本 × `runtime_tier` × `plan_id` × set_ids × oracle × 维度 × `sample_n` |
| 门槛（准确率） | 有运行证据；适用侧无 `untested`；非 `fixture`/`mixed`；`runtime_claim=true`；`sample_n ≥ min_sample_n`（默认 100） |
| 门槛（充分性） | 在准确率门槛之上，另需 `human_review` 或 `calibrated_rubric` |
| 解禁动作 | 仅当 `explicit_authorize=true` **且**门槛全过，门禁报告才可输出 claim=true；**禁止**静默抬升 |
| 入口 | `evaluate_l5_claims_gate` / `POST /evaluation/claims-gate` |

---

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

- Agent：优先读 `config.eval_profile`；`AgentManager` 加载时也会把 AGENT.md **顶层** `eval_profile` 注入 `config`（与写在 `config:` 下等价）。缺省时 `resolve_agent_eval_profile` 可用 skills/tools **子串 hint** 推导，但必须 `profile_source=derived_hints` 并遵守 **§0.7**（建议选题，不得单独驱动 N/A / 静默漏测）；禁止 `if agent_id ==`。  
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

### 6.1 维度聚合规则（混合态 · 强制）

**适用态定义（锁定）**：适用态仅包括 `pass` / `fail` / `untested` / `inconclusive`；**`not_applicable` 不属于适用态**。  
（工程扩展 `warn` / `missing` 若出现，按适用侧参与聚合，不得当作 N/A。）

维度由所属用例/切片状态聚合。**优先级（高→低）**：

1. 无任何所属用例 / 覆盖集为空（**零样本 / 零覆盖**）→ `untested`（不得标 `pass`，也不得静默省略该维当通过；**零覆盖 ≠ `not_applicable`**）  
2. 存在适用态且含 `fail` → `fail`  
3. 无 fail，存在适用态且含 `inconclusive` → `inconclusive`  
4. 无 fail/inconclusive，存在适用态且含 `untested` → **`untested`（不完整覆盖 ≠ 通过）**  
5. **存在至少一个适用用例，且所有适用用例均为 `pass`，其余用例均为 `not_applicable`** → `pass`  
6. **没有任何适用用例**（全部为 `not_applicable`）→ `not_applicable`（**禁止**把「没有适用题」读成通过）

| 混合 | 维状态 | 说明 |
|------|--------|------|
| `pass` + `untested` | **`untested`** | 不完整覆盖不得聚合成通过 |
| `pass` + `not_applicable` | `pass` | N/A 不稀释已适用通过 |
| `untested` + `not_applicable` | `untested` | 仍有适用未测 |
| 仅 `not_applicable` | `not_applicable` | 无适用用例 |
| 零覆盖用例 | `untested` | 无样本 ≠ N/A ≠ pass |

- **综合「不通过」** 仅由 `fail`（及安全硬门槛 veto）驱动；不得因大量 `untested`/`not_applicable` 单独判「不通过」。  
- **综合「通过 / 可宣称」** 不得由含 `untested` 的不完整覆盖推出；报告必须分列计数。  
- **工程复合分**（若仍用 legacy_7dim）：`not_applicable` **不得**填满分；`untested`/`inconclusive` 按已文档化的 missing_fill（中性占位）并进 `filled_keys`；硬门槛 veto 单独否决。细则变更须同步 formal report `score_policy`。  
- 安全硬门槛：`veto=true` → 发布讨论否决；与平均分正交。  
- 实现锚点：前端 `mergeMatrixStatuses` 与上表对齐（含 `pass+untested`→`untested`）。

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
| `runtime_tier` | **顾问**实际执行面（编译期）；执行后以 Runtime Tiers 重标注为准 |
| `target_runtime` | 主目标交付形态（可与实际不同） |
| `runtime_parts[]` | **仅 `system` / 多执行面**：每子任务 `{sub_id, runtime_tier, target_runtime, runner_id?, result}`；见 §10.1 |
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

**接线（formal `v1.14`）**：`buildObjectContractDisclosure` → 报告 `object_contract` + Markdown §2.1 + EvalFullReportPanel「1.1」；含 `plan_ids`、三包覆盖、MatchReport 入选/排除、失败归因粗分、**`claims_gate` check-only**（`explicit_authorize=false` → claim 恒 false）；维有 `untested` 时综合结论至多「有条件通过」；`runtime_parts` 入 meta。

---

## 9. 动态生成题（候选通道）

| 允许 | 禁止 |
|------|------|
| 按契约生成**候选**用例 → 人工/门禁审核 → 写入版本化集 | 每次 live 即时生成并直接进可比回归 |
| 生成题标记 `provenance=generated` + `locked_version` | 无版本锁定却对比历史分数 |
| 默认 `accuracy_claim=false` | 生成题自动抬升 accuracy |

---

## 10. 对象类型适配器（实现边界）

> **权威**：下表是入口摘要；`runtime_tier` / `execution_mode` / `runtime_claim` 的完整判定以 [`eval-exam-runtime-tiers.md`](./eval-exam-runtime-tiers.md) **v1.4** §7 / §7.1 为准。相对 v1.2：Skill quality ≠ 一律 `fixture`；离线 Pi / `runs_eval` ≠ `runtime_tier=pi`。

| object_type | 典型 `target_runtime` | 实际 `runtime_tier`（按行为） | `execution_mode` 等 | 备注 |
|-------------|----------------------|------------------------------|---------------------|------|
| `agent` | `workspace_execute` | live→`workspace_execute`；dry→`fixture` | — | 现状主路径 |
| `api` / 外部对话 | `external_pull` | live pull→`external_pull`；dry→`fixture` | — | external contract |
| `generated_app` | `pi` | **仅** live Pi CLI 成功→`pi`；offline / `runs_eval`→`fixture` | — | `target_runtime` 可仍为 `pi`；`runtime_claim=false` 当未进宿主 |
| `skill` | `core_skill_execute` | **quality**（skill_manager 已调）→`core_skill_execute`；**trigger**（仅路由）→`fixture` | `skill_manager_quality` / `skill_trigger_*` | 不得冒充 agent workspace；`core_skill_execute` **是** Runtime Tiers v1.3 合法档，不是五档外发明 |
| `prompt` | `fixture` / `prompt_execute` | Plan dry/live→实际 `fixture`（`execution_mode=prompt_plan_*`）；页面链另计 | `prompt_plan_dry` / `prompt_plan_llm` | **分列**：Plan `prompt-plan-exam`≈L3–L4；页面 `prompt_eval`≈L3–L4。禁止合并评级 |
| `workflow` | `workspace_execute` | Plan→实际 `fixture`（`workflow_plan_*`） | `workflow_plan_dry` / `workflow_plan_llm` | **L3–L4** Plan exam；≠ 真实 pipeline 宿主 |
| `model` | `fixture` / `model_generate` | Plan→实际 `fixture`（`model_plan_*`） | `model_plan_dry` / `model_plan_llm` | **L3–L4** Plan exam；≠ 模型榜 |
| `dataset` | `fixture` | Plan→`fixture`（`dataset_plan_assert`） | `dataset_plan_assert` | **L3–L4** 夹具表断言；**≠ KB 样本路径** |
| `system` | 组合声明 | 子任务自带实际 tier；汇总见 §10.1 / `system-plan-exam` | 各 `execution_mode` | **L3–L4** 组合入口；异质不压档 |

**匹配分层（pack）≠ 完成度**：`core`/`capability`/`special` 是用例适用语义；draft 登记多项 ≠「三包产品已齐」。详见 §0.6。

### 10.1 系统组合 / 多执行面归档（强制）

当一次评测含多个实际执行面（`system`，或报告聚合多个入口）：

| 规则 | 要求 |
|------|------|
| 子任务必留痕 | 顶层报告保存 `runtime_parts[]`：每项含 `sub_id`、`runtime_tier`、`target_runtime`、可选 `runner_id`/`execution_mode`、该子结果 |
| 顶层单值 | **仅当**所有子任务实际 `runtime_tier` **相同**时，顶层可写该单值；否则顶层 **`runtime_tier` 省略或显式 `mixed`**（若实现采用 `mixed`，须在 Runtime Tiers 登记为**非执行档元标记**，不得当作真实宿主） |
| 禁止 | 把 `workspace_execute` + `fixture` + `pi` 等压成某一个「代表性」tier |
| claim | 顶层 `runtime_claim` 仅可对「各 parts 均允许 claim 且 tier 一致」为 true；异质时 false + reason 指向 parts |

新对象类型：契约+匹配（L2）→ 题卷+oracle+**Runner 挂载**（L3）→ 运行证据（L4）→ 统计/充分性门槛（L5）；禁止只加按钮不改 MatchReport，禁止无 Runner 宣称 L3。

---

## 11. 实施阶段（设计锁定；开工另批）

| 阶段 | 交付 | 验收 |
|------|------|------|
| **P0** | `eval.target_contract.v1` + `applicability_draft.json` + MatchReport + `POST /evaluation/match-cases`；exam 响应挂载 advisory 报告 | ✅ 单测可解释入选/不适用；high_risk refuse_or_handoff；**不**改执行选题 |
| **P1** | 报告/矩阵五态含 `not_applicable`；formal `v1.11`；MatchReport 排除卷→维 N/A | ✅ 不计失败；与 untested 分列；旧「未测/不适用」混称保留兼容 |
| **P2** | `compile_evaluation_plan` + `POST /evaluation/compile-plan`；冒烟按 Plan 跳过 N/A/专项未测 | ✅ 默认 core+匹配 capability；special 需 purpose 或 include_special；本地冒烟 purpose 含 safety/reliability |
| **P3** | `object_adapters` + 类型默认用例模板；**skill/api/generated_app（及 Agent）** 挂载同一 Plan 执行入口 | ✅ 同一 `eval.evaluation_plan.v1`；agent 卷对 skill 标 N/A；**不等于** prompt/workflow/model/dataset 已达同等执行成熟度 |

**本文件状态 = v1.0 字段语义锁定**：与 Runtime Tiers v1.4 交叉验收通过；`mergeMatrixStatuses` / 正式报告综合结论遵循 §6.1（含 untested→有条件通过）；`summarize_runtime_parts` 已接线。框架 P0–P3 已接线；**对象级可跑成熟度仍以 §0.6 / §0.8 为准，不得一概而论。**

---

## 12. 变更规则

1. 改匹配语义、五态或 pack 定义 → 升本文版本 + formal report / attributable 同步。  
2. 新增 `object_type` 或 `oracle.type` → 改 §2.2 / §5 并登记 CAPABILITIES。  
3. 与 `runtime_tier` / 报告侧 `target_runtime` 冲突时：**以 runtime-tiers 文档为实际/目标归档权威**；本契约只定义对象声明的 `target_runtime[]` 与选题匹配。  
4. 宣称「已按能力画像评测」前：须有 MatchReport 落盘证据与非测试调用方。

---

## 13. 一句话

**统一评测流程与报告契约：不同对象用适用的用例、运行时和判分器；公共指标可比较；未测与不适用必须诚实可见，不能靠筛题或刷绿假装充分。**
