"""http 模块测试"""

import pytest


class TestHttpClient:
    """HTTP 客户端测试"""

    def test_create_client(self):
        """测试创建客户端"""
        from infra.http.httpx_client import SyncHTTPClient

        client = SyncHTTPClient()
        assert client is not None


class TestHttpFactory:
    """HTTP 工厂测试"""

    def test_create_http_client(self):
        """测试创建 HTTP 客户端"""
        from infra.http.factory import create_http_client

        client = create_http_client()
        assert client is not None
