# DIAGNOSIS_V1 C0 — API / UI 设计稿（不实现）

- charter: [`diagnosis-v1-charter.md`](../../../docs/architecture/plans/diagnosis-v1-charter.md)  
- unfreeze: C0 only — **禁止写产品代码**（C1 另解冻）

## Canonical API

Base: `/api/platform/apps/diagnosis`

| Method | Path | 说明 |
|---|---|---|
| POST | `/cases` | 创建 DiagnosisCase（scenario + subject_ref） |
| GET | `/cases` | 列表（tenant 隔离） |
| GET | `/cases/{id}` | 详情 |
| POST | `/cases/{id}/collect` | 只读采集证据引用（adapters） |
| GET | `/cases/{id}/evidence` | EvidenceRef 列表 |
| GET | `/cases/{id}/findings` | Finding 列表 |
| GET | `/cases/{id}/hypotheses` | Hypothesis 列表（Top-K） |
| GET | `/cases/{id}/report` | DiagnosisReport |
| POST | `/cases/{id}/recommendations` | 生成建议（`auto_execute=false`） |
| GET | `/healthz` | `product_id=diagnosis` |

**禁止**：`POST …/remediate` 自动执行；跨产品写；与 `/diagnostics` 路径混用。

---

## Auth / Tenant（C1 必须实现）

| 项 | 规则 |
|---|---|
| 认证 | 与平台一致：`require_auth`（JWT / API key）；匿名禁止 |
| 租户 | 所有 Case/Evidence/Report **按 `tenant_id` 隔离**；列表/详情越权 → 404（不泄露存在性） |
| 角色 | admin/developer/operator/fde：读写 case；只读角色仅 GET report/list |
| 采集 | adapters 只读源系统；诊断服务**不写**源 run/trace |
| 审计 | 创建 case / 生成报告写 audit 事件（谁、何时、subject_ref） |

---

## Error 模型

| HTTP | code | 何时 |
|---:|---|---|
| 400 | `invalid_scenario` | scenario 非 run_failure/version_regression |
| 400 | `missing_subject` | 缺 subject_ref |
| 404 | `case_not_found` | 无此 case 或跨租户 |
| 409 | `case_not_ready` | 未 collect 就强要「已确认根因」 |
| 422 | `accuracy_claim_forbidden` | 请求体试图设 `accuracy_claim=true` |
| 422 | `auto_execute_forbidden` | recommendation.auto_execute≠false |
| 503 | `adapter_unavailable` | 源系统不可达 → 报告侧记 `unknown`，不伪造根因 |

Envelope：`{"data": {...}}` 或 `{"detail": {"code", "message"}}`（对齐平台）。

---

## Retention

| 对象 | 默认保留 | 说明 |
|---|---|---|
| DiagnosisCase / Report | 90 天 | 可配置；到期软删 |
| EvidenceRef | 随 case | **不**复制源 payload；只存引用；源侧自管 TTL |
| Fixture（评测用） | 仓库内长期 | 脱敏；不含密钥 |

过期证据：`freshness=stale` 或 `uncertainty.stale[]`；UI 必须展示，不得当 fresh 根因。

---

## unknown / stale 展示规则（诚实条）

| 状态 | API | UI |
|---|---|---|
| 证据不足 | `status=blocked_unknown`；`uncertainty.unknown` 非空；**不得**给 Top-1「已确认」 | 黄/橙条：「证据不足，结论 unknown」；隐藏「根因已确认」徽章 |
| 证据过期 | `status=blocked_stale` 或 report 含 `stale[]` | 条：「证据过期 (stale)」；假设可展示但标低置信 |
| 正常报告 | `accuracy_claim=false` 恒成立 | 页脚诚实条：工程诊断 ≠ 准确率认证；≠ authorize |
| 建议 | `auto_execute=false` | 按钮文案「复制建议 / 打开目标 API」，**无**「一键修复」 |

违反（无证据却给出唯一根因）= **产品缺陷**，C1 验收计 0。

---

## UI `/diagnosis`

| 视图 | 内容 |
|---|---|
| 列表 | Case 状态、场景、subject、unknown/stale 标记 |
| 详情 | 证据图（refs）、Findings、Hypotheses（置信度）、Report |
| 对比 | S2：baseline vs candidate |
| 诚实条 | 见上表；始终可见 |

旧 `/diagnostics` 保留为工程工具箱；可深链采集器，不嵌 20+ 页当产品。

## Adapters（C1 接线预留）

| source | 读什么 | 写 |
|---|---|---|
| aiplat | run/trace/syscall/context/policy | 否 |
| pi | healthz/deploy/log ref | 否 |
| fde | project/evidence envelope | 否 |
| evaluation | eval/gate report | 否 |
