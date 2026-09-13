"""Factory skill hop schema gate (Phase B W4).

Validates execute_skill params against Skill input_schema before core_chat.
Supports:
  - Field-map schema (agent_engineering): {field: {type, required, description}}
  - JSON-schema-like: {type, required[], properties{}}
Empty / missing schema → pass (backward compatible).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

RUNTIME_FAILED_STAGES = (
    "planning",
    "tool_selection",
    "tool_execution",
    "response_synthesis",
    "verification",
)


def load_skill_input_schema(skill_name: str, app_home: Optional[str] = None) -> Dict[str, Any]:
    """Load input_schema from workspace/app SKILL.md frontmatter."""
    name = str(skill_name or "").strip()
    if not name:
        return {}
    candidates: List[Path] = []
    home = os.getenv("AIPLAT_HOME", os.path.expanduser("~/.aiplat"))
    if app_home:
        candidates.append(Path(app_home) / "skills" / name / "SKILL.md")
        # nested under app current
        for p in Path(app_home).rglob("SKILL.md"):
            if p.parent.name == name:
                candidates.append(p)
    candidates.append(Path(home) / "skills" / name / "SKILL.md")
    seen = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        schema = fm.get("input_schema")
        if isinstance(schema, dict) and schema:
            return schema
    return {}


def validate_skill_hop_params(
    params: Optional[Mapping[str, Any]],
    input_schema: Optional[Mapping[str, Any]],
) -> List[str]:
    """Return violation messages; empty = OK."""
    schema = input_schema if isinstance(input_schema, Mapping) else {}
    if not schema:
        return []
    payload = dict(params or {})

    # JSON-schema-like
    if "properties" in schema or (
        isinstance(schema.get("required"), list) and schema.get("type") in (None, "object", "Object")
    ):
        return _validate_json_schema_like(payload, schema)

    # Field-map (factory SKILL.md)
    return _validate_field_map(payload, schema)


def gate_skill_hop(
    skill_name: str,
    params: Optional[Mapping[str, Any]],
    *,
    app_home: Optional[str] = None,
    input_schema: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Full hop gate result for execute_skill.

    Returns {ok, violations, failed_stage, skill, schema_present}.
    """
    schema = input_schema if input_schema is not None else load_skill_input_schema(
        skill_name, app_home=app_home
    )
    violations = validate_skill_hop_params(params, schema)
    if violations:
        return {
            "ok": False,
            "skill": skill_name,
            "violations": violations,
            "failed_stage": "tool_selection",
            "schema_present": bool(schema),
            "error": "hop_schema_gate: " + "; ".join(violations[:5]),
        }
    return {
        "ok": True,
        "skill": skill_name,
        "violations": [],
        "failed_stage": "",
        "schema_present": bool(schema),
    }


def build_hop_handoff(
    *,
    skill: str,
    agent: str,
    ok: bool,
    verify: str = "",
    known_issues: Optional[List[str]] = None,
    next_hint: str = "",
) -> Dict[str, Any]:
    """Minimal 5-field envelope for runtime hops (align stage_handoff keys)."""
    return {
        "summary": f"skill={skill} agent={agent} ok={ok}",
        "artifact_ref": f"skill:{skill}",
        "verify": verify or ("schema_ok" if ok else "schema_failed"),
        "known_issues": list(known_issues or []),
        "next": next_hint,
    }


def _validate_field_map(payload: Dict[str, Any], schema: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    for field, spec in schema.items():
        if not isinstance(field, str) or field.startswith("$"):
            continue
        if not isinstance(spec, Mapping):
            continue
        required = spec.get("required")
        is_req = required is True or str(required).lower() in ("true", "1", "yes")
        if is_req and field not in payload:
            errors.append(f"Missing required field: {field}")
            continue
        if field not in payload:
            continue
        expected = str(spec.get("type") or "").lower()
        if not expected:
            continue
        val = payload[field]
        if not _type_ok(val, expected):
            errors.append(
                f"Field '{field}': expected {expected}, got {type(val).__name__}"
            )
    return errors


def _validate_json_schema_like(payload: Dict[str, Any], schema: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    required = schema.get("required") or []
    if isinstance(required, list):
        missing = [f for f in required if f not in payload]
        if missing:
            errors.append(f"Missing required field(s): {', '.join(str(m) for m in missing)}")
    properties = schema.get("properties") or {}
    if isinstance(properties, Mapping):
        for name, prop in properties.items():
            if name not in payload or not isinstance(prop, Mapping):
                continue
            expected = str(prop.get("type") or "").lower()
            if expected and not _type_ok(payload[name], expected):
                errors.append(
                    f"Field '{name}': expected {expected}, got {type(payload[name]).__name__}"
                )
    return errors


def _type_ok(val: Any, expected: str) -> bool:
    expected = expected.lower()
    if expected in ("string", "str"):
        return isinstance(val, str)
    if expected in ("number", "float"):
        return isinstance(val, (int, float)) and not isinstance(val, bool)
    if expected in ("integer", "int"):
        return isinstance(val, int) and not isinstance(val, bool)
    if expected in ("boolean", "bool"):
        return isinstance(val, bool)
    if expected == "object":
        return isinstance(val, dict)
    if expected == "array":
        return isinstance(val, list)
    return True


def _parse_frontmatter(text: str) -> Dict[str, Any]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.safe_load(parts[1])
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}
