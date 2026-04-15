"""observability 模块测试"""

import pytest


class TestObservability:
    """可观测性测试"""

    def test_tracer(self):
        """测试追踪器"""
        from infra.observability.tracing import SimpleTracer
        from infra.observability.schemas import ObservabilityConfig

        config = ObservabilityConfig()
        tracer = SimpleTracer(config)
        assert tracer is not None


class TestObservabilitySchema:
    """可观测性数据模型测试"""

    def test_config(self):
        """测试配置"""
        from infra.observability.schemas import TracingConfig

        config = TracingConfig()
        assert config is not None
