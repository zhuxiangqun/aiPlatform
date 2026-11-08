"""Mode-aware Agent exam — M1a plan_execute / conversational (no tools).

Hard rules (eval-agent-impl-mode-exam.md):
- selection union ≠ execution union (per-mode create_agent / manifest / run)
- M1a: tools=retrieval=network=none; session only for conversational
- claim_eligible / rank_claim stay false
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.agent_impl_mode import (
    AgentImplModeError,
    load_mode_core_matrix,
    m1a_environment_lock,
    plan_executions_per_mode,
    resolve_impl_modes,
)
from core.apps.eval.service.capability_case_bank import default_seed_dir

_log = logging.getLogger(__name__)

M1A_MODES = ("plan_execute", "conversational")
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
