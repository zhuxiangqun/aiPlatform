"""
Evidence diff for regression comparison.

Input: two evidence_pack payloads (dicts) from browser-driven evaluation.
Output: a structured diff + human-readable summary suitable for evaluator prompts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional
import hashlib
import json


def _as_list(x: Any) -> List[Any]:
    return x if isinstance(x, list) else []


def _as_dict(x: Any) -> Dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _norm_str(x: Any) -> str:
    return str(x or "").strip()


def _console_key(m: Dict[str, Any]) -> str:
    # tolerate various shapes from MCP tool
    level = _norm_str(m.get("type") or m.get("level") or m.get("severity"))
    text = _norm_str(m.get("text") or m.get("message") or m.get("msg"))
    loc = _norm_str(m.get("location") or m.get("url"))
    return f"{level}|{text}|{loc}"


def _network_key(r: Dict[str, Any]) -> str:
    url = _norm_str(r.get("url"))
    method = _norm_str(r.get("method"))
    status = _norm_str(r.get("status") or r.get("statusCode"))
    return f"{method}|{status}|{url}"


def _extract_snapshot_title(snapshot: Any) -> str:
    s = _as_dict(snapshot)
    # common fields
    for k in ("title", "pageTitle", "documentTitle"):
        if k in s and _norm_str(s.get(k)):
            return _norm_str(s.get(k))
    # sometimes nested
    meta = _as_dict(s.get("meta") or s.get("metadata"))
    if _norm_str(meta.get("title")):
        return _norm_str(meta.get("title"))
    return ""


def compute_evidence_diff(base: Dict[str, Any], cur: Dict[str, Any]) -> Dict[str, Any]:
    base0 = _as_dict(base)
    cur0 = _as_dict(cur)

    base_console = [_as_dict(x) for x in _as_list(base0.get("console_messages"))]
    cur_console = [_as_dict(x) for x in _as_list(cur0.get("console_messages"))]

    base_net = [_as_dict(x) for x in _as_list(base0.get("network_requests"))]
    cur_net = [_as_dict(x) for x in _as_list(cur0.get("network_requests"))]

    base_snapshot = base0.get("snapshot")
    cur_snapshot = cur0.get("snapshot")
    base_cov = _as_dict(base0.get("coverage"))
    cur_cov = _as_dict(cur0.get("coverage"))
    base_tags = [str(x) for x in _as_list(base_cov.get("executed_tags")) if str(x).strip()]
    cur_tags = [str(x) for x in _as_list(cur_cov.get("executed_tags")) if str(x).strip()]

    # visual regression: per-tag screenshot hash (best-effort)
    base_by_tag = _as_dict(base0.get("by_tag"))
    cur_by_tag = _as_dict(cur0.get("by_tag"))

    def _hash_screen(x: Any) -> str:
        try:
            s = json.dumps(x, ensure_ascii=False, sort_keys=True)
        except Exception:
            s = str(x)
        return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()[:12]

    changed_screenshot_tags: List[str] = []
    try:
        common = set(base_by_tag.keys()) & set(cur_by_tag.keys())
        for tag in sorted(list(common))[:100]:
            b = _as_dict(base_by_tag.get(tag)).get("screenshot")
            c = _as_dict(cur_by_tag.get(tag)).get("screenshot")
            if b is None or c is None:
                continue
            if _hash_screen(b) != _hash_screen(c):
                changed_screenshot_tags.append(str(tag))
    except Exception:
        changed_screenshot_tags = []

    base_console_set = {_console_key(m) for m in base_console if _console_key(m)}
    cur_console_set = {_console_key(m) for m in cur_console if _console_key(m)}
    new_console = sorted(list(cur_console_set - base_console_set))[:50]

    base_net_set = {_network_key(r) for r in base_net if _network_key(r)}
    cur_net_set = {_network_key(r) for r in cur_net if _network_key(r)}
    new_net = sorted(list(cur_net_set - base_net_set))[:50]

    base_title = _extract_snapshot_title(base_snapshot)
    cur_title = _extract_snapshot_title(cur_snapshot)

    summary_parts: List[str] = []
    if base_title or cur_title:
        if base_title != cur_title:
            summary_parts.append(f"页面标题变化：'{base_title}' → '{cur_title}'")
        else:
            summary_parts.append(f"页面标题一致：'{cur_title}'")
    summary_parts.append(f"新增 console 条目：{len(new_console)}")
    summary_parts.append(f"新增 network 条目：{len(new_net)}")

    # Regression-oriented metrics (best-effort)
    def _level_from_console_key(k: str) -> str:
        return (k.split("|", 1)[0] if "|" in k else k).strip().lower()

    def _status_from_net_key(k: str) -> int:
        # method|status|url
        try:
            parts = k.split("|")
            if len(parts) >= 2:
                return int(str(parts[1]).strip())
        except Exception:
            pass
        return 0

    new_console_errors = [k for k in new_console if "error" in _level_from_console_key(k)]
    new_console_warns = [k for k in new_console if "warn" in _level_from_console_key(k)]

    new_net_5xx = [k for k in new_net if 500 <= _status_from_net_key(k) <= 599]
    new_net_4xx = [k for k in new_net if 400 <= _status_from_net_key(k) <= 499]

    return {
        "schema_version": "0.1",
        "base_evidence_pack_id": _norm_str(base0.get("evidence_pack_id") or ""),
        "new_evidence_pack_id": _norm_str(cur0.get("evidence_pack_id") or ""),
        "summary": "；".join([p for p in summary_parts if p]),
        "diff": {
            "title": {"base": base_title, "new": cur_title},
            "console_new": new_console,
            "network_new": new_net,
            "coverage": {
                "executed_tags_added": sorted(list(set(cur_tags) - set(base_tags)))[:50],
                "executed_tags_removed": sorted(list(set(base_tags) - set(cur_tags)))[:50],
            },
            "visual": {"changed_screenshot_tags": changed_screenshot_tags[:50]},
        },
        "metrics": {
            "new_console_errors": len(new_console_errors),
            "new_console_warns": len(new_console_warns),
            "new_network_5xx": len(new_net_5xx),
            "new_network_4xx": len(new_net_4xx),
            "changed_screenshot_tags": len(changed_screenshot_tags),
        },
        "stats": {
            "base": {"console": len(base_console), "network": len(base_net)},
            "new": {"console": len(cur_console), "network": len(cur_net)},
        },
    }


def evaluate_regression(diff: Dict[str, Any], gate: Dict[str, Any], *, executed_tags: Optional[List[str]] = None) -> Tuple[bool, List[str]]:
    """
    Return (is_regression, reasons).
    gate example:
      { "max_new_console_errors": 0, "max_new_network_5xx": 0, "max_new_network_4xx": 5 }
    """
    d = _as_dict(diff)
    m = _as_dict(d.get("metrics"))
    g = _as_dict(gate)

    reasons: List[str] = []
    try:
        max_err = int(g.get("max_new_console_errors", 0))
    except Exception:
        max_err = 0
    try:
        max_5xx = int(g.get("max_new_network_5xx", 0))
    except Exception:
        max_5xx = 0
    try:
        max_4xx = int(g.get("max_new_network_4xx", 999999))
    except Exception:
        max_4xx = 999999
    try:
        max_changed_shots = int(g.get("max_changed_screenshot_tags", 999999))
    except Exception:
        max_changed_shots = 999999

    new_err = int(m.get("new_console_errors") or 0)
    new_5xx = int(m.get("new_network_5xx") or 0)
    new_4xx = int(m.get("new_network_4xx") or 0)
    changed_shots = int(m.get("changed_screenshot_tags") or 0)

    if new_err > max_err:
        reasons.append(f"新增 console error {new_err} > {max_err}")
    if new_5xx > max_5xx:
        reasons.append(f"新增 network 5xx {new_5xx} > {max_5xx}")
    if new_4xx > max_4xx:
        reasons.append(f"新增 network 4xx {new_4xx} > {max_4xx}")
    if changed_shots > max_changed_shots:
        reasons.append(f"截图变化 tag 数 {changed_shots} > {max_changed_shots}")

    # Coverage gate: required tags must be executed (best-effort)
    req = g.get("required_tags")
    if isinstance(req, list) and executed_tags is not None:
        ex = set([str(x).strip() for x in executed_tags if str(x).strip()])
        missing = [str(x) for x in req if str(x).strip() and str(x).strip() not in ex]
        if missing:
            reasons.append("缺失关键路径标签：" + ",".join(missing[:20]))
    return (len(reasons) > 0), reasons
