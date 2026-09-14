"""Unit tests for Phase A security_view compiler (no LLM, fake graph)."""

from __future__ import annotations

from pathlib import Path

from core.harness.knowledge.security_view import (
    SCHEMA_VERSION,
    build_security_view,
    compact_security_digest,
)


def _tiny_repo(tmp_path: Path) -> Path:
    """Create a minimal repo layout for path-based detection."""
    entry = tmp_path / "aiPlat-platform" / "api" / "routers"
    entry.mkdir(parents=True)
    (entry / "demo.py").write_text(
        '''
from fastapi import APIRouter
router = APIRouter()

@router.post("/demo")
def create_demo(url: str):
    import requests
    return requests.get(url)
''',
        encoding="utf-8",
    )
    sink = tmp_path / "aiPlat-infra" / "utils"
    sink.mkdir(parents=True)
    (sink / "http.py").write_text(
        "import requests\ndef fetch(u):\n    return requests.get(u)\n",
        encoding="utf-8",
    )
    gate = tmp_path / "aiPlat-core" / "harness"
    gate.mkdir(parents=True)
    (gate / "ssrf.py").write_text(
        "def check_ssrf(url: str) -> bool:\n    return True\n",
        encoding="utf-8",
    )
    return tmp_path


def test_build_security_view_from_injected_nodes(tmp_path, monkeypatch):
    root = _tiny_repo(tmp_path)
    entry_rel = "aiPlat-platform/api/routers/demo.py"
    sink_rel = "aiPlat-infra/utils/http.py"
    gate_rel = "aiPlat-core/harness/ssrf.py"

    nodes = {
        entry_rel: {
            "id": entry_rel,
            "path": entry_rel,
            "out": [sink_rel, gate_rel],
            "in": 0,
            "symbols": [("create_demo", "function", 5, None)],
            "routes": [("/demo", "create_demo")],
        },
        sink_rel: {
            "id": sink_rel,
            "path": sink_rel,
            "out": [],
            "in": 1,
            "symbols": [("fetch", "function", 2, None)],
        },
        gate_rel: {
            "id": gate_rel,
            "path": gate_rel,
            "out": [],
            "in": 1,
            "symbols": [("check_ssrf", "function", 1, None)],
        },
    }
    edges = [
        {"from": entry_rel, "to": sink_rel},
        {"from": entry_rel, "to": gate_rel},
    ]

    monkeypatch.setattr(
        "core.harness.knowledge.code_graph.repo_root",
        lambda: root,
    )
    # Avoid real graph build / layer path quirks for unknown roots
    monkeypatch.setattr(
        "core.harness.knowledge.code_graph._layer_bucket",
        lambda p: (
            "platform"
            if "platform" in p
            else "infra"
            if "infra" in p
            else "core"
            if "core" in p
            else "unknown"
        ),
    )

    rules = {
        "entry": {
            "python": [
                {
                    "kind": "http_route",
                    "trust": "external",
                    "match": {
                        "path_contains": ["/api/", "/routers/"],
                        "text_regex": [r"@router\.(get|post)\b"],
                    },
                }
            ]
        },
        "sink": {
            "python": [
                {
                    "kind": "network_egress",
                    "match": {"text_regex": [r"\brequests\.(get|post)\b"]},
                }
            ]
        },
        "gate": {
            "python": [
                {"kind": "ssrf", "match": {"text_regex": [r"\bcheck_ssrf\b"]}}
            ]
        },
    }

    sv = build_security_view(
        repo_id="test",
        nodes=nodes,
        edges=edges,
        rules=rules,
        cache=False,
        force=True,
    )
    assert sv.schema_version == SCHEMA_VERSION
    assert any(e.kind == "http_route" for e in sv.entries)
    assert any(s.kind == "network_egress" for s in sv.sinks)
    assert any(g.kind == "ssrf" for g in sv.gates)
    assert sv.hot_paths
    assert all(h.heuristic for h in sv.hot_paths)
    assert "heuristic" in (sv.repo_summary.notes[0] if sv.repo_summary.notes else "heuristic")
    digest = compact_security_digest(sv)
    assert digest.get("_token_estimate", 0) > 0
    assert "top_hot_paths" in digest


def test_empty_graph():
    sv = build_security_view(
        repo_id="empty",
        nodes={},
        edges=[],
        rules={},
        cache=False,
        force=True,
    )
    assert sv.entries == []
    assert sv.sinks == []
    assert sv.hot_paths == []


def test_path_scoring_prefers_unguarded_external(tmp_path, monkeypatch):
    root = tmp_path
    (root / "platform" / "api").mkdir(parents=True)
    (root / "infra").mkdir(parents=True)
    e = "platform/api/r.py"
    s = "infra/http.py"
    (root / e).write_text("@router.post\ndef h():\n    pass\n", encoding="utf-8")
    (root / s).write_text("import requests\nrequests.get('x')\n", encoding="utf-8")

    nodes = {
        e: {"id": e, "path": e, "out": [s], "in": 0, "symbols": [], "routes": [("/x", "h")]},
        s: {"id": s, "path": s, "out": [], "in": 1, "symbols": []},
    }
    monkeypatch.setattr("core.harness.knowledge.code_graph.repo_root", lambda: root)
    monkeypatch.setattr(
        "core.harness.knowledge.code_graph._layer_bucket",
        lambda p: "platform" if "platform" in p else "infra",
    )
    rules = {
        "entry": {
            "python": [
                {
                    "kind": "http_route",
                    "trust": "external",
                    "match": {"path_contains": ["/api/"], "text_regex": [r"@router\.post"]},
                }
            ]
        },
        "sink": {
            "python": [
                {"kind": "network_egress", "match": {"text_regex": [r"requests\.get"]}}
            ]
        },
        "gate": {"python": []},
    }
    sv = build_security_view(
        nodes=nodes, edges=[{"from": e, "to": s}], rules=rules, cache=False, force=True
    )
    assert sv.hot_paths
    assert any("without_gate" in h.risk_hint for h in sv.hot_paths)
    assert sv.hot_paths[0].score >= sv.hot_paths[-1].score
