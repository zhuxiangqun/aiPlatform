"""Unit tests for v2.9 key modules — GrillingBridge, EvalMetrics, BusinessValue, SelfHealGate, SystemHealth.

Tests cover the most critical subsystems built in the v2.9 evaluation cycle.
Run: pytest tests/unit/test_v2_9_modules.py -v
"""

import pytest
import sys
import os

# Path setup
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
os.chdir(os.path.join(os.path.dirname(__file__), "../.."))


# ═══════════════════════════════════════════════════════════════
# 1. GrillingBridge Tests
# ═══════════════════════════════════════════════════════════════

class TestGrillingBridge:
    def test_start_grilling_returns_question(self):
        from core.api.core_facade import start_grilling
        r = start_grilling("fde_builder", "fde-delivery")
        assert r["status"] == "asking"
        assert "question" in r
        assert len(r["question"]["options"]) >= 3

    def test_start_grilling_fallback_dimensions(self):
        from core.api.core_facade import start_grilling
        r = start_grilling("unknown_entry_point", "")
        assert r["status"] == "asking" or r["status"] == "no_dimensions"

    def test_continue_grilling_progresses(self):
        from core.api.core_facade import start_grilling, continue_grilling
        r = start_grilling("fde_builder", "fde-delivery")
        sid = r["session_id"]
        r2 = continue_grilling(sid, "Web 应用")
        assert r2["status"] == "asking"
        assert r2.get("progress", {}).get("current", 0) >= 2

    def test_skip_grilling(self):
        from core.api.core_facade import start_grilling, skip_grilling_question
        r = start_grilling("agent_chat", "")
        sid = r["session_id"]
        r2 = skip_grilling_question(sid)
        assert r2["status"] in ("asking", "error")

    def test_get_grilling_progress(self):
        from core.api.core_facade import start_grilling, get_grilling_progress
        r = start_grilling("fde_builder", "")
        sid = r["session_id"]
        p = get_grilling_progress(sid)
        assert p["status"] == "in_progress"
        assert "answered" in p

    def test_finalize_grilling_returns_structured(self):
        from core.api.core_facade import start_grilling, continue_grilling
        r = start_grilling("fde_builder", "fde-delivery")
        sid = r["session_id"]
        for ans in ["Web 应用", "React + TypeScript", "Docker 自托管",
                     "Docker Compose", "4角色(PM+Arch+Dev+QA)", "中型(万级用户)",
                     "REST API", "无特殊要求"]:
            r = continue_grilling(sid, ans)
        assert r["status"] == "completed"
        assert r.get("answered", 0) >= 5
        assert "answers_flat" in r


# ═══════════════════════════════════════════════════════════════
# 2. EvalMetrics Tests (P0-P2)
# ═══════════════════════════════════════════════════════════════

class TestTrajectoryMatch:
    def test_exact_order_full_match(self):
        from core.harness.evaluation.eval_metrics import EvalMetricsEngine
        from core.harness.evaluation.eval_types import MatchMode
        engine = EvalMetricsEngine()
        events = [
            {"kind": "tool", "name": "lookup_order"},
            {"kind": "tool", "name": "check_refund_policy"},
            {"kind": "tool", "name": "issue_refund"},
        ]
        r = engine.compute_trajectory_quality(
            events, ["lookup_order", "check_refund_policy", "issue_refund"],
            MatchMode.EXACT_ORDER)
        assert r.matched is True
        assert r.score == 1.0

    def test_exact_order_missing_step(self):
        from core.harness.evaluation.eval_metrics import EvalMetricsEngine
        from core.harness.evaluation.eval_types import MatchMode
        engine = EvalMetricsEngine()
        events = [
            {"kind": "tool", "name": "lookup_order"},
            {"kind": "tool", "name": "issue_refund"},
        ]
        r = engine.compute_trajectory_quality(
            events, ["lookup_order", "check_refund_policy", "issue_refund"],
            MatchMode.EXACT_ORDER)
        assert r.matched is False
        assert "check_refund_policy" in r.missing

    def test_in_order_allows_extra(self):
        from core.harness.evaluation.eval_metrics import EvalMetricsEngine
        from core.harness.evaluation.eval_types import MatchMode
        engine = EvalMetricsEngine()
        events = [
            {"kind": "tool", "name": "lookup_order"},
            {"kind": "tool", "name": "log_action"},
            {"kind": "tool", "name": "check_refund_policy"},
            {"kind": "tool", "name": "issue_refund"},
        ]
        r = engine.compute_trajectory_quality(
            events, ["lookup_order", "check_refund_policy", "issue_refund"],
            MatchMode.IN_ORDER)
        assert r.matched is True
        assert r.matched_count == 3

    def test_any_order_match(self):
        from core.harness.evaluation.eval_metrics import EvalMetricsEngine
        from core.harness.evaluation.eval_types import MatchMode
        engine = EvalMetricsEngine()
        events = [
            {"kind": "tool", "name": "issue_refund"},
            {"kind": "tool", "name": "lookup_order"},
            {"kind": "tool", "name": "check_refund_policy"},
        ]
        r = engine.compute_trajectory_quality(
            events, ["lookup_order", "check_refund_policy", "issue_refund"],
            MatchMode.ANY_ORDER)
        assert r.matched is True

    def test_empty_expected_always_matches(self):
        from core.harness.evaluation.eval_metrics import EvalMetricsEngine
        from core.harness.evaluation.eval_types import MatchMode
        engine = EvalMetricsEngine()
        r = engine.compute_trajectory_quality(
            [{"kind": "tool", "name": "any"}], [], MatchMode.EXACT_ORDER)
        assert r.matched is True


class TestTextQuality:
    def test_text_quality_heuristic_fallback(self):
        from core.harness.evaluation.eval_metrics import EvalMetricsEngine
        engine = EvalMetricsEngine()
        r = engine.compute_text_quality("## Section\nContent here\n## More")
        assert 0 <= r.coherence_score <= 1
        assert 0 <= r.conciseness_score <= 1
        assert 0 <= r.instruction_following_score <= 1

    def test_text_quality_short_input(self):
        from core.harness.evaluation.eval_metrics import EvalMetricsEngine
        engine = EvalMetricsEngine()
        r = engine.compute_text_quality("ab")
        assert r.coherence_score == 0.5
        assert r.reasoning == "too short"


class TestContentSafety:
    def test_clean_content(self):
        from core.harness.evaluation.eval_metrics import EvalMetricsEngine
        engine = EvalMetricsEngine()
        r = engine.compute_content_safety("This is a normal message about programming.")
        assert r.harmful_score == 1.0
        assert r.stereotype_score == 1.0
        assert r.flagged_patterns == []

    def test_harmful_content_detected(self):
        from core.harness.evaluation.eval_metrics import EvalMetricsEngine
        engine = EvalMetricsEngine()
        r = engine.compute_content_safety("how to hack someone password and bypass security")
        assert r.harmful_score < 1.0
        assert len(r.flagged_patterns) >= 1

    def test_stereotype_detected(self):
        from core.harness.evaluation.eval_metrics import EvalMetricsEngine
        engine = EvalMetricsEngine()
        r = engine.compute_content_safety("all women are bad at coding")
        assert r.stereotype_score < 1.0


class TestRefusal:
    def test_no_refusal(self):
        from core.harness.evaluation.eval_metrics import EvalMetricsEngine
        engine = EvalMetricsEngine()
        r = engine.compute_refusal("Sure, here is your answer.", "")
        assert r.is_refusal is False

    def test_refusal_detected(self):
        from core.harness.evaluation.eval_metrics import EvalMetricsEngine
        engine = EvalMetricsEngine()
        r = engine.compute_refusal("I cannot help you with that.", "")
        assert r.is_refusal is True

    def test_over_refusal_classification(self):
        from core.harness.evaluation.eval_metrics import EvalMetricsEngine
        engine = EvalMetricsEngine()
        r = engine.compute_refusal(
            "As an AI I cannot help you write an email.",
            "write an email to my boss")
        assert r.refusal_type == "over_refusal"


# ═══════════════════════════════════════════════════════════════
# 3. BusinessValue Tests
# ═══════════════════════════════════════════════════════════════

class TestBusinessValue:
    def test_generate_renewal_report_basics(self):
        from core.harness.evaluation.business_value import generate_renewal_report
        r = generate_renewal_report("spec_test", "Test Project", 500)
        assert r["grade"] in ("A", "B", "C", "D", "F")
        assert len(r["kpis"]) == 5
        assert r["monthly_exec_count"] == 500
        assert "agent_breakdown" in r

    def test_renewal_suggestion_non_empty(self):
        from core.harness.evaluation.business_value import generate_renewal_report
        r = generate_renewal_report("spec_test_2", "Project2", 100)
        assert len(r["renewal_suggestion"]) > 10
        assert r["hours_saved"] > 0

    def test_agent_breakdown_has_entries(self):
        from core.harness.evaluation.business_value import generate_renewal_report
        r = generate_renewal_report("spec_with_agents", "Multi Agent", 300)
        assert len(r.get("agent_breakdown", [])) >= 3


# ═══════════════════════════════════════════════════════════════
# 4. SelfHealGate Tests
# ═══════════════════════════════════════════════════════════════

class TestSelfHealGate:
    def test_auto_apply_for_low_risk_dev(self):
        from core.harness.evaluation.self_heal_gate import SelfHealGate, AUTO
        gate = SelfHealGate()
        level = gate.evaluate("orphan_domain_flag", {"source": "test"}, "dev")
        assert level == AUTO

    def test_suggest_for_medium_risk(self):
        from core.harness.evaluation.self_heal_gate import SelfHealGate, SUGGEST
        gate = SelfHealGate()
        level = gate.evaluate("model_tier_escalate", {"source": "test"}, "dev")
        assert level == SUGGEST

    def test_reject_for_high_risk(self):
        from core.harness.evaluation.self_heal_gate import SelfHealGate, REJECT
        gate = SelfHealGate()
        level = gate.evaluate("hitl_bypass_fix", {"source": "test"}, "dev")
        assert level == REJECT

    def test_production_escalation(self):
        from core.harness.evaluation.self_heal_gate import SelfHealGate, SUGGEST, REJECT
        gate = SelfHealGate()
        # model_tier_escalate: SUGGEST for dev → REJECT for production
        level = gate.evaluate("model_tier_escalate", {"source": "prod"}, "production")
        assert level == REJECT

    def test_apply_logs_entry(self):
        from core.harness.evaluation.self_heal_gate import SelfHealGate
        gate = SelfHealGate()
        r = gate.apply("orphan_domain_flag", {"source": "test_domain",
                        "detail": "5 orphans"}, "dev")
        assert r["status"] == "applied"
        logs = gate.get_heal_log(5)
        assert len(logs) >= 1


# ═══════════════════════════════════════════════════════════════
# 5. SystemHealth Tests
# ═══════════════════════════════════════════════════════════════

class TestSystemHealth:
    def test_compute_returns_all_fields(self):
        from core.harness.evaluation.system_health import SystemHealthCalculator
        report = SystemHealthCalculator().compute()
        assert 0 <= report.health_index <= 100
        assert report.grade in ("A", "B+", "B", "B-", "C", "D")
        assert report.trend in ("↑", "→", "↓")
        assert len(report.sub_scores) == 4
        for k in ("ontology_audit", "staleness", "config_drift", "eval_metrics"):
            assert k in report.sub_scores

    def test_sub_scores_in_range(self):
        from core.harness.evaluation.system_health import SystemHealthCalculator
        report = SystemHealthCalculator().compute()
        for v in report.sub_scores.values():
            assert 0 <= v.score <= 100

    def test_ewma_trend_consistent(self):
        from core.harness.evaluation.system_health import SystemHealthCalculator
        calc = SystemHealthCalculator()
        report = calc.compute()
        if report.trend == "→":
            assert abs(report.trend_delta) <= 1
        elif report.trend == "↑":
            assert report.trend_delta > 0
        elif report.trend == "↓":
            assert report.trend_delta < 0


# ═══════════════════════════════════════════════════════════════
# 6. Constraint Validator Tests
# ═══════════════════════════════════════════════════════════════

class TestConstraintValidator:
    def test_scan_returns_list(self):
        from core.harness.evaluation.constraint_validator import ConstraintValidator
        issues = ConstraintValidator().scan_all()
        assert isinstance(issues, list)

    def test_issue_has_required_fields(self):
        from core.harness.evaluation.constraint_validator import ConstraintValidator
        issues = ConstraintValidator().scan_all()
        if issues:
            i = issues[0]
            assert i.source
            assert i.issue_type
            assert i.level in ("CRITICAL", "HIGH", "WARNING")


# ═══════════════════════════════════════════════════════════════
# 7. Agent Config Diff Tests
# ═══════════════════════════════════════════════════════════════

class TestAgentConfigDiff:
    def test_diff_detects_model_change(self):
        from core.harness.evaluation.agent_config_diff import compute_agent_diff
        old = "---\nmodel: qwen2.5:3b\nrequired_skills: [code_review]\n---"
        new = "---\nmodel: deepseek-v4-pro\nrequired_skills: [code_review, grilling]\n---"
        d = compute_agent_diff(old, new)
        assert "model" in d["changed"]
        assert d["risk_level"] == "high"  # model change is high risk

    def test_diff_detects_field_addition(self):
        from core.harness.evaluation.agent_config_diff import compute_agent_diff
        old = "---\nstatus: ready\n---"
        new = "---\nstatus: ready\nauto_hitl: true\n---"
        d = compute_agent_diff(old, new)
        assert d["summary"] != "无变更"
        assert "auto_hitl" in d["added"]

    def test_no_change(self):
        from core.harness.evaluation.agent_config_diff import compute_agent_diff
        cfg = "---\nstatus: ready\nversion: '1.0'\n---"
        d = compute_agent_diff(cfg, cfg)
        assert d["summary"] == "无变更"
