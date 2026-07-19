"""Unit tests for v2.7 new modules: metric_engine, action_contract, rule_auditor."""
import pytest
from unittest.mock import patch, MagicMock
import tempfile, os, json


# ── metric_engine tests ──

class TestMetricEngine:
    def test_load_metrics(self):
        from core.harness.knowledge.metric_engine import load_metrics
        yaml_raw = {
            'metrics': {
                'order_cycle_time': {
                    'label': '订单周期', 'binds_to': 'Order',
                    'measurement': 'completed_at - created_at',
                    'aggregation': 'p95', 'unit': 'hours',
                    'fields_required': ['completed_at', 'created_at'],
                    'thresholds': {'green': '<= 4', 'yellow': '> 4 and <= 8', 'red': '> 8'},
                }
            },
            'classes': {'Order': {'fields': [{'name': 'completed_at'}, {'name': 'created_at'}]}}
        }
        metrics = load_metrics(yaml_raw)
        assert len(metrics) == 1
        m = metrics[0]
        assert m.name == 'order_cycle_time'
        assert m.label == '订单周期'
        assert m.aggregation == 'p95'
        assert m.unit == 'hours'

    def test_load_metrics_empty(self):
        from core.harness.knowledge.metric_engine import load_metrics
        assert load_metrics({}) == []
        assert load_metrics({'metrics': {}}) == []

    def test_threshold_evaluation(self):
        from core.harness.knowledge.metric_engine import _evaluate_thresholds
        thresholds = {'green': '<= 4', 'yellow': '> 4 and <= 8', 'red': '> 8'}
        assert _evaluate_thresholds(2, thresholds) == 'green'
        assert _evaluate_thresholds(6, thresholds) == 'yellow'
        assert _evaluate_thresholds(10, thresholds) == 'red'

    def test_threshold_single_condition(self):
        from core.harness.knowledge.metric_engine import _eval_single_condition
        assert _eval_single_condition(5, '>= 3')
        assert not _eval_single_condition(5, '>= 10')
        assert _eval_single_condition(5, '<= 10')
        assert _eval_single_condition(5, '> 3')
        assert _eval_single_condition(5, '< 10')
        assert _eval_single_condition(5, '== 5')
        assert _eval_single_condition(5, '!= 3')

    def test_compute_requires_db(self):
        """compute() requires a SQLite DB — gracefully returns error when DB missing."""
        from core.harness.knowledge.metric_engine import MetricDefinition, compute
        metric = MetricDefinition(
            name='test', label='test', binds_to='Order',
            measurement='completed_at - created_at', aggregation='count', unit='h',
        )
        result = compute(metric, 'test', time_window_days=1)
        assert result.get('error') or result.get('value') is not None


# ── action_contract tests ──

class TestActionRegistry:
    def test_registry_singleton(self):
        from core.harness.infrastructure.action_contract import get_action_registry
        reg1 = get_action_registry()
        reg2 = get_action_registry()
        assert reg1 is reg2
        assert len(reg1.list_all()) == 4

    def test_builtin_actions_registered(self):
        from core.harness.infrastructure.action_contract import get_action_registry
        reg = get_action_registry()
        actions = {a.action_id for a in reg.list_all()}
        assert 'add_tag' in actions
        assert 'call_webhook' in actions
        assert 'mark_related_for_review' in actions
        assert 'inject_case_study' in actions

    def test_validate_valid_params(self):
        from core.harness.infrastructure.action_contract import get_action_registry
        reg = get_action_registry()
        result = reg.validate_params('add_tag', {'tag': 'test-tag'})
        assert result['valid'] is True

    def test_validate_missing_required(self):
        from core.harness.infrastructure.action_contract import get_action_registry
        reg = get_action_registry()
        result = reg.validate_params('add_tag', {'not_tag': 'x'})
        assert result['valid'] is False
        assert len(result['errors']) >= 1

    def test_validate_unknown_action(self):
        from core.harness.infrastructure.action_contract import get_action_registry
        reg = get_action_registry()
        result = reg.validate_params('nonexistent', {})
        assert result['valid'] is False

    def test_contract_get(self):
        from core.harness.infrastructure.action_contract import get_action_registry
        reg = get_action_registry()
        c = reg.get('call_webhook')
        assert c is not None
        assert c.label == 'Webhook 回调'
        assert c.failure_strategy == 'log_only'
        assert c.retry_policy == {'max_retries': 1, 'backoff_seconds': 5}

    def test_contract_register_new(self):
        from core.harness.infrastructure.action_contract import (
            ActionContract, ActionRegistry,
        )
        reg = ActionRegistry()
        contract = ActionContract(
            action_id='test_action',
            label='Test',
            input_schema={'type': 'object', 'required': ['x']},
            failure_strategy='retry',
        )
        reg.register(contract)
        assert reg.get('test_action') is not None
        result = reg.validate_params('test_action', {'x': 1})
        assert result['valid'] is True
        result = reg.validate_params('test_action', {})
        assert result['valid'] is False


# ── rule_auditor tests ──

class TestRuleAuditor:
    def test_detect_conflicts_empty(self):
        from core.harness.knowledge.rule_auditor import detect_conflicts
        assert detect_conflicts([]) == []

    def test_detect_unreachable(self):
        from core.harness.knowledge.rule_auditor import detect_unreachable
        rules = [{
            'name': 'test_rule',
            'premises': [{'relation': 'nonexistent_rel', 'direction': 'outgoing'}],
            'conclusion': {'relation': 'inferred', 'label': 'test'},
        }]
        domain = {'object_properties': [{'name': 'existing_rel'}]}
        result = detect_unreachable(rules, domain)
        assert len(result) == 1
        assert result[0]['rule_name'] == 'test_rule'
        assert result[0]['missing_relation'] == 'nonexistent_rel'

    def test_detect_unreachable_none(self):
        from core.harness.knowledge.rule_auditor import detect_unreachable
        rules = [{
            'name': 'ok_rule',
            'premises': [{'relation': 'existing_rel', 'direction': 'outgoing'}],
            'conclusion': {'relation': 'inferred'},
        }]
        domain = {'object_properties': [{'name': 'existing_rel'}]}
        assert detect_unreachable(rules, domain) == []

    def test_detect_missing_transitions(self):
        from core.harness.knowledge.rule_auditor import detect_missing_transitions
        domain = {
            'classes': {
                'Order': {
                    'states': {
                        'enum': [{'name': 'created'}, {'name': 'confirmed'}, {'name': 'shipped'}],
                        'transitions': [],
                    }
                },
                'Material': {
                    'states': {
                        'enum': [{'name': 'in_stock'}],
                        'transitions': [],
                    }
                }
            }
        }
        result = detect_missing_transitions(domain)
        assert len(result) == 1  # Order has 3 states but 0 transitions
        assert result[0]['class_name'] == 'Order'

    def test_full_audit(self):
        from core.harness.knowledge.rule_auditor import audit_rules
        domain = {
            'inference_rules': [
                {'name': 'r1', 'premises': [{'relation': 'rel_a', 'direction': 'outgoing'}],
                 'conclusion': {'relation': 'result'}},
                {'name': 'r2', 'premises': [{'relation': 'unknown_x', 'direction': 'outgoing'}],
                 'conclusion': {'relation': 'result'}},
            ],
            'object_properties': [{'name': 'rel_a'}],
            'classes': {},
        }
        result = audit_rules(domain)
        assert result['total_rules'] == 2
        assert result['has_issues'] is True
        assert len(result['unreachable']) >= 1

    def test_audit_empty(self):
        from core.harness.knowledge.rule_auditor import audit_rules
        result = audit_rules({})
        assert result['total_rules'] == 0
        assert result['has_issues'] is False


# ── Round 4: Scoring Engine ──

class TestScoringEngine:
    def test_load_models(self):
        from core.harness.knowledge.scoring_engine import load_models
        yaml = {
            'scoring_models': {
                'churn': {
                    'label': '流失风险', 'binds_to': 'Customer',
                    'rules': [{
                        'name': 'complaints', 'weight': 1,
                        'condition': {'type': 'relation_count', 'relation': 'has_complaint', 'operator': '>=', 'threshold': 3},
                        'score': 'weight * count'
                    }],
                    'thresholds': [{'level': 'high', 'min_score': 3, 'action': 'alert'}],
                }
            }
        }
        models = load_models(yaml)
        assert len(models) == 1
        m = models[0]
        assert m.name == 'churn'
        assert m.binds_to == 'Customer'
        assert len(m.rules) == 1
        assert m.rules[0].weight == 1

    def test_calc_score_formula(self):
        from core.harness.knowledge.scoring_engine import _calc_score
        assert _calc_score('weight * 1', 2, 5) == 2.0
        assert _calc_score('weight * count', 1, 3) == 3.0

    def test_eval_condition(self):
        from core.harness.knowledge.scoring_engine import _eval_condition
        assert _eval_condition('>=', 3, 3)
        assert not _eval_condition('>=', 3, 2)
        assert _eval_condition('>', 2, 3)
        assert _eval_condition('==', 5, 5)
        assert _eval_condition('<', 10, 5)


# ── Round 4: Path Planner ──

class TestPathPlanner:
    def test_load_paths(self):
        from core.harness.knowledge.path_planner import load_paths
        yaml = {
            'reasoning_paths': {
                'test_path': {
                    'label': 'Test', 'start_class': 'Customer', 'target_class': 'Defect',
                    'steps': [{'relation': 'has_ticket', 'direction': 'outgoing', 'target_class': 'Ticket'}],
                    'metadata': {'confidence': 0.85, 'estimated_cost': 5},
                }
            }
        }
        paths = load_paths(yaml)
        assert 'test_path' in paths
        p = paths['test_path']
        assert p.start_class == 'Customer'
        assert len(p.steps) == 1

    def test_compute_cost(self):
        from core.harness.knowledge.path_planner import _compute_cost, ReasoningPath
        p = ReasoningPath(name='t',label='t', steps=[{'relation':'r','direction':'outgoing'}],
                           metadata={'confidence':0.9})
        cost = _compute_cost(p)
        assert cost > 0

    def test_check_applicability(self):
        from core.harness.knowledge.path_planner import _check_applicability, ReasoningPath
        p = ReasoningPath(name='t', label='t')
        assert _check_applicability(p, {})  # no conditions → always applicable
        p2 = ReasoningPath(name='t2', label='t2', applicability={
            'property_condition': {'field': 'customer_level', 'operator': '==', 'value': 'VIP'}
        })
        assert not _check_applicability(p2, {'filters': {'customer_level': '普通'}})


# ── Round 5: Domain Maturity ──

class TestDomainMaturity:
    def test_score_from_mapping(self):
        from core.harness.knowledge.domain_maturity import _score_from_mapping
        m = {"0": 0, "10": 50, "50": 100}
        assert _score_from_mapping(0, m) == 0
        assert _score_from_mapping(10, m) == 50
        assert _score_from_mapping(30, m) == 75  # interpolated
        assert _score_from_mapping(100, m) == 100

    def test_level_mapping(self):
        from core.harness.knowledge.domain_maturity import LEVELS
        assert len(LEVELS) == 5
        assert LEVELS[0] == (80, "production-ready")
        assert LEVELS[-1] == (0, "seeding")


# ── Round 5: Scenario Selector ──

class TestScenarioSelector:
    def test_evaluate_5_criteria(self):
        from core.harness.knowledge.scenario_selector import evaluate_scenario_5_criteria, Scenario
        s = Scenario(name='test', impact='high', urgency='high',
                      process_closure='clear', data_availability='available',
                      value_verifiability='verifiable', semantic_asset_reuse='high')
        result = evaluate_scenario_5_criteria(s)
        assert result['total'] >= 80
        assert result['recommendation'] == 'strongly_recommended'

    def test_evaluate_weak_scenario(self):
        from core.harness.knowledge.scenario_selector import evaluate_scenario_5_criteria, Scenario
        s = Scenario(name='test', impact='low', urgency='low',
                      process_closure='unknown', data_availability='unavailable',
                      value_verifiability='unknown', semantic_asset_reuse='low')
        result = evaluate_scenario_5_criteria(s)
        assert result['total'] < 60
        assert result['recommendation'] == 'defer'

    def test_value_formula(self):
        from core.harness.knowledge.scenario_selector import value_opportunity_formula, Scenario
        s = Scenario(name='供应商评估', domain_id='supply-chain', pain='评审周期过长')
        formula = value_opportunity_formula(s)
        assert '供应商评估' in formula
        assert 'supply-chain' in formula

    def test_quadrant_labels(self):
        from core.harness.knowledge.scenario_selector import QUADRANT_LABELS
        assert QUADRANT_LABELS[('high', 'high')][0] == 'P0'
        assert QUADRANT_LABELS[('low', 'low')][0] == 'P3'


# ── Round 6: Governance Pipeline ──

class TestGovernancePipeline:
    def test_step_result_defaults(self):
        from core.harness.knowledge.governance_pipeline import StepResult
        s = StepResult(step_index=1, step_name="scenario")
        assert s.status == "completed"
        assert s.warnings == []

    def test_cycle_result_health(self):
        from core.harness.knowledge.governance_pipeline import GovernanceCycleResult, StepResult
        r = GovernanceCycleResult(
            cycle_id="test-1", timestamp="2026-07-19", domain_id="test",
            step_results=[
                StepResult(step_index=1, step_name="scenario", status="completed"),
                StepResult(step_index=2, step_name="modeling", status="completed"),
                StepResult(step_index=3, step_name="mapping", status="warning", warnings=["low coverage"]),
            ],
            overall_health=75.0, health_level="warning",
        )
        assert r.overall_health == 75.0
        assert r.health_level == "warning"


# ── Round 6: Ontology Approval ──

class TestOntologyApproval:
    def test_submit_and_list(self):
        from core.harness.infrastructure.gates.ontology_approval import submit, list_pending, approve
        # Submit a test request
        req = submit("test_domain", "class_add", requested_by="test_user", justification="test")
        assert req.status == "pending"
        assert req.domain_id == "test_domain"

        # List pending
        pending = list_pending("test_domain")
        assert len(pending) >= 1

        # Approve it
        result = approve(req.id, "governance_admin")
        assert result["success"]

        # Clean up — delete test request
        import sqlite3, os
        db = os.path.expanduser("~/.aiplat/state_changes.db")
        conn = sqlite3.connect(db, timeout=5.0)
        conn.execute("DELETE FROM change_requests WHERE domain_id = 'test_domain'")
        conn.commit()
        conn.close()

    def test_reject(self):
        from core.harness.infrastructure.gates.ontology_approval import submit, reject
        req = submit("test_domain2", "rule_edit", requested_by="test", justification="test")
        result = reject(req.id, "governance_admin", "not needed")
        assert result["success"]

    def test_can_publish(self):
        from core.harness.infrastructure.gates.ontology_approval import can_publish
        assert can_publish("governance_admin")
        assert can_publish("admin")
        assert not can_publish("viewer")


# ── Round 6: Mapping Validator ──

class TestMappingValidator:
    def test_validate_nonexistent_source(self):
        from core.harness.knowledge.mapping_validator import validate_source
        result = validate_source("nonexistent_ds_999")
        assert result.status == "critical"

    def test_generate_empty_report(self):
        from core.harness.knowledge.mapping_validator import generate_mapping_report
        report = generate_mapping_report(["nonexistent_ds_999"])
        assert "No data sources" in report or "nonexistent" in report
