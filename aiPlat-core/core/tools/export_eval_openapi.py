"""
Export a stable OpenAPI snapshot for the auto-eval / evidence / policy surface.

Usage:
  python -m core.tools.export_eval_openapi > docs/design/evaluation/openapi-eval.snapshot.json
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


def _as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _resolve_ref(openapi: Dict[str, Any], ref: str) -> Any:
    # example: "#/components/schemas/AutoEvalRequest"
    if not ref.startswith("#/"):
        return {}
    cur: Any = openapi
    for part in ref[2:].split("/"):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return {}
    return cur


def _resolve_schema(openapi: Dict[str, Any], schema: Any, *, depth: int = 0) -> Dict[str, Any]:
    if depth > 8:
        return {}
    s = _as_dict(schema)
    if "$ref" in s and isinstance(s.get("$ref"), str):
        target = _resolve_ref(openapi, str(s["$ref"]))
        return _resolve_schema(openapi, target, depth=depth + 1)
    # allOf merge (common in pydantic)
    if "allOf" in s and isinstance(s.get("allOf"), list):
        out: Dict[str, Any] = {}
        req: List[str] = []
        props: Dict[str, Any] = {}
        for item in s["allOf"]:
            ss = _resolve_schema(openapi, item, depth=depth + 1)
            props.update(_as_dict(ss.get("properties")))
            for r in ss.get("required") or []:
                if r not in req:
                    req.append(r)
        out["properties"] = props
        out["required"] = req
        return out
    return s


def _extract_request_props(openapi: Dict[str, Any], op: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    rb = _as_dict(op.get("requestBody"))
    content = _as_dict(rb.get("content"))
    app_json = _as_dict(content.get("application/json"))
    schema0 = app_json.get("schema")
    schema = _resolve_schema(openapi, schema0)
    props = sorted([str(k) for k in _as_dict(schema.get("properties")).keys()])
    required = sorted([str(x) for x in (schema.get("required") or []) if isinstance(x, str)])
    return props, required


def build_snapshot() -> Dict[str, Any]:
    from core.server import app  # import lazily to avoid side-effects in module import

    openapi = app.openapi()

    wanted: List[Tuple[str, str]] = [
        ("POST", "/api/core/runs/{run_id}/evaluate/auto"),
        ("GET", "/api/core/runs/{run_id}/evaluation/latest"),
        ("POST", "/api/core/runs/{run_id}/investigate/auto"),
        ("GET", "/api/core/runs/{run_id}/investigate/latest"),
        ("GET", "/api/core/runs/{run_id}/evidence_pack/latest"),
        ("POST", "/api/core/runs/{run_id}/evidence/diff"),
        ("GET", "/api/core/evaluation/policy/latest"),
        ("POST", "/api/core/evaluation/policy"),
        ("GET", "/api/core/projects/{project_id}/evaluation/policy/latest"),
        ("POST", "/api/core/projects/{project_id}/evaluation/policy"),
    ]

    out: Dict[str, Any] = {
        "generated_from": "core.server:app.openapi",
        "endpoints": {},
    }

    paths = _as_dict(openapi.get("paths"))
    for method, path in wanted:
        op = _as_dict(_as_dict(paths.get(path)).get(method.lower()))
        key = f"{method} {path}"
        if not op:
            out["endpoints"][key] = {"missing": True}
            continue
        props, required = _extract_request_props(openapi, op) if method in {"POST", "PUT", "PATCH"} else ([], [])
        out["endpoints"][key] = {
            "operationId": op.get("operationId"),
            "request_properties": props,
            "request_required": required,
        }
    return out


def main() -> None:
    snap = build_snapshot()
    print(json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
