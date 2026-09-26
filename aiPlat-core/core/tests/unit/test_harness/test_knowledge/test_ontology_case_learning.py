"""Ontology online learning P0 + gated evolution P1."""

from __future__ import annotations

import pytest

from core.harness.knowledge.ontology_case_learning import (
    OntologyCaseStore,
    maybe_enqueue_evolution_proposal,
    record_case_from_action,
    record_feedback_and_maybe_evolve,
    rollback_case_evolution,
)
from core.harness.ontology_engine.graph_index import GraphIndex


@pytest.fixture()
def aiplat_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("AIPLAT_HOME", str(home))
    monkeypatch.setenv("AIPLAT_ONTOLOGY_CASE_LEARNING", "true")
    monkeypatch.setenv("AIPLAT_ONTOLOGY_EVOLVE_MIN_REWARD", "0.7")
    monkeypatch.setenv("AIPLAT_ONTOLOGY_EVOLVE_MIN_FEEDBACK", "1")
    GraphIndex._loaded_instances.clear()
    return home


def test_record_and_reward_weighted_search(aiplat_home):
    store = OntologyCaseStore("it-ops")
    low = store.record(
        title="weak triage",
        summary="alert noise 实体 NoiseAlert",
        outcome="failure",
        reward=0.1,
        action_id="triage_alert",
    )
    high = store.record(
        title="good triage",
        summary="alert resolved 实体 ServiceEndpoint",
        outcome="success",
        reward=0.95,
        action_id="triage_alert",
        tags=["triage"],
    )
    assert low["status"] == "ok" and high["status"] == "ok"

    hits = store.search("triage alert ServiceEndpoint", top_k=5)
    assert hits
    assert hits[0]["case_id"] == high["case_id"]
    assert hits[0]["score"] >= hits[-1]["score"]


def test_action_hook_records_case(aiplat_home):
    out = record_case_from_action(
        domain_id="it-ops",
        action_id="customer_action:it-ops:triage_alert",
        entity_id="A1",
        status="executed",
        result={"summary": "ok"},
        actor="tester",
    )
    assert out.get("status") == "ok"
    assert out.get("case_id")
    hits = OntologyCaseStore("it-ops").search("triage_alert", top_k=3)
    assert any(h["case_id"] == out["case_id"] for h in hits)


@pytest.mark.asyncio
async def test_feedback_enqueues_draft_no_auto_apply(aiplat_home):
    # domain yaml so VersionedOntologyStore can load
    onto = aiplat_home / "ontologies"
    onto.mkdir(parents=True)
    (onto / "demo-learn.yaml").write_text(
        "domain_id: demo-learn\nclasses:\n  - name: Base\n    label: Base\n",
        encoding="utf-8",
    )

    store = OntologyCaseStore("demo-learn")
    rec = store.record(
        title="gap",
        summary="缺失实体 NewObservabilitySignal for SLO breach",
        outcome="success",
        reward=0.6,
        action_id="observe_slo",
        metadata={"gap_hint": "实体 NewObservabilitySignal"},
    )
    case_id = rec["case_id"]

    result = await record_feedback_and_maybe_evolve(
        case_id, rating=0.95, note="useful", actor="reviewer", auto_enqueue=True
    )
    assert result["feedback"]["status"] == "ok"
    assert result["feedback"]["reward_ema"] >= 0.7
    evolve = result["evolve"]
    assert evolve.get("auto_apply") is False
    assert evolve.get("proposal_id")
    assert evolve.get("status") in ("draft", "local_draft")


@pytest.mark.asyncio
async def test_evolve_force_never_auto_apply(aiplat_home):
    onto = aiplat_home / "ontologies"
    onto.mkdir(parents=True)
    (onto / "demo-learn2.yaml").write_text(
        "domain_id: demo-learn2\nclasses: []\n",
        encoding="utf-8",
    )
    store = OntologyCaseStore("demo-learn2")
    rec = store.record(
        title="low",
        summary="class FooBar missing",
        outcome="partial",
        reward=0.2,
    )
    out = await maybe_enqueue_evolution_proposal(rec["case_id"], force=True)
    assert out["auto_apply"] is False
    assert out.get("proposal_id")
    # second call without force → already_enqueued
    again = await maybe_enqueue_evolution_proposal(rec["case_id"], force=False)
    assert again["status"] == "already_enqueued"
    assert again["auto_apply"] is False


def test_facade_wrappers_delegate(aiplat_home):
    """CoreFacade wrappers are thin; exercise store path used by record/search."""
    from core.harness.knowledge import ontology_case_learning as ocl

    assert callable(ocl.OntologyCaseStore)
    store = ocl.OntologyCaseStore("facade-d")
    store.record(
        title="t1",
        summary="ServiceEndpoint health",
        outcome="success",
        reward=0.9,
    )
    hits = store.search("ServiceEndpoint", top_k=3)
    assert len(hits) >= 1
    # source-level symbols expected on CoreFacade (avoid importing whole facade on py3.9)
    facade_path = (
        __import__("pathlib").Path(__file__).resolve().parents[4]
        / "api"
        / "core_facade.py"
    )
    text = facade_path.read_text(encoding="utf-8")
    for name in (
        "def record_ontology_case",
        "def search_ontology_cases",
        "def ontology_case_learning_status",
        "async def feedback_ontology_case",
        "async def evolve_ontology_from_case",
        "async def rollback_ontology_case_evolution",
    ):
        assert name in text, name


def test_ucb_search_explores_low_feedback(aiplat_home, monkeypatch):
    monkeypatch.setenv("AIPLAT_ONTOLOGY_CASE_UCB", "true")
    store = OntologyCaseStore("ucb-d")
    store.record(
        title="mature",
        summary="ServiceEndpoint triage mature",
        outcome="success",
        reward=0.9,
        case_id="c_mature",
    )
    store.record_feedback("c_mature", rating=0.9, note="many", actor="a")
    store.record_feedback("c_mature", rating=0.9, note="many2", actor="a")
    store.record(
        title="fresh",
        summary="ServiceEndpoint triage fresh unexplored",
        outcome="success",
        reward=0.55,
        case_id="c_fresh",
    )
    hits = store.search("ServiceEndpoint triage", top_k=5)
    assert hits
    assert any("ucb_bonus" in h for h in hits)
    # under-feedback case should not be buried solely by lower reward
    ids = [h["case_id"] for h in hits]
    assert "c_fresh" in ids


@pytest.mark.asyncio
async def test_edge_auto_apply_and_rollback(aiplat_home, monkeypatch):
    monkeypatch.setenv("AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY", "true")
    onto = aiplat_home / "ontologies"
    onto.mkdir(parents=True)
    (onto / "edge-auto.yaml").write_text(
        "domain_id: edge-auto\nclasses:\n  - name: Base\n    label: Base\n    tier: logic\n",
        encoding="utf-8",
    )
    store = OntologyCaseStore("edge-auto")
    rec = store.record(
        title="gap",
        summary="缺失实体 AutoEdgeSignal for SLO",
        outcome="success",
        reward=0.9,
        metadata={"gap_hint": "实体 AutoEdgeSignal"},
    )
    out = await maybe_enqueue_evolution_proposal(rec["case_id"], force=True)
    assert out.get("edge_auto_apply_enabled") is True
    assert out.get("auto_apply") is True
    assert out.get("status") == "edge_auto_applied"
    assert out.get("proposal_id")

    live = (onto / "edge-auto.yaml").read_text(encoding="utf-8")
    assert "AutoEdgeSignal" in live or out.get("suggested_class", "") in live

    rb = await rollback_case_evolution(rec["case_id"])
    assert rb.get("ok") is True
    live2 = (onto / "edge-auto.yaml").read_text(encoding="utf-8")
    assert out.get("suggested_class", "AutoEdgeSignal") not in live2 or "AutoEdgeSignal" not in live2


@pytest.mark.asyncio
async def test_edge_auto_apply_default_off(aiplat_home, monkeypatch):
    monkeypatch.delenv("AIPLAT_ONTOLOGY_EDGE_AUTO_APPLY", raising=False)
    onto = aiplat_home / "ontologies"
    onto.mkdir(parents=True)
    (onto / "edge-off.yaml").write_text(
        "domain_id: edge-off\nclasses: []\n",
        encoding="utf-8",
    )
    store = OntologyCaseStore("edge-off")
    rec = store.record(
        title="gap",
        summary="class FooBarMissing",
        outcome="success",
        reward=0.95,
    )
    out = await maybe_enqueue_evolution_proposal(rec["case_id"], force=True)
    assert out.get("auto_apply") is False
    assert out.get("status") in ("draft", "local_draft")


def test_format_cases_for_context_and_bus_overlay(aiplat_home):
    from core.harness.knowledge.context_bus import _inject_historical_cases
    from core.harness.knowledge.ontology_case_learning import format_cases_for_context

    store = OntologyCaseStore("it-ops")
    store.record(
        title="good triage",
        summary="ServiceEndpoint SLO breach rooted at Redis",
        outcome="success",
        reward=0.92,
        action_id="triage_alert",
    )
    text = format_cases_for_context("it-ops", "ServiceEndpoint triage", top_k=3)
    assert "本体在线学习案例" in text
    assert "ServiceEndpoint" in text

    parts: list = []
    _inject_historical_cases(parts, "it-ops", {"pain_points": "ServiceEndpoint triage"})
    joined = "\n".join(parts)
    assert "本体在线学习案例" in joined
    assert "说明书" in joined or "建议层" in joined


def test_serve_count_and_learning_meta(aiplat_home):
    from core.harness.knowledge.ontology_case_learning import ontology_case_learning_meta

    store = OntologyCaseStore("serve-d")
    store.record(
        title="s1",
        summary="ServiceEndpoint health",
        outcome="success",
        reward=0.8,
        case_id="serve_c1",
    )
    hits1 = store.search("ServiceEndpoint", top_k=3)
    assert hits1 and hits1[0]["serve_count"] >= 1
    hits2 = store.search("ServiceEndpoint", top_k=3)
    assert hits2[0]["serve_count"] >= hits1[0]["serve_count"]

    meta = ontology_case_learning_meta("serve-d")
    assert meta["enabled"] is True
    assert meta["case_count"] == 1
    assert meta["total_serves"] >= 2
    assert "edge_auto_apply_enabled" in meta
    assert meta["edge_auto_apply_enabled"] is False


def test_context_demotes_repeated_low_yield_without_delete(aiplat_home):
    from core.harness.knowledge.ontology_case_learning import (
        format_cases_for_context,
        select_cases_for_context,
    )

    store = OntologyCaseStore("ctx-d")
    store.record(
        title="noise",
        summary="SharedToken failed again",
        outcome="failure",
        reward=0.1,
        case_id="bad1",
    )
    store.record(
        title="keep",
        summary="SharedToken rooted cleanly",
        outcome="success",
        reward=0.9,
        case_id="good1",
    )
    cases = store._load()
    cases["bad1"].serve_count = 6
    cases["bad1"].reward_ema = 0.1
    store._save(cases)

    picked = select_cases_for_context(
        [
            {"case_id": "bad1", "serve_count": 6, "reward_ema": 0.1, "outcome": "failure"},
            {"case_id": "fresh", "serve_count": 0, "reward_ema": 0.2, "outcome": "failure"},
        ],
        top_k=3,
    )
    assert picked["deleted"] is False
    assert picked["demoted"] == 1
    assert [row["case_id"] for row in picked["kept"]] == ["fresh"]

    text = format_cases_for_context("ctx-d", "SharedToken", top_k=3)
    assert "good1" in text
    assert "bad1" not in text
    assert "未删除" in text
    assert "bad1" in store._load()


def test_archive_cold_moves_without_delete(aiplat_home):
    from core.harness.knowledge.ontology_case_learning import (
        OntologyCaseStore,
        archive_cold_cases,
        format_cases_for_context,
        list_cold_cases,
    )

    store = OntologyCaseStore("cold-d")
    store.record(
        title="stale",
        summary="SharedToken failed again",
        outcome="failure",
        reward=0.1,
        case_id="stale1",
    )
    store.record(
        title="keep",
        summary="SharedToken rooted cleanly",
        outcome="success",
        reward=0.9,
        case_id="keep1",
    )
    cases = store._load()
    cases["stale1"].serve_count = 10
    cases["stale1"].reward_ema = 0.1
    store._save(cases)

    out = archive_cold_cases("cold-d")
    assert out["ok"] is True
    assert out["deleted"] is False
    assert out["wrote_live_yaml"] is False
    assert out["tbox_changed"] is False
    assert out["moved_count"] == 1
    assert "stale1" not in store._load()
    assert "keep1" in store._load()
    listed = list_cold_cases("cold-d")
    assert listed["count"] == 1
    assert listed["items"][0]["case_id"] == "stale1"
    text = format_cases_for_context("cold-d", "SharedToken", top_k=3)
    assert "stale1" not in text
    assert "keep1" in text
