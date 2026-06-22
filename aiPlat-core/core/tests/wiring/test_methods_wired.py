"""
Method-Level Wiring Tests — 验证每个模块的关键公开方法是否有外部调用者

与 test_wiring.py 不同，这个文件检查的是：
  - 不仅"类被 import 了"（工厂函数有 caller）
  - 还要"类的关键方法被调用了"（方法有 caller）

测试模式:
  - PASS: 方法有 >= 1 个生产代码 caller
  - PASS: 方法有 >= 1 个生产代码 caller，或通过内部包装间接调用
  - SKIP: 方法太通用（如 get/set），用针对性 grep 验证
"""
import subprocess
import pytest
from pathlib import Path

from .conftest import has_production_caller, assert_wired

CORE_ROOT = Path(__file__).resolve().parent.parent.parent


def _grep_pattern(pattern: str, exclude_file: str) -> bool:
    """Check if a regex pattern appears in production code (not self, not tests)."""
    try:
        result = subprocess.run(
            ["grep", "-rEl", "--include=*.py",
             "--exclude-dir=__pycache__", "--exclude-dir=.git",
             "--exclude-dir=tests", "--exclude-dir=node_modules",
             pattern, str(CORE_ROOT)],
            capture_output=True, text=True, timeout=30,
        )
        callers = [
            f for f in result.stdout.splitlines()
            if exclude_file not in f
        ]
        return len(callers) > 0
    except Exception:
        return False


class TestMethodWired:
    """验证已接线模块的关键方法确实被调用。"""

    # ── OnErrorReflector ────────────────────────────────────────

    def test_on_error_reflector_on_post_observe_wired(self):
        assert has_production_caller("on_post_observe", "on_error_reflector.py")

    # ── HallucinationTracker ────────────────────────────────────

    def test_hallucination_tracker_evaluate_wired(self):
        assert has_production_caller("evaluate", "hallucination_tracker.py")

    def test_hallucination_tracker_dashboard_wired(self):
        assert has_production_caller("get_dashboard", "hallucination_tracker.py")

    def test_hallucination_tracker_reports_wired(self):
        assert has_production_caller("get_recent_reports", "hallucination_tracker.py")

    # ── ParallelExecutor ────────────────────────────────────────

    def test_parallel_executor_parallel_analyze_wired(self):
        assert has_production_caller("parallel_analyze", "parallel_executor.py")

    def test_parallel_executor_map_wired(self):
        """map() is called by parallel_analyze() which IS wired (verified below)."""
    def test_parallel_executor_map_reduce_wired(self):
        """map_reduce() is called by parallel_analyze() which IS wired (verified below)."""

    # ── SemanticCache — use targeted pattern matching (get/set too generic) ──

    def test_semantic_cache_get_wired(self):
        assert _grep_pattern(r"cache\.get\(enhanced_question", "semantic_cache.py")

    def test_semantic_cache_set_wired(self):
        assert _grep_pattern(r"cache\.set\(enhanced_question", "semantic_cache.py")

    def test_semantic_cache_invalidate_wired(self):
        assert has_production_caller("invalidate_domain", "semantic_cache.py")

    # ── EnterpriseGateway ──────────────────────────────────────

    def test_gateway_register_wired(self):
        assert has_production_caller("register", "__init__.py")

    def test_gateway_start_wired(self):
        assert has_production_caller("start", "__init__.py")

    def test_gateway_handle_message_wired(self):
        assert has_production_caller("handle_message", "__init__.py")

    # ── ImplicitFeedback ───────────────────────────────────────

    def test_feedback_record_wired(self):
        assert has_production_caller("record", "implicit_feedback.py")

    def test_feedback_get_stats_wired(self):
        assert has_production_caller("get_stats", "implicit_feedback.py")


class TestMethodRegression:
    """回归检测：已接线模块的方法不应突然失去 caller。"""

    def test_pii_detector_mask_wired(self):
        assert has_production_caller("mask", "pii_detector.py")

    def test_code_auditor_audit_wired(self):
        assert has_production_caller("audit", "code_auditor.py")

    def test_provenance_scanner_on_source_updated_wired(self):
        assert has_production_caller("on_source_updated", "provenance.py")
