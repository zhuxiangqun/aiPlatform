"""Leading-token verdict helpers for LLM evaluator / critic text.

Mid-string substring checks (``\"APPROVED\" in text`` / ``\"PASS\" in text``)
false-approve on ``NOT APPROVED``, ``DISAPPROVED``, ``BYPASS``, etc.
"""

from __future__ import annotations

import re
from typing import Any, Optional


def is_leading_token(text: Any, token: str) -> bool:
    """True when ``token`` starts the text (optional ``:`` / fullwidth colon / space)."""
    raw = str(text or "").strip()
    tok = str(token or "").strip()
    if not raw or not tok:
        return False
    return (
        re.match(
            rf"^{re.escape(tok)}(?:\s*[:：]|\s|$)",
            raw,
            flags=re.IGNORECASE,
        )
        is not None
    )


def is_approved_evaluation(text: Any) -> bool:
    """Tri-agent style: leading APPROVED (not REJECTED / mid-string APPROVED)."""
    raw = str(text or "").strip()
    if not raw:
        return False
    if is_leading_token(raw, "REJECTED"):
        return False
    return is_leading_token(raw, "APPROVED")


def parse_status_line_pass(
    text: Any,
    *,
    pass_keyword: str = "PASS",
) -> Optional[bool]:
    """Read ``STATUS:`` line if present. None when no STATUS line."""
    keyword = str(pass_keyword or "PASS").strip().upper() or "PASS"
    for line in str(text or "").splitlines():
        s = line.strip()
        if not s.upper().startswith("STATUS:"):
            continue
        status_val = s.split(":", 1)[1].strip().upper()
        if status_val in (keyword, "PASS"):
            return True
        if status_val in (
            "FAIL",
            "FAILED",
            "REJECT",
            "REJECTED",
            "NO",
            "FALSE",
        ):
            return False
        # Unknown STATUS value is not a pass.
        return False
    return None


def is_pass_keyword_verdict(text: Any, pass_keyword: str = "PASS") -> bool:
    """Reflection critic: STATUS line wins; else leading pass keyword only."""
    status = parse_status_line_pass(text, pass_keyword=pass_keyword)
    if status is not None:
        return status
    return is_leading_token(text, pass_keyword)


def is_yes_review(text: Any) -> bool:
    """Producer–reviewer: leading YES only (not mid-string YES / leading NO)."""
    raw = str(text or "").strip()
    if not raw:
        return False
    if is_leading_token(raw, "NO"):
        return False
    return is_leading_token(raw, "YES")


def _coerce_complete_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    token = str(value or "").strip().lower()
    return token in ("true", "yes", "1")


def is_complete_evaluation(text: Any) -> bool:
    """LLM completeness judge: JSON ``complete`` wins; else leading COMPLETE.

    ``{"complete": false}`` contains the substring COMPLETE and must not pass.
    ``COMPLETELY`` / ``NOT COMPLETE`` / mid-string COMPLETE are not a pass.
    """
    raw = str(text or "").strip()
    if not raw:
        return False
    from core.utils.json_utils import parse_json

    obj = parse_json(raw)
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).strip().lower() == "complete":
                return _coerce_complete_flag(value)
        return False
    head = raw.splitlines()[0].strip()
    if is_leading_token(head, "INCOMPLETE") or is_leading_token(head, "NOT"):
        return False
    return is_leading_token(head, "COMPLETE")


def is_same_task_verdict(text: Any) -> bool:
    """Continuity classifier: JSON ``same_task`` wins; else leading SAME.

    ``{"same_task": false}`` contains the substring SAME and must not match.
    Leading NEW / mid-string SAME / ``SAMENESS`` are not the same task.
    """
    raw = str(text or "").strip()
    if not raw:
        return False
    from core.utils.json_utils import parse_json

    obj = parse_json(raw)
    if isinstance(obj, dict):
        for key, value in obj.items():
            if str(key).strip().lower() == "same_task":
                return _coerce_complete_flag(value)
        return False
    head = raw.splitlines()[0].strip()
    if is_leading_token(head, "NEW"):
        return False
    return is_leading_token(head, "SAME")
