# Eval Agent 能力升域：A3–A5 / A8 / A9 → in-scope

> **类型**：立项 Plan（工程 + 评测方法；非 Certification）  
> **版本**：v0.1 · 2026-11-08  
> **状态**：**T0 工程契约已落地**（样例 + validate；等方法负责人 `SIGNED t0_contracts_usable` 后开 T1）· 见 [EVAL_AGENT_TOOL_SESSION_CONTRACTS_T0.md](./EVAL_AGENT_TOOL_SESSION_CONTRACTS_T0.md)  
> **触发**：`[ADR-EVAL-CAPABILITY-CASE-PACK-V1](../decisions/ADR-EVAL-CAPABILITY-CASE-PACK-V1.md)` §7 #9；v1 签字子集强制 A3–A5/A8/A9 = `unknown`  
> **关联**：`[eval-capability-driven-case-pack.md](./eval-capability-driven-case-pack.md)` §4.2.2 · `[CAPABILITY_ID_MAP_V1.md](./CAPABILITY_ID_MAP_V1.md)` · `[eval-exam-runtime-tiers.md](./eval-exam-runtime-tiers.md)` · PR #622（v1 文本子集已落地）

---

## 1. 为什么立项

v1 Agent Case Pack 只声明「**文本可观测**」能力可测：A1/A2/A6/A7/A10–A13。  
A3–A5（工具）、A8（多轮 Session）、A9（长上下文）在代码与 ADR 中为 `V1_OUT_OF_SCOPE` → 覆盖只能标 `unknown`，**禁止因写了题就标** `covered`。

当前缺口（以代码为准）：


| 缺口                     | 证据                                                                |
| ---------------------- | ----------------------------------------------------------------- |
| Agent adapter 无真实执行/判分 | `AgentSubjectAdapter.execute/judge/normalize` → `not_implemented` |
| 无评测侧工具 harness         | ADR：本阶段不接 live skill tools / microVM                              |
| Session 仅有采样契约         | `session_group` 整组入选已有；无多轮 runner                                 |
| 无长上下文 fixture 协议       | seed bank 无 `long_context` 正式卷                                    |


**结论**：需要单独立项补齐「环境 + 执行 + 证据 + 再签字」，不能在 #622 尾巴上直接改 `V1_IN_SCOPE`。

---



## 2. 目标与非目标



### 2.1 目标

1. 提供可复现的 **Mock Tool Harness**（默认）与可选 **live tool** 档（显式声明 `runtime_tier`）。
2. 提供 **Session Runner**：同 `session_group` 按 `turn_index` 串行执行，状态跨轮保留。
3. 提供 **Long-context Fixture 协议**：输入长度/噪声槽位/关键事实金标可版本化。
4. 落地 A3/A4/A5/A8/A9 的 **execute → judge → evidence**，使覆盖可从 `unknown` 升为可宣称 `covered`（仍 `accuracy_claim=false`，非 Certification）。
5. 升域前完成 **§4.2.2 再签字**（`SIGNED v1_1_measurable_subset` 或新版本号），同步改 `V1_IN_SCOPE` / Profile 配额。



### 2.2 非目标

- 不做 Certification / 外部审计（仍走 Case Pack P5 另立项）。  
- 不默认上 microVM；第一期以 **mock tools** 为主。  
- 不把 Arena / G2b / 业务验收混进 Agent capability bank。  
- 不宣称「真实生产工具恢复已测」——A6 仍保持 limited；A5 只测「结果是否进入后续回答」级证据。  
- 不在未接线 execute 时改 `in_scope=true`。

---



## 3. 能力升域条件（硬门）

每项能力升 `in_scope` 必须 **全部**满足：


| #   | 门              | 说明                                                                                                          |
| --- | -------------- | ----------------------------------------------------------------------------------------------------------- |
| G1  | 执行面真实          | `AgentSubjectAdapter.execute` 对该能力返回非 stub；`runtime_tier` ∈ {`fixture`（仅结构预检）, `workspace_execute`, …} 诚实标注 |
| G2  | Oracle 可机判或可校准 | A3/A4：expected/forbidden tools + args schema；A5：result→answer rubric；A8：session rubric；A9：gold claims       |
| G3  | Evidence 落盘    | sample_manifest + run trace（含 tool_calls / turn 边界）可复现                                                      |
| G4  | 题量下限           | smoke≥1 / regression≥5 / benchmark≥8（与现 Profile 一致）                                                         |
| G5  | 人审冻结           | 升域卷 `frozen`；`claim`/`certification_eligible` 仍 false                                                       |
| G6  | 方法再签字          | Plan §4.2.2 更新表 + ADR 附录或修订；**禁止静默改 frozenset**                                                             |


任一能力未过门 → 保持 `unknown`。

---



## 4. 分期交付



### 阶段 T0 — 契约钉死（约 1 周）


| 交付物                                                                                | 验收                                      |
| ---------------------------------------------------------------------------------- | --------------------------------------- |
| Mock tool 目录 schema（name / args_schema / deterministic result / fail modes）        | YAML/JSON 样例 + 校验测试                     |
| Session 卷字段：`session_group` + `turn_index` + `memory_probe`                        | schema 文档 Frozen                        |
| Long-context fixture：`context_tokens_est` / `noise_slots` / `must_retain_claims[]` | schema 文档 Frozen                        |
| `runtime_tier` 映射表（mock vs live）                                                   | 对齐 exam-runtime-tiers；mock ≠ live claim |


**工程完成（2026-11-08）**：契约文档 Frozen + `fixtures/mock_tools|session|long_context` 样例 + `validate_*` / `evaluate_t0_inscope_contracts` 测试绿；**未**改 `V1_IN_SCOPE`。  

**Go T1**：评测方法负责人在 [EVAL_AGENT_TOOL_SESSION_CONTRACTS_T0.md](./EVAL_AGENT_TOOL_SESSION_CONTRACTS_T0.md) §5 签字「契约可用」。

### 阶段 T1 — Mock Tool Harness + A3/A4（约 2–3 周）


| 交付物                                               | 验收                                          |
| ------------------------------------------------- | ------------------------------------------- |
| `eval` 侧 mock tool registry + 注入 agent env        | 单测：给定 case → 强制可选工具集                        |
| `execute`：收集 `tool_calls[{name,args}]`            | 非 stub；失败 fail-closed                       |
| `judge`：A3 expected/forbidden；A4 JSON-schema / 规则 | 已知正/负例各 ≥3                                  |
| Regression 卷：A3≥5、A4≥5                            | Case Editor / seed；`in_scope` 仍 false 直到 G6 |


**Go T2**：A3/A4 机判稳定（同 seed 字节一致）。

### 阶段 T2 — A5 + Session Runner（A8）（约 2–3 周）


| 交付物                                  | 验收                                           |
| ------------------------------------ | -------------------------------------------- |
| A5：工具结果注入后的回答 rubric / must_contain  | 正/负例                                         |
| Session runner：同组整卷执行；中断不半组写 covered | `assert_session_groups_intact` 仍 fail-closed |
| A8：跨轮探针题（前轮埋事实 → 后轮追问）               | regression≥5                                 |


**Go T3**：A5/A8 证据链可审计。

### 阶段 T3 — Long-context（A9）+ 升域签字（约 2–4 周）


| 交付物                                           | 验收                                 |
| --------------------------------------------- | ---------------------------------- |
| 长输入 fixture 生成器（噪声 + 关键 claim）                | 长度档可配置；CI 可用短档                     |
| A9 judge：must_retain_claims                   | regression≥5；benchmark 配额进 Profile |
| 更新 `V1_IN_SCOPE` / OUT；Profile 配额；coverage 报表 | G6 签字齐                             |
| ADR §7 #9 关闭；§4.2.2 修订为 v1.1 可测子集             | 变更单勾选                              |


**Done**：A3–A5/A8/A9 可标 `covered`（工程宣称）；**仍非** Certification。

### 可选 T4 — Live tools / microVM（另估）

仅当 mock 不足时单独立项；live 必须单独 `runtime_tier` / `runtime_claim_reason`，不得与 mock 结果混表。

---



## 5. 建议落地位置（最小改动）


| 组件                    | 建议路径                                                           | 备注                                       |
| --------------------- | -------------------------------------------------------------- | ---------------------------------------- |
| Mock tools            | `core/apps/eval/service/mock_tools/`                           | 配置驱动；禁止 harness 硬编码业务工具名列表进内核分支          |
| Session runner        | `core/apps/eval/service/session_runner.py`                     | 消费已有 `session_group`                     |
| Long-context fixtures | `workspace_seeds/eval/agent_capability/fixtures/long_context/` | seed 权威，与 Case Editor 一致                 |
| Adapter 接线            | `subject_adapter.py` AgentSubjectAdapter                       | 去掉 stub；按能力分派 method，不用 `if agent_id ==` |
| Scope 常量              | `capability_id_map.py`                                         | **仅 G6 签字后**移动 frozenset                 |


平台访问仍走 CoreFacade；新公共符号同步 `AIPLAT_CAPABILITIES.md` + `capability_registry.yaml`。

---



## 6. 与 #622 / v1 的边界


| 事项                                   | 归属                |
| ------------------------------------ | ----------------- |
| 文本子集 8×8 bank、Case Editor、Profile、工厂 | #622 / 已落地        |
| A3–A5/A8/A9 环境与升域                    | **本立项**           |
| Certification 外部审计                   | Case Pack P5，再另立项 |


#622 可合入 v1；本立项开新分支 / 新 PR，不阻塞文本子集合并。

---



## 7. Go / No-Go

**Go 开工 T0** 当且仅当：

1. 评测方法负责人确认：mock 证据可接受为 A3–A5 第一期 covered（非 live）；
2. 工程负责人确认：T1 可在不接 microVM 下完成；
3. 本文件入库（本稿）。

**No-Go / 保持 unknown**：

- 只有题目没有 execute；  
- 用最终文本答案冒充 tool_selection；  
- 未再签字就改 `V1_IN_SCOPE`。



### 签字栏


| 角色      | 勾选    | 签字  | 日期         |
| ------- | ----- | --- | ---------- |
| 评测方法负责人 | Go T0 | 朱向群 | 2026/11/08 |
| 工程负责人   | Go T0 | 朱鸿林 | 2026/11/08 |


---



## 8. 一句话

**先 mock 工具 + Session + 长上下文 fixture，再签字扩可测子集；在那之前 A3–A5/A8/A9 继续诚实标** `unknown`**。**