"""monitoring 模块测试"""

import pytest


class TestMonitoring:
    """监控测试"""

    def test_collector(self):
        """测试收集器"""
        from infra.monitoring.collector import PrometheusMetricsCollector
        from infra.monitoring.schemas import MonitoringConfig

        config = MonitoringConfig()
        collector = PrometheusMetricsCollector(config)
        assert collector is not None


class TestMonitoringSchema:
    """监控数据模型测试"""

    def test_metric_config(self):
        """测试指标配置"""
        from infra.monitoring.schemas import MetricConfig

        config = MetricConfig()
        assert config is not None
