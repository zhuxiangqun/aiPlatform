"""Mock tool catalog schema v1 — T0 mechanical validate.

Authority: docs/architecture/plans/EVAL_AGENT_TOOL_SESSION_CONTRACTS_T0.md §1.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Sequence

CATALOG_SCHEMA = "eval.mock_tool_catalog.v1"
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _nonempty_str(v: Any) -> str:
    return str(v or "").strip()


def validate_mock_tool(tool: Mapping[str, Any] | None) -> List[str]:
    """Return error codes for one tool entry; empty = pass."""
    errors: List[str] = []
    if not isinstance(tool, Mapping):
        return ["missing_field:tool"]

    name = _nonempty_str(tool.get("name"))
    if not name:
        errors.append("missing_field:name")
    elif not _NAME_RE.match(name):
        errors.append("invalid_name")

    if not _nonempty_str(tool.get("description")):
        errors.append("missing_field:description")

    args_schema = tool.get("args_schema")
    if not isinstance(args_schema, Mapping):
        errors.append("missing_field:args_schema")
    else:
        if str(args_schema.get("type") or "").strip().lower() != "object":
            errors.append("args_schema_type_not_object")

    if "result" not in tool:
        errors.append("missing_field:result")

    fail_modes = tool.get("fail_modes")
    if fail_modes is None:
        fail_modes = []
    if not isinstance(fail_modes, (list, tuple)):
        errors.append("invalid_fail_modes")
        fail_modes = []
    seen_modes: set = set()
    for i, mode in enumerate(fail_modes):
        if not isinstance(mode, Mapping):
            errors.append(f"invalid_fail_mode:{i}")
            continue
        mid = _nonempty_str(mode.get("mode_id"))
        if not mid:
            errors.append(f"missing_field:fail_modes[{i}].mode_id")
        elif mid in seen_modes:
            errors.append(f"duplicate_fail_mode:{mid}")
        else:
            seen_modes.add(mid)
        if not _nonempty_str(mode.get("when")):
            errors.append(f"missing_field:fail_modes[{i}].when")
        if not _nonempty_str(mode.get("error")):
            errors.append(f"missing_field:fail_modes[{i}].error")
        status = mode.get("http_status")
        if status is not None and not isinstance(status, int):
            errors.append(f"invalid_fail_modes[{i}].http_status")

    return _uniq(errors)


def validate_mock_tool_catalog(catalog: Mapping[str, Any] | None) -> List[str]:
    """Return error codes for a catalog document; empty = pass."""
    if not isinstance(catalog, Mapping):
        return ["missing_field:catalog"]
    errors: List[str] = []
    schema = _nonempty_str(catalog.get("schema"))
    if schema != CATALOG_SCHEMA:
        errors.append("invalid_schema")
    if not _nonempty_str(catalog.get("catalog_id")):
        errors.append("missing_field:catalog_id")
    if not _nonempty_str(catalog.get("version")):
        errors.append("missing_field:version")

    tools = catalog.get("tools")
    if not isinstance(tools, (list, tuple)) or not tools:
        errors.append("empty_list:tools")
        return _uniq(errors)

    seen_names: set = set()
    for i, tool in enumerate(tools):
        terrs = validate_mock_tool(tool if isinstance(tool, Mapping) else None)
        for e in terrs:
            errors.append(f"tools[{i}].{e}" if not e.startswith("tools[") else e)
        if isinstance(tool, Mapping):
            n = _nonempty_str(tool.get("name"))
            if n:
                if n in seen_names:
                    errors.append(f"duplicate_tool_name:{n}")
                seen_names.add(n)
    return _uniq(errors)


def assert_mock_tool_catalog_valid(
    catalog: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    errs = validate_mock_tool_catalog(catalog)
    if errs:
        raise ValueError("mock_tool_catalog_invalid:" + ",".join(errs))
    assert isinstance(catalog, Mapping)
    return dict(catalog)


def _uniq(errors: Sequence[str]) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out
