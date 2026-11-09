"""Session runner (T2) — run session_group turns in order; A8 memory probes.

Fail closed if a group is incomplete / split. Does not claim v1 covered.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from core.apps.eval.service.session_case_schema import (
    SESSION_SCHEMA,
    validate_session_case_fields,
    validate_session_group_unique_turns,
)

RUNNER_SCHEMA = "eval.session_runner.v1"


class SessionRunnerError(ValueError):
    """Session group execution failure (fail closed)."""


def _sg(case: Mapping[str, Any]) -> str:
    return str(case.get("session_group") or "").strip()


def group_session_cases(
    cases: Sequence[Mapping[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Partition by session_group; fail closed on field / uniqueness errors."""
    rows = [dict(c) for c in cases if isinstance(c, Mapping) and _sg(c)]
    field_errs: List[str] = []
    for c in rows:
        field_errs.extend(validate_session_case_fields(c))
    uniq_errs = validate_session_group_unique_turns(rows)
    if field_errs or uniq_errs:
        raise SessionRunnerError(
            "session_invalid:" + ",".join(dict.fromkeys(field_errs + uniq_errs))
        )
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for c in rows:
        groups.setdefault(_sg(c), []).append(c)
    for sg, items in groups.items():
        missing_turn = [c for c in items if c.get("turn_index") is None]
        if missing_turn:
            raise SessionRunnerError(f"session_group_missing_turn:{sg}")
        items.sort(key=lambda c: int(c.get("turn_index") or 0))
    return groups


def assert_session_groups_complete(
    selected: Sequence[Mapping[str, Any]],
    universe: Sequence[Mapping[str, Any]],
) -> None:
    """Fail closed if selected set splits any session_group from universe."""
    uni = group_session_cases(universe) if any(_sg(c) for c in universe if isinstance(c, Mapping)) else {}
    sel_ids = {
        str(c.get("case_id") or "")
        for c in selected
        if isinstance(c, Mapping) and str(c.get("case_id") or "")
    }
    for sg, items in uni.items():
        ids = [str(c.get("case_id") or "") for c in items]
        present = [i for i in ids if i in sel_ids]
        if present and len(present) != len(ids):
            raise SessionRunnerError(
                f"session_group_split:{sg}:have={len(present)}/need={len(ids)}"
            )


def judge_memory_probe(
    *,
    planted: Mapping[str, Any],
    answer: str,
) -> Dict[str, Any]:
    """Check must_recall tokens appear in later-turn answer."""
    probe = planted.get("memory_probe") if isinstance(planted.get("memory_probe"), Mapping) else {}
    must = [str(x).strip() for x in (probe.get("must_recall") or []) if str(x).strip()]
    errors: List[str] = []
    if not must:
        errors.append("empty_must_recall")
    for tok in must:
        if tok not in (answer or ""):
            errors.append(f"memory_miss:{tok}")
    return {"passed": not errors, "errors": errors, "must_recall": must}


def run_session_group(
    cases: Sequence[Mapping[str, Any]],
    *,
    answers: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Execute one session_group worth of turns (scripted answers).

    ``answers`` maps case_id → assistant text. Falls back to case.scripted_answer.
    Memory probes planted on turn T are checked on turn T+ask_after_turns.
    """
    groups = group_session_cases(cases)
    if len(groups) != 1:
        raise SessionRunnerError(
            f"run_session_group expects exactly 1 group, got {len(groups)}"
        )
    sg, turns = next(iter(groups.items()))
    ans_map = dict(answers or {})
    planted: List[Dict[str, Any]] = []
    turn_results: List[Dict[str, Any]] = []
    errors: List[str] = []

    for case in turns:
        cid = str(case.get("case_id") or "")
        turn_i = int(case.get("turn_index") or 0)
        answer = str(ans_map.get(cid) or case.get("scripted_answer") or "")
        if case.get("memory_probe") and isinstance(case.get("memory_probe"), Mapping):
            planted.append(
                {
                    "planted_at": turn_i,
                    "case_id": cid,
                    "memory_probe": dict(case["memory_probe"]),
                }
            )

        probe_errs: List[str] = []
        for p in planted:
            ask_after = int((p.get("memory_probe") or {}).get("ask_after_turns") or 0)
            if ask_after < 1:
                continue
            if turn_i == int(p["planted_at"]) + ask_after:
                j = judge_memory_probe(planted=p, answer=answer)
                if not j.get("passed"):
                    probe_errs.extend(j.get("errors") or [])
                    errors.extend(j.get("errors") or [])

        turn_results.append(
            {
                "case_id": cid,
                "turn_index": turn_i,
                "answer": answer,
                "memory_probe_errors": probe_errs,
                "ok": not probe_errs and bool(answer.strip() or not case.get("memory_probe")),
            }
        )

    # Pending probes never fired → fail closed
    for p in planted:
        ask_after = int((p.get("memory_probe") or {}).get("ask_after_turns") or 0)
        due = int(p["planted_at"]) + ask_after
        max_turn = max(int(c.get("turn_index") or 0) for c in turns)
        if ask_after >= 1 and due > max_turn:
            errors.append(f"memory_probe_not_due:{p.get('case_id')}")

    return {
        "schema": RUNNER_SCHEMA,
        "session_schema": SESSION_SCHEMA,
        "session_group": sg,
        "ok": not errors,
        "errors": errors,
        "n_turns": len(turns),
        "turns": turn_results,
        "claim_eligible": False,
        "v1_in_scope": False,
    }


def run_all_session_groups(
    cases: Sequence[Mapping[str, Any]],
    *,
    answers: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Run every session_group in the fixture set."""
    groups = group_session_cases(cases)
    reports: List[Dict[str, Any]] = []
    ok = True
    for sg, items in sorted(groups.items()):
        rep = run_session_group(items, answers=answers)
        reports.append(rep)
        if not rep.get("ok"):
            ok = False
    return {
        "schema": RUNNER_SCHEMA,
        "ok": ok and bool(reports),
        "n_groups": len(reports),
        "groups": reports,
        "claim_eligible": False,
        "v1_in_scope": False,
    }
