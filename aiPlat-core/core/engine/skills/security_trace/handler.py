"""Rule-first security_trace handler — Phase B (no LLM).

Builds clipped anchors for each plan hot_path by reading entry/sink files only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_GATE_PATTERNS = [
    re.compile(r"\bDepends\s*\("),
    re.compile(r"\bPolicyGate\b"),
    re.compile(r"\brequire_auth\b"),
    re.compile(r"\brequire_role\b"),
    re.compile(r"\bcheck_ssrf\b"),
    re.compile(r"\bvalidate_url\b"),
    re.compile(r"\bmfa_required\b"),
]

_SINK_LINE = {
    "subprocess": re.compile(r"\bsubprocess\.(run|Popen|call)\b|\bos\.system\b"),
    "eval_exec": re.compile(r"(?<![\w.])eval\s*\(\s*['\"\w(]|(?<![\w.])exec\s*\(\s*['\"\w(]"),
    "deserialize": re.compile(r"\bpickle\.loads\b|\byaml\.load\s*\("),
    "network_egress": re.compile(r"\brequests\.(get|post)\b|\bhttpx\.(get|post)\b|\burlopen\s*\("),
    "sql": re.compile(r"execute\s*\("),
}


def _parse_entry_file(entry_id: str) -> str:
    # entry:{relpath}
    return str(entry_id or "").removeprefix("entry:")


def _parse_sink(sink_id: str) -> Tuple[str, str]:
    # sink:{kind}:{relpath}
    parts = str(sink_id or "").split(":", 2)
    if len(parts) >= 3:
        return parts[1], parts[2]
    if len(parts) == 2:
        return parts[1], ""
    return "", ""


def _repo_root() -> Path:
    from core.harness.knowledge.code_graph import repo_root

    return repo_root()


def _read_lines(rel: str, max_lines: int = 400) -> List[str]:
    if not rel:
        return []
    p = _repo_root() / rel
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return text.splitlines()[:max_lines]


def _find_anchor(lines: List[str], pattern: Optional[re.Pattern], *, fallback_first: bool = False) -> Dict[str, Any]:
    if pattern:
        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                return {"line": i, "snippet": line.strip()[:160]}
    if fallback_first and lines:
        return {"line": 1, "snippet": lines[0].strip()[:160]}
    return {"line": None, "snippet": ""}


def _gate_hits(lines: List[str]) -> List[str]:
    hits: List[str] = []
    blob = "\n".join(lines)
    for rx in _GATE_PATTERNS:
        if rx.search(blob):
            hits.append(rx.pattern)
    return hits


def _artifact(params: Dict[str, Any], key: str) -> Dict[str, Any]:
    v = params.get(key)
    if isinstance(v, dict):
        return v
    return {}


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    plan = _artifact(params, "security_plan")
    paths = plan.get("top_hot_paths") or []
    traces: List[Dict[str, Any]] = []

    for h in paths:
        if not isinstance(h, dict):
            continue
        entry_file = _parse_entry_file(str(h.get("entry_id") or ""))
        sink_kind, sink_file = _parse_sink(str(h.get("sink_id") or ""))
        entry_lines = _read_lines(entry_file)
        sink_lines = _read_lines(sink_file)
        sink_rx = _SINK_LINE.get(sink_kind)
        entry_anchor = _find_anchor(
            entry_lines,
            re.compile(r"@router\.(get|post|put|patch|delete)\b|def\s+\w+"),
            fallback_first=True,
        )
        sink_anchor = _find_anchor(sink_lines, sink_rx, fallback_first=True)
        possible_gates = list(dict.fromkeys(_gate_hits(entry_lines) + _gate_hits(sink_lines)))
        anchors = []
        if entry_file:
            anchors.append({"file": entry_file, **entry_anchor})
        if sink_file and sink_file != entry_file:
            anchors.append({"file": sink_file, **sink_anchor})
        traces.append(
            {
                "path_id": h.get("id"),
                "entry_id": h.get("entry_id"),
                "sink_id": h.get("sink_id"),
                "anchors": anchors,
                "possible_gates": possible_gates,
                "confidence": "heuristic",
                "notes": [
                    "trace built by deterministic handler; snippets only",
                ],
            }
        )

    return {
        "traces": traces,
        "notes": [
            "Phase B security_trace handler — no LLM",
            f"traced={len(traces)}",
        ],
        "heuristic": True,
    }
