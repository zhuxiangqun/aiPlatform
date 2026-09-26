"""Phase K3 — OrgRun carries reasoning_paths or explicit skip; never executes."""

from __future__ import annotations

from core.apps.fde.service.k_wave_reason import build_org_run_reasoning


def test_skip_when_no_entity():
    out = build_org_run_reasoning("it-ops", "告警", [])
    assert out["status"] == "skipped"
    assert out["skipped"] == "no_entity"
    assert out["reasoning_paths"] == []
    assert out["can_execute"] is False


def test_paths_from_hits(monkeypatch):
    class _Edge:
        relation_name = "depends_on"
        target_id = "svc-2"

    class _Node:
        entity_name = "svc-1"
        out_edges = [_Edge()]

    class _G:
        _nodes = {"svc-1": _Node(), "svc-2": type("N", (), {"entity_name": "svc-2"})()}

    monkeypatch.setattr(
        "core.harness.ontology_engine.graph_index.GraphIndex.load",
        staticmethod(lambda *_a, **_k: _G()),
    )
    out = build_org_run_reasoning(
        "it-ops",
        "告警",
        [{"entity_id": "svc-1", "entity_name": "svc-1", "class_name": "Service"}],
    )
    assert out["status"] == "ok"
    assert out["can_execute"] is False
    assert out["path_count"] >= 1
    assert any("depends_on" in p for p in out["reasoning_paths"])


def test_run_org_goal_includes_reasoning_step(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    monkeypatch.setattr(
        "core.apps.org.service.org_runtime._resolve_goal",
        lambda *_a, **_k: {
            "goal_id": "g",
            "domain_id": "it-ops",
            "status": "active",
            "exception_policy": {"triage_requires_hitl": False, "max_entities_per_run": 1},
            "query_open": "none",
            "steps": ["locate"],
        },
    )
    monkeypatch.setattr(
        "core.apps.fde.service.governance_deepen.locate_via_ontology",
        lambda *_a, **_k: {"status": "empty", "hits": []},
    )
    monkeypatch.setattr(
        "core.apps.org.service.org_io.fetch_by_entity",
        lambda *_a, **_k: {"status": "ok", "graph": {}, "sandbox": {}},
    )
    from core.apps.org.service.org_runtime import run_org_goal

    run = run_org_goal(domain_id="it-ops", dry_actions=False, week_label="w-k3")
    steps = {s.get("step"): s for s in (run.get("steps") or []) if isinstance(s, dict)}
    assert "reasoning" in steps
    assert steps["reasoning"]["can_execute"] is False
    assert steps["reasoning"]["skipped"] == "no_entity"
    assert run.get("reasoning", {}).get("skipped") == "no_entity"
    assert run.get("trace_id") == run.get("run_id")
