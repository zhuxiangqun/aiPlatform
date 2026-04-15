"""
Dashboard 测试
"""

import pytest
from management.dashboard import DashboardAggregator, InfraAdapter


@pytest.mark.asyncio
async def test_dashboard_aggregator():
    """测试 Dashboard 聚合器"""
    aggregator = DashboardAggregator()
    aggregator.register_adapter("infra", InfraAdapter())
    
    # 测试聚合
    result = await aggregator.aggregate()
    
    assert "timestamp" in result
    assert "layers" in result
    assert "infra" in result["layers"]
    assert "overall_status" in result


@pytest.mark.asyncio
async def test_infra_adapter():
    """测试 infra 适配器"""
    adapter = InfraAdapter()
    
    # 测试状态获取
    status = await adapter.get_status()
    assert status["layer"] == "infra"
    assert "status" in status
    
    # 测试健康检查
    health = await adapter.health_check()
    assert isinstance(health, bool)
