"""Rule-first security_critique handler — Phase B (no LLM).

Severity never exceeds candidate. Prefer refute over keep when uncertain gates exist.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Ops / installer sinks that are usually intentional (not user-tainted)
_OPS_SINK_HINTS = (
    "diagnostics.py",
    "health_checker.py",
    "asset_installer.py",
    "model/health",
    "overview.py",
)

# Dev / governance tooling — import-reachable from many APIs, not request taint sinks
_INTERNAL_TOOLING_SINKS = (
    "arch_guard_base.py",
    "arch_guard",
    "autoreview/diff_loader.py",
    "harness/context/engine.py",
    "architecture_guard",
)

# Infra ops plane (network/node/storage/scheduler/model managers) — intentional subprocess
_INFRA_MGMT_SINKS = (
    "infra/management/",
    "aiPlat-infra/infra/management/",
    "health_checker.py",
)

_ACCEPTED_RISK_ENTRY = (
    "fde_acceptance.py",
    "fde_reports.py",
    "overview.py",
    "diagnostics.py",
    "compat.py",
)

_FDE_OR_ADMIN_ENTRY = (
    "/apps/fde/",
    "/apps/workbench/",
    "fde_acceptance.py",
    "fde_reports.py",
)

_SINK_EVIDENCE = {
    "subprocess": re.compile(r"\bsubprocess\.(run|Popen|call)\b|\bos\.system\b"),
    "eval_exec": re.compile(r"(?<![\w.])eval\s*\(\s*['\"\w(]|(?<![\w.])exec\s*\(\s*['\"\w(]"),
    "deserialize": re.compile(r"\bpickle\.loads\b|\byaml\.load\s*\("),
    "network_egress": re.compile(r"\brequests\.(get|post)\b|\bhttpx\.(get|post)\b|\burlopen\s*\("),
    "sql": re.compile(r"\bexecute\s*\("),
}

_PROSE_EVAL = re.compile(
    r"eval_score|Golden Query|evaluation\b|^\s*\d+\.\s+eval\b",
    re.I,
)

_FIXED_CMD = re.compile(
    r"""\b(git|bash|lsof|shlex\.split|proc_cmd)\b|"""
    r"""subprocess\.run\(\s*\[\s*['\"]git['\"]|"""
    r"""subprocess\.run\(\s*\[\s*['\"]bash['\"]|"""
    r"""subprocess\.run\(\s*\[\s*['\"]lsof['\"]""",
    re.I,
)

_READ_ONLY_ROUTE = re.compile(r"@router\.get\b")


def _artifact(params: Dict[str, Any], key: str) -> Dict[str, Any]:
    v = params.get(key)
    return v if isinstance(v, dict) else {}


def _sink_parts(sink_id: str) -> Tuple[str, str]:
    parts = str(sink_id or "").split(":", 2)
    if len(parts) >= 3:
        return parts[1], parts[2]
    return "", str(sink_id or "")


def _category(kind: str) -> str:
    return {
        "subprocess": "rce",
        "eval_exec": "rce",
        "deserialize": "rce",
        "network_egress": "ssrf",
        "sql": "injection",
    }.get(kind, "other")


def _trace_map(trace_doc: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for t in trace_doc.get("traces") or []:
        if isinstance(t, dict) and t.get("path_id"):
            out[str(t["path_id"])] = t
    return out


def _sink_anchor_snippet(anchors: List[Any], sink_file: str) -> str:
    for a in anchors or []:
        if not isinstance(a, dict):
            continue
        if sink_file and str(a.get("file") or "").endswith(sink_file.split("/")[-1]):
            return str(a.get("snippet") or "")
        if sink_file and sink_file in str(a.get("file") or ""):
            return str(a.get("snippet") or "")
    # fallback: last anchor often sink
    if anchors and isinstance(anchors[-1], dict):
        return str(anchors[-1].get("snippet") or "")
    return ""


def _entry_anchor_snippet(anchors: List[Any], entry_file: str) -> str:
    for a in anchors or []:
        if not isinstance(a, dict):
            continue
        f = str(a.get("file") or "")
        if entry_file and (entry_file in f or f.endswith(entry_file.split("/")[-1])):
            return str(a.get("snippet") or "")
    if anchors and isinstance(anchors[0], dict):
        return str(anchors[0].get("snippet") or "")
    return ""


async def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    plan = _artifact(params, "security_plan")
    trace = _artifact(params, "security_trace")
    paths = plan.get("top_hot_paths") or []
    by_id = _trace_map(trace)

    findings: List[Dict[str, Any]] = []
    refuted: List[Dict[str, Any]] = []

    for h in paths:
        if not isinstance(h, dict):
            continue
        path_id = str(h.get("id") or "")
        sink_kind, sink_file = _sink_parts(str(h.get("sink_id") or ""))
        entry_id = str(h.get("entry_id") or "")
        entry_file = entry_id.removeprefix("entry:")
        tr = by_id.get(path_id) or {}
        possible_gates = list(tr.get("possible_gates") or [])
        gates_on = list(h.get("gates_on_path") or [])
        anchors = tr.get("anchors") or []

        # Rule 1: explicit gate on import path
        if gates_on:
            refuted.append({"path_id": path_id, "reason": f"gate_on_path={gates_on}"})
            continue

        # Rule 2: counterfactual — gate symbols in entry/sink text
        if possible_gates:
            refuted.append(
                {
                    "path_id": path_id,
                    "reason": f"gate_likely_in_anchors={possible_gates[:3]}",
                    "gate_search": possible_gates[:5],
                }
            )
            continue

        # Rule 3: ops / installer accepted risk (heuristic)
        if any(x in sink_file for x in _OPS_SINK_HINTS) and any(
            x in entry_file for x in _ACCEPTED_RISK_ENTRY
        ):
            refuted.append(
                {"path_id": path_id, "reason": "accepted_risk:ops_or_installer_path"}
            )
            continue

        # Rule 3b: infra management ops plane (any entry → infra/management subprocess)
        if any(x in sink_file for x in _INFRA_MGMT_SINKS):
            refuted.append(
                {
                    "path_id": path_id,
                    "reason": "accepted_risk:infra_management_ops",
                }
            )
            continue

        # Rule 4: empty anchors → refute (cannot verify)
        if not anchors:
            refuted.append({"path_id": path_id, "reason": "no_anchors"})
            continue

        sink_snip = _sink_anchor_snippet(anchors, sink_file)
        entry_snip = _entry_anchor_snippet(anchors, entry_file)

        # Rule 5: weak sink anchor — snippet does not evidence the declared sink kind
        # (e.g. file header docstring matched instead of real subprocess/sql line)
        evidence_rx = _SINK_EVIDENCE.get(sink_kind)
        if evidence_rx and (not sink_snip or not evidence_rx.search(sink_snip)):
            refuted.append(
                {
                    "path_id": path_id,
                    "reason": "weak_sink_anchor",
                    "detail": (sink_snip or "")[:80],
                }
            )
            continue

        # Rule 5b: prose / docstring "eval (" false positive (e.g. "Golden Query eval (")
        if sink_kind == "eval_exec" and sink_snip and _PROSE_EVAL.search(sink_snip):
            refuted.append(
                {
                    "path_id": path_id,
                    "reason": "prose_eval_false_positive",
                    "detail": sink_snip[:80],
                }
            )
            continue

        # Rule 6: internal tooling sinks (arch_guard / autoreview / context engine)
        if any(x in sink_file for x in _INTERNAL_TOOLING_SINKS):
            if any(x in entry_file for x in _FDE_OR_ADMIN_ENTRY):
                refuted.append(
                    {
                        "path_id": path_id,
                        "reason": "accepted_risk:admin_entry_to_internal_tooling",
                    }
                )
                continue
            # Even from other entries: fixed-cmd tooling is not request RCE
            if sink_snip and _FIXED_CMD.search(sink_snip):
                refuted.append(
                    {
                        "path_id": path_id,
                        "reason": "accepted_risk:fixed_cmd_internal_tooling",
                    }
                )
                continue
            # core/api routers → core internal tooling is still import FP
            if "/api/routers/" in entry_file or "/apps/" in entry_file:
                refuted.append(
                    {
                        "path_id": path_id,
                        "reason": "accepted_risk:router_to_internal_tooling",
                    }
                )
                continue

        # Rule 7: fixed-argument subprocess (git/bash/proc_cmd) — no user format
        if sink_kind == "subprocess" and sink_snip and _FIXED_CMD.search(sink_snip):
            # reject if also looks user-formatted
            if "%s" not in sink_snip and "{}" not in sink_snip and "f\"" not in sink_snip:
                refuted.append(
                    {"path_id": path_id, "reason": "accepted_risk:fixed_cmd_subprocess"}
                )
                continue

        # Rule 8: read-only FDE/admin GET → internal core sink (import FP)
        if (
            entry_snip
            and _READ_ONLY_ROUTE.search(entry_snip)
            and any(x in entry_file for x in _FDE_OR_ADMIN_ENTRY)
            and ("/core/" in sink_file or "aiPlat-core/" in sink_file)
            and sink_kind in ("subprocess", "sql", "eval_exec")
        ):
            refuted.append(
                {
                    "path_id": path_id,
                    "reason": "accepted_risk:readonly_admin_get_to_core_tooling",
                }
            )
            continue

        # Keep as candidate
        findings.append(
            {
                "path_id": path_id,
                "severity": "candidate",
                "category": _category(sink_kind),
                "summary": (
                    f"Heuristic reachability {entry_file} → {sink_kind}:{sink_file} "
                    f"(risk={h.get('risk_hint')})"
                ),
                "evidence_anchors": anchors,
                "gate_search": [],
                "heuristic": True,
                "score": h.get("score"),
                "entry_id": entry_id,
                "sink_id": h.get("sink_id"),
            }
        )

    return {
        "findings": findings,
        "refuted": refuted,
        "notes": [
            "Phase B security_critique handler — rules only, no LLM",
            "max_severity=candidate",
            "rules: gate/ops/weak_anchor/internal_tooling/fixed_cmd/readonly_admin",
        ],
        "heuristic": True,
        "counts": {"findings": len(findings), "refuted": len(refuted)},
    }
