# Eval 能力驱动 Case Pack 设计

> **类型**：架构设计 / 题库与评测方案  
> **版本**：v0.2.5 · 2026-11-08  
> **状态**：**Accepted（§6.1 齐 · ADR Accepted；实施另开变更单；v0.2.5）**  
> **范围**：先 Agent（参考实现）；Subject 可扩展，**方法不得混入 object_type**；统一编排与治理，不统一题面；不包含业务验收  
> **诚实锁**：不打开 `accuracy_claim`；生成题默认不可 claim；禁止运行时随机出题当金标；G2b/Arena 仍走独立人工协议  
> **关联**：[`eval-case-pack-factory.md`](./eval-case-pack-factory.md) · [`CAPABILITY_ID_MAP_V1.md`](./CAPABILITY_ID_MAP_V1.md) · [`CASE_TEST_PURPOSE_SCHEMA_V1.md`](./CASE_TEST_PURPOSE_SCHEMA_V1.md) · [`SUITE_PROFILE_SCHEMA_V1.md`](./SUITE_PROFILE_SCHEMA_V1.md) · [`ADR-EVAL-CAPABILITY-CASE-PACK-V1.md`](../decisions/ADR-EVAL-CAPABILITY-CASE-PACK-V1.md)

---

## 0. 一句话

**用“能力矩阵”定义测什么，用“Case Pack”组织题目，用“Suite Profile”决定这次测多少，用 `sample_manifest` 锁定实际执行，用证据门禁决定能说什么。**

不是把 `eval_sets/*.json` 从 6 题灌到 300 题。

---

## 1. 背景与现状

### 1.1 现有链路

```text
目标契约 → Plan 选 set_id → load_eval_set → 整卷 tasks
          → runner 逐题 → 词面/规则 oracle → 报告
```

| 项 | 现状 |
|---|---|
| 默认卷 | Agent 6 卷：normal / missing_info / tool_failure / noise / high_risk / multi_turn |
| 题量 | 每卷 1–3 题；全开约 10 题 |
| Plan | 已出现 v2 / `sample_manifest` 预览；实现以代码为准 |
| 适用性 | 卷级为主；#618 已约束 `derived_hints` 不得硬 N/A |
| 判分 | 多数 `must_contain` / `must_contain_any` |
| 独立基准 | G2b-100、Arena、S1、calibration 不走本 Plan 出题链 |

### 1.2 真正的问题

| 问题 | 后果 |
|---|---|
| 只有固定卷 | 覆盖天花板低 |
| 卷级匹配 | 一题不适用会牵连整卷 |
| 无能力覆盖表 | 不知道“漏了什么” |
| 题目无测试目的 | 人审只能凭感觉 |
| 无题级 manifest | 无法审计“这次跑了哪几题” |
| 无分层 Profile | Smoke 和 Benchmark 混在一起 |
| 扩题无工厂 | 手改 JSON，易污染基准 |

### 1.3 已有基础

- Case Pack P0–P3.1：registry/hash/expand/bump/holdout、mutation/trace、LLM 候选、difficulty/judge 工单；
- Plan v2 预览已显示卷/题/步骤、manifest hash、fingerprint；
- #618 已修 `derived_hints` 不得硬 N/A；
- G2b/Arena 独立，不会被本方案吞并。

**本设计不重写这些能力，只补齐“能力矩阵 + 测试目的 + Profile 组卷 + 覆盖闭环”。**

---

## 2. 目标与非目标

### 2.1 目标

1. 以**能力**为主键组织题目，而不是以“卷”为主键。
2. 每个题目必须能明确回答：测什么、什么算失败、不测什么。
3. 同一 Case Bank 支持 Smoke / Regression / Benchmark 三种跑法。
4. 生成器可以产候选，但必须人审、冻结、版本化。
5. 每次运行输出 `sample_manifest`，题级可复现。
6. 未测能力显式 `unknown`，不算通过。
7. 先覆盖 Agent 的通用能力，不接业务场景。

### 2.2 非目标

- 不做业务验收 / 客户数据 / 生产认证；
- 不做运行时随机出题；
- 不让 LLM 生成的题直接当 gold；
- 不用题数冒充完整性；
- 不替代 G2b/Arena 人工基准；
- 不在本阶段接 live skill tools / microVM。

---

## 3. 设计原则

1. **能力优先**：先定义能力，再写题。
2. **一个题库，多套 Profile**：不复制四套题。
3. **测试目的与题干分离**：模型只看 `prompt`；审核人看 `test_purpose`。
4. **生成只产候选**：人审 + oracle + 冻结后才可用。
5. **Manifest 是唯一执行事实**：`selected_cases` 只是摘要。
6. **Unknown 不是 Pass**：没测的能力必须显式标出。
7. **Claim 独立**：Profile 选档不自动打开 accuracy/security claim。

---

## 4. 能力模型

### 4.1 Capability Registry

每个对象类型维护一份能力表：

```json
{
  "capability_id": "tool_selection",
  "object_types": ["agent"],
  "definition": "根据任务选择正确工具，不选禁止工具",
  "observable": ["tool_name", "tool_args", "tool_order"],
  "oracle_types": ["tool_trace"],
  "environment": ["tool"],
  "min_cases": {"smoke": 1, "regression": 5, "benchmark": 8},
  "in_scope": true
}
```

### 4.2 Agent 能力矩阵 v1（canonical_id）

| ID | canonical_id | 能力 | 可观测信号 | 典型 oracle | 环境 |
|---|---|---|---|---|---|
| A1 | `task_completion` | 任务理解与完成 | 最终答案/产物 | rule/gold | 文本 |
| A2 | `planning` | 计划与分解 | 步骤序列 | trace rubric | 文本 |
| A3 | `tool_selection` | 工具选择 | 工具名/顺序 | expected/forbidden tools | 工具 |
| A4 | `tool_args` | 工具参数正确性 | 参数 schema | schema/规则 | 工具 |
| A5 | `tool_result_use` | 工具结果使用 | 后续回答 | rubric | 工具 |
| A6 | `error_recovery` | 错误检测与恢复 | 失败后行为 | trace rubric | 工具/注入 |
| A7 | `safety` | 安全/拒绝/转交 | 是否确认/拒绝 | safety rule | 权限 |
| A8 | `multi_turn_memory` | 多轮记忆 | 跨轮引用 | session rubric | Session |
| A9 | `long_context` | 长上下文/检索 | 关键事实保留 | gold/claims | 长输入 |
| A10 | `robustness` | 鲁棒性/抗干扰 | 噪声下表现 | 对比 rubric | 文本 |
| A11 | `efficiency` | 效率/成本 | 步骤/token/延迟 | 阈值 | 文本/工具 |
| A12 | `observability` | 可观测性 | trace 完整度 | schema | 全部 |
| A13 | `clarification` | 缺信息追问/澄清 | 是否追问/瞎编 | rule/rubric | 文本 |

**canonical_id 是覆盖报表与 Profile 配额的唯一主键。**

### 4.2.1 Legacy ↔ Canonical 对照表

**权威冻结稿**：[`CAPABILITY_ID_MAP_V1.md`](./CAPABILITY_ID_MAP_V1.md)（含 `clarify_or_ask → clarification`、A13、全量 legacy）。  
本节仅作索引；冲突以冻结稿为准。

### 4.2.2 v1 / v1.1 可测能力子集 · 签字页

#### v1（历史 Frozen · `SIGNED v1_measurable_subset` · 2026-11-08）

文本可观测子集：**A1 / A2 / A6 / A7 / A10 / A11 / A12 / A13**。  
当时 A3–A5/A8/A9 强制 `unknown`（无 mock/session/long-context 执行链）。

#### v1.1（本页现行 · `SIGNED v1_1_measurable_subset`）

在 **mock tool harness ≠ live tools**、**scripted session**、**long_context fixtures** 就绪后升域。  
`claim_eligible` / `accuracy_claim` / Certification **仍为 false**；禁止把 mock 证据写成 live/Certification。

| 能力 | v1.1 可测？ | Profile 默认 | 说明 |
|---|---|---|---|
| A1 `task_completion` | ✅ | in_scope | 文本可测 |
| A2 `planning` | ✅（limited） | in_scope | 仅文本 trace / 步骤措辞 |
| A3 `tool_selection` | ✅（mock） | in_scope | mock catalog + scripted_tool_calls；**≠ live** |
| A4 `tool_args` | ✅（mock） | in_scope | args schema / 规则机判；**≠ live** |
| A5 `tool_result_use` | ✅（mock） | in_scope | result→answer rubric；**≠ live** |
| A6 `error_recovery` | ✅（limited） | in_scope | **只测失败措辞/定位，不测真实工具恢复** |
| A7 `safety` | ✅ | in_scope | 权限/确认文本可测 |
| A8 `multi_turn_memory` | ✅（session） | in_scope | session_group atomic + session_runner |
| A9 `long_context` | ✅（fixture） | in_scope | must_retain_claims / generator fixtures |
| A10 `robustness` | ✅ | in_scope | 文本噪声可测 |
| A11 `efficiency` | ✅ | in_scope | 有审计/步骤计数 |
| A12 `observability` | ✅ | in_scope | trace schema |
| A13 `clarification` | ✅ | in_scope | 缺信息追问文本可测 |

**v1.1 声明范围 =「Agent 文本 + mock/session/fixture 可测子集」≠「Agent 全能力 / live tools / Certification」。**  
可测集合：**A1–A13 全部**（`V1_OUT_OF_SCOPE` 为空）。  
升域工程：[`eval-agent-tool-session-inscope.md`](./eval-agent-tool-session-inscope.md)（T0–T3 Done）。

#### §4.2.2 签字栏

| 角色 | 勾选 | 签字 | 日期 |
|------|:----:|------|------|
| 评测方法负责人 | v1 文本子集 | `SIGNED v1_measurable_subset` · 朱向群 | 2026-11-08 |
| 评测方法负责人 | v1.1 升域（mock/session/fixture） | `SIGNED v1_1_measurable_subset` · 朱向群 | 2026-11-08 |
| 工程负责人 | `V1_IN_SCOPE` / Profile 配额与上表一致；claim 关闭 | `SIGNED v1_1_measurable_subset` · 朱向群 | 2026-11-08 |

**已签字：v1.1 可测子集 Frozen；A3–A5/A8/A9 可标工程 `covered`（mock/session/fixture），不得宣称 live 或 Certification。**

### 4.3 其他对象

| 对象 | 能力 |
|---|---|
| Prompt | 指令遵循、格式/schema、正确性、grounding、安全/拒答、鲁棒性、效率 |
| KB/RAG | 检索召回、上下文精度、faithfulness、引用、拒答、延迟 |
| Code Review | 缺陷召回、P0、误报、定位、可操作性、安全 |
| Session | 目标保持、冲突处理、摘要保真、截断降级、长程回忆 |

### 4.4 覆盖状态

每个能力在每次运行中只能是：

```text
covered      已测，有证据
unknown      未测 / 无 case / 无环境
not_applicable 对象不具备条件
failed       测了但失败
```

**不允许把 `unknown` 写成 pass。**

---

## 5. 用例模型

### 5.1 `EvalCase` 必填字段

```json
{
  "case_id": "agent.tool_failure.001",
  "object_types": ["agent"],
  "capabilities": ["error_recovery"],
  "secondary_capabilities": ["observability"],
  "test_purpose": {},
  "prompt": "...",
  "fixtures": {},
  "env": {"tools": [], "sandbox": "local", "permissions": []},
  "oracle": {},
  "expected_tools": [],
  "forbidden_tools": [],
  "difficulty": "medium",
  "tags": ["agent", "tool"],
  "session_group": null,
  "holdout": false,
  "provenance": {},
  "review": {},
  "hash": "sha256:..."
}
```

### 5.2 `test_purpose` 必填

```json
{
  "summary": "验证工具失败后，Agent 是否明确报告失败并定位，而不是编造成功",
  "why_this_case": "真实工具失败时最容易出现假成功",
  "expected_behavior": [
    "明确说明工具失败或无法完成",
    "指出失败发生在哪一步/哪个工具"
  ],
  "failure_signals": [
    "声称任务成功",
    "编造工具返回结果",
    "把空结果当成有效结果"
  ],
  "not_testing": [
    "不测试工具本身的成功率",
    "不测试规划质量"
  ],
  "oracle_rationale": "本卷无 expected_tools，只按失败报告措辞与定位判分"
}
```

### 5.3 三个视图

| 视图 | 可见内容 |
|---|---|
| **模型视图** | 仅 `prompt` + 允许的工具/上下文 |
| **审核视图** | `test_purpose` + `prompt` + `rubric/oracle` + expected/failure |
| **报告视图** | `test_purpose` + 结果 + failure + `not_testing` |

**模型绝不能看到 `test_purpose`、`rubric`、`failure_signals`。**

### 5.4 人审检查表

- [ ] summary 是否具体、可证伪？
- [ ] prompt 是否真的制造了目标条件？
- [ ] expected_behavior 是否可观察？
- [ ] failure_signals 是否覆盖主要错误？
- [ ] oracle 是否能区分通过/失败？
- [ ] not_testing 是否写清边界？
- [ ] prompt 是否泄漏答案/评分标准？
- [ ] capabilities 是否与 purpose 一致？
- [ ] 是否有 trace/证据路径？
- [ ] 难度/标签/来源是否合理？

审核结论：

```text
purpose_ok
purpose_mismatch
oracle_mismatch
prompt_leak
not_testable
needs_edit
```

`purpose_mismatch` / `not_testable` 必须打回，不能冻结。

---

## 6. Case Pack / Profile / Manifest

### 6.1 `CasePack`

```json
{
  "schema": "eval.case_pack.v1",
  "pack_id": "agent.capability",
  "version": "0.1.0",
  "kind": "curated",
  "status": "frozen",
  "claim_eligible": false,
  "scope": "workspace",
  "workspace_id": "ws-a",
  "object_types": ["agent"],
  "cases": [],
  "hash": "sha256:..."
}
```

### 6.2 `SuiteProfile`

```json
{
  "profile_id": "agent.regression.v1",
  "object_type": "agent",
  "pack_id": "agent.capability",
  "version": "0.1.0",
  "quotas": {
    "task_completion": 8,
    "clarification": 8,
    "error_recovery": 8,
    "safety": 8,
    "robustness": 8,
    "multi_turn_memory": 5
  },
  "notes": "v1: tool_selection/tool_args/tool_result_use 默认不入配额（无工具环境→unknown）",
  "strategy": "stratified",
  "claim_eligible": false
}
```

### 6.3 `SampleManifest`

```json
{
  "plan_id": "plan-...",
  "profile_id": "agent.regression.v1",
  "pack_id": "agent.capability",
  "pack_version": "0.1.0",
  "scope": "workspace",
  "workspace_id": "ws-a",
  "seed": 7,
  "cases": [
    {"case_id": "agent.tool_failure.001", "hash": "..."}
  ],
  "manifest_hash": "sha256:...",
  "execution_fingerprint": "exec-..."
}
```

### 6.4 Profile 是一套跑法，不是一套题

| Profile | 选题策略 | 目标 | 参考规模 |
|---|---|---|---|
| Smoke | 每核心能力 1–2 题 | 发现明显坏 | 10–20 |
| Regression | 每能力 5–10 题 | 发现退化 | 40–80 |
| Benchmark | 分层 + holdout + CI | 估计表现 | 100+ |
| Certification | 外部冻结快照 + 审计 | 对外认证 | 300+，非硬标准 |

**题数是结果，不是定义。**

- 40 题覆盖 8 能力、稳定可复现 → Regression；
- 100 题全是简单题 → 仍然只是大 Smoke；
- 300 题无外部审计 → 不是 Certification。

---

## 7. Case Factory

### 7.1 四种生成器

| 生成器 | 用途 | 自动 | 约束 |
|---|---|---|---|
| 模板参数化 | 通用能力题 | ✅ | 槽位枚举、seed |
| 变异 | 鲁棒/安全/恢复 | ✅ | 基于已审种子 |
| Trace 挖掘 | 真实行为 | ⚠️ | 脱敏、权限、人审 |
| LLM 候选 | 扩池 | ⚠️ | 只产候选，不当 gold |

### 7.2 流水线

```text
能力缺口
  → generate
  → validate
  → dedupe
  → oracle 可判定性检查
  → human review
  → freeze
```

### 7.3 状态机

```text
draft -> validated -> reviewed -> frozen -> deprecated
```

- `frozen` 不可修改，只能新版本；
- `generated` 默认 `claim_eligible=false`；
- `reviewed` 只能探索，不能 claim；
- `holdout` 不参与调参。

### 7.4 LLM 出题红线

- 不能直接当 gold；
- 不能和 judge 用同一模型；
- 不能看答案/泄漏；
- 必须人审；
- 只能进 L3，不能直接进 L1。

---

## 8. Plan 与覆盖

### 8.1 Plan 输入

```json
{
  "object_type": "agent",
  "profile_id": "agent.regression.v1",
  "capability_quotas": {
    "tool_selection": 8,
    "error_recovery": 8
  },
  "sample_n": 40,
  "seed": 7,
  "strategy": "stratified"
}
```

### 8.2 Plan 输出

- `selected_cases`：兼容投影；
- `sample_manifest`：唯一执行清单；
- `coverage`：每能力实际题数；
- `gaps`：未覆盖能力；
- `manifest_hash`；
- `execution_fingerprint`。

### 8.3 规则

- manifest 为空 → fail closed；
- hash 不匹配 → fail closed；
- 缺能力 → `unknown`，不是 pass；
- 特殊能力需 profile 显式开启；
- 不同 profile 分数不可直接比较。

### 8.4 覆盖报告

```text
capability        cases  reviewed  selected  gap
task_completion     12       12         8      0
tool_selection      10       10         8      0
error_recovery       8        6         4      2
multi_turn_memory    6        0         0      6
```

### 8.5 “完整”的判定

一个 Profile 算能力完整，当且仅当：

1. 所有 in-scope 能力都有定义；
2. 每能力达到最低 case 数；
3. 每 case 有可判定 oracle；
4. 所有选中 case 已 frozen/reviewed；
5. manifest 覆盖配额；
6. 未测能力明确 `unknown`；
7. 报告披露样本量/CI/限制。

**“完整”是相对声明范围，不是绝对所有任务。**

---

## 9. Runner / Oracle / Judge

### 9.1 Runner

- 只执行 `sample_manifest`；
- 校验 case hash / pack version；
- 按 `session_group` 分组；
- 环境适配：文本 / 工具 / 记忆 / 长上下文。

### 9.2 Oracle

| 类型 | 自动化 | 适用 |
|---|---|---|
| exact/rule | ✅ | 格式、must_contain |
| tool_trace | ✅ | 工具选择/参数 |
| trace rubric | ⚠️ | 计划/恢复 |
| LLM judge | ⚠️ | 语义质量，需校准 |
| human | ⚠️ | 主观/高风险 |

### 9.3 Judge 校准

- judge vs 人工一致率；
- 误报/漏报；
- 分歧仲裁；
- 校准前后对比；
- 未校准的 judge 只能 report-only。

---

## 10. 存储 / API / UI

### 10.1 存储（权威路径 · 与 Case Pack 工厂一致）

**禁止**使用 `core/engine/eval_packs/` 作为运行时权威路径（那会形成双源题库）。  
权威与现有 `case_pack_registry.py` 一致：

```text
$AIPLAT_HOME/eval_packs/global/
  registry.json
  packs/{pack_id}/{version}/pack.json

$AIPLAT_HOME/workspaces/{workspace_id}/eval_packs/
  registry.json
  packs/{pack_id}/{version}/pack.json

$AIPLAT_HOME/tenants/{tenant_id}/eval_packs/
  registry.json
  packs/{pack_id}/{version}/pack.json
```

| scope | 路径 | 写权限 | 默认何时用 |
|---|---|---|---|
| `global` | `$AIPLAT_HOME/eval_packs/global` | P0 只读；平台发布角色才能发新版本 | **仅**内置/官方导入 |
| `workspace` | `$AIPLAT_HOME/workspaces/{id}/eval_packs` | 同 workspace ACL | **用户新建默认** |
| `tenant` | `$AIPLAT_HOME/tenants/{id}/eval_packs` | 同 tenant ACL | **显式开启**；P0 不默认 |

#### Scope 按创建来源（禁止「全局默认 global」）

| 创建来源 | 默认 scope |
|---|---|
| 内置 / 官方导入 | `global` |
| 用户新建 pack | `workspace` |
| 租户共享 | `tenant`（必须显式传 + tenant admin） |
| 来源无法判定 | **400 `scope_required`**，禁止静默推断 |

跨 scope 引用：

| 引用方 | 可引用 |
|---|---|
| workspace | 自己的 workspace + `global` 只读 |
| tenant | 同 tenant + `global` 只读 |
| global | 不得引用用户 workspace/tenant pack |

- **禁止跨 workspace 引用**；
- 改 scope = clone + 新 version + 新 hash（禁止原地改）；升 global 需平台审核；
- frozen 只能 deprecate；删除前检查 Profile/manifest 引用；
- **manifest / report 必须带 `scope`（及 workspace_id/tenant_id）**，否则无法审计「全局基准 vs 工作区私有」；
- 仓库内 `core/engine/eval_sets/*.json` 仍是**旧卷种子/映射源**，不是 Case Pack 权威存储；
- registry 原子写 + 锁。

### 10.2 API（经 CoreFacade）

- `eval_capability_list(object_type)`
- `eval_case_pack_list/get/freeze`
- `eval_case_factory_generate/validate`
- `eval_case_pack_coverage`
- `eval_plan_compile_profile`

### 10.3 UI

- 能力矩阵；
- Case Pack 列表；
- 生成候选/审核队列；
- **测试目的卡**（purpose / expected / failure / not testing）；
- Coverage 热力图；
- Profile 选择（Smoke/Regression/Benchmark）；
- Manifest 查看；
- 结果按能力切片；
- `unknown` 明确显示。

---

## 11. 治理与证据

- `frozen` 不可变，只能 bump version；
- `generated` 永远 `claim_eligible=false`；
- 只有 `frozen + human_reviewed` 才可进入 claim 候选；
- G2b/Arena 仍独立，不被本方案吞并；
- 报告显示：
  - `pack_id/version`
  - `profile_id`
  - `manifest_hash`
  - `execution_fingerprint`
  - `claim_eligible`
  - `unknown` / `not_applicable`
- 任何 sample/manifest 失败 → fail closed，不回退整包。

---

## 12. 迁移与兼容

### 第 1 步：旧卷映射 + 能力 ID alias

- `default/normal` → `agent.default.normal@1.0.0`（附录对齐 factory Plan）；
- 挂上 §4.2.1 legacy→canonical 映射；
- 旧 API 保留；结果 bit 兼容。

### 第 2 步：能力标注（仅 v1 可测子集）

- 给现有 case 加 `capabilities`（canonical）；
- A3–A5 无工具环境 → `unknown` / `in_scope=false`；
- 生成 coverage baseline + gap。

### 第 3 步：Regression 内容（优先于再造工厂）

- **30–50 题人审冻结**（每可测能力 5–10）；
- 建立 `agent.regression.v1` Profile + pack；
- **不**把 Smoke 6 题膨胀成 100 题。

### 第 4 步：Profile 编译 + UI 选档

- Plan 支持 `profile_id`；
- Smoke / Regression / Benchmark 选档；
- manifest 落盘；覆盖热力图。

### 第 5 步：复用现有工厂做覆盖驱动补题

- 模板 / 变异 / trace / LLM 候选（**已有 P2–P3.1，不重写**）；
- 人审 / 冻结 / holdout；
- 按 gap 补题。

### 第 6 步：校准

- judge vs 人工；
- 置信区间；
- benchmark/claim 门。

---

## 13. 路线图与验收（内容 + Profile 优先）

> 工厂 mutation/trace/LLM/difficulty/judge 工单已在 Case Pack P2–P3.1 落地。  
> **本路线图不再重复“再造工厂”，P1 核心是题库内容。**

| 阶段 | 内容 | 周期 |
|---|---|---:|
| D0 | 能力矩阵 + `test_purpose`/Profile schema + ADR（含对照表/可测子集） | 1–2 周 |
| **P0** | 能力矩阵落地 + `test_purpose` schema + 旧卷映射 + legacy alias | 2–3 周 |
| **P1** | **30–50 题 Regression 内容 + 人审冻结**（v1 可测子集） | 4–6 周 |
| **P2** | **Profile 编译 + UI 选档 + manifest/coverage** | 3–4 周 |
| **P3** | **复用现有工厂**做覆盖驱动补题（模板/变异/trace/LLM） | 3–4 周 |
| **P4** | judge 校准 + holdout + Benchmark | 4–8 周 |
| P5 | Certification 外部审计 | 另立项 |
| **P6** | **A3–A5 / A8 / A9 升 in-scope**（mock tools + session + long-context） | **[另立项](./eval-agent-tool-session-inscope.md)** |

### 验收指标

| 指标 | 目标 |
|---|---|
| 能力覆盖 | in-scope 能力 100% 有 case |
| 每能力样本 | Regression ≥5，Benchmark ≥8 |
| 审核率 | frozen 前 100% 人审 |
| 重复率 | 生成候选去重后 <10% |
| 可复现 | 同 profile/seed/manifest 字节一致 |
| 判分 | judge-human agreement 达标 |
| 回归发现 | 已知退化能被 Regression 捕获 |
| Claim | generated 恒 false；frozen 也需独立门 |

---

## 14. 风险与不做

| 风险 | 缓解 |
|---|---|
| 生成题质量低 | 人审 + oracle 校验 |
| LLM 自证 | 禁同模 judge；人审 |
| 基准污染 | L1/L2/L3 + holdout |
| 题多但判分弱 | 先校准 judge，再扩题 |
| 运行成本高 | Profile 采样，不全跑 |
| 工具/记忆不可测 | 明确 `unknown`，不假装 |
| 范围膨胀 | 先 Agent，后其他对象 |

**不做：**

- 运行时随机出题；
- LLM 题直接进 claim；
- 用题数冒充完整性；
- 用 Smoke 分数做上线认证；
- 无环境却宣称工具/记忆已测。

---

## 15. 通用方法：Subject × Capability × Method × Evidence

> **通用的是评测框架；不是通用题目；也不是把“方法/维度”硬塞进 `object_type`。**  
> 四元组：`Subject（被测物） × Capability（测什么） × Method（怎么测） × Evidence（证据）`。

### 15.1 当前代码中的 `object_type`（9 类）

权威：`core/apps/eval/service/target_contract.py` → `OBJECT_TYPES`：

```text
agent | prompt | skill | workflow | model | api | generated_app | dataset | system
```

**下列不是（或尚未成为）一等 `object_type`：**

| 名称 | 当前归属 | 分类 |
|------|----------|------|
| KB / RAG | 独立 KB eval 路径 | Subject 候选（建议纳入） |
| Code Review | code-review-gold runner | Subject 候选（建议纳入） |
| Session | session_eval | 运行时 / evidence 为主；可作 Subject 候选 |
| Tool / MCP | 协议/工具 | Subject 候选（未来） |
| Multi-Agent | 组合系统 | Subject 候选（未来） |
| Arena / Preference | 人评偏好 | **Method** |
| G2b | 人工双盲基准 | **Method** |
| S1 Redteam | 攻击包 | **Method** |
| Calibration | 评估器校准 | **Method** |
| PII / 合规 / 成本 / 延迟 | 规则或指标 | **Dimension**（可跨 Subject 复用） |

> **评测对象 ≠ 评测方法 ≠ 评分维度。** Prompt/KB/Code/Session 只是示例，不是完整清单。

### 15.2 分类

**A. 可版本化产物（Artifact / Subject）** — 可挂 Target Contract + Case Pack  

| Subject | 当前 |
|---------|------|
| Agent / Skill / Prompt / Workflow / Model / API / Generated App / Dataset / System | ✅ 在 9 类 |
| KB / RAG、Code Review | ⚠️ 独立路径，建议 SubjectAdapter |
| Tool/MCP、Multi-Agent | ⚠️ 未来 Subject |

**B. 运行时对象** — 多为 evidence，不一定升 `object_type`  

Session / Conversation、Agent Run、Tool Call Trace、Deployment / Environment。

**C. Method** — 不得对象化进 `OBJECT_TYPES`  

Arena、G2b、S1、Calibration、Human Review、Static/Replay/Dynamic。

**D. Dimension** — 跨 Subject 复用  

安全、合规/PII、成本、延迟、鲁棒性、可观测性、记忆、长上下文（与能力矩阵可对齐，但不是 object_type）。

### 15.3 五层统一 · Subject 适配

```text
Target Contract → Capability Resolver → Case Selector (Profile)
        → Execution Adapter → Oracle Adapter → Evidence Normalizer → Claim Gate
```

```python
class EvalSubjectAdapter:
    subject_kind: str  # agent|prompt|kb|code_review|session|...
    def build_contract(...): ...
    def capability_catalog(...): ...
    def validate_case(...): ...
    def execute(...): ...
    def judge(...): ...
    def normalize(...): ...
```

| 统一 | 按 Subject 适配 |
|------|-----------------|
| 契约外壳 / Capability 元字段 / Case+`test_purpose` | 执行器与环境 |
| SuiteProfile / sample_manifest | oracle 形态 |
| Evidence / claim gate / fail closed | 人审清单 |

**Core 禁止 `if object_type ==` 堆业务；用 SubjectAdapter registry。**  
已有：[`eval-object-contract-and-plan.md`](./eval-object-contract-and-plan.md) + `object_adapters.py`（契约侧）。本方案补能力 Case Pack；**不另起 Plan 引擎，不把 Method 塞进 OBJECT_TYPES。**

### 15.4 落地顺序

1. **AgentAdapter**（本文件 P0–P4）参考实现；  
2. 抽出 `EvalSubjectAdapter`；  
3. Prompt / Workflow / Model（文本类，复用多）；  
4. KB/RAG → Code Review → Session；  
5. Tool/MCP / Multi-Agent；  
6. Arena / G2b / S1 **保持方法轨**；  
7. **不**为 15 种对象各写一套 Plan。

### 15.5 边界

- 无环境 → `unknown`；  
- 不同 Subject 分数不可直接比较；  
- 通用框架 ≠ 通用准确率；  
- Method 独立，不自动 claim；  
- 业务验收不在范围。

---

## 16. 结论

**能力驱动 Case Pack 的核心不是“自动生成 100 道题”，而是：**

> **能力矩阵定义“测什么”；Case Factory 生产“可审的题”；Profile 决定“这次测多少”；Manifest 保证“跑的是哪几题”；Coverage 证明“有没有漏”；Claim Gate 决定“能说什么”。**

**跨对象扩展的核心：**

> **Subject × Capability × Method × Evidence。**  
> 统一“怎么评”；Subject 用 adapter 扩展；Method（Arena/G2b/S1）不混入 `object_type`；Agent 先跑通，再逐个接入。

**§6.1 已齐 · ADR Accepted。** 开实施变更单后进入 P0（能力矩阵接线 + `test_purpose` + alias）；本文件不直接改代码。
