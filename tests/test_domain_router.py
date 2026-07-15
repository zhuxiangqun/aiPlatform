"""Unit tests for DomainRouter 3-tier classification (Phase A fix)."""
import pytest
from core.harness.knowledge.domain_router import DomainRouter


class TestDomainRouterClassification:
    """Verify T1 (label match) → T2 (embedding) → T3 (LLM) fallback chain."""

    @pytest.fixture
    def router(self):
        return DomainRouter()

    def test_t1_label_match_ship_design(self, router):
        """'船东意见' label should match ship-design domain via T1 (label in query)."""
        result = router.classify("船东意见第2024-0037号的处理流程")
        assert result == "ship-design", f"Expected ship-design, got {result}"

    def test_t2_embedding_routing_supply_chain(self, router):
        """T1 should NOT match '物流路线优化', T2 should route via embedding."""
        result = router.classify("物流路线优化")
        assert result == "supply-chain", f"Expected supply-chain, got {result}"

    def test_t2_embedding_routing_procurement(self, router):
        """T1 should NOT match '供应商风险评估', T2 should route to procurement."""
        result = router.classify("供应商风险评估")
        assert result == "procurement-mvo", f"Expected procurement-mvo, got {result}"

    def test_fallback_returns_valid_domain(self, router):
        """Even for unknown queries, the router should return a valid domain string."""
        result = router.classify("xyzzy magic words 魔法")
        assert isinstance(result, str) and len(result) > 0

    def test_stats_tracked_correctly(self, router):
        """After classification, stats should be non-zero and consistent."""
        router.classify("船舶引擎")
        router.classify("物流路线")
        router.classify("供应商评估")
        router.classify("what is random stuff about clouds")
        stats = router.route_stats()
        assert stats["total"] >= 4
        assert isinstance(stats["t1_label_pct"], (int, float))
        assert isinstance(stats["t2_embedding_pct"], (int, float))
        assert isinstance(stats["t3_llm_pct"], (int, float))
