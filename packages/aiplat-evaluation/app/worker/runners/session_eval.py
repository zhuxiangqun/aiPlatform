"""session_eval — multi-turn / session chain v0 (2–3 turns).

Honesty:
- Pure-text; optional independent LLM per turn (no Central / no tools).
- Prior turns appended into the next prompt as plain context.
- accuracy_claim=false; not full dialogue certification.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.llm.client import complete_text, llm_enabled, llm_mode
from app.scoring.session import (
    MAX_TURNS_V0,
    MIN_TURNS_V0,
    normalize_turns,
    session_dimension,
)
from app.scoring.semantics import (
    efficiency_dimension,
    groundedness_dimension,
    prompt_eval_p1_metrics,
)
from app.worker.runners._common import runner_result


def _turn_prompt(history: List[Dict[str, str]], user: str) -> str:
    if not history:
        return user
    lines = ["Prior turns:"]
    for i, h in enumerate(history, 1):
        lines.append(f"User{i}: {h.get('user', '')}")
        lines.append(f"Assistant{i}: {h.get('assistant', '')}")
    lines.append("Current user:")
    lines.append(user)
    return "\n".join(lines)


def run_session_eval(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    job_id = str(job.get("job_id") or "")
    tenant_id = str(job.get("tenant_id") or "")
    session_id = str(payload.get("session_id") or payload.get("conversation_id") or job_id)
    turns = normalize_turns(payload.get("turns") or payload.get("messages") or [])

    if len(turns) < MIN_TURNS_V0:
        return runner_result(
            runner_id="session_eval",
            job_id=job_id,
            ok=False,
            metrics={"turns_n": float(len(turns)), "turn_success_rate": 0.0, "session_pass": 0.0},
            evidence={"session_id": session_id, "max_turns_v0": MAX_TURNS_V0},
            detail=f"session_eval v0 requires {MIN_TURNS_V0}–{MAX_TURNS_V0} turns",
            mode="session_v0",
        )

    history: List[Dict[str, str]] = []
    turn_oks: List[bool] = []
    turn_details: List[Dict[str, Any]] = []
    audits: List[Dict[str, Any]] = []
    gdims: List[Dict[str, Any]] = []
    used_llm = False

    for i, turn in enumerate(turns):
        prompt = str(turn.get("prompt") or turn.get("user") or turn.get("input") or "")
        expected = str(turn.get("expected") or turn.get("expected_text") or "")
        actual = str(turn.get("actual") or turn.get("output") or turn.get("assistant") or "")
        context = str(turn.get("context") or "")
        sources_raw = turn.get("sources") or []
        sources = [str(s) for s in sources_raw] if isinstance(sources_raw, list) else []
        audit: Dict[str, Any] = {}

        if not actual and llm_enabled():
            used_llm = True
            llm = complete_text(
                _turn_prompt(history, prompt),
                job_id=f"{job_id}:t{i}",
                tenant_id=tenant_id,
                runner_id="session_eval",
                purpose="session_eval",
                model=str(turn.get("model") or "") or None,
            )
            audit = dict(llm.get("audit") or {})
            audits.append(audit)
            actual = str(llm.get("text") or "") if llm.get("ok") else ""

        if expected:
            ok = actual == expected
            exact = 1.0 if ok else 0.0
        else:
            ok = bool(actual.strip())
            exact = 0.0

        metrics = prompt_eval_p1_metrics(
            actual=actual,
            expected=expected,
            context=context,
            sources=sources,
            llm_audit=audit,
            exact_match=exact,
            ok=ok,
        )
        gdim = groundedness_dimension(
            actual=actual, expected=expected, context=context, sources=sources
        )
        gdims.append(gdim)
        turn_oks.append(ok)
        turn_details.append(
            {
                "i": i,
                "ok": ok,
                "prompt_len": len(prompt),
                "actual_len": len(actual),
                "exact_match": exact,
                "groundedness_scored": bool(gdim.get("scored")),
            }
        )
        history.append({"user": prompt, "assistant": actual})

    sdim = session_dimension(turns=turns, turn_oks=turn_oks, session_id=session_id)
    edim = efficiency_dimension(audits, success_flags=turn_oks)
    n_ok = int(sdim["turns_ok"])
    rate = float(sdim["turn_success_rate"])
    session_pass = bool(sdim["session_pass"])

    mode = "session_v0"
    if used_llm:
        mode = f"session_v0_llm_{llm_mode()}"

    return runner_result(
        runner_id="session_eval",
        job_id=job_id,
        ok=session_pass,
        metrics={
            "turns_n": float(len(turns)),
            "turns_ok": float(n_ok),
            "turn_success_rate": rate,
            "session_pass": 1.0 if session_pass else 0.0,
            "pass": 1.0 if session_pass else 0.0,
        },
        groundedness_dimension=gdims[-1] if gdims else None,
        efficiency_dimension=edim,
        session_dimension=sdim,
        evidence={
            "session_id": session_id,
            "turns": turn_details,
            "max_turns_v0": MAX_TURNS_V0,
            "llm_audits_n": len(audits),
        },
        detail="" if session_pass else f"turn_success_rate={rate}",
        mode=mode,
    )
