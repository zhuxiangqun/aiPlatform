"""
Core 层监控指标测试

测试 Format Affinity 和 Value Decay 指标采集
"""

import pytest
from datetime import datetime
from management.monitoring.collector import Metric, MetricsCollector
from management.monitoring.core_collector import CoreMetricsCollector


class TestFormatAffinityMetrics:
    """Format Affinity 指标测试"""
    
    def test_metric_creation(self):
        """测试指标创建"""
        metric = Metric(
            name="format_affinity_match_rate",
            value=0.85,
            labels={"type": "all"},
            unit="ratio"
        )
        
        assert metric.name == "format_affinity_match_rate"
        assert metric.value == 0.85
        assert metric.unit == "ratio"
    
    def test_metric_to_dict(self):
        """测试指标转字典"""
        metric = Metric(
            name="format_affinity_structural_score",
            value=0.82,
            labels={"type": "all"},
            unit="score"
        )
        
        result = metric.to_dict()
        
        assert result["name"] == "format_affinity_structural_score"
        assert result["value"] == 0.82
        assert "timestamp" in result
    
    def test_format_affinity_metric_fields(self):
        """测试 Format Affinity 指标字段"""
        metrics = [
            Metric(name="format_affinity_match_rate", value=0.85, unit="ratio"),
            Metric(name="format_affinity_structural_score", value=0.82, unit="score"),
            Metric(name="format_affinity_style_score", value=0.78, unit="score"),
        ]
        
        names = [m.name for m in metrics]
        
        assert "format_affinity_match_rate" in names
        assert "format_affinity_structural_score" in names
        assert "format_affinity_style_score" in names
    
    def test_format_affinity_value_range(self):
        """测试 Format Affinity 值范围 (0-1)"""
        metric = Metric(
            name="format_affinity_match_rate",
            value=0.85,
            labels={"type": "all"},
            unit="ratio"
        )
        
        assert 0 <= metric.value <= 1


class TestValueDecayMetrics:
    """Value Decay 指标测试"""
    
    def test_value_decay_metric_creation(self):
        """测试 Value Decay 指标创建"""
        metric = Metric(
            name="value_decay_format_affinity",
            value=0.05,
            labels={"type": "format"},
            unit="per_day"
        )
        
        assert metric.name == "value_decay_format_affinity"
        assert metric.value == 0.05
        assert metric.unit == "per_day"
    
    def test_decay_rates_different(self):
        """测试不同类型的衰减速率不同"""
        decay_metrics = [
            Metric(name="value_decay_format_affinity", value=0.05, labels={"type": "format"}, unit="per_day"),
            Metric(name="value_decay_capability_complement", value=0.02, labels={"type": "capability"}, unit="per_day"),
            Metric(name="value_decay_feedback_quality", value=0.005, labels={"type": "feedback"}, unit="per_day"),
        ]
        
        rates = [m.value for m in decay_metrics]
        
        assert rates[0] > rates[1] > rates[2]
    
    def test_format_affinity_decay_fastest(self):
        """测试 Format Affinity 衰减最快"""
        format_decay = Metric(name="value_decay_format_affinity", value=0.05, unit="per_day")
        capability_decay = Metric(name="value_decay_capability_complement", value=0.02, unit="per_day")
        feedback_decay = Metric(name="value_decay_feedback_quality", value=0.005, unit="per_day")
        
        assert format_decay.value == capability_decay.value * 2.5
        assert capability_decay.value == feedback_decay.value * 4
    
    def test_decay_unit_per_day(self):
        """测试衰减单位为 per_day"""
        metric = Metric(
            name="value_decay_format_affinity",
            value=0.05,
            unit="per_day"
        )
        
        assert metric.unit == "per_day"


class TestCoreMetricsCollector:
    """Core 指标采集器测试"""
    
    def test_collector_initialization(self):
        """测试采集器初始化"""
        collector = CoreMetricsCollector()
        
        assert collector.layer == "core"
    
    def test_collect_includes_format_affinity(self):
        """测试采集包含 Format Affinity 指标"""
        collector = CoreMetricsCollector()
        
        import asyncio
        loop = asyncio.new_event_loop()
        metrics = loop.run_until_complete(collector.collect())
        loop.close()
        
        metric_names = [m.name for m in metrics]
        
        assert "format_affinity_match_rate" in metric_names
    
    def test_collect_includes_value_decay(self):
        """测试采集包含 Value Decay 指标"""
        collector = CoreMetricsCollector()
        
        import asyncio
        loop = asyncio.new_event_loop()
        metrics = loop.run_until_complete(collector.collect())
        loop.close()
        
        metric_names = [m.name for m in metrics]
        
        assert "value_decay_format_affinity" in metric_names
        assert "value_decay_capability_complement" in metric_names
        assert "value_decay_feedback_quality" in metric_names
    
    def test_all_new_metrics_present(self):
        """测试所有新增指标都存在"""
        collector = CoreMetricsCollector()
        
        import asyncio
        loop = asyncio.new_event_loop()
        metrics = loop.run_until_complete(collector.collect())
        loop.close()
        
        expected_metrics = [
            "format_affinity_match_rate",
            "format_affinity_structural_score",
            "format_affinity_style_score",
            "value_decay_format_affinity",
            "value_decay_capability_complement",
            "value_decay_feedback_quality"
        ]
        
        metric_names = [m.name for m in metrics]
        
        for expected in expected_metrics:
            assert expected in metric_names, f"Missing: {expected}"