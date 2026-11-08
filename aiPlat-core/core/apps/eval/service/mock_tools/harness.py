"""Mock tool harness (T1) — allowed set + deterministic invoke.

Does not call live skills / microVM. tool_backend is always ``mock``.
"""
from __future__ import annotations

import copy
import json
import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from core.apps.eval.service.mock_tools.catalog_load import load_mock_tool_catalog

_LOG = logging.getLogger(__name__)

HARNESS_SCHEMA = "eval.mock_tool_harness.v1"


class MockToolHarnessError(ValueError):
    """Harness failure (fail closed)."""


def _tool_index(catalog: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for tool in list(catalog.get("tools") or []):
        if isinstance(tool, Mapping):
            name = str(tool.get("name") or "").strip()
            if name:
                out[name] = dict(tool)
    return out


def allowed_tool_names(
    case: Mapping[str, Any],
    *,
    catalog: Optional[Mapping[str, Any]] = None,
) -> Set[str]:
    """Tools the case may call: catalog ∩ (expected ∪ optional allowlist).

    If ``expected_tools`` is empty, allow the full catalog (still mock-only).
    ``forbidden_tools`` are always excluded.
    """
    cat = dict(catalog) if catalog is not None else load_mock_tool_catalog()
    index = _tool_index(cat)
    catalog_names = set(index.keys())
    expected = {
        str(x).strip()
        for x in (case.get("expected_tools") or [])
        if str(x).strip()
    }
    allow_extra = {
        str(x).strip()
        for x in (case.get("allowed_tools") or [])
        if str(x).strip()
    }
    forbidden = {
        str(x).strip()
        for x in (case.get("forbidden_tools") or [])
        if str(x).strip()
    }
    if expected or allow_extra:
        allowed = (expected | allow_extra) & catalog_names
    else:
        allowed = set(catalog_names)
    return allowed - forbidden


def _normalize_calls(raw: Any) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise MockToolHarnessError("tool_calls must be a list")
    out: List[Dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise MockToolHarnessError(f"tool_calls[{i}] must be object")
        name = str(item.get("name") or "").strip()
        if not name:
            raise MockToolHarnessError(f"tool_calls[{i}] missing name")
        args = item.get("args")
        if args is None:
            args = item.get("arguments")
        if args is None:
            args = {}
        if not isinstance(args, Mapping):
            raise MockToolHarnessError(f"tool_calls[{i}].args must be object")
        out.append({"name": name, "args": dict(args)})
    return out


def validate_tool_args_against_schema(
    args: Mapping[str, Any], schema: Mapping[str, Any]
) -> List[str]:
    """Minimal JSON-Schema object check; prefer jsonschema when installed."""
    try:
        import jsonschema  # type: ignore

        jsonschema.validate(instance=dict(args), schema=dict(schema))
        return []
    except ImportError:  # noqa: — optional dep; fall through to minimal check
        _LOG.debug("jsonschema not installed; using minimal args check")
    except Exception as exc:  # noqa: BLE001 — surface as codes
        return [f"args_schema:{exc}"]

    errors: List[str] = []
    if str(schema.get("type") or "").lower() == "object":
        props = schema.get("properties") if isinstance(schema.get("properties"), Mapping) else {}
        required = schema.get("required") if isinstance(schema.get("required"), list) else []
        for key in required:
            if key not in args:
                errors.append(f"missing_arg:{key}")
        if schema.get("additionalProperties") is False:
            for key in args:
                if key not in props:
                    errors.append(f"unexpected_arg:{key}")
        for key, val in args.items():
            prop = props.get(key) if isinstance(props, Mapping) else None
            if not isinstance(prop, Mapping):
                continue
            ptype = str(prop.get("type") or "")
            if ptype == "string" and not isinstance(val, str):
                errors.append(f"arg_type:{key}:string")
            elif ptype == "integer" and not isinstance(val, int):
                errors.append(f"arg_type:{key}:integer")
            elif ptype == "number" and not isinstance(val, (int, float)):
                errors.append(f"arg_type:{key}:number")
            elif ptype == "boolean" and not isinstance(val, bool):
                errors.append(f"arg_type:{key}:boolean")
            elif ptype == "object" and not isinstance(val, Mapping):
                errors.append(f"arg_type:{key}:object")
            elif ptype == "array" and not isinstance(val, list):
                errors.append(f"arg_type:{key}:array")
    return errors


def invoke_mock_tools(
    tool_calls: Sequence[Mapping[str, Any]],
    *,
    case: Mapping[str, Any],
    catalog: Optional[Mapping[str, Any]] = None,
    fail_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Invoke scripted calls against mock catalog; enforce allowed set.

    ``fail_mode`` selects a catalog fail_modes.mode_id for all calls (optional).
    """
    cat = dict(catalog) if catalog is not None else load_mock_tool_catalog()
    index = _tool_index(cat)
    allowed = allowed_tool_names(case, catalog=cat)
    calls = _normalize_calls(tool_calls)
    results: List[Dict[str, Any]] = []
    errors: List[str] = []

    for i, call in enumerate(calls):
        name = call["name"]
        if name not in allowed:
            errors.append(f"tool_not_allowed:{name}")
            results.append(
                {
                    "name": name,
                    "args": call["args"],
                    "ok": False,
                    "error": "tool_not_allowed",
                }
            )
            continue
        tool = index.get(name)
        if tool is None:
            errors.append(f"tool_not_in_catalog:{name}")
            results.append(
                {
                    "name": name,
                    "args": call["args"],
                    "ok": False,
                    "error": "tool_not_in_catalog",
                }
            )
            continue

        schema = tool.get("args_schema") if isinstance(tool.get("args_schema"), Mapping) else {}
        arg_errs = validate_tool_args_against_schema(call["args"], schema)
        if arg_errs:
            errors.extend(f"tools[{i}].{e}" for e in arg_errs)
            results.append(
                {
                    "name": name,
                    "args": call["args"],
                    "ok": False,
                    "error": "args_invalid",
                    "arg_errors": arg_errs,
                }
            )
            continue

        if fail_mode:
            matched = None
            for mode in list(tool.get("fail_modes") or []):
                if isinstance(mode, Mapping) and str(mode.get("mode_id") or "") == fail_mode:
                    matched = mode
                    break
            if matched is not None:
                results.append(
                    {
                        "name": name,
                        "args": call["args"],
                        "ok": False,
                        "error": str(matched.get("error") or fail_mode),
                        "fail_mode": fail_mode,
                    }
                )
                continue

        result = copy.deepcopy(tool.get("result"))
        # Tiny template: replace "{{key}}" in JSON dump when args provide key.
        try:
            blob = json.dumps(result, ensure_ascii=False)
            for k, v in call["args"].items():
                blob = blob.replace("{{" + str(k) + "}}", str(v))
            result = json.loads(blob)
        except (TypeError, json.JSONDecodeError) as exc:
            _LOG.debug("mock result template skip for %s: %s", name, exc)
        results.append(
            {
                "name": name,
                "args": call["args"],
                "ok": True,
                "result": result,
            }
        )

    ok = not errors and all(r.get("ok") for r in results)
    return {
        "schema": HARNESS_SCHEMA,
        "ok": ok,
        "tool_backend": "mock",
        "allowed_tools": sorted(allowed),
        "tool_calls": calls,
        "tool_results": results,
        "errors": errors,
        "catalog_id": str(cat.get("catalog_id") or ""),
        "catalog_version": str(cat.get("version") or ""),
    }


def resolve_scripted_tool_calls(
    case: Mapping[str, Any],
    env: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Prefer env.tool_calls, else case.scripted_tool_calls."""
    env = env or {}
    if "tool_calls" in env:
        return _normalize_calls(env.get("tool_calls"))
    if "scripted_tool_calls" in case:
        return _normalize_calls(case.get("scripted_tool_calls"))
    raise MockToolHarnessError("missing_tool_calls")
