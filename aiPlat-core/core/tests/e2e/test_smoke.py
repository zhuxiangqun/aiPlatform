"""
E2E Smoke Tests — 端到端冒烟测试模板

对每个新接线模块，必须至少有一个 E2E 测试验证该能力在真实执行路径中生效。

模式：
  1. 构造触发场景
  2. 执行真实的 agent.execute / tool.execute / API 调用
  3. 断言预期信号（事件、日志、返回值变化）

注意：E2E 测试需要 live 服务（platform 8003 + core 8001），
      如服务不可用则标记为 SKIP（不阻断 CI）。
"""

import os
import sys
import pytest
from pathlib import Path


# ── 跳过条件：如果核心服务未运行则跳过 ──

CORE_URL = os.getenv("AIPLAT_CORE_URL", "http://localhost:8001")

def _core_healthy() -> bool:
    """Check if core service is reachable."""
    try:
        import urllib.request
        r = urllib.request.urlopen(f"{CORE_URL}/health", timeout=3)
        return r.status == 200
    except Exception:
        return False


def requires_live_server(test_fn):
    """Decorator: skip test if core service is unreachable."""
    return pytest.mark.skipif(
        not _core_healthy(),
        reason=f"Core service unreachable at {CORE_URL}. Start server first."
    )(test_fn)


# ═══════════════════════════════════════════════════════════════
# 模板：为新接线模块编写 E2E 测试
# ═══════════════════════════════════════════════════════════════

class TestE2ESmoke:
    """E2E smoke tests for wired capabilities."""

    @requires_live_server
    def test_semantic_cache_hit_on_duplicate_query(self):
        """Phase 0.3: SemanticCache — duplicate query should hit cache."""
        # Template — implement when SemanticCache is wired to RAG pipeline.
        # 1. Execute query via agent → capture response + cache metrics
        # 2. Execute identical query → assert response time < first query
        # 3. Assert cache hit event in logs/metrics
        pytest.skip("SemanticCache not yet wired — implement after Phase 7 wiring")

    @requires_live_server
    def test_hallucination_detection_on_contradictory_context(self):
        """Phase 3.1: HallucinationTracker — contradictory context triggers warning."""
        # Template:
        # 1. Submit query with known contradictory source data
        # 2. Assert hallucination_risk > 0.5 in response metadata
        # 3. Assert hallucination_report present in audit log
        pytest.skip("HallucinationTracker not yet wired — implement after Phase 7 wiring")

    @requires_live_server
    def test_error_reflection_on_consecutive_tool_failures(self):
        """Phase 4.1: OnErrorReflector — 2 consecutive failures trigger reflection."""
        # Template:
        # 1. Execute agent with tool that always fails
        # 2. Assert RuntimeEvent with type="reflection" appears
        # 3. Assert reflection hint injected into next reasoning step
        pytest.skip("OnErrorReflector not yet wired — implement after Phase 7 wiring")

    @requires_live_server
    def test_parallel_executor_fanout_completion(self):
        """Phase 1.2: ParallelExecutor — 3 parallel tasks complete faster than serial."""
        # Template:
        # 1. Submit 3 independent sub-tasks via ParallelExecutor.map_reduce()
        # 2. Assert all 3 complete successfully
        # 3. Assert total time < sum of individual times (parallelism benefit)
        pytest.skip("ParallelExecutor not yet wired — implement after Phase 7 wiring")

    @requires_live_server
    def test_implicit_feedback_copy_event(self):
        """Phase 4.2: ImplicitFeedbackCollector — copy event updates provenance."""
        # Template:
        # 1. Execute query → get answer
        # 2. Simulate frontend "copy" event via feedback API
        # 3. Assert answer confidence increased (+0.3) in ProvenanceTracker
        pytest.skip("ImplicitFeedbackCollector not yet wired — implement after Phase 7 wiring")

    @requires_live_server
    def test_gateway_sends_to_feishu_webhook(self):
        """Phase 2.3: EnterpriseGateway — notification sent via feishu adapter."""
        # Template:
        # 1. Configure AIPLAT_FEISHU_WEBHOOK
        # 2. Trigger notification event
        # 3. Assert feishu adapter formatted message correctly
        pytest.skip("EnterpriseGateway not yet wired — implement after Phase 7 wiring")


# ═══════════════════════════════════════════════════════════════
# 已接线模块的回归 E2E 测试（有 live 服务时运行）
# ═══════════════════════════════════════════════════════════════

class TestE2ERegression:
    """Regression E2E tests for already-wired capabilities."""

    @requires_live_server
    def test_health_endpoint(self):
        """Core health endpoint should return 200."""
        import urllib.request
        r = urllib.request.urlopen(f"{CORE_URL}/health", timeout=5)
        assert r.status == 200

    @requires_live_server
    def test_pii_masked_in_llm_call(self):
        """PII should be masked before reaching LLM."""
        # Template: send query with phone number, verify masked in logs
        pytest.skip("Requires log inspection — implement manually")
