# 工具系统增强（As-Is 对齐 + To-Be 规划）

> 扩展工具类型与增强权限控制，构建更强大的 Agent 执行能力

---

## 一句话定义

**工具系统增强**旨在扩展 Agent 的执行能力边界——通过新增工具类型（HTTP/Browser/Database/CodeExecution）和增强权限控制（资源级别权限、角色权限、调用审计），让 Agent 能处理更复杂的任务。

---

## 核心概念

### 当前系统能力（As-Is）

| 工具类型 | 状态 | 说明 |
|---------|------|------|
| CalculatorTool | ✅ | 数学计算 |
| SearchTool | ✅ | Web 搜索（实现以代码为准） |
| WebFetchTool | ✅ | 网页抓取（实际已注册） |
| HTTPClientTool | ✅ | HTTP API 调用（实际已注册） |
| FileOperationsTool | ⚠️ | 文件操作（若存在实现，需以启动注册与单测为准） |
| PermissionManager | ✅ | 用户-工具权限映射 |
| ToolRecaller | ✅ | 混合召回（Token+RAG） |

### 新增工具能力

| 工具类型 | 说明 | 优先级 |
|---------|------|--------|
| **HTTPClientTool** | REST API 调用 | P0 |
| **BrowserTool** | 浏览器自动化 | P0 |
| **DatabaseTool** | SQL 执行 | P1 |
| **CodeExecutionTool** | 代码执行沙箱 | P1 |
| **WebFetchTool** | 网页抓取 | P1 |

> 说明：以上“新增工具能力”章节属于 To-Be 规划；当前仓库中 `HTTPClientTool/WebFetchTool` 已落地，其它如 Browser/Database/CodeExecution 是否存在以代码与测试为准。

---

## 证据索引（Evidence Index｜抽样）

- 已落地工具：`core/server.py`（lifespan 注册 WebFetchTool/HTTPClientTool）
- Tool 基类封装：`core/apps/tools/base.py`
- 权限管理：`core/apps/tools/permission.py`

---

## 新增工具设计

### HTTPClientTool

```python
class HTTPClientTool(BaseTool):
    """HTTP 客户端工具 - 调用 REST API"""
    
    SUPPORTED_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]
    
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        参数:
            - url: str - 请求 URL
            - method: str - HTTP 方法
            - headers: Dict - 请求头
            - body: Any - 请求体 (POST/PUT)
            - timeout: int - 超时时间(毫秒)
        """
```

**安全限制**：
- 白名单域名（可配置）
- 仅允许 HTTP/HTTPS
- 最大响应大小：10MB
- 超时限制：30s

---

### BrowserTool

```python
class BrowserTool(BaseTool):
    """浏览器自动化工具 - 基于 Playwright"""
    
    SUPPORTED_ACTIONS = [
        "goto", "click", "type", "screenshot",
        "evaluate", "wait_for_selector", "get_text"
    ]
```

**功能**：
- 页面导航与交互
- 元素定位与操作
- 截图与内容提取
- JavaScript 执行

**安全限制**：
- 禁止 file:// 协议
- 禁止内网 IP（可配置白名单）
- 页面导航超时：30s
- 截图尺寸限制：1920x1080

---

### DatabaseTool

```python
class DatabaseTool(BaseTool):
    """数据库工具 - SQL 执行"""
    
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        参数:
            - operation: str - "query" | "execute" | "schema"
            - connection: str - 连接字符串别名
            - sql: str - SQL 语句
        """
```

**安全限制**：
- 只读/写入分离（配置控制）
- 危险操作拦截（DROP, TRUNCATE, DELETE 无 WHERE）
- 查询结果限制：1000 行
- 超时限制：60s

---

### CodeExecutionTool

```python
class CodeExecutionTool(BaseTool):
    """代码执行沙箱 - 安全执行 Python/JS"""
    
    SUPPORTED_LANGUAGES = ["python", "javascript"]
    
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        参数:
            - language: str - "python" | "javascript"
            - code: str - 要执行的代码
            - timeout: int - 超时时间(毫秒)
        """
```

**安全限制**：
- 资源限制：CPU 50%, 内存 512MB
- 网络隔离（可选）
- 禁止文件系统访问（除临时目录）
- 禁止子进程 spawn

---

## 权限控制增强

### 资源级别权限

```python
@dataclass
class ResourcePermission:
    """资源级别权限"""
    resource_type: str  # "file" | "api" | "database" | "command"
    resource_pattern: str  # 正则匹配
    permission: Permission  # READ | WRITE | EXECUTE
    
# 示例
ResourcePermission(
    resource_type="file",
    resource_pattern=r"/workspace/src/.*\.py",
    permission=Permission.READ
)
```

### 角色权限系统

```python
class Role:
    """角色定义"""
    name: str
    permissions: List[ResourcePermission]
    inherits: List[str]  # 继承其他角色

# 预定义角色
ROLES = {
    "developer": Role(
        name="developer",
        permissions=[
            ResourcePermission("file", r"/workspace/.*", Permission.READ),
            ResourcePermission("file", r"/workspace/src/.*", Permission.WRITE),
            ResourcePermission("api", r"https://api\.example\.com/.*", Permission.READ),
        ]
    ),
    "analyst": Role(
        name="analyst",
        permissions=[
            ResourcePermission("file", r"/workspace/data/.*", Permission.READ),
            ResourcePermission("database", r"analytics_.*", Permission.READ),
        ]
    )
}
```

### 工具调用审计

```python
@dataclass
class ToolAuditLog:
    """工具调用审计日志"""
    timestamp: datetime
    user_id: str
    agent_id: str
    tool_name: str
    parameters: Dict[str, Any]
    result: ToolResult
    resource_accessed: List[str]
    permission_checked: bool
    
class ToolAuditLogger:
    """工具调用审计记录器"""
    
    async def log(self, audit: ToolAuditLog) -> None:
        """记录审计日志"""
        
    async def query(
        self, 
        user_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[ToolAuditLog]:
        """查询审计日志"""
```

---

## 与现有系统集成

### ToolRegistry 集成

```python
class ToolRegistry:
    async def register_tool(self, tool: BaseTool) -> None:
        # 现有逻辑
        
    async def register_http_tool(self, config: HTTPClientConfig) -> None:
        """注册 HTTP 工具"""
        
    async def register_browser_tool(self) -> None:
        """注册浏览器工具"""
        
    async def register_database_tool(self, config: DatabaseConfig) -> None:
        """注册数据库工具"""
        
    async def register_code_tool(self, config: CodeExecutionConfig) -> None:
        """注册代码执行工具"""
```

### Hook 集成

```python
# PreToolUse Hook - 资源级别权限检查
@hook("PreToolUse")
async def check_resource_permission(tool_call: ToolCall) -> HookResult:
    if tool_call.resource_pattern:
        has_permission = await permission_manager.check_resource(
            user_id=tool_call.user_id,
            resource_type=tool_call.resource_type,
            resource_pattern=tool_call.resource_pattern,
            permission=tool_call.required_permission
        )
        if not has_permission:
            return HookResult(approved=False, reason="资源权限不足")
    return HookResult(approved=True)
```

---

## 配置示例

```yaml
# config/tools.yaml
tools:
  http:
    enabled: true
    whitelist:
      - "https://api.example.com/*"
      - "https://internal.company.com/*"
    timeout: 30000
    max_response_size: 10485760  # 10MB
    
  browser:
    enabled: true
    block_internal_ips: true
    navigation_timeout: 30000
    screenshot_max_size: 1920x1080
    
  database:
    enabled: true
    connections:
      - name: "analytics"
        type: "postgresql"
        host: "localhost"
        database: "analytics"
        # 只读连接
        readonly: true
      - name: "app"
        type: "mysql"
        host: "localhost"
        database: "app"
        # 可读写
        readonly: false
        
  code:
    enabled: true
    max_cpu_percent: 50
    max_memory_mb: 512
    allowed_languages:
      - "python"
      - "javascript"
    network_isolation: true

# 权限配置
permissions:
  roles:
    developer:
      - resource_type: "file"
        pattern: "/workspace/src/.*"
        permission: "write"
      - resource_type: "api"
        pattern: "https://api.example.com/.*"
        permission: "read"
        
    analyst:
      - resource_type: "file"
        pattern: "/workspace/data/.*"
        permission: "read"
      - resource_type: "database"
        pattern: "analytics_.*"
        permission: "read"
```

---

## 相关文档

- [工具系统](./tools/index.md) - 基础工具接口
- [安全设计](./harness/security.md) - 安全审计
- [权限管理](./harness/security.md#权限控制)

---

*最后更新: 2026-04-14*
