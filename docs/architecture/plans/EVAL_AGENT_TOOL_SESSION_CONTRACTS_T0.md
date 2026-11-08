# Eval Agent 升域契约 T0（Mock Tool / Session / Long-context / Runtime map）

> **类型**：契约冻结 / 升域立项 T0  
> **版本**：`eval.agent.inscope_contracts.t0` · 2026-11-08  
> **状态**：**Frozen（工程契约）** — 评测方法负责人「契约可用」签字见 §5（Go T1）  
> **关联**：[eval-agent-tool-session-inscope.md](./eval-agent-tool-session-inscope.md) · [eval-exam-runtime-tiers.md](./eval-exam-runtime-tiers.md) · ADR-EVAL-CAPABILITY-CASE-PACK-V1 §7 #9  
> **实现**：`core/apps/eval/service/mock_tools/` · `session_case_schema.py` · `long_context_fixture_schema.py` · `tool_eval_runtime_map.py`

---

## 0. 冻结元数据

| 字段 | 值 |
|------|-----|
| schema | `eval.agent.inscope_contracts.t0` |
| change_policy | 改必填字段 = bump 本文件版本；升 `V1_IN_SCOPE` 仍须 G6 再签字 |
| 非目标 | 不实现 execute/judge；不改 `V1_IN_SCOPE`；非 Certification |

---

## 1. Mock Tool 目录（`eval.mock_tool_catalog.v1`）

### 1.1 Catalog

```json
{
  "schema": "eval.mock_tool_catalog.v1",
  "catalog_id": "agent.mock_tools.default",
  "version": "0.1.0",
  "tools": [ { "...": "§1.2" } ]
}
```

| 字段 | 类型 | 约束 |
|------|------|------|
| `schema` | string | 必须 = `eval.mock_tool_catalog.v1` |
| `catalog_id` | string | 非空 |
| `version` | string | semver-ish 非空 |
| `tools` | object[] | ≥1；`name` 目录内唯一 |

### 1.2 Tool 条目

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `name` | string | `[a-z][a-z0-9_]*` | 工具名（canonical） |
| `description` | string | 非空 | 给人/模型看的说明 |
| `args_schema` | object | JSON Schema object（`type=object`） | 参数 schema |
| `result` | any | 必填 | 确定性成功返回（可序列化） |
| `fail_modes` | object[] | 可空 | 见下表 |

`fail_modes[]`：

| 字段 | 类型 | 约束 |
|------|------|------|
| `mode_id` | string | 非空；工具内唯一 |
| `when` | string | 非空（触发说明，机读标签即可） |
| `error` | string | 非空 |
| `http_status` | int? | 可选 |

样例：`workspace_seeds/eval/agent_capability/fixtures/mock_tools/catalog.sample.json`（另附 `.yaml`）。

---

## 2. Session 卷字段（`eval.session_case.v1`）

在 `EvalCase` 上扩展（与现有 `session_group` 兼容）：

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `session_group` | string \| null | 多轮必填非空；单轮可 null | 同组整卷入选 |
| `turn_index` | int \| null | 有 `session_group` 时必填；≥0；组内唯一 | 轮次顺序 |
| `memory_probe` | object \| null | 可选 | 跨轮记忆探针 |

`memory_probe`：

| 字段 | 类型 | 约束 |
|------|------|------|
| `planted_fact` | string | 非空（本轮或前轮埋下的事实；**不得**泄漏进后续用户可见 prompt 的「标准答案句」——人审） |
| `ask_after_turns` | int | ≥1 | 再过几轮追问 |
| `must_recall` | string[] | ≥1 | 追问轮 oracle 线索 |

规则：

1. 若 `turn_index` 有值则必须有非空 `session_group`。  
2. 同 `session_group` 内 `turn_index` 不得重复（卷级校验，单 case 校验只查字段形）。  
3. `memory_probe` 出现时必须有 `session_group`。

样例：`fixtures/session/session_case.sample.json`。

---

## 3. Long-context fixture（`eval.long_context_fixture.v1`）

Case 可挂 `long_context_fixture` 对象（A9）：

| 字段 | 类型 | 约束 |
|------|------|------|
| `schema` | string | = `eval.long_context_fixture.v1` |
| `context_tokens_est` | int | ≥100（CI 短档可用 100–2000；正式档另配置） |
| `noise_slots` | object[] | ≥1 |
| `must_retain_claims` | string[] | ≥1 |

`noise_slots[]`：`{ "slot_id": string, "kind": "filler"|"distractor"|"conflict", "approx_tokens": int≥1 }`

样例：`fixtures/long_context/fixture.sample.json`。

---

## 4. `runtime_tier` 映射（mock vs live）

对齐 [eval-exam-runtime-tiers.md](./eval-exam-runtime-tiers.md)。升域执行面额外约定：

| `tool_backend` | 含义 | 允许的实际 `runtime_tier` | `runtime_claim` 边界 |
|----------------|------|---------------------------|----------------------|
| `none` | 无工具（文本子集） | `fixture` / `workspace_execute` | 不得宣称工具能力 covered |
| `mock` | 本目录确定性工具 | `fixture`（仅结构）或带 mock 注入的 `workspace_execute` | **仅**可对 mock 工具轨迹作有限陈述；**≠ live** |
| `live` | 真实 skill / API / microVM | 须显式 live tier；不得与 mock 混表 | 另立项 T4；不得用 mock 分冒充 live |

强制：

- 报告须带 `tool_backend`（T1+ execute 写入）。  
- `tool_backend=mock` 时禁止 `runtime_claim_reason` 写「生产工具已测」。  
- A3–A5 在 T1 默认 `tool_backend=mock`。

机器表：`tool_eval_runtime_map.py` → `TOOL_BACKEND_RUNTIME_MAP`。

---

## 5. Go T1 签字栏

| 角色 | 勾选 | 签字（`SIGNED t0_contracts_usable`） | 日期 |
|------|:----:|--------------------------------------|------|
| 评测方法负责人 | 契约可用 → 可开 T1 | | |
| 工程负责人 | 样例 + 校验测试绿 | | |

**工程侧 T0 完成标准**：本文件入库 + 样例校验测试通过 + 公共 validate 符号已注册。方法负责人签字后开 T1 代码（harness），不在本文件内改 `V1_IN_SCOPE`。
