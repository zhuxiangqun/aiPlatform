"""Ollaya Phase 0: process-wide DomainRouter route_stats + T3 latency."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from core.harness.knowledge.domain_router import (
    DomainRouter,
    _reset_domain_router_for_tests,
    get_domain_router,
)


@pytest.fixture(autouse=True)
def _clean_router_stats():
    _reset_domain_router_for_tests()
    yield
    _reset_domain_router_for_tests()


def test_route_stats_shared_across_instances():
    a = DomainRouter()
    b = DomainRouter()
    with patch.object(a, "list_domains", return_value=["d1", "d2"]):
        with patch.object(a, "_ensure_built"):
            with patch.object(a, "_t1_label_match", return_value="d1"):
                assert a.classify("hello") == "d1"
    snap = b.route_stats()
    assert snap["total"] == 1
    assert snap["t1_hits"] == 1
    assert snap["scope"] == "process"


def test_t3_records_latency(monkeypatch):
    r = DomainRouter()

    def _fake_llm(_query: str) -> str:
        return "d2"

    with patch.object(r, "list_domains", return_value=["d1", "d2"]):
        with patch.object(r, "_ensure_built"):
            with patch.object(r, "_t1_label_match", return_value=None):
                with patch.object(r, "_t2_embed_score", return_value=0.1):
                    with patch.object(r, "_load_registry", return_value={"routing": {"embedding": {}}}):
                        with patch.object(r, "_llm_classify", side_effect=_fake_llm):
                            assert r.classify("obscure query") == "d2"
    snap = r.route_stats()
    assert snap["t3_hits"] == 1
    assert snap["t3_latency_samples"] == 1
    assert snap["t3_latency_ms_p50"] is not None
    assert snap["t3_latency_ms_p95"] is not None


def test_get_domain_router_singleton():
    assert get_domain_router() is get_domain_router()


def test_facade_route_stats():
    from core.api.core_facade import domain_router_route_stats

    a = DomainRouter()
    with patch.object(a, "list_domains", return_value=["d1", "d2"]):
        with patch.object(a, "_ensure_built"):
            with patch.object(a, "_t1_label_match", return_value="d1"):
                a.classify("x")
    snap = domain_router_route_stats()
    assert snap["t1_hits"] >= 1
    assert "honesty" in snap
    assert "≠ accuracy" in snap["honesty"]


def test_t2_boundary_and_reject_side_counters():
    r = DomainRouter()
    cfg = {
        "routing": {
            "embedding": {
                "min_confidence": 0.4,
                "min_margin": 0.08,
                "boundary_score_slack": 0.05,
                "boundary_margin_factor": 2.0,
            }
        }
    }

    # Accepted T2 near boundary (score 0.42 < 0.4+0.05)
    with patch.object(r, "list_domains", return_value=["d1", "d2"]):
        with patch.object(r, "_ensure_built"):
            with patch.object(r, "_t1_label_match", return_value=None):
                with patch.object(r, "_load_registry", return_value=cfg):

                    def _scores(query, did):
                        return {"d1": 0.42, "d2": 0.10}[did]

                    with patch.object(r, "_t2_embed_score", side_effect=_scores):
                        assert r.classify("near") == "d1"
    snap = r.route_stats()
    assert snap["t2_hits"] == 1
    assert snap["t2_boundary_hits"] == 1
    assert snap["t2_reject_hits"] == 0

    # Reject → T3 path increments t2_reject
    with patch.object(r, "list_domains", return_value=["d1", "d2"]):
        with patch.object(r, "_ensure_built"):
            with patch.object(r, "_t1_label_match", return_value=None):
                with patch.object(r, "_load_registry", return_value=cfg):
                    with patch.object(r, "_t2_embed_score", return_value=0.1):
                        with patch.object(r, "_llm_classify", return_value="d2"):
                            assert r.classify("far") == "d2"
    snap = r.route_stats()
    assert snap["t3_hits"] == 1
    assert snap["t2_reject_hits"] == 1
    assert "stats_uptime_s" in snap


def test_diagnostics_route_stats_endpoint():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from core.api.routers.diagnostics import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    resp = client.get("/diagnostics/domain-router/route-stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") is True
    assert body.get("scope") == "process"
    assert "honesty" in body
    assert "t2_boundary_hits" in body
    assert "≠" in body["honesty"]
