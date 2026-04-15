# MCP 协议集成设计

## 概述

本文档描述如何将 Model Context Protocol (MCP) 集成到 aiPlat-core 系统，使系统能够连接外部 MCP 服务器并使用其提供的工具。

## 目标

1. **连接外部 MCP 服务器** - 支持 stdio 和 SSE 传输
2. **工具接入** - 将 MCP 工具转换为本地 ITool 接口
3. **工具导出** - 将本地工具暴露为 MCP 服务器

## 架构设计

### 模块结构

```
core/apps/mcp/
├── types.py       # 协议数据类型定义
├── protocol.py    # JSON-RPC 处理、SSE/stdio 传输
├── client.py      # MCP Client 和 ClientManager
├── adapter.py     # 工具适配器 (MCP ↔ ITool)
├── server.py      # MCP Server (FastAPI)
└── config.py      # 配置管理
```

### 核心组件

#### 1. 类型定义 (types.py)

| 类型 | 用途 |
|------|------|
| `JSONRPCRequest` | JSON-RPC 请求 |
| `JSONRPCResponse` | JSON-RPC 响应 |
| `MCPTool` | MCP 工具定义 |
| `MCPToolResult` | 工具调用结果 |
| `MCPResource` | MCP 资源定义 |
| `MCPServerCapabilities` | 服务器能力 |
| `MCPServerConfig` | 服务器配置 |
| `MCPClientConfig` | 客户端配置 |

#### 2. 协议处理 (protocol.py)

- JSON-RPC 2.0 请求/响应编解码
- SSE (Server-Sent Events) 传输
- STDIO 传输

#### 3. 客户端 (client.py)

| 类 | 职责 |
|------|------|
| `MCPClient` | 单个 MCP 服务器连接管理 |
| `MCPClientManager` | 多服务器连接管理 |

#### 4. 适配器 (adapter.py)

| 类 | 职责 |
|------|------|
| `MCPToolAdapter` | MCP 工具 → 本地 ITool |
| `MCPToolExporter` | 本地 ITool → MCP 工具 |
| `MCPClientWrapper` | 批量注册 MCP 工具到注册表 |

## 使用方式

### 1. 连接外部 MCP 服务器

```python
from core.apps.mcp import MCPClientManager, MCPClientConfig

manager = MCPClientManager()

# SSE 连接
client = await manager.add_server(
    "my-server",
    MCPClientConfig(
        server_url="http://localhost:3000/mcp",
        transport=TransportType.SSE
    )
)

# STDIO 连接
client = await manager.add_server(
    "filesystem",
    MCPClientConfig(
        transport=TransportType.STDIO,
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/data"]
    )
)
```

### 2. 注册 MCP 工具到本地注册表

```python
from core.apps.mcp.adapter import MCPClientWrapper

wrapper = MCPClientWrapper(manager)
count = await wrapper.register_server_tools("my-server", tool_registry)
print(f"Registered {count} tools")
```

### 3. 启动 MCP 服务器（暴露本地工具）

```python
from core.apps.mcp import MCPServer

server = MCPServer(tool_registry)
await server.start(host="0.0.0.0", port=8080)
```

## 配置

### 服务器配置 (MCP Server)

```python
MCPServerConfig(
    name="my-server",
    transport=TransportType.SSE,  # 或 STDIO
    command="python",  # for stdio
    args=["server.py"],
    url="http://localhost:3000",  # for sse
    auth={"type": "bearer", "token": "..."}
)
```

### 客户端配置 (MCP Client)

```python
MCPClientConfig(
    server_url="http://localhost:3000/mcp",
    transport=TransportType.SSE,
    timeout=30000,  # ms
    auth={"type": "bearer", "token": "..."}
)
```

## 安全考虑

1. **URL 白名单** - HTTP 工具应配置允许的域名
2. **认证** - 支持 Bearer Token 认证
3. **超时控制** - 防止工具调用挂起
4. **响应大小限制** - 防止过大响应占用内存

## 待实现

- [ ] STDIO 传输的进程启动和管理
- [ ] MCP 服务器认证
- [ ] 工具缓存和刷新机制
- [ ] 连接池管理