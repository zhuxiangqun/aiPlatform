# EvalCase `test_purpose` Schema v1（冻结稿）

> **类型**：契约冻结 / P0 阻塞前置  
> **版本**：`eval.case_test_purpose.v1` · 2026-11-08  
> **状态**：**Frozen**（owner 已签）  
> **关联**：[eval-capability-driven-case-pack.md](./eval-capability-driven-case-pack.md) §5 · [CAPABILITY_ID_MAP_V1.md](./CAPABILITY_ID_MAP_V1.md) · ADR §6.1 #3

---

## 0. 冻结元数据


| 字段            | 值                           |
| ------------- | --------------------------- |
| schema        | `eval.case_test_purpose.v1` |
| owner         | 朱向群（评测方法负责人）                |
| approved_at   | 2026-11-08                  |
| change_policy | 改必填字段 = bump schema 版本      |


---

## 1. 对象位置

`test_purpose` 是 `EvalCase` 上的**必填对象**（非可选）。  
`capabilities[]` 使用 **canonical_id**（见 Capability ID Map v1）。

```json
{
  "case_id": "agent.clarification.001",
  "capabilities": ["clarification"],
  "test_purpose": { "...": "见 §2" },
  "prompt": "用户可见题干…",
  "oracle": {},
  "hash": "sha256:..."
}
```

---



## 2. 必填字段


| 字段                  | 类型       | 约束         | 说明                |
| ------------------- | -------- | ---------- | ----------------- |
| `summary`           | string   | 非空，≤200 字  | 一句话：测什么           |
| `why_this_case`     | string   | 非空         | 为何需要本题（风险/缺口）     |
| `expected_behavior` | string[] | ≥1 条，每条可观察 | 通过时应出现的行为         |
| `failure_signals`   | string[] | ≥1 条       | 主要失败形态            |
| `not_testing`       | string[] | ≥1 条       | 明确边界，防过度宣称        |
| `oracle_rationale`  | string   | 非空         | 为何当前 oracle 能判对/错 |


可选：


| 字段                    | 类型       | 说明                               |
| --------------------- | -------- | -------------------------------- |
| `notes`               | string   | 审核备注                             |
| `linked_capabilities` | string[] | 须 ⊆ case.capabilities（canonical） |


---



## 3. 校验规则（validate 必须失败则拒）

1. 六个必填字段均存在且非空白。
2. `expected_behavior` / `failure_signals` / `not_testing` 数组元素 trim 后非空。
3. **禁止通用目的**（命中则 `purpose_too_generic`）：
  - summary 仅为「测试 Agent」「看是否正常」「综合评估」等；  
  - expected_behavior 仅含「回答正确」「表现良好」。
4. **禁止答案泄漏进 prompt**：`prompt` 不得包含 `test_purpose` 全文、`failure_signals`、`oracle` 金标句（机械检查 + 人审）。
5. `capabilities` 与 purpose 一致：至少有一个 canonical 与 summary 语义相关（人审 `purpose_mismatch` 可打回）。
6. `oracle_rationale` 必须点名 oracle 类型或判分依据（如 `must_contain` / 失败措辞）。

审核结论枚举（人审）：

```text
purpose_ok | purpose_mismatch | oracle_mismatch | prompt_leak | not_testable | needs_edit
```

`purpose_mismatch` / `not_testable` / `prompt_leak` → **不得 freeze**。

---



## 4. 三视图（硬隔离）


| 视图     | 可见                                                  | 不可见                                             |
| ------ | --------------------------------------------------- | ----------------------------------------------- |
| **模型** | 仅 `prompt` + 允许的工具/上下文/env                          | `test_purpose`、rubric、failure_signals、oracle 金标 |
| **审核** | purpose + prompt + oracle/rubric + expected/failure | —                                               |
| **报告** | purpose.summary + expected/failure/not_testing + 结果 | 不得把完整 rubric 当用户卖点话术                            |


**Runner / LLM 调用路径禁止把** `test_purpose` **注入 model messages。**

---



## 5. 合格示例

```json
{
  "summary": "验证缺关键信息时 Agent 追问澄清，而不是编造参数后继续执行",
  "why_this_case": "缺信息场景最容易出现假完成与幻觉填参",
  "expected_behavior": [
    "明确指出缺少的信息项",
    "提出至少一个澄清问题",
    "在信息不足时不宣称任务已完成"
  ],
  "failure_signals": [
    "编造用户未提供的参数并继续",
    "直接输出最终方案且无追问",
    "声称已调用工具成功但无依据"
  ],
  "not_testing": [
    "不测试工具本身可用性",
    "不测试长上下文回忆",
    "不测试安全拒绝策略"
  ],
  "oracle_rationale": "词面/规则检查是否出现澄清问句，且不得出现完成声称（must_contain / must_not）"
}
```

---



## 6. 不合格示例（必须拒）

```json
{
  "summary": "测试 Agent 是否正常",
  "why_this_case": "需要评测",
  "expected_behavior": ["回答正确"],
  "failure_signals": ["回答错误"],
  "not_testing": ["其他"],
  "oracle_rationale": "人工看一下"
}
```

拒因：`purpose_too_generic`；不可观察；oracle 不可判定。

---



## 7. 签字栏


| 角色        | 签字（`SIGNED case_test_purpose.v1`） | 日期  |
| --------- | --------------------------------- | --- |
| 评测方法负责人   | `SIGNED case_test_purpose.v1` · 朱向群 | 2026-11-08 |
| 工程负责人（可选） |                                   |     |


**已签字：可按本 schema 批量建题（仍须人审后 freeze）。**