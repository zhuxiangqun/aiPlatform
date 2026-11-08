"""Mode-aware Agent exam — M1a / M1b / M1c (react fixture sandbox).

Hard rules (eval-agent-impl-mode-exam.md):
- selection union ≠ execution union (per-mode create_agent / manifest / run)
- M1a: tools=retrieval=network=none; session only for conversational
- M1b: retrieval=required; tools=network=session=none
- M1c: tools+sandbox required; fixture_mock default; A3–A5 coverage unknown
- claim_eligible / rank_claim stay false
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.agent_impl_mode import (
    AgentImplModeError,
    load_mode_core_matrix,
    m1a_environment_lock,
    m1b_environment_lock,
    m1c_environment_lock,
    plan_executions_per_mode,
    resolve_impl_modes,
)
from core.apps.eval.service.capability_case_bank import default_seed_dir

_log = logging.getLogger(__name__)

M1A_MODES = ("plan_execute", "conversational")
M1B_MODES = ("rag",)
M1C_MODES = ("react",)
M1C_TOOL_CAPS_UNKNOWN = ("tool_selection", "tool_args", "tool_result_use")
EXAM_SCHEMA = "eval.mode_aware_exam.v1"


class ModeAwareExamError(ValueError):
    """Fail-closed mode exam error."""


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _config_hash(mode: str, lock: Mapping[str, Any]) -> str:
    blob = json.dumps(
        {"impl_mode": mode, "env_lock": dict(lock), "tools": []},
        sort_keys=True,
        ensure_ascii=False,
    )
    return _sha256_text(blob)


def load_m1a_mode_cases(
    mode: str,
    *,
    seed_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    path = root / "fixtures" / "mode_exam" / mode / "cases.json"
    if not path.is_file():
        raise ModeAwareExamError(f"m1a_cases_missing:{path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ModeAwareExamError(f"m1a_cases_not_array:{path}")
    return [dict(x) for x in raw if isinstance(x, Mapping)]


def enforce_m1a_environment(
    mode: str,
    observed: Mapping[str, Any] | None,
    *,
    matrix: Mapping[str, Any] | None = None,
) -> List[str]:
    """Return violation codes if tools/retrieval/network/session break M1a lock."""
    lock_all = m1a_environment_lock(matrix)
    lock = lock_all.get(mode) if isinstance(lock_all.get(mode), Mapping) else None
    if lock is None:
        return [f"m1a_lock_missing:{mode}"]
    obs = dict(observed or {})
    errors: List[str] = []

    tool_calls = list(obs.get("tool_calls") or [])
    if lock.get("tools") == "none" and tool_calls:
        errors.append("environment_violation:tools")
    if lock.get("retrieval") == "none" and (
        obs.get("retrieval_used") or obs.get("retrieval_hits")
    ):
        errors.append("environment_violation:retrieval")
    if lock.get("network") == "none" and obs.get("network_used"):
        errors.append("environment_violation:network")
    if lock.get("session") == "none" and (
        obs.get("session_group") or obs.get("session_id")
    ):
        # plan_execute must not carry session_group on cases during M1a
        errors.append("environment_violation:session")
    return errors


def _lexical_pass(answer: str, case: Mapping[str, Any]) -> bool:
    rubric = case.get("rubric") if isinstance(case.get("rubric"), Mapping) else {}
    must = [str(x) for x in (rubric.get("must_contain") or []) if str(x).strip()]
    forbid = [str(x) for x in (rubric.get("must_not_contain") or []) if str(x).strip()]
    text = str(answer or "")
    for m in must:
        if m not in text:
            return False
    for f in forbid:
        if f in text:
            return False
    return True


def _instantiate_mode_agent(mode: str) -> Any:
    """create_agent for mode with tools forced empty (M1a)."""
    from core.apps.agents.base import create_agent
    from core.harness.interfaces.agent import AgentConfig

    cfg = AgentConfig(name=f"eval-m1a-{mode}")
    # plan_execute accepts tools=; conversational uses internal _tools list.
    if mode == "plan_execute":
        agent = create_agent(mode, config=cfg, tools=[])
    else:
        agent = create_agent(mode, config=cfg)
    if hasattr(agent, "_tools"):
        agent._tools = []
    return agent


async def _execute_case_inprocess(
    mode: str,
    case: Mapping[str, Any],
    *,
    live: bool,
) -> Dict[str, Any]:
    """Run one case: always construct mode agent with tools=[].

    live=False → scripted_answer path after create_agent (CI).
    live=True → agent.execute (requires model); fail closed on error.
    """
    agent = _instantiate_mode_agent(mode)
    tools_attr = getattr(agent, "_tools", None)
    if tools_attr:
        return {
            "status": "error",
            "ok": False,
            "errors": ["environment_violation:tools_bound_on_agent"],
            "runtime_tier": "fixture",
            "execution_mode": mode,
        }

    prompt = str(case.get("prompt") or "")
    if not live:
        answer = str(case.get("scripted_answer") or "")
        observed = {
            "tool_calls": [],
            "retrieval_used": False,
            "network_used": False,
            "answer": answer,
        }
        if mode == "conversational" and case.get("session_group"):
            observed["session_group"] = case.get("session_group")
            observed["session_id"] = str(case.get("session_group"))
        violations = enforce_m1a_environment(mode, observed)
        passed = (not violations) and _lexical_pass(answer, case)
        return {
            "status": "ok" if passed else "fail",
            "ok": passed,
            "answer": answer,
            "errors": violations
            + ([] if _lexical_pass(answer, case) else ["lexical_fail"]),
            "runtime_tier": "fixture",
            "runtime_claim": False,
            "runtime_claim_reason": "m1a_scripted_after_create_agent_tools_empty",
            "execution_mode": mode,
            "tool_calls": [],
            "subject": {
                "agent_id": f"eval.m1a.{mode}",
                "agent_version": "m1a",
                "impl_mode": mode,
                "config_hash": _config_hash(mode, m1a_environment_lock().get(mode) or {}),
                "model_fingerprint": "scripted",
            },
        }

    # live path
    try:
        from core.harness.interfaces.agent import AgentContext

        ctx = AgentContext(
            session_id=f"m1a-{mode}",
            user_id="eval-m1a",
            messages=[{"role": "user", "content": prompt}],
            variables={"eval_m1a": True, "tools_allowed": []},
            tools=[],
        )
        result = await agent.execute(ctx)
        answer = ""
        if result is not None:
            answer = str(getattr(result, "output", None) or getattr(result, "content", None) or "")
        meta = getattr(result, "metadata", None) or {}
        tool_calls = list(meta.get("tool_calls") or []) if isinstance(meta, Mapping) else []
        observed = {
            "tool_calls": tool_calls,
            "retrieval_used": bool(meta.get("retrieval_used")) if isinstance(meta, Mapping) else False,
            "network_used": bool(meta.get("network_used")) if isinstance(meta, Mapping) else False,
            "answer": answer,
        }
        if mode == "conversational" and case.get("session_group"):
            observed["session_group"] = case.get("session_group")
        violations = enforce_m1a_environment(mode, observed)
        success = bool(getattr(result, "success", False)) and not violations
        return {
            "status": "ok" if success else "fail",
            "ok": success and _lexical_pass(answer, case),
            "answer": answer,
            "errors": violations
            + ([] if _lexical_pass(answer, case) else ["lexical_fail"]),
            "runtime_tier": "workspace_execute",
            "runtime_claim": False,
            "runtime_claim_reason": "m1a_inprocess_create_agent_live",
            "execution_mode": mode,
            "tool_calls": tool_calls,
            "agent_status": str(getattr(result, "status", "") or ""),
            "subject": {
                "agent_id": f"eval.m1a.{mode}",
                "agent_version": "m1a",
                "impl_mode": mode,
                "config_hash": _config_hash(mode, m1a_environment_lock().get(mode) or {}),
                "model_fingerprint": "live_unresolved",
            },
        }
    except Exception as exc:  # noqa: BLE001
        _log.warning("m1a live execute failed mode=%s: %s", mode, exc, exc_info=True)
        return {
            "status": "error",
            "ok": False,
            "errors": [f"live_execute_error:{type(exc).__name__}"],
            "runtime_tier": "workspace_execute",
            "runtime_claim": False,
            "runtime_claim_reason": "m1a_live_failed",
            "execution_mode": mode,
            "tool_calls": [],
        }


async def run_m1a_mode_exam(
    *,
    live: bool = False,
    modes: Optional[Sequence[str]] = None,
    seed_dir: Optional[Path] = None,
    max_cases_per_mode: int = 0,
) -> Dict[str, Any]:
    """M1a exam: plan_execute + conversational, separate runs, env lock enforced."""
    try:
        matrix = load_mode_core_matrix(
            path=(Path(seed_dir) / "mode_core_capabilities.v1.yaml")
            if seed_dir
            else None
        )
    except AgentImplModeError as exc:
        raise ModeAwareExamError(str(exc)) from exc

    wanted = [str(m).strip() for m in (modes or M1A_MODES) if str(m).strip()]
    for m in wanted:
        if m not in M1A_MODES:
            raise ModeAwareExamError(f"m1a_mode_not_allowed:{m}")

    columns: Dict[str, Any] = {}
    totals = {"modes": 0, "cases": 0, "pass": 0, "fail": 0, "error": 0}

    for mode in wanted:
        # Independent execution plan row (never merge with other modes).
        impl = resolve_impl_modes(
            {
                "impl_modes": {
                    "primary": mode,
                    "secondary": [],
                    "confidence": "explicit",
                    "source": "config",
                }
            }
        )
        exe_plan = plan_executions_per_mode(impl, matrix=matrix)
        cases = load_m1a_mode_cases(mode, seed_dir=seed_dir)
        if max_cases_per_mode > 0:
            cases = cases[: int(max_cases_per_mode)]

        # plan_execute must not use session on cases
        if mode == "plan_execute":
            for c in cases:
                if c.get("session_group"):
                    raise ModeAwareExamError(
                        f"plan_execute_session_forbidden:{c.get('case_id')}"
                    )

        results: List[Dict[str, Any]] = []
        for case in cases:
            # a6 subtype guard for plan_execute
            if mode == "plan_execute" and "error_recovery" in (
                case.get("capabilities") or []
            ):
                subtype = str(case.get("a6_subtype") or "")
                pe = (matrix.get("modes") or {}).get("plan_execute") or {}
                forbidden = set(pe.get("a6_forbidden_subtypes") or [])
                allowed = set(pe.get("a6_allowed_subtypes") or [])
                if subtype in forbidden or (allowed and subtype and subtype not in allowed):
                    results.append(
                        {
                            "case_id": case.get("case_id"),
                            "ok": False,
                            "status": "error",
                            "errors": [f"a6_subtype_forbidden:{subtype}"],
                        }
                    )
                    totals["error"] += 1
                    totals["cases"] += 1
                    continue

            out = await _execute_case_inprocess(mode, case, live=bool(live))
            row = {
                "case_id": case.get("case_id"),
                "capabilities": case.get("capabilities"),
                "ok": bool(out.get("ok")),
                "status": out.get("status"),
                "errors": out.get("errors") or [],
                "runtime_tier": out.get("runtime_tier"),
                "execution_mode": out.get("execution_mode"),
                "subject": out.get("subject"),
                "answer_excerpt": str(out.get("answer") or "")[:300],
            }
            results.append(row)
            totals["cases"] += 1
            if row["status"] == "error":
                totals["error"] += 1
            elif row["ok"]:
                totals["pass"] += 1
            else:
                totals["fail"] += 1

        columns[mode] = {
            "impl_mode": mode,
            "execution_plan": exe_plan,
            "n_cases": len(results),
            "n_passed": sum(1 for r in results if r.get("ok")),
            "results": results,
            "separate_manifest": True,
            "separate_create_agent": True,
            "environment_lock": (m1a_environment_lock(matrix).get(mode) or {}),
        }
        totals["modes"] += 1

    all_ok = totals["fail"] == 0 and totals["error"] == 0 and totals["cases"] > 0
    return {
        "schema": EXAM_SCHEMA,
        "phase": "m1a",
        "ok": all_ok,
        "live": bool(live),
        "modes": list(wanted),
        "columns": columns,
        "counts": totals,
        "merged_execution_forbidden": True,
        "claim_eligible": False,
        "rank_claim": False,
        "accuracy_claim": False,
        "honesty": (
            "M1a per-mode columns; tools/retrieval/network locked none; "
            "scripted path uses runtime_tier=fixture after create_agent(tools=[]); "
            "live path marks workspace_execute; no cross-mode rank"
        ),
    }


def load_m1b_mode_cases(
    mode: str,
    *,
    seed_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    path = root / "fixtures" / "mode_exam" / mode / "cases.json"
    if not path.is_file():
        raise ModeAwareExamError(f"m1b_cases_missing:{path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ModeAwareExamError(f"m1b_cases_not_array:{path}")
    return [dict(x) for x in raw if isinstance(x, Mapping)]


def enforce_m1b_environment(
    mode: str,
    observed: Mapping[str, Any] | None,
    *,
    matrix: Mapping[str, Any] | None = None,
) -> List[str]:
    """Return violation codes if M1b rag lock is broken."""
    lock_all = m1b_environment_lock(matrix)
    lock = lock_all.get(mode) if isinstance(lock_all.get(mode), Mapping) else None
    if lock is None:
        return [f"m1b_lock_missing:{mode}"]
    obs = dict(observed or {})
    errors: List[str] = []

    tool_calls = list(obs.get("tool_calls") or [])
    if lock.get("tools") == "none" and tool_calls:
        errors.append("environment_violation:tools")
    if lock.get("network") == "none" and obs.get("network_used"):
        errors.append("environment_violation:network")
    if lock.get("session") == "none" and (
        obs.get("session_group") or obs.get("session_id")
    ):
        errors.append("environment_violation:session")
    if lock.get("retrieval") == "required":
        hits = list(obs.get("retrieval_hits") or [])
        if not (obs.get("retrieval_used") or hits):
            errors.append("environment_violation:retrieval_required")
    return errors


def _fixture_hits_from_case(case: Mapping[str, Any]) -> List[Dict[str, Any]]:
    fix = case.get("retrieval_fixture")
    if not isinstance(fix, Mapping):
        return []
    hits = fix.get("hits")
    if not isinstance(hits, list):
        return []
    out: List[Dict[str, Any]] = []
    for h in hits:
        if isinstance(h, Mapping):
            out.append(
                {
                    "id": str(h.get("id") or ""),
                    "title": str(h.get("title") or ""),
                    "content": str(h.get("content") or ""),
                }
            )
    return out


def _instantiate_rag_agent() -> Any:
    from core.apps.agents.base import create_agent
    from core.harness.interfaces.agent import AgentConfig

    agent = create_agent("rag", config=AgentConfig(name="eval-m1b-rag"))
    if hasattr(agent, "_tools"):
        agent._tools = []
    return agent


def _patch_rag_retrieve_with_fixture(agent: Any, hits: Sequence[Mapping[str, Any]]) -> None:
    """Bind fixture hits onto RAGAgent._retrieve (honest fixture retrieval backend)."""

    async def _retrieve(_query: str) -> List[Any]:
        from core.harness.knowledge.types import KnowledgeEntry, KnowledgeResult, KnowledgeType

        results: List[Any] = []
        for h in hits:
            entry = KnowledgeEntry(
                id=str(h.get("id") or "fixture"),
                type=KnowledgeType.DOCUMENT,
                content=str(h.get("content") or ""),
                title=str(h.get("title") or ""),
            )
            results.append(KnowledgeResult(entry=entry, score=1.0))
        return results

    agent._retrieve = _retrieve  # type: ignore[method-assign]


async def _execute_rag_case(
    case: Mapping[str, Any],
    *,
    live: bool,
    matrix: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    mode = "rag"
    hits = _fixture_hits_from_case(case)
    agent = _instantiate_rag_agent()
    tools_attr = getattr(agent, "_tools", None)
    if tools_attr:
        return {
            "status": "error",
            "ok": False,
            "errors": ["environment_violation:tools_bound_on_agent"],
            "runtime_tier": "fixture",
            "execution_mode": mode,
        }

    lock = m1b_environment_lock(matrix).get(mode) or {}
    subject = {
        "agent_id": "eval.m1b.rag",
        "agent_version": "m1b",
        "impl_mode": mode,
        "config_hash": _config_hash(mode, lock),
        "model_fingerprint": "scripted" if not live else "live_unresolved",
    }

    if not live:
        answer = str(case.get("scripted_answer") or "")
        observed = {
            "tool_calls": [],
            "retrieval_used": bool(hits),
            "retrieval_hits": hits,
            "network_used": False,
            "answer": answer,
        }
        violations = enforce_m1b_environment(mode, observed, matrix=matrix)
        passed = (not violations) and _lexical_pass(answer, case)
        return {
            "status": "ok" if passed else "fail",
            "ok": passed,
            "answer": answer,
            "errors": violations
            + ([] if _lexical_pass(answer, case) else ["lexical_fail"]),
            "runtime_tier": "fixture",
            "runtime_claim": False,
            "runtime_claim_reason": "m1b_scripted_after_create_agent_fixture_retrieval",
            "execution_mode": mode,
            "retrieval_hits": hits,
            "tool_calls": [],
            "subject": subject,
        }

    # live: fixture-backed retrieve (retrieval env ready as fixture corpus), then agent.execute
    try:
        from core.harness.interfaces.agent import AgentContext

        if not hits:
            return {
                "status": "error",
                "ok": False,
                "errors": ["m1b_live_requires_retrieval_fixture"],
                "runtime_tier": "workspace_execute",
                "runtime_claim": False,
                "execution_mode": mode,
            }
        _patch_rag_retrieve_with_fixture(agent, hits)
        prompt = str(case.get("prompt") or "")
        ctx = AgentContext(
            session_id="m1b-rag",
            user_id="eval-m1b",
            messages=[{"role": "user", "content": prompt}],
            variables={"eval_m1b": True, "query": prompt, "tools_allowed": []},
            tools=[],
        )
        result = await agent.execute(ctx)
        answer = ""
        if result is not None:
            answer = str(
                getattr(result, "output", None) or getattr(result, "content", None) or ""
            )
        meta = getattr(result, "metadata", None) or {}
        tool_calls = list(meta.get("tool_calls") or []) if isinstance(meta, Mapping) else []
        observed = {
            "tool_calls": tool_calls,
            "retrieval_used": True,
            "retrieval_hits": hits,
            "network_used": bool(meta.get("network_used")) if isinstance(meta, Mapping) else False,
            "answer": answer,
        }
        violations = enforce_m1b_environment(mode, observed, matrix=matrix)
        success = bool(getattr(result, "success", False)) and not violations
        subject["model_fingerprint"] = "live_unresolved"
        return {
            "status": "ok" if success else "fail",
            "ok": success and _lexical_pass(answer, case),
            "answer": answer,
            "errors": violations
            + ([] if _lexical_pass(answer, case) else ["lexical_fail"]),
            "runtime_tier": "workspace_execute",
            "runtime_claim": False,
            "runtime_claim_reason": "m1b_live_create_agent_fixture_retrieval",
            "execution_mode": mode,
            "retrieval_hits": hits,
            "tool_calls": tool_calls,
            "subject": subject,
        }
    except Exception as exc:  # noqa: BLE001
        _log.warning("m1b live execute failed: %s", exc, exc_info=True)
        return {
            "status": "error",
            "ok": False,
            "errors": [f"live_execute_error:{type(exc).__name__}"],
            "runtime_tier": "workspace_execute",
            "runtime_claim": False,
            "runtime_claim_reason": "m1b_live_failed",
            "execution_mode": mode,
            "tool_calls": [],
        }


async def run_m1b_mode_exam(
    *,
    live: bool = False,
    modes: Optional[Sequence[str]] = None,
    seed_dir: Optional[Path] = None,
    max_cases_per_mode: int = 0,
) -> Dict[str, Any]:
    """M1b exam: rag only, separate column, retrieval required, tools/network none."""
    try:
        matrix = load_mode_core_matrix(
            path=(Path(seed_dir) / "mode_core_capabilities.v1.yaml")
            if seed_dir
            else None
        )
    except AgentImplModeError as exc:
        raise ModeAwareExamError(str(exc)) from exc

    wanted = [str(m).strip() for m in (modes or M1B_MODES) if str(m).strip()]
    for m in wanted:
        if m not in M1B_MODES:
            raise ModeAwareExamError(f"m1b_mode_not_allowed:{m}")

    columns: Dict[str, Any] = {}
    totals = {"modes": 0, "cases": 0, "pass": 0, "fail": 0, "error": 0}

    for mode in wanted:
        impl = resolve_impl_modes(
            {
                "impl_modes": {
                    "primary": mode,
                    "secondary": [],
                    "confidence": "explicit",
                    "source": "config",
                }
            }
        )
        exe_plan = plan_executions_per_mode(impl, matrix=matrix)
        cases = load_m1b_mode_cases(mode, seed_dir=seed_dir)
        if max_cases_per_mode > 0:
            cases = cases[: int(max_cases_per_mode)]

        results: List[Dict[str, Any]] = []
        for case in cases:
            if not _fixture_hits_from_case(case):
                results.append(
                    {
                        "case_id": case.get("case_id"),
                        "ok": False,
                        "status": "error",
                        "errors": ["m1b_retrieval_fixture_required"],
                    }
                )
                totals["error"] += 1
                totals["cases"] += 1
                continue
            if case.get("session_group"):
                results.append(
                    {
                        "case_id": case.get("case_id"),
                        "ok": False,
                        "status": "error",
                        "errors": ["rag_session_forbidden"],
                    }
                )
                totals["error"] += 1
                totals["cases"] += 1
                continue

            out = await _execute_rag_case(case, live=bool(live), matrix=matrix)
            row = {
                "case_id": case.get("case_id"),
                "capabilities": case.get("capabilities"),
                "ok": bool(out.get("ok")),
                "status": out.get("status"),
                "errors": out.get("errors") or [],
                "runtime_tier": out.get("runtime_tier"),
                "execution_mode": out.get("execution_mode"),
                "subject": out.get("subject"),
                "n_retrieval_hits": len(out.get("retrieval_hits") or []),
                "answer_excerpt": str(out.get("answer") or "")[:300],
            }
            results.append(row)
            totals["cases"] += 1
            if row["status"] == "error":
                totals["error"] += 1
            elif row["ok"]:
                totals["pass"] += 1
            else:
                totals["fail"] += 1

        columns[mode] = {
            "impl_mode": mode,
            "execution_plan": exe_plan,
            "n_cases": len(results),
            "n_passed": sum(1 for r in results if r.get("ok")),
            "results": results,
            "separate_manifest": True,
            "separate_create_agent": True,
            "environment_lock": (m1b_environment_lock(matrix).get(mode) or {}),
            "retrieval_backend": "fixture",
        }
        totals["modes"] += 1

    all_ok = totals["fail"] == 0 and totals["error"] == 0 and totals["cases"] > 0
    return {
        "schema": EXAM_SCHEMA,
        "phase": "m1b",
        "ok": all_ok,
        "live": bool(live),
        "modes": list(wanted),
        "columns": columns,
        "counts": totals,
        "merged_execution_forbidden": True,
        "claim_eligible": False,
        "rank_claim": False,
        "accuracy_claim": False,
        "honesty": (
            "M1b rag column; retrieval=required via fixture corpus; "
            "tools/network/session locked none; scripted=fixture tier after create_agent(rag); "
            "live uses fixture-patched _retrieve then execute; no cross-mode rank; "
            "not CRAG production KB coverage"
        ),
    }


def probe_m1c_sandbox() -> Dict[str, Any]:
    """Fixture mock sandbox ready when catalog loads; live needs explicit env flag.

    ``AIPLAT_EVAL_M1C_SANDBOX=1`` opts into live_sandbox_ready — does **not**
    imply microVM/KVM isolation covered.
    """
    from core.apps.eval.service.mock_tools import load_mock_tool_catalog

    fixture_ok = False
    detail = ""
    try:
        cat = load_mock_tool_catalog()
        fixture_ok = bool(list(cat.get("tools") or []))
    except Exception as exc:  # noqa: BLE001
        detail = f"{type(exc).__name__}:{exc}"
    live_flag = os.environ.get("AIPLAT_EVAL_M1C_SANDBOX", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    return {
        "fixture_sandbox_ready": fixture_ok,
        "live_sandbox_ready": bool(live_flag and fixture_ok),
        "sandbox_backend": "fixture_mock" if fixture_ok else "none",
        "live_opt_in_env": "AIPLAT_EVAL_M1C_SANDBOX",
        "detail": detail,
        "microvm_covered": False,
    }


def load_m1c_mode_cases(
    mode: str,
    *,
    seed_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    root = Path(seed_dir) if seed_dir else default_seed_dir()
    path = root / "fixtures" / "mode_exam" / mode / "cases.json"
    if not path.is_file():
        raise ModeAwareExamError(f"m1c_cases_missing:{path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ModeAwareExamError(f"m1c_cases_not_array:{path}")
    return [dict(x) for x in raw if isinstance(x, Mapping)]


def enforce_m1c_environment(
    mode: str,
    observed: Mapping[str, Any] | None,
    *,
    matrix: Mapping[str, Any] | None = None,
) -> List[str]:
    """Return violation codes if M1c react lock is broken."""
    lock_all = m1c_environment_lock(matrix)
    lock = lock_all.get(mode) if isinstance(lock_all.get(mode), Mapping) else None
    if lock is None:
        return [f"m1c_lock_missing:{mode}"]
    obs = dict(observed or {})
    errors: List[str] = []

    tool_calls = list(obs.get("tool_calls") or [])
    if lock.get("tools") == "required" and not tool_calls:
        errors.append("environment_violation:tools_required")
    if lock.get("retrieval") == "none" and (
        obs.get("retrieval_used") or obs.get("retrieval_hits")
    ):
        errors.append("environment_violation:retrieval")
    if lock.get("network") == "none" and obs.get("network_used"):
        errors.append("environment_violation:network")
    if lock.get("session") == "none" and (
        obs.get("session_group") or obs.get("session_id")
    ):
        errors.append("environment_violation:session")
    if lock.get("sandbox") == "required":
        backend = str(obs.get("sandbox_backend") or "").strip()
        if backend in {"", "none"}:
            errors.append("environment_violation:sandbox_required")
    return errors


def _instantiate_react_agent() -> Any:
    from core.apps.agents.base import create_agent
    from core.harness.interfaces.agent import AgentConfig

    # Tools bound via mock harness, not live skill registry.
    agent = create_agent("react", config=AgentConfig(name="eval-m1c-react"), tools=[])
    if hasattr(agent, "_tools"):
        agent._tools = []
    return agent


async def _execute_react_case(
    case: Mapping[str, Any],
    *,
    live: bool,
    sandbox: Mapping[str, Any],
    matrix: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    mode = "react"
    from core.apps.eval.service.mock_tools.harness import (
        MockToolHarnessError,
        invoke_mock_tools,
        resolve_scripted_tool_calls,
    )
    from core.apps.eval.service.tool_trace_judge import judge_tool_trace

    agent = _instantiate_react_agent()
    lock = m1c_environment_lock(matrix).get(mode) or {}
    subject = {
        "agent_id": "eval.m1c.react",
        "agent_version": "m1c",
        "impl_mode": mode,
        "config_hash": _config_hash(mode, lock),
        "model_fingerprint": "scripted" if not live else "live_unresolved",
    }

    if live and not sandbox.get("live_sandbox_ready"):
        return {
            "status": "error",
            "ok": False,
            "errors": ["sandbox_not_ready"],
            "runtime_tier": "workspace_execute",
            "runtime_claim": False,
            "runtime_claim_reason": "m1c_live_requires_AIPLAT_EVAL_M1C_SANDBOX",
            "execution_mode": mode,
            "capability_coverage": {
                c: "unknown" for c in M1C_TOOL_CAPS_UNKNOWN
            },
            "subject": subject,
        }

    try:
        calls = resolve_scripted_tool_calls(case, {})
        harness = invoke_mock_tools(calls, case=case)
    except MockToolHarnessError as exc:
        return {
            "status": "error",
            "ok": False,
            "errors": [f"mock_harness:{exc}"],
            "runtime_tier": "fixture",
            "runtime_claim": False,
            "execution_mode": mode,
            "capability_coverage": {
                c: "unknown" for c in M1C_TOOL_CAPS_UNKNOWN
            },
            "subject": subject,
        }

    answer = str(case.get("scripted_answer") or "")
    # Prefer answer derived from successful tool results when scripted empty.
    if not answer.strip():
        for tr in list(harness.get("tool_results") or []):
            if isinstance(tr, Mapping) and tr.get("ok"):
                answer = json.dumps(tr.get("result"), ensure_ascii=False)
                break

    result_payload = {
        "tool_calls": harness.get("tool_calls") or [],
        "tool_results": harness.get("tool_results") or [],
        "answer": answer,
        "scripted_answer": answer,
        "tool_backend": "mock",
    }
    caps = list(case.get("capabilities") or [])
    tool_caps = set(caps) & set(M1C_TOOL_CAPS_UNKNOWN)
    if tool_caps:
        judgment = judge_tool_trace(case, result_payload)
        judge_ok = bool(judgment.get("passed"))
        judge_errors = list(judgment.get("errors") or [])
    else:
        judge_ok = _lexical_pass(answer, case)
        judge_errors = [] if judge_ok else ["lexical_fail"]
        judgment = {"status": "lexical", "passed": judge_ok}

    observed = {
        "tool_calls": result_payload["tool_calls"],
        "retrieval_used": False,
        "network_used": False,
        "sandbox_backend": sandbox.get("sandbox_backend") or "fixture_mock",
        "answer": answer,
    }
    violations = enforce_m1c_environment(mode, observed, matrix=matrix)
    # Prove create_agent(react) constructed (agent unused for scripted tool path).
    _ = agent
    passed = bool(harness.get("ok")) and judge_ok and not violations
    return {
        "status": "ok" if passed else "fail",
        "ok": passed,
        "answer": answer,
        "errors": violations + list(harness.get("errors") or []) + judge_errors,
        "runtime_tier": "fixture" if not live else "workspace_execute",
        "runtime_claim": False,
        "runtime_claim_reason": (
            "m1c_fixture_mock_tools_after_create_agent_react"
            if not live
            else "m1c_live_opt_in_fixture_mock_still"
        ),
        "execution_mode": mode,
        "tool_calls": result_payload["tool_calls"],
        "tool_results": result_payload["tool_results"],
        "tool_backend": "mock",
        "sandbox_backend": observed["sandbox_backend"],
        "judgment": judgment,
        "capability_coverage": {
            c: "unknown" for c in M1C_TOOL_CAPS_UNKNOWN
        },
        "subject": subject,
    }


async def run_m1c_mode_exam(
    *,
    live: bool = False,
    modes: Optional[Sequence[str]] = None,
    seed_dir: Optional[Path] = None,
    max_cases_per_mode: int = 0,
) -> Dict[str, Any]:
    """M1c exam: react column; tools+sandbox required; A3–A5 coverage unknown."""
    try:
        matrix = load_mode_core_matrix(
            path=(Path(seed_dir) / "mode_core_capabilities.v1.yaml")
            if seed_dir
            else None
        )
    except AgentImplModeError as exc:
        raise ModeAwareExamError(str(exc)) from exc

    wanted = [str(m).strip() for m in (modes or M1C_MODES) if str(m).strip()]
    for m in wanted:
        if m not in M1C_MODES:
            raise ModeAwareExamError(f"m1c_mode_not_allowed:{m}")

    sandbox = probe_m1c_sandbox()
    if not sandbox.get("fixture_sandbox_ready"):
        raise ModeAwareExamError(
            f"m1c_fixture_sandbox_not_ready:{sandbox.get('detail')}"
        )
    if live and not sandbox.get("live_sandbox_ready"):
        return {
            "schema": EXAM_SCHEMA,
            "phase": "m1c",
            "ok": False,
            "live": True,
            "modes": list(wanted),
            "columns": {},
            "counts": {"modes": 0, "cases": 0, "pass": 0, "fail": 0, "error": 1},
            "sandbox": sandbox,
            "errors": ["sandbox_not_ready"],
            "merged_execution_forbidden": True,
            "claim_eligible": False,
            "rank_claim": False,
            "accuracy_claim": False,
            "capability_coverage": {
                c: "unknown" for c in M1C_TOOL_CAPS_UNKNOWN
            },
            "honesty": (
                "M1c live blocked: set AIPLAT_EVAL_M1C_SANDBOX=1 for opt-in; "
                "still ≠ microVM isolation covered; A3–A5 remain unknown"
            ),
        }

    columns: Dict[str, Any] = {}
    totals = {"modes": 0, "cases": 0, "pass": 0, "fail": 0, "error": 0}

    for mode in wanted:
        impl = resolve_impl_modes(
            {
                "impl_modes": {
                    "primary": mode,
                    "secondary": [],
                    "confidence": "explicit",
                    "source": "config",
                }
            }
        )
        exe_plan = plan_executions_per_mode(impl, matrix=matrix)
        cases = load_m1c_mode_cases(mode, seed_dir=seed_dir)
        if max_cases_per_mode > 0:
            cases = cases[: int(max_cases_per_mode)]

        results: List[Dict[str, Any]] = []
        for case in cases:
            out = await _execute_react_case(
                case, live=bool(live), sandbox=sandbox, matrix=matrix
            )
            row = {
                "case_id": case.get("case_id"),
                "capabilities": case.get("capabilities"),
                "ok": bool(out.get("ok")),
                "status": out.get("status"),
                "errors": out.get("errors") or [],
                "runtime_tier": out.get("runtime_tier"),
                "execution_mode": out.get("execution_mode"),
                "subject": out.get("subject"),
                "tool_backend": out.get("tool_backend"),
                "sandbox_backend": out.get("sandbox_backend"),
                "capability_coverage": out.get("capability_coverage"),
                "answer_excerpt": str(out.get("answer") or "")[:300],
            }
            results.append(row)
            totals["cases"] += 1
            if row["status"] == "error":
                totals["error"] += 1
            elif row["ok"]:
                totals["pass"] += 1
            else:
                totals["fail"] += 1

        columns[mode] = {
            "impl_mode": mode,
            "execution_plan": exe_plan,
            "n_cases": len(results),
            "n_passed": sum(1 for r in results if r.get("ok")),
            "results": results,
            "separate_manifest": True,
            "separate_create_agent": True,
            "environment_lock": (m1c_environment_lock(matrix).get(mode) or {}),
            "sandbox_backend": sandbox.get("sandbox_backend"),
            "tool_backend": "mock",
        }
        totals["modes"] += 1

    all_ok = totals["fail"] == 0 and totals["error"] == 0 and totals["cases"] > 0
    return {
        "schema": EXAM_SCHEMA,
        "phase": "m1c",
        "ok": all_ok,
        "live": bool(live),
        "modes": list(wanted),
        "columns": columns,
        "counts": totals,
        "sandbox": sandbox,
        "merged_execution_forbidden": True,
        "claim_eligible": False,
        "rank_claim": False,
        "accuracy_claim": False,
        "capability_coverage": {c: "unknown" for c in M1C_TOOL_CAPS_UNKNOWN},
        "honesty": (
            "M1c react column; tools+sandbox required via fixture_mock; "
            "create_agent(react)+mock harness; A3–A5 coverage_status=unknown "
            "(≠ live sandbox / microVM covered); no cross-mode rank"
        ),
    }
