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
    assert "accuracy" not in snap.get("honesty", "").lower() or "≠ accuracy" in snap["honesty"]
