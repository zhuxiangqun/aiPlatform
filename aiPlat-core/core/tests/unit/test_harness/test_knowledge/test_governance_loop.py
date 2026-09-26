"""Governance 8-step loop map + schema enrichment (step ②) + deepen ⑥⑦."""

from __future__ import annotations

from core.apps.fde.service.governance_deepen import (
    governance_quality_snapshot,
    locate_via_ontology,
)
from core.apps.fde.service.governance_loop import get_governance_loop_map
from core.apps.fde.service.ontology_code_suggestions import (
    enrich_column_meanings,
    suggest_classes_from_table_schema,
)
from core.harness.ontology_engine.graph_index import GraphIndex


def test_governance_loop_eight_steps_honest():
    m = get_governance_loop_map()
    assert m["count"] == 8
    assert m["kpis_claimed_by_material"] is False
    assert "KPI" in m["authority_note"] or "补齐率" in m["authority_note"]
    steps = m["steps"]
    assert [s["step"] for s in steps] == list(range(1, 9))
    assert steps[0]["status"] == "vertical"
    assert steps[1]["status"] == "suggestion"
    assert steps[5]["status"] == "vertical"
    assert steps[5]["api"] and "quality" in steps[5]["api"]
    assert steps[6]["status"] == "vertical"
    assert steps[6]["api"] and "locate" in steps[6]["api"]
    assert steps[7]["href"].endswith("/workspace/agents") or "agents" in steps[7]["href"]


def test_governance_quality_snapshot_has_ocs_and_actions():
    snap = governance_quality_snapshot("data-gov")
    assert snap["step"] == 6
    assert snap["status"] == "vertical"
    assert "ocs" in snap
    assert isinstance(snap.get("actions"), list)
    assert len(snap["actions"]) >= 1
    assert any("mount" in a["action_id"] for a in snap["actions"])
    assert "KPI" in snap["authority_note"] or "套件" in snap["authority_note"]


def test_locate_via_ontology_hits_seeded_graph(tmp_path, monkeypatch):
    monkeypatch.setenv("AIPLAT_HOME", str(tmp_path))
    GraphIndex._loaded_instances.clear()
    g = GraphIndex.load("data-gov")
    g.add_entity("ASSET-积分流水", "积分流水资产", "数据资产")
    g.add_entity("TBL-ghost", "幽灵表_tmp", "物理表")
    out = locate_via_ontology("data-gov", "积分流水", top_k=5)
    assert out["step"] == 7
    assert out["status"] == "ok"
    assert any("积分" in (h.get("entity_name") or "") for h in out.get("hits") or [])
    empty = locate_via_ontology("data-gov", "")
    assert empty["status"] == "need_query"


def test_enrich_column_meanings_heuristic():
    meanings = enrich_column_meanings(
        ["service_name", "severity", "foo_bar"],
        [{"service_name": "SVC-查询", "severity": "critical", "foo_bar": "x"}],
    )
    assert "服务" in meanings["service_name"] or "service" in meanings["service_name"].lower()
    assert "严重" in meanings["severity"] or "critical" in meanings["severity"].lower()
    assert "foo_bar" in meanings


def test_schema_suggest_includes_field_meanings():
    out = suggest_classes_from_table_schema(
        "it-ops",
        table_name="alert_events",
        columns=["id", "service_name", "severity"],
        sample_rows=[{"id": "1", "service_name": "SVC-A", "severity": "critical"}],
        enqueue=False,
    )
    s = out["suggestions"][0]
    assert s.get("field_meanings")
    assert "service_name" in s["field_meanings"]
    assert "AI补齐" in s["description"]
    assert out.get("step2_enrichment") is True
    assert s["enrichment"]["mode"] == "heuristic"
