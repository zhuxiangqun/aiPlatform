"""EvalSubjectAdapter — Subject×Capability×Method×Evidence P0 skeleton.

Agent is the reference implementation. execute/judge/normalize stay stubs until
execution wiring; contract + capability catalog + case validate are live.
Core must dispatch via registry — no ``if object_type ==`` business piles here
beyond the type→adapter map.
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
        if not tool_caps:
            return {
                "schema": ADAPTER_SCHEMA,
                "status": "not_implemented",
                "subject_kind": self.subject_kind,
                "reason": "agent_execute_deferred_non_tool",
            }

        env_map = dict(env or {})
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
            "harness": harness,
            "gate_errors": claim_errs + tier_errs,
        }

    def judge(self, case: Mapping[str, Any], result: Mapping[str, Any]) -> Dict[str, Any]:
        from core.apps.eval.service.tool_trace_judge import judge_tool_trace

        caps = resolve_capability_ids(
            list((case or {}).get("capabilities") or []), fail_closed=False
        )
        tool_caps = {"tool_selection", "tool_args", "tool_result_use"} & set(caps)
        if not tool_caps:
            return {
                "schema": ADAPTER_SCHEMA,
                "status": "not_implemented",
                "subject_kind": self.subject_kind,
                "reason": "agent_judge_deferred_non_tool",
            }
        judgment = judge_tool_trace(case, result if isinstance(result, Mapping) else {})
        return {
            "schema": ADAPTER_SCHEMA,
            "status": judgment.get("status") or "ok",
            "subject_kind": self.subject_kind,
            **judgment,
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
        tool_caps = {"tool_selection", "tool_args", "tool_result_use"} & set(caps)
        if not tool_caps:
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
                or "mock"
            ),
            "runtime_tier": str((result or {}).get("runtime_tier") or "fixture"),
            "claim_eligible": False,
            "certification_eligible": False,
            "v1_in_scope": False,
            "capabilities": caps,
        }


_REGISTRY: Dict[str, EvalSubjectAdapter] = {
    "agent": AgentSubjectAdapter(),
}


def get_subject_adapter(subject_kind: str) -> EvalSubjectAdapter:
    kind = (subject_kind or "").strip().lower()
    adapter = _REGISTRY.get(kind)
    if adapter is None:
        raise ValueError(f"no_subject_adapter:{kind or '(empty)'}")
    return adapter


def list_subject_kinds() -> List[str]:
    return sorted(_REGISTRY.keys())
