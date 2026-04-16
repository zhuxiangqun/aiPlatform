# MCP 协议集成（设计真值：以代码事实为准）

> 提供 Model Context Protocol (MCP) 支持，实现与外部工具生态的无缝对接

---

## 一句话定义

**MCP (Model Context Protocol)** 是 AI Agent 与外部工具/服务交互的标准协议。通过实现 MCP，系统可以：
- 调用外部 MCP 服务器提供的工具
- 将本地工具通过 MCP 协议暴露给外部 Agent
- 与 Claude Code 生态无缝对接

---

## 核心概念

### MCP 协议架构

```
┌─────────────┐      JSON-RPC      ┌─────────────┐
│   MCP       │ ◄──────────────►  │   MCP       │
│   Client    │   HTTP/SSE        │   Server    │
└─────────────┘                   └─────────────┘
       │                                  │
       ▼                                  ▼
┌─────────────┐                   ┌─────────────┐
│  本地工具   │                   │ 外部服务    │
│ (ITool)     │                   │ (Filesystem │
└─────────────┘                   │  Database   │
                                   │  Git, etc)  │
                                   └─────────────┘
```

### 传输模式

| 模式 | 说明 | 适用场景 |
|------|------|---------|
| **stdio** | 标准输入输出通信 | 本地进程（如 `npx @modelcontextprotocol/server-filesystem`） |
| **SSE** | Server-Sent Events over HTTP | 远程服务（如云端 MCP 服务器） |

> 实现状态提示（As-Is）：
> - core 内 MCP **Server** 已支持 SSE + JSON-RPC over HTTP（`core/apps/mcp/server.py`）。
> - core 内 MCP **Client** 当前以 **SSE transport** 为主；STDIO client 的“spawn 进程并握手”仍属于 To-Be（需补齐实现与测试）。

---

## 架构设计

### 模块结构

```
core/apps/mcp/
├── __init__.py              # 模块入口
├── client.py                # MCP Client (连接外部服务器)
├── server.py                # MCP Server (暴露本地工具)
├── adapter.py              # 工具适配器 (MCP Tools ↔ ITool)
├── protocol.py              # JSON-RPC 协议处理
├── types.py                # MCP 协议数据类型
└── config.py               # MCP 配置管理
```

---

## MCP Client 设计

### 连接管理

```python
class MCPClient:
    """MCP 客户端 - 连接外部 MCP 服务器"""
    
    async def connect(self, server_url: str, transport: str = "sse") -> None:
        """连接 MCP 服务器"""
        
    async def disconnect(self) -> None:
        """断开连接"""
        
    async def list_tools(self) -> List[MCPTool]:
        """列出可用工具"""
        
    async def call_tool(self, name: str, arguments: Dict) -> MCPResult:
        """调用工具"""
```

### 自动重连与故障恢复

- **指数退避重连**：失败后 1s → 2s → 4s → 8s... 重试
- **健康检查**：定期 ping 服务器确认可用性
- **工具失效标记**：服务器不可用时标记工具为 unavailable

---

## MCP Server 设计

### 端点设计

| 端点 | 方法 | 功能 |
|------|------|------|
| `/mcp` | GET | SSE 流式连接 |
| `/mcp` | POST | JSON-RPC 调用 |
| `/mcp/tools` | GET | 列出可用工具 |
| `/mcp/resources` | GET | 列出资源 |

### 协议方法

| 方法 | 说明 |
|------|------|
| `initialize` | 初始化握手，获取服务器能力 |
| `tools/list` | 列出可用工具 |
| `tools/call` | 调用工具 |
| `resources/list` | 列出资源 |
| `resources/read` | 读取资源 |

---

## 工具适配器

### MCP Tools → ITool 转换

```python
class MCPToolAdapter:
    """将 MCP Tool 转换为本地 ITool"""
    
    def __init__(self, mcp_tool: MCPTool, client: MCPClient):
        self._tool = mcp_tool
        self._client = client
        
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """执行 MCP 工具调用"""
        result = await self._client.call_tool(
            self._tool.name, 
            params
        )
        return ToolResult(
            success=result.isError is False,
            output=result.content,
            error=result.isError
        )
```

### 本地工具 → MCP 暴露

反向地，将本地 `ITool` 暴露为 MCP 工具：

```python
class LocalToolExporter:
    """将本地工具导出为 MCP 工具"""
    
    def export(self, tool: ITool) -> MCPTool:
        """转换本地工具为 MCP 工具"""
```

---

## 安全设计

### OAuth 2.1 PKCE 认证

```python
class MCPAuthHandler:
    """MCP 认证处理"""
    
    async def authenticate(self, request: Request) -> bool:
        """验证请求合法性"""
        
    async def refresh_token(self, refresh_token: str) -> str:
        """刷新访问令牌"""
```

### 恶意包扫描

MCP 服务器返回的工具可能包含恶意代码，需扫描：
- Prompt injection 模式
- 文件系统访问限制
- 网络请求白名单
- 命令执行限制

---

## 与现有系统集成

### 工具注册表集成

```python
# 在 ToolRegistry 中添加 MCP 工具
class ToolRegistry:
    async def register_mcp_server(
        self, 
        server_url: str, 
        transport: str = "sse"
    ) -> None:
        """注册 MCP 服务器工具"""
        client = MCPClient()
        await client.connect(server_url, transport)
        
        # 获取工具并注册
        tools = await client.list_tools()
        for tool in tools:
            adapter = MCPToolAdapter(tool, client)
            self.register(adapter)
```

### Hook 集成

```python
# PreToolUse Hook 检查 MCP 工具权限
@hook("PreToolUse")
async def check_mcp_tool_permission(tool_call: ToolCall) -> HookResult:
    if tool_call.source == "mcp":
        # MCP 工具额外的安全检查
        await validate_mcp_tool_schema(tool_call)
    return HookResult(approved=True)
```

---

## 配置示例

### 配置 MCP 服务器

```yaml
# config/mcp.yaml
mcp:
  servers:
    - name: "filesystem"
      type: "stdio"
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
      
    - name: "github"
      type: "sse"
      url: "http://localhost:8080/mcp"
      auth:
        type: "oauth2"
        client_id: "your-client-id"
        
    - name: "postgres"
      type: "sse"
      url: "http://localhost:8081/mcp"
      # 数据库连接配置
```

### 环境变量

```bash
# MCP 相关环境变量
MCP_SERVER_URL=http://localhost:8000/mcp
MCP_TRANSPORT=sse
MCP_AUTH_ENABLED=true
```

---

## 相关文档

- [工具系统](../tools/index.md) - 基础工具接口
- [Harness 框架](../harness/index.md) - Agent 运行环境
- [安全设计](../harness/security.md) - 安全审计

---

## 证据索引（Evidence Index｜抽样）

- MCP Server：`core/apps/mcp/server.py`（`/mcp` SSE 与 JSON-RPC endpoints）
- MCP Client：`core/apps/mcp/client.py`（SSE handler；STDIO client 仍需补齐 spawn 路径）
- MCP Tool 适配：`core/apps/mcp/adapter.py`（`MCPToolAdapter` → `BaseTool`）

---

*最后更新: 2026-04-14*
