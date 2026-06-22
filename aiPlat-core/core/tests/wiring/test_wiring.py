"""
Wiring Assertion Tests — 验证模块是否被接入生产线

这些测试不测模块功能（那是单元测试的事），而是测模块是否被实际使用。
每个新创建的公共模块必须有一个生产代码 caller，否则 CI 亮红灯。

测试模式:
  - PASS: 工厂函数有 >= 1 个非自身的 production caller
  - PASS: 模块有 >= 1 个非自身的 production caller
  - FAIL: 模块突然失去所有 caller（回归检测）
"""

import pytest

from .conftest import has_production_caller, assert_wired


# ═══════════════════════════════════════════════════════════════
# 已接线模块 — 必须持续保持 PASS（回归检测）
# ═══════════════════════════════════════════════════════════════

class TestWiredModules:

    def test_pii_detector_wired(self):
        assert has_production_caller("get_pii_detector", "pii_detector.py")

    def test_code_auditor_wired(self):
        assert has_production_caller("CodeAuditor", "code_auditor.py")

    def test_provenance_scanner_wired(self):
        assert has_production_caller("ProvenanceScanner", "provenance.py")

    def test_auto_trigger_wired(self):
        assert has_production_caller("get_lora_auto_trigger", "auto_trigger.py")

    def test_skill_simulator_wired(self):
        assert has_production_caller("SkillSimulator", "skill_simulator.py")

    def test_canary_router_wired(self):
        assert has_production_caller("get_skill_router", "canary.py")

    def test_experience_cache_wired(self):
        assert has_production_caller("get_experience_cache", "experience_vector.py")

    def test_evolution_engine_wired(self):
        assert has_production_caller("EvolutionEngine", "evolution_engine.py")


# ═══════════════════════════════════════════════════════════════
# 已接线模块 — 全部 PASS（回归检测）
# ═══════════════════════════════════════════════════════════════

class TestNewlyWiredModules:

    def test_error_reflector_wired(self):
        assert_wired("create_on_error_reflector", "on_error_reflector.py",
                      "Phase 4.1", "Real-time Agent error reflection hook")

    def test_hallucination_tracker_wired(self):
        assert_wired("get_hallucination_tracker", "hallucination_tracker.py",
                      "Phase 3.1", "NLI fact-checking + Faithfulness scoring")

    def test_parallel_executor_wired(self):
        assert_wired("ParallelExecutor", "parallel_executor.py",
                      "Phase 1.2", "Sub-Agent FanOut Map-Reduce parallel execution")

    def test_enterprise_gateway_wired(self):
        assert_wired("get_enterprise_gateway", "__init__.py",
                      "Phase 2.3", "Feishu/WeCom/Slack enterprise messaging")

    def test_implicit_feedback_wired(self):
        assert_wired("get_implicit_feedback_collector", "implicit_feedback.py",
                      "Phase 4.2", "User behavior implicit feedback collection")

    def test_semantic_cache_wired(self):
        assert_wired("get_semantic_cache", "semantic_cache.py",
                      "Phase 0.3", "L1+L2+L3 semantic cache for RAG pipeline")


# ═══════════════════════════════════════════════════════════════
# 自检 — wiring test infrastructure correctness
# ═══════════════════════════════════════════════════════════════

class TestWiringInfrastructure:

    def test_has_caller_detects_wired_symbol(self):
        assert has_production_caller("get_pii_detector", "pii_detector.py") is True

    def test_has_caller_detects_dead_symbol(self):
        assert has_production_caller("NonExistentSymbolXYZ123", "nonexistent.py") is False

    def test_caller_index_size(self):
        from .conftest import _build_index
        idx = _build_index()
        assert len(idx) > 500, f"Index too small: {len(idx)} symbols"
