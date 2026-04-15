"""
Monitoring 测试
"""

import pytest
from management.monitoring import InfraMetricsCollector


@pytest.mark.asyncio
async def test_infra_metrics_collector():
    """测试 infra 指标采集器"""
    collector = InfraMetricsCollector()
    
    # 测试指标采集
    metrics = await collector.collect()
    
    assert len(metrics) > 0
    assert all(m.name for m in metrics)
    assert all(m.value is not None for m in metrics)
