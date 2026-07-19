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
