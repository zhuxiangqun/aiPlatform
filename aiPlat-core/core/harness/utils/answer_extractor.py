"""Answer extractor — extract answer string from loop output formats.

Handles various output shapes returned by sys_skill_call and ReActLoop.
"""

from typing import Any, Dict


def extract_answer_from_output(output: Any) -> str:
    """Extract a plain-text answer from agent/skill loop output.

    Supports: dict with "answer"/"content"/"output" keys, plain strings.
    """
    if isinstance(output, dict):
        d: Dict[str, Any] = output
        if "output" in d:
            inner = d["output"]
            if isinstance(inner, dict):
                return str(inner.get("answer", "") or inner.get("content", "") or str(inner))
            return str(inner)
        return str(d.get("answer", "") or d.get("content", "") or "")
    return str(output or "")
