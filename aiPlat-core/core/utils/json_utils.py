"""JSON extraction utilities — pure functions with no internal dependencies."""
from __future__ import annotations
import os
import re
from typing import Any, Dict, Optional


def extract_json_safe(text: str) -> Optional[str]:
    """Extract JSON substring with bracket-balanced truncation handling.
    Unlike extract_json, this finds the first balanced {…} or […] block,
    making it safe for LLM outputs where JSON may be followed by commentary.

    Prefer whole-text JSON when valid so embedded markdown fences inside string
    values (e.g. skill_call with ```ts code) are not mistaken for a JSON fence.
    """
    if not text:
        return None
    stripped = text.strip()
    # 0) Whole-text already valid JSON (common for structured skill/tool calls)
    if stripped[:1] in "{[":
        try:
            import json as _json

            _json.loads(stripped)
            return stripped
        except Exception:
            pass  # noqa: cleanup-best-effort — fall through to fence / balanced
    # 1) Prefer explicit ```json fence (not bare ```ts / ```python)
    m = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
    elif stripped[:1] in "{[":
        # Already looks like an object/array; do not peel inner ``` fences
        candidate = stripped
    else:
        m = re.search(r"```\s*([\s\S]*?)\s*```", text)
        candidate = m.group(1).strip() if m else text
    # 2. Find first { or [ at outermost level
    def _balanced(src: str, open_ch: str, close_ch: str) -> Optional[str]:
        i = src.find(open_ch)
        if i < 0:
            return None
        depth, in_str, esc = 0, False, False
        for j in range(i, len(src)):
            ch = src[j]
            if in_str:
                if esc: esc = False
                elif ch == '\\': esc = True
                elif ch == '"': in_str = False
            else:
                if ch == '"': in_str = True
                elif ch == open_ch: depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        return src[i:j + 1]
        return None
    return _balanced(candidate, '{', '}') or _balanced(candidate, '[', ']')


def _apply_llm_json_fixes(text: str) -> str:
    """Deterministic fixes for common LLM JSON mistakes (no model call)."""
    t = text or ""
    t = re.sub(r",\s*}", "}", t)
    t = re.sub(r",\s*]", "]", t)
    t = t.replace(": True", ": true").replace(": False", ": false").replace(": None", ": null")
    t = re.sub(r":\s*'([^']*)'", r': "\1"', t)
    return t


def parse_json(raw: str) -> Optional[Dict[str, Any]]:
    """Extract and parse JSON from LLM output. Returns parsed dict or None.

    Pipeline: ``extract_json_safe`` → ``json.loads`` → deterministic LLM fixes → reload.
    """
    import json

    json_str = extract_json_safe(raw or "")
    if not json_str:
        return None
    for candidate in (json_str, _apply_llm_json_fixes(json_str)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def extract_json(text: str) -> str:
    """Extract JSON block from text (markdown-fenced or bare braces)."""
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if m:
        return m.group(1).strip()
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        return m.group(0).strip()
    return ""


_SCHEMA_META = frozenset(
    {
        "$schema",
        "$id",
        "title",
        "description",
        "examples",
        "default",
        "x-display-profile",
        "x-ui",
        "additionalProperties",
    }
)


def build_llm_response_format(
    schema: Any,
    *,
    name: str = "output",
    force_json_object: bool = False,
) -> Optional[Dict[str, Any]]:
    """Build OpenAI-compatible ``response_format`` from a JSON-Schema-like dict.

    - Empty / non-dict → None (caller keeps prompt-only constraint).
    - Valid schema (``type`` / ``properties`` / ``$ref``) → ``json_schema``.
    - Key-only dict (legacy skill shape) → wrap as object properties then ``json_schema``.
    - ``force_json_object`` or unusable schema → ``{"type": "json_object"}``.

    Kill-switch: ``AIPLAT_LLM_RESPONSE_FORMAT=0`` → always None.
    """
    flag = (os.environ.get("AIPLAT_LLM_RESPONSE_FORMAT") or "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return None
    if force_json_object:
        return {"type": "json_object"}
    if not isinstance(schema, dict) or not schema:
        return None

    # Already a full JSON Schema object
    if (
        schema.get("type") in ("object", "array")
        or isinstance(schema.get("properties"), dict)
        or schema.get("$ref")
        or schema.get("items")
    ):
        clean = {k: v for k, v in schema.items() if not str(k).startswith("x-")}
        if "type" not in clean and isinstance(clean.get("properties"), dict):
            clean = {**clean, "type": "object"}
        return {
            "type": "json_schema",
            "json_schema": {
                "name": (name or "output")[:64] or "output",
                "schema": clean,
                "strict": False,
            },
        }

    # Legacy: top-level keys are payload fields (not JSON Schema keywords)
    props: Dict[str, Any] = {}
    for k, v in schema.items():
        sk = str(k)
        if sk in _SCHEMA_META or sk.startswith("x-") or sk.startswith("$"):
            continue
        if isinstance(v, dict) and ("type" in v or "properties" in v):
            props[sk] = v
        else:
            props[sk] = {"type": "string"} if v is None or isinstance(v, str) else {"type": "object"}
    if not props:
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": (name or "output")[:64] or "output",
            "schema": {"type": "object", "properties": props},
            "strict": False,
        },
    }

