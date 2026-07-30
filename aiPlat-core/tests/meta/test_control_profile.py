"""Integration tests for ControlProfile pipeline.

Covers:
  - ProfileRegistry loading
  - resolve() with task_type + priority
  - interpolate() fusion strategies
  - OrchestrationSelector table-driven selection
  - CacheAwareRouter TTL + freeze logic
  - primary_failure_domain set/get/clear
  - get_active_profile() fallback chain
"""

import pytest
import numpy as np

from core.harness.meta.control_profile import (
    ControlProfile, ControlProfileInterpolator,
    FLOAT_FIELDS, INT_FIELDS, ENUM_FIELDS, BOOL_FIELDS, LIST_FIELDS,
    _fuse_enum, _fuse_list,
)
from core.harness.meta.profile_registry import (
    ProfileRegistry, get_active_profile,
    set_failure_domain, get_last_failure_domain, clear_failure_domain,
)
from core.harness.meta.orchestration_selector import OrchestrationSelector
from core.harness.meta.cache_aware_router import CacheAwareRouter


class TestControlProfile:
    """Test ControlProfile dataclass + interpolation."""

    def test_default_values(self):
        p = ControlProfile()
        assert p.model_tier == "auto"
        assert p.temperature == 0.3
        assert p.compression_strictness == 1.0
        assert p.gate_strictness == 1.0
        assert p.episodic_injection is True
        assert p.context_layers == 3

    def test_to_from_dict(self):
        p = ControlProfile(temperature=0.7, model_tier="T4")
        d = p.to_dict()
        p2 = ControlProfile.from_dict(d)
        assert p2.temperature == 0.7
        assert p2.model_tier == "T4"
        assert p2.compression_strictness == 1.0  # default

    def test_interpolate_floats(self):
        p1 = ControlProfile(temperature=0.7, gate_strictness=0.5)
        p2 = ControlProfile(temperature=0.1, gate_strictness=1.5)
        blended = ControlProfile.interpolate([p1, p2], [0.5, 0.5])
        assert 0.35 < blended.temperature < 0.45
        assert 0.95 < blended.gate_strictness < 1.05

    def test_interpolate_int(self):
        p1 = ControlProfile(context_layers=3)
        p2 = ControlProfile(context_layers=9)
        blended = ControlProfile.interpolate([p1, p2], [0.5, 0.5])
        assert blended.context_layers == 6

    def test_interpolate_enum_excludes_auto(self):
        p1 = ControlProfile(model_tier="T3", orchestration_mode="chain")
        p2 = ControlProfile(model_tier="auto", orchestration_mode="auto")
        p3 = ControlProfile()
        blended = ControlProfile.interpolate([p1, p2, p3], [0.6, 0.2, 0.2])
        assert blended.model_tier == "T3"  # auto excluded

    def test_interpolate_bool(self):
        p1 = ControlProfile(episodic_injection=True)
        p2 = ControlProfile(episodic_injection=False)
        blended = ControlProfile.interpolate([p1, p2], [0.7, 0.3])
        assert blended.episodic_injection is True

    def test_interpolate_list(self):
        p1 = ControlProfile(tool_whitelist=["a", "b"])
        p2 = ControlProfile(tool_whitelist=["b", "c"])
        blended = ControlProfile.interpolate([p1, p2], [0.6, 0.4])
        # b has weight 1.0, a has 0.6, c has 0.4
        assert blended.tool_whitelist == ["b", "a", "c"]

    def test_interpolate_list_with_none(self):
        p1 = ControlProfile(tool_whitelist=["x"])
        p2 = ControlProfile(tool_whitelist=None)  # all open
        blended = ControlProfile.interpolate([p1, p2], [0.5, 0.5])
        assert blended.tool_whitelist == ["x"]

    def test_cache_key_stable(self):
        p1 = ControlProfile(context_layers=3, context_max_sources=5, tool_rank_by="static")
        p2 = ControlProfile(context_layers=3, context_max_sources=5, tool_rank_by="static")
        assert p1.to_cache_key() == p2.to_cache_key()
        assert p1.cache_key_hash() == p2.cache_key_hash()
        assert p1.to_cache_key() == "l3|s5|tr0"

    def test_cache_key_changes(self):
        p1 = ControlProfile(context_layers=3)
        p2 = ControlProfile(context_layers=10)
        assert p1.cache_key_hash() != p2.cache_key_hash()

    def test_field_classification(self):
        assert "temperature" in FLOAT_FIELDS
        assert "context_layers" in INT_FIELDS
        assert "model_tier" in ENUM_FIELDS
        assert "episodic_injection" in BOOL_FIELDS
        assert "tool_whitelist" in LIST_FIELDS


class TestFuseHelpers:
    """Test the fusion helper functions directly."""

    def test_fuse_enum_argmax(self):
        result = _fuse_enum(["chain", "tree", "chain"], np.array([0.3, 0.2, 0.5]))
        assert result == "chain"

    def test_fuse_enum_excludes_auto(self):
        result = _fuse_enum(["auto", "T3", "T4"], np.array([0.8, 0.1, 0.1]))
        # "auto" (0.8) excluded, remaining ["T3"(0.1), "T4"(0.1)]
        # argmax of equal weights picks first → T3
        assert result == "T3"

    def test_fuse_enum_excludes_auto_strong(self):
        result = _fuse_enum(["auto", "T3", "T4"], np.array([0.8, 0.05, 0.15]))
        assert result == "T4"  # T4 has higher weight after auto excluded

    def test_fuse_list_merge(self):
        result = _fuse_list([["a", "b"], ["b", "c"]], np.array([0.6, 0.4]))
        assert result == ["b", "a", "c"]

    def test_fuse_list_all_none(self):
        result = _fuse_list([None, None], np.array([0.5, 0.5]))
        assert result is None


class TestProfileRegistry:
    """Test ProfileRegistry singleton."""

    def setup_method(self):
        ProfileRegistry.reset()

    def test_singleton(self):
        r1 = ProfileRegistry.instance()
        r2 = ProfileRegistry.instance()
        assert r1 is r2

    def test_load_presets(self):
        r = ProfileRegistry.instance()
        names = r.list_presets()
        assert "default" in names
        assert "safety_critical" in names
        assert "creative_exploration" in names

    def test_get_preset_values(self):
        r = ProfileRegistry.instance()
        safety = r.get_preset("safety_critical")
        assert safety is not None
        assert safety.gate_strictness == 1.5
        assert safety.orchestration_mode == "reflexion"
        assert safety.temperature == 0.1

    def test_resolve_by_task_type(self):
        r = ProfileRegistry.instance()
        p = r.resolve(task_type="code_generation")
        assert p.model_tier == "T3"

    def test_resolve_by_task_hints(self):
        r = ProfileRegistry.instance()
        p = r.resolve(task_type="security_audit")
        assert p.model_tier == "T5"
        assert p.gate_strictness == 1.5

    def test_resolve_unknown_task(self):
        r = ProfileRegistry.instance()
        p = r.resolve(task_type="nonexistent_task")
        assert p == r.get_default()

    def test_resolve_with_critical_priority(self):
        r = ProfileRegistry.instance()
        p = r.resolve(task_type="code_generation", priority="critical")
        # code_generation gate=1.0 + 30% safety_critical gate=1.5 → ~1.15
        assert 1.1 < p.gate_strictness < 1.2

    def test_resolve_with_elevated_priority(self):
        r = ProfileRegistry.instance()
        p = r.resolve(task_type="code_generation", priority="elevated")
        # code_generation gate=1.0 + 10% safety_critical gate=1.5 → ~1.05
        assert 1.02 < p.gate_strictness < 1.08

    def test_resolve_by_explicit_name(self):
        r = ProfileRegistry.instance()
        p = r.resolve(profile_name="quick_fact_lookup")
        assert p.model_tier == "T1"
        assert p.compression_strictness == 1.5

    def test_resolve_with_embedding_unknown_task(self):
        r = ProfileRegistry.instance()
        fake_vec = np.random.randn(768).astype(np.float32)
        p = r.resolve_with_embedding(fake_vec, task_type="unknown_xyz")
        # 应降级到语义插值（结果不一定是 default）
        assert isinstance(p, ControlProfile)

    def test_resolve_with_embedding_known_task(self):
        r = ProfileRegistry.instance()
        fake_vec = np.random.randn(768).astype(np.float32)
        p = r.resolve_with_embedding(fake_vec, task_type="code_generation")
        # 已知 task_type 应精确匹配
        assert p.model_tier == "T3"

    def test_register_preset(self):
        r = ProfileRegistry.instance()
        custom = ControlProfile(temperature=0.99, model_tier="T5")
        r.register_preset("my_custom", custom)
        p = r.get_preset("my_custom")
        assert p.temperature == 0.99


class TestOrchestrationSelector:
    """Test P5: OrchestrationSelector."""

    def test_single_step(self):
        os = OrchestrationSelector()
        assert os.select(expected_tool_steps=1, has_branching=False) == "single"

    def test_two_steps_no_branch(self):
        os = OrchestrationSelector()
        assert os.select(expected_tool_steps=2, has_branching=False) == "chain"

    def test_two_steps_with_branch(self):
        os = OrchestrationSelector()
        assert os.select(expected_tool_steps=2, has_branching=True) == "tree"

    def test_complex(self):
        os = OrchestrationSelector()
        assert os.select(expected_tool_steps=5) == "reflexion"

    def test_explicit_mode(self):
        os = OrchestrationSelector()
        assert os.select(profile_mode="tree") == "tree"
        assert os.select(profile_mode="chain") == "chain"

    def test_pipeline_single(self):
        os = OrchestrationSelector()
        assert os.select_for_pipeline(stage_count=1) == "single"

    def test_pipeline_multi(self):
        os = OrchestrationSelector()
        assert os.select_for_pipeline(stage_count=3, has_parallel=True) == "tree"


class TestCacheAwareRouter:
    """Test P6: CacheAwareRouter."""

    def test_first_call_allows_all(self):
        car = CacheAwareRouter()
        p = ControlProfile()
        action = car.evaluate(p)
        assert action["freeze"] == []
        assert "D1" in action["allow"]

    def test_same_profile_allows_all(self):
        car = CacheAwareRouter()
        p = ControlProfile(context_layers=3, context_max_sources=5, tool_rank_by="static")
        car.evaluate(p)
        car.update(p)
        action = car.evaluate(p)
        assert action["freeze"] == []

    def test_different_profile_freezes_d1_d2(self):
        car = CacheAwareRouter()
        p1 = ControlProfile(context_layers=3, tool_rank_by="static")
        car.evaluate(p1)
        car.update(p1)

        p2 = ControlProfile(context_layers=10, tool_rank_by="relevance")
        action = car.evaluate(p2)
        assert "D1" in action["freeze"]
        assert "D2" in action["freeze"]

    def test_ttl_reset_allows_all(self):
        car = CacheAwareRouter(ttl_seconds=300)
        p1 = ControlProfile(context_layers=3)
        car.evaluate(p1)
        car.update(p1)
        p2 = ControlProfile(context_layers=10)
        car.evaluate(p2)  # this should freeze, but after reset...

        car.reset()
        action = car.evaluate(p2)
        assert action["freeze"] == []  # after reset, first call always allows

    def test_update_makes_next_same(self):
        car = CacheAwareRouter()
        p = ControlProfile(context_layers=10)
        car.evaluate(p)
        car.update(p)
        action = car.evaluate(p)
        assert action["freeze"] == []


class TestFailureDomain:
    """Test primary_failure_domain attribution."""

    def test_set_get(self):
        clear_failure_domain()
        assert get_last_failure_domain() is None
        set_failure_domain("D3_generation")
        assert get_last_failure_domain() == "D3_generation"

    def test_overwrite(self):
        set_failure_domain("D1_context")
        set_failure_domain("D6_output")
        assert get_last_failure_domain() == "D6_output"

    def test_clear(self):
        set_failure_domain("D5_memory")
        clear_failure_domain()
        assert get_last_failure_domain() is None

    def test_valid_domains(self):
        for d in ["D1_context", "D2_tools", "D3_generation",
                   "D4_orchestration", "D5_memory", "D6_output"]:
            set_failure_domain(d)
            assert get_last_failure_domain() == d
        clear_failure_domain()


class TestGetActiveProfile:
    """Test get_active_profile() fallback chain."""

    def test_returns_default(self):
        """Without any active ReActLoop or RunContext, returns default."""
        p = get_active_profile()
        assert isinstance(p, ControlProfile)

    def test_interpolator_imports(self):
        """Ensure Interpolator doesn't cause circular imports."""
        from core.harness.meta.control_profile import ControlProfileInterpolator
        interp = ControlProfileInterpolator()
        assert interp._registry is not None
