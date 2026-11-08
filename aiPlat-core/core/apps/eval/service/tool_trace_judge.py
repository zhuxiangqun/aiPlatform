"""Judge A3 tool_selection / A4 tool_args from execute traces (T1)."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from core.apps.eval.service.capability_id_map import resolve_capability_ids
from core.apps.eval.service.mock_tools.catalog_load import load_mock_tool_catalog
from core.apps.eval.service.mock_tools.harness import (
    _tool_index,
    validate_tool_args_against_schema,
)

JUDGE_SCHEMA = "eval.tool_trace_judge.v1"


def _names(calls: Sequence[Mapping[str, Any]]) -> List[str]:
    return [str(c.get("name") or "").strip() for c in calls if str(c.get("name") or "").strip()]


def judge_tool_selection(
    case: Mapping[str, Any],
    result: Mapping[str, Any],
) -> Dict[str, Any]:
    """A3: expected tools present; forbidden absent; optional exact-set."""
    calls = result.get("tool_calls") if isinstance(result.get("tool_calls"), list) else []
    got = _names(calls)
    expected = [
        str(x).strip()
        for x in (case.get("expected_tools") or [])
        if str(x).strip()
    ]
    forbidden = [
        str(x).strip()
        for x in (case.get("forbidden_tools") or [])
        if str(x).strip()
    ]
    exact = bool(case.get("exact_tool_set"))
    errors: List[str] = []

    for name in forbidden:
        if name in got:
            errors.append(f"forbidden_tool_used:{name}")

    if expected:
        if exact:
            if sorted(got) != sorted(expected):
                errors.append("tool_set_mismatch")
        else:
            for name in expected:
                if name not in got:
                    errors.append(f"missing_expected_tool:{name}")

    order = case.get("expected_tool_order")
    if isinstance(order, list) and order:
        want = [str(x).strip() for x in order if str(x).strip()]
        # subsequence order check
        it = iter(got)
        for name in want:
            for g in it:
                if g == name:
                    break
            else:
                errors.append(f"tool_order_miss:{name}")
                break

    passed = not errors
    return {
        "capability_id": "tool_selection",
        "passed": passed,
        "errors": errors,
        "got_tools": got,
        "expected_tools": expected,
        "forbidden_tools": forbidden,
    }


def judge_tool_args(
    case: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    catalog: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """A4: each call args valid vs catalog schema and optional expected_args."""
    calls = result.get("tool_calls") if isinstance(result.get("tool_calls"), list) else []
    cat = dict(catalog) if catalog is not None else load_mock_tool_catalog()
    index = _tool_index(cat)
    errors: List[str] = []
    expected_by_name: Dict[str, Mapping[str, Any]] = {}
    raw_exp = case.get("expected_tool_args")
    if isinstance(raw_exp, Mapping):
        for k, v in raw_exp.items():
            if isinstance(v, Mapping):
                expected_by_name[str(k).strip()] = v

    for i, call in enumerate(calls):
        if not isinstance(call, Mapping):
            errors.append(f"invalid_call:{i}")
            continue
        name = str(call.get("name") or "").strip()
        args = call.get("args") if isinstance(call.get("args"), Mapping) else {}
        tool = index.get(name)
        if tool is None:
            errors.append(f"tool_not_in_catalog:{name}")
            continue
        schema = tool.get("args_schema") if isinstance(tool.get("args_schema"), Mapping) else {}
        for e in validate_tool_args_against_schema(args, schema):
            errors.append(f"tools[{i}].{e}")
        if name in expected_by_name:
            want = expected_by_name[name]
            for k, v in want.items():
                if args.get(k) != v:
                    errors.append(f"tools[{i}].arg_value:{k}")

    # Also surface harness arg failures if execute already recorded them.
    for tr in list(result.get("tool_results") or []):
        if isinstance(tr, Mapping) and tr.get("arg_errors"):
            for e in tr.get("arg_errors") or []:
                errors.append(str(e))

    # dedupe
    seen: Set[str] = set()
    uniq: List[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            uniq.append(e)

    return {
        "capability_id": "tool_args",
        "passed": not uniq,
        "errors": uniq,
    }


def judge_tool_trace(
    case: Mapping[str, Any],
    result: Mapping[str, Any],
) -> Dict[str, Any]:
    """Dispatch A3/A4 judges for capabilities on the case."""
    caps = resolve_capability_ids(
        list(case.get("capabilities") or []), fail_closed=False
    )
    judgments: Dict[str, Any] = {}
    errors: List[str] = []
    if "tool_selection" in caps:
        j = judge_tool_selection(case, result)
        judgments["tool_selection"] = j
        if not j.get("passed"):
            errors.extend(j.get("errors") or [])
    if "tool_args" in caps:
        j = judge_tool_args(case, result)
        judgments["tool_args"] = j
        if not j.get("passed"):
            errors.extend(j.get("errors") or [])
    if not judgments:
        return {
            "schema": JUDGE_SCHEMA,
            "status": "skipped",
            "reason": "no_tool_capabilities",
            "passed": False,
            "errors": ["no_tool_capabilities"],
        }
    return {
        "schema": JUDGE_SCHEMA,
        "status": "ok",
        "passed": not errors,
        "errors": errors,
        "judgments": judgments,
        "tool_backend": str(result.get("tool_backend") or "mock"),
    }
