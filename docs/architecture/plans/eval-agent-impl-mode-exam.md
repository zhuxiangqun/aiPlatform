# Eval Agent：按实现模式实评 + 有限跨模式相对比较

> **类型**：立项 Plan（工程 + 评测方法；非 Certification）  
> **版本**：v0.1 · M0 设计单 · 2026-11-09  
> **状态**：**M0 工程完成**（种子 + 纯函数 + 契约门 + 单测绿）— 方法/工程签字后才开 M1a；ReAct / 排行不抢跑  
> **关联**：[eval-capability-driven-case-pack.md](./eval-capability-driven-case-pack.md) · [eval-exam-runtime-tiers.md](./eval-exam-runtime-tiers.md) · [eval-object-contract-and-plan.md](./eval-object-contract-and-plan.md) · [eval-agent-tool-session-inscope.md](./eval-agent-tool-session-inscope.md)

---

## 0. 一句话

**轨 A** 按 `Agent × Mode × Config` 真跑（选题并集、执行分开）；**轨 B** 只在同题、同环境、同 oracle、同模型、同 manifest 的交集上用 Pareto/CI 比较。先钉 M0，再开 M1a。

---



## 1. 目标与非目标



### 1.1 目标


| 轨   | 内容                                                 |
| --- | -------------------------------------------------- |
| A   | 识别主/次 `impl_modes` → 按模式测 `mode_core` → live 证据可审计 |
| B   | 交集卷上有限相对比较（Pareto/CI）；默认无单一 winner                 |




### 1.2 非目标

- M0 未齐就开 M1 / M3  
- 抽象「ReAct 比 RAG 好」  
- primary 一次执行吞 secondary 题  
- 无沙箱宣称 A3–A5 covered  
- 默认 Certification / 自动 `accuracy_claim`

---



## 2. 比较单位（强制）

```text
Subject = agent_id + agent_version + impl_mode + config_hash + model_fingerprint
```

排行结论只能写：「在 Agent X、配置 C、模型 M 下，mode A 在交集能力上相对 mode B …」。

---



## 3. `impl_modes` 多值语义

```yaml
impl_modes:
  primary: react
  secondary: [tool_loop]
  confidence: explicit   # explicit | derived
  source: AGENT.md       # AGENT.md | registry | config
```


| 规则    | 说明                                                              |
| ----- | --------------------------------------------------------------- |
| 显式优先  | 配置 > 派生提示                                                       |
| 派生不硬判 | `derived` 只披露，不单独开能力宣称                                          |
| 未知    | `primary=unknown`（禁止默认 react）                                   |
| 延期    | `multi_agent` / `pipeline` / `operator` → `deferred`（≠ unknown） |




### 3.1 selection union ≠ execution union（硬句）


| 层   | 语义                                                |
| --- | ------------------------------------------------- |
| 选题  | `mode_core(primary) ∪ mode_core(secondary…)`      |
| 执行  | **每个 mode 独立** create_agent / manifest / run / 证据 |
| 报告  | 按 mode **分栏**                                     |


禁止：以 primary=react 的一次 run 去跑 RAG 的 A9。

---



## 4. 矩阵五字段

权威种子：`aiPlat-core/workspace_seeds/eval/agent_capability/mode_core_capabilities.v1.yaml`


| 字段                     | 含义                                                |
| ---------------------- | ------------------------------------------------- |
| `mode_core`            | 该模式必须测                                            |
| `mode_optional`        | 可选                                                |
| `mode_not_applicable`  | N/A（≠ unknown）                                    |
| `rank_eligible`        | **case 级**资格（绑 case_id + hashes）                  |
| `environment_required` | none / tools / retrieval / session / long_context |


- `unknown` **不进分母**  
- plan_execute 的 A6 仅：`replan` / `step_conflict` / `text_recovery`（禁止 tool_failure_recovery）  
- A12 未过 **trace contract parity** 前不得 `rank_eligible`

---



## 5. `rank_fingerprint`

跨主体比较用此值，**不用**含 agent_id 的 raw `execution_fingerprint`：

```text
rank_fingerprint =
  manifest_hash + prompt_hash + oracle_hash
  + runner/judge version + model fingerprint
  + runtime_tier + runtime_parts contract
  + tools/retrieval/session contract hashes
```

排除：`subject_id` / `agent_id` / `workspace_id` / 显示名 / run 时间。

---



## 6. 交集卷与 parity

默认候选能力：A1 / A7 / A12（**仅候选，非自动合格**）。  
每个候选 case：`prompt_hash` / `oracle_hash` / `env_contract_hash` / `rank_eligible`。  
M0 parity sample：人工确认 oracle 语义等价；失败则移出交集。

---



## 7. Pareto / CI 支配规则


| 项            | 锁定                                                    |
| ------------ | ----------------------------------------------------- |
| CI           | Wilson（默认）或 bootstrap（协议版本化）                          |
| 支配           | A 的 CI 下界 ≥ B 的 CI 上界 → dominates；否则 undetermined/tie |
| 多能力          | Pareto 按能力向量，不按总分                                     |
| 默认           | 无单一 winner                                            |
| `rank_claim` | 预注册权重 + 敏感性 + 样本量/CI + 三方签字                           |


---



## 8. M1a 环境禁用表


| 开关        | plan_execute | conversational |
| --------- | ------------ | -------------- |
| tools     | none         | none           |
| retrieval | none         | none           |
| network   | none         | none           |
| session   | 默认无          | 允许             |


M1b 开 retrieval；M1c 开 tools/sandbox。

---



## 9. Rank gate（摘要）

轨 A 完成；同 intersection manifest；同 runtime_tier + 可比 runtime_parts；无 fixture 入榜；同 model fingerprint；oracle 版本一致；**rank_fingerprint 一致**；完成率 100%；unknown 不当 0/通过；样本量/CI；三方签字（方法 + 独立 QA + 产品）。

`rank_claim` 不能由「跑完了」自动产生。

---



## 10. M0 退出标准（10 项）

1. `impl_modes` 多值；unknown / deferred
2. 矩阵五字段 + case 级 rank_eligible
3. 选题并集、执行分开
4. `rank_fingerprint` 定义 + 可测实现
5. 交集 parity 流程与样例记录
6. Pareto/CI 支配规则成文
7. Subject = Agent × Mode × Config
8. M1a 禁用表
9. Rank gate + 签字角色
10. M1a/b/c 环境依赖清单

**未齐 → 不开 M1。**

### 10.1 阶段顺序

M0 → M1a（无工具 live）→ M1b（rag）→ M1c（react/沙箱后）→ M3（交集排行）→ M2（multi-agent）。

---



## 11. 工程落点（M0）


| 组件               | 路径                                                                                                   |
| ---------------- | ---------------------------------------------------------------------------------------------------- |
| 矩阵 YAML          | `workspace_seeds/eval/agent_capability/mode_core_capabilities.v1.yaml`                               |
| 解析 / fingerprint | `core/apps/eval/service/agent_impl_mode.py`                                                          |
| M0 契约门           | `evaluate_m0_impl_mode_contracts()`                                                                  |
| Facade           | `eval_evaluate_m0_impl_mode_contracts` / `eval_resolve_impl_modes` / `eval_compute_rank_fingerprint` |
| Parity 样例        | `workspace_seeds/eval/agent_capability/intersection/parity_sample.v1.json`                           |


M0 **不**接线 live `create_agent` runner。

---



## 12. 签字栏（M0 契约可用）


| 角色          | 勾选       | 签字  | 日期         |
| ----------- | -------- | --- | ---------- |
| 评测方法负责人     | M0 十条可审  | 朱向群 | 2026/11/09 |
| 工程负责人       | 种子 + 单测绿 | 朱鸿林 | 2026/11/09 |
| 独立 QA（M3 前） | 排行协议     | 朱莹  | 2026/11/09 |


