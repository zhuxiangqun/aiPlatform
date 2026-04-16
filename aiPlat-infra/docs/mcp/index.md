# 📚 MCP 模块文档

> MCP（Model Context Protocol）协议客户端 - 基础设施层

---

## 🎯 模块定位

**职责**：提供 MCP 协议的底层实现，包括协议解析、连接管理、工具调用。

**依赖方向（以代码事实为准）**：
```
infra.mcp → infra 内部基础设施能力（可选）
core 层当前自带 MCP 实现（core/apps/mcp），并未直接依赖 infra.mcp
```

**与 core 层 tools 模块的关系**：
- infra.mcp：提供底层 MCP 协议能力（协议解析、连接管理、工具调用接口）
- core.tools：提供业务层工具能力（工具注册表、选择策略、执行编排）

---

## 🏗️ MCP 协议概述

### 什么是 MCP？

MCP（Model Context Protocol）是一种标准化协议，用于 AI 模型与外部工具/服务交互。

### 支持的能力

| 能力 | 说明 |
|------|------|
| `tools/list` | 列出 MCP Server 可用的工具 |
| `tools/call` | 调用指定工具 |
| `resources/list` | 列出可用资源 |
| `resources/read` | 读取资源内容 |
| `prompts/list` | 列出可用提示模板 |
| `prompts/get` | 获取提示模板 |

### 支持的传输方式（设计目标 vs 当前实现）

| 传输方式 | 说明 | 适用场景 |
|----------|------|----------|
| STDIO | 标准输入输出 | 本地 MCP Server（已实现 transport） |
| HTTP（JSON-RPC） | HTTP POST JSON-RPC（已实现 transport） | 远程 MCP Server（非流式） |
| HTTP/SSE | HTTP + Server-Sent Events（规划项） | 远程 MCP Server（流式） |
| WebSocket | 双向实时通信（已实现 transport） | 需要双向交互的场景 |

> 备注（As-Is）：当前仓库在 `infra/mcp/transport/stdio.py` 内同时提供 `STDIOTransport/HTTPTransport/WebSocketTransport`；但 **SSE streaming transport 尚未落地**，需新增实现与测试覆盖。

---

## 📖 接口定义

### MCPClient 接口

**位置**：`infra/mcp/base.py`

---

## ✅ 现状说明（避免 core/infra 双栈误用）

当前仓库内存在两套 MCP 相关实现：
- `aiPlat-core/core/apps/mcp/*`：core 内置 MCP 子系统（并与 ToolRegistry 集成）
- `aiPlat-infra/infra/mcp/*`：infra 层 MCP 基础设施实现（transport/client 等）

**统一口径（本轮文档修订后的设计决策）**：
1. 短期：core 以 `core/apps/mcp` 为主实现；infra.mcp 仅作为 infra 参考实现/基础设施能力，不作为 core 的直接依赖
2. 中期：若要收敛为单栈，需制定迁移计划（保留 thin wrapper、统一协议/transport、删除重复实现）


**接口定义**：

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `connect` | `server_url: str` | `None` | 连接到 MCP Server |
| `disconnect` | 无 | `None` | 断开连接 |
| `list_tools` | 无 | `List[Tool]` | 列出可用工具 |
| `call_tool` | `name: str`, `arguments: dict` | `ToolResult` | 调用工具 |
| `list_resources` | 无 | `List[Resource]` | 列出可用资源 |
| `read_resource` | `uri: str` | `ResourceContent` | 读取资源 |
| `health_check` | 无 | `bool` | 健康检查 |

### 数据模型

| 模型 | 字段 | 说明 |
|------|------|------|
| `Tool` | `name: str`, `description: str`, `inputSchema: dict` | 工具定义 |
| `ToolResult` | `content: Any`, `isError: bool` | 工具调用结果 |
| `Resource` | `uri: str`, `name: str`, `mimeType: str` | 资源定义 |
| `ResourceContent` | `uri: str`, `mimeType: str`, `content: Any` | 资源内容 |

---

## 🏭 工厂函数

### MCP 工厂

**位置**：`infra/mcp/factory.py`

**函数签名**：
```python
create_mcp_client(config: MCPConfig) -> MCPClient
```

**参数说明**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `config.type` | str | 传输类型：`stdio`, `http`, `websocket` |
| `config.server_command` | str | STDIO 模式：启动命令 |
| `config.server_url` | str | HTTP/WebSocket 模式：服务器地址 |
| `config.timeout` | int | 超时时间（秒）|
| `config.max_retries` | int | 最大重试次数 |
| `config.retry_delay` | int | 重试间隔（秒）|

**使用示例**：
```python
from infra.mcp import create_mcp_client

# STDIO 模式（本地 MCP Server）
config = MCPConfig(
    type="stdio",
    server_command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "./data"]
)
mcp = create_mcp_client(config)

# HTTP/SSE 模式（远程 MCP Server）
config = MCPConfig(
    type="http",
    server_url="http://localhost:3000/mcp"
)
mcp = create_mcp_client(config)
```

---

## ⚙️ 配置结构

### 配置文件示例

**位置**：`config/infra/mcp.yaml`

```yaml
# MCP Server 配置
mcp:
  # 默认超时配置
  timeout: 30
  max_retries: 3
  retry_delay: 1
  
  # MCP Servers 配置
  servers:
    - name: filesystem
      type: stdio
      command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "./data"]
      enabled: true
      
    - name: brave-search
      type: http
      url: http://localhost:3001/mcp
      enabled: false
      
    - name: slack
      type: http
      url: http://localhost:3002/mcp
      headers:
        Authorization: "Bearer ${SLACK_TOKEN}"
      enabled: false
```

---

## 🚀 使用示例

### 基础使用

```python
# 1. 创建 MCP 客户端
from infra.mcp import create_mcp_client
from infra.mcp.config import MCPConfig

config = MCPConfig(
    type="stdio",
    server_command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "./data"]
)
mcp = create_mcp_client(config)

# 2. 连接 MCP Server
await mcp.connect()

# 3. 列出可用工具
tools = await mcp.list_tools()
for tool in tools:
    print(f"Tool: {tool.name} - {tool.description}")

# 4. 调用工具
result = await mcp.call_tool(
    name="read_file",
    arguments={"path": "/data/README.md"}
)
print(f"Result: {result.content}")

# 5. 断开连接
await mcp.disconnect()
```

### MCP Server 管理

```python
from infra.mcp import MCPServerManager

# 创建 MCP Server 管理器
manager = MCPServerManager()

# 注册 MCP Server
manager.register(
    name="filesystem",
    config=MCPConfig(
        type="stdio",
        server_command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "./data"]
    )
)

manager.register(
    name="brave-search",
    config=MCPConfig(
        type="http",
        server_url="http://localhost:3001/mcp"
    )
)

# 获取所有工具（聚合多个 MCP Server）
all_tools = await manager.get_all_tools()

# 获取特定 Server 的工具
fs_tools = await manager.get_tools("filesystem")
```

---

## 📁 文件结构

```
infra/mcp/
├── __init__.py               # 模块导出
├── base.py                   # MCPClient 接口
├── factory.py                # create_mcp_client()
├── schemas.py                # 数据模型
├── client.py                # MCP Client 实现
└── transport/
    ├── stdio.py           # STDIO 传输
    ├── http_sse.py        # HTTP/SSE 传输
    └── websocket.py        # WebSocket 传输
```

---

## 🔧 扩展指南

### 添加新的 MCP Server 支持

1. **实现 MCP Server**：确保 MCP Server 遵循 MCP 协议
2. **配置连接信息**：在 `config/infra/mcp.yaml` 中添加配置
3. **注册到管理器**：使用 `MCPServerManager.register()` 注册

### 添加新的传输方式

1. **创建传输实现**：在 `infra/mcp/protocol/transport/` 下创建新文件
2. **实现传输接口**：
```python
class Transport(ABC):
    async def connect(self, config: dict): ...
    async def send(self, message: dict): ...
    async def receive(self) -> dict: ...
    async def close(self): ...
```
3. **注册到工厂**：在 `factory.py` 中添加新传输类型的分支

---

## ⚠️ 注意事项

1. **连接管理**：MCP 连接通常是长连接，需要妥善处理重连和心跳
2. **超时控制**：工具调用可能耗时较长，需要配置合理的超时时间
3. **错误处理**：MCP Server 可能返回错误，需要正确处理 `ToolResult.isError`
4. **资源清理**：使用完毕后务必调用 `disconnect()` 释放资源

---

## 🔗 相关链接

- **上级**：[← 返回 infra 索引](../index.md)
- **core tools 模块**：[→ aiPlat-core/tools](../aiPlat-core/docs/tools/index.md)
- **MCP 协议规范**：https://spec.modelcontextprotocol.io

---

*最后更新: 2026-04-11*
