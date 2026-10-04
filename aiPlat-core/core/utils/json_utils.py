"""JSON extraction utilities — pure functions with no internal dependencies."""
from __future__ import annotations
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


def parse_json(raw: str) -> Optional[Dict[str, Any]]:
    """Extract and parse JSON from LLM output. Returns parsed dict or None."""
    import json
    json_str = extract_json_safe(raw or "")
    if json_str:
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass  # noqa: cleanup-best-effort
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

