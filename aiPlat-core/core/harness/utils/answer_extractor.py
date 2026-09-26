"""Answer extractor — extract answer string from loop output formats.

Handles various output shapes returned by sys_skill_call and ReActLoop.
"""

from typing import Any, Dict


def extract_answer_from_output(output: Any) -> str:
    """Extract a plain-text answer from agent/skill loop output.

    Supports: dict with "answer"/"content"/"output" keys, plain strings,
    and JSON envelopes like {"type":"done","answer":"..."}.
    """
    if isinstance(output, dict):
        d: Dict[str, Any] = output
        typ = str(d.get("type") or "").strip().lower()
        if typ == "done" and d.get("answer") is not None:
            return str(d.get("answer") or "")
        if "output" in d:
            inner = d["output"]
            if isinstance(inner, dict):
                return extract_answer_from_output(inner)
            if isinstance(inner, str):
                return extract_answer_from_output(inner)
            return str(inner)
        if "text" in d and d.get("text") is not None:
            return extract_answer_from_output(d.get("text"))
        if d.get("answer") is not None:
            return str(d.get("answer") or "")
        if d.get("content") is not None:
            return str(d.get("content") or "")
        return ""
    if isinstance(output, str):
        s = output.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                import json
                parsed = json.loads(s)
                if isinstance(parsed, dict):
                    return extract_answer_from_output(parsed) or s
            except Exception:  # noqa: cleanup-best-effort
                pass
        return s
    return str(output or "")
