"""EvalSubjectAdapter — Subject×Capability×Method×Evidence P0 skeleton.

Agent is the reference implementation. Prompt / Workflow / Model are typed
lexical Subjects; KB / Code Review / Session / Tool are fixture Subjects
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

# Workflow v1 measurable subset (maps from typed workflow/* packs + defaults).
WORKFLOW_V1_CAPS = frozenset(
    {
        "task_completion",  # basic stage delivery
        "clarification",  # missing_input
        "error_recovery",  # stage_failure
        "planning",  # long_chain
        "safety",
        "robustness",  # noise
    }
)

# Model v1 measurable subset (maps from typed model/* packs + defaults).
MODEL_V1_CAPS = frozenset(
    {
        "task_completion",  # basic / format_constraint / consistency
        "clarification",  # missing_info
        "safety",
        "robustness",  # noise
    }
)

# KB/RAG v1 measurable subset (fixture hits / expected_ids; mirrors package kb_rag).
# Not a first-class OBJECT_TYPES member yet — SubjectAdapter registry only.
KB_V1_CAPS = frozenset(
    {
        "task_completion",  # hit cover / expected_ids
        "safety",  # policy/source gate via expected_ids
        "robustness",  # noise hits still cover expected
    }
)

# Code Review v1 measurable subset (findings vs gold exact set; mirrors code_review_gold).
# Not a first-class OBJECT_TYPES member yet — SubjectAdapter registry only.
CODE_REVIEW_V1_CAPS = frozenset(
    {
        "task_completion",  # exact gold set match
        "safety",  # security finding gold
        "robustness",  # order-insensitive set equality
    }
)

# Session v1 measurable subset (multi-turn fixture; mirrors package session_eval).
# Not a first-class OBJECT_TYPES member yet — SubjectAdapter registry only.
SESSION_V1_CAPS = frozenset(
    {
        "task_completion",  # per-turn exact / non-empty
        "multi_turn_memory",  # later turn recalls planted token
        "clarification",  # ask-for-info exact
    }
)

# Tool/MCP v1 measurable subset (mock tool_trace; reuses Agent A3–A5 harness/judge).
# Not a first-class OBJECT_TYPES member yet — SubjectAdapter registry only.
TOOL_V1_CAPS = frozenset(
    {
        "tool_selection",  # A3 expected/forbidden tools
        "tool_args",  # A4 schema / expected args
        "tool_result_use",  # A5 answer uses tool result
    }
)

# session_eval profile bounds (engineering only; accuracy_claim=false).
_SESSION_PROFILE_BOUNDS = {
    "v0": (2, 3),
    "v1": (5, 8),
}


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


class _TypedLexicalSubjectAdapter:
    """Shared lexical fixture Subject for prompt/workflow/model typed packs.

    Does not fork Plan/EvalStore. claim_eligible always false.
    """

    subject_kind: str = ""
    object_type: str = ""
    v1_caps: frozenset = frozenset()
    live_reason: str = "typed_plan_live_deferred"
    runtime_claim_reason: str = "lexical_fixture_stub"

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
            object_type=self.object_type,
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
        for cid in sorted(self.v1_caps):
            rows.append(
                {
                    "capability_id": cid,
                    "object_types": [self.object_type],
                    "in_scope": cid in self.v1_caps,
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
            if c not in self.v1_caps:
                errors.append(f"{self.subject_kind}_cap_out_of_scope:{c}")
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
                "reason": self.live_reason,
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
            "runtime_claim_reason": self.runtime_claim_reason,
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
            "v1_in_scope": all(c in self.v1_caps for c in caps) if caps else False,
            "capabilities": caps,
        }


class PromptSubjectAdapter(_TypedLexicalSubjectAdapter):
    """Prompt Subject — lexical fixture path; reuses typed_plan oracle."""

    subject_kind = "prompt"
    object_type = "prompt"
    v1_caps = PROMPT_V1_CAPS
    live_reason = "prompt_live_via_typed_plan_exam"
    runtime_claim_reason = "prompt_lexical_fixture_stub"


class WorkflowSubjectAdapter(_TypedLexicalSubjectAdapter):
    """Workflow Subject — lexical fixture path; reuses typed_plan oracle."""

    subject_kind = "workflow"
    object_type = "workflow"
    v1_caps = WORKFLOW_V1_CAPS
    live_reason = "workflow_live_via_typed_plan_exam"
    runtime_claim_reason = "workflow_lexical_fixture_stub"


class ModelSubjectAdapter(_TypedLexicalSubjectAdapter):
    """Model Subject — lexical fixture path; reuses typed_plan oracle."""

    subject_kind = "model"
    object_type = "model"
    v1_caps = MODEL_V1_CAPS
    live_reason = "model_live_via_typed_plan_exam"
    runtime_claim_reason = "model_lexical_fixture_stub"


def _kb_fixture_hits(case: Mapping[str, Any], env: Mapping[str, Any] | None) -> List[Any]:
    env_map = dict(env or {})
    hits = env_map.get("hits")
    if hits is None:
        hits = case.get("hits")
    if hits is None:
        hits = case.get("docs")
    return list(hits) if isinstance(hits, list) else []


def _kb_hit_ids(hits: Sequence[Any]) -> List[Any]:
    got: List[Any] = []
    for h in hits:
        if isinstance(h, Mapping) and h.get("id") is not None:
            got.append(h.get("id"))
        elif isinstance(h, str):
            got.append(h)
    return got


class KbSubjectAdapter:
    """KB/RAG Subject — readonly retrieval fixture (mirrors package kb_rag oracle).

    Not in OBJECT_TYPES yet; contract is Subject-local. claim_eligible always false.
    """

    subject_kind = "kb"
    v1_caps = KB_V1_CAPS

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
        caps = (
            resolve_capability_ids(capabilities or (), fail_closed=True)
            if capabilities
            else None
        )
        profile = dict(eval_profile or {})
        if caps is None and profile.get("capabilities"):
            caps = resolve_capability_ids(
                list(profile.get("capabilities") or []), fail_closed=False
            )
        return {
            "schema": ADAPTER_SCHEMA,
            "subject_kind": self.subject_kind,
            "object_type_registered": False,
            "object_id": str(object_id or "").strip(),
            "object_version": str(object_version or "").strip() or "version_unspecified",
            "capabilities": list(caps or profile.get("capabilities") or []),
            "tools": list(tools or profile.get("tools") or []),
            "permissions": list(permissions or profile.get("permissions") or []),
            "roles": list(roles or profile.get("roles") or []),
            "target_runtime": list(profile.get("target_runtime") or ["fixture", "kb_rag"]),
            "eval_purpose": list(profile.get("eval_purpose") or ["behavior", "regression"]),
            "source_refs": list(source_refs or profile.get("source_refs") or ["kb_rag"]),
            "claim_eligible": False,
            "honesty": (
                "kb SubjectAdapter only — not first-class OBJECT_TYPES; "
                "fixture hits/expected_ids ≠ live RAG accuracy"
            ),
        }

    def capability_catalog(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for cid in sorted(self.v1_caps):
            rows.append(
                {
                    "capability_id": cid,
                    "object_types": ["kb"],
                    "in_scope": cid in self.v1_caps,
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
            if c not in self.v1_caps:
                errors.append(f"kb_cap_out_of_scope:{c}")
        query = str(case.get("query") or case.get("prompt") or "").strip()
        if not query:
            errors.append("missing_field:query")
        hits = case.get("hits")
        if hits is None:
            hits = case.get("docs")
        if hits is not None and not isinstance(hits, list):
            errors.append("invalid_field:hits")
        expected = case.get("expected_ids")
        if expected is not None and not isinstance(expected, list):
            errors.append("invalid_field:expected_ids")
        purpose = case.get("test_purpose")
        errors.extend(
            validate_test_purpose(
                purpose if isinstance(purpose, Mapping) else None,
                prompt=query,
                capabilities=caps,
            )
        )
        return errors

    def execute(
        self, case: Mapping[str, Any], env: Mapping[str, Any] | None = None
    ) -> Dict[str, Any]:
        env_map = dict(env or {})
        if bool(env_map.get("live")):
            return {
                "schema": ADAPTER_SCHEMA,
                "status": "not_implemented",
                "subject_kind": self.subject_kind,
                "reason": "kb_live_retrieve_deferred",
                "runtime_tier": "fixture",
                "runtime_claim": False,
                "ok": False,
            }
        hits = _kb_fixture_hits(case, env_map)
        query = str(case.get("query") or case.get("prompt") or "")
        expected = case.get("expected_ids") if isinstance(case.get("expected_ids"), list) else []
        return {
            "schema": ADAPTER_SCHEMA,
            "status": "ok",
            "subject_kind": self.subject_kind,
            "tool_backend": "none",
            "runtime_tier": "fixture",
            "runtime_claim": False,
            "runtime_claim_reason": "kb_retrieval_fixture",
            "ok": True,
            "query": query,
            "hits": hits,
            "expected_ids": list(expected),
            "readonly": True,
        }

    def judge(self, case: Mapping[str, Any], result: Mapping[str, Any]) -> Dict[str, Any]:
        res = result if isinstance(result, Mapping) else {}
        hits = res.get("hits") if isinstance(res.get("hits"), list) else []
        errors: List[str] = []
        if not hits:
            return {
                "schema": ADAPTER_SCHEMA,
                "status": "ok",
                "subject_kind": self.subject_kind,
                "passed": False,
                "errors": ["missing_hits"],
                "tool_backend": "none",
                "hit_count": 0,
            }
        expected = case.get("expected_ids")
        if isinstance(expected, list) and expected:
            got = _kb_hit_ids(hits)
            passed = all(eid in got for eid in expected)
            if not passed:
                errors.append("expected_ids_not_covered")
        else:
            passed = len(hits) > 0
        return {
            "schema": ADAPTER_SCHEMA,
            "status": "ok",
            "subject_kind": self.subject_kind,
            "passed": passed,
            "errors": errors,
            "tool_backend": "none",
            "hit_count": len(hits),
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
            "v1_in_scope": all(c in self.v1_caps for c in caps) if caps else False,
            "capabilities": caps,
            "hit_count": int(judgment.get("hit_count") or 0),
        }


class CodeReviewSubjectAdapter:
    """Code Review Subject — gold finding set match (mirrors package code_review_gold).

    Not in OBJECT_TYPES yet; contract is Subject-local. claim_eligible always false.
    """

    subject_kind = "code_review"
    v1_caps = CODE_REVIEW_V1_CAPS

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
        caps = (
            resolve_capability_ids(capabilities or (), fail_closed=True)
            if capabilities
            else None
        )
        profile = dict(eval_profile or {})
        if caps is None and profile.get("capabilities"):
            caps = resolve_capability_ids(
                list(profile.get("capabilities") or []), fail_closed=False
            )
        return {
            "schema": ADAPTER_SCHEMA,
            "subject_kind": self.subject_kind,
            "object_type_registered": False,
            "object_id": str(object_id or "").strip(),
            "object_version": str(object_version or "").strip() or "version_unspecified",
            "capabilities": list(caps or profile.get("capabilities") or []),
            "tools": list(tools or profile.get("tools") or []),
            "permissions": list(permissions or profile.get("permissions") or []),
            "roles": list(roles or profile.get("roles") or []),
            "target_runtime": list(
                profile.get("target_runtime") or ["fixture", "code_review_gold"]
            ),
            "eval_purpose": list(profile.get("eval_purpose") or ["behavior", "regression"]),
            "source_refs": list(
                source_refs or profile.get("source_refs") or ["code_review_gold"]
            ),
            "claim_eligible": False,
            "honesty": (
                "code_review SubjectAdapter only — not first-class OBJECT_TYPES; "
                "fixture findings/gold exact set ≠ live autoreview E2E"
            ),
        }

    def capability_catalog(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for cid in sorted(self.v1_caps):
            rows.append(
                {
                    "capability_id": cid,
                    "object_types": ["code_review"],
                    "in_scope": cid in self.v1_caps,
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
            if c not in self.v1_caps:
                errors.append(f"code_review_cap_out_of_scope:{c}")
        prompt = str(case.get("prompt") or case.get("query") or "").strip()
        if not prompt:
            errors.append("missing_field:prompt")
        findings = case.get("findings")
        if findings is not None and not isinstance(findings, list):
            errors.append("invalid_field:findings")
        gold = case.get("gold")
        if gold is None:
            errors.append("missing_field:gold")
        elif not isinstance(gold, list):
            errors.append("invalid_field:gold")
        elif not gold:
            errors.append("empty_field:gold")
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
        env_map = dict(env or {})
        if bool(env_map.get("live")):
            return {
                "schema": ADAPTER_SCHEMA,
                "status": "not_implemented",
                "subject_kind": self.subject_kind,
                "reason": "code_review_live_autoreview_deferred",
                "runtime_tier": "fixture",
                "runtime_claim": False,
                "ok": False,
            }
        findings = env_map.get("findings")
        if findings is None:
            findings = case.get("findings")
        findings_list = list(findings) if isinstance(findings, list) else []
        gold = case.get("gold") if isinstance(case.get("gold"), list) else []
        return {
            "schema": ADAPTER_SCHEMA,
            "status": "ok",
            "subject_kind": self.subject_kind,
            "tool_backend": "none",
            "runtime_tier": "fixture",
            "runtime_claim": False,
            "runtime_claim_reason": "code_review_gold_fixture",
            "ok": True,
            "findings": findings_list,
            "gold": list(gold),
        }

    def judge(self, case: Mapping[str, Any], result: Mapping[str, Any]) -> Dict[str, Any]:
        res = result if isinstance(result, Mapping) else {}
        findings = res.get("findings") if isinstance(res.get("findings"), list) else []
        gold = case.get("gold") if isinstance(case.get("gold"), list) else []
        if not gold:
            # Prefer result gold only if case omitted (should not pass validate).
            gold = res.get("gold") if isinstance(res.get("gold"), list) else []
        if not gold:
            return {
                "schema": ADAPTER_SCHEMA,
                "status": "ok",
                "subject_kind": self.subject_kind,
                "passed": False,
                "errors": ["missing_gold"],
                "tool_backend": "none",
                "exact_set_match": False,
            }
        norm_f = sorted(str(x) for x in findings)
        norm_g = sorted(str(x) for x in gold)
        passed = norm_f == norm_g
        return {
            "schema": ADAPTER_SCHEMA,
            "status": "ok",
            "subject_kind": self.subject_kind,
            "passed": passed,
            "errors": [] if passed else ["findings_ne_gold"],
            "tool_backend": "none",
            "exact_set_match": passed,
            "finding_count": len(findings),
            "gold_count": len(gold),
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
            "v1_in_scope": all(c in self.v1_caps for c in caps) if caps else False,
            "capabilities": caps,
            "exact_set_match": bool(judgment.get("exact_set_match")),
        }


class SessionSubjectAdapter:
    """Session Subject — multi-turn fixture (mirrors package session_eval).

    Not in OBJECT_TYPES yet; contract is Subject-local. claim_eligible always false.
    """

    subject_kind = "session"
    v1_caps = SESSION_V1_CAPS

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
        caps = (
            resolve_capability_ids(capabilities or (), fail_closed=True)
            if capabilities
            else None
        )
        profile = dict(eval_profile or {})
        if caps is None and profile.get("capabilities"):
            caps = resolve_capability_ids(
                list(profile.get("capabilities") or []), fail_closed=False
            )
        return {
            "schema": ADAPTER_SCHEMA,
            "subject_kind": self.subject_kind,
            "object_type_registered": False,
            "object_id": str(object_id or "").strip(),
            "object_version": str(object_version or "").strip() or "version_unspecified",
            "capabilities": list(caps or profile.get("capabilities") or []),
            "tools": list(tools or profile.get("tools") or []),
            "permissions": list(permissions or profile.get("permissions") or []),
            "roles": list(roles or profile.get("roles") or []),
            "target_runtime": list(
                profile.get("target_runtime") or ["fixture", "session_eval"]
            ),
            "eval_purpose": list(profile.get("eval_purpose") or ["behavior", "regression"]),
            "source_refs": list(
                source_refs or profile.get("source_refs") or ["session_eval"]
            ),
            "claim_eligible": False,
            "honesty": (
                "session SubjectAdapter only — not first-class OBJECT_TYPES; "
                "fixture multi-turn exact/non-empty ≠ long-horizon Agent memory"
            ),
        }

    def capability_catalog(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for cid in sorted(self.v1_caps):
            rows.append(
                {
                    "capability_id": cid,
                    "object_types": ["session"],
                    "in_scope": cid in self.v1_caps,
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
            if c not in self.v1_caps:
                errors.append(f"session_cap_out_of_scope:{c}")
        turns = case.get("turns") or case.get("messages")
        if turns is None:
            errors.append("missing_field:turns")
            turns_list: List[Any] = []
        elif not isinstance(turns, list):
            errors.append("invalid_field:turns")
            turns_list = []
        else:
            turns_list = list(turns)
        profile = str(case.get("profile") or case.get("session_version") or "v0").strip().lower()
        if profile not in _SESSION_PROFILE_BOUNDS:
            errors.append(f"invalid_field:profile:{profile}")
            profile = "v0"
        min_t, max_t = _SESSION_PROFILE_BOUNDS[profile]
        if turns_list and not (min_t <= len(turns_list) <= max_t):
            errors.append(f"turns_out_of_profile:{profile}:{len(turns_list)}")
        prompt = ""
        for t in turns_list:
            if not isinstance(t, Mapping):
                errors.append("invalid_field:turn")
                continue
            turn_prompt = str(
                t.get("prompt") or t.get("user") or t.get("input") or ""
            ).strip()
            if not turn_prompt:
                errors.append("missing_field:turn.prompt")
            if not prompt:
                prompt = turn_prompt
        if not prompt:
            errors.append("missing_field:prompt")
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
        env_map = dict(env or {})
        if bool(env_map.get("live")):
            return {
                "schema": ADAPTER_SCHEMA,
                "status": "not_implemented",
                "subject_kind": self.subject_kind,
                "reason": "session_live_agent_deferred",
                "runtime_tier": "fixture",
                "runtime_claim": False,
                "ok": False,
            }
        raw_turns = env_map.get("turns")
        if raw_turns is None:
            raw_turns = case.get("turns") or case.get("messages") or []
        turns_list = list(raw_turns) if isinstance(raw_turns, list) else []
        profile = str(
            case.get("profile") or case.get("session_version") or "v0"
        ).strip().lower()
        if profile not in _SESSION_PROFILE_BOUNDS:
            profile = "v0"
        session_id = str(
            case.get("session_id") or case.get("conversation_id") or case.get("case_id") or ""
        )
        return {
            "schema": ADAPTER_SCHEMA,
            "status": "ok",
            "subject_kind": self.subject_kind,
            "tool_backend": "none",
            "runtime_tier": "fixture",
            "runtime_claim": False,
            "runtime_claim_reason": "session_eval_fixture",
            "ok": True,
            "turns": turns_list,
            "profile": profile,
            "session_id": session_id,
        }

    def judge(self, case: Mapping[str, Any], result: Mapping[str, Any]) -> Dict[str, Any]:
        res = result if isinstance(result, Mapping) else {}
        turns = res.get("turns") if isinstance(res.get("turns"), list) else []
        if not turns:
            turns = case.get("turns") if isinstance(case.get("turns"), list) else []
        profile = str(
            res.get("profile")
            or case.get("profile")
            or case.get("session_version")
            or "v0"
        ).strip().lower()
        if profile not in _SESSION_PROFILE_BOUNDS:
            profile = "v0"
        min_t, max_t = _SESSION_PROFILE_BOUNDS[profile]
        n = len(turns)
        turn_oks: List[bool] = []
        turn_details: List[Dict[str, Any]] = []
        for i, turn in enumerate(turns):
            if not isinstance(turn, Mapping):
                turn_oks.append(False)
                turn_details.append({"i": i, "ok": False, "exact_match": 0.0})
                continue
            expected = str(turn.get("expected") or turn.get("expected_text") or "")
            actual = str(
                turn.get("actual") or turn.get("output") or turn.get("assistant") or ""
            )
            if expected:
                ok = actual == expected
                exact = 1.0 if ok else 0.0
            else:
                ok = bool(actual.strip())
                exact = 0.0
            turn_oks.append(ok)
            turn_details.append(
                {
                    "i": i,
                    "ok": ok,
                    "exact_match": exact,
                    "actual_len": len(actual),
                }
            )
        n_ok = sum(1 for x in turn_oks if x)
        rate = round(n_ok / float(n), 4) if n else 0.0
        in_range = min_t <= n <= max_t
        passed = bool(in_range and n_ok == n and n > 0)
        errors: List[str] = []
        if n < min_t:
            errors.append(f"turns_below_min:{profile}:{n}<{min_t}")
        elif n > max_t:
            errors.append(f"turns_above_max:{profile}:{n}>{max_t}")
        if n and n_ok != n:
            errors.append("turn_failures")
        if n == 0:
            errors.append("missing_turns")
        return {
            "schema": ADAPTER_SCHEMA,
            "status": "ok",
            "subject_kind": self.subject_kind,
            "passed": passed,
            "errors": errors,
            "tool_backend": "none",
            "session_pass": passed,
            "turns_n": n,
            "turns_ok": n_ok,
            "turn_success_rate": rate,
            "profile": profile,
            "turns": turn_details,
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
            "v1_in_scope": all(c in self.v1_caps for c in caps) if caps else False,
            "capabilities": caps,
            "session_pass": bool(judgment.get("session_pass")),
            "turn_success_rate": judgment.get("turn_success_rate"),
        }


class ToolSubjectAdapter:
    """Tool/MCP Subject — mock tool_trace (reuses harness + judge_tool_trace).

    Not in OBJECT_TYPES yet; contract is Subject-local. claim_eligible always false.
    Live tools / real MCP deferred (runtime_tier=fixture only).
    """

    subject_kind = "tool"
    v1_caps = TOOL_V1_CAPS

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
        caps = (
            resolve_capability_ids(capabilities or (), fail_closed=True)
            if capabilities
            else None
        )
        profile = dict(eval_profile or {})
        if caps is None and profile.get("capabilities"):
            caps = resolve_capability_ids(
                list(profile.get("capabilities") or []), fail_closed=False
            )
        return {
            "schema": ADAPTER_SCHEMA,
            "subject_kind": self.subject_kind,
            "object_type_registered": False,
            "object_id": str(object_id or "").strip(),
            "object_version": str(object_version or "").strip() or "version_unspecified",
            "capabilities": list(caps or profile.get("capabilities") or []),
            "tools": list(tools or profile.get("tools") or []),
            "permissions": list(permissions or profile.get("permissions") or []),
            "roles": list(roles or profile.get("roles") or []),
            "target_runtime": list(
                profile.get("target_runtime") or ["fixture", "mock_tools"]
            ),
            "eval_purpose": list(profile.get("eval_purpose") or ["behavior", "regression"]),
            "source_refs": list(
                source_refs or profile.get("source_refs") or ["tool_trace_judge", "mock_tools"]
            ),
            "claim_eligible": False,
            "honesty": (
                "tool SubjectAdapter only — not first-class OBJECT_TYPES; "
                "mock tool_trace ≠ live tools / real MCP"
            ),
        }

    def capability_catalog(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for cid in sorted(self.v1_caps):
            rows.append(
                {
                    "capability_id": cid,
                    "object_types": ["tool"],
                    "in_scope": cid in self.v1_caps,
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
            if c not in self.v1_caps:
                errors.append(f"tool_cap_out_of_scope:{c}")
        prompt = str(case.get("prompt") or case.get("query") or "").strip()
        if not prompt:
            errors.append("missing_field:prompt")
        calls = case.get("scripted_tool_calls")
        if calls is None:
            errors.append("missing_field:scripted_tool_calls")
        elif not isinstance(calls, list):
            errors.append("invalid_field:scripted_tool_calls")
        elif not calls:
            errors.append("empty_field:scripted_tool_calls")
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
        from core.apps.eval.service.mock_tools.harness import (
            MockToolHarnessError,
            invoke_mock_tools,
            resolve_scripted_tool_calls,
        )
        from core.apps.eval.service.tool_eval_runtime_map import (
            assert_mock_not_claimed_as_live,
            validate_tool_backend_runtime,
        )

        env_map = dict(env or {})
        if bool(env_map.get("live")):
            return {
                "schema": ADAPTER_SCHEMA,
                "status": "not_implemented",
                "subject_kind": self.subject_kind,
                "reason": "tool_live_mcp_deferred",
                "runtime_tier": "fixture",
                "runtime_claim": False,
                "ok": False,
            }
        answer = str(
            env_map.get("answer")
            or env_map.get("scripted_answer")
            or case.get("scripted_answer")
            or ""
        )
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
            "status": "ok"
            if harness.get("ok") and not claim_errs and not tier_errs
            else "error",
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
        from core.apps.eval.service.tool_trace_judge import judge_tool_trace

        res = result if isinstance(result, Mapping) else {}
        judgment = judge_tool_trace(case, res)
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
            "v1_in_scope": all(c in self.v1_caps for c in caps) if caps else False,
            "capabilities": caps,
        }


_REGISTRY: Dict[str, EvalSubjectAdapter] = {
    "agent": AgentSubjectAdapter(),
    "prompt": PromptSubjectAdapter(),
    "workflow": WorkflowSubjectAdapter(),
    "model": ModelSubjectAdapter(),
    "kb": KbSubjectAdapter(),
    "code_review": CodeReviewSubjectAdapter(),
    "session": SessionSubjectAdapter(),
    "tool": ToolSubjectAdapter(),
}


def get_subject_adapter(subject_kind: str) -> EvalSubjectAdapter:
    kind = (subject_kind or "").strip().lower()
    adapter = _REGISTRY.get(kind)
    if adapter is None:
        raise ValueError(f"no_subject_adapter:{kind or '(empty)'}")
    return adapter


def list_subject_kinds() -> List[str]:
    return sorted(_REGISTRY.keys())
