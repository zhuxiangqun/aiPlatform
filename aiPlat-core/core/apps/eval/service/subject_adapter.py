"""EvalSubjectAdapter — Subject×Capability×Method×Evidence P0 skeleton.

Agent is the reference implementation. Prompt is the first non-agent Subject
(ADR-EVAL-CAPABILITY-CASE-PACK-V1). Core must dispatch via registry — no
``if object_type ==`` business piles beyond the type→adapter map.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, runtime_checkable

from core.apps.eval.service.capability_id_map import (
    CANONICAL_IDS,
    UnknownCapabilityId,
    V1_IN_SCOPE,
    V1_OUT_OF_SCOPE,
    resolve_capability_ids,
)
from core.apps.eval.service.long_context_fixture_schema import (
    validate_case_long_context_fields,
)
from core.apps.eval.service.object_adapters import build_contract_for_object_type
from core.apps.eval.service.session_case_schema import validate_session_case_fields
from core.apps.eval.service.test_purpose import validate_test_purpose

ADAPTER_SCHEMA = "eval.subject_adapter.v1"

# Prompt v1 measurable subset (maps from typed prompt/* packs + defaults).
PROMPT_V1_CAPS = frozenset(
    {
        "task_completion",  # basic / format_constraint
        "clarification",  # missing_vars
        "long_context",  # multi_slot
        "safety",
        "robustness",  # noise
    }
)


@runtime_checkable
class EvalSubjectAdapter(Protocol):
    subject_kind: str

    def build_contract(self, **kwargs: Any) -> Dict[str, Any]: ...

    def capability_catalog(self) -> List[Dict[str, Any]]: ...

    def validate_case(self, case: Mapping[str, Any]) -> List[str]: ...

    def execute(self, case: Mapping[str, Any], env: Mapping[str, Any] | None = None) -> Dict[str, Any]: ...

    def judge(self, case: Mapping[str, Any], result: Mapping[str, Any]) -> Dict[str, Any]: ...

    def normalize(
        self,
        case: Mapping[str, Any],
        result: Mapping[str, Any],
        judgment: Mapping[str, Any],
    ) -> Dict[str, Any]: ...


class AgentSubjectAdapter:
    """Agent reference adapter (P0: contract / catalog / validate_case)."""

    subject_kind = "agent"

    def build_contract(
        self,
        *,
        object_id: str,
        object_version: str = "",
        capabilities: Optional[Sequence[str]] = None,
        tools: Optional[Sequence[str]] = None,
        permissions: Optional[Sequence[str]] = None,
        roles: Optional[Sequence[str]] = None,
        eval_profile: Optional[Mapping[str, Any]] = None,
        source_refs: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        caps = resolve_capability_ids(capabilities or (), fail_closed=True) if capabilities else None
        profile = dict(eval_profile or {})
        if caps is None and profile.get("capabilities"):
            profile["capabilities"] = resolve_capability_ids(
                list(profile.get("capabilities") or []), fail_closed=False
            )
        return build_contract_for_object_type(
            object_type="agent",
            object_id=object_id,
            object_version=object_version,
            capabilities=caps,
            tools=tools,
            permissions=permissions,
            roles=roles,
            eval_profile=profile,
            source_refs=source_refs,
        )

    def capability_catalog(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for cid in sorted(CANONICAL_IDS):
            rows.append(
                {
                    "capability_id": cid,
                    "object_types": ["agent"],
                    "in_scope": cid in V1_IN_SCOPE,
                    "v1_unknown": cid in V1_OUT_OF_SCOPE,
                }
            )
        return rows

    def validate_case(self, case: Mapping[str, Any]) -> List[str]:
        errors: List[str] = []
        if not isinstance(case, Mapping):
            return ["invalid_case"]
        case_id = str(case.get("case_id") or "").strip()
        if not case_id:
            errors.append("missing_field:case_id")
        caps_raw = case.get("capabilities")
        try:
            caps = resolve_capability_ids(
                list(caps_raw or []), fail_closed=True
            )
        except UnknownCapabilityId as exc:
            errors.append(f"unknown_capability:{exc}")
            caps = []
        if not caps:
            errors.append("missing_field:capabilities")
        purpose = case.get("test_purpose")
        errors.extend(
            validate_test_purpose(
                purpose if isinstance(purpose, Mapping) else None,
                prompt=str(case.get("prompt") or ""),
                capabilities=caps,
            )
        )
        # T0 contracts: session + long-context fields when present / required.
        errors.extend(validate_session_case_fields(case))
        errors.extend(validate_case_long_context_fields(case))
        return errors

    def execute(
        self, case: Mapping[str, Any], env: Mapping[str, Any] | None = None
    ) -> Dict[str, Any]:
        from core.apps.eval.service.mock_tools.harness import (
            MockToolHarnessError,
            invoke_mock_tools,
            resolve_scripted_tool_calls,
        )
        from core.apps.eval.service.tool_eval_runtime_map import (
            assert_mock_not_claimed_as_live,
            validate_tool_backend_runtime,
        )

        caps = resolve_capability_ids(
            list((case or {}).get("capabilities") or []), fail_closed=False
        )
        tool_caps = {"tool_selection", "tool_args", "tool_result_use"} & set(caps)
        text_caps = {"long_context", "multi_turn_memory"} & set(caps)
        env_map = dict(env or {})
        answer = str(
            env_map.get("answer")
            or env_map.get("scripted_answer")
            or case.get("scripted_answer")
            or ""
        )

        if text_caps and not tool_caps:
            return {
                "schema": ADAPTER_SCHEMA,
                "status": "ok",
                "subject_kind": self.subject_kind,
                "tool_backend": "none",
                "runtime_tier": "fixture",
                "runtime_claim": False,
                "runtime_claim_reason": "scripted_text_fixture",
                "ok": True,
                "answer": answer,
                "scripted_answer": answer,
            }

        if not tool_caps:
            return {
                "schema": ADAPTER_SCHEMA,
                "status": "not_implemented",
                "subject_kind": self.subject_kind,
                "reason": "agent_execute_deferred_non_tool",
            }

        try:
            calls = resolve_scripted_tool_calls(case, env_map)
            harness = invoke_mock_tools(
                calls,
                case=case,
                fail_mode=str(env_map.get("fail_mode") or "") or None,
            )
        except MockToolHarnessError as exc:
            return {
                "schema": ADAPTER_SCHEMA,
                "status": "error",
                "subject_kind": self.subject_kind,
                "tool_backend": "mock",
                "runtime_tier": "fixture",
                "runtime_claim": False,
                "runtime_claim_reason": "mock_harness_error",
                "error": str(exc),
                "ok": False,
            }

        claim_errs = assert_mock_not_claimed_as_live(
            tool_backend="mock",
            runtime_claim_reason=str(env_map.get("runtime_claim_reason") or ""),
        )
        tier_errs = validate_tool_backend_runtime(
            tool_backend="mock", runtime_tier="fixture"
        )
        return {
            "schema": ADAPTER_SCHEMA,
            "status": "ok" if harness.get("ok") and not claim_errs and not tier_errs else "error",
            "subject_kind": self.subject_kind,
            "tool_backend": "mock",
            "runtime_tier": "fixture",
            "runtime_claim": False,
            "runtime_claim_reason": "mock_tool_trace_only",
            "ok": bool(harness.get("ok")) and not claim_errs and not tier_errs,
            "tool_calls": harness.get("tool_calls") or [],
            "tool_results": harness.get("tool_results") or [],
            "allowed_tools": harness.get("allowed_tools") or [],
            "answer": answer,
            "scripted_answer": answer,
            "harness": harness,
            "gate_errors": claim_errs + tier_errs,
        }

    def judge(self, case: Mapping[str, Any], result: Mapping[str, Any]) -> Dict[str, Any]:
        from core.apps.eval.service.long_context_generator import judge_long_context
        from core.apps.eval.service.tool_trace_judge import judge_tool_trace

        caps = resolve_capability_ids(
            list((case or {}).get("capabilities") or []), fail_closed=False
        )
        tool_caps = {"tool_selection", "tool_args", "tool_result_use"} & set(caps)
        res = result if isinstance(result, Mapping) else {}
        if "long_context" in caps:
            judgment = judge_long_context(case, res)
            return {
                "schema": ADAPTER_SCHEMA,
                "status": "ok",
                "subject_kind": self.subject_kind,
                "passed": bool(judgment.get("passed")),
                "errors": list(judgment.get("errors") or []),
                "judgments": {"long_context": judgment},
                "tool_backend": str(res.get("tool_backend") or "none"),
            }
        if tool_caps:
            judgment = judge_tool_trace(case, res)
            return {
                "schema": ADAPTER_SCHEMA,
                "status": judgment.get("status") or "ok",
                "subject_kind": self.subject_kind,
                **judgment,
            }
        if "multi_turn_memory" in caps:
            # Group-level judging is session_runner; single-turn scripted smoke.
            answer = str(res.get("answer") or res.get("scripted_answer") or "")
            ok = bool(answer.strip())
            return {
                "schema": ADAPTER_SCHEMA,
                "status": "ok",
                "subject_kind": self.subject_kind,
                "passed": ok,
                "errors": [] if ok else ["missing_answer"],
                "tool_backend": "none",
            }
        return {
            "schema": ADAPTER_SCHEMA,
            "status": "not_implemented",
            "subject_kind": self.subject_kind,
            "reason": "agent_judge_deferred_non_tool",
        }

    def normalize(
        self,
        case: Mapping[str, Any],
        result: Mapping[str, Any],
        judgment: Mapping[str, Any],
    ) -> Dict[str, Any]:
        from core.apps.eval.service.capability_id_map import is_v1_in_scope

        caps = resolve_capability_ids(
            list((case or {}).get("capabilities") or []), fail_closed=False
        )
        handled = {
            "tool_selection",
            "tool_args",
            "tool_result_use",
            "long_context",
            "multi_turn_memory",
        } & set(caps)
        if not handled:
            return {
                "schema": ADAPTER_SCHEMA,
                "status": "not_implemented",
                "subject_kind": self.subject_kind,
                "reason": "agent_normalize_deferred_non_tool",
            }
        return {
            "schema": ADAPTER_SCHEMA,
            "status": "ok",
            "subject_kind": self.subject_kind,
            "passed": bool(judgment.get("passed")),
            "errors": list(judgment.get("errors") or []),
            "tool_backend": str(
                (result or {}).get("tool_backend")
                or judgment.get("tool_backend")
                or "none"
            ),
            "runtime_tier": str((result or {}).get("runtime_tier") or "fixture"),
            "claim_eligible": False,
            "certification_eligible": False,
            "v1_in_scope": all(is_v1_in_scope(c) for c in caps) if caps else False,
            "capabilities": caps,
        }


class PromptSubjectAdapter:
    """Prompt Subject — lexical fixture path; reuses typed_plan oracle.

    Does not fork Plan/EvalStore. claim_eligible always false.
    """

    subject_kind = "prompt"

    def build_contract(
        self,
        *,
        object_id: str,
        object_version: str = "",
        capabilities: Optional[Sequence[str]] = None,
        tools: Optional[Sequence[str]] = None,
        permissions: Optional[Sequence[str]] = None,
        roles: Optional[Sequence[str]] = None,
        eval_profile: Optional[Mapping[str, Any]] = None,
        source_refs: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        caps = resolve_capability_ids(capabilities or (), fail_closed=True) if capabilities else None
        profile = dict(eval_profile or {})
        if caps is None and profile.get("capabilities"):
            profile["capabilities"] = resolve_capability_ids(
                list(profile.get("capabilities") or []), fail_closed=False
            )
        return build_contract_for_object_type(
            object_type="prompt",
            object_id=object_id,
            object_version=object_version,
            capabilities=caps,
            tools=tools,
            permissions=permissions,
            roles=roles,
            eval_profile=profile,
            source_refs=source_refs,
        )

    def capability_catalog(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for cid in sorted(PROMPT_V1_CAPS):
            rows.append(
                {
                    "capability_id": cid,
                    "object_types": ["prompt"],
                    "in_scope": cid in PROMPT_V1_CAPS,
                    "v1_unknown": False,
                    "agent_canonical": cid in CANONICAL_IDS,
                    "agent_v1_in_scope": cid in V1_IN_SCOPE,
                }
            )
        return rows

    def validate_case(self, case: Mapping[str, Any]) -> List[str]:
        errors: List[str] = []
        if not isinstance(case, Mapping):
            return ["invalid_case"]
        case_id = str(case.get("case_id") or "").strip()
        if not case_id:
            errors.append("missing_field:case_id")
        caps_raw = case.get("capabilities")
        try:
            caps = resolve_capability_ids(list(caps_raw or []), fail_closed=True)
        except UnknownCapabilityId as exc:
            errors.append(f"unknown_capability:{exc}")
            caps = []
        if not caps:
            errors.append("missing_field:capabilities")
        for c in caps:
            if c not in PROMPT_V1_CAPS:
                errors.append(f"prompt_cap_out_of_scope:{c}")
        prompt = str(case.get("prompt") or case.get("user_input") or "").strip()
        if not prompt:
            errors.append("missing_field:prompt")
        crit = case.get("success_criteria")
        if crit is not None and not isinstance(crit, Mapping):
            errors.append("invalid_field:success_criteria")
        purpose = case.get("test_purpose")
        errors.extend(
            validate_test_purpose(
                purpose if isinstance(purpose, Mapping) else None,
                prompt=prompt,
                capabilities=caps,
            )
        )
        return errors

    def execute(
        self, case: Mapping[str, Any], env: Mapping[str, Any] | None = None
    ) -> Dict[str, Any]:
        from core.apps.eval.service.typed_plan_exam import dry_stub_output

        env_map = dict(env or {})
        if bool(env_map.get("live")):
            return {
                "schema": ADAPTER_SCHEMA,
                "status": "not_implemented",
                "subject_kind": self.subject_kind,
                "reason": "prompt_live_via_typed_plan_exam",
                "runtime_tier": "fixture",
                "runtime_claim": False,
                "ok": False,
            }
        answer = str(
            env_map.get("answer")
            or env_map.get("scripted_answer")
            or case.get("scripted_answer")
            or ""
        ).strip()
        if not answer:
            task = {
                "task_id": str(case.get("case_id") or ""),
                "category": str(case.get("category") or ""),
                "user_input": str(case.get("prompt") or case.get("user_input") or ""),
                "success_criteria": case.get("success_criteria")
                if isinstance(case.get("success_criteria"), Mapping)
                else {},
            }
            answer = dry_stub_output(task)
        return {
            "schema": ADAPTER_SCHEMA,
            "status": "ok",
            "subject_kind": self.subject_kind,
            "tool_backend": "none",
            "runtime_tier": "fixture",
            "runtime_claim": False,
            "runtime_claim_reason": "prompt_lexical_fixture_stub",
            "ok": True,
            "answer": answer,
            "scripted_answer": answer,
        }

    def judge(self, case: Mapping[str, Any], result: Mapping[str, Any]) -> Dict[str, Any]:
        from core.apps.eval.service.typed_plan_exam import score_lexical_output

        res = result if isinstance(result, Mapping) else {}
        answer = str(res.get("answer") or res.get("scripted_answer") or "")
        crit = case.get("success_criteria") if isinstance(case.get("success_criteria"), Mapping) else {}
        scored = score_lexical_output(answer, crit)
        status = str(scored.get("status") or "inconclusive")
        passed = status == "pass"
        errors: List[str] = []
        if status == "fail":
            errors.append(str(scored.get("summary") or "lexical_fail"))
        elif status == "inconclusive":
            errors.append("lexical_inconclusive")
        return {
            "schema": ADAPTER_SCHEMA,
            "status": "ok",
            "subject_kind": self.subject_kind,
            "passed": passed,
            "errors": errors,
            "lexical": scored,
            "tool_backend": "none",
        }

    def normalize(
        self,
        case: Mapping[str, Any],
        result: Mapping[str, Any],
        judgment: Mapping[str, Any],
    ) -> Dict[str, Any]:
        caps = resolve_capability_ids(
            list((case or {}).get("capabilities") or []), fail_closed=False
        )
        return {
            "schema": ADAPTER_SCHEMA,
            "status": "ok",
            "subject_kind": self.subject_kind,
            "passed": bool(judgment.get("passed")),
            "errors": list(judgment.get("errors") or []),
            "tool_backend": "none",
            "runtime_tier": str((result or {}).get("runtime_tier") or "fixture"),
            "claim_eligible": False,
            "certification_eligible": False,
            "v1_in_scope": all(c in PROMPT_V1_CAPS for c in caps) if caps else False,
            "capabilities": caps,
        }


_REGISTRY: Dict[str, EvalSubjectAdapter] = {
    "agent": AgentSubjectAdapter(),
    "prompt": PromptSubjectAdapter(),
}


def get_subject_adapter(subject_kind: str) -> EvalSubjectAdapter:
    kind = (subject_kind or "").strip().lower()
    adapter = _REGISTRY.get(kind)
    if adapter is None:
        raise ValueError(f"no_subject_adapter:{kind or '(empty)'}")
    return adapter


def list_subject_kinds() -> List[str]:
    return sorted(_REGISTRY.keys())
