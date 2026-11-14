---
doc_type: Reference
---

# R12 · 能力对账结果（tranche-1：evaluation-system）

> 规则：计划 §4.5 · 主键 `capability_registry.yaml` · 视图 `AIPLAT_CAPABILITIES.md`
> **范围**：仅 `domains.evaluation-system`
> **诚实锁**：对账工件已产出；差异多为 `open`；**≠** Tier A 扩容；**≠** 定稿
> **时点**：2026-11-14T16:24:52+08:00
> 复跑：`python3 packages/aiplat-evaluation/scripts/r12_capability_reconciliation.py`
> 机器可读：[`evidence/r12_capability_reconciliation.v0.json`](./evidence/r12_capability_reconciliation.v0.json)

## 汇总

| 指标 | 数量 |
|---|---:|
| registry 符号（evaluation-system） | 638 |
| 两边均有 | 27 |
| registry 有、CAPABILITIES 无 | 611 |
| CAPABILITIES eval 样词有、本域 registry 无 | 56 |
| 差异合计 | 667 |

## 处置队列（前 40 条；全文见 JSON）

| 类型 | 符号 | module | owner | 处理结果 |
|---|---|---|---|---|
| registry_has_capabilities_missing | `AdversarialTestSuite` | `core/harness/evaluation/adversarial_test_suite.py` | 评测 owner | open |
| registry_has_capabilities_missing | `AgentImplModeError` | `aiPlat-core/core/apps/eval/service/agent_impl_mode.py` | 评测 owner | open |
| registry_has_capabilities_missing | `AgentSubjectAdapter` | `aiPlat-core/core/apps/eval/service/subject_adapter.py` | 评测 owner | open |
| registry_has_capabilities_missing | `ApiCapabilityBankError` | `aiPlat-core/core/apps/eval/service/api_capability_bank.py` | 评测 owner | open |
| registry_has_capabilities_missing | `CapabilityCaseBankError` | `aiPlat-core/core/apps/eval/service/capability_case_bank.py` | 评测 owner | open |
| registry_has_capabilities_missing | `CapabilityCaseEditorError` | `aiPlat-core/core/apps/eval/service/capability_case_editor.py` | 评测 owner | open |
| registry_has_capabilities_missing | `CapabilityCertReadinessError` | `aiPlat-core/core/apps/eval/service/capability_cert_readiness.py` | 评测 owner | open |
| registry_has_capabilities_missing | `CapabilityCoverageFillError` | `aiPlat-core/core/apps/eval/service/capability_coverage_fill.py` | 评测 owner | open |
| registry_has_capabilities_missing | `CapabilityP4GateError` | `aiPlat-core/core/apps/eval/service/capability_p4_gate.py` | 评测 owner | open |
| registry_has_capabilities_missing | `CodeReviewCapabilityBankError` | `aiPlat-core/core/apps/eval/service/code_review_capability_bank.py` | 评测 owner | open |
| registry_has_capabilities_missing | `CodeReviewSubjectAdapter` | `aiPlat-core/core/apps/eval/service/subject_adapter.py` | 评测 owner | open |
| registry_has_capabilities_missing | `ContentPurposeOkError` | `aiPlat-core/core/apps/eval/service/content_purpose_ok.py` | 评测 owner | open |
| registry_has_capabilities_missing | `DatasetCapabilityBankError` | `aiPlat-core/core/apps/eval/service/dataset_capability_bank.py` | 评测 owner | open |
| registry_has_capabilities_missing | `EvalA1IntersectionCard` | `aiPlat-management/frontend/src/pages/Eval/EvalA1IntersectionCard.tsx` | 评测 owner | open |
| registry_has_capabilities_missing | `EvalRunner` | `core/harness/evaluation/eval_runner.py` | 评测 owner | open |
| registry_has_capabilities_missing | `EvalSecurityS1Card` | `aiPlat-management/frontend/src/pages/Eval/EvalSecurityS1Card.tsx` | 评测 owner | open |
| registry_has_capabilities_missing | `EvalStore` | `core/apps/eval/service/store.py` | 评测 owner | open |
| registry_has_capabilities_missing | `EvalSubjectAdapter` | `aiPlat-core/core/apps/eval/service/subject_adapter.py` | 评测 owner | open |
| registry_has_capabilities_missing | `GeneratedAppCapabilityBankError` | `aiPlat-core/core/apps/eval/service/generated_app_capability_bank.py` | 评测 owner | open |
| registry_has_capabilities_missing | `HttpChatPullAdapter` | `core/apps/eval/service/external_chat_pull.py` | 评测 owner | open |
| registry_has_capabilities_missing | `KbCapabilityBankError` | `aiPlat-core/core/apps/eval/service/kb_capability_bank.py` | 评测 owner | open |
| registry_has_capabilities_missing | `KbSubjectAdapter` | `aiPlat-core/core/apps/eval/service/subject_adapter.py` | 评测 owner | open |
| registry_has_capabilities_missing | `MethodTrackError` | `aiPlat-core/core/apps/eval/service/method_track.py` | 评测 owner | open |
| registry_has_capabilities_missing | `MockToolCatalogError` | `aiPlat-core/core/apps/eval/service/mock_tools/catalog_load.py` | 评测 owner | open |
| registry_has_capabilities_missing | `MockToolHarnessError` | `aiPlat-core/core/apps/eval/service/mock_tools/harness.py` | 评测 owner | open |
| registry_has_capabilities_missing | `ModeAwareExamError` | `aiPlat-core/core/apps/eval/service/mode_aware_exam.py` | 评测 owner | open |
| registry_has_capabilities_missing | `ModeDeferredEstimateError` | `aiPlat-core/core/apps/eval/service/mode_deferred_estimate.py` | 评测 owner | open |
| registry_has_capabilities_missing | `ModeIntersectionRankError` | `aiPlat-core/core/apps/eval/service/mode_intersection_rank.py` | 评测 owner | open |
| registry_has_capabilities_missing | `ModelCapabilityBankError` | `aiPlat-core/core/apps/eval/service/model_capability_bank.py` | 评测 owner | open |
| registry_has_capabilities_missing | `ModelSubjectAdapter` | `aiPlat-core/core/apps/eval/service/subject_adapter.py` | 评测 owner | open |
| registry_has_capabilities_missing | `MultiAgentCapabilityBankError` | `aiPlat-core/core/apps/eval/service/multi_agent_capability_bank.py` | 评测 owner | open |
| registry_has_capabilities_missing | `MultiAgentSubjectAdapter` | `aiPlat-core/core/apps/eval/service/subject_adapter.py` | 评测 owner | open |
| registry_has_capabilities_missing | `NLIBridge` | `core/harness/evaluation/nli_engine.py` | 评测 owner | open |
| registry_has_capabilities_missing | `PromptCapabilityBankError` | `aiPlat-core/core/apps/eval/service/prompt_capability_bank.py` | 评测 owner | open |
| registry_has_capabilities_missing | `PromptSubjectAdapter` | `aiPlat-core/core/apps/eval/service/subject_adapter.py` | 评测 owner | open |
| registry_has_capabilities_missing | `QualityScoring` | `core/harness/knowledge/scoring_engine.py` | 评测 owner | open |
| registry_has_capabilities_missing | `RunsEvalGateFailed` | `core/apps/eval/service/runs_eval_ops.py` | 评测 owner | open |
| registry_has_capabilities_missing | `SessionCapabilityBankError` | `aiPlat-core/core/apps/eval/service/session_capability_bank.py` | 评测 owner | open |
| registry_has_capabilities_missing | `SessionRunnerError` | `aiPlat-core/core/apps/eval/service/session_runner.py` | 评测 owner | open |
| registry_has_capabilities_missing | `SessionSubjectAdapter` | `aiPlat-core/core/apps/eval/service/subject_adapter.py` | 评测 owner | open |
| … | （另有 627 条见 JSON） | | | open |

## Owner

| 字段 | 值 |
|---|---|
| Owner | 评测 owner |
| 签字日 | ________________ |
| 备注 | 差异清零前禁止宣称全平台覆盖完成 |

