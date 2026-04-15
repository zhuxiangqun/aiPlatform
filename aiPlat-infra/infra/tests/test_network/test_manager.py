"""network 模块测试"""

import pytest


class TestNetworkManager:
    """网络管理器测试"""

    def test_static_network_manager(self):
        """测试静态网络管理器"""
        from infra.network.manager import StaticNetworkManager
        from infra.network.schemas import NetworkConfig

        config = NetworkConfig()
        manager = StaticNetworkManager(config)
        assert manager is not None


class TestNetworkSchema:
    """网络数据模型测试"""

    def test_service(self):
        """测试服务"""
        from infra.network.schemas import Service

        service = Service(name="test", endpoints=[])
        assert service.name == "test"

    def test_endpoint(self):
        """测试端点"""
        from infra.network.schemas import Endpoint

        endpoint = Endpoint(address="localhost", port=8000)
        assert endpoint.address == "localhost"
        assert endpoint.port == 8000
