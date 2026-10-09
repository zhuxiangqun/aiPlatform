"""Deterministic run-level Mermaid structure diagram (no LLM).

Nodes come from PipelineStageConfig ids / depends_on / input_artifacts /
output_artifact only. Facts are tool-derived; LLM must not invent nodes.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

STATE_STRUCTURE_KEY = "_structure_diagram"
SCHEMA_VERSION = "structure.v1"

_SAFE_ID = re.compile(r"[^A-Za-z0-9_]")


def _node_id(raw: str, *, prefix: str = "n") -> str:
    s = _SAFE_ID.sub("_", str(raw or "").strip())
    if not s:
        s = "empty"
    if s[0].isdigit():
        s = f"{prefix}_{s}"
    return s[:64]


def _label(text: str) -> str:
    """Mermaid node label — escape quotes; keep real symbol names."""
    t = str(text or "").replace('"', "'").replace("\n", " ")
    return t[:80] if t else "?"


def stages_to_mermaid(stages: Sequence[Any]) -> Tuple[str, List[Dict[str, str]]]:
    """Build flowchart from stage topology.

    Edges: depends_on → stage; input_artifacts producers → consumers by
    matching output_artifact names.
    """
    stage_list = list(stages or [])
    if not stage_list:
        return ("flowchart LR\n  empty([no stages])\n", [])

    by_id: Dict[str, Any] = {}
    by_artifact: Dict[str, str] = {}  # output_artifact → stage_id
    node_refs: List[Dict[str, str]] = []
    lines: List[str] = ["flowchart LR"]

    for st in stage_list:
        sid = str(getattr(st, "id", None) or (st.get("id") if isinstance(st, Mapping) else "") or "").strip()
        if not sid:
            continue
        by_id[sid] = st
        art = str(
            getattr(st, "output_artifact", None)
            or (st.get("output_artifact") if isinstance(st, Mapping) else "")
            or ""
        ).strip()
        if art:
            by_artifact[art] = sid
        nid = _node_id(sid, prefix="s")
        label_bits = [sid]
        if art:
            label_bits.append(f"→{art}")
        lines.append(f'  {nid}["{_label(" ".join(label_bits))}"]')
        ref: Dict[str, str] = {
            "id": nid,
            "stage_id": sid,
            "kind": "stage",
            "source_type": "tool_result",
            "confidence": "1.0",
        }
        if art:
            ref["artifact"] = art
            ref["href"] = f"#artifact:{art}"
        node_refs.append(ref)

    edges: set[Tuple[str, str]] = set()

    def _add_edge(src_sid: str, dst_sid: str) -> None:
        if not src_sid or not dst_sid or src_sid == dst_sid:
            return
        if src_sid not in by_id or dst_sid not in by_id:
            return
        key = (src_sid, dst_sid)
        if key in edges:
            return
        edges.add(key)
        lines.append(f"  {_node_id(src_sid, prefix='s')} --> {_node_id(dst_sid, prefix='s')}")

    for st in stage_list:
        sid = str(getattr(st, "id", None) or (st.get("id") if isinstance(st, Mapping) else "") or "").strip()
        if not sid:
            continue
        deps = getattr(st, "depends_on", None)
        if deps is None and isinstance(st, Mapping):
            deps = st.get("depends_on")
        for dep in deps or []:
            _add_edge(str(dep).strip(), sid)

        inputs = getattr(st, "input_artifacts", None)
        if inputs is None and isinstance(st, Mapping):
            inputs = st.get("input_artifacts")
        for art in inputs or []:
            producer = by_artifact.get(str(art).strip())
            if producer:
                _add_edge(producer, sid)

    # Sequential fallback when no edges declared
    if not edges and len(by_id) > 1:
        ordered = [
            str(getattr(st, "id", None) or (st.get("id") if isinstance(st, Mapping) else "") or "").strip()
            for st in stage_list
        ]
        ordered = [x for x in ordered if x]
        for a, b in zip(ordered, ordered[1:]):
            _add_edge(a, b)

    # Click hints (Mermaid); consumers may ignore
    for ref in node_refs:
        href = ref.get("href")
        if href:
            lines.append(f'  click {ref["id"]} "{href}" "open artifact"')

    return ("\n".join(lines) + "\n", node_refs)


def build_run_structure_diagram(
    state: Optional[Mapping[str, Any]] = None,
    *,
    stages: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Return structure payload — deterministic, no LLM."""
    stage_seq: Sequence[Any] = stages or ()
    # Only read the generic `stages` key (baseline OK); callers should pass stages=
    if not stage_seq and isinstance(state, Mapping):
        raw = state.get("stages")
        if isinstance(raw, list):
            stage_seq = raw

    mermaid, node_refs = stages_to_mermaid(stage_seq)
    layer = {
        "name": "stages",
        "source_type": "tool_result",
        "confidence": 1.0,
        "node_count": len(node_refs),
        "edge_hint": "depends_on + input_artifacts→output_artifact",
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "mermaid": mermaid,
        "layers": {"stages": layer},
        "node_refs": node_refs,
        "source_type": "tool_result",
        "confidence": 1.0,
        "hint": (
            "Deterministic stage topology. Nodes are real stage.id / output_artifact; "
            "not LLM-invented. Click href → #artifact:<key>."
        ),
    }


def write_structure_diagram(
    state: MutableMapping[str, Any],
    *,
    stages: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Persist under state[_structure_diagram] (best-effort like bloat metrics)."""
    payload = build_run_structure_diagram(state, stages=stages)
    state[STATE_STRUCTURE_KEY] = payload
    return payload
