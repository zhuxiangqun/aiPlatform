"""
Tag-based assertions for browser evidence (coverage stages).

We evaluate per-tag evidence collected in evidence_pack.by_tag[tag]:
  - snapshot: JSON (from browser_snapshot)
  - console_messages: list
  - network_requests: list
  - duration_ms: float
and compare against expectations.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


def _as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _as_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _count_console_errors(console_messages: Any) -> int:
    cnt = 0
    for m in _as_list(console_messages):
        mm = _as_dict(m)
        level = str(mm.get("type") or mm.get("level") or mm.get("severity") or "").lower()
        if "error" in level:
            cnt += 1
    return cnt


def _count_network_status(network_requests: Any, *, lo: int, hi: int) -> int:
    cnt = 0
    for r in _as_list(network_requests):
        rr = _as_dict(r)
        st = rr.get("status") or rr.get("statusCode")
        try:
            code = int(st)
        except Exception:
            continue
        if lo <= code <= hi:
            cnt += 1
    return cnt


def _snapshot_contains_text(snapshot: Any, text: str) -> bool:
    if not text:
        return True
    try:
        s = json.dumps(snapshot, ensure_ascii=False)
    except Exception:
        s = str(snapshot)
    return str(text) in s


def evaluate_tag_assertions(evidence_pack: Dict[str, Any], tag_expectations: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Returns (ok, failures).

    tag_expectations example:
      {
        "login": {"text_contains": ["Welcome"], "max_console_errors": 0, "max_network_5xx": 0, "max_duration_ms": 5000},
        "save": {"max_network_5xx": 0}
      }
    """
    ev = _as_dict(evidence_pack)
    by_tag = _as_dict(ev.get("by_tag"))
    exp = _as_dict(tag_expectations)

    failures: List[Dict[str, Any]] = []
    for tag, cfg in exp.items():
        tag0 = str(tag or "").strip()
        if not tag0:
            continue
        cfg0 = _as_dict(cfg)
        data = _as_dict(by_tag.get(tag0))
        if not data:
            failures.append({"tag": tag0, "type": "missing_tag_data", "expected": "by_tag entry exists", "actual": None})
            continue

        # text_contains: list[str]
        for t in _as_list(cfg0.get("text_contains")):
            tt = str(t or "")
            if tt and not _snapshot_contains_text(data.get("snapshot"), tt):
                failures.append({"tag": tag0, "type": "text_missing", "expected": tt, "actual": "not_found_in_snapshot"})

        # max_console_errors
        if "max_console_errors" in cfg0:
            try:
                mx = int(cfg0.get("max_console_errors"))
            except Exception:
                mx = 0
            actual = _count_console_errors(data.get("console_messages"))
            if actual > mx:
                failures.append({"tag": tag0, "type": "console_errors", "expected": f"<= {mx}", "actual": actual})

        # max_network_5xx / max_network_4xx
        if "max_network_5xx" in cfg0:
            try:
                mx = int(cfg0.get("max_network_5xx"))
            except Exception:
                mx = 0
            actual = _count_network_status(data.get("network_requests"), lo=500, hi=599)
            if actual > mx:
                failures.append({"tag": tag0, "type": "network_5xx", "expected": f"<= {mx}", "actual": actual})
        if "max_network_4xx" in cfg0:
            try:
                mx = int(cfg0.get("max_network_4xx"))
            except Exception:
                mx = 999999
            actual = _count_network_status(data.get("network_requests"), lo=400, hi=499)
            if actual > mx:
                failures.append({"tag": tag0, "type": "network_4xx", "expected": f"<= {mx}", "actual": actual})

        # max_duration_ms
        if "max_duration_ms" in cfg0:
            try:
                mx = float(cfg0.get("max_duration_ms"))
            except Exception:
                mx = 0.0
            try:
                actual = float(data.get("duration_ms") or 0.0)
            except Exception:
                actual = 0.0
            if mx > 0 and actual > mx:
                failures.append({"tag": tag0, "type": "duration_ms", "expected": f"<= {mx}", "actual": actual})

    return (len(failures) == 0), failures

