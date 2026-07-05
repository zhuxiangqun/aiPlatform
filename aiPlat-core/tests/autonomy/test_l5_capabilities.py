"""
L5 capability depth tests — verifies that Phase 25-32 modules do real work,
not just exist as classes.

Each test imports the module, injects data, exercises the core logic,
and verifies behavioral output — not just grep -c existence.
"""

import sys
import os
import pytest
import asyncio
import tempfile
import uuid


# ══════════════════════════════════════════════════════════
# F Axis: StrategySearchEngine (UCB1 convergence)
# ══════════════════════════════════════════════════════════

class TestUCB1Convergence:
    """Verify UCB1 actually converges to optimal strategy under clean data."""

    def test_converges_on_clean_data(self):
        """With 80% success for compress_retry vs 20% for others, UCB1 must converge."""
        from core.harness.optimization.strategy_tracker import get_strategy_tracker
        from core.harness.optimization.search_engine import StrategySearchEngine

        t = get_strategy_tracker()
        # Seed: each strategy gets 1 initial attempt
        for s in t.ALL_STRATEGIES:
            t._get_or_create('conv_test', s).attempts = 1
            t._get_or_create('conv_test', s).successes = 1 if s == 'compress_retry' else 0

        engine = StrategySearchEngine(t)

        # Run 10 rounds: compress_retry wins 80%, others win 20%
        import random
        rng = random.Random(42)  # deterministic seed
        for _ in range(10):
            best = engine.select_best('conv_test')
            assert best is not None, f"UCB1 must select a strategy, got None at round {_}"
            if best == 'compress_retry':
                t.record('conv_test', best, success=rng.random() < 0.8)
            else:
                t.record('conv_test', best, success=rng.random() < 0.2)

        # After 10 rounds with biased data, best should be compress_retry
        final_best = engine.select_best('conv_test')
        assert final_best == 'compress_retry', (
            f"UCB1 should converge to 'compress_retry', got '{final_best}'"
        )

    def test_cold_start_returns_none(self):
        """Untested error types should return None (defer to hardcoded fallback)."""
        from core.harness.optimization.strategy_tracker import get_strategy_tracker
        from core.harness.optimization.search_engine import StrategySearchEngine

        t = get_strategy_tracker()
        engine = StrategySearchEngine(t)

        result = engine.select_best('never_seen_before')
        assert result is None, "Cold-start should return None, not guess a strategy"

    def test_converged_flag_persists(self):
        """After convergence, is_converged must return True."""
        from core.harness.optimization.strategy_tracker import get_strategy_tracker
        from core.harness.optimization.search_engine import StrategySearchEngine

        t = get_strategy_tracker()
        engine = StrategySearchEngine(t)

        # Manually mark as converged
        engine._converged['flag_test'] = 'backoff_retry'
        converged, best = engine.is_converged('flag_test')
        assert converged, "is_converged must return True after manual convergence"
        assert best == 'backoff_retry', f"Expected 'backoff_retry', got '{best}'"


# ══════════════════════════════════════════════════════════
# A Axis: GoalExecutor (autonomous closed-loop execution)
# ══════════════════════════════════════════════════════════

class TestGoalExecutor:
    """Verify GoalExecutor can detect and execute goals."""

    def test_executor_stats_defaults(self):
        """GoalExecutor should report stats even when idle."""
        from core.harness.optimization.goal_executor import GoalExecutor

        ex = GoalExecutor(enabled=False)
        stats = ex.stats()
        assert stats['enabled'] is False
        assert stats['running'] is False
        assert stats['total_auto_executed'] == 0
        assert 'recent_executions' in stats

    def test_executor_has_bootstrap_debounce(self):
        """GoalExecutor must debounce tool bootstrap calls."""
        from core.harness.optimization.goal_executor import GoalExecutor

        ex = GoalExecutor()
        assert not ex._has_bootstrapped('rate_limit'), "Fresh executor should have empty bootstrap set"
        ex._bootstrapped.add('rate_limit')
        assert ex._has_bootstrapped('rate_limit'), "Debounce should remember bootstrapped types"


# ══════════════════════════════════════════════════════════
# C Axis: ToolBootstrapEngine (tool creation pipeline)
# ══════════════════════════════════════════════════════════

class TestToolBootstrap:
    """Verify ToolBootstrap can generate and register skills."""

    def test_fallback_skill_is_valid(self):
        """Fallback skill generation must produce valid YAML frontmatter."""
        from core.harness.optimization.tool_bootstrap import ToolBootstrapEngine

        engine = ToolBootstrapEngine()
        skill = engine._generate_fallback_skill('test_tool', 'A test description')
        assert len(skill) >= 200, f"Fallback skill too short: {len(skill)} chars"
        assert '---' in skill, "Missing YAML frontmatter delimiter"
        assert 'name: test_tool' in skill, "Missing name field"
        assert 'version:' in skill, "Missing version field"
        assert 'effects:' in skill, "Missing effects declaration"

    @pytest.mark.asyncio
    async def test_bootstrap_registers_skill(self):
        """Full bootstrap pipeline must generate and register a read-only skill."""
        from core.harness.optimization.tool_bootstrap import ToolBootstrapEngine

        engine = ToolBootstrapEngine()
        safe_name = f"test_bootstrap_{uuid.uuid4().hex[:8]}"
        result = await engine.bootstrap(
            safe_name, 'Automated test tool for L5 verification', auto_approve=True
        )
        assert result.status == 'registered', (
            f"Expected 'registered', got '{result.status}': {result.error}"
        )
        assert result.auto_registered, "Read-only skill should auto-register"
        assert result.effects_type == 'read', f"Expected 'read', got '{result.effects_type}'"

        # Verify file exists
        skill_path = os.path.expanduser(
            f"~/.aiplat/skills/bootstrap/{safe_name}/SKILL.md"
        )
        assert os.path.exists(skill_path), f"SKILL.md not found at {skill_path}"
        assert os.path.getsize(skill_path) >= 100, f"SKILL.md too small"

        # Cleanup
        import shutil
        shutil.rmtree(os.path.dirname(skill_path), ignore_errors=True)

    def test_effects_extraction(self):
        """Must correctly parse effects type from SKILL.md frontmatter."""
        from core.harness.optimization.tool_bootstrap import ToolBootstrapEngine

        engine = ToolBootstrapEngine()
        skill = engine._generate_fallback_skill('test', 'desc')
        effects = engine._extract_effects_type(skill)
        assert effects == 'read', f"Expected 'read', got '{effects}'"


# ══════════════════════════════════════════════════════════
# E Axis: DynamicOrchestrator (capability gap detection)
# ══════════════════════════════════════════════════════════

class TestDynamicOrchestrator:
    """Verify orchestrator can detect capability gaps from agent output."""

    @pytest.mark.asyncio
    async def test_senses_security_gap(self):
        """Must detect '需要安全检查' as a security capability gap."""
        from core.harness.coordination.dynamic_orchestrator import DynamicOrchestrator

        orch = DynamicOrchestrator()
        result = await orch.sense_gap('我们需要安全检查这段代码', 'test_agent')
        assert result is not None, "Should detect security capability gap"
        assert result['capability'] == 'security', (
            f"Expected 'security', got '{result.get('capability')}'"
        )
        assert 'security_reviewer' in result['candidates'], (
            f"Expected security_reviewer in candidates: {result['candidates']}"
        )

    @pytest.mark.asyncio
    async def test_senses_review_gap_english(self):
        """Must detect 'needs review' in English text."""
        from core.harness.coordination.dynamic_orchestrator import DynamicOrchestrator

        orch = DynamicOrchestrator()
        result = await orch.sense_gap('this module needs review before deploy', 'test')
        assert result is not None, "Should detect review gap in English"
        assert result['capability'] == 'review'

    @pytest.mark.asyncio
    async def test_no_false_positive(self):
        """Should NOT detect gaps in normal text."""
        from core.harness.coordination.dynamic_orchestrator import DynamicOrchestrator

        orch = DynamicOrchestrator()
        result = await orch.sense_gap('hello world', 'test')
        assert result is None, f"Should not detect gap in normal text, got {result}"

    def test_capability_map_complete(self):
        """All 5 capability types should have candidate agents."""
        from core.harness.coordination.dynamic_orchestrator import DynamicOrchestrator

        orch = DynamicOrchestrator()
        caps = orch.get_capabilities()
        for cap_type in ['security', 'review', 'refactor', 'analysis', 'test']:
            assert cap_type in caps, f"Missing capability: {cap_type}"
            assert len(caps[cap_type]) >= 1, f"No agents for {cap_type}"


# ══════════════════════════════════════════════════════════
# D Axis: SharedKnowledgePool (cross-session knowledge)
# ══════════════════════════════════════════════════════════

class TestSharedKnowledgePool:
    """Verify shared pool enables cross-session knowledge transfer."""

    def test_publish_and_query(self):
        """Publishing a fact must be retrievable by another session."""
        from core.harness.memory.shared_pool import SharedKnowledgePool, POOL_FILE, POOL_DB

        pool = SharedKnowledgePool()
        pool._facts.clear()
        if os.path.exists(POOL_FILE):
            os.remove(POOL_FILE)
        if os.path.exists(POOL_DB):
            os.remove(POOL_DB)
            pool._db_conn = None
            pool._loaded = False

        # Use unique topic to avoid contamination
        uid = uuid.uuid4().hex[:8]
        topic = f"l5_test_{uid}"

        fid = pool.publish(
            topic=topic,
            content='rotate_credential succeeds 85% for rate_limit errors',
            session_id='session_a',
            source='strategy',
            confidence=0.85,
        )
        assert fid is not None, "Publish must return a fact_id"

        results = pool.query(topic, exclude_session_id='session_b')
        assert len(results) >= 1, f"Query should return ≥1 result, got {len(results)}"
        fact = results[0]
        assert fact.topic == topic

    def test_exclude_session_id(self):
        """Must exclude own session from query results."""
        from core.harness.memory.shared_pool import SharedKnowledgePool, POOL_FILE

        pool = SharedKnowledgePool()
        pool._facts.clear()
        # Force empty pool file to avoid cross-test contamination
        if os.path.exists(POOL_FILE):
            os.remove(POOL_FILE)

        pool.publish('l5_test_topic', 'data from s1', session_id='s1')
        pool.publish('l5_test_topic', 'data from s2', session_id='s2')
        pool.publish('l5_test_topic', 'data from s3', session_id='s3')

        results_s1 = pool.query('l5_test_topic', exclude_session_id='s1')
        assert len(results_s1) == 2, f"Expected 2 results excluding s1, got {len(results_s1)}"
        for r in results_s1:
            assert r.session_id != 's1', f"Should not see s1: {r.session_id}"

    def test_stats(self):
        """Stats must report topic distribution."""
        from core.harness.memory.shared_pool import SharedKnowledgePool, POOL_FILE, POOL_DB

        pool = SharedKnowledgePool()
        pool._facts.clear()
        if os.path.exists(POOL_FILE):
            os.remove(POOL_FILE)
        # Phase 34: also clear SQLite
        if os.path.exists(POOL_DB):
            os.remove(POOL_DB)
            pool._db_conn = None  # force re-init
            pool._loaded = False

        pool.publish('l5ta', 'data a')
        pool.publish('l5tb', 'data b')
        pool.publish('l5ta', 'more a')

        stats = pool.stats()
        assert stats['total_facts'] == 3, f"Expected 3 facts, got {stats['total_facts']}"
        assert 'l5ta' in stats['top_topics']


# ══════════════════════════════════════════════════════════
# Integration: StrategyTracker → SearchEngine → Pipeline
# ══════════════════════════════════════════════════════════

class TestHealingIntegration:
    """Verify that tracker + search engine + pipeline work end-to-end."""

    def test_tracker_feeds_search_engine(self):
        """StrategyTracker data must be usable by SearchEngine."""
        from core.harness.optimization.strategy_tracker import get_strategy_tracker
        from core.harness.optimization.search_engine import StrategySearchEngine

        t = get_strategy_tracker()

        # Initialize all strategies with baseline attempts (cold-start requirement)
        for s in t.ALL_STRATEGIES:
            t._get_or_create('test_error2', s).attempts = 1
            t._get_or_create('test_error2', s).successes = 1 if s == 'rotate_credential' else 0

        # Add biased data: rotate_credential wins 3/3, backoff loses 0/3
        for _ in range(3):
            t.record('test_error2', 'rotate_credential', success=True)
            t.record('test_error2', 'backoff_retry', success=False)
        for _ in range(2):
            t.record('test_error2', 'compress_retry', success=False)
            t.record('test_error2', 'skip_stage', success=True)

        engine = StrategySearchEngine(t)
        best = engine.select_best('test_error2')
        # rotate_credential: 4 attempts, 4 success = 100%
        # compress_retry: 3 attempts, 1 success = 33%
        # skip_stage: 3 attempts, 1 success = 33%
        # backoff_retry: 4 attempts, 0 success = 0%
        # UCB1 should select rotate_credential (highest Q + exploration term)
        assert best == 'rotate_credential', (
            f"Expected 'rotate_credential' (100% success), got '{best}'"
        )

    def test_search_engine_reset(self):
        """Resetting convergence must allow re-exploration."""
        from core.harness.optimization.strategy_tracker import get_strategy_tracker
        from core.harness.optimization.search_engine import StrategySearchEngine

        t = get_strategy_tracker()
        engine = StrategySearchEngine(t)
        engine._converged['test'] = 'rotate_credential'

        assert engine.get_converged_count() == 1
        engine.reset('test')
        assert engine.get_converged_count() == 0, "Reset should clear convergence"


# ══════════════════════════════════════════════════════════
# Cleanup helper
# ══════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Clean shared state between tests."""
    yield
    try:
        import core.harness.memory.shared_pool as sp
        sp._pool = None
    except Exception:
        pass
    try:
        import core.harness.optimization.strategy_tracker as st
        st._tracker = None
    except Exception:
        pass
