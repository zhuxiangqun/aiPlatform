"""mcp 模块测试"""

import pytest


class TestMCPClient:
    """MCP 客户端测试"""

    def test_mcp_client_implementation(self):
        """测试 MCP 客户端实现"""
        from infra.mcp.client import MCPClientImpl
        from infra.mcp.schemas import MCPConfig

        config = MCPConfig()
        client = MCPClientImpl(config)
        assert client is not None


class TestMCPTransport:
    """MCP 传输测试"""

    def test_stdio_transport_available(self):
        """测试 stdio 传输可导入性"""
        try:
            from infra.mcp.transport.stdio import StdioTransport

            transport = StdioTransport
            assert transport is not None
        except ImportError:
            pass  # optional dependency


class TestMCPSchema:
    """MCP 数据模型测试"""

    def test_tool(self):
        """测试工具"""
        from infra.mcp.schemas import Tool

        tool = Tool(name="test", description="A test tool")
        assert tool.name == "test"
