"""Deterministic security_plan handler — Phase B plan stage (no LLM)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from typing import Any, Dict, List, Set

# Phase B defaults from full-repo baseline (2026-09-14 → widened 2026-09-14)
DEFAULT_MAX_PATHS = 20
DEFAULT_MAX_DEPTH = 6
DEFAULT_DIGEST_MAX_CHARS = 4000
SINK_WHITELIST = frozenset(
    {"subprocess", "eval_exec", "network_egress", "deserialize", "sql"}
)
ENTRY_LAYERS = frozenset({"platform", "app", "core"})
# Cap per sink kind so subprocess does not crowd out SSRF/sql/eval
DEFAULT_PER_KIND_CAP = 8


def _sink_kind(sink_id: str) -> str:
    parts = str(sink_id or "").split(":")
    return parts[1] if len(parts) >= 2 else ""


def _filter_hot_paths(
    hot_paths: List[Any],
    *,
    sink_whitelist: Set[str],
    entry_layers: Set[str],
    max_paths: int,
    per_kind_cap: int = DEFAULT_PER_KIND_CAP,
) -> List[Dict[str, Any]]:
    preferred: List[Dict[str, Any]] = []
    fallback: List[Dict[str, Any]] = []
    for h in hot_paths or []:
        data = asdict(h) if hasattr(h, "__dataclass_fields__") else dict(h)
        kind = _sink_kind(str(data.get("sink_id") or ""))
        if sink_whitelist and kind and kind not in sink_whitelist:
            continue
        layer = str(data.get("layer") or "")
        row = {
            "id": data.get("id"),
            "entry_id": data.get("entry_id"),
            "sink_id": data.get("sink_id"),
            "risk_hint": data.get("risk_hint"),
            "score": data.get("score"),
            "via_len": len(data.get("via") or []),
            "gates_on_path": data.get("gates_on_path") or [],
            "layer": layer,
            "heuristic": True,
            "max_severity": "candidate",
            "_kind": kind or "other",
        }
        if not entry_layers or layer in entry_layers:
            preferred.append(row)
        else:
            fallback.append(row)

    pool = preferred if preferred else fallback
    # Already score-sorted from compiler; diversify by sink kind
    kind_counts: Dict[str, int] = defaultdict(int)
    out: List[Dict[str, Any]] = []
    for row in pool:
        kind = str(row.pop("_kind", "other"))
        if kind_counts[kind] >= per_kind_cap:
            continue
        kind_counts[kind] += 1
        out.append(row)
        if len(out) >= max_paths:
            break
    # If under-filled due to caps, top up ignoring cap
    if len(out) < max_paths:
        seen = {r.get("id") for r in out}
        for row in pool:
            rid = row.get("id")
            if rid in seen:
                continue
            cleaned = {k: v for k, v in row.items() if k != "_kind"}
            out.append(cleaned)
            seen.add(rid)
            if len(out) >= max_paths:
                break
    return out


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    """Build filtered security plan digest for downstream trace/critique."""
    from core.harness.knowledge.security_view import (
        build_security_view,
        compact_security_digest,
    )

    max_paths = int(params.get("max_paths") or DEFAULT_MAX_PATHS)
    max_depth = int(params.get("max_depth") or DEFAULT_MAX_DEPTH)
    force = bool(params.get("force") or False)
    digest_max = int(params.get("digest_max_chars") or DEFAULT_DIGEST_MAX_CHARS)
    sink_wl = set(params.get("sink_whitelist") or SINK_WHITELIST)
    entry_layers = set(params.get("entry_layers") or ENTRY_LAYERS)
    per_kind_cap = int(params.get("per_kind_cap") or DEFAULT_PER_KIND_CAP)

    sv = build_security_view(
        max_paths=max(max_paths * 8, 80),
        max_depth=max_depth,
        force=force,
        cache=not force,
    )
    filtered = _filter_hot_paths(
        list(sv.hot_paths),
        sink_whitelist=sink_wl,
        entry_layers=entry_layers,
        max_paths=max_paths,
        per_kind_cap=per_kind_cap,
    )
    digest = compact_security_digest(sv, max_chars=digest_max)
    digest["top_hot_paths"] = filtered
    digest["params"] = {
        "max_paths": max_paths,
        "max_depth": max_depth,
        "sink_whitelist": sorted(sink_wl),
        "entry_layers": sorted(entry_layers),
        "per_kind_cap": per_kind_cap,
        "max_severity": "candidate",
        "autoreview_scope": "clipped_anchors_only",
        "heuristic": True,
    }
    digest["schema_version"] = digest.get("schema_version") or "secview.v1"
    digest["metrics"] = dict(sv.metrics or {})
    digest["counts"] = {
        "entries": len(sv.entries),
        "sinks": len(sv.sinks),
        "gates": len(sv.gates),
        "hot_paths_selected": len(filtered),
    }
    return digest
