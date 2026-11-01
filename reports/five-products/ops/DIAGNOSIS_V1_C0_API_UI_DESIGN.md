# DIAGNOSIS_V1 C0 — API / UI 设计稿（不实现）

- charter: [`diagnosis-v1-charter.md`](../../../docs/architecture/plans/diagnosis-v1-charter.md)  
- unfreeze: C0 only — **禁止写代码**

## Canonical API

Base: `/api/platform/apps/diagnosis`

| Method | Path | 说明 |
|---|---|---|
| POST | `/cases` | 创建 DiagnosisCase（scenario + subject_ref） |
| GET | `/cases` | 列表 |
| GET | `/cases/{id}` | 详情 |
| POST | `/cases/{id}/collect` | 只读采集证据引用（adapters） |
| GET | `/cases/{id}/evidence` | EvidenceRef 列表 |
| GET | `/cases/{id}/findings` | Finding 列表 |
| GET | `/cases/{id}/hypotheses` | Hypothesis 列表（Top-K） |
| GET | `/cases/{id}/report` | DiagnosisReport |
| POST | `/cases/{id}/recommendations` | 生成建议（`auto_execute=false`） |
| GET | `/healthz` | `product_id=diagnosis` |

**禁止**：`POST …/remediate` 自动执行；跨产品写；与 `/diagnostics` 路径混用。

## UI `/diagnosis`

| 视图 | 内容 |
|---|---|
| 列表 | Case 状态、场景、subject、不确定性标记 |
| 详情 | 证据图（refs）、Findings、Hypotheses（置信度）、Report |
| 对比 | S2：baseline vs candidate 证据/评测分差 |
| 诚实条 | `accuracy_claim=false`；无证据不得显示「根因已确认」 |

旧 `/diagnostics` 保留为工程工具箱；产品页可链到具体采集器，但不把 20+ 页嵌成产品。

## Adapters（C1 接线预留）

| source | 读什么 | 写 |
|---|---|---|
| aiplat | run/trace/syscall/context/policy | 否 |
| pi | healthz/deploy/log ref | 否 |
| fde | project/evidence envelope | 否 |
| evaluation | eval/gate report | 否 |
