"""P0: deterministic run-level Mermaid (tool_result facts, no LLM)."""
from __future__ import annotations

from types import SimpleNamespace

from core.harness.execution.run_structure_diagram import (
    STATE_STRUCTURE_KEY,
    build_run_structure_diagram,
    stages_to_mermaid,
    write_structure_diagram,
)


def test_stages_to_mermaid_depends_and_artifacts():
    stages = [
        SimpleNamespace(
            id="pm",
            output_artifact="prd",
            depends_on=[],
            input_artifacts=[],
        ),
        SimpleNamespace(
            id="arch",
            output_artifact="architecture",
            depends_on=["pm"],
            input_artifacts=["prd"],
        ),
        SimpleNamespace(
            id="code",
            output_artifact="code",
            depends_on=[],
            input_artifacts=["architecture"],
        ),
    ]
    mermaid, refs = stages_to_mermaid(stages)
    assert "flowchart LR" in mermaid
    assert 'pm["pm →prd"]' in mermaid or "pm[" in mermaid
    assert "-->" in mermaid
    assert all(r.get("source_type") == "tool_result" for r in refs)
    assert all(r.get("confidence") == "1.0" for r in refs)
    assert any(r.get("href") == "#artifact:prd" for r in refs)


def test_build_and_write_structure_diagram():
    stages = [
        {"id": "a", "output_artifact": "x", "depends_on": []},
        {"id": "b", "output_artifact": "y", "depends_on": ["a"], "input_artifacts": ["x"]},
    ]
    payload = build_run_structure_diagram({}, stages=stages)
    assert payload["schema_version"] == "structure.v1"
    assert payload["source_type"] == "tool_result"
    assert payload["confidence"] == 1.0
    assert "flowchart" in payload["mermaid"]
    state: dict = {}
    written = write_structure_diagram(state, stages=stages)
    assert state[STATE_STRUCTURE_KEY] is written
    assert written["mermaid"] == payload["mermaid"]


def test_empty_stages():
    mermaid, refs = stages_to_mermaid([])
    assert "no stages" in mermaid
    assert refs == []
