---
doc_type: Standard
status: active
authority: canonical
doc_id: EVAL_SYS_V10_APPENDIX
purpose: 评测系统 v1.0 规范性附录（字段/错误码/符合性清单）
scope_in: 附录 A–O；附录 N 符合性清单
scope_out: 实现状态声明、业务域内容
owner: 朱向群
version: 1.0.0
last_reviewed: 2026-11-26
review_cycle: 90d
---
# aiPlat 评测系统规范性附录 v1.0

> **配套**：《评测系统技术白皮书 v1.0》  
> **效力**：与正文同等（2026-12-01 起）。  
> **用语**：MUST / MUST NOT / SHOULD / MAY。  
> **机读**：`schemas/evaluation-system.v1.0.schema.json` + `conformance-checklist.yaml`。

## 附录地图

| 小节 | 内容 | 对应正文 |
|---|---|---|
| 0 | 规范性约定 | 全文 |
| A | 架构对象与边界 | 3 |
| B | 评测对象契约 | 4 |
| C | 唯一入口 / Plan / Runner | 5 |
| D | 结果与归因报告 | 6 |
| E | Case Pack / Gold | 7 |
| F | Judge | 8 |
| G | Gate | 9 |
| H | 评测中心 UX 约束 | 10 |
| I | 安全 / 租户 | 11 |
| J | A3 边界 | 12 |
| N | Conformance Checklist | 16 |
| O | 校准与 accuracy 声明 | 13 |

---

## 0. 规范性约定

- 字段名区分大小写；必填缺失 = 不合规；
- 扩展字段使用 `x-` 前缀；
- 时间 RFC3339 UTC；
- Patch/Minor/Major 兼容规则同知识体系附录 0.3。

---

## A. 架构对象

| 对象 | MUST |
|---|---|
| EvaluationPlan | 选题真相；失败 fail closed |
| CasePack | 可哈希、可 ACL |
| Runner | 唯一执行语义 |
| GateResult | 绑定指纹 |

Harness/Core 禁止硬编码业务 Agent 名做评测分叉（配置驱动）。

---

## B. 评测对象契约

```text
subject_kind: agent | skill | tool | mcp | prompt | workflow
subject_id: string (tenant-scoped)
protocol_version: string
```

v1.0 Core MUST：`agent`、`skill`。  
未知 `subject_kind` MUST 拒绝执行（非静默跳过）。

---

## C. 唯一入口 / Plan / Runner

### C.1 HTTP

- Canonical：`/api/platform/apps/eval/**`；
- 新端点 MUST NOT 落在并行「第二套评测 API」。

### C.2 Plan

| 字段 | 规则 |
|---|---|
| `plan_id` | MUST |
| `sample_manifest` | MUST；空 → fail closed |
| `selected_cases` | legacy 投影 only；MUST NOT 作为唯一清单 |
| `manifest_hash` | MUST 可计算 |

### C.3 错误码（最小集）

| code | 含义 |
|---|---|
| `eval.plan_compile_failed` | Plan 编译失败 |
| `eval.manifest_empty` | 执行清单空 |
| `eval.manifest_hash_mismatch` | live hash 不符 |
| `eval.entry_not_canonical` | 非唯一入口 |
| `eval.claim_forbidden` | 试图宣称 accuracy/certified 无证据 |

---

## D. 结果与归因

报告 MUST 含：

- 总分（可选）+ **维度分**；
- `evidence_refs[]`；
- `plan_id` / `manifest_hash` / `execution_fingerprint`；
- `claim_eligible: false` 默认，除非附录 O 条件满足。

---

## E. Case Pack / Gold

- Canonical case/pack hash MUST；
- 执行前 live hash 校验 MUST；
- `generated+claim_eligible` MUST 拒；
- Gold 变更 MUST 升版本，禁止静默改标签。

---

## F. Judge

- Judge 输出 MUST 带 `judge_id` / `calibration_ref`（可空但须显式）；
- `calibration_ref` 空时 MUST NOT 单独满足对外 accuracy gate。

---

## G. Gate

- Gate 输入 MUST 引用同一 Runner 结果；
- 通过结论 MUST 持久化指纹；
- UI preview 通过 ≠ Gate 通过。

---

## H. UX

- Canonical 路由 SHOULD 为 `/eval`；
- 旧诊断评测页 MUST redirect 或标明「非认证面」。

---

## I. 安全 / 租户

- `tenant_id` / actor MUST 注入；
- 跨租户读取金标 MUST 拒绝或显式授权记录。

---

## J. A3

- `process_split` 默认 false；
- 拆分 MUST 保持附录 C 语义唯一，禁止平行协议。

---

## N. Conformance Checklist（机读权威）

| ID | 等级 | 项 | Core |
|---|---|---|---|
| E01 | Core | 唯一入口 `/api/platform/apps/eval` | MUST |
| E02 | Core | Plan + sample_manifest fail closed | MUST |
| E03 | Core | Case Pack hash + live 校验 | MUST |
| E04 | Core | 结果含维度分与证据引用 | MUST |
| E05 | Core | 默认 `claim_eligible=false` | MUST |
| E06 | Core | 门禁绑定指纹 | MUST |
| E07 | Extended | Judge 校准报告 | SHOULD |
| E08 | Extended | 评测中心 `/eval` | SHOULD |
| E09 | Extended | Tool/MCP subject | SHOULD |
| E10 | Operational | A3 process_split 授权 | MAY |
| E11 | Operational | 生产 SLA / authorize | MAY |
| E12 | Operational | 双人标注 κ 报告 | MAY |

`core_ready` = E01–E06 exists；`certified` 须非作者批准 + 证据包。

### N.1 代码证据快照（2026-11-26 · 测量，非认证）

权威测量报告：`reports/products/evaluation-system/v1.0/core-gap-evidence.md`。

| ID | 测量状态 | 一句话 |
|---|---|---|
| E01 | exists | canonical `/api/platform/apps/eval` + legacy shim |
| E02 | exists | `require_sample_manifest` fail closed |
| E03 | exists | pack/manifest hash + live case hash |
| E04 | exists | `normalize_evidence_refs` + attributable/attach 统一 refs |
| E05 | exists | 默认 claim/accuracy false + generated 禁 claim |
| E06 | exists | claims_gate 强制三指纹；`gates.fingerprints_bound` |
| E07 | exists | `normalize_judge_report` + `run_e4_calibration` 显式 `calibration_ref` |
| E08 | exists | `/eval` EvalCenter + `eval_center_route_contract`；旧 diagnostics 硬切 |
| E09 | exists | `normalize_tool_mcp_subject` + `McpSubjectAdapter`；外援须 `verified_tier` |
| E10 | exists | `evaluate_eval_process_split_authorize`；**authorized=true**（朱莹 pilot；见批准记录） |
| E11 | exists | `evaluate_eval_production_sla_authorize`；**authorized=true**（须 `sla_ref`） |
| E12 | exists | `build_dual_annotator_kappa_report`；κ≠accuracy |

**测量：Core/Extended/Operational 项均为 exists。**  
**徽章（2026-11-26 clause-sync）**：conditional `core_ready`（朱鸿林）+ `extended_ready`（朱莹）；E10–E11 authorized → `operational_ready`；E12 不构成 accuracy。`certified`：**否**。  
证据：`core|extended|operational-gap-evidence.md` + `*-approval-record.approved.json`。

---

## O. 校准与 accuracy 声明

允许 accuracy 类声明仅当：

1. 双人标注或等价协议；  
2. 范围（对象/域/版本）写明；  
3. 校准报告可复现；  
4. 附录 N 对应项 `certified`。

否则 MUST 使用工程措辞（门禁通过 / 指纹匹配），MUST NOT 使用「准确率 xx%」对外宣称。
