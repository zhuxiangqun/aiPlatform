---
doc_type: Report
doc_id: EVAL_SYS_V10_CORE_GAP
status: measurement
authority: evidence
created: 2026-11-26
last_reviewed: 2026-11-26
purpose: 评测系统 v1.0 附录 N Core（E01–E06）代码证据盘点；非 certified 声明
---

# 评测系统 v1.0 — Core 差距证据（测量）

> **性质**：测量报告。`exists` ≠ `certified`。  
> **刷新**：2026-11-26 收口 E04/E06 后重测。

## 总判定

| 问题 | 结论 |
|---|---|
| 能否宣称 `core_ready`？ | **测量态：E01–E06 均为 exists**；正式 `core_ready` 仍须非作者复核 |
| 能否宣称 `certified`？ | **否** |

## E01–E06

| ID | 状态 | 证据 | 缺口 |
|---|---|---|---|
| E01 唯一入口 `/api/platform/apps/eval` | **exists** | `routes.py:8055`；`apps.yaml:108`；`legacy_shim.py`；`test_eval_v1_e1_canonical.py` | — |
| E02 Plan + sample_manifest fail closed | **exists** | `case_pack_legacy.py` `require_sample_manifest` | — |
| E03 Case Pack hash + live 校验 | **exists** | `case_pack_hash.py`；`verify_manifest_case_hashes` | — |
| E04 维度分 + 证据引用 | **exists** | `claims_gate.normalize_evidence_refs`；gate 返回 `evidence_refs` + `dimensions`；`attach_evaluation_plan` 统一 refs；`build_attributable_report` 含 `evidence_refs` | 历史调用方若未走 attach/attributable 仍可能缺字段 — 新路径已强制 |
| E05 默认 claim_eligible=false | **exists** | `claims_gate` 默认 false；`assert_claim_eligible_allowed` | — |
| E06 门禁绑定指纹 | **exists** | `_REQUIRED_SCOPE_KEYS` 含 `manifest_hash`+`execution_fingerprint`；返回 `fingerprints` + `gates.fingerprints_bound`；`attach_evaluation_plan` 盖章三指纹；测试 `test_missing_fingerprints_block_accuracy` | — |

## 复现命令

```bash
rg -n 'manifest_hash|execution_fingerprint|normalize_evidence_refs|fingerprints_bound' \
  aiPlat-core/core/apps/eval/service/claims_gate.py
pytest aiPlat-core/core/tests/unit/test_apps/test_claims_gate.py -q
```
