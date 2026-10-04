"""Answer extractor — extract answer string from loop output formats.

Handles various output shapes returned by sys_skill_call and ReActLoop.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

_PRODUCT_LIST_KEYS = (
    "test_questions",
    "test_cases",
    "cases",
    "questions",
    "functional_requirements",
    "user_stories",
    "components",
    "files",
    "api_contracts",
)

_COT_HEAD = re.compile(
    r"(?:^|\n)\s*(?:#{1,6}\s*)?(?:步骤\s*\d|方案\s*[ABC]|可能的方案|比较取舍)",
)


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
        peeled = unwrap_react_done_product(s)
        if peeled != s:
            return peeled
        if s.startswith("{") and s.endswith("}"):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, dict):
                    return extract_answer_from_output(parsed) or s
            except Exception:  # noqa: cleanup-best-effort
                pass
        return s
    return str(output or "")


def _raw_decode(s: str, idx: int) -> Tuple[Any, int]:
    obj, end = json.JSONDecoder().raw_decode(s, idx)
    return obj, end


def _first_json_object(s: str, start: int = 0) -> Optional[Tuple[Any, int]]:
    i = s.find("{", start)
    if i < 0:
        return None
    try:
        obj, end = _raw_decode(s, i)
        return obj, end
    except json.JSONDecodeError:
        return None


def _dump_product(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _list_product_len(obj: Any) -> int:
    if not isinstance(obj, dict):
        return 0
    best = 0
    for k in _PRODUCT_LIST_KEYS:
        v = obj.get(k)
        if isinstance(v, list) and v and isinstance(v[0], (dict, str)):
            best = max(best, len(v))
    return best


def _is_done_envelope(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    typ = str(obj.get("type") or "").strip().lower()
    if typ in ("done", "final", "response"):
        return True
    keys = {str(k) for k in obj.keys()}
    return bool(obj.get("answer")) and keys <= {"type", "answer", "text", "response", "input"}


def _recover_named_array(s: str, key: str) -> List[Any]:
    marker = f'"{key}"'
    i = s.find(marker)
    if i < 0:
        return []
    lb = s.find("[", i)
    if lb < 0:
        return []
    items: List[Any] = []
    pos = lb + 1
    n = len(s)
    while pos < n:
        while pos < n and s[pos] in " \n\r\t,":
            pos += 1
        if pos >= n or s[pos] == "]":
            break
        if s[pos] != "{":
            break
        try:
            obj, end = _raw_decode(s, pos)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            items.append(obj)
        pos = end
    return items


def unwrap_react_done_product(text: str) -> str:
    """Peel CoT + ``{"type":"done","answer":...}`` down to the structured product.

    Second-round ReAct often prefixes 「步骤1」analysis and wraps the skill JSON
    as an escaped string. Store/show the product, not the envelope.
    """
    s = str(text or "").strip()
    if not s:
        return s
    cur = s
    for _ in range(8):
        blob = cur
        idx = blob.find('{"type"')
        if idx < 0:
            idx = blob.find("{")
        found = _first_json_object(blob, idx if idx >= 0 else 0) if "{" in blob else None
        if not found:
            recovered: Dict[str, Any] = {}
            qs = _recover_named_array(blob, "test_questions")
            if not qs:
                qs = _recover_named_array(blob, "test_cases")
                if qs:
                    recovered["test_cases"] = qs
            else:
                recovered["test_questions"] = qs
            if qs:
                recovered.setdefault("total_test_cases", len(qs))
                return _dump_product(recovered)
            return cur
        obj, _end = found
        if _is_done_envelope(obj):
            inner = obj.get("answer") or obj.get("text") or obj.get("response")
            if isinstance(inner, (dict, list)):
                cur = _dump_product(inner)
                continue
            if isinstance(inner, str) and inner.strip():
                cur = inner.strip()
                continue
            return cur
        if isinstance(obj, dict) and _list_product_len(obj) >= 1:
            return _dump_product(obj)
        if isinstance(obj, dict) and idx is not None and idx > 0 and _COT_HEAD.search(blob[: idx + 8]):
            # JSON after CoT but not a known product — still prefer the object
            return _dump_product(obj)
        return cur
    return cur


def choose_loop_final_output(reasoning: str, skill_output: str = "") -> str:
    """Pick the structured product over a CoT / truncated done envelope."""
    rs = str(reasoning or "").strip()
    sk = str(skill_output or "").strip()
    u_r = unwrap_react_done_product(rs) if rs else ""
    u_s = unwrap_react_done_product(sk) if sk else ""
    n_r = _list_product_len(_try_obj(u_r))
    n_s = _list_product_len(_try_obj(u_s))
    if n_s > n_r:
        return u_s
    if n_r >= 1:
        return u_r
    if sk and _COT_HEAD.search(rs) and (u_s.startswith("{") or u_s.startswith("[")):
        return u_s
    if u_s and len(u_s) > len(u_r) * 2 and u_s[:1] in "{[":
        return u_s
    return u_r or u_s or rs or sk


def _try_obj(text: str) -> Any:
    s = str(text or "").strip()
    if not s.startswith("{"):
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None
